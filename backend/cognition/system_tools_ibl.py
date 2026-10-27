"""system_tools IBL 통합 실행 계층 (2026-07-18 모듈화 — 1500줄 규칙)

system_tools.py 에서 verbatim 이동: execute_ibl 단일도구의 실행 본체
(_execute_ibl_unified — 검사 원문 참조·현행 엔진 위임·결과 투영).
system_tools 가 재수출하므로 기존 `from system_tools import _execute_ibl_unified` 불변.
"""
import runtime_work
import json
import hashlib
import re
import time
from typing import Dict, Optional

from common.value_semantics import dumps_public_result
from result_read_contract import is_observation_request


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


def _preview_boundary(result, tool_input: dict):
    """봉투 기본값 반전(2026-09-06 승인) — 모델 경계에서만 큰 구조 데이터를 미리보기로. 앱·원격 표면(호출 통로
    "app")은 렌더를 위해 전체를 받는다. 전체 값은 현재 실행의 증거 저장소에서 참조한다."""
    try:
        from thread_context import get_call_channel
        if get_call_channel() == "app":
            from ibl_result_transport import compact_recordings
            return compact_recordings(result)
        from model_result_view import project_result
        return project_result(result)
    except Exception as exc:
        from episode_logger import record_trajectory_event
        record_trajectory_event("context.projection_failed", {"error": str(exc)})
        return result


_CHECKED_CODE_RE = re.compile(r"\s*\$checked:([0-9a-f]{64})\s*")
_SAVED_REQUEST_KEYS = ("inputs", "budget", "edition", "value_protocols", "reuse", "function_refs", "composition", "completion", "repair")


def _offer_checked_code(checked, code, request=None) -> None:
    """검사를 통과한 프로그램에 실행 손잡이를 붙인다 — 같은 원문을 다시 적지 않게(ep4211).

    check 뒤 실행은 같은 프로그램을 통째로 다시 생성했다(다섯 쌍 약 195초, 7K자 한 편에 100초).
    원문을 증거 저장소에 두고 `code: "$checked:<id>"` 로 부르게 한다. 새 인자가 아니라 `$초안` 과 같은
    code 자리의 참조다. 비밀 후보로 가려진 원문은 손잡이를 주지 않는다(가려진 문자열이 실행되면 안 된다)."""
    if not isinstance(checked, dict) or checked.get("ok") is not True or checked.get("executed") is not False:
        return
    if not isinstance(code, str) or not code.strip():
        return
    try:
        from model_result_view import evidence_store
        saved = {key: request[key] for key in _SAVED_REQUEST_KEYS
                 if request is not None and key in request}
        if saved.get('repair') and checked.get('repair', {}).get('plan_hash'):
            saved['repair'] = {**saved['repair'], 'plan_hash': checked['repair']['plan_hash']}
        ref = evidence_store().evidence(json.dumps(
            {"kind": "checked_program", "code": code, "request": saved}, ensure_ascii=False))
    except (OSError, ValueError, TypeError):
        return
    if ref.get("masked_paths"):
        return
    checked["execute_args"] = {"code": f"$checked:{ref['id']}"}
    checked["next_action"] = ('실행하려면 execute_args 를 그대로 check 없이 호출하세요 — '
                              '프로그램 원문과 검사한 inputs·budget·edition·value_protocols를 재사용하므로 다시 적지 않습니다. '
                              '바꿀 인자만 명시하면 그 인자 전체를 교체합니다. '
                              '실행 결과의 success·executed와 쓰기 영수증을 확인한 뒤 산출물을 읽으세요.')


#: 이보다 짧은 원문은 다시 적는 편이 싸다 — 손잡이 안내가 원문보다 길어지지 않게.
_REVISION_MIN_CHARS = 300
_REJECTED_CODE_RE = re.compile(r"\s*\$rejected:([0-9a-f]{64})\s*")
_CODE_EDIT_EXAMPLE = [{"old": "<고칠 원문 조각>", "new": "<바꿀 글>"}]


