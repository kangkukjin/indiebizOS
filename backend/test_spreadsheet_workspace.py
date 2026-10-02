"""Shared office ownership, spreadsheet types and conditional publication."""
import io
import zipfile

import boot_paths  # noqa: F401
import pytest
from openpyxl import Workbook, load_workbook

from spreadsheet_workspace import SpreadsheetWorkspace, SpreadsheetEngine
from office_sessions import DocumentConflict, DocumentUnsupported
from spreadsheet_files import projection, validate


def data(value=10):
    book=Workbook(); sheet=book.active
    sheet['A1']='00123'; sheet['B1']=value; sheet['C1']=False; sheet['D1']='=B1*2'
    buffer=io.BytesIO();book.save(buffer);return buffer.getvalue()


@pytest.fixture
def workspace(tmp_path,monkeypatch):
    import document_office
    monkeypatch.setattr(document_office,'available',lambda:True)
    return SpreadsheetWorkspace(tmp_path/'office')


def opened(workspace,tmp_path):
    path=tmp_path/'book.xlsx';path.write_bytes(data())
    doc=workspace.open(path)['document'];detail=workspace.acquire(doc['id'],'window1')
    return path,doc,detail['session']


def args(s):
    return dict(session_id=s['id'],client_id=s['client_id'],epoch=s['engine_epoch'],expected=s['session_revision'])


def test_projection_preserves_identifiers_boolean_zero_formula():
    rows=projection(data(0),'1','A1:E1')['items']
    assert rows[0]['entered_value']=='00123'
    assert rows[1]['entered_value']==0 and rows[1]['value_type']=='number'
    assert rows[2]['entered_value'] is False
    assert rows[3]['formula']=='=B1*2' and rows[3]['effective_value'] is None
    assert rows[4]['entered_value'] is None and rows[4]['value_type']=='blank'


def test_common_registration_and_writer_fence(workspace,tmp_path):
    from document_workspace import DocumentWorkspace
    path,doc,s=opened(workspace,tmp_path)
    other=DocumentWorkspace(workspace.store.root)
    assert other.open(path)['document']['id']==doc['id']
    with pytest.raises(DocumentConflict):
        workspace.acquire(doc['id'],'window2')
    assert path.read_bytes()==data() or load_workbook(path).active['B1'].value==10


def test_proposal_fences_revision_and_replay(workspace,tmp_path):
    path,doc,s=opened(workspace,tmp_path)
    snap=workspace.snapshot(doc['id'],**args(s),engine_state='synthetic engine state',calculation='stale')
    p=workspace.propose(doc['id'],snap['id'],'1','B1',[[22]])
    queued=workspace.apply(doc['id'],p['id'],**args(s),operation_id='one')
    assert queued['status']=='queued'
    s['session_revision']+=1;workspace.store.put('session',s)
    with pytest.raises(DocumentConflict):
        workspace.apply(doc['id'],p['id'],**args(s),operation_id='two')
    assert load_workbook(path).active['B1'].value==10


def test_cross_resource_snapshot_rejected(workspace,tmp_path):
    _,doc,s=opened(workspace,tmp_path)
    snap=workspace.snapshot(doc['id'],**args(s),engine_state='state',calculation='stale')
    other=tmp_path/'other.xlsx';other.write_bytes(data())
    other_id=workspace.open(other)['document']['id']
    with pytest.raises(PermissionError):
        workspace.read(other_id,snap['id'],'1','A1')


def test_external_change_preserves_draft_and_original(workspace,tmp_path):
    path,doc,s=opened(workspace,tmp_path)
    s.update(blob=workspace.store.blob(data(20)),session_revision=1,state='draft');workspace.store.put('session',s)
    external=data(99);path.write_bytes(external)
    with pytest.raises(DocumentConflict):
        workspace.save(doc['id'],**args(s),operation_id='save',expected_revision=doc['revision_id'])
    assert path.read_bytes()==external
    assert workspace.store.bytes(s['blob'])==data(20) or load_workbook(io.BytesIO(workspace.store.bytes(s['blob']))).active['B1'].value==20


def test_save_idempotence_and_restore(workspace,tmp_path):
    path,doc,s=opened(workspace,tmp_path)
    s.update(blob=workspace.store.blob(data(20)),session_revision=1,state='draft');workspace.store.put('session',s)
    a=workspace.save(doc['id'],**args(s),operation_id='save',expected_revision=doc['revision_id'])
    b=workspace.save(doc['id'],**args(s),operation_id='save',expected_revision=doc['revision_id'])
    assert a==b and load_workbook(path).active['B1'].value==20
    restored=workspace.restore(doc['id'],doc['revision_id'],**args(s),operation_id='restore')
    assert restored['session']['engine_epoch']!=s['engine_epoch']
    assert load_workbook(path).active['B1'].value==20


