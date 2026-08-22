"""system_tools IBL 통합 실행 계층 (2026-07-18 모듈화 — 1500줄 규칙)

system_tools.py 에서 verbatim 이동: execute_ibl 단일도구의 실행 본체
(_execute_ibl_unified — 첨부파일 참조 치환·엔진 위임·param 힌트 보강).
system_tools 가 재수출하므로 기존 `from system_tools import _execute_ibl_unified` 불변.
"""
import json
import re
import time
from typing import Dict, Optional

from episode_logger import truncate_for_log


# === 액션 서킷 브레이커 (같은 액션 반복 실패 방지) ===
# 표준 서킷 브레이커 패턴: closed → (연속 N회 실패) → open → (쿨다운 경과) → half-open
#   - closed: 정상 실행. 실패 시 fails 증가, 한도 도달하면 open.
#   - open: open_until 이전에는 즉시 차단. 쿨다운이 지나면 half-open으로 자동 전이.
#   - half-open: 1회 시험 실행 허용. 성공하면 reset(closed), 실패하면 다시 open.
# 키: "agent_id:node:action", 값: {"fails": int, "open_until": Optional[float]}
#   open_until 은 time.monotonic() 기준 epoch (벽시계 변경에 영향받지 않음).
#
# 주의: 인메모리 모듈 전역이라 워커 프로세스마다 독립적이다. 멀티 워커(uvicorn
# reload/다중 워커) 환경에서는 워커별로 카운터가 따로 쌓이지만, 쿨다운 기반
# 자동 복구(half-open)가 있으므로 어느 워커도 영구 차단되지 않는다.
_action_fail_counter: Dict[str, dict] = {}
_ACTION_FAIL_LIMIT = 3       # 연속 N번 실패 시 차단(open)
_ACTION_OPEN_SECONDS = 90    # open 상태 유지 시간(초). 경과 후 half-open 시험 허용.


def _params_sig(params) -> str:
    """호출 시그니처 — params 의 안정 해시 (교정 시험 판정용).

    판정 2026-08-20 (상상훈련 16회차): 차단기의 목적은 *같은 호출의 눈감은 반복*을 끊는
    것이지 자가교정을 처벌하는 게 아니다. 실측: project_id 누락 3연발 뒤 파라미터를
    교정한 올바른 호출까지 68초 차단 — 자가교정 1왕복이 원리적으로 막혔다. 파라미터를
    바꾼 호출은 open 창당 1회 즉시 허용한다(아래 trial_used 게이트 — 실패하면 재-open
    되고 그 창에서는 더 안 열리므로 폭주 방어는 보존).
    """
    import hashlib
    try:
        raw = json.dumps(params or {}, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        raw = str(params)
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:12]

# IBL_DEBUG 로그 디듀프 — 동일 코드 반복(=UI 라이브-상태 폴링)을 시간창으로 접어
# 디버그 로그 도배를 막는다. 일회성 명령·서로 다른 조회는 영향 없음.
_ibl_log_seen: Dict[str, float] = {}
_IBL_LOG_WINDOW = 30.0       # 같은 코드 재로그 최소 간격(초)
_IBL_DEBUG_CAP = 2000        # providers/claude_code.py _TOOLUSE_CAP_IBL 과 같은 값


def reset_action_breaker(key: Optional[str] = None) -> int:
    """액션 서킷 브레이커를 수동으로 리셋한다.

    key=None 이면 전체 초기화, 특정 키("agent_id:node:action")면 해당 항목만 제거.
    프로세스 재시작 없이 차단을 해제하는 복구 경로 (수동/self-check 용).
    Returns: 제거된 항목 수.
    """
    global _action_fail_counter
    if key is None:
        n = len(_action_fail_counter)
        _action_fail_counter = {}
        return n
    return 1 if _action_fail_counter.pop(key, None) is not None else 0


def get_action_breaker_state() -> Dict[str, dict]:
    """현재 차단(open/half-open 대기) 중인 액션 상태를 조회한다 (관측/디버그용)."""
    now = time.monotonic()
    out = {}
    for k, v in _action_fail_counter.items():
        open_until = v.get("open_until")
        if open_until is not None:
            out[k] = {
                "fails": v.get("fails", 0),
                "remaining_seconds": max(0, round(open_until - now, 1)),
                "state": "open" if now < open_until else "half-open",
            }
    return out