def _offer_code_revision(result, code, request=None) -> None:
    """거절·읽기 후 실패에 원문·입력·읽기 재사용을 묶은 수정 손잡이를 붙인다.

    통과한 검사에는 `$checked` 가 있는데 거절에는 없어서, 7K자 프로그램의 인자 이름 하나를 고치는 데 92초가 들었다
    (ep4338, 전문 재출력). 보낸 원문은 이미 여기 있으므로 증거 저장소에 두고 `code: "$rejected:<id>"` 와
    `code_edits`(정확히 일치하는 조각 치환)로 고친다. `$checked` 와 같은 code 자리의 참조이고 새 문법이 아니다."""
    if not isinstance(result, dict):
        return
    rejected = (result.get("executed") is False and result.get("ok") is False
                and bool(result.get("issues")))
    continuation = result.get("continuation") or {}
    reuse_args = continuation.get("reuse_args") or {}
    # 이미 쓰기를 했거나 결과가 불확실한 실행을 수정 재실행으로 유도하지 않는다.
    reusable_failure = (result.get("executed") is True and result.get("success") is False
                        and continuation.get("state_change_possible") is False
                        and bool(reuse_args.get("reuse"))
                        and result.get("run_status") == "interrupted")
    if not (rejected or reusable_failure):
        return
    if not isinstance(code, str) or not code.strip() or (not reusable_failure and len(code) < _REVISION_MIN_CHARS):
        return
    try:
        from model_result_view import evidence_store
        saved = {key: request[key] for key in _SAVED_REQUEST_KEYS
                 if request is not None and key in request}
        if reusable_failure:
            previous = saved.get("reuse") or {}
            saved["reuse"] = {**previous, **reuse_args["reuse"]}
        ref = evidence_store().evidence(json.dumps(
            {"kind": "rejected_program", "code": code, "request": saved}, ensure_ascii=False))
    except (OSError, ValueError, TypeError):
        return
    if ref.get("masked_paths"):
        return
    result["revise_args"] = {"code": f"$rejected:{ref['id']}", "code_edits": _CODE_EDIT_EXAMPLE}
    result["revise_hint"] = ('고칠 조각만 보내세요: revise_args.code 를 그대로 code 에 넣고 code_edits 에 {old, new} 를 적습니다'
                             '(old 는 원문에 정확히 한 번 나오는 조각, 여러 곳이면 all:true). 입력·예산과 재사용 가능한 읽기를 '
                             '복원하므로 원문 전체나 inputs를 다시 적지 않습니다. check:true는 검사만, '
                             'reuse:null은 새 조회입니다. 명시한 인자는 저장된 인자 전체를 교체합니다.')


def apply_code_edits(source, edits):
    """(고친 원문, 오류문). 조각은 글자 그대로 일치해야 하며 앞 치환의 결과 위에 차례로 적용한다."""
    if not isinstance(edits, list) or not edits or len(edits) > 40:
        return source, "code_edits 는 {old, new} 1~40개의 목록입니다."
    for index, edit in enumerate(edits):
        if (not isinstance(edit, dict) or set(edit) - {"old", "new", "all"} or type(edit.get("old")) is not str
                or not edit["old"] or type(edit.get("new")) is not str or type(edit.get("all", False)) is not bool):
            return source, f"code_edits[{index}] 는 {{old: 비어 있지 않은 글, new: 글, all?: Bool}} 입니다."
        found = source.count(edit["old"])
        if found == 0:
            return source, (f"code_edits[{index}].old 가 원문에 없습니다: {edit['old'][:120]!r}. "
                            "앞 치환이 이미 바꿨는지, 공백·따옴표가 원문과 같은지 확인하세요.")
        if found > 1 and not edit.get("all"):
            return source, (f"code_edits[{index}].old 가 원문에 {found}번 나옵니다: {edit['old'][:120]!r}. "
                            "한 곳만 가리키도록 길게 적거나 all:true 로 전부 바꾸세요.")
        source = source.replace(edit["old"], edit["new"])
    return source, None


