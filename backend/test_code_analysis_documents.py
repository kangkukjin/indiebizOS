import boot_paths  # noqa: F401
import threading
from types import SimpleNamespace
from code_analysis_documents import Session


def subject():
    s = object.__new__(Session)
    s.diagnostics = {}; s.diag_lock = threading.Condition()
    s.document = lambda path: {'uri': 'file:///a.py', 'version': 3}
    s.supports = lambda *args: False
    return s


def test_pending_is_not_zero_and_old_empty_push_is_stale():
    s = subject()
    assert s.diagnostic('a.py')[2] == 'pending'
    s.on_notice('textDocument/publishDiagnostics', {'uri': 'file:///a.py', 'version': 2, 'diagnostics': []})
    assert s.diagnostic('a.py')[2] == 'stale'
    s.on_notice('textDocument/publishDiagnostics', {'uri': 'file:///a.py', 'diagnostics': []})
    assert s.diagnostic('a.py')[2] == 'version_unconfirmed'
    s.on_notice('textDocument/publishDiagnostics', {'uri': 'file:///a.py', 'version': 3, 'diagnostics': []})
    assert s.diagnostic('a.py')[2] == 'received'
    s.on_request('workspace/diagnostic/refresh', {})
    assert s.diagnostic('a.py')[2] == 'stale'


def test_pull_unchanged_preserves_previous_diagnostics_and_result_id():
    s = subject(); s.supports = lambda *args: True
    s.diagnostics['file:///a.py'] = {'resultId': 'before', 'diagnostics': [{'message': 'existing'}]}
    calls = []
    def request(method, params):
        calls.append(params)
        return {'kind': 'unchanged', 'resultId': 'after'}
    s.client = SimpleNamespace(request=request)
    doc, value, status = s.diagnostic('a.py')
    assert calls[0]['previousResultId'] == 'before' and value['diagnostics'] == [{'message': 'existing'}]
    assert value['resultId'] == 'after' and status == 'received'


def test_unsolicited_apply_edit_is_rejected():
    assert subject().on_request('workspace/applyEdit', {'edit': {}})['applied'] is False