def _replace_file_refs_in_steps(steps: list, files: list):
    """파싱된 step 리스트의 params에서 $file:N 플레이스홀더를 실제 내용으로 치환.

    코드 문자열 수준에서 치환하면 HTML 등 따옴표/특수문자가 포함된 콘텐츠가
    IBL 파서를 깨뜨리므로, 파싱 후 params dict 값을 직접 교체한다.
    """
    for step in steps:
        # 일반 step
        params = step.get("params")
        if params and isinstance(params, dict):
            _replace_file_refs_in_dict(params, files)
        # 병렬 branches
        branches = step.get("branches")
        if branches and isinstance(branches, list):
            _replace_file_refs_in_steps(branches, files)
        # fallback chain
        chain = step.get("_fallback_chain")
        if chain and isinstance(chain, list):
            _replace_file_refs_in_steps(chain, files)


def _replace_file_refs_in_dict(d: dict, files: list):
    """dict 값에서 $file:N 플레이스홀더를 치환 (재귀)."""
    for key, val in d.items():
        if isinstance(val, str):
            for idx, file_content in enumerate(files):
                placeholder = f"$file:{idx}"
                if placeholder in val:
                    val = val.replace(placeholder, file_content)
            d[key] = val
        elif isinstance(val, dict):
            _replace_file_refs_in_dict(val, files)
        elif isinstance(val, list):
            _replace_file_refs_in_list(val, files)


def _replace_file_refs_in_list(lst: list, files: list):
    """list 요소에서 $file:N 플레이스홀더를 치환 (재귀)."""
    for i, val in enumerate(lst):
        if isinstance(val, str):
            for idx, file_content in enumerate(files):
                placeholder = f"$file:{idx}"
                if placeholder in val:
                    val = val.replace(placeholder, file_content)
            lst[i] = val
        elif isinstance(val, dict):
            _replace_file_refs_in_dict(val, files)
        elif isinstance(val, list):
            _replace_file_refs_in_list(val, files)


def _collect_step_nodes(obj, out: set):
    """스텝 트리에서 실행될 모든 노드명을 재귀 수집 (D5, 2026-08-05).

    예전엔 노드 ACL 이 step 의 최상위 `_node` 키만 봐서, 병렬(branches)·폴백(_fallback_chain)·
    [goal:](strategy)·[if:]/[case:](branches[].action, default) 복합 스텝이 무검사 통과했다
    — 제한 에이전트가 금지 노드에 도달 가능. 구조 키만 재귀해 params 값의 우연한 키와
    충돌하지 않는다. [if:]/[case:] 의 조건·source 평가도 노드 실행이므로 함께 수집한다.
    """
    if isinstance(obj, list):
        for item in obj:
            _collect_step_nodes(item, out)
        return
    if not isinstance(obj, dict):
        return
    d = obj.get("_node") or obj.get("node")
    if isinstance(d, str) and d:
        out.add(d)
    # [case:] 의 source ("node:action") / [if:] 브랜치의 condition ("node:action < 값")
    for key in ("source", "condition"):
        v = obj.get(key)
        if isinstance(v, str):
            m = re.match(r"\s*(\w+):\w+", v)
            if m:
                out.add(m.group(1))
    # 구조 키 재귀 — 일반 step 의 action 은 문자열이라 여기 안 걸린다
    for key in ("branches", "_fallback_chain", "action", "default", "strategy", "steps",
                "body", "catch", "finally", "_branch_steps"):
        v = obj.get(key)
        if isinstance(v, (list, dict)):
            _collect_step_nodes(v, out)


def _collect_step_actions(obj, out: list):
    """스텝 트리에서 코드에 등장한 (node, action) 쌍을 재귀 수집 — 사용 계수용 (2026-08-05).

    의미=어휘 수요(코드에 쓰였는가)이지 실행 완료가 아니다 — 폴백(??)의 뒷가지는
    앞이 성공하면 실행되지 않지만, 어휘가 요구된 사실은 계수한다.
    _collect_step_nodes 와 같은 구조 키만 재귀(병렬 branches·폴백 체인·[goal:] strategy·
    [if:]/[case:] 하위 action) — 일반 step 의 action 은 문자열이라 재귀에 안 걸린다."""
    if isinstance(obj, list):
        for item in obj:
            _collect_step_actions(item, out)
        return
    if not isinstance(obj, dict):
        return
    n = obj.get("_node") or obj.get("node")
    a = obj.get("action")
    if isinstance(n, str) and n and isinstance(a, str) and a:
        out.append((n, a))
    for key in ("branches", "_fallback_chain", "action", "default", "strategy", "steps",
                "body", "catch", "finally", "_branch_steps"):
        v = obj.get(key)
        if isinstance(v, (list, dict)):
            _collect_step_actions(v, out)


