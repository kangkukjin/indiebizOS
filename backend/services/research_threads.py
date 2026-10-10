"""연구 대화 실행과 IBL 입구. 모델 호출은 부팅 시 주입한다."""
import json
import threading
from pathlib import Path

import task_receipts
import thread_context
from project_manager import ProjectManager
from research_store import ResearchStore, identifier
from research_library import ResearchLibrary
from research_capture import schedule_index
from research_context import scope

_run_stream = None
_summarize = None
_active = {}
_lock = threading.RLock()
_pool = None


def install(run_stream, summarize=None):
    global _run_stream, _summarize
    _run_stream, _summarize = run_stream, summarize
    task_receipts.register('research', task_status, cancel_task)


def resolve(project_ref):
    import principal
    from research_context import current
    if not principal.is_owner():
        raise PermissionError('연구 자료실은 프로젝트 소유자만 접근할 수 있습니다')
    pm = ProjectManager()
    row = next((p for p in pm.list_projects() if project_ref in {p.get('project_uid'), p.get('id')}
                and p.get('project_kind') == 'research' and not p.get('in_trash')), None)
    if not row:
        raise ValueError('연구 프로젝트를 찾을 수 없습니다')
    context = current()
    if context and context['project_uid'] != row['project_uid']:
        raise PermissionError('현재 연구 프로젝트 밖의 자료에는 접근할 수 없습니다')
    store = ResearchStore(pm.get_project_path(row['id']))
    with store.connect() as db:
        store.check_epoch(db)
    with _lock:
        store.recover_runs(set(_active))
    schedule_index(store.path)
    return row, store


def active_project(path):
    with _lock:
        return any(str(Path(path).resolve()) == entry['path'] for entry in _active.values())


def start(store, tid, message, request_id, attachments=()):
    global _pool
    if not _run_stream:
        raise RuntimeError('연구 실행기가 초기화되지 않았습니다')
    import runtime_work
    from execution_workers import create_executor
    lease = runtime_work.reserve('research-chat')
    with _lock:
        try:
            run, fresh = store.begin_run(tid, message, request_id, attachments)
        except BaseException:
            lease.close()
            raise
        if not fresh:
            lease.close()
            return {'success': True, 'accepted': True, 'task_ref': task_receipts.ref('research', run, store.uid)}
        cancel = threading.Event()
        _active[run] = {'cancel': cancel, 'path': str(store.path), 'thread': tid}
        if _pool is None:
            _pool = create_executor('research-chat', max_workers=4)
        try:
            _pool.submit(_work, store, tid, run, message, cancel, lease, thread_context.snapshot())
        except BaseException:
            _active.pop(run, None)
            store.write_response(tid, run, '실행을 시작하지 못했습니다', 'failed')
            lease.close()
            raise
    return task_receipts.receipt('research', run, owner=store.uid, thread_ref=tid)


def _work(store, tid, run, message, cancel, lease, snapshot):
    thread_context.restore(snapshot)
    context = {'project_uid': store.uid, 'thread_id': tid, 'run_id': run,
               'path': str(store.path), 'epoch': store.epoch, 'mode': store.thread(tid)['mode']}
    text, final, failure = '', None, None
    try:
        with lease.activate(), scope(context):
            for event in _run_stream(store, tid, run, message, cancel):
                kind = event.get('type')
                if kind == 'text':
                    text += str(event.get('content') or '')
                    store.write_response(tid, run, text)
                elif kind == 'final' and event.get('content'):
                    final = str(event['content'])
                elif kind == 'error':
                    failure = str(event.get('content') or event.get('error') or '실행 실패')
                elif kind in {'tool_start', 'cognition'}:
                    with store.connect(True) as db:
                        store.event(db, kind, {'name': event.get('name', ''), 'content': str(event.get('content') or '')[:1000]}, tid, run)
            text = final if final is not None else text
            if context.get('capture_failed'):
                failure = '자료를 보존하지 못해 추가 조사를 멈췄습니다. 저장 공간과 권한을 확인하세요.'
            state = 'cancelled' if cancel.is_set() else 'failed' if failure else 'completed'
            if failure:
                text += '\n\n조사 중 오류: ' + failure
            if not text:
                text = '조사를 중단했습니다.' if cancel.is_set() else '답변을 받지 못했습니다.'
                if not cancel.is_set():
                    state = 'failed'
            lib = ResearchLibrary(store)
            citations = lib.citations(text, run)
            valid = {(c['version_id'], c['locator']) for c in citations}
            import re
            text = re.sub(r'\[자료:([a-f0-9]{32}):([^\]]+)\]', lambda m: m.group(0) if (m[1], m[2]) in valid else '[확인되지 않은 인용]', text)
            if context.get('model_notice'):
                text += '\n\n' + context['model_notice']
            store.write_response(tid, run, text, state, citations)
            if state == 'completed' and _summarize:
                try:
                    _summarize(store, tid)
                except Exception:
                    # 요약은 파생 기억이다. 실패해도 확정된 답변·인용을 실패로 덮지 않는다.
                    import logging
                    logging.getLogger(__name__).exception('연구 대화 요약 실패; 다음 완료 턴에 재시도')
    except Exception as exc:
        try:
            store.write_response(tid, run, (text + '\n\n실행 오류: ' + str(exc)).strip(), 'failed')
        except Exception:
            pass  # 실행 신원이 만료된 프로젝트를 되살리지 않는다.
    finally:
        with _lock:
            _active.pop(run, None)
        lease.close()
        thread_context.clear_all_context()


