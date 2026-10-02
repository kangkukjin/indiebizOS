"""CSV fidelity, scan completeness, and legacy office writer fencing."""
import csv
import io

import boot_paths  # noqa: F401
import pytest
from openpyxl import load_workbook
from spreadsheet_workspace import SpreadsheetWorkspace
from spreadsheet_imports import preview,import_csv,decode
from spreadsheet_files import projection
from office_store import digest


def test_cp949_identifiers_quotes_newlines_and_literal_formulas(tmp_path):
    app=SpreadsheetWorkspace(tmp_path/'office')
    stream=io.StringIO(newline='');writer=csv.writer(stream)
    writer.writerow(['코드','ID','전화','메모','수식 같은 텍스트','금액'])
    writer.writerow(['00123','123456789012345678','010-1234-5678','쉼표, 그리고\n줄바꿈','=1+1','1,200'])
    raw=stream.getvalue().encode('cp949');source=tmp_path/'원본.csv';source.write_bytes(raw)
    d=app.open(source)['document']
    args={'expected_revision':d['revision_id'],'encoding':'cp949','types':['text']*5+['number']}
    scan=preview(app,d['id'],**args)
    assert scan['total_rows']==2 and scan['error_count']==0 and scan['full_scan']
    imported=import_csv(app,d['id'],**args)
    path=imported['document']['source_uri'];book=load_workbook(path)
    assert [c.value for c in book.active[2]]==['00123','123456789012345678','010-1234-5678','쉼표, 그리고\n줄바꿈','=1+1',1200]
    assert book.active['E2'].data_type=='s'
    assert source.read_bytes()==raw
    assert imported['import']['source_sha256']==digest(raw)
    assert projection(open(path,'rb').read(),'1','E2')['items'][0]['formula'] is None


def test_type_error_after_preview_window_is_not_silently_dropped(tmp_path):
    app=SpreadsheetWorkspace(tmp_path/'office');p=tmp_path/'large.csv'
    p.write_text('number\n'+'1\n'*40+'not a number\n')
    d=app.open(p)['document'];args={'expected_revision':d['revision_id'],'types':['number']}
    result=preview(app,d['id'],**args)
    assert result['truncated'] and result['error_count']==1 and result['errors'][0]['row']==42
    with pytest.raises(ValueError):import_csv(app,d['id'],**args)
    assert len(app.list())==1


def test_number_precision_requires_text(tmp_path):
    app=SpreadsheetWorkspace(tmp_path/'office');p=tmp_path/'ids.csv';p.write_text('id\n123456789012345678\n')
    d=app.open(p)['document']
    assert preview(app,d['id'],d['revision_id'],types=['number'])['error_count']==1


def test_import_limit_is_failure_not_truncation(monkeypatch):
    import spreadsheet_imports
    monkeypatch.setattr(spreadsheet_imports,'MAX_CELLS',2)
    with pytest.raises(ValueError):decode(b'a,b\n1,2\n')


def test_legacy_write_fences_an_open_spreadsheet(tmp_path,monkeypatch):
    import document_office
    monkeypatch.setattr(document_office,'available',lambda:True)
    app=SpreadsheetWorkspace(tmp_path/'office');d=app.create('guard')['document']
    path=__import__('pathlib').Path(d['source_uri']);original=path.read_bytes()
    app.acquire(d['id'],'writer')
    with pytest.raises(ValueError,match='OFFICE_SESSION_CONFLICT'):
        with app.store.legacy_write(path,digest(original)):path.write_bytes(b'not allowed')
    assert path.read_bytes()==original


def test_legacy_write_rejects_a_stale_read(tmp_path):
    app=SpreadsheetWorkspace(tmp_path/'office');p=tmp_path/'outside.xlsx';p.write_bytes(b'newer')
    with pytest.raises(ValueError,match='OFFICE_SOURCE_CONFLICT'):
        with app.store.legacy_write(p,digest(b'older')):p.write_bytes(b'not allowed')
    assert p.read_bytes()==b'newer'


if __name__ == '__main__':
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