def _usage_origin(agent_id) -> str:
    """실행 출처 분류 — 계수의 origin 축.

    앱/조종실 표면은 시스템 프로젝트 컨텍스트로 식별(직접조작 표면이 자기 project_id 를
    thread_context 에 명시하는 관습 재사용). 포털 게이트도 project_id=앱모드로 오므로 app.

    ★자가점검(ibl_health_check)은 /ibl/execute 에 agent_id="__self_check__" 로 POST 하므로
    이 관문을 *지나간다* — 2026-08-15 이전에는 'agent' 로 오분류돼 실사용 계수를 오염시켰다
    (11일 표본에서 agent 계수의 55%가 순찰분). 은퇴/압축 감사는 origin='selfcheck' 를
    제외하고 읽을 것. 2026-08-15 이전의 origin='agent' 행에는 순찰분이 섞여 있다."""
    if agent_id == "__self_check__":
        return "selfcheck"
    try:
        from thread_context import get_current_project_id, get_current_surface
        pid = get_current_project_id()
        if pid == "앱모드":
            return "app"
        if pid == "수동모드":
            return "manual"
        if get_current_surface() == "web":
            return "web"
    except Exception:
        pass
    return "agent" if agent_id else "internal"


# ============ 통합 도구 실행 함수 ============

def _enrich_error_with_param_hint(result, code: str):
    """단일-스텝 액션이 에러로 끝나면 그 액션의 description(파라미터 용법 포함)을
    힌트로 붙인다.

    자율주행 경로의 '실패 가시화' — 모델은 이미 구조화 에러를 받아 다음 턴에 자가교정하지만,
    'city 또는 lat/lon 필요' 같은 핸들러 에러는 *어떤 파라미터가 유효한지*를 안 알려줘서
    약한 모델이 자기가 쓴 잘못된 파라미터명(예: location)을 못 고친다(valid≠correct).
    액션 description은 canonical 파라미터 용법을 담으므로, 실패 지점에서 그걸 돌려준다.
    (강제 재시도 루프는 더하지 않는다 — 에이전트 루프가 이미 재시도이고, 서킷브레이커가
    반복 실패를 격리한다. 빠진 건 '재시도'가 아니라 '재시도를 옳게 할 단서'였다.)"""
    try:
        # dict 또는 JSON 문자열 모두 수용 — 도구 패키지 핸들러는 json.dumps(...) 문자열을 반환한다.
        was_str = False
        obj = result
        if isinstance(result, str):
            try:
                obj = json.loads(result)
                was_str = True
            except Exception:
                return result
        if not isinstance(obj, dict):
            return result
        is_err = (obj.get("success") is False) or ("error" in obj and not obj.get("success"))
        if not is_err or obj.get("_param_hint") or obj.get("blocked"):
            return result
        from ibl_parser import parse as _p
        parsed = _p(code)
        if not (parsed and len(parsed) == 1 and not parsed[0].get("_parallel")):
            return result  # 파이프라인/병렬은 스텝별 결과로 이미 구분됨
        node = parsed[0].get("_node", "")
        action = parsed[0].get("action", "")
        from ibl_access import _load_nodes_data
        meta = _load_nodes_data().get("nodes", {}).get(node, {}).get("actions", {}).get(action, {})
        desc = (meta.get("description") or "").strip()
        if desc:
            obj["_param_hint"] = (
                f"[{node}:{action}] 올바른 사용법: {desc} "
                "— 위 사용법에 맞는 파라미터명/값으로 다시 시도하세요."
            )
            return json.dumps(obj, ensure_ascii=False, indent=2) if was_str else obj
    except Exception:
        pass
    return result


