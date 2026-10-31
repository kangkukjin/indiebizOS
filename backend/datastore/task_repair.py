"""일반 업무가 발견한 구현 결함의 한정 수리. 부모 목적과 수리 목적을 별도로 보존한다."""
import hashlib
import json
import re
import time
from pathlib import Path

import component_continuation as parent_tasks
import repair_continuation as journal

# 통제 기반 전체를 열지 않는다. 명세·권한은 그대로 두고 구현을 검사하는 첫 코어 경계.
CORE_IMPLEMENTATIONS = frozenset({'backend/ibl/ibl_v2_parser.py'})
NOTICE = '필요한 구현 수리를 같은 업무의 사본에서 진행합니다. 검사·반영 뒤 원래 업무를 자동으로 이어갑니다.'


def eligible(relative):
    path = Path(relative)
    return (path.as_posix() == relative and '..' not in path.parts and not path.is_absolute()
            and (relative in CORE_IMPLEMENTATIONS or bool(re.fullmatch(
                r'data/packages/installed/tools/(?!system_essentials/)[A-Za-z0-9_-]+/tool_[A-Za-z0-9_]+\.py', relative))))


def scope(row):
    return (row or {}).get('task_scope')


def check_delta(session, relatives):
    limit = scope(session)
    active = scope(journal.current())
    if active and limit != active:
        raise PermissionError('업무 수리의 사본 범위를 다른 세션으로 바꿀 수 없습니다')
    if not limit:
        return
    paths = limit.get('paths')
    if not isinstance(paths, list) or not paths or any(not eligible(p) for p in paths):
        raise PermissionError('업무 수리의 구현 범위가 유효하지 않습니다')
    outside = set(relatives) - set(paths)
    if outside:
        raise PermissionError('업무 수리 범위 밖 변경: ' + ', '.join(sorted(outside)))


def parent_of(row, base=None, *, check=True):
    limit = scope(row)
    if not limit:
        return None
    parent = journal.read(limit['parent'], base)
    if not parent or not parent_tasks.is_task(parent) or parent.get('repair_child') != limit['root']:
        raise PermissionError('수리의 원래 업무 연결이 유효하지 않습니다')
    if check:
        from task_cancellation import requested
        owner = 'system' if parent['system_ai'] else parent['project_id']
        if (parent['status'] != 'waiting_repair' or journal.cancelled(parent, base)
                or requested(owner, parent['original_task_id'])):
            raise PermissionError('원래 업무가 취소되었거나 수리 대기 상태가 아닙니다')
        budget = parent['budget']
        if (budget.get('deadline_at') is not None and budget['deadline_at'] <= time.time()
                or budget.get('hard_token_limit') is not None
                and budget['input'] + budget['output'] >= budget['hard_token_limit']):
            raise PermissionError('원래 업무의 관측 예산·시간 한도가 끝났습니다')
        import conversation_sessions as sessions
        b = parent['last_conversation']
        with sessions.connection(b['db_path']) as conn:
            last = conn.execute('SELECT id,state FROM conversation_turns WHERE session_id=? '
                                'ORDER BY started_at DESC,id DESC LIMIT 1', (b['session_id'],)).fetchone()
        if not last or last[0] != b['turn_id'] or last[1] == 'cancelled':
            raise PermissionError('원래 대화에 새 요청이 있습니다. 이전 업무의 수리를 자동 실행하지 않습니다')
    return parent