def _resolve_checked_code(tool_input):
    """code 자리의 참조(`$checked:<id>` 통과분 · `$rejected:<id>` 거절분+code_edits)를 저장한 원문으로 바꾼다.

    (요청, 오류문) — 참조가 아니면 그대로. 실행 초크포인트와 도구 호출 기록 자리가 같은 함수를 쓴다:
    기록이 손잡이만 담으면 실행한 프로그램을 읽는 소비자(연상 사용 집계·증류·평가)가 원문을 못 본다."""
    code = (tool_input or {}).get("code")
    edits = (tool_input or {}).get("code_edits")
    match = _CHECKED_CODE_RE.fullmatch(code) if isinstance(code, str) else None
    rejected = _REJECTED_CODE_RE.fullmatch(code) if isinstance(code, str) and not match else None
    if not match and not rejected:
        if edits is not None:
            return tool_input, ("code_edits 는 code 가 $checked:… 또는 $rejected:… 참조일 때 그 원문에 적용합니다. "
                                "새 프로그램은 code 에 원문을 적으세요.")
        return tool_input, None
    name, kind = ("$checked", "checked_program") if match else ("$rejected", "rejected_program")
    again = " 프로그램 원문을 code 로 다시 보내세요."
    try:
        from model_result_view import evidence_store
        page = evidence_store().read_evidence_across_turns((match or rejected)[1], 0, None)
        record = json.loads(page["text"])
    except (ValueError, OSError, TypeError, KeyError) as exc:
        return tool_input, f"{name} 참조를 읽을 수 없습니다: {exc}.{again}"
    if (page.get("masked_paths") or not isinstance(record, dict)
            or record.get("kind") != kind or not isinstance(record.get("code"), str)):
        return tool_input, f"{name} 참조가 {'검사를 통과한' if match else '거절된'} 프로그램이 아닙니다.{again}"
    source = record["code"]
    if edits is not None:
        source, problem = apply_code_edits(source, edits)
        if problem:
            return tool_input, problem
    elif rejected:
        return tool_input, "$rejected 참조는 거절된 원문입니다 — code_edits 로 고칠 조각을 함께 보내세요."
    saved = record.get("request", {})
    if not isinstance(saved, dict):
        return tool_input, f"{name} 참조의 저장 인자가 잘못됐습니다.{again}"
    defaults = {k: v for k, v in saved.items() if k in _SAVED_REQUEST_KEYS}
    return {**defaults, **{k: v for k, v in tool_input.items() if k != "code_edits"}, "code": source}, None