def task_status(ref):
    try:
        _, store = resolve(ref.get('owner'))
        row = store.conversations.get_task(ref['task_id'])
        if not row or not str(row.get('requester_channel', '')).startswith('research:'):
            return task_receipts.view(ref, 'unknown')
        states = {'completed': 'succeeded', 'running': 'running', 'failed': 'failed', 'cancelled': 'cancelled', 'interrupted': 'interrupted'}
        return task_receipts.view(ref, states.get(row['status'], 'unknown'), result=row.get('result'),
                                  error=row.get('result') if row['status'] == 'failed' else None)
    except ValueError as exc:
        return task_receipts.view(ref, 'unknown', error=str(exc))


def cancel_task(ref):
    _, store = resolve(ref.get('owner'))
    with _lock:
        item = _active.get(ref['task_id'])
        if item and item['path'] == str(store.path):
            item['cancel'].set()
            return task_receipts.view(ref, 'cancel_requested')
    return task_status(ref)


def project_operation(params):
    row, store = resolve(params.get('project_ref') or params.get('project_id'))
    op = params.get('op')
    tid = params.get('thread_ref')
    from research_context import current
    context = current() or {}
    if context.get('thread_id') and (tid != context['thread_id'] or op in {'thread_list', 'thread_create'}):
        raise PermissionError('현재 대화의 기록만 사용할 수 있습니다')
    limit = int(params.get('limit') or 50)
    if not 1 <= limit <= 100:
        raise ValueError('limit은 1~100이어야 합니다')
    cursor = int(params.get('cursor') or 0)
    if op == 'research_view':
        from research_view import manifest
        return {'success': True, 'manifest': manifest(store.uid, row['name'], store.thread(tid)['id']), 'items': []}
    if op == 'thread_list':
        return store.threads(bool(params.get('archived')), params.get('query') or '', cursor, limit)
    if op == 'thread_create':
        return {'items': [store.create_thread(params.get('title') or params.get('name'), params.get('agent_id') or '', params.get('mode') or 'research')]}
    if op == 'thread_search' and not tid:
        with store.connect() as db:
            rows = db.execute("SELECT m.content,m.message_time,m.research_role AS role,t.title AS thread_title,t.id AS thread_ref "
                              "FROM messages m JOIN research_threads t ON t.id=m.thread_id "
                              "WHERE m.content LIKE ? AND m.id<? ORDER BY m.id DESC LIMIT ?",
                              ('%' + str(params.get('query') or '') + '%', cursor or 9223372036854775807, limit)).fetchall()
        return {'items': [dict(r) for r in rows]}
    thread = store.thread(tid)
    if op == 'thread_messages':
        out = store.messages(tid, cursor or None, limit)
        lib = ResearchLibrary(store)
        with store.connect() as db:
            materials = [dict(r) for r in db.execute('SELECT DISTINCT v.id AS version_ref,s.title,v.coverage,s.origin FROM research_captures c '
                                                    'JOIN research_versions v ON v.id=c.version_id JOIN research_sources s ON s.id=v.source_id '
                                                    'WHERE c.thread_id=? ORDER BY c.created_at DESC LIMIT 50', (tid,))]
        labels = {'complete': '', 'completed': '', 'running': '답변 중', 'cancelled': '중단', 'interrupted': '재시작으로 중단', 'failed': '실패'}
        for item in out['items']:
            item['status_label'] = labels.get(item['status'], item['status'])
            for attachment in item['attachments']:
                attachment['path'] = store.material_path(attachment['blob'], attachment['mime'])
        return {**out, **thread, 'materials': materials, 'citations': [dict(c, version_ref=c['version_id']) for m in out['items'] for c in m['citations']], 'project_ref': store.uid,
                'controls': [{'title': '', 'thread_ref': tid}] if thread['active_run'] else [],
                'run_status': '조사 중 — 확보한 자료는 순서대로 저장됩니다' if thread['active_run'] else '질문을 이어갈 수 있습니다'}
    if op == 'thread_update':
        changes = {k: params[k] for k in ('title', 'mode', 'notes') if k in params}
        return {'items': [store.update_thread(tid, params.get('expected_revision'), **changes)]}
    if op == 'thread_archive':
        return {'items': [store.update_thread(tid, archived=bool(params.get('archived', True)))]}
    if op == 'thread_search':
        return store.messages(tid, cursor or None, limit, params.get('query') or '')
    if op == 'thread_send':
        request = params.get('request_id') or identifier()
        attachments = prepare_attachments(store, tid, params.get('attachments') or [], request)
        return start(store, tid, str(params.get('message') or ''), request, attachments)
    if op == 'thread_cancel':
        run = thread['active_run']
        return cancel_task(task_receipts.ref('research', run, store.uid)) if run else {'items': [], 'message': '진행 중인 실행이 없습니다'}
    raise ValueError('지원하지 않는 연구 대화 연산')


