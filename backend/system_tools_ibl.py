"""system_tools IBL 통합 실행 계층 (2026-07-18 모듈화 — 1500줄 규칙)

system_tools.py 에서 verbatim 이동: execute_ibl 단일도구의 실행 본체
(_execute_ibl_unified — 첨부파일 참조 치환·엔진 위임·param 힌트 보강).
system_tools 가 재수출하므로 기존 `from system_tools import _execute_ibl_unified` 불변.
"""
import json
import time
from typing import Dict, Optional


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

# IBL_DEBUG 로그 디듀프 — 동일 코드 반복(=UI 라이브-상태 폴링)을 시간창으로 접어
# 디버그 로그 도배를 막는다. 일회성 명령·서로 다른 조회는 영향 없음.
_ibl_log_seen: Dict[str, float] = {}
_IBL_LOG_WINDOW = 30.0       # 같은 코드 재로그 최소 간격(초)


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
                "단일": '[sense:web_search]{query: "AI 뉴스"}',
                "파이프라인": '[sense:web_search]{query: "AI 뉴스"} >> [self:output]{op: "file", path: "result.md"}',
                "병렬": '[sense:web_search]{query: "AI"} & [sense:search_gnews]{query: "tech"}',
                "폴백": '[sense:stock]{op: "quote", ticker: "AAPL"} ?? [sense:web_search]{query: "AAPL stock"}'
            }
        }, ensure_ascii=False)

    # --- files 파라미터: $file:N 참조 정보 보관 (파싱 후 치환) ---
    files = tool_input.get("files")

    # 디버그 — 잘림 한도를 500자로 늘림. 8개 병렬 호출 같은 긴 IBL 코드도 회고 가능.
    _c = code if len(code) <= 500 else code[:500] + f"... [trunc, total={len(code)}]"
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
                    # open: 쿨다운 미경과 → 즉시 차단
                    _remaining = int(_open_until - _now) + 1
                    _fail_count = _entry.get("fails", _ACTION_FAIL_LIMIT)
                    print(f"[IBL] 액션 차단(open): {_node}:{_action} (연속 {_fail_count}회 실패, {_remaining}초 후 재시도 가능)")
                    return json.dumps({
                        "error": f"[{_node}:{_action}] 액션이 연속 {_fail_count}회 실패하여 일시 차단되었습니다. 약 {_remaining}초 후 자동으로 재시도가 허용됩니다. 그동안 파라미터를 점검하거나 다른 방법을 찾으세요.",
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

        # 노드 접근 체크
        if allowed is not None:
            for step in parsed:
                d = step.get("_node", step.get("node", ""))
                if d and not check_node_access(d, allowed):
                    return json.dumps(get_denied_message(d, allowed), ensure_ascii=False)

        # 실행 분기 결정
        # 1) 병렬(_parallel) 또는 fallback(_fallback_chain) → workflow_engine
        # 2) 파이프라인(2개 이상 step) → workflow_engine
        # 3) 단일 step → 직접 execute_ibl
        has_special = any(
            s.get("_parallel") or "_fallback_chain" in s
            for s in parsed
        )

        if len(parsed) == 1 and not has_special:
            # 단일 step 직접 실행
            step = parsed[0]
            ibl_input = {
                "_node": step.get("_node", step.get("node", "")),
                "action": step.get("action", ""),
                "params": step.get("params", {}),
                # 노드 주소지정(@별칭) 전달 — 단일 액션도 특정 노드로 라우팅(파이프 경로는 이미 전달됨).
                # 없으면 `[self:read]{...}@맥` 이 폰서 로컬 실행돼 맥 파일을 못 읽는다(다중노드 버그).
                "target_node": step.get("target_node"),
            }
            # 노드 타입 처리 (info, store, exec, output)
            node = step.get("_node", step.get("node", ""))
            if node in ("info", "store", "exec", "output"):
                ibl_input["_node_type"] = node
                if node == "info":
                    ibl_input["source"] = step.get("action", "")
                    sub_action = step.get("params", {}).get("action", "")
                    if sub_action:
                        ibl_input["action"] = sub_action
                elif node == "store":
                    ibl_input["store"] = step.get("action", "")
                    sub_action = step.get("params", {}).get("action", "")
                    if sub_action:
                        ibl_input["action"] = sub_action

            result = execute_ibl(ibl_input, project_path, agent_id)
        else:
            # 파이프라인 / 병렬 / fallback → workflow_engine
            # 이미 파싱 + $file:N 치환된 steps를 직접 전달 (재파싱 방지)
            from workflow_engine import execute_pipeline
            result = execute_pipeline(parsed, project_path, agent_id=agent_id)

        # (map_data → [MAP:] 변환은 execute_tool 래퍼의 재귀 수확 단일 관문에서 처리 —
        #  단독/파이프/병렬 모양별 승격 분기는 병렬(&) 중첩에서 지도를 유실해 폐기. 2026-07-13)

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
                    if _cnt >= _ACTION_FAIL_LIMIT:
                        _entry["open_until"] = time.monotonic() + _ACTION_OPEN_SECONDS
                        print(f"[IBL] 액션 차단(open) 진입: {_n}:{_a} ({_cnt}회 실패 — {_ACTION_OPEN_SECONDS}초 차단)")
                else:
                    _action_fail_counter.pop(_fk, None)  # 성공하면 reset → closed
        except Exception:
            pass

        # 단일-스텝 에러면 액션 사용법 힌트 부착 (실패 가시화 → 다음 턴 자가교정)
        result = _enrich_error_with_param_hint(result, code)

        if isinstance(result, dict):
            return json.dumps(result, ensure_ascii=False, indent=2)
        return str(result)

    except Exception as e:
        return json.dumps({"error": f"IBL 실행 오류: {str(e)}"}, ensure_ascii=False)
