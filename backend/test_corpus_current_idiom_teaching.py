"""Current calls must see their resolved contract, not old same-name evidence."""
import boot_paths  # noqa: F401
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
import ibl_access
from test_ibl_v2_assets import memory  # noqa: F401 — isolated DB/FTS/vector fixture
from ibl_v2_adapters import Adapter
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]
LESSONS = json.loads((ROOT / 'data/idioms/current_call_lessons.json').read_text())['idioms']


def db():
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE ibl_examples(intent,ibl_code,success_count,fail_count,topic,alias,returns,signature,always_on,updated_at)')
    return conn


def test_same_name_native_contract_does_not_inherit_legacy_success():
    with db() as conn:
        old = ('옛 뜻', '$return=$목록', 99, 1, '목록', 'f', 'items', '목록', 1, '2026-01')
        native = ('현재 뜻', '#!ibl edition=2\n[def:f]($목록){return $목록}', 0, 0, '목록', 'f', 'List', '목록', 0, '2026-02')
        conn.executemany('INSERT INTO ibl_examples VALUES (?,?,?,?,?,?,?,?,?,?)', [old, native])
        result = ibl_access._current_idiom_rows(conn, [old[:8]], 'returns', 'signature')
        assert result == [native[:8]]
        assert conn.execute('SELECT success_count FROM ibl_examples WHERE always_on=1').fetchone()[0] == 99


def test_only_selected_names_are_exposed_and_legacy_has_no_current_pipe_slot():
    with db() as conn:
        old = ('뜻', '$return=$목록', 3, 0, '목록', 'f', 'items', '목록', 1, '2026-01')
        conn.execute('INSERT INTO ibl_examples VALUES (?,?,?,?,?,?,?,?,?,?)', old)
        result = ibl_access._current_idiom_rows(conn, [old[:8]], 'returns', 'signature')
        assert result[0][6] == 'Record'
        assert ibl_access._authoring_pipe_note(result[0][1]) == ''
        assert conn.execute('SELECT returns FROM ibl_examples').fetchone()[0] == 'items'


def test_latest_legacy_body_owns_the_signature_and_statistics():
    with db() as conn:
        old = ('옛 뜻', '$return=$목록', 99, 0, '목록', 'f', 'items', '목록', 1, '2026-01')
        latest = ('새 뜻', '$return=$새목록', 0, 0, '목록', 'f', 'items', '새목록', 0, '2026-02')
        conn.executemany('INSERT INTO ibl_examples VALUES (?,?,?,?,?,?,?,?,?,?)', [old, latest])
        rows = ibl_access._current_idiom_rows(conn, [old[:8]], 'returns', 'signature')
        assert rows[0][1] == latest[1] and rows[0][2] == 0
        assert rows[0][7] == '새목록' and rows[0][6] == 'Record'


def test_current_pipe_slot_disallows_duplicate_argument():
    code = '#!ibl edition=2\n[def:f]($목록,$개수){return $목록}'
    assert '목록' in ibl_access._authoring_pipe_note(code)
    assert '동시 명시 금지' in ibl_access._authoring_pipe_note(code)
    plan = compile_program(code + '\n[] >> [fn:f]{목록:[],개수:0}')
    assert any(i['code'] == 'PIPE_COLLISION' for i in plan.issues)


def test_changed_definition_hides_stale_lesson():
    source = '$return=$목록'
    lesson = {'source_edition': 1, 'source_sha256': hashlib.sha256(source.encode()).hexdigest()}
    assert ibl_access._current_lesson(lesson, source) == lesson
    assert ibl_access._current_lesson(lesson, source + '; [self:read]{path:"x"}') == {}


def test_current_example_header_does_not_comment_out_the_whole_example():
    source = '#!ibl edition=2\n[def:f]($목록){return $목록}'
    r = ('뜻', source, 0, 0, '목록', 'f', 'List', '목록')
    lines = ibl_access._idiom_lines(r, {'inputs': '목록', 'example': '#!ibl edition=2\nreturn [fn:f]{목록:[]}'}, authoring=True)
    assert '  조합 예: return [fn:f]{목록:[]}' in lines
    assert not any('#!ibl edition=2;' in line for line in lines)


@pytest.mark.parametrize('lesson', LESSONS, ids=lambda x: x['name'])
def test_current_call_examples_compile_and_preserve_adapter_result(lesson):
    """Only the named callable is stubbed. Its complete return is preserved."""
    from workflow_contract import call_signature
    catalog = json.loads((ROOT / 'data/idioms/curated.json').read_text())
    legacy = {e['name']: e['body'] for e in catalog['idioms']}
    seeds = json.loads((ROOT / 'data/idioms/ibl_v2_seeds.json').read_text())
    native = {e['alias']: e['ibl_code'] for e in seeds if e.get('alias')}
    source = native[lesson['name']] if lesson['source_edition'] == 2 else legacy[lesson['name']]
    assert hashlib.sha256(source.encode()).hexdigest() == lesson['source_sha256']
    seen = []
    if lesson['source_edition'] == 2:
        import sys
        sys.path.insert(0, str(ROOT / 'scripts'))
        from probe_corpus_v2_values import pure_registry
        import yaml
        catalog = yaml.safe_load((ROOT / 'data/ibl_nodes.yaml').read_text())
        contracts = {n+':'+a: cfg['callable_contract'] for n,node in catalog['nodes'].items()
                     for a,cfg in node['actions'].items() if cfg.get('callable_contract')}
        registry = pure_registry(contracts)
        plan = compile_program(lesson['example'], registry, definitions=native)
        result = Runtime(plan).run()
        assert result['success'] and isinstance(result['value'], list)
        assert result['value'] == ([{'id': '007'}] if lesson['name'] == '열추려보기' else [{'id': 'b'}])
    else:
        keys = call_signature(source)
        payload = {'items': [{'id': '007'}], 'match_info': {'total_matches': 1}, 'receipt': 'fixture'}
        def run(rt, args):
            seen.append(args)
            return payload
        contract = {'version': 1, 'params': {k: 'Unknown' for k in keys}, 'required': keys,
                    'result': 'Record', 'effects': ['unknown'], 'compatibility': 'legacy-function/1'}
        plan = compile_program(lesson['example'], {'fn:' + lesson['name']: Adapter(contract, run)})
        result = Runtime(plan).run()
        assert not plan.issues and result['success']
        assert result['value'] == payload and len(seen) == 1
        assert set(seen[0]) == set(keys)


def test_real_legacy_body_keeps_match_diagnostics_in_its_envelope(memory):
    from ibl_v2_entry import handle_request
    catalog = json.loads((ROOT / 'data/idioms/curated.json').read_text())['idioms']
    body = next(e['body'] for e in catalog if e['name'] == '본문에서찾기')
    lesson = next(e for e in LESSONS if e['name'] == '본문에서찾기')
    assert memory.add_examples_batch([{'intent': '문단에서 패턴과 문맥 찾기', 'ibl_code': body,
                                      'alias': lesson['name'], 'category': 'phrase'}]) == 1
    result = handle_request({'edition': 2, 'code': lesson['example']})
    assert result['success'], result
    envelope = result['value']
    assert [r['text'] for r in envelope['items']] == ['앞 문단', '핵심 근거']
    assert all(r['url'] == 'https://example.com/' for r in envelope['items'])
    # Only items/count are promoted. The full result owns the richer metadata.
    assert 'match_info' in json.loads(envelope['final_result'])
    assert 'results' in envelope


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