def _execute_ibl_unified_impl(tool_input: dict, project_path: str, agent_id: str = None,
                              cancel_check=None) -> str:
    """execute_ibl 통합 실행기 — IBL 코드 기반

    AI가 IBL 코드 문자열을 생성하면, 파서가 해석하고 엔진이 실행한다.
    code 파라미터를 우선 사용하며, 레거시(pipeline, node+action)도 호환 지원.
    """
    from ibl_engine import execute_ibl
    from thread_context import get_allowed_nodes
    from ibl_access import check_node_access, get_denied_message

    # 노드 접근 제어 (allowed_nodes)
    allowed = get_allowed_nodes()
    if tool_input.get("describe") is not None or tool_input.get("read_result") is not None:
        from model_result_view import describe_actions, read_result
        has_code = bool(tool_input.get("code") or tool_input.get("pipeline"))
        if tool_input.get("read_result") is not None and has_code:
            return json.dumps({"success": False, "executed": False,
                               "error": "read_result는 code·pipeline과 함께 사용할 수 없습니다"}, ensure_ascii=False)
        if tool_input.get("read_result") is not None and tool_input.get("describe") is not None:
            # 둘 다 효과 없는 조회다 — 한 번에 받게 한다(ep4211: 함께 보냈다가 거절돼 한 라운드를 잃었다).
            try:
                page = read_result(tool_input["read_result"])
                from ibl_edition import authoring_request
                page["descriptions"] = describe_actions(
                    tool_input["describe"], allowed,
                    edition=authoring_request(tool_input).get("edition"))["actions"]
            except (ValueError, KeyError, TypeError, OSError) as exc:
                return json.dumps({"success": False, "executed": False, "error": str(exc)}, ensure_ascii=False)
            return json.dumps(page, ensure_ascii=False)
        try:
            if tool_input.get("describe") is not None:
                from ibl_edition import authoring_request, source_edition
                described_edition = source_edition(
                    tool_input.get("code") or tool_input.get("pipeline") or "",
                    (tool_input if has_code else authoring_request(tool_input)).get("edition"))
                value = describe_actions(tool_input["describe"], allowed, edition=described_edition,
                                         program=tool_input.get("code") or tool_input.get("pipeline"))
            else:
                value = read_result(tool_input["read_result"])
        except (ValueError, KeyError, TypeError, OSError) as exc:
            return json.dumps({"success": False, "executed": False, "error": str(exc)}, ensure_ascii=False)
        if not has_code:
            return json.dumps(value, ensure_ascii=False)
        descriptions = value["actions"]
        if any(row.get("error") for row in descriptions):
            return json.dumps({"success": False, "executed": False,
                               "error": "요청한 액션 계약을 확인하지 못해 실행하지 않았습니다",
                               "descriptions": descriptions}, ensure_ascii=False)
        # 부가 조회의 실패는 효과 전에 거절한다. 실행은 원래 경로를 딱 한 번
        # 통과하며 value·실패·영수증·check의 의미를 그대로 보존한다.
        request = {k: v for k, v in tool_input.items() if k != "describe"}
        raw = _execute_ibl_unified_impl(request, project_path, agent_id, cancel_check=cancel_check)
        try:
            result = json.loads(raw)
        except (ValueError, TypeError):
            result = raw
        if not isinstance(result, dict):
            result = {"result": raw}  # 기존 저장 문장의 평문도 원형으로 보존한다.
        result["descriptions"] = descriptions
        return json.dumps(result, ensure_ascii=False)

    # --- IBL 코드 결정 ---
    code = tool_input.get("code") or tool_input.get("pipeline")
    # ★상상실행 초안 인계(2026-09-06): code 가 "$초안" 이면 의식이 지은 초안(검증 통과분, 턴 보관)을 그대로 실행 —
    #   실행자가 같은 500자를 다시 치지 않는다(ep2890 의식 초안 524자 vs 첫 호출 497자, 유사도 0.85).
    if isinstance(code, str) and code.strip() in ("$초안", "${초안}", "$draft"):
        from ibl_turn_vars import load_draft as _load_draft
        _d = _load_draft()
        if not _d:
            return json.dumps({"error": "이 턴에 보관된 초안이 없습니다(의식 초안이 기계 검증을 통과했을 때만 "
                                        "$초안 으로 실행됩니다) — 코드를 직접 적으세요."}, ensure_ascii=False)
        code = _d
        tool_input = dict(tool_input, code=_d)
        print("[상상실행] 초안 그대로 실행 ($초안)")

    if not code:
        return json.dumps({
            "error": "code 파라미터가 필요합니다.",
            "usage": {
                "단일": '[sense:search]{query: "AI 뉴스"}',
                "파이프라인": '$r=[sense:search]{query: "AI 뉴스"}; [self:write]{path: "result.json",content:$r,format:"json"}',
                "병렬": '[sense:search]{query: "AI"} & [sense:search]{source: "gnews", query: "tech"}',
                "폴백": '[sense:stock]{op: "quote", ticker: "AAPL"} ?? [sense:search]{query: "AAPL stock"}'
            }
        }, ensure_ascii=False)

    # 원문 형식과 헤더/API 일치는 효과 전에 검사한다.
    from ibl_v2_entry import handle_request as _v2_request
    # inputs 값 자리의 {"$ref": result_ref.id, "path": [...]} — 앞 실행의 저장 결과를 복사 없이 넘긴다(2026-09-26).
    # 증거 저장소는 인지 층에서 풀고, 값과 출처 근거를 실행기에 함께 전달한다.
    _ref_notes = []
    _checked_request = tool_input
    from model_result_view import input_evidence_by_name
    if isinstance(tool_input.get("inputs"), dict):
        try:
            from model_result_view import resolve_input_refs
            _resolved, _ref_notes = resolve_input_refs(tool_input["inputs"])
        except ValueError as exc:
            return json.dumps({"edition": 2, "ok": False, "success": False, "executed": False,
                               "status": "invalid", "error": str(exc)}, ensure_ascii=False)
        if _ref_notes:
            tool_input = dict(tool_input, inputs=_resolved)
    _v2 = _v2_request(dict(tool_input, code=code), project_path, agent_id, cancel_check,
                      input_evidence=input_evidence_by_name(_ref_notes))
    if isinstance(_v2, dict):
        if _ref_notes and isinstance(_v2, dict):
            _v2["inputs_resolved"] = _ref_notes
        from model_result_view import retain_failed_inputs
        retain_failed_inputs(_v2, tool_input.get("inputs"), _ref_notes)
        if tool_input.get("check"):
            _offer_checked_code(_v2, code, _checked_request)
        _shown = _v2 if tool_input.get("check") else _preview_boundary(_v2, tool_input)
        _offer_code_revision(_shown, code, _checked_request)
        return json.dumps(_shown, ensure_ascii=False)