def _execute_ibl_unified(tool_input: dict, project_path: str, agent_id: str = None, cancel_check=None) -> str:
    """execute_ibl 통합 실행기 — IBL 코드 기반

    AI가 IBL 코드 문자열을 생성하면, 파서가 해석하고 엔진이 실행한다.
    code 파라미터를 우선 사용하며, 레거시(pipeline, node+action)도 호환 지원.
    """
    from ibl_engine import execute_ibl
    from thread_context import get_allowed_nodes
    from ibl_access import check_node_access, get_denied_message

    # 노드 접근 제어 (allowed_nodes)
    allowed = get_allowed_nodes()

    # --- IBL 코드 결정 ---
    code = tool_input.get("code") or tool_input.get("pipeline")

    if not code:
        return json.dumps({
            "error": "code 파라미터가 필요합니다.",
            "usage": {
                "단일": '[sense:search]{query: "AI 뉴스"}',
                "파이프라인": '[sense:search]{query: "AI 뉴스"} >> [self:write]{path: "result.md"}',
                "병렬": '[sense:search]{query: "AI"} & [sense:search]{source: "gnews", query: "tech"}',
                "폴백": '[sense:stock]{op: "quote", ticker: "AAPL"} ?? [sense:search]{query: "AAPL stock"}'
            }
        }, ensure_ascii=False)

    # --- files 파라미터: $file:N 참조 정보 보관 (파싱 후 치환) ---
    files = tool_input.get("files")

    # 디버그 — 잘림 한도 2000자. 표식 모양은 episode_logger 가 소유한다(단일 진실):
    # 옛 판은 `... [trunc, total=N]` 로 자기만의 모양을 썼는데, 같은 사실을 두 모양으로
    # 적으면 읽는 쪽이 두 벌을 알아야 한다(이름 드리프트). 폭도 tool_use 쪽과 맞춘다.
    _c = truncate_for_log(code, _IBL_DEBUG_CAP)
    # 폴링 도배 방지 — 동일 코드가 _IBL_LOG_WINDOW 초 안에 또 오면 로그 생략.
    # (UI 라이브-상태 폴링 op:queue 류가 디버그 로그를 덮는 걸 막음. 일회성 명령·서로 다른 조회는 그대로 보임.)
    _now_log = time.monotonic()
    _last_log = _ibl_log_seen.get(code)
    if _last_log is None or (_now_log - _last_log) > _IBL_LOG_WINDOW:
        print(f"[IBL_DEBUG] code={_c}")
    _ibl_log_seen[code] = _now_log
    if len(_ibl_log_seen) > 256:  # 가벼운 정리 — 창 지난 항목 제거(무한 성장 방지)
        for _k in [_k for _k, _v in _ibl_log_seen.items() if _now_log - _v >= _IBL_LOG_WINDOW]:
            _ibl_log_seen.pop(_k, None)

    # --- 서킷 브레이커 체크: open 상태면 쿨다운 동안만 차단, 경과하면 half-open 시험 허용 ---
    # 단일 액션만 체크 (파이프라인/병렬은 개별 액션이 아니라 통과)
    try:
        from ibl_parser import parse as _pre_parse
        _pre_parsed = _pre_parse(code)
        if _pre_parsed and len(_pre_parsed) == 1 and not _pre_parsed[0].get("_parallel"):
            _node = _pre_parsed[0].get("_node", "")
            _action = _pre_parsed[0].get("action", "")
            _fail_key = f"{agent_id or 'default'}:{_node}:{_action}"
            _entry = _action_fail_counter.get(_fail_key)
            _open_until = _entry.get("open_until") if _entry else None
            if _open_until is not None:
                _now = time.monotonic()
                if _now < _open_until:
                    # 교정 시험 (판정 2026-08-20, 상상훈련 16회차): 파라미터를 바꾼 호출은
                    # open 창당 1회 즉시 허용 — 실패하면 재-open + trial_used 유지라
                    # 그 창에서는 더 안 열린다(폭주 방어 보존, 자가교정 개통).
                    _cur_sig = _params_sig(_pre_parsed[0].get("params"))
                    _last_sig = _entry.get("last_params_sig")
                    if (_last_sig is not None and _cur_sig != _last_sig
                            and not _entry.get("trial_used")):
                        _entry["trial_used"] = True
                        print(f"[IBL] 액션 교정 시험 허용: {_node}:{_action} (파라미터 변경 감지 — open 창당 1회)")
                    else:
                        # open: 쿨다운 미경과 → 즉시 차단
                        _remaining = int(_open_until - _now) + 1
                        _fail_count = _entry.get("fails", _ACTION_FAIL_LIMIT)
                        print(f"[IBL] 액션 차단(open): {_node}:{_action} (연속 {_fail_count}회 실패, {_remaining}초 후 재시도 가능)")
                        _last_err = (_entry or {}).get("last_error")
                        _cause = f" 마지막 실패 사유: {_last_err}" if _last_err else ""
                        _trial_note = (" 파라미터를 바꾼 교정 호출은 차단 중에도 1회 즉시 허용됩니다."
                                       if not _entry.get("trial_used")
                                       else " 이번 차단 창의 교정 시험은 이미 사용했습니다 — 쿨다운을 기다리세요.")
                        return json.dumps({
                            "error": f"[{_node}:{_action}] 액션이 연속 {_fail_count}회 실패하여 일시 차단되었습니다. 약 {_remaining}초 후 자동으로 재시도가 허용됩니다. 그동안 파라미터를 점검하거나 다른 방법을 찾으세요.{_trial_note}{_cause}",
                            "last_error": _last_err,
                            "blocked": True,
                            "action": f"{_node}:{_action}",
                            "consecutive_failures": _fail_count,
                            "retry_after_seconds": _remaining,
                        }, ensure_ascii=False)
                else:
                    # half-open: 쿨다운 경과 → 이번 1회 시험 실행 허용 (성공 시 reset, 실패 시 재-open)
                    print(f"[IBL] 액션 half-open 시험: {_node}:{_action} (쿨다운 경과, 1회 시험 실행)")
    except Exception:
        pass

    # --- IBL 코드 파싱 + 실행 ---
    try:
        from ibl_parser import parse as parse_ibl
        parsed = parse_ibl(code)

        if not parsed:
            return json.dumps({"error": f"IBL 파싱 실패: {code}"}, ensure_ascii=False)

        # $file:N 치환 — 파싱 후 params 레벨에서 수행 (코드 문자열에서 치환하면
        # HTML 등 따옴표 포함 콘텐츠가 파서를 깨뜨림)
        if files and isinstance(files, list):
            _replace_file_refs_in_steps(parsed, files)

        # 노드 접근 체크 — 복합 스텝(&/??/[goal:]/[if:]/[case:]) 내부까지 재귀 수집 (D5)
        if allowed is not None:
            _nodes_in_code: set = set()
            _collect_step_nodes(parsed, _nodes_in_code)
            for d in sorted(_nodes_in_code):
                if not check_node_access(d, allowed):
                    return json.dumps(get_denied_message(d, allowed), ensure_ascii=False)

        # 실행 분기 결정
        # 1) 병렬(_parallel) 또는 fallback(_fallback_chain) → workflow_engine
        # 2) 파이프라인(2개 이상 step) → workflow_engine
        # 3) 단일 step → 직접 execute_ibl
        has_special = any(
            s.get("_parallel") or "_fallback_chain" in s
            for s in parsed
        )

        # 재개 (M5 §2.6): 실패 봉투의 resume={from_step, prev_ref} 로 그 step 부터 — 1~(from_step-1) 단은 재실행하지 않는다.
        resume = tool_input.get("resume")
        if isinstance(resume, dict) and resume.get("from_step"):
            from workflow_engine import execute_pipeline
            from common.spill import read_ref
            try:
                from_step = int(resume.get("from_step"))
            except (TypeError, ValueError):
                return json.dumps({"error": "resume.from_step 은 정수여야 합니다."}, ensure_ascii=False)
            if not (2 <= from_step <= len(parsed)):
                return json.dumps({"error": f"resume.from_step={from_step} 범위 밖 — 이 코드는 step {len(parsed)}개입니다(2 이상)."}, ensure_ascii=False)
            ref = resume.get("prev_ref")
            ref = {"path": ref} if isinstance(ref, str) else (ref or {})
            body, err = read_ref(ref)
            if err:
                return json.dumps({"error": f"resume 실패 — {err}"}, ensure_ascii=False)
            tail = [dict(st) if isinstance(st, dict) else st for st in parsed[from_step - 1:]]
            # 앞 단을 참조하는 $변수({{_step_N_result}}·_vars N < from_step-1)가 남아 있으면 정직 거절 — 빈 값 치환은 침묵 오답
            blob = json.dumps(tail, ensure_ascii=False)
            early = sorted({int(m) for m in re.findall(r"\{\{_step_(\d+)_result", blob) if int(m) < from_step - 1})
            for st in tail:
                if isinstance(st, dict):
                    early += [int(ix) for ix in (st.get("_vars") or {}).values() if int(ix) < from_step - 1]
            if early:
                return json.dumps({"error": f"resume 불가 — step {from_step} 이후가 재실행하지 않는 앞 단(step {sorted(set(x + 1 for x in early))})의 $변수를 참조합니다. 처음부터 다시 실행하세요."}, ensure_ascii=False)
            if isinstance(tail[0], dict):
                tail[0].pop("_seq_boundary", None)
            result = execute_pipeline(tail, project_path, context={"_prev_result": body}, agent_id=agent_id)
            if isinstance(result, dict):
                result["resumed_from"] = from_step
                for r in result.get("results") or []:
                    if isinstance(r, dict) and isinstance(r.get("step"), int):
                        r["step"] += from_step - 1
            from ibl_envelope import diet_envelope
            result = diet_envelope(result, verbose=bool(tool_input.get("verbose"))) if isinstance(result, dict) else result
            return json.dumps(result, ensure_ascii=False, indent=2) if isinstance(result, dict) else str(result)

        if len(parsed) == 1 and not has_special:
            # 단일 step 직접 실행
            step = parsed[0]
            if step.get("_goal") or step.get("_condition") or step.get("_case") or step.get("_try") or step.get("_repeat") or step.get("_assign"):
                # 복합 블록([goal:]/[if:]/[case:])은 step 통짜 전달 — 아래처럼 키를 골라
                # 담으면 _goal/_condition/_case 가 유실돼 엔진의 블록 디스패치에 못 닿고
                # "action 파라미터가 필요합니다"로 죽는다(전 표면 블록 실행 봉쇄 부류).
                _blk = dict(step)
                result = execute_ibl(_blk, project_path, agent_id)
                # ★F19-1: 분기 몸이 스칼라를 내면 통화에 관측 메타를 못 싣는다 — 단독 실행은
                # 하류 소비자가 없으므로 여기서 봉투로 감싸 어느 가지를 탔는지 보이게 한다.
                _bmeta = _blk.get("_branch_meta")
                if isinstance(_bmeta, dict) and not isinstance(result, dict):
                    result = {"result": result, **_bmeta}
            else:
                ibl_input = {
                    "_node": step.get("_node", step.get("node", "")),
                    "action": step.get("action", ""),
                    "params": step.get("params", {}),
                    # 노드 주소지정(@별칭) 전달 — 단일 액션도 특정 노드로 라우팅(파이프 경로는 이미 전달됨).
                    # 없으면 `[self:read]{...}@맥` 이 폰서 로컬 실행돼 맥 파일을 못 읽는다(다중노드 버그).
                    "target_node": step.get("target_node"),
                }
                # (2026-08-05 감사 D11) 옛 노드타입 특례(info/store/exec/output → _node_type 주입)
                # 삭제 — 그 노드들은 레지스트리에 없어, 이제 정상 경로의 명시 오류로 수렴한다.
                result = execute_ibl(ibl_input, project_path, agent_id)
        else:
            # 파이프라인 / 병렬 / fallback → workflow_engine
            # 이미 파싱 + $file:N 치환된 steps를 직접 전달 (재파싱 방지)
            from workflow_engine import execute_pipeline
            result = execute_pipeline(parsed, project_path, agent_id=agent_id)

        # (map_data → [MAP:] 변환은 execute_tool 래퍼의 재귀 수확 단일 관문에서 처리 —
        #  단독/파이프/병렬 모양별 승격 분기는 병렬(&) 중첩에서 지도를 유실해 폐기. 2026-07-13)

        # --- 액션 사용 계수 (표면 사각지대 해소, 2026-08-05) ---
        # episode_log 는 자율주행만 기록: 앱/조종실/원격의 /ibl/execute 직행이 안 보였다.
        # 어휘 은퇴·압축 판단은 ibl_usage.db action_usage_daily 를 본다. 실패는 무해 삼킴.
        try:
            _pairs: list = []
            _collect_step_actions(parsed, _pairs)
            if _pairs:
                from ibl_usage_db import bump_action_usage
                bump_action_usage(_pairs, _usage_origin(agent_id))
        except Exception:
            pass

        # --- 서킷 브레이커 상태 업데이트 ---
        # 실패: fails 증가, 한도 도달 시 open_until 설정(open/재-open). 성공: 항목 제거(reset → closed).
        # half-open 시험 실행이 실패하면 fails 는 이미 한도 이상이므로 곧장 open_until 갱신 → 재-open.
        try:
            _pre_parsed2 = parse_ibl(code)
            if _pre_parsed2 and len(_pre_parsed2) == 1 and not _pre_parsed2[0].get("_parallel"):
                _n = _pre_parsed2[0].get("_node", "")
                _a = _pre_parsed2[0].get("action", "")
                _fk = f"{agent_id or 'default'}:{_n}:{_a}"
                # 성공/실패 판정: *최상위* success/error만 본다. 중첩 "error" 키(예: 성공한
                # native 슬라이드의 verify.error: null)에 오탐하지 않도록 — 문자열이면 JSON 파싱 후
                # 최상위 키로 판정. (2026-06-23: '"error" in result' 부분문자열 검색이 성공한
                #  슬라이드를 실패로 오인 → 서킷 브레이커 오발동·죽음의 나선 버그)
                _is_err = False
                _ro = result if isinstance(result, dict) else None
                if _ro is None and isinstance(result, str):
                    try:
                        _ro = json.loads(result)
                    except Exception:
                        _ro = None
                if isinstance(_ro, dict):
                    _is_err = (_ro.get("success") is False) or ("error" in _ro and not _ro.get("success"))
                    # ★환경적 미도달(폰/맥이 일시적으로 안 닿음)은 '액션 고장'이 아니라
                    # 일시적 환경 조건 → 서킷브레이커가 세면 안 된다. 안 그러면 부팅 직후
                    # World Pulse 가 [sense:here]{} 를 폰에 보냈다가 폰이 아직 안 깨어나
                    # 3회 실패 → 90초 차단이 열리고, 그 사이 폰이 깨어난 뒤의 *정상* 호출까지
                    # 거짓 차단된다(phone_only 거짓양성). 미도달은 카운트 제외.
                    if _is_err and any(_ro.get(k) for k in
                                       ("phone_unreachable", "phone_forward",
                                        "mac_unreachable", "mac_forward")):
                        _is_err = False
                elif isinstance(result, str):
                    # 파싱 불가한 문자열: 보수적으로 최상위 실패 표식만
                    _is_err = '"success": false' in result or '"success":false' in result
                if _is_err:
                    _entry = _action_fail_counter.setdefault(_fk, {"fails": 0, "open_until": None})
                    _entry["fails"] += 1
                    _cnt = _entry["fails"]
                    # 교정 시험 판정용 — 마지막 실패 호출의 파라미터 시그니처 (2026-08-20)
                    _entry["last_params_sig"] = _params_sig(_pre_parsed2[0].get("params"))
                    # ★차단 메시지가 원인을 나를 수 있게 마지막 실패 사유를 보관.
                    # (원인 없는 "실패" 만 돌려주면 모델이 같은 호출을 눈감고 반복한다 —
                    #  2026-08-19 ep1251: 429 쿼터 소진이 "생성 실패"로만 보여 9분 낭비)
                    if isinstance(_ro, dict):
                        _le = _ro.get("error") or _ro.get("message")
                        if isinstance(_le, str) and _le.strip():
                            _entry["last_error"] = _le.strip()[:300]
                    if _cnt >= _ACTION_FAIL_LIMIT:
                        _entry["open_until"] = time.monotonic() + _ACTION_OPEN_SECONDS
                        print(f"[IBL] 액션 차단(open) 진입: {_n}:{_a} ({_cnt}회 실패 — {_ACTION_OPEN_SECONDS}초 차단)")
                else:
                    _action_fail_counter.pop(_fk, None)  # 성공하면 reset → closed
        except Exception:
            pass

        # 단일-스텝 에러면 액션 사용법 힌트 부착 (실패 가시화 → 다음 턴 자가교정)
        result = _enrich_error_with_param_hint(result, code)

        # 봉투 다이어트 (2026-08-22 프로그램급 IBL M1): 파이프 봉투의 results[] 는 step 요약,
        # final_result 만 원형 — 여기는 에이전트 경계(인프로세스·MCP 재진입·/ibl/execute 공통).
        # verbose: true 가 옛 모양. 표면은 final_result 만 읽으므로 무영향.
        if isinstance(result, dict):
            from ibl_envelope import diet_envelope
            result = diet_envelope(result, verbose=bool(tool_input.get("verbose")))

        if isinstance(result, dict):
            return json.dumps(result, ensure_ascii=False, indent=2)
        return str(result)

    except Exception as e:
        return json.dumps({"error": f"IBL 실행 오류: {str(e)}"}, ensure_ascii=False)