def notebook_operation(params):
    if params.get('name') and params.get('project_ref'):
        raise ValueError('name과 project_ref는 함께 지정할 수 없습니다')
    _, store = resolve(params.get('project_ref'))
    from research_context import current
    tid = params.get('thread_ref') or (current() or {}).get('thread_id')
    if not tid:
        raise ValueError('대화 자료실의 thread_ref를 지정하세요')
    lib = ResearchLibrary(store, tid)
    op = params.get('op') or 'sources'
    if op == 'sources':
        return lib.sources(params.get('query') or '', int(params.get('cursor') or 0), include_excluded=bool(params.get('include_excluded')))
    if op == 'search':
        top_k = int(params.get('top_k') or 12)
        if not 1 <= top_k <= 40:
            raise ValueError('top_k는 1~40이어야 합니다')
        return lib.search(params.get('query') or '', top_k)
    if op == 'versions':
        return lib.versions(params.get('source_ref'))
    if op == 'read':
        return lib.read(params.get('version_ref'), int(params.get('cursor') or 0), revision=params.get('extraction_revision'))
    if op == 'remove':
        return lib.exclude(params.get('source_ref'), params.get('excluded', True))
    if op == 'add':
        if params.get('version_ref'):
            result = lib.retry(params['version_ref'])
        elif params.get('path'):
            path = params['path']
            if str(path).startswith(('http://', 'https://')):
                result = lib.add_url(path)
            else:
                path = Path(path).expanduser()
                result = lib.add_file(path if path.is_absolute() else store.path / path)
        elif params.get('text'):
            result = lib.capture(params['text'], title=params.get('title') or '사용자 자료', kind='user')
        else:
            raise ValueError('저장할 파일 path 또는 text가 필요합니다')
        schedule_index(store.path)
        return {'items': [result], 'message': '원문을 저장했습니다. 검색 색인을 준비합니다.'}
    raise ValueError('연구 자료실은 sources/search/read/versions/add/remove를 사용하세요')


def prepare_attachments(store, tid, attachments, request):
    """공통 업로드 경로의 원문을 대화 자료실에 보존하고 메시지에 고정 참조를 남긴다."""
    if not isinstance(attachments, list) or len(attachments) > 20:
        raise ValueError('첨부파일은 한 번에 20개까지 보낼 수 있습니다')
    lib = ResearchLibrary(store, tid)
    saved = []
    for i, item in enumerate(attachments):
        if not isinstance(item, dict) or not item.get('path'):
            raise ValueError('첨부파일 경로가 필요합니다')
        path = Path(item['path']).expanduser().resolve(strict=True)
        if path.stat().st_size > 25 * 1024 * 1024:
            raise ValueError('첨부파일은 25MB 이하로 보내세요')
        receipt = lib.add_file(path, title=str(item.get('name') or path.name), run='attachment:' + tid + ':' + request, call=str(i))
        version = lib.version(receipt['version_ref'])
        saved.append({'name': str(item.get('name') or path.name), 'version_ref': receipt['version_ref'],
                      'mime': version['mime'], 'blob': version['blob']})
    if saved:
        schedule_index(store.path)
    return saved