def _collect_honesty_markers(obj) -> dict:
    """봉투 최상위의 정직 표지를 집계로 압축한다 (목록=ibl_honesty.HONESTY_KEYS 한 벌).

    표지가 봉투 최상위에 오는 것은 엔진의 책임이다(workflow_engine 승격 — B24/B27/
    F35/B48 부류의 관문이 지킨다). 여기서 깊은 스캔을 다시 짜면 목록·지형이 두 벌이 된다.
    궤적 data 는 4KB 캡 + 원문 금지 계약이라 값 원문(_caught 전문·errors 행) 대신
    **집계만** 싣는다: 목록=길이, 수량=값, 플래그=1. step 원형은 봉투(스필)가 정본."""
    from ibl_honesty import markers_of
    out = {}
    for k, v in markers_of(obj).items():
        if isinstance(v, bool):
            out[k] = 1
        elif isinstance(v, (int, float)):
            out[k] = v
        elif isinstance(v, (list, tuple)):
            out[k] = len(v)
        else:
            out[k] = 1
    return out


@runtime_work.tracked("ibl-program", bypass=lambda tool_input, *a, **kw:
                      is_observation_request(tool_input))
def _execute_ibl_unified(tool_input: dict, project_path: str, agent_id: str = None,
                         cancel_check=None) -> str:
    """전 IBL 표면의 trajectory choke point.

    실행 본체의 많은 이른 return 을 건드리지 않고 wrapper 한 벌에서 start/end/resume 을
    남긴다. 궤적에는 코드·결과 원문 대신 안정 해시·길이·액션 이름만 싣고, 코드 원문은
    같은 해시를 키로 ibl_code_corpus(episode_logger.record_ibl_code)에 누적한다(2026-09-06).
    """
    from episode_logger import trajectory_scope, record_trajectory_event, record_ibl_code

    # 검사 통과분 참조는 초크포인트에서 원문으로 바꾼다 — 궤적·코퍼스·관문이 모두 실제 프로그램을 본다.
    tool_input, _checked_error = _resolve_checked_code(tool_input)
    if _checked_error:
        return json.dumps({"success": False, "executed": False, "error": _checked_error}, ensure_ascii=False)
    code = str((tool_input or {}).get("code") or (tool_input or {}).get("pipeline") or "")
    from ibl_scanner import source_heads
    actions = [f"{n}:{a}" for n, a in source_heads(code)]
    # 조합 모양의 **관측**(판정 아님) — 여기가 전 IBL 표면의 유일한 초크포인트라
    # 편향 없는 모집단이다. 조합률 지표(scripts/vocab_composition_metrics.py)는
    # 그동안 해마 코퍼스의 `distilled` 행만 볼 수 있었는데, 그건 '새로운 실행'만
    # 남는 자리라 조합률이 구조적으로 과대추정된다(그 스크립트의 편향 고지 참조).
    # 옛 예정석(ibl_usage.db.ibl_execution_logs)은 2026-07-03 이래 호출자 0·0행으로
    # 죽어 있었고 2026-08-31 에 제거했다 — 조합 모양은 여기로, 원문은 ibl_code_corpus 로(아래).
    # ★원시값만 적고 "조합인가"의 판정은 지표 쪽이 소유한다(판정을 두 벌 두지 않는다).
    _pipes = code.count(">>")
    _nested = bool(re.search(r"\bdo\s*:\s*[\"'\[]", code))
    resume = (tool_input or {}).get("resume")
    called = False
    result = None
    try:
        with trajectory_scope() as _tr:
            start = time.monotonic()
            # ★무주 run 의 귀속 (2026-09-06). 봉투에 episode_id 가 안 실린 실행은 여기서
            #   run 만 서고 episode_log 에는 행이 없다 — 궤적은 남는데 **주인이 없다**.
            #   실측: 시험·외부 세션이 라이브 백엔드에 쏜 IBL 이 agent 라벨만 남기고 돌아,
            #   사용자가 "내가 안 시켰는데 뭐가 돌고 있냐"고 물었을 때 원장으로 답할 수
            #   없었다. 관측을 늘리는 게 아니라 **귀속을 복구**하는 것이다 — 누가(origin)
            #   어느 작업으로(task_id) 쐈는지를 사건 자체에 적어 둔다.
            _unowned = getattr(_tr, "episode_id", None) is None
            _origin = ""
            if _unowned:
                try:
                    from thread_context import get_task_origin
                    _origin = get_task_origin() or ""
                except Exception:
                    _origin = ""
            from ibl_edition import source_edition, program_hash
            try:
                edition = source_edition(code, tool_input.get("edition"))
            except ValueError:
                edition = None
            record_trajectory_event("ibl.started", {
                "code_sha256": (program_hash(code, edition) if edition is not None
                                else hashlib.sha256(code.encode("utf-8")).hexdigest()),
                "code_chars": len(code),
                "edition": edition,
                # 조회 종류를 원문·티켓 없이 보존한다. 빈 코드 해시만으로는
                # 계약 조회·결과 열람·잘못된 빈 호출을 구별할 수 없다.
                "request_keys": [k for k in ("describe", "read_result", "recover")
                                 if tool_input.get(k) is not None],
                "actions": actions[:100],
                "action_count": len(actions),
                "fn_count": sum(a.startswith("fn:") for a in actions),
                "pipes": _pipes,
                "nested": _nested,
                "agent": agent_id or "",
                "unowned": _unowned,
                "origin": _origin,
                "task_id": getattr(_tr, "task_id", "") or "",
            })
            if isinstance(resume, dict):
                ref = resume.get("prev_ref")
                ref_path = ref if isinstance(ref, str) else (
                    ref.get("path") if isinstance(ref, dict) else "")
                record_trajectory_event("ibl.resumed", {
                    "from_step": resume.get("from_step"),
                    "prev_ref_sha256": hashlib.sha256(str(ref_path).encode(
                        "utf-8", "replace")).hexdigest() if ref_path else "",
                })
            called = True
            result = _execute_ibl_unified_impl(
                tool_input, project_path, agent_id, cancel_check=cancel_check)
            obj = result if isinstance(result, dict) else None
            if obj is None and isinstance(result, str):
                try:
                    obj = json.loads(result)
                except Exception:
                    obj = None
            failed = bool(isinstance(obj, dict) and (
                obj.get("success") is False or ("error" in obj and not obj.get("success"))))
            raw = result if isinstance(result, str) else json.dumps(
                result, ensure_ascii=False, sort_keys=True, default=str)
            _finished = {
                "success": not failed,
                "elapsed_ms": int((time.monotonic() - start) * 1000),
                "result_sha256": hashlib.sha256(raw.encode(
                    "utf-8", "replace")).hexdigest(),
                "result_chars": len(raw),
                "resumed_from": obj.get("resumed_from") if isinstance(obj, dict) else None,
            }
            # 정직 표지 집계 — `??` 갈아탐·행별 부분 실패가 success:true 한 줄로
            # 뭉개지지 않게 한다. 빈 집계는 싣지 않는다(평시 봉투 무변).
            _markers = _collect_honesty_markers(obj) if isinstance(obj, dict) else {}
            if _markers:
                _finished["markers"] = _markers
            record_trajectory_event("ibl.finished", _finished)
            # 원문 코퍼스 — 궤적은 해시만 싣는 계약이라 원문은 여기(같은 해시로 조인).
            # 2026-09-06 부활. 실패 사유는 봉투의 error 한 줄(캡·마스킹은 기록기 몫).
            if edition is not None and not tool_input.get("check"):
                record_ibl_code(
                    code, success=not failed, elapsed_ms=_finished["elapsed_ms"],
                    error=(obj.get("error") if failed and isinstance(obj, dict) else ""),
                    agent=agent_id or "", edition=edition,
                    origin=str((tool_input or {}).get("origin") or ""))
            return result
    except Exception as e:
        # trajectory 는 관측이다. 계측 실패가 IBL 실행을 막지 않는다.
        # ★본체가 이미 시작됐으면 절대 재실행하지 않는다 — 쓰기/메시지 부작용 중복 방지.
        if called:
            if result is not None:
                return result
            return json.dumps({"error": f"IBL 실행 오류: {str(e)}"}, ensure_ascii=False)
        return _execute_ibl_unified_impl(tool_input, project_path, agent_id,
                                         cancel_check=cancel_check)
