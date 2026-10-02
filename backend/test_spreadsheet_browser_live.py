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
