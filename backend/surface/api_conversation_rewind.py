"""Owner-only previews and durable rewind jobs for conversation sessions."""
from fastapi import APIRouter, Depends
from pydantic import Field
from api_chat_sessions import Target, get_store
from api_coding import owner
from api_process_sessions import call
import conversation_rewind as service

router = APIRouter(prefix='/chat-sessions', dependencies=[Depends(owner)])


class Preview(Target):
    checkpoint: str
    mode: str = 'both'


class Apply(Target):
    preview: str = Field(min_length=1)


@router.get('/{sid}/checkpoints')
def checkpoints(sid: str, target: str = 'system_ai', project_id: str = '', agent_id: str = ''):
    return call(service.list_checkpoints, get_store(target, project_id, agent_id)[0], sid)


@router.post('/{sid}/rewinds/preview')
def preview(sid: str, req: Preview):
    return call(service.preview, get_store(req.target, req.project_id, req.agent_id)[0], sid, req.checkpoint, req.mode)


@router.post('/{sid}/rewinds')
def apply(sid: str, req: Apply):
    return call(service.submit, get_store(req.target, req.project_id, req.agent_id)[0], sid, req.preview)


@router.get('/{sid}/rewinds/{rid}')
def status(sid: str, rid: str, target: str = 'system_ai', project_id: str = '', agent_id: str = ''):
    return service.public(call(service.get, get_store(target, project_id, agent_id)[0], sid, rid))


@router.get('/{sid}/processes')
def processes(sid: str, target: str = 'system_ai', project_id: str = '', agent_id: str = ''):
    from coding_store import CodingStore
    import conversation_sessions as sessions
    from process_sessions import query, directory
    import json
    store = get_store(target, project_id, agent_id)[0]
    with sessions.connection(store.path) as conn: store.require(conn, sid)
    items = []
    for row in CodingStore().list('process_session'):
        binding = row.get('attribution') or {}
        if binding.get('session_id') == sid and binding.get('db_path') == store.path:
            try:
                end = json.loads((directory(row['id']) / 'output.json').read_text())['end']
            except (OSError, ValueError):
                end = 0
            items.append({'id': row['id'], 'command': row['command'], **query(row['id'], cursor=max(0, end-65536), limit_bytes=65536)})
    import remote_process_sessions
    for row in CodingStore().list('remote_process'):
        binding = row.get('attribution') or {}
        if binding.get('session_id') == sid and binding.get('db_path') == store.path:
            value = remote_process_sessions.status({'kind': 'remote_process', 'task_id': row['id'], '_history_cursor': max(0,row['end']-65536)})
            items.append({'id': row['id'], 'command': row['command'], **value})
    return {'items': items}
