"""Owner spreadsheet API. Editor I/O is additionally ticket and JWT fenced."""
import json
from functools import lru_cache
from html import escape
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from api_documents import authorize, invoke, LOOPBACK, OpenRequest, Command
from spreadsheet_workspace import SpreadsheetWorkspace, SpreadsheetEngine
import document_office
import spreadsheet_imports

router=APIRouter(prefix='/spreadsheets',tags=['spreadsheets'],dependencies=[Depends(authorize)])


@lru_cache(maxsize=1)
def service():
    return SpreadsheetWorkspace()


def engine():
    return SpreadsheetEngine(service())


@router.get('')
def listing():
    return {'items':invoke(service().list),'release_complete':False}


@router.post('/open')
def open_file(body:OpenRequest,request:Request):
    if not request.client or request.client.host not in LOOPBACK or request.headers.get('x-forwarded-for') or request.headers.get('cf-connecting-ip'):
        raise HTTPException(403,'원격에서는 등록 자료 ID 또는 파일 업로드를 사용하세요')
    return invoke(service().open,body.path)


@router.post('/new')
def new_file(body:Command):
    return invoke(service().create,**body.args)


@router.post('/import')
async def import_file(request:Request,filename:str):
    from document_creation import import_bytes
    data=bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data)>25*1024*1024:
            raise HTTPException(413,'파일 상한 25MB를 초과했습니다')
    return await run_in_threadpool(invoke,import_bytes,service(),filename,bytes(data))


@router.get('/engine-io/{session_id}/content')
def content(session_id:str,ticket:str):
    data,_=invoke(engine().content,session_id,ticket)
    return Response(data,media_type='application/octet-stream',headers={'Cache-Control':'no-store'})


@router.post('/engine-io/{session_id}/callback')
async def callback(session_id:str,ticket:str,request:Request):
    data=bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data)>1024*1024:
            raise HTTPException(413,'콜백 크기 초과')
    try:
        body=json.loads(data)
        if not isinstance(body,dict):
            raise ValueError()
    except ValueError as exc:
        raise HTTPException(400,'콜백 형식 오류') from exc
    return await run_in_threadpool(invoke,engine().callback,session_id,ticket,body,request.headers.get('authorization',''))


@router.get('/engine-io/{session_id}/plugin/{ticket}/{asset}')
def plugin(session_id:str,ticket:str,asset:str,request:Request):
    _,s=invoke(engine().ticket,session_id,ticket)
    cfg=document_office.settings()
    headers={'Cache-Control':'no-store','Access-Control-Allow-Origin':cfg['url']}
    if asset=='config.json':
        query=urlencode({'channel':ticket,'ib_parent':s['plugin_parent']})
        return JSONResponse({'name':'IndieBiz 스프레드시트','guid':SpreadsheetEngine.plugin_guid,
             'baseUrl':str(request.url).rsplit('/',1)[0]+'/',
             'variations':[{'description':'스냅샷과 범위 수정','url':'index.html?'+query,'isViewer':False,
                 'EditorsSupport':['cell'],'isVisual':False,'isModal':False,'isInsideMode':False,
                 'initDataType':'none','initData':'','buttons':[]}]},headers=headers)
    if asset=='index.html':
        sdk=escape(cfg['url'].rstrip('/')+'/sdkjs-plugins/v1/plugins.js',quote=True)
        return HTMLResponse('<!doctype html><meta charset="utf-8"><script src="'+sdk+'"></script><script src="plugin.js"></script>',headers=headers)
    if asset=='plugin.js':
        path=Path(__file__).resolve().parents[1]/'static/spreadsheet_plugin/plugin.js'
        return Response(path.read_text(),media_type='application/javascript',headers=headers)
    raise HTTPException(404,'편집기 자원이 없습니다')


@router.get('/{document_id}')
def detail(document_id:str):
    return invoke(service().detail,document_id)


@router.get('/{document_id}/versions')
def versions(document_id:str):
    return {'items':invoke(service().versions,document_id)}


@router.get('/{document_id}/snapshots/{snapshot_id}')
def read(document_id:str,snapshot_id:str,sheet_id:str,range:str):
    return invoke(service().read,document_id,snapshot_id,sheet_id,range)


@router.get('/{document_id}/events')
def events(document_id:str,after:int=0):
    invoke(service().detail,document_id)
    rows=service().store.events(document_id,max(0,after))
    return {'items':rows,'next':rows[-1]['sequence'] if rows else after,'has_more':len(rows)==200}


OPERATIONS={
    'report':SpreadsheetWorkspace.create_report,
    'csv-preview':spreadsheet_imports.preview, 'csv-import':spreadsheet_imports.import_csv,
    'sessions':SpreadsheetWorkspace.acquire,'reclaim':SpreadsheetWorkspace.reclaim,
    'snapshot':SpreadsheetWorkspace.snapshot,'propose':SpreadsheetWorkspace.propose,
    'ai':SpreadsheetWorkspace.generate_proposal,
    'apply':SpreadsheetWorkspace.apply,'pending':SpreadsheetWorkspace.pending,'receipt':SpreadsheetWorkspace.receipt,
    'save':SpreadsheetWorkspace.save,'export':SpreadsheetWorkspace.export_copy,
    'restore':SpreadsheetWorkspace.restore,'recover':SpreadsheetWorkspace.recover,'close':SpreadsheetWorkspace.close,
    'engine-config':lambda app,document_id,**args:SpreadsheetEngine(app).config(document_id,**args),
    'engine-capture':lambda app,document_id,**args:SpreadsheetEngine(app).capture(document_id,**args),
}


@router.post('/{document_id}/{operation}')
async def command(document_id:str,operation:str,request:Request):
    if operation not in OPERATIONS:
        raise HTTPException(404,'지원하지 않는 시트 작업입니다')
    data=bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data)>5*1024*1024:
            raise HTTPException(413,'요청 크기 상한을 초과했습니다')
    try:
        body=Command.model_validate_json(data)
    except ValueError as exc:
        raise HTTPException(422,'시트 작업 인자를 확인하세요') from exc
    if operation=='engine-config':
        body.args['browser_origin']=request.headers.get('origin') or str(request.base_url).rstrip('/')
        body.args['browser_api_origin']=str(request.base_url).rstrip('/')
    return await run_in_threadpool(invoke,OPERATIONS[operation],service(),document_id,**body.args)