def test_external_resource_is_blocked():
    source=io.BytesIO(data());result=io.BytesIO()
    with zipfile.ZipFile(source) as original,zipfile.ZipFile(result,'w') as changed:
        for name in original.namelist():changed.writestr(name,original.read(name))
        changed.writestr('xl/externalLinks/externalLink1.xml','<externalLink/>')
    with pytest.raises(DocumentUnsupported):validate(result.getvalue())


def test_unordered_close_is_a_recovery_candidate_not_a_newer_draft(workspace,tmp_path,monkeypatch):
    import document_office
    import jwt
    cfg={'url':'http://127.0.0.1:8093','callback_origin':'http://localhost:8765','secret':'x'*40}
    monkeypatch.setattr(document_office,'settings',lambda:cfg)
    path,doc,s=opened(workspace,tmp_path)
    adapter=SpreadsheetEngine(workspace)
    setup=adapter.config(doc['id'],**args(s),browser_origin='http://localhost',browser_api_origin='http://localhost:8765')
    s=setup['session'];confirmed=workspace.store.blob(data(20))
    s.update(blob=confirmed,captured_sequence=1,capture_requests={'capture':1})
    workspace.store.put('session',s)
    monkeypatch.setattr(document_office,'download',lambda url,cfg:data(10))
    body={'key':s['engine_key'],'status':2,'filetype':'xlsx','url':cfg['url']+'/closing'}
    body['token']=jwt.encode(body,cfg['secret'],algorithm='HS256')
    assert adapter.callback(s['id'],s['ticket'],body)=={'error':0}
    current=workspace.store.get('session',s['id'])
    assert current['blob']==confirmed and current['state']=='recovering'
    recovery=[v for v in workspace.versions(doc['id']) if v.get('is_recovery')]
    assert len(recovery)==2 and {r['blob'] for r in recovery} >= {confirmed}
    with pytest.raises(DocumentConflict):
        workspace.save(doc['id'],**args(current),operation_id='unsafe',expected_revision=doc['revision_id'])
    chosen=next(v for v in recovery if v['blob']==confirmed)
    restored=workspace.restore(doc['id'],chosen['id'],**args(current),operation_id='restore-confirmed')['session']
    assert restored['state']=='draft'
    assert load_workbook(path).active['B1'].value==10


def test_report_pins_unsaved_snapshot_and_does_not_rewrite_source(workspace,tmp_path):
    from resource_links import ResourceLinks
    path,doc,s=opened(workspace,tmp_path)
    s.update(blob=workspace.store.blob(data(20)),session_revision=1,state='draft');workspace.store.put('session',s)
    snap=workspace.snapshot(doc['id'],**args(s),engine_state='fixture state',calculation='stale')
    with pytest.raises(DocumentConflict):
        workspace.create_report(doc['id'],snap['id'],'1','A1:C1','reject-stale')
    report=workspace.create_report(doc['id'],snap['id'],'1','A1:C1','report',allow_stale=True)
    assert report['reference']['snapshot_id']==snap['id']
    assert report['reference']['provenance']['unsaved']
    assert '00123' in __import__('pathlib').Path(report['document']['source_uri']).read_text()
    assert load_workbook(path).active['B1'].value==10
    assert workspace.create_report(doc['id'],snap['id'],'1','A1:C1','report',allow_stale=True)==report
    assert not ResourceLinks(workspace).status(report['reference']['id'])['source_changed']


