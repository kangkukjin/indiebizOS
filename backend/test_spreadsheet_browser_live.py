"""Real browser app + local engine + conditional source save acceptance."""
import os
import socket
import threading
import time
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.system
@pytest.mark.skipif(os.environ.get('INDIEBIZ_OFFICE_LIVE_TEST')!='1',reason='explicit local office app test')
def test_app_snapshot_proposal_save(tmp_path,monkeypatch):
    import api_spreadsheets
    import document_office
    import uvicorn
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse
    from fastapi.staticfiles import StaticFiles
    from playwright.sync_api import sync_playwright,expect
    from openpyxl import load_workbook
    from spreadsheet_workspace import SpreadsheetWorkspace

    workspace=SpreadsheetWorkspace(tmp_path/'office')
    source=workspace.create('인수 장부','quotation')['document']['source_uri']
    monkeypatch.setattr(api_spreadsheets,'service',lambda:workspace)
    app=FastAPI();app.include_router(api_spreadsheets.router)
    @app.get('/launcher/auth/session')
    def auth():return {'authenticated':True,'external':False}
    @app.get('/health')
    def health():return {'status':'ok'}
    html=(ROOT/'frontend/dist/index.html').read_text().replace('<html','<html data-indiebiz-surface="remote"',1)
    @app.get('/')
    def index():return HTMLResponse(html)
    app.mount('/assets',StaticFiles(directory=ROOT/'frontend/dist/assets'))
    sock=socket.socket();sock.bind(('0.0.0.0',0));port=sock.getsockname()[1]
    cfg=document_office.settings();assert cfg
    from urllib.parse import urlsplit
    cfg={**cfg,'callback_origin':f"http://{urlsplit(cfg['callback_origin']).hostname}:{port}"}
    monkeypatch.setattr(document_office,'settings',lambda:cfg)
    server=uvicorn.Server(uvicorn.Config(app,log_level='error'))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
    try:
        deadline=time.monotonic()+10
        while not server.started and time.monotonic()<deadline:time.sleep(.05)
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True)
            page=browser.new_page(viewport={'width':1600,'height':1100})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            try:
                page.goto(f'http://127.0.0.1:{port}/#/spreadsheets')
                page.get_by_label('로컬 파일 경로').fill(source)
                page.get_by_role('button',name='파일 열기',exact=True).click()
                expect(page.locator('.sheet-editor [role=status]')).to_have_text('편집 준비 완료',timeout=60000)
                expect(page.get_by_role('button',name='계산·스냅샷',exact=True)).to_be_enabled(timeout=20000)
                page.get_by_label('범위',exact=True).fill('B2')
                page.get_by_role('button',name='최신 범위 읽기',exact=True).click()
                expect(page.locator('.sheet-review pre').first).to_contain_text('effective_value',timeout=30000)
                page.get_by_text('직접 변경안 작성',exact=True).click()
                page.get_by_label('행·열 값 (JSON)').fill('[[7]]')
                page.get_by_role('button',name='변경안 만들기',exact=True).click()
                page.get_by_role('button',name='변경안 적용',exact=True).click()
                expect(page.locator('.sheet-editor [role=status]')).to_contain_text('변경 묶음 적용됨',timeout=30000)
                assert load_workbook(source).active['B2'].value==1, 'UI edits must not overwrite the source'
                page.get_by_role('button',name='원본 저장',exact=True).click()
                expect(page.locator('.sheet-editor [role=status]')).to_have_text('저장됨 · 원본 파일 기록 확인',timeout=60000)
                assert load_workbook(source).active['B2'].value==7
                assert load_workbook(source).active['D2'].value=='=B2*C2'
                document_id=workspace.list()[0]['id']
                queued=workspace.request_snapshot(document_id,'ibl-snapshot-test')
                deadline=time.monotonic()+30
                receipt=None
                while time.monotonic()<deadline:
                    receipt=workspace.operation_status(document_id,queued['operation_id'])
                    if receipt['completed']:break
                    page.wait_for_timeout(100)
                assert receipt and receipt['completed'],receipt
                assert receipt['result']['snapshot']['id']
                for literal in ('00123','=1+1'):
                    page.get_by_label('범위',exact=True).fill('A2')
                    page.get_by_role('button',name='최신 범위 읽기',exact=True).click()
                    expect(page.locator('.sheet-review pre').first).to_contain_text('A2',timeout=30000)
                    page.get_by_label('행·열 값 (JSON)').fill(__import__('json').dumps([[literal]]))
                    page.get_by_role('button',name='변경안 만들기',exact=True).click()
                    page.get_by_role('button',name='변경안 적용',exact=True).click()
                    expect(page.locator('.sheet-editor [role=status]')).to_contain_text('변경 묶음 적용됨',timeout=30000)
                    page.get_by_role('button',name='원본 저장',exact=True).click()
                    expect(page.locator('.sheet-editor [role=status]')).to_have_text('저장됨 · 원본 파일 기록 확인',timeout=60000)
                    cell=load_workbook(source).active['A2']
                    assert cell.value==literal and cell.data_type=='s'
                page.get_by_label('범위',exact=True).fill('B2')
                assert not errors,errors
                page.screenshot(path=str(tmp_path/'spreadsheet-app.png'))
                # Reuse the already verified snapshot only after re-reading current state.
                page.get_by_role('button',name='최신 범위 읽기',exact=True).click()
                expect(page.locator('.sheet-review pre').first).to_contain_text('\"entered_value\": 7',timeout=30000)
                from spreadsheet_changes import history
                operations=history(workspace,document_id)
                first=next(o for o in operations if workspace.store.get('sheet_proposal',o['proposal_id'])['range']=='B2')
                assert first['result'].get('snapshot_id'),first
                page.get_by_text('변경 취소와 가져오기 갱신',exact=True).click()
                page.get_by_role('button',name='변경·가져오기 이력',exact=True).click()
                page.get_by_role('button',name='변경 '+first['operation_id'][:8]+' 취소안',exact=True).click()
                expect(page.locator('.sheet-editor [role=status]')).to_contain_text('영향 셀만',timeout=40000)
                page.get_by_role('button',name='변경안 적용',exact=True).click()
                expect(page.locator('.sheet-editor [role=status]')).to_contain_text('변경 묶음 적용됨',timeout=40000)
                page.get_by_role('button',name='원본 저장',exact=True).click()
                expect(page.locator('.sheet-editor [role=status]')).to_have_text('저장됨 · 원본 파일 기록 확인',timeout=60000)
                restored=load_workbook(source)
                assert restored.active['B2'].value==1
                assert restored.active['A2'].value=='=1+1' and restored.active['A2'].data_type=='s'
                assert restored.active['D2'].value=='=B2*C2'
                print('ACTIVE_UNDO: restored B2 only; later literal-text A2 and formula D2 preserved')
                page.get_by_label('범위', exact=True).fill('A2:D2')
                page.get_by_text('범위 내보내기', exact=True).click()
                page.get_by_label('문자 인코딩', exact=True).select_option('cp949')
                with page.expect_download(timeout=60000) as download:
                    page.get_by_role('button', name='현재 범위 다운로드', exact=True).click()
                import csv
                import io
                exported = Path(download.value.path()).read_bytes()
                assert list(csv.reader(io.StringIO(exported.decode('cp949'))))[0] == ["'=1+1", '1', '0', '0']
                page.get_by_label('출력 형식', exact=True).select_option('json')
                with page.expect_download(timeout=60000) as download:
                    page.get_by_role('button', name='현재 범위 다운로드', exact=True).click()
                exported = __import__('json').loads(Path(download.value.path()).read_bytes())
                assert exported['items'][0]['entered_value'] == '=1+1'
                assert exported['items'][3]['formula'] == '=B2*C2'
                assert exported['metadata']['calc_status'] == 'fresh'
                assert load_workbook(source).active['A2'].value == '=1+1'
                print('ACTIVE_EXPORT: CP949 text-safe CSV and typed JSON downloaded through current snapshot')
                from spreadsheet_imports import import_csv
                csv_path=tmp_path/'repeat.csv';csv_path.write_text('id,amount\n00123,7\n00456,8\n')
                csv_doc=workspace.open(csv_path)['document']
                imported=import_csv(workspace,csv_doc['id'],csv_doc['revision_id'],types=['text','number'])
                imported_path=imported['document']['source_uri']
                page.get_by_label('로컬 파일 경로').fill(imported_path)
                page.get_by_role('button',name='파일 열기',exact=True).click()
                expect(page.locator('.sheet-editor [role=status]')).to_have_text('편집 준비 완료',timeout=60000)
                expect(page.get_by_role('button',name='계산·스냅샷',exact=True)).to_be_enabled(timeout=20000)
                page.get_by_text('변경 취소와 가져오기 갱신',exact=True).click()
                page.get_by_role('button',name='변경·가져오기 이력',exact=True).click()
                expect(page.get_by_label('갱신 CSV/TSV 파일')).to_be_enabled(timeout=10000)
                page.get_by_label('갱신 CSV/TSV 파일').set_input_files({'name':'updated.csv','mimeType':'text/csv','buffer':b'id,amount\n00123,9\n'})
                expect(page.locator('.sheet-editor [role=status]')).to_have_text('갱신 원본을 등록했습니다',timeout=20000)
                page.get_by_role('button',name='3행 가져오기 갱신안',exact=True).click()
                expect(page.locator('.sheet-editor [role=status]')).to_contain_text('갱신안을 적용하세요',timeout=40000)
                page.get_by_role('button',name='변경안 적용',exact=True).click()
                expect(page.locator('.sheet-editor [role=status]')).to_contain_text('변경 묶음 적용됨',timeout=40000)
                page.get_by_role('button',name='원본 저장',exact=True).click()
                expect(page.locator('.sheet-editor [role=status]')).to_have_text('저장됨 · 원본 파일 기록 확인',timeout=60000)
                result=load_workbook(imported_path)
                assert result.active['A2'].value=='00123' and result.active['A2'].data_type=='s'
                assert result.active['B2'].value==9 and result.active['A3'].value is None
                recipe=workspace.store.get('sheet_import',imported['import']['id'])
                assert recipe['rows_imported']==2 and len(recipe['runs'])==1
                print('ACTIVE_REFRESH: recorded types reapplied, shortened area cleared, ID preserved, source retained')
                original_bytes=Path(imported_path).read_bytes()
                page.get_by_label('변환 사본 형식',exact=True).select_option('ods')
                page.get_by_role('button',name='변환 사본 만들기',exact=True).click()
                expect(page.get_by_role('status').filter(has_text='XLSX → ODS')).to_be_visible(timeout=60000)
                ods_doc=next(d for d in workspace.list() if d['source_format']=='ods')
                assert Path(imported_path).read_bytes()==original_bytes
                assert ods_doc['provenance']['original_preserved'] is True
                page.get_by_label('변환 사본 형식',exact=True).select_option('xlsx')
                page.get_by_role('button',name='변환 사본 만들기',exact=True).click()
                expect(page.locator('.sheet-editor [role=status]')).to_have_text('편집 준비 완료',timeout=60000)
                copied=next(d for d in workspace.list() if d.get('provenance',{}).get('resource_id')==ods_doc['id'])
                book=load_workbook(copied['source_uri'])
                assert book.active['A2'].value=='00123' and book.active['A2'].data_type=='s'
                assert book.active['B2'].value==9
                from spreadsheet_formats import convert
                from test_spreadsheet_workspace import args as session_args
                # Template conversions use the same real engine and source fences.
                for fmt in ('xltx','ots'):
                    doc=workspace.detail(copied['id'])
                    converted=convert(workspace,copied['id'],fmt,doc['document']['revision_id'],**session_args(doc['session']))
                    template=converted['document']
                    reopened=convert(workspace,template['id'],'xlsx',template['revision_id'])
                    assert load_workbook(reopened['document']['source_uri']).active['A2'].value=='00123'
                import subprocess
                independent=tmp_path/'independent-conversion';independent.mkdir()
                result=subprocess.run(['soffice','-env:UserInstallation='+(tmp_path/'conversion-profile').as_uri(),
                    '--headless','--convert-to','xlsx','--outdir',str(independent),ods_doc['source_uri']],
                    capture_output=True,text=True,timeout=90)
                assert result.returncode==0,result.stderr
                reopened=load_workbook(independent/(Path(ods_doc['source_uri']).stem+'.xlsx'))
                assert reopened.active['A2'].value=='00123' and reopened.active['B2'].value==9
                assert Path(imported_path).read_bytes()==original_bytes
                from openpyxl import Workbook
                from openpyxl.chart import BarChart, Reference
                from document_creation import import_bytes
                fixture=Workbook();sheet=fixture.active
                sheet.append(['품목','수량','단가','합계'])
                sheet.append(['00123',7,33.5,'=B2*C2'])
                sheet['A3']='=1+1';sheet['A3'].data_type='s';sheet['B3']=False
                sheet['D2'].number_format='#,##0.00'
                chart=BarChart();chart.add_data(Reference(sheet,min_col=2,max_col=3,min_row=1,max_row=2),titles_from_data=True)
                sheet.add_chart(chart,'F1');sheet.print_title_rows='1:1';sheet.print_area='A1:J20'
                fixture.create_sheet('보조')['A1']='한글 보존'
                buffer=io.BytesIO();fixture.save(buffer)
                original=import_bytes(workspace,'형식 인수.xlsx',buffer.getvalue())['document']
                odf_copy=convert(workspace,original['id'],'ods',original['revision_id'])['document']
                returned=convert(workspace,odf_copy['id'],'xlsx',odf_copy['revision_id'])['document']
                formulas=load_workbook(returned['source_uri']);values=load_workbook(returned['source_uri'],data_only=True)
                assert formulas.active['D2'].value=='=B2*C2' and values.active['D2'].value==234.5
                assert formulas.active['A2'].value=='00123' and formulas.active['A3'].value=='=1+1'
                assert formulas.active['A3'].data_type=='s' and values.active['B3'].value is False
                # The converter changes a boolean literal into =FALSE(). This is
                # a reported loss, not a pass of the literal-type preservation gate.
                assert formulas.active['B3'].value=='=FALSE()'
                assert odf_copy['provenance']['loss_report']['changes']
                assert returned['provenance']['loss_report']['changes']
                assert len(formulas.active._charts)==1 and formulas['보조']['A1'].value=='한글 보존'
                assert Path(original['source_uri']).read_bytes()==buffer.getvalue()
                print('ACTIVE_CONVERSION: XLSX/ODS and XLTX/OTS copies; LibreOffice reopening; text, formula 234.5, chart and 2 sheets; boolean representation loss reported; original unchanged')
            except Exception:
                page.screenshot(path=str(tmp_path/'spreadsheet-failure.png'))
                print('UI',page.locator('body').inner_text()[-6000:])
                print('PAGE ERRORS',errors)
                for f in page.frames[1:]:
                    try:print('EDITOR',f.locator('body').inner_text()[-2000:])
                    except Exception:pass
                raise
            finally:browser.close()
    finally:
        server.should_exit=True;thread.join(timeout=10);sock.close()


if __name__ == '__main__':
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
