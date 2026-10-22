"""Ephemeral executions of durable task sessions using the shared cognitive loop."""
from dataclasses import asdict
import json
from pathlib import Path
import threading
import time
import weakref

import conversation_sessions as sessions
import task_worker_store as store

_dispatch_lock = threading.RLock()
_dispatching = set()
_trees = weakref.WeakValueDictionary()
_resume_armed = False


def arm_resume():
    global _resume_armed
    _resume_armed = True


def resume():
    """The boot owner arms recovery; only a ready, active body dispatches it."""
    global _resume_armed
    import runtime_work
    registry = runtime_work.registry()
    with _dispatch_lock:
        if not _resume_armed or registry is not None and not registry.accepting:
            return
        recover_all()
        _resume_armed = False


def _tree(path, root, payload):
    from task_tree_budget import Tree
    with _dispatch_lock:
        key = str(path), root
        tree = _trees.get(key)
        if tree is None:
            with sessions.connection(path) as conn:
                first = conn.execute('SELECT worker_payload FROM tasks WHERE worker_root=? ORDER BY rowid LIMIT 1', (root,)).fetchone()
                limits = json.loads(first[0]).get('limits', {}) if first else payload.get('limits', {})
                used = conn.execute("SELECT COALESCE(SUM(json_extract(payload,'$.tokens')),0) FROM conversation_events WHERE json_extract(payload,'$.type')='worker.usage' AND json_extract(payload,'$.root')=?", (root,)).fetchone()[0]
            def record(amount):
                with sessions.connection(path) as conn:
                    store.event(conn, payload['controller'], 'worker.usage', {'root': root, 'tokens': amount})
            tree = Tree(limits.get('tokens'), limits.get('deadline'), limits.get('initial', 0) + used, record)
            _trees[key] = tree
        return tree


def _identity():
    from delegation_tasks import _owner_db_path
    from thread_context import get_current_project_id, get_current_task_id, get_current_agent_id
    binding = sessions.current()
    if not binding or not get_current_task_id():
        raise ValueError('scope:task는 세션에 속한 부모 작업에서 사용합니다')
    owner = get_current_project_id() or 'system'
    if Path(_owner_db_path('system')).resolve() == Path(binding.db_path).resolve():
        owner = 'system'
    expected = _owner_db_path(owner)
    if expected is None or Path(expected).resolve() != Path(binding.db_path).resolve():
        raise ValueError('부모 작업과 대화 저장소의 소유권이 다릅니다')
    return binding, owner, get_current_task_id(), get_current_agent_id() or 'system_ai'


def delegate(params, project_path):
    from delegation_tasks import envelope, accepted
    import principal
    binding, owner, parent, actor = _identity()
    request_id, message = params.get('request_id'), params.get('message')
    if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 200:
        raise ValueError('scope:task에는 1~200자 request_id가 필요합니다')
    if not isinstance(message, str) or not message.strip():
        raise ValueError('message가 필요합니다')
    ref = params.get('worker_ref')
    sid = None
    prior = None
    if ref:
        if not isinstance(ref, dict) or ref.get('owner') != owner:
            raise ValueError('이 부모가 소유한 worker_ref가 아닙니다')
        sid = ref.get('session_id')
        with sessions.connection(binding.db_path) as conn:
            prior = store.metadata(conn, sid)
        if not prior or prior['controller'] != binding.session_id or json.dumps(prior['principal'], sort_keys=True) != json.dumps(asdict(principal.current()), sort_keys=True):
            raise ValueError('이 대화가 소유한 worker_ref가 아닙니다')
    target = 'worker:' + (sid or request_id + ':' + parent)
    env = envelope(target, role=params.get('role'), allowed=params.get('allowed'), context=params.get('context'))
    if prior:
        saved_allowed = prior['envelope'].get('allowed')
        if saved_allowed is not None:
            current = env.get('allowed')
            env['allowed'] = sorted(set(saved_allowed) & set(current)) if current is not None else saved_allowed
    workspace = params.get('workspace') or (prior or {}).get('workspace')
    if workspace:
        from ibl_routing import system_capability
        project_path = system_capability('collaboration_workspace')(workspace, binding.session_id)
    from providers.base import _turn_token_ledger
    ledger = _turn_token_ledger.get() or {}
    limits = {'tokens': ledger.get('hard_token_limit'),
              'initial': ledger.get('input', 0) + ledger.get('output', 0),
              'deadline': time.time() + ledger['deadline'] - time.monotonic() if ledger.get('deadline') else None}
    payload = {'limits': limits, 'controller': binding.session_id, 'principal': asdict(principal.current()),
               'actor': actor, 'agent_id': (prior or {}).get('agent_id', actor), 'owner': owner,
               'project_path': str(project_path), 'envelope': env, 'workspace': workspace}
    row = store.accept(binding.db_path, parent, request_id, message, payload, session_id=sid)
    tree = _tree(binding.db_path, row['worker_root'], payload)
    if _turn_token_ledger.get() is not None:
        _turn_token_ledger.get()['tree'] = tree
    dispatch(binding.db_path, row['worker_session'])
    receipt = accepted(owner, row['task_id'], queued=row['status'] == 'queued',
                       worker_ref={'owner': owner, 'session_id': row['worker_session']},
                       parent_task_id=parent, child_task_id=row['task_id'], scope='task')
    if params.get('mode') == 'sync':
        from execution_capacity import suspended
        from task_receipts import wait
        with suspended():
            view = wait(receipt['task_ref'], timeout=240)
        return {**receipt, **view, 'worker_ref': receipt['worker_ref']}
    return receipt


