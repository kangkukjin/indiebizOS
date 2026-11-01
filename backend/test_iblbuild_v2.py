"""코퍼스의 중복 원문을 한 번 검사해도 행별 진단과 다음 검사 신선도는 보존한다."""
from pathlib import Path

import pytest


@pytest.fixture
def corpus_check(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    import iblbuild_v2
    import ibl_v2_adapters
    import ibl_v2_learning
    import ibl_v2_store

    calls, loads = [], []
    registry = {}
    original = ibl_v2_learning.check_source

    def check(source, function_body=False, **kwargs):
        calls.append((source, function_body))
        return original(source, function_body, **kwargs)

    def load():
        loads.append(True)
        return registry.copy()

    monkeypatch.setattr(ibl_v2_adapters, 'load_registry', load)
    monkeypatch.setattr(ibl_v2_store, 'definitions', lambda: {})
    monkeypatch.setattr(ibl_v2_learning, 'check_source', check)
    return iblbuild_v2, calls, loads, registry


def test_duplicate_sources_keep_every_failure_origin_and_match_uncached(corpus_check):
    gate, calls, loads, _ = corpus_check
    rows = [
        ('a.json', {'ibl_code': 'return 7', 'intent': '첫 표현'}),
        ('b.json', {'ibl_code': 'return 7', 'intent': '다른 표현'}),
        ('c.json', {'ibl_code': 'return $missing'}),
        ('ibl_usage.db', {'ibl_code': 'return $missing'}),
        ('d.json', {'ibl_code': 'return 8'}),
    ]
    cached, session = [], {}
    for origin, entry in rows:
        gate.check_v2_corpus(entry['ibl_code'], entry, cached, origin, session)
    assert len(calls) == 3 and len(loads) == 1
    assert len(cached) == 2
    assert cached[0].startswith('c.json:') and cached[1].startswith('ibl_usage.db:')
    uncached = []
    for origin, entry in rows:
        gate.check_v2_corpus(entry['ibl_code'], entry, uncached, origin)
    assert cached == uncached
    assert len(calls) == 8


def test_function_body_mode_is_part_of_compile_input(corpus_check):
    gate, calls, _, _ = corpus_check
    issues, session = [], {}
    for entry in ({}, {'alias': 'one'}, {'alias': 'two'}, {'category': 'phrase'}):
        gate.check_v2_corpus('return 7', entry, issues, 'row', session)
    assert calls == [('return 7', False), ('return 7', True)]
    assert len(issues) == 3 and all('저장본은 하나의 [def:' in i for i in issues)


@pytest.mark.parametrize('edition', [1, '2', True, None])
def test_every_row_checks_edition_even_when_its_source_was_cached(corpus_check, edition):
    gate, calls, _, _ = corpus_check
    issues, session = [], {}
    gate.check_v2_corpus('return 7', {}, issues, 'valid', session)
    gate.check_v2_corpus('return 7', {'edition': edition}, issues, 'invalid', session)
    assert calls == [('return 7', False)]
    assert len(issues) == 1 and issues[0].startswith('invalid:')
    assert 'EDITION_' in issues[0]


def test_next_corpus_pass_rechecks_changed_contract(corpus_check, monkeypatch):
    gate, calls, loads, registry = corpus_check
    import iblbuild_validators
    from ibl_v2_adapters import Adapter

    code = '[probe:read]{value:1}'
    monkeypatch.setattr(iblbuild_validators, '_corpus_entries', lambda *a, **k: iter([
        ('a.json', {'ibl_code': code}), ('ibl_usage.db', {'ibl_code': code}),
    ]))
    def adapter(kind):
        return Adapter({'version': 1, 'params': {'value': kind}, 'required': ['value'],
                        'result': 'Number', 'effects': ['pure']}, lambda *a: 1)

    registry['probe:read'] = adapter('Number')
    assert iblbuild_validators.validate_corpus_vocab({}, Path('.')) == []
    registry['probe:read'] = adapter('Text')
    issues = iblbuild_validators.validate_corpus_vocab({}, Path('.'))
    assert len(calls) == 2 and len(loads) == 2
    assert len(issues) == 2 and all('Text' in i for i in issues)


def test_unexpected_checker_failure_is_reported_and_not_memoized(corpus_check, monkeypatch):
    gate, _, _, _ = corpus_check
    import ibl_v2_learning
    attempts = []

    def check(*a, **k):
        attempts.append(True)
        if len(attempts) == 1:
            raise OSError('temporary read failure')
        return None

    monkeypatch.setattr(ibl_v2_learning, 'check_source', check)
    issues, session = [], {}
    gate.check_v2_corpus('return 7', {}, issues, 'first', session)
    gate.check_v2_corpus('return 7', {}, issues, 'second', session)
    assert len(attempts) == 2
    assert len(issues) == 1 and 'temporary read failure' in issues[0]


def test_build_index_isolated_by_consumer_root_and_build(tmp_path, monkeypatch):
    import json
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    import iblbuild_derive as derive

    def write(root, value):
        path = root / 'data/packages/installed/tools/probe/tool.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'tools': [{'name': 'probe', 'params': {'value': value}}]}))
        return path

    path = write(tmp_path, 1)
    other = tmp_path / 'other'
    write(other, 2)
    original = derive._build_tool_index
    loads = []

    def build(root):
        loads.append(root)
        return original(root)

    monkeypatch.setattr(derive, '_build_tool_index', build)
    with derive.tool_index_session():
        first = derive.build_tool_index(tmp_path)
        first['probe'][1]['params']['value'] = 99
        assert derive.build_tool_index(tmp_path)['probe'][1]['params']['value'] == 1
        assert derive.build_tool_index(other)['probe'][1]['params']['value'] == 2
    assert len(loads) == 2
    write(tmp_path, 3)
    with pytest.raises(RuntimeError), derive.tool_index_session():
        assert derive.build_tool_index(tmp_path)['probe'][1]['params']['value'] == 3
        raise RuntimeError('interrupted build')
    assert derive._tool_indexes.get() is None
    path.unlink()
    assert derive.build_tool_index(tmp_path) == {}


def test_template_duplicates_preserve_locations_and_next_pass_freshness(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    import iblbuild_appview as gate
    import ibl_v2_adapters as adapters
    import ibl_v2_compile as compiler
    import ibl_v2_store as store

    def adapter(kind):
        return adapters.Adapter({'version': 1, 'params': {'value': kind},
                                 'result': 'Number', 'effects': ['pure']}, lambda *a: 1)

    registry = {'probe:read': adapter('Number')}
    calls = []
    compile_program = compiler.compile_program

    def compile_source(source, *args, **kwargs):
        calls.append(source)
        return compile_program(source, *args, **kwargs)

    good = '[probe:read]{value:1}'
    bad = '[probe:read]{value:"x"}'
    rows = [('a', {'action': good}), ('b', {'action': good}),
            ('c', {'action': bad}), ('d', {'action': bad})]
    monkeypatch.setattr(gate, '_edition2_blocks', lambda _: rows)
    monkeypatch.setattr(adapters, 'load_registry', lambda *a: registry.copy())
    monkeypatch.setattr(store, 'definitions', lambda: {})
    monkeypatch.setattr(compiler, 'compile_program', compile_source)
    errors, warnings = gate.check_app_templates_edition2({}, Path('.'))
    assert calls == [good, bad] and warnings == []
    assert len(errors) == 2 and errors[0].startswith('c:') and errors[1].startswith('d:')
    registry['probe:read'] = adapter('Text')
    errors, warnings = gate.check_app_templates_edition2({}, Path('.'))
    assert calls == [good, bad, good, bad] and warnings == []
    assert len(errors) == 2 and errors[0].startswith('a:') and errors[1].startswith('b:')


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
