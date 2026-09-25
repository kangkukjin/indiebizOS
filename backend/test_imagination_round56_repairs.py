"""Real vocabulary boundaries found by imagination round 56; no external APIs."""
import boot_paths  # noqa: F401
from pathlib import Path

import pytest

from ibl_v2_adapters import load_registry
from ibl_v2_compile import compile_program
from ibl_v2_entry import handle_request
from ibl_v2_runtime import Runtime


@pytest.fixture
def run(tmp_path, monkeypatch):
    import ibl_run_journal
    monkeypatch.setattr(ibl_run_journal, 'journal_root', lambda _: tmp_path / 'runs')
    def invoke(code, inputs=None):
        return handle_request({'edition': 2, 'code': code, 'inputs': inputs or {}}, str(tmp_path))
    return invoke


@pytest.mark.parametrize('inputs', [
    {'a': [{'id': 'a', 'price': 300}], 'b': [{'id': 'a', 'memo': 'station'}]},
    {'a': {'items': [{'id': 'a', 'price': 300}]}, 'b': {'items': [{'id': 'a', 'memo': 'station'}]}},
])
def test_join_native_values_reach_actual_handler(run, inputs):
    result = run('[table:join]{left:$a,right:$b,on:"id"}', inputs)
    assert result['success'], result
    assert result['value']['items'] == [{'id': 'a', 'price': 300, 'memo': 'station'}]


def test_left_join_defaults_and_actual_null_remain_distinct(run):
    result = run('''[table:join]{left:[{id:"a"},{id:"b"}],right:[{id:"a",memo:null}],
        on:"id",how:"left",defaults:{memo:"unseen"}}''')
    assert result['success'], result
    assert result['value']['items'] == [{'id': 'a', 'memo': None}, {'id': 'b', 'memo': 'unseen'}]


@pytest.mark.parametrize('action', ['join', 'merge', 'union'])
def test_pair_pipeline_and_explicit_bundle_share_the_handler(run, action):
    option = ',on:"id"' if action == 'join' else ''
    for code in [
        f'([{{id:"a"}}] & [{{id:"a"}}]) >> [table:{action}]' + '{' + option.lstrip(',') + '}',
        f'[table:{action}]' + '{inputs:[[{id:"a"}],[{id:"a"}]]' + option + '}',
        f'[table:{action}]' + '{left:[{id:"a"}],right:[{id:"a"}]' + option + '}',
    ]:
        result = run(code)
        assert result['success'], result
        assert len(result['value']['items']) == (1 if action == 'join' else 2)


@pytest.mark.parametrize('action', ['merge', 'union'])
def test_all_parallel_branches_and_empty_sources_survive(run, action):
    option = 'by:"id"' if action == 'merge' else ''
    result = run(f'([{{id:"a"}}] & [] & [{{id:"b"}}]) >> [table:{action}]' + '{' + option + '}')
    assert result['success'], result
    assert result['value']['items'] == [{'id': 'a'}, {'id': 'b'}]
    assert run(f'([] & []) >> [table:{action}]' + '{}')['value']['items'] == []


@pytest.mark.parametrize('action', ['join', 'merge', 'union'])
@pytest.mark.parametrize('args', [
    'left:[]', 'right:[]', 'inputs:[[],[]],left:[],right:[]', 'inputs:null',
])
def test_bad_or_ambiguous_pair_inputs_rejected_before_execution(action, args):
    code = f'[table:{action}]' + '{' + args + (',on:"id"' if action == 'join' else '') + '}'
    plan = compile_program(code, load_registry())
    assert plan.issues, plan.report()
    assert Runtime(plan).run()['executed'] is False


@pytest.mark.parametrize('action', ['join', 'merge', 'union'])
def test_pipeline_cannot_silently_override_explicit_pair(action):
    code = f'([] & []) >> [table:{action}]' + '{left:[],right:[]' + (',on:"id"' if action == 'join' else '') + '}'
    assert compile_program(code, load_registry()).issues


def test_join_cannot_discard_a_third_branch(run):
    result = run('([] & [] & []) >> [table:join]{on:"id"}')
    assert not result['success']