def dispatch(path, sid):
    key = str(path), sid
    with _dispatch_lock:
        if key in _dispatching:
            return
        _dispatching.add(key)
        import runtime_work
        def drain():
            try:
                while row := store.claim(path, sid):
                    _run(path, row)
            finally:
                with _dispatch_lock:
                    _dispatching.discard(key)
                    # Close the accept/empty-queue race under the dispatcher lock.
                    with sessions.connection(path) as conn:
                        pending = conn.execute("SELECT 1 FROM tasks WHERE worker_session=? AND status='queued'", (sid,)).fetchone()
                        busy = conn.execute("SELECT 1 FROM tasks WHERE worker_session=? AND status IN ('running','waiting_children')", (sid,)).fetchone()
                    if pending and not busy:
                        dispatch(path, sid)
        bound = None
        try:
            bound = runtime_work.bind_lease(drain, 'task-session')
            threading.Thread(target=bound, name='task-session', daemon=True).start()
        except BaseException:
            if bound:
                bound.release()
            _dispatching.remove(key)
            raise


def _runner(payload, sid):
    from agent_runner import AgentRunner
    if payload['owner'] == 'system':
        from system_ai_core import get_system_ai_runner
        # A bound conversation creates a fresh runner and provider, never the singleton.
        runner = get_system_ai_runner()
        runner.project_path = Path(payload['project_path'])
        runner.ai.project_path = payload['project_path']
        runner.ai._provider.project_path = payload['project_path']
        return runner
    from agent_lifecycle import _load
    from delegation_tasks import _owner_db_path
    config = next((a for a in _load(Path(_owner_db_path(payload['owner'])).parent).get('agents', [])
                   if a.get('id') == payload['agent_id']), None)
    if not config:
        raise ValueError('부모 에이전트 설정이 삭제되어 작업자를 만들 수 없습니다')
    config = {**config, '_conversation_session': sid, '_project_path': payload['project_path'],
              '_project_id': payload['owner']}
    runner = AgentRunner(config)
    runner._init_ai()
    runner.running = True
    return runner


def _run(path, row):
    from delegation_tasks import received, with_context
    from thread_context import actor_context, set_current_project_id, set_current_agent_name
    from task_cancellation import requested
    from episode_logger import EpisodeLogger
    import principal
    payload = json.loads(row['worker_payload'])
    sid, task = row['worker_session'], row['task_id']
    state, result, binding, processes = 'failed', '', None, None
    try:
        if store.cancellation_requested(path, payload['owner'], task):
            state = 'cancelled'
            return
        session_store = sessions.SessionStore(path, 'conversations' if payload['owner'] == 'system' else 'messages',
                                              'worker:' + payload['controller'], create_legacy=False)
        binding = session_store.begin(sid)
        from task_tree_budget import scope as tree_scope
        with tree_scope(_tree(path, row['worker_root'], payload)), sessions.scope(binding), principal.narrow(principal.Principal(**payload['principal']), 'task delegation'), \
                received(payload['envelope']), actor_context(agent_id=payload['agent_id'], task_id=task):
            sessions.bind_task(task)
            set_current_project_id(payload['owner'])
            set_current_agent_name('과제 실행자')
            EpisodeLogger.start_episode('과제 실행자', row['original_request'], project_id=payload['owner'], task_id=task)
            history = store.history(path, sid)
            message = with_context(row['original_request'], payload['envelope'].get('context'))
            with sessions.connection(path) as conn:
                # Follow-ups need the same conditions the worker actually saw,
                # including structured context, not only the short request.
                store.event(conn, sid, 'worker.history', {'message': {'role': 'user', 'content': message}}, binding.turn_id)
            runner = _runner(payload, sid)
            cancelled = lambda: store.cancellation_requested(path, payload['owner'], task)
            if payload.get('workspace'):
                from ibl_routing import system_capability
                runner.config['_isolated_workspace'] = payload['project_path']
                processes = system_capability('collaboration_executor')(runner, payload['project_path'], task, cancelled)
            for item in runner.cognitive_stream(message, history,
                    extra_role=payload['envelope'].get('role', ''),
                    force_role='coding' if payload.get('workspace') else '',
                    allowed_set=payload['envelope'].get('allowed'), utterance_author='agent', cancel_check=cancelled):
                sessions.record_event(item)
                if item.get('type') == 'final':
                    result, state = item.get('content', ''), 'completed'
                elif item.get('type') == 'error':
                    result, state = item.get('content') or item.get('error') or str(item), 'failed'
                if item.get('type') in {'tool_start', 'tool_result', 'final'}:
                    text = item.get('content', '') if item['type'] == 'final' else json.dumps(item, ensure_ascii=False, default=str)
                    with sessions.connection(path) as conn:
                        store.event(conn, sid, 'worker.history', {'message': {'role': 'assistant', 'content': text}}, binding.turn_id)
            if cancelled():
                state = 'cancelled'
    except Exception as exc:
        state, result = 'failed', str(exc)
    finally:
        EpisodeLogger.end_episode()
        if processes:
            processes.close()
        if binding:
            session_store.finish(binding, state, result if state == 'failed' else None)
        store.finish(path, task, state, result)
        # Finishing a last child may have released an ancestor's queued follow-up.
        with sessions.connection(path) as conn:
            waiting = [r[0] for r in conn.execute("SELECT DISTINCT worker_session FROM tasks WHERE worker_session IS NOT NULL AND status='queued'")]
        for queued_sid in waiting:
            dispatch(path, queued_sid)


