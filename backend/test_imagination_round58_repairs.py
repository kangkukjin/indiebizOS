"""Round 58: real unary vocabulary seams; all external/model effects isolated."""
import boot_paths  # noqa: F401
import copy
from pathlib import Path
import sys

import pytest

from ibl_v2_adapters import load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime


@pytest.fixture(scope='module')
def registry(tmp_path_factory):
    return load_registry(str(tmp_path_factory.mktemp('round58')))


def run(registry, code, inputs=None):
    return Runtime(compile_program(code, registry, inputs), inputs).run()


@pytest.mark.parametrize('action,args,rows,expected', [
    ('groupby', 'by:"category",agg:{total:["sum","amount"]}',
     [{'category': 'a', 'amount': 2}, {'category': 'a', 'amount': 3}],
     [{'category': 'a', 'total': 5}]),
    ('rename', 'map:{name:"id"}', [{'name': 'a'}], [{'id': 'a'}]),
    ('dedup', 'by:"id"', [{'id': 'a'}, {'id': 'a'}], [{'id': 'a'}]),
    ('flatten', 'field:"refs",keep:["id"]', [{'id': 'a', 'refs': [{'title': 'x'}]}],
     [{'title': 'x', 'id': 'a'}]),
    ('reduce', 'step:"acc + amount",init:0', [{'amount': 2}, {'amount': 3}], [{'value': 5}]),
])
def test_unary_pipeline_equals_explicit_input(registry, action, args, rows, expected):
    for code in [f'$rows >> [table:{action}]{{{args}}}',
                 f'[table:{action}]{{items:$rows,{args}}}']:
        result = run(registry, code, {'rows': rows})
        assert result['success'], result
        assert result['value']['items'] == expected


@pytest.mark.parametrize('action,args', [
    ('groupby', 'by:"id"'), ('dedup', 'by:"id"'), ('rename', 'map:{a:"b"}'),
    ('flatten', 'field:"refs"'), ('reduce', 'step:"acc+1"'),
    ('ai', 'instruction:"검사"'), ('brief', 'instruction:"검사"'),
    ('judge', 'instruction:"관련 있는가"'),
])
def test_empty_unary_input_is_success_without_model_call(registry, action, args):
    result = run(registry, f'[] >> [table:{action}]{{{args}}}')
    assert result['success'], result


@pytest.mark.parametrize('action', ['reduce', 'judge', 'ai', 'brief', 'chunk',
                                  'rename', 'flatten', 'dedup', 'since', 'groupby'])
def test_no_pipe_can_overwrite_explicit_input(registry, action):
    plan = compile_program(f'[] >> [table:{action}]{{items:[]}}', registry)
    assert 'PIPE_COLLISION' in [issue['code'] for issue in plan.issues]
    assert Runtime(plan).run()['executed'] is False


def test_builder_guards_every_unary_flow_without_action_name_list():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    from iblbuild_v2 import validate_v2_contracts
    from ibl_registry import load_nodes_installed
    data = copy.deepcopy(load_nodes_installed())
    assert not validate_v2_contracts(data)
    for node in data['nodes'].values():
        for action, entry in node['actions'].items():
            if entry.get('flow', {}).get('accepts') not in {'items', 'prose|items'}:
                continue
            if entry.get('func') == 'table_each':
                continue
            contract = entry.pop('callable_contract')
            assert any(action in issue for issue in validate_v2_contracts(data))
            entry['callable_contract'] = contract


@pytest.mark.parametrize('source', ['abcdef', [{'text': 'abcdef'}], {'items': [{'text': 'abcdef'}]}])
def test_chunk_accepts_text_rows_and_envelope(registry, source):
    result = run(registry, '$source >> [table:chunk]{size:3,by:"chars"}', {'source': source})
    assert result['success'], result
    assert [r['text'] for r in result['value']['items']] == ['abc', 'def']


def test_chunk_bad_envelope_reports_input_error_not_name_error(registry):
    result = run(registry, '{foo:"no body"} >> [table:chunk]{}')
    assert not result['success']
    assert '본문' in result['error']
    assert 'cands' not in result['error']


def test_chunk_empty_rows_are_a_valid_empty_result(registry):
    for source in [[], {'items': []}]:
        result = run(registry, '$source >> [table:chunk]{}', {'source': source})
        assert result['success'], result
        assert result['value']['items'] == []


def test_chunk_missing_text_rows_cannot_look_complete(registry):
    result = run(registry, '[{text:"abc"},{id:"missing"}] >> [table:chunk]{}')
    assert not result['success'], result
    assert result['source_complete'] is False


def test_unary_envelope_does_not_drop_partial_source(registry):
    result = run(registry, '{items:[{id:"a"}],truncated:true} >> [table:dedup]{by:"id"}')
    assert not result['success'], result
    assert result['source_complete'] is False


@pytest.mark.parametrize('source', [
    {'items': [], 'error_count': 1}, {'items': [], 'rows_unprocessed': 1},
    {'items': [], 'rows_dropped': 1}, {'items': [], 'success': False, 'error': 'failed'},
    '{"items":[],"truncated":true}',
])
def test_input_envelope_honesty_is_independent_of_output_shape(source):
    from ibl_v2_adapters import decode_envelope
    from ibl_v2_ir import Fault
    with pytest.raises(Fault) as exc:
        decode_envelope({'items': []}, {'input_envelopes': ['items']}, {'items': source})
    assert exc.value.kind == 'partial'
    assert exc.value.partial == {'items': []}


@pytest.mark.parametrize('source', [
    [{'error': 'business', 'success': False, 'truncated': True}],
    {'items': [{'truncated': True}]},
    {'items': [], 'truncated': True, 'truncations': [{'scope': 'selection'}]},
])
def test_row_data_and_intentional_selection_remain_complete(source):
    from ibl_v2_adapters import decode_envelope
    assert decode_envelope({'items': []}, {'input_envelopes': ['items']}, {'items': source})[0] == {'items': []}


def test_since_peek_pipeline_does_not_create_a_baseline(registry, tmp_path, monkeypatch):
    import sqlite3
    from tool_loader import load_tool_handler
    module = load_tool_handler('data_since')
    def connect():
        conn = sqlite3.connect(tmp_path / 'since.db')
        conn.execute('CREATE TABLE IF NOT EXISTS since_seen ('
                     'stream TEXT, k TEXT, watched TEXT, first_seen TEXT, last_seen TEXT,'
                     'PRIMARY KEY(stream,k))')
        return conn
    monkeypatch.setattr(module, '_since_conn', connect)
    result = run(registry, '[{id:"a"}] >> [table:since]{key:"IT58",by:"id",peek:true}')
    assert result['success'], result
    with sqlite3.connect(tmp_path / 'since.db') as conn:
        assert conn.execute('SELECT count(*) FROM since_seen').fetchone()[0] == 0


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
