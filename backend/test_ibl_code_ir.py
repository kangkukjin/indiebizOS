"""실행 코어 불변식: 값 보존·알파 이름변경·함수 추출·행 격리·전송 왕복."""
import copy
import json
import random
import sys
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ibl_boundary_probe import probe
from ibl_boundary_cases_round3 import each
from ibl_boundary_cases import literal as q
from ibl_code_ir import compile_code, bind_code, Code, Literal, pack, unpack


def values():
    fixed = ['', '007', 0, False, None, [], {},
             '$it.id ${x.items.*.v} {{_step_0_result.items}} {{_prev_result}}',
             "'\"\\\n# } [def:fake] $return = 999", {'a': ['$items', '$x', False]}]
    rng = random.Random(20260908)
    alphabet = "abc한글'\"\\\n\t$[]{}:#0123"
    return fixed + [''.join(rng.choice(alphabet) for _ in range(rng.randrange(2, 55)))
                    for _ in range(20)]


@pytest.mark.parametrize('value', values())
@pytest.mark.parametrize('shape', ['direct', 'renamed', 'nested', 'function', 'pipeline', 'parallel'])
def test_value_survives_equivalent_program_shapes(value, shape):
    alias = '행' if shape == 'renamed' else 'it'
    body = '[table:take]{items:[{v:$' + alias + '.v}],n:1}'
    rows = [{'v': value}]
    if shape == 'nested':
        body = each([{}], body, **{'as': 'child'})
    if shape == 'function':
        code = '[def:f]{$return=' + each([{}], '[table:take]{items:[{v:$입력}],n:1}') + '}\n[fn:f]{입력:' + q(value) + '}'
    elif shape == 'pipeline':
        code = '$r=[table:take]{items:' + q(rows) + ',n:1}\n' + each([{}], '[table:take]{items:[{v:${r.items.0.v}}],n:1}')
    else:
        if shape == 'parallel':
            rows = rows * 4
        code = each(rows, body, **{'as': alias, 'parallel': 4 if shape == 'parallel' else 1})
    expected = [{'v': value}] * (4 if shape == 'parallel' else 1)
    result = probe(dict(id='invariant', code=code, expected=expected, error=False, contains=None))
    assert result['ok'], (code, result.get('actual'), result.get('error_text'))


def test_rows_bind_without_parsing_again(monkeypatch):
    import ibl_parser
    plan = compile_code('[table:take]{items:[{v:$it.v}],n:1}')
    before = pack(plan)
    monkeypatch.setattr(ibl_parser, 'parse_function_body', lambda *_: pytest.fail('행 바인딩 중 재파싱'))
    for value in values():
        bound = bind_code(plan, lambda name, path: (True, value))
        assert bound.tree[0]['params']['items'][0]['v'] == value
    assert pack(plan) == before


def test_compiled_program_and_captures_survive_json_and_copy():
    plan = bind_code('[table:take]{items:[{v:$outer, row:$it.id}],n:1}',
                     lambda name, path: (True, "$it.id 'quoted'") if name == 'outer' else (False, None))
    for restored in [copy.deepcopy(plan), unpack(json.loads(json.dumps(pack(plan))))]:
        bound = bind_code(restored, lambda name, path: (True, 7) if name == 'it' else (False, None))
        assert bound.tree[0]['params']['items'] == [{'v': "$it.id 'quoted'", 'row': 7}]
        assert isinstance(bound.tree[0]['params']['items'][0]['v'], Literal)


def test_partial_string_binding_does_not_rescan_inserted_data():
    plan = compile_code('[table:take]{items:[{v:"${a} / ${b}"}],n:1}')
    first = bind_code(plan, lambda n, p: (True, '${b}') if n == 'a' else (False, None))
    second = bind_code(first, lambda n, p: (True, 'done') if n == 'b' else (False, None))
    assert second.tree[0]['params']['items'] == [{'v': '${b} / done'}]


def test_wire_parameters_preserve_code_and_values():
    from ibl_code_ir import transport_params, receive_params
    from ibl_exec_each import _execute_table_each
    import workflow_engine
    from unittest.mock import patch
    plan = bind_code('[table:take]{items:[{v:$outer,row:$it.id}],n:1}',
                     lambda n, p: (True, ['$items', "'quote'"]) if n == 'outer' else (False, None))
    sent = transport_params({'items': [{'id': 2}], 'do': plan})
    received = receive_params(json.loads(json.dumps(sent)))
    assert isinstance(received['do'], Code)
    observed = []
    def execute(steps, *a, **kw):
        observed.extend(steps[0]['params']['items'])
        return {'success': True, 'final_result': {'items': observed}}
    with patch.object(workflow_engine, 'execute_pipeline', execute):
        out = _execute_table_each(received, '.')
    assert out['success'] and observed == [{'v': ['$items', "'quote'"], 'row': 2}]


def test_unknown_wire_version_is_rejected():
    from ibl_code_ir import receive_params
    with pytest.raises(ValueError, match='버전'):
        receive_params({'_ibl_ir': {'version': 999}})


@pytest.mark.parametrize('raw', ['1e-3', '-2.5e+4', '0x10', '.25', '+3',
                                '"\\uD83D\\uDE80"', "'\\x41'", '"\\d+"',
                                '[1e2, {v:"\\uD83D\\uDE80"}]', '[1, /* { ignored } */ 2]',
                                '{a:1/* note */, /* other */ b:2}'])