def test_engine_type_and_namespace(workspace,tmp_path,monkeypatch):
    import document_office
    monkeypatch.setattr(document_office,'settings',lambda:{'url':'http://127.0.0.1:8093','callback_origin':'http://localhost:8765','secret':'x'*40})
    _,doc,s=opened(workspace,tmp_path)
    setup=SpreadsheetEngine(workspace).config(doc['id'],**args(s),browser_origin='http://localhost',browser_api_origin='http://localhost:8765')
    assert setup['config']['documentType']=='cell'
    assert setup['config']['editorConfig']['customization']['macrosMode']=='disable'
    assert '/spreadsheets/engine-io/' in setup['config']['document']['url']
    assert setup['config']['editorConfig']['plugins']['autostart']==[SpreadsheetEngine.plugin_guid]


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-8-sig', 'utf-16', 'cp949', 'euc-kr'])
def test_export_csv_text_policy_and_encoding(workspace, tmp_path, encoding):
    import csv
    book = Workbook()
    values = ['00123', '123456789012345678', '010-1234-5678', '한글,줄\n바꿈', '=1+1', '+cmd', '-cmd', '@cmd', 0, False, None]
    for col, value in enumerate(values, 1):
        cell = book.active.cell(1, col, value)
        if isinstance(value, str):
            cell.data_type = 's'
    path = tmp_path / 'types.xlsx'
    book.save(path)
    original = path.read_bytes()
    doc = workspace.open(path)['document']
    session = workspace.acquire(doc['id'], 'export-test')['session']
    snap = workspace.snapshot(doc['id'], **args(session), engine_state='fixture', calculation='stale')
    with pytest.raises(DocumentConflict):
        workspace.export_range(doc['id'], snap['id'], '1', 'A1:K1')
    output, mime, report = workspace.export_range(doc['id'], snap['id'], '1', 'A1:K1',
                                                 encoding=encoding, allow_stale=True)
    row = list(csv.reader(io.StringIO(output.decode(encoding), newline='')))[0]
    assert row == values[:4] + ["'=1+1", "'+cmd", "'-cmd", "'@cmd", '0', 'FALSE', '']
    assert report['escaped_text_cells'] == 4 and report['cells'] == 11
    assert report['snapshot_id'] == snap['id'] and report['calc_status'] == 'stale'
    assert mime == 'text/csv; charset=' + ('utf-8' if encoding == 'utf-8-sig' else encoding)
    assert path.read_bytes() == original
    raw, _, raw_report = workspace.export_range(doc['id'], snap['id'], '1', 'E1:H1',
                                                text_mode='raw', encoding=encoding, newline='lf', allow_stale=True)
    assert list(csv.reader(io.StringIO(raw.decode(encoding))))[0] == values[4:8]
    assert raw_report['escaped_text_cells'] == 0 and raw.decode(encoding).endswith('\n')


def test_export_json_preserves_types_and_snapshot(workspace, tmp_path):
    import json
    path, doc, session = opened(workspace, tmp_path)
    snap = workspace.snapshot(doc['id'], **args(session), engine_state='fixture', calculation='stale')
    session.update(blob=workspace.store.blob(data(99)), session_revision=1)
    workspace.store.put('session', session)
    result, mime, report = workspace.export_range(doc['id'], snap['id'], '1', 'A1:E1',
                                                 format='json', allow_stale=True)
    result = json.loads(result)
    assert mime == 'application/json'
    assert [c['effective_value'] for c in result['items']] == ['00123', 10, False, None, None]
    assert result['items'][3]['formula'] == '=B1*2'
    assert result['items'][4]['value_type'] == 'blank'
    assert report['missing_formula_cells'] == 1 and report['session_revision'] == 0
    assert load_workbook(path).active['B1'].value == 10
    other = workspace.create('other')['document']
    with pytest.raises(PermissionError):
        workspace.export_range(other['id'], snap['id'], '1', 'A1', allow_stale=True)


def test_export_html_escapes_content_and_unencodable_text_fails(workspace, tmp_path):
    book = Workbook()
    book.active['A1'] = '<script>alert(1)</script>😀'
    path = tmp_path / 'unsafe.xlsx'
    book.save(path)
    doc = workspace.open(path)['document']
    session = workspace.acquire(doc['id'], 'export-test')['session']
    snap = workspace.snapshot(doc['id'], **args(session), engine_state='fixture', calculation='stale')
    output, _, _ = workspace.export_range(doc['id'], snap['id'], '1', 'A1', format='html', allow_stale=True)
    assert b'<script>' not in output and b'&lt;script&gt;' in output
    with pytest.raises(ValueError, match='인코딩'):
        workspace.export_range(doc['id'], snap['id'], '1', 'A1', encoding='cp949', allow_stale=True)
    with pytest.raises(ValueError):
        workspace.export_range(doc['id'], snap['id'], '1', 'A1', format='xlsx', allow_stale=True)


def test_export_api_attachment_is_guarded(workspace, tmp_path, monkeypatch):
    import api_spreadsheets
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    _, doc, session = opened(workspace, tmp_path)
    snap = workspace.snapshot(doc['id'], **args(session), engine_state='fixture', calculation='stale')
    monkeypatch.setattr(api_spreadsheets, 'service', lambda: workspace)
    app = FastAPI()
    app.dependency_overrides[api_spreadsheets.authorize] = lambda: None
    app.include_router(api_spreadsheets.router)
    with TestClient(app) as client:
        request = {'snapshot_id': snap['id'], 'sheet_id': '1', 'range': 'A1:C1', 'format': 'tsv'}
        assert client.post('/spreadsheets/'+doc['id']+'/range-export', json={'args': request}).status_code == 409
        result = client.post('/spreadsheets/'+doc['id']+'/range-export', json={'args': {**request, 'allow_stale': True}})
        assert result.status_code == 200, result.text
        assert result.content.decode('utf-8-sig') == '00123\t10\tFALSE\r\n'
        assert result.headers['content-disposition'] == 'attachment; filename=range.tsv'
        assert result.headers['x-content-type-options'] == 'nosniff'


if __name__ == '__main__':
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