@pytest.mark.parametrize('alias', [('a', 'b'), ('table1', 'table2')])
def test_pair_aliases_accept_containers_without_serializing(run, alias):
    left, right = alias
    result = run(f'[table:join]{{{left}:[{{id:"a"}}],{right}:[{{id:"a"}}],on:"id"}}')
    assert result['success'] and result['value']['items'] == [{'id': 'a'}], result


@pytest.mark.parametrize('action', ['merge', 'union'])
def test_partial_and_failed_legacy_branches_do_not_become_complete(run, action):
    for branch in ['{success:false,error:"source failed"}', '{items:[{id:"b"}],truncated:true}']:
        result = run(f'[table:{action}]' + '{inputs:[{items:[{id:"a"}]},' + branch + ']}')
        assert not result['success'], result
        assert not result['source_complete'], result
    stopped = run(f'[table:{action}]' + '{inputs:[{items:[{id:"a"}]},{success:false,error:"bad"}],on_error:"stop"}')
    assert not stopped['success'], stopped


@pytest.mark.parametrize('boundary', ['row_honesty', 'branches_honesty', 'markers'])
def test_missing_branch_evidence_is_only_read_at_execution_boundaries(boundary):
    from ibl_honesty import completion_evidence, merge_into
    from ibl_v2_adapters import decode_envelope
    from ibl_v2_ir import Fault
    missing = {'branches_skipped': [{'branch': 2, 'error': 'failed'}]}
    promoted = {}
    merge_into(missing, promoted)
    assert promoted == missing
    with pytest.raises(Fault) as exc:
        decode_envelope({'success': True, 'items': [], boundary: [missing]}, {})
    assert exc.value.code == 'PARTIAL_SOURCE'
    assert completion_evidence({'items': [missing], 'text': str(missing)}) == []
    assert decode_envelope({'items': [missing]}, {})[0] == {'items': [missing]}


@pytest.mark.parametrize('fmt', ['literal', '007', '{"error":"business data"}', 'Error: literal', ''])
def test_time_returns_exact_text_even_when_it_looks_like_json_or_failure(run, fmt):
    result = run('[self:time]{format:$fmt}', {'fmt': fmt})
    assert result['success'], result
    assert result['value'] == fmt


def test_time_can_be_used_as_report_title(run):
    result = run('$date=[self:time]{format:"%Y-%m-%d"}; return f"Report ${date}"')
    assert result['success'] and result['value'].startswith('Report 20'), result


def test_actual_text_success_file_operations_do_not_report_failure_after_writing(run, tmp_path):
    (tmp_path / 'original').write_text('payload')
    for code in ['[self:copy]{src:"original",dest:"copy"}',
                 '[self:move]{src:"copy",dest:"moved"}',
                 '[self:delete]{path:"moved"}',
                 '[self:delete]{path:"moved",missing_ok:true}']:
        result = run(code)
        assert result['success'], result
        assert result['value']['success'] is True
    assert (tmp_path / 'original').read_text() == 'payload'
    assert not (tmp_path / 'copy').exists() and not (tmp_path / 'moved').exists()
    assert not run('[self:copy]{src:"missing",dest:"other"}')['success']


def test_old_time_semantics_stay_text(tmp_path):
    from ibl_edition import source_context
    from ibl_engine import execute_ibl
    with source_context(1):
        assert execute_ibl({'_node': 'self', 'action': 'time', 'params': {'format': 'literal'}}, str(tmp_path)) == 'literal'


def test_builder_detects_missing_pair_bridge_and_container_declaration():
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    from iblbuild_v2 import validate_v2_contracts
    from ibl_registry import load_nodes_installed
    import copy
    data = copy.deepcopy(load_nodes_installed())
    assert not validate_v2_contracts(data)
    entry = data['nodes']['table']['actions']['join']
    del entry['callable_contract']['pipe_input']
    assert any('join' in issue for issue in validate_v2_contracts(data))
    data = copy.deepcopy(load_nodes_installed())
    del data['nodes']['table']['actions']['join']['params']['left']
    assert any('left' in issue for issue in validate_v2_contracts(data))


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