def test_literal_grammar_matches_existing_parser(raw):
    from ibl_parser import parse_function_body
    code = '[table:take]{items:[{v:' + raw + '}],n:1}'
    expected = parse_function_body(code)[0]['params']['items']
    assert compile_code(code).tree[0]['params']['items'] == expected


def test_live_execution_does_not_use_legacy_source_substitution(monkeypatch):
    import ibl_code_binding
    monkeypatch.setattr(ibl_code_binding, 'bind_scoped_code', lambda *a, **k: pytest.fail('옛 코드 치환 경로 사용'))
    code = '$r=[table:take]{items:[{v:"outer"}],n:1}\n' + each(
        [{'v': "$it.no 'quote'"}], '[table:take]{items:[{outer:${r.items.0.v},row:$it.v}],n:1}')
    out = probe(dict(id='no_legacy', code=code,
                     expected=[{'outer': 'outer', 'row': "$it.no 'quote'"}], error=False, contains=None))
    assert out['ok'], out


@pytest.mark.parametrize('nested', [False, True])
def test_outer_and_local_step_zero_are_different_scopes(nested):
    body = ('$local=[table:take]{items:[{v:7}],n:1}\n'
            '[table:take]{items:[{a:${outer.items.0.v},b:${local.items.0.v}}],n:1}')
    if nested:
        body = each([{}], body)
    code = '$outer=[table:take]{items:[{v:99}],n:1}\n' + each([{}], body)
    out = probe(dict(id='scope_ids', code=code, expected=[{'a': 99, 'b': 7}], error=False, contains=None))
    assert out['ok'], out


def test_outer_result_and_row_in_expression_use_values():
    code = '$outer=[table:take]{items:[{v:99}],n:1}\n' + each(
        [{'n': 3}], '$x=${outer.items.0.v} + $it.n\n[table:take]{items:[{v:$x}],n:1}')
    out = probe(dict(id='capture_expr', code=code, expected=[{'v': '102'}], error=False, contains=None))
    assert out['ok'], (out['actual'], out['error_text'])


@pytest.mark.parametrize('parallel', [1, 4])
def test_hundred_rows_parse_the_body_once(monkeypatch, parallel):
    import ibl_parser
    import workflow_engine
    from ibl_exec_each import _execute_table_each
    original = ibl_parser.parse_with_vars
    calls = []
    def parse(*args, **kwargs):
        calls.append(args[0])
        return original(*args, **kwargs)
    monkeypatch.setattr(ibl_parser, 'parse_with_vars', parse)
    monkeypatch.setattr(workflow_engine, 'execute_pipeline', lambda steps, *a, **k:
                        {'success': True, 'final_result': {'items': steps[0]['params']['items']}})
    rows = [{'v': n} for n in range(100)]
    out = _execute_table_each({'items': rows, 'limit': 100, 'parallel': parallel,
                              'do': '[table:take]{items:[{v:$it.v}],n:1}'}, '.')
    assert out['success'] and out['items'] == rows
    assert len(calls) == 1


def test_episode3148_failed_sentence_replays_with_fixed_external_responses(monkeypatch, tmp_path):
    import hashlib
    import ibl_engine
    import episode_logger
    import workflow_engine
    from ibl_parser import parse
    from ibl_exec_each import _execute_table_each
    from idiom_experiment_worker import load
    from tool_context import ToolContext
    root = Path(__file__).resolve().parents[1]
    fixture = json.loads((root / 'docs/experiments/ibl_ir_episode3148_fixture.json').read_text())
    assert hashlib.sha256(fixture['code'].encode()).hexdigest() == fixture['code_sha256']
    dataops = load('_ir_replay_dataops', root / 'data/packages/installed/tools/data-ops/handler.py')
    original = ibl_engine._execute_ibl_impl
    seen = []
    def leaf(step, project, agent_id=None):
        node, action = step.get('_node'), step.get('action')
        params = dict(step.get('params') or {})
        if step.get('_var_emit'):
            return original(step, project, agent_id)
        if node == 'table' and action == 'each':
            return _execute_table_each(params, project, agent_id)
        if node == 'table':
            return dataops.execute(params, ToolContext(project, 'data_' + action))
        if node == 'sense' and action == 'video':
            return {'items': [{'video_id': params['video_id']}], 'success': True}
        if node == 'self' and action == 'struct':
            assert params['known'] == fixture['known']
            seen.append(params['known'])
            return {'items': [{'tip': 'fixture tip', 'timestamp': '00:12'}], 'success': True}
        pytest.fail(f'허용하지 않은 외부 작업: {node}:{action}')
    monkeypatch.setattr(ibl_engine, '_execute_ibl_impl', leaf)
    monkeypatch.setattr(ibl_engine, 'execute_ibl', leaf)
    monkeypatch.setattr(episode_logger, 'record_trajectory_event', lambda *a, **k: None)
    seed = ('$신선=[table:take]{items:' + q(fixture['videos']) + ',n:4}\n'
            '$기존팁=[table:take]{items:' + q([{'tip': v} for v in fixture['known']]) + ',n:3}\n')
    out = workflow_engine.execute_pipeline(parse(seed + fixture['code']), str(tmp_path))
    final = json.loads(out['final_result']) if isinstance(out.get('final_result'), str) else out.get('final_result')
    assert out['success'] and len(final['items']) == 4 and len(seen) == 4, out


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