def authorize(ref):
    """Existing resident delegations keep their contract; task children require ownership."""
    from delegation_tasks import _owner_db_path
    path = _owner_db_path(ref.get('owner') or 'system')
    if not path or not Path(path).exists():
        return None
    with sessions.connection(path) as conn:
        if 'worker_session' not in {r[1] for r in conn.execute('PRAGMA table_info(tasks)')}:
            return None
        row = conn.execute('SELECT * FROM tasks WHERE task_id=?', (ref['task_id'],)).fetchone()
        if not row or not row['worker_session']:
            return None
        payload = json.loads(row['worker_payload'])
    binding = sessions.current()
    import principal
    if (not binding or Path(binding.db_path).resolve() != Path(path).resolve()
            or binding.session_id not in (payload['controller'], row['worker_session'])
            or json.dumps(payload['principal'], sort_keys=True) != json.dumps(asdict(principal.current()), sort_keys=True)):
        raise ValueError('이 세션이 소유한 과제 참조가 아닙니다')
    return path, dict(row), payload


def wake_after_reply(path, task):
    """After a resident reply commits, release any queued session follow-up."""
    with sessions.connection(path) as conn:
        if 'worker_session' not in {r[1] for r in conn.execute('PRAGMA table_info(tasks)')}:
            return
        row = conn.execute('SELECT worker_session FROM tasks WHERE task_id=?', (task,)).fetchone()
    if row and row[0]:
        dispatch(path, row[0])


def steer(ref, message, request_id):
    found = authorize(ref)
    if not found:
        raise ValueError('이 위임은 조향을 지원하지 않습니다. scope:task 실행자를 지정하세요')
    path, row, payload = found
    if not request_id:
        raise ValueError('조향에는 request_id가 필요합니다')
    with sessions.connection(path) as conn:
        events = [json.loads(r[0]) for r in conn.execute(
            "SELECT payload FROM conversation_events WHERE session_id=? ORDER BY id", (row['worker_session'],))]
    prior = next((e for e in events if e.get('type') == 'handoff.steer.accepted'
                  and e.get('request_id') == request_id and e.get('target', {}).get('task') == row['task_id']), None)
    if prior:
        if prior['instruction'] != message.strip() or prior.get('source') != 'agent':
            raise ValueError('같은 request_id로 다른 조향을 보낼 수 없습니다')
        delivery = 'accepted'
        for e in events:
            if prior['id'] in e.get('ids', []):
                delivery = e['type'].rsplit('.', 1)[-1]
        return {'success': True, 'accepted': True, 'delivery': delivery, 'task_ref': ref}
    from steer_inbox import post
    from thread_context import get_current_agent_id
    count = post(payload['agent_id'], message, row['task_id'], require_active=True,
                 request_id=request_id, source='agent', sender=get_current_agent_id())
    return {'success': True, 'accepted': True, 'delivery': 'accepted', 'pending': count, 'task_ref': ref}


def recover_all():
    from runtime_utils import get_base_path
    from system_ai_memory import MEMORY_DB_PATH
    for path in [Path(MEMORY_DB_PATH), *Path(get_base_path()).glob('projects/*/conversations.db')]:
        if not path.exists():
            continue
        with sessions.connection(path) as conn:
            if 'worker_session' not in {r[1] for r in conn.execute('PRAGMA table_info(tasks)')}:
                continue
        for sid in store.recover(path):
            dispatch(path, sid)
