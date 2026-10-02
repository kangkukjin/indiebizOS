"""Session-aware self:sheet operations; legacy file operations retain their names.

snapshot/save queue work to the owning editor. queued is not completion: status
returns the durable receipt. No operation executes model-generated source code.
"""
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def service():
    from spreadsheet_workspace import SpreadsheetWorkspace
    return SpreadsheetWorkspace()


SESSION=('document_id','session_id','client_id','epoch','expected')


def call(p,name,names):
    import principal
    if not principal.is_owner():raise PermissionError('스프레드시트는 소유자 전용입니다')
    args=p.get('args',{})
    if not isinstance(args,dict) or set(args)-set(names):raise ValueError('args에 허용되지 않은 시트 인자가 있습니다')
    args=dict(args)
    for key in names:
        if key in p:
            if key in args:raise ValueError('같은 인자를 중복 지정하지 마세요')
            args[key]=p[key]
    app=service()
    if name in ('request_save','export_copy'):
        d=app._doc(args.get('document_id'))
        target=Path(d['source_uri'])
        if name=='export_copy':
            filename=args.get('filename','')
            if not filename or Path(filename).name!=filename or '/' in filename or '\\' in filename:
                raise ValueError('사본은 새 파일명만 지정하세요')
            target=target.parent/filename
        guard=p.get('_path_guard')
        if not callable(guard):raise PermissionError('파일 쓰기 범위 검증기가 필요합니다')
        reason=guard(str(target),p.get('_project_path') or str(target.parent))
        if reason:raise PermissionError(str(reason))
    result=getattr(app,name)(**args)
    if isinstance(result,list):return {'success':True,'items':result}
    if isinstance(result.get('session'),dict):
        fields={'id','client_id','engine_epoch','session_revision','blob','saved_blob','state'}
        result={**result,'session':{k:v for k,v in result['session'].items() if k in fields}}
    return {'success':True,**result,'items':result.get('items',[result])}


def op_open(p):
    from runtime_utils import expand_body_path
    p=dict(p);args=dict(p.get('args') or {})
    raw=p.get('path',args.get('path'))
    if not isinstance(raw,str) or not raw:raise ValueError('open에는 path가 필요합니다')
    path=Path(expand_body_path(raw))
    if not path.is_absolute():path=Path(p.get('_project_path') or '.')/path
    p.pop('path',None);args['path']=str(path);p['args']=args
    return call(p,'open',('path',))


def op_snapshot(p):return call(p,'request_snapshot',('document_id','operation_id'))
def op_status(p):return call(p,'operation_status',('document_id','operation_id'))
def op_read(p):return call(p,'read',('document_id','snapshot_id','sheet_id','range'))
def op_propose(p):return call(p,'propose',('document_id','snapshot_id','sheet_id','range','values','kind'))
def op_apply(p):return call(p,'apply',SESSION+('proposal_id','operation_id'))
def op_save(p):return call(p,'request_save',('document_id','operation_id','expected_revision'))
def op_export(p):return call(p,'export_copy',SESSION+('operation_id','filename'))
def op_versions(p):return call(p,'versions',('document_id',))
def op_restore(p):return call(p,'restore',SESSION+('operation_id','revision_id'))
def op_capabilities(p):return call(p,'capabilities',('document_id',))
def op_recover(p):return call(p,'recover',('document_id',))
