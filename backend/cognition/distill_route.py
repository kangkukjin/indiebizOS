"""경험 증류의 '턴의 길' — 통한 원문에 이르기 전의 헛걸음과 참고한 것 (2026-11-14, docs/MEMORY_REPAIR_PLAN_2026_11_14.md R4).

왜 있나: 경험 증류는 성공한 실행의 마지막 코드만 남겼다. 10-15 이후 실패한 뒤 성공한 275턴 가운데
실행기억이 저장된 턴은 10개였고, 저장된 것도 답뿐이라 "무엇이 왜 안 됐고 무엇을 찾아봤더니 풀렸는가"는
어디에도 없었다. 같은 실패 34종이 3일 이상 되풀이되며 실패의 55%를 차지했다.

역할을 가른다. 여기(프로그램)는 사실만 모은다 — 호출 순서, 성공 여부, 실패의 오류 머리, 조회 단계.
그 턴이 배울 만한지, 무엇이 원인인지는 통합 증류의 판단 모델이 정하고(unified_distill.SYSTEM_PROMPT),
여기서는 그 선택이 근거에 있는 단계를 가리키는지만 확인해 용례의 출처 기록(provenance.routes)에 적는다.
"""
import json
import re
from datetime import datetime

MAX_STEPS = 24          # 판단 입력에 싣는 단계 수 상한(앞 4 + 뒤 20)
MAX_ROUTES = 3          # 한 용례에 남기는 길의 수(최근 것만)
MAX_PREVIOUS_STEPS = 10  # 직전 턴에서 싣는 단계 수(뒤에서부터)
_ACTION = re.compile(r'\[([a-z_]+:[a-z_0-9]+)\]')


def _error_head(result):
    try:
        data = json.loads(result) if isinstance(result, str) else result
        error = data.get('error') if isinstance(data, dict) else None
        if isinstance(error, dict):
            error = error.get('message') or error.get('error')
        if error:
            return ' '.join(str(error).split())[:160]
    except (ValueError, TypeError):
        pass
    return ' '.join(str(result or '').split())[:160]


def _is_lookup(code):
    try:
        from ibl_edition import explicit_source
        from ibl_distill_gates import memory_only_program
        return memory_only_program(explicit_source(code, 2))
    except Exception:
        return False


def _steps(tool_calls, source_ids):
    steps = []
    for index, tc in enumerate(tool_calls or [], 1):
        if not isinstance(tc, dict):
            continue
        name, request = tc.get('tool_name') or '', tc.get('input') or {}
        if name == 'execute_ibl' and isinstance(request, dict):
            code = request.get('code') or ''
            step = {'step': index, 'tool': 'execute_ibl', 'ok': tc.get('success') is True,
                    'actions': sorted(set(_ACTION.findall(code)))[:4]}
            if request.get('check'):
                step['check'] = True
            elif step['ok'] and _is_lookup(code):
                step['lookup'] = True
            if index in source_ids:
                step['source_id'] = source_ids[index]
            if not step['ok']:
                step['error'] = _error_head(tc.get('result'))
        elif name == 'read_guide':
            label = request.get('query') or request.get('name') or '' if isinstance(request, dict) else ''
            step = {'step': index, 'tool': 'read_guide', 'name': str(label)[:80], 'lookup': True}
        else:
            step = {'step': index, 'tool': str(name)[:32], 'ok': tc.get('success') is not False}
        steps.append(step)
    return steps


def turn_path(tool_calls, source_ids, always=False):
    """호출 순서의 요약. source_ids = {tool_call_index: 원문 번호}(판단이 고를 수 있는 성공 원문).

    통한 원문 앞에 실패한 실행도 조회도 없으면 None 을 돌려준다 — 곧장 성공한 턴의 판단 입력은 늘리지 않는다.
    always 는 직전 턴 근거가 있을 때 쓴다: 바로잡힌 길을 고른 원문에 묶으려면 이번 턴의 번호가 있어야 한다."""
    steps = _steps(tool_calls, source_ids)
    solved = [s['step'] for s in steps if 'source_id' in s]
    if not solved:
        return None
    before = [s for s in steps if s['step'] < max(solved)]
    failed = [s for s in before if s['tool'] == 'execute_ibl' and not s['ok'] and not s.get('check')]
    lookups = [s for s in before if s.get('lookup')]
    if not failed and not lookups and not always:
        return None
    path = {'failed_runs': len(failed), 'lookups': len(lookups)}
    if len(steps) > MAX_STEPS:
        path['omitted_steps'] = len(steps) - MAX_STEPS
        steps = steps[:4] + steps[-(MAX_STEPS - 4):]
    return {**path, 'steps': steps}