def request(handler, payload, context, *, framing_factory):
    """기존 patch propose에서 파일 하나의 구현 수정만 접수한다. 현재 모델에 RED를 주지 않는다."""
    if context.tool_name != 'patch_op' or payload.get('op', 'propose') != 'propose' or handler._red_grant_active():
        return None
    raw = handler._get_path(payload)
    if not raw or not handler._REPO_ROOT:
        return None
    from runtime_utils import expand_body_path
    repo = Path(handler._REPO_ROOT).resolve()
    path = Path(expand_body_path(raw))
    path = path if path.is_absolute() else repo / path
    if not path.is_relative_to(repo):
        return None
    relative = path.relative_to(repo).as_posix()
    if not eligible(relative):
        return None
    from execution_turn import current
    from supervision_bus import current as supervisor
    turn, controller = current(), supervisor()
    if not turn or not controller or controller.repair_granted:
        raise PermissionError('직접 사용자 업무의 실행 문맥이 필요합니다')
    if not path.is_file() or path.resolve() != path or path.stat().st_nlink != 1:
        raise PermissionError('기존 일반 구현 파일만 업무 중 수리할 수 있습니다')
    reason = str(payload.get('reason') or '').strip()
    if not reason:
        raise ValueError('관측한 구현 결함과 원래 업무의 관계를 reason에 적으세요')
    before = path.read_text()
    content = payload.get('content')
    if content is None:
        old, new = payload.get('old_string'), payload.get('new_string')
        if not isinstance(old, str) or not old or not isinstance(new, str) or before.count(old) != 1:
            raise ValueError('old_string은 현재 구현에 정확히 한 번 있어야 합니다')
        content = before.replace(old, new, 1)
    if not isinstance(content, str) or content == before:
        raise ValueError('실제 구현 변경이 필요합니다')
    try:
        compile(content, relative, 'exec')
    except (SyntaxError, ValueError) as exc:
        raise ValueError(f'수정안의 Python 구문이 유효하지 않습니다: {exc}') from exc
    parent_tasks.arm(turn)
    parent = journal.read(turn.continuation_key) if turn.continuation_key else None
    if not parent:
        raise PermissionError('원래 대화·취소·예산을 보존할 수 없는 실행은 자동 수리하지 않습니다')
    signature = hashlib.sha256((relative + '\0' + content).encode()).hexdigest()
    if parent.get('repair_child'):
        if parent.get('repair_signature') != signature:
            raise PermissionError('진행 중인 수리 뒤에 원래 업무로 복귀해야 합니다')
        controller.apply_scheduled = {'task_repair': parent['repair_child']}
        return json.dumps({'success': True, 'pending_repair': True, 'key': parent['repair_child'], 'message': NOTICE}, ensure_ascii=False)
    if signature in parent.get('repair_signatures', []) or len(parent.get('repair_signatures', [])) >= 3:
        raise PermissionError('같은 수정의 반복 또는 원래 업무의 수리 시도 한도입니다')
    key = 'work-repair-' + hashlib.sha256((parent['task_id'] + signature).encode()).hexdigest()[:28]
    execution = key.replace('work-repair-', 'work-exec-')
    limit = {'parent': parent['task_id'], 'root': key, 'paths': [relative]}
    st = handler._staging_mod()
    with st._candidate.locked(str(repo), 'application'):
        candidate = st.stage_file(str(repo), execution, str(path))
        if not candidate:
            raise RuntimeError('수리 사본을 준비하지 못했습니다')
        session = st.read_session(str(repo), execution)
        session.update(task_scope=limit, repair_policy=2, root_task_id=key)
        st._candidate.target(repo / session['worktree'], relative).write_text(content)
        st._candidate.collect(str(repo), session)
        st._save_session(str(repo), session)
    # 원래 기준을 후보 적용의 조건으로 삼지 않는다. 수리 검사 뒤 부모가 실제 업무를 마친다.
    goal = ('원래 사용자 업무를 계속하기 위해 관측된 구현 결함을 수리하세요. 기존 공개 계약·권한·지침을 유지하고 '
            '사본에서 관련 검사를 수행해 self:patch apply로 반영하세요. 파일 범위를 넓히지 마세요. '
            '수리 완료가 원래 업무 완료는 아니며 부모 실행자가 남은 일을 맡습니다.\n' + json.dumps(
                {'original_goal': parent['goal'], 'observed_defect': reason, 'implementation': relative}, ensure_ascii=False))
    child = {'task_id': key, 'root_task_id': key, 'resume_task_id': execution, 'staging_task_id': execution,
             'task_scope': limit, 'status': 'waiting_execution', 'phase': 'execution', 'retry_at': 0,
             'authorized_origin': 'user', 'goal': goal, 'framing': framing_factory(goal), 'repair_policy': 2,
             'attempt': 0, 'failures': [], 'worktree': session['worktree'], 'created_at': time.time(),
             **{k: parent[k] for k in ('agent_id', 'project_id', 'system_ai')}}
    parent.update(status='waiting_repair', repair_child=key, repair_signature=signature,
                  repair_signatures=[*parent.get('repair_signatures', []), signature])
    # 저장 사이 사망 시 부모는 같은 child key를 복원한다. 부모 없는 자식은 실행하지 않는다.
    parent['repair_request'] = child
    journal.save(parent)
    journal.save(child)
    controller.apply_scheduled = {'task_repair': key}
    return json.dumps({'success': True, 'pending_repair': True, 'key': key, 'message': NOTICE}, ensure_ascii=False)


def pending():
    from execution_turn import current
    turn = current()
    row = journal.read(turn.continuation_key) if turn and turn.continuation_key else None
    return row if row and row.get('status') == 'waiting_repair' and turn.task == row['execution_task_id'] else None


def pending_response():
    """어느 실행 구간에서 접수했든 원래 업무의 성공 판정 대신 인계 대기를 기록한다."""
    if not pending():
        return None
    from thread_context import set_goal_eval_outcome
    set_goal_eval_outcome(False, status='PENDING_REPAIR', reason=NOTICE)
    return NOTICE


def inherit_budget(turn):
    row = journal.current()
    if not turn or not scope(row):
        return
    parent = parent_of(row)
    from principal import is_owner
    from thread_context import get_task_origin
    if not is_owner() or get_task_origin() != 'user':
        raise PermissionError('직접 소유자 업무만 수리 예산을 이어받습니다')
    if row['resume_task_id'] != turn.task or row['agent_id'] != turn.agent or row['goal'] != turn.request:
        raise PermissionError('수리 자식 실행 신원이 다릅니다')
    parent_tasks.restore_budget(turn, parent)
    turn.continuation_key = parent['task_id']


def advance_parent(row, base, completion_check):
    """수리 종결 영수증을 확인한 뒤에만 일반 업무의 복귀를 연다."""
    key = row.get('repair_child')
    if not key:
        return row
    child = journal.read(key, base)
    if not child:
        child = journal.save(row['repair_request'], base)
    seen = set()
    while child.get('status') == 'continued' and child.get('child_task_id'):
        if child['task_id'] in seen:
            raise ValueError('수리 인계 순환')
        seen.add(child['task_id'])
        child = journal.read(child['child_task_id'], base)
        if not child:
            return None
    if child['status'] not in journal.TERMINAL:
        return None
    from restart_protocol import read_json
    session = read_json(Path(base) / 'data/system_ai_state/repair_sessions' /
                        (journal.key(child.get('staging_task_id') or child['task_id']) + '.json')) or {}
    passed, reason = completion_check(session, child, base)
    row.update(repair_result={'task': child['task_id'], 'success': passed, 'reason': reason,
                              'failure': child.get('reason', '') if not passed else '',
                              'response': child.get('response', '')}, returning_from_repair=True)
    row.pop('repair_child', None)
    row.pop('repair_request', None)
    # 실패여도 일반 실행자가 우회 가능성을 판단한다. 같은 후보를 다시 제출하지는 못한다.
    row.update(status='waiting', process='', generation='')
    return journal.save(row, base)
