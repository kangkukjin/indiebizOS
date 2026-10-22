"""연구 대화 실행과 IBL 입구. 모델 호출은 부팅 시 주입한다."""
import json
import threading
from pathlib import Path

import task_receipts
import thread_context
from project_manager import ProjectManager
from research_store import ResearchStore, identifier
from conversation_db import ConversationDB
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
                elif kind in {'tool_start', 'tool_result', 'cognition', 'thinking'}:
                    from research_capture import sanitize
                    with store.connect(True) as db:
                        store.check_epoch(db)
                        store.event(db, kind, sanitize(event), tid, run)
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
        return {'items': [{**dict(r), 'message_time': ConversationDB.message_timestamp(r['message_time'])} for r in rows]}
    thread = store.thread(tid)
    if op == 'thread_messages':
        if params.get('questions_only'):
            from research_questions import ResearchQuestions
            return ResearchQuestions(store, tid).read(question_id=params.get('question_id'), cursor=cursor,
                limit=limit, query=params.get('query') or '', history=bool(params.get('question_history')))
        out = store.messages(tid, cursor or None, limit)
        lib = ResearchLibrary(store)
        with store.connect() as db:
            materials = [dict(r) for r in db.execute('SELECT DISTINCT v.id AS version_ref,s.title,v.coverage,s.origin FROM research_captures c '
                                                    'JOIN research_versions v ON v.id=c.version_id JOIN research_sources s ON s.id=v.source_id '
                                                    'WHERE c.thread_id=? ORDER BY c.created_at DESC LIMIT 50', (tid,))]
        with store.connect() as db:
            perspective_history = [dict(r) for r in db.execute(
                "SELECT id,body,origin,created_at FROM research_notes WHERE thread_id=? AND origin IN ('user','agent') ORDER BY id DESC LIMIT 20", (tid,))]
        labels = {'complete': '', 'completed': '', 'running': '답변 중', 'cancelled': '중단', 'interrupted': '재시작으로 중단', 'failed': '실패'}
        for item in out['items']:
            item['status_label'] = labels.get(item['status'], item['status'])
            if item['role'] == 'assistant':
                item.update(chat_activity(store, tid, item['run_id']))
            for attachment in item['attachments']:
                attachment['path'] = store.material_path(attachment['blob'], attachment['mime'])
        return {**out, **thread, 'perspective_history': perspective_history, 'materials': materials, 'citations': [dict(c, version_ref=c['version_id']) for m in out['items'] for c in m['citations']], 'project_ref': store.uid,
                'controls': [{'title': '', 'thread_ref': tid}] if thread['active_run'] else [],
                'run_status': '조사 중 — 확보한 자료는 순서대로 저장됩니다' if thread['active_run'] else '질문을 이어갈 수 있습니다'}
    if op == 'thread_update':
        if 'questions' in params:
            if any(k in params for k in ('notes', 'title', 'mode')):
                raise ValueError('질문 변경은 대화 메모·설정 변경과 별도로 요청하세요')
            from research_questions import ResearchQuestions
            return ResearchQuestions(store, tid).apply(params['questions'],
                origin='agent' if context else 'user', run=context.get('run_id'))
        changes = {k: params[k] for k in ('title', 'mode', 'notes') if k in params}
        if 'notes' in changes:
            notes = changes['notes']
            if not isinstance(notes, str) or len(notes) > 12000:
                raise ValueError('사용자의 관점은 12000자 이내의 문서로 정리하세요')
            if context.get('thread_id'):
                if params.get('expected_revision') is None:
                    raise ValueError('최신 문서의 revision을 expected_revision으로 지정하세요')
                import re
                refs = {int(value) for value in re.findall(r'\[발언:(\d+)\]', notes)}
                with store.connect() as db:
                    valid = {r[0] for r in db.execute("SELECT id FROM messages WHERE thread_id=? AND research_role='user'", (tid,))}
                if not refs or not refs <= valid:
                    raise ValueError('이 대화의 사용자 발언만 [발언:메시지ID]로 연결하세요')
        return {'items': [store.update_thread(tid, params.get('expected_revision'),
                                              notes_origin='agent' if context.get('thread_id') else 'user', **changes)]}
    if op == 'thread_archive':
        return {'items': [store.update_thread(tid, archived=bool(params.get('archived', True)))]}
    if op == 'thread_search':
        return store.messages(tid, cursor or None, limit, params.get('query') or '')
    if op == 'thread_send':
        request = params.get('request_id') or identifier()
        steered = steer(store, tid, str(params.get('message') or ''), request, params.get('attachments'))
        if steered is not None:
            return steered
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
        if not params.get('source_ref'):
            raise ValueError('versions 에는 source_ref 가 필요합니다 — sources 로 먼저 자료를 고르세요')
        return lib.versions(params.get('source_ref'))
    if op == 'read':
        max_chars = params.get('max_chars')
        return lib.read(params.get('version_ref'), int(params.get('cursor') or 0),
                        limit=12000 if max_chars is None else max_chars,
                        revision=params.get('extraction_revision'))
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