def previous_summary(previous, recorded_at):
    """같은 대화의 직전 턴을 판단 근거로 줄인다 — 그때의 사용자 말과 호출 순서. 실행이 없던 턴은 None.

    이번 사용자 말이 그 방법을 바로잡은 것인지는 판단 모델이 본다(R6). 여기서는 문장 꼴로 추측하지 않는다."""
    if not isinstance(previous, dict):
        return None
    steps = [s for s in _steps(previous.get('tool_calls'), {}) if not s.get('check')]
    if not any(s['tool'] == 'execute_ibl' for s in steps):
        return None
    try:
        gap = datetime.fromisoformat(str(recorded_at)) - datetime.fromisoformat(str(previous.get('recorded_at')))
        minutes = max(0, int(gap.total_seconds() // 60))
    except (TypeError, ValueError):
        minutes = None
    omitted = max(0, len(steps) - MAX_PREVIOUS_STEPS)
    return {'user_message': ' '.join(str(previous.get('user_message') or '').split())[:240],
            'minutes_ago': minutes, 'steps': steps[-MAX_PREVIOUS_STEPS:],
            **({'omitted_steps': omitted} if omitted else {})}


def _corrected(previous, chosen):
    """사용자가 바로잡은 직전의 길 — 직전 턴의 실행 단계를 가리키고 무엇을 바로잡았는지 적혔을 때만."""
    if not isinstance(previous, dict) or not isinstance(chosen, dict):
        return None
    cause, ids = chosen.get('cause'), chosen.get('previous_steps')
    if not isinstance(cause, str) or not cause.strip() or len(cause) > 200 or not isinstance(ids, list):
        return None
    steps = {s['step']: s for s in previous.get('steps', [])}
    hit = [steps[i] for i in ids if type(i) is int and i in steps and steps[i]['tool'] == 'execute_ibl']
    if not hit:
        return None
    return {'actions': sorted({a for s in hit for a in s.get('actions', [])})[:4],
            'error': '', 'cause': ' '.join(cause.split()), 'by': 'user'}


def build_route(path, chosen, source_ids, recorded_at=None, previous=None):
    """판단 모델이 고른 route 를 근거(path·직전 턴)와 대조해 저장할 꼴로 만든다. 근거 밖의 것은 버린다."""
    if not isinstance(path, dict) or not isinstance(chosen, dict):
        return None
    steps = {s['step']: s for s in path.get('steps', [])}
    selected = [s['step'] for s in steps.values() if s.get('source_id') in (source_ids or [])]
    limit = max(selected) if selected else None
    if limit is None:
        return None
    consulted = []
    for ident in chosen.get('consulted_steps') or []:
        step = steps.get(ident) if type(ident) is int else None
        if not step or not step.get('lookup') or step['step'] >= limit:
            continue
        pointer = ({'guide': step['name']} if step['tool'] == 'read_guide' else {'actions': step.get('actions', [])})
        if pointer not in consulted:
            consulted.append(pointer)
    failed = []
    for row in (chosen.get('failed') or [])[:2]:
        cause = row.get('cause') if isinstance(row, dict) else None
        ids = row.get('steps') if isinstance(row, dict) else None
        if not isinstance(cause, str) or not cause.strip() or len(cause) > 200 or not isinstance(ids, list):
            continue
        hit = [steps[i] for i in ids if type(i) is int and i in steps and steps[i]['step'] < limit
               and steps[i]['tool'] == 'execute_ibl' and not steps[i]['ok'] and not steps[i].get('check')]
        if hit:
            failed.append({'actions': sorted({a for s in hit for a in s.get('actions', [])})[:4],
                           'error': hit[0].get('error', ''), 'cause': ' '.join(cause.split())})
    corrected = _corrected(previous, chosen.get('corrected'))
    if corrected:
        failed = [corrected] + failed[:1]      # 사용자 교정이 가장 믿을 만한 실패 신호다 — 맨 앞에 둔다
    if not consulted and not failed:
        return None
    return {'at': str(recorded_at or datetime.now().isoformat())[:10], 'consulted': consulted[:4], 'failed': failed}


def attach_route(db, code, route):
    """이미 있는 같은 원문의 용례에 길을 덧붙인다(새 행을 만들지 않는다). 이름 있는 함수는 건드리지 않는다."""
    with db._get_connection() as conn:
        row = conn.execute("SELECT id, provenance FROM ibl_current_examples WHERE ibl_code = ? "
                           "AND COALESCE(alias,'') = '' ORDER BY updated_at DESC, id DESC LIMIT 1", (code,)).fetchone()
        if not row:
            return 0
        try:
            evidence = json.loads(row['provenance'] or '{}')
        except (ValueError, TypeError):
            evidence = {}
        if not isinstance(evidence, dict):
            evidence = {}
        evidence['routes'] = ([r for r in evidence.get('routes', []) if r != route] + [route])[-MAX_ROUTES:]
        conn.execute("UPDATE ibl_examples SET provenance = ? WHERE id = ?",
                     (json.dumps(evidence, ensure_ascii=False), row['id']))
        conn.commit()
        return row['id']
