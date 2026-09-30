"""Partial source recovery through the real runtime, model view and input reader."""
import json
from decimal import Decimal

import boot_paths  # noqa: F401
import pytest


@pytest.fixture
def view(monkeypatch, tmp_path):
    import model_result_view
    from supervision_store import TurnStore
    monkeypatch.setattr(model_result_view, 'evidence_store', lambda: TurnStore(tmp_path / 'evidence'))
    return model_result_view


def run_partial(partial, *, nested=False):
    from ibl_v2_adapters import Adapter, Adapted
    from ibl_v2_compile import compile_program
    from ibl_v2_ir import Fault
    from ibl_v2_runtime import Runtime
    calls = []

    def call(runtime, args):
        calls.append(args['id'])
        if args['id'] == 'blocked':
            raise Fault('PARTIAL_SOURCE', 'one source blocked', kind='partial', partial=partial)
        return Adapted({'text': 'search result'}, {})

    contract = {'version': 1, 'params': {'id': 'Text'}, 'required': ['id'],
                'result': 'Record', 'effects': ['read_external'],
                'adapter': {'protocol': 'legacy-envelope', 'value_path': ''}}
    code = '[sense:source]{id:"search"} & [sense:source]{id:"blocked"}'
    if nested:
        code = '[def:inner](){return ' + code + '}\n[sense:source]{id:"outer"} & [fn:inner]{}'
    plan = compile_program(code, {'sense:source': Adapter(contract, call)})
    assert not plan.issues
    return Runtime(plan).run(), calls


def test_failed_branch_has_direct_rows_after_transport_without_reexecution(view):
    from ibl_result_transport import provider_tool_result
    rows = [{'url': 'https://source.test/good', 'text': 'source paragraph ' * 1000},
            {'url': 'https://source.test/blocked', '_error': 'blocked'}]
    partial = {'items': rows, 'error_count': 1, 'results': [{'result': rows}],
               'final_result': json.dumps({'items': rows})}
    raw, calls = run_partial(partial)
    before = json.dumps(raw)
    shown = view.project_v2_result(raw)
    delivered = json.loads(provider_tool_result(json.dumps(shown, ensure_ascii=False)))
    entries = delivered['result_ref']['failed_partial_reads']
    entry = next(e for e in entries if e['branch_path'] == [1])
    assert entry['source_complete'] is False and entry['code'] == 'PARTIAL_SOURCE'
    assert entry['read_args']['path'][-2:] == ['partial', 'items']
    page = view.read_result(entry['read_args'])
    assert json.loads(page['text']) == rows and page['read_scope']['complete']
    inputs, notes = view.resolve_input_refs(entry['input_args'])
    assert inputs['입력'] == rows and notes[0]['evidence']['execution_success'] is False
    assert json.dumps(raw) == before and sorted(calls) == ['blocked', 'search']
    assert delivered['success'] is False
    assert len(json.dumps(shown, ensure_ascii=False)) < 24000


def test_nested_partial_input_preserves_types_and_json_looking_text(view):
    from ibl_v2_ir import UNIT
    rows = [{'number': Decimal('0.10000000000000000001'), 'unit': UNIT,
             'large': 2**80, 'text': '[1, 2]'}]
    raw, calls = run_partial({'items': rows, 'error_count': 1}, nested=True)
    ref = view.project_v2_result(raw)['result_ref']
    entry = next(e for e in ref['failed_partial_reads'] if e['branch_path'] == [1, 1])
    inputs, _ = view.resolve_input_refs(entry['input_args'])
    assert inputs['입력'] == rows and inputs['입력'][0]['unit'] is UNIT
    assert len(calls) == 3


def test_old_nested_partial_gets_read_reference_without_claiming_lossless_input(view):
    raw, _ = run_partial({'items': [{'text': 'old source'}], 'error_count': 1})
    raw['diagnostic']['details']['errors']['1'].pop('partial_wire', None)
    ref = view.project_v2_result(raw)['result_ref']
    entry = next(e for e in ref['failed_partial_reads'] if e['branch_path'] == [1])
    assert 'input_args' not in entry and entry['input_unavailable']
    page = view.read_result(entry['read_args'])
    assert json.loads(page['text']) == [{'text': 'old source'}]
    assert 'input_args' not in page and page['input_unavailable']
    with pytest.raises(ValueError, match='손실 없는'):
        view.resolve_input_refs({'입력': {'$ref': ref['id'], 'path': entry['read_args']['path']}})


@pytest.mark.parametrize('blocked', ['masked', 'unsupported'])
def test_nested_partial_cannot_bypass_masking_or_protocol_rejection(view, monkeypatch, blocked):
    raw, _ = run_partial({'items': [{'text': 'source'}], 'error_count': 1})
    fault = raw['diagnostic']['details']['errors']['1']
    if blocked == 'unsupported':
        fault.pop('partial_wire')
        fault['partial_wire_error'] = {'code': 'VALUE_PROTOCOL_UNSUPPORTED'}
    store = view.evidence_store()
    monkeypatch.setattr(view, 'evidence_store', lambda: store)
    original_read = store.read_evidence
    original_save = store.evidence
    masked = [['diagnostic', 'details', 'errors', '1', 'partial_wire', 'data']]
    if blocked == 'masked':
        monkeypatch.setattr(store, 'evidence', lambda value: {**original_save(value), 'masked_paths': masked})
        monkeypatch.setattr(store, 'read_evidence',
                            lambda *a, **kw: {**original_read(*a, **kw), 'masked_paths': masked})
    ref = view.project_v2_result(raw)['result_ref']
    entry = ref['failed_partial_reads'][0]
    assert 'input_args' not in entry and entry['input_unavailable']
    assert 'input_args' not in view.read_result(entry['read_args'])
    with pytest.raises(ValueError):
        view.resolve_input_refs({'입력': {'$ref': ref['id'], 'path': entry['read_args']['path']}})


def test_reference_list_is_bounded_and_business_errors_are_not_branches(view):
    from ibl_v2_ir import pack
    data = {'items': [], 'details': {'errors': {'42': {'has_partial': True, 'partial': 'business'}}}}
    fault = {'code': 'PARTIAL_SOURCE', 'kind': 'partial', 'has_partial': True,
             'partial': data, 'partial_wire': {'protocol': 'ibl-value/1', 'data': pack(data)}}
    raw = {'edition': 2, 'success': False, 'source_complete': False, 'diagnostic': {
        'has_partial': True, 'partial': [], 'details': {
            'successful_indices': [], 'errors': {str(i): fault for i in range(20)}}}}
    ref = view.project_v2_result(raw)['result_ref']
    assert len(ref['failed_partial_reads']) == 6
    assert ref['failed_partial_reads_omitted'] == 14
    assert ref['failed_partial_scan_incomplete'] is False
    for i, entry in enumerate(ref['failed_partial_reads']):
        assert entry['branch_path'] == [i] and entry['source_complete'] is False
        assert view.resolve_input_refs(entry['input_args'])[0]['입력'] == []


def test_deep_diagnostics_stop_with_explicit_incomplete_scan(view):
    fault = {'code': 'TOOL', 'has_partial': True, 'partial': {'items': []}}
    for _ in range(12):
        fault = {'code': 'TOOL', 'has_partial': True, 'partial': [],
                 'details': {'errors': {'0': fault}}}
    raw = {'edition': 2, 'success': False, 'diagnostic': fault}
    ref = view.project_v2_result(raw)['result_ref']
    assert ref['failed_partial_scan_incomplete'] is True
    for entry in ref['failed_partial_reads']:
        assert len(entry['read_args']['path']) <= 16
        view.read_result(entry['read_args'])


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