def chat_activity(store, tid, run):
    """대화 재개 때도 공통 채팅 도구 패널을 복원한다. 원문 자료의 정본은 자료실이다."""
    tools, out = [], {}
    with store.connect() as db:
        events = db.execute("SELECT kind,payload FROM research_events WHERE thread_id=? AND run_id=? "
                            "AND kind IN ('tool_start','tool_result','cognition','thinking') ORDER BY sequence", (tid, run))
        for row in events:
            event = json.loads(row['payload'])
            if row['kind'] == 'tool_start':
                tools.append({'id': event.get('id'), 'name': event.get('name', ''),
                              'input': event.get('input'), 'status': 'running'})
            elif row['kind'] == 'tool_result':
                target = next((t for t in reversed(tools) if event.get('id') and t['id'] == event['id']), None)
                if target is None:
                    target = next((t for t in reversed(tools) if t['name'] == event.get('name') and t['status'] == 'running'), None)
                if target is not None:
                    result = event.get('result', '')
                    target.update(status='done', result=result if isinstance(result, str) else json.dumps(result, ensure_ascii=False),
                                  isError=bool(event.get('is_error')))
                if target is not None and not event.get('is_error'):
                    inputs = target.get('input') if isinstance(target.get('input'), dict) else {}
                    if target['name'] == 'ask_user_question' and inputs.get('questions'):
                        out['questions'] = inputs['questions']
                    elif target['name'] in {'todo_write', 'mcp__indiebizos__todo_write'}:
                        from ibl_result_transport import tool_result_is_error
                        if not tool_result_is_error(result) and isinstance(inputs.get('todos'), list):
                            out['todos'] = inputs['todos']
                    elif target['name'] == 'exit_plan_mode' and '[[PLAN_APPROVAL_REQUESTED]]' in str(result):
                        out['plan_mode'] = {'active': True, 'phase': 'awaiting_approval',
                                            'plan_content': str(result).split('---', 1)[-1].strip()}
                if isinstance(event.get('todos'), list) and not event.get('is_error'):
                    out['todos'] = event['todos']
            elif row['kind'] == 'cognition' and event.get('decision'):
                out['cognition'] = {k: event.get(k) for k in ('decision', 'score', 'action', 'criteria')}
            elif row['kind'] == 'thinking':
                out['thinking'] = event.get('content', '')
    return {**out, 'tool_activities': tools}


def steer(store, tid, message, request, attachments):
    """일반 대화와 같은 steer_inbox를 사용한다. 수신 여부와 별개로 입력 기록을 보존한다."""
    import steer_inbox
    with store.connect(True) as db:
        store.check_epoch(db)
        previous = db.execute("SELECT payload FROM research_events WHERE thread_id=? AND kind='chat.steer'", (tid,)).fetchall()
        for row in previous:
            payload = json.loads(row['payload'])
            if payload.get('request_id') == request:
                if payload['message'] != message or attachments:
                    raise ValueError('같은 요청 신원으로 다른 메시지를 보낼 수 없습니다')
                return {'success': True, 'steered': True, 'items': []}
        thread = store.thread(tid, db)
        run = thread['active_run']
        if not run:
            return None
        # 원래 전송의 재접수는 begin_run의 기존 멱등 경로가 처리한다.
        if db.execute('SELECT 1 FROM tasks WHERE requester_channel=?', ('research:' + tid + ':' + request,)).fetchone():
            return None
        if attachments:
            raise ValueError('작업 중에는 텍스트로 방향을 수정할 수 있습니다. 파일은 현재 응답 완료 후 보내세요')
        if not message.strip() or len(message) > 2000:
            raise ValueError('작업 중 추가 지시는 1~2000자로 입력하세요')
        actor = f'research:{store.uid}:{tid}'
        source = db.execute("SELECT from_agent_id,to_agent_id FROM messages WHERE thread_id=? AND research_run=? AND research_role='user' LIMIT 1", (tid, run)).fetchone()
    # journal 콜백도 같은 DB에 기록하므로 기존 쓰기 트랜잭션 밖에서 접수한다.
    steer_inbox.post(actor, message, task_id=run, require_active=True, request_id=request)
    with store.connect(True) as db:
        store.check_epoch(db)
        previous = db.execute("SELECT payload FROM research_events WHERE thread_id=? AND kind='chat.steer'", (tid,)).fetchall()
        if not any(json.loads(row['payload']).get('request_id') == request for row in previous):
            db.execute("INSERT INTO messages(from_agent_id,to_agent_id,content,contact_type,thread_id,research_run,research_role,research_status) "
                       "VALUES (?,?,?,'research',?,?,'user','complete')", (*source, message, tid, run))
            store.event(db, 'chat.steer', {'request_id': request, 'message': message}, tid, run)
    return {'success': True, 'steered': True, 'items': [], 'message': '추가 지시를 접수했습니다. 다음 도구 결과 또는 응답 후 이어서 반영합니다'}
