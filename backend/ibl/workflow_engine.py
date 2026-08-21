"""
workflow_engine.py - IBL 파이프라인 실행 & 워크플로우 관리

IBL Phase 5의 핵심.
여러 IBL 액션을 순차 연결하고, YAML로 저장/로드하여 반복 실행합니다.

사용법:
    from workflow_engine import execute_pipeline, execute_workflow, list_workflows

    # 파이프라인 직접 실행
    steps = [
        {"_node": "fs", "action": "exec_python", "target": "print(42)"},
        {"_node": "system", "action": "notify", "target": "결과: {{_prev_result}}"},
    ]
    result = execute_pipeline(steps, ".")

    # 저장된 워크플로우 실행
    result = execute_workflow("daily_news", ".")
"""

import os
import re
import json
import time
import yaml
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


# === 경로 ===

def _get_workflows_path() -> Path:
    """워크플로우 저장 디렉토리"""
    env_path = os.environ.get("INDIEBIZ_BASE_PATH")
    if env_path:
        base = Path(env_path)
    else:
        base = Path(__file__).parent.parent.parent
    wf_path = base / "data" / "workflows"
    wf_path.mkdir(parents=True, exist_ok=True)
    return wf_path


# === 실패 판정 (단일 소스) ===

def _is_error_result(result) -> bool:
    """도구 결과가 실패인지 판정한다 — `>>`·`??` 공용 **단일 소스**.

    도구가 실패를 알리는 방식이 **네 갈래**라 판정이 곳곳에 복제됐다가 갈라졌었다
    (2026-07-18: `??` 만 문자열 에러를 성공으로 세어, NameError 를 고친 뒤에도 폴백이 안 됨).
    새 소비자는 이 함수를 부를 것 — 판정을 다시 손으로 적지 말 것.

    실패로 치는 것:
      1. dict: `success is False`, 또는 최상위 `error` 키가 있고 success 가 참이 아님
      2. str `"Error:"` 접두 — system_essentials 계열(self:read/delete/copy)
      3. **JSON 문자열** — handler 라우터는 `format_json(...)` 으로 *문자열*을 돌려주므로
         `{"success": false, "message": …}` 가 문자열에 실려 온다. 파싱해서 1번 규칙 적용.
         ★이걸 안 보면 handler 도구의 실패가 전부 성공으로 샌다(2026-07-18 블로그 파이프에서
         실측: `[self:blog]` 가 실패했는데 파이프가 success=True 로 보고).
      4. 예외 — 호출부가 잡아서 별도 처리(이 함수 밖).

    실패로 치지 않는 것:
      - `status == "not_implemented"` — 미구현은 고장이 아님
      - `{"success": true, "error": null}` — 성공인데 error 키가 있는 모양
        (서킷 브레이커가 `verify.error: null` 로 성공을 실패로 오인했던 전례를 판정에 반영)

    ★한계: `"Error:"` 접두 판정은 **휴리스틱**이다. 본문이 그렇게 시작하는 정당한 콘텐츠
    (로그 요약·코드 스니펫)를 실패로 오인할 수 있다. 도구 반환 규약을 통화로 수렴시키기 전까지의
    잠정 규칙이며, **최상위 result 에만** 적용한다(중첩 dict 의 error 키는 보지 않는다).
    """
    if isinstance(result, dict):
        if result.get("status") == "not_implemented":
            return False
        if result.get("success") is False:
            return True
        return ("error" in result) and not result.get("success")
    if isinstance(result, str):
        s = result.lstrip()
        if s.startswith("Error:"):
            return True
        # handler 라우터의 JSON 문자열 — 최상위만 파싱해 dict 규칙 재사용
        if s.startswith("{"):
            try:
                import json as _json
                parsed = _json.loads(s)
            except Exception:
                return False
            if isinstance(parsed, dict):
                return _is_error_result(parsed)
        return False
    return False


def _is_empty_result(result) -> bool:
    """도구 결과가 **빈손**인지 판정한다 — `??` 전용 보조 술어 (2026-08-08, 실험 7 ⑯).

    두 연산자의 술어는 원래 다르다:
      - `>>` 순차: "앞이 죽었으면 멈춰라" → 고장(_is_error_result)만. 0건은 죽음이
        아니고, 0건 위의 take/filter 가 0건을 내는 것이 정답이다.
      - `??` 폴백: "원하는 걸 못 얻었으면 딴 데로" → **빈손도 못 얻은 것**.
        폴백을 거는 대상은 대개 검색이고 목록형 검색의 흔한 실패 모드가 0건이라,
        고장 판정만으로는 발동해야 할 자리의 다수를 통과시킨다(실측: [sense:used]
        total:0 이 status ok 로 기록되고 뒤의 웹 검색이 손도 안 대진 채 남았다).
    2026-07-18 의 판정 통일(_is_error_result 단일 소스)은 유지 — 이 술어는 or 로만 얹는다.

    빈손 판정은 **구조 신호만** (산문 휴리스틱 없음):
      - dict(또는 JSON 문자열)의 items == [] (빈 리스트)
      - total == 0 / count == 0 (명시된 0 — 키 부재는 판정 밖)
      - 표 통화의 rows == [] (columns 가 함께 있을 때만 — 우연한 rows 키 오판 방지)
    """
    if isinstance(result, str):
        s = result.lstrip()
        if not s.startswith("{"):
            return False
        try:
            import json as _json
            result = _json.loads(s)
        except Exception:
            return False
    if not isinstance(result, dict):
        return False
    items = result.get("items")
    if isinstance(items, list) and not items:
        return True
    for k in ("total", "count"):
        v = result.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v == 0:
            return True
    t = result.get("table")
    holder = t if isinstance(t, dict) else result
    rows = holder.get("rows")
    if isinstance(rows, list) and not rows and isinstance(holder.get("columns"), list):
        return True
    return False


# === 파이프라인 실행 ===

def _first_step_project_id(steps: list):
    """파이프의 어느 leaf 가 명시한 project_id 를 앞 순서로 찾는다(없으면 None).

    순차 step + 병렬 branches + fallback 체인을 재귀로 본다. 합성 코드에서 project_id 는
    그것을 적은 leaf 의 params 에만 산다 — head 가 정의한 프로젝트 컨텍스트를 집어낸다.
    """
    for s in steps:
        if not isinstance(s, dict):
            continue
        if isinstance(s.get("branches"), list):
            r = _first_step_project_id(s["branches"])
            if r:
                return r
            continue
        if isinstance(s.get("_fallback_chain"), list):
            r = _first_step_project_id(s["_fallback_chain"])
            if r:
                return r
            continue
        p = s.get("params")
        if isinstance(p, dict):
            pid = p.get("project_id")
            if isinstance(pid, str) and pid.strip():
                return pid.strip()
    return None


def _propagate_project_id(steps: list, pid: str):
    """pid 를 project_id 미지정 leaf 의 params 에 setdefault (순차/병렬/fallback 재귀).

    leaf 자신이 명시한 project_id 는 보존한다 — [A]{project_id:X} >> [B]{project_id:Y} 같은
    교차 프로젝트 파이프가 깨지지 않게. workspace 스코프 leaf 는 project_id 를 무시하므로 무해.
    """
    for s in steps:
        if not isinstance(s, dict):
            continue
        if isinstance(s.get("branches"), list):
            _propagate_project_id(s["branches"], pid)
            continue
        if isinstance(s.get("_fallback_chain"), list):
            _propagate_project_id(s["_fallback_chain"], pid)
            continue
        p = s.get("params")
        if not isinstance(p, dict):
            p = {}
            s["params"] = p
        existing = p.get("project_id")
        if not (isinstance(existing, str) and existing.strip()):
            p["project_id"] = pid


def execute_pipeline(steps: list, project_path: str = ".",
                     context: dict = None, agent_id: str = None) -> dict:
    """
    파이프라인 실행 - 여러 IBL 액션을 순차 연결

    Args:
        steps: IBL step 리스트. 각 step은 dict:
            {_node, action, target, params} 또는
            {node, action, target, params} (YAML에서 로드 시)
        project_path: 프로젝트 경로
        context: 초기 컨텍스트 (첫 step의 _prev_result로 사용)
        agent_id: 실행 주체 에이전트 ID (schedule, execute_plan 등에서 사용)

    Returns:
        {
            "success": bool,
            "steps_completed": int,
            "steps_total": int,
            "results": [{step, result, duration_ms}...],
            "final_result": Any,
            "error": str (실패 시)
        }
    """
    from ibl_engine import execute_ibl

    # ★B1 (2026-08-16 상상훈련): steps 가 IBL 코드 *문자열 하나*로 오면 그대로 두면 안 된다 —
    # str 도 iterable 이라 아래 any(isinstance(s, str)) 관문을 "글자들의 리스트"로 통과해
    # 한 글자씩 파싱을 시도한다(steps_total=글자 수, 'IBL 문법 오류: ['). do/steps 별칭이
    # 저장 원문(문자열)을 그대로 나르므로(target_description 도 문자열을 명시 허용), 관문이
    # 아니라 계약 입구에서 감싼다 — run/run_pipeline/execute_workflow/트리거 전 호출처 공통.
    if isinstance(steps, str):
        steps = [steps] if steps.strip() else []

    if not steps:
        return {"success": False, "error": "steps가 비어있습니다.", "steps_completed": 0, "steps_total": 0}

    # steps 정규화 — 원소가 IBL 코드 *문자열*이면 dict step 으로 파싱한다.
    # 이 함수는 아래에서 step.get(...) 로 dict 를 가정하지만, run_pipeline 액션 문서·해마 용례·
    # 자가점검·트리거가 모두 steps 를 IBL 코드 문자열 리스트로 넘겨 'str' object has no attribute
    # 'get' 으로 만성 실패해 왔다. 계약을 정의하는 입구에서 한 번 정규화해 모든 호출처
    # (run_pipeline·calendar·channel_poller·plans)를 함께 고친다.
    # 문자열이 '>>'/'&'/'??' 합성을 품으면 ibl_parse 가 여러 step 으로 펼친다.
    if any(isinstance(s, str) for s in steps):
        from ibl_parser import parse as ibl_parse, IBLSyntaxError
        normalized = []
        for s in steps:
            if isinstance(s, str):
                if not s.strip():
                    continue
                try:
                    normalized.extend(ibl_parse(s))
                except IBLSyntaxError as e:
                    return {"success": False, "error": f"IBL 문법 오류: {s} → {str(e)}",
                            "steps_completed": 0, "steps_total": len(steps)}
            else:
                normalized.append(s)
        steps = normalized
        if not steps:
            return {"success": False, "error": "steps가 비어있습니다.", "steps_completed": 0, "steps_total": 0}

    # project_id 파이프 전파 — 합성 코드(>>/&/??)의 project_id 는 그것을 적은 leaf 의 params 에만
    # 살아서, 뒤따르는 step 이 그대로면 "활성 프로젝트 경로 확보 불가"로 게이트에서 죽는다
    # (예: [self:read]{project_id:X} >> [table:document] — document 가 X 를 모름).
    # 호출자가 구체 project_path 를 *안* 줬을 때(시스템 AI·스케줄러 등 — top-level project_id 는
    # api_ibl 에서 이미 경로로 해소됨)에 한해, head leaf 의 project_id 를 미지정 후속 leaf 에 전파한다.
    # 무회귀: project_path 가 구체적이면(프로젝트 에이전트) 건드리지 않고, 어느 leaf 도 project_id 를
    # 안 적었으면(전부 미지정) 아무 일도 안 한다 — 기존 thread_context 폴백 그대로.
    if (not project_path) or str(project_path).strip() in ("", "."):
        _head_pid = _first_step_project_id(steps)
        if _head_pid:
            _propagate_project_id(steps, _head_pid)

    prev_result = context.get("_prev_result", "") if context else ""
    results = []
    total = len(steps)
    action_count = 0  # 실제 실행된 액션 수 (병렬 branches 포함)
    # $var 바인딩 저장소: step 인덱스 → 결과 문자열. 파서가 $var 를 {{_step_N_result}} 로
    # 치환해 두므로, 여기 저장된 값으로 실행 시점에 실제 결과가 주입된다 (문장 경계와 무관).
    step_results: Dict[int, str] = {}

    # ── 문장 경계(`;` · 개행) ──────────────────────────────────────────────
    # 여러 문장이 한 리스트로 평탄화돼 들어오므로, 파서가 각 문장 첫 step 에 `_seq_boundary` 를
    # 붙여 둔다. `>>` 는 "성공했을 때만 다음"이지만 문장 경계는 "되든 안 되든 다음"이다.
    # 실패해도 다음 문장으로 건너뛰어 계속 실행하고, _prev_result 는 경계를 넘기지 않는다(독립).
    # ★정직: 건너뛰었다고 실패를 숨기지 않는다 — 실패한 문장이 하나라도 있으면 success=False 이고
    #   results 에 그 실패가 그대로 남는다(스케줄러가 조용히 성공으로 착각하지 않게).
    def _next_boundary(from_idx: int) -> int:
        for j in range(from_idx, total):
            if isinstance(steps[j], dict) and steps[j].get("_seq_boundary"):
                return j
        return -1

    _seq = {"skip_until": -1, "failed": 0, "last_mode": None, "skipped": []}

    def _handle_failure(idx: int, abort_payload: dict):
        """실패 처리. ①그 step 의 문장이 [on_error: skip|null] 이면 건너뛰고 계속(신고 동반),
        ②뒤에 독립 문장이 있으면 거기로 건너뛰고 계속(None 반환),
        ③없으면 중단 payload — 2단 이상 진행했으면 재개 지점(resume)을 스필해 싣는다(M5 §2.6)."""
        st = steps[idx] if isinstance(steps[idx], dict) else {}
        mode = st.get("_on_error")
        if mode in ("skip", "null"):
            _seq["last_mode"] = mode
            _seq["skipped"].append(idx + 1)
            if results and isinstance(results[-1], dict) and results[-1].get("step") == idx + 1:
                results[-1]["skipped"] = mode
            return None
        _seq["last_mode"] = None
        b = _next_boundary(idx + 1)
        if b < 0:
            if idx >= 1 and prev_result and not st.get("_seq_boundary"):
                try:
                    from common.spill import spill_write
                    ref = spill_write(prev_result, tag=f"resume_step{idx + 1}")["ref"]
                    abort_payload["resume"] = {
                        "from_step": idx + 1, "prev_ref": ref,
                        "note": (f"step {idx + 1} 부터 다시 돌리려면 execute_ibl(code, resume={{from_step: {idx + 1}, "
                                 f"prev_ref: \"{ref['path']}\"}}) — 1~{idx} 단은 재실행하지 않습니다(스필 24h 유효)."),
                    }
                except Exception:
                    pass
            return abort_payload
        _seq["skip_until"] = b
        _seq["failed"] += 1
        return None

    def _after_failure(prev: str) -> str:
        """실패 뒤 다음 step 에 넘길 통화 — skip=직전 통화 그대로, null=빈 items, 그 외=끊김."""
        m = _seq["last_mode"]
        if m == "skip":
            return prev
        if m == "null":
            return '{"items": []}'
        return ""

    def _spill_if_large(prev: str, idx: int) -> str:
        """자동 스필(M5 §2.5-3): 이음매 통화가 임계를 넘으면 파일로 내리고 참조만 흘린다 — 신고 동반."""
        try:
            from common.spill import AUTO_SPILL_THRESHOLD, spill_write
            if idx < total - 1 and isinstance(prev, str) and len(prev) > AUTO_SPILL_THRESHOLD:
                env = spill_write(prev, tag=f"step{idx + 1}")
                if results and isinstance(results[-1], dict):
                    results[-1]["spilled"] = env["ref"]
                    results[-1]["note"] = (f"통화 {len(prev):,}자 > 임계 {AUTO_SPILL_THRESHOLD:,} — 스필 파일로 내리고 "
                                           "참조만 다음 step 에 넘겼습니다(변환자·each·$items·write 는 투명하게 읽음)")
                return json.dumps(env, ensure_ascii=False)
        except Exception:
            pass
        return prev

    for i, step in enumerate(steps):
        if i < _seq["skip_until"]:
            continue  # 실패한 문장의 남은 step — 건너뛴다(다음 문장 경계까지)
        if isinstance(step, dict) and step.get("_seq_boundary"):
            # 문장 경계 — 앞 문장이 성공했어도 결과를 넘기지 않는다(독립).
            # 실패 경로는 각 _handle_failure 뒤에서 리셋하지만, 성공 경로는 여기가 유일한 관문
            # (없으면 _auto_inject_prev 가 앞 문장 결과를 다음 문장 첫 step 에 무조건 주입한다).
            prev_result = ""
        # $var 바인딩 치환 — {{_step_N_result[.path]}} 를 저장된 step 결과로 (branches/체인 포함).
        # 문장 경계의 prev_result 리셋과 독립이라, 앞 문장 결과를 명시 참조로 가져올 수 있다.
        # 필드 경로(.path) 추출 실패는 정직한 step 실패로 — 침묵 "" 치환 금지 (G1, 2026-08-16).
        if step_results and isinstance(step, dict):
            try:
                step = _inject_step_results(step, step_results)
                # 블록 조건식의 $변수 = 값 바인딩 (2026-08-22 M2): 파서가 적어 둔 _vars
                # {이름: step 인덱스} 를 실제 결과로 — 텍스트 치환이 아니라 봉투로 싣는다.
                if step.get("_vars"):
                    step = dict(step)
                    # 바깥(스탬프)보다 이 파이프의 최신 결과가 우선 (M6: 안쪽 재할당)
                    step["_var_values"] = {**(step.get("_var_values") or {}),
                                           **{n: step_results.get(int(i), "") for n, i in step["_vars"].items()}}
            except ValueError as e:
                results.append({
                    "step": i + 1,
                    "node": _step_label(step)[0],
                    "action": step.get("action", "?"),
                    "error": str(e),
                    "duration_ms": 0,
                })
                _abort = _handle_failure(i, {
                    "success": False, "steps_completed": i, "steps_total": total,
                    "results": results, "final_result": None,
                    "error": f"Step {i+1} 변수 치환 실패: {str(e)}",
                })
                if _abort is not None:
                    return _abort
                prev_result = _after_failure(prev_result)
                continue
        step_start = time.time()

        # Phase 9: 특수 노드 처리 (병렬, fallback)
        if step.get("_parallel"):
            # 병렬 실행
            try:
                result = _execute_parallel(step["branches"], project_path, prev_result, raw=(i < total - 1))
            except Exception as e:
                results.append({
                    "step": i + 1, "type": "parallel",
                    "error": str(e),
                    "duration_ms": int((time.time() - step_start) * 1000),
                })
                _abort = _handle_failure(i, {
                    "success": False, "steps_completed": i, "steps_total": total,
                    "results": results, "final_result": None,
                    "error": f"Step {i+1} 병렬 실행 예외: {str(e)}",
                })
                if _abort is not None:
                    return _abort
                prev_result = _after_failure(prev_result)
                continue

            duration_ms = int((time.time() - step_start) * 1000)
            result_str = _to_string(result)

            # 괄호 분기 파이프는 속 step 수만큼 (G13-1)
            action_count += sum(
                (len(b.get("_branch_steps") or ()) or 1) if isinstance(b, dict) else 1
                for b in step["branches"])
            results.append({
                "step": i + 1, "type": "parallel",
                "branches": len(step["branches"]),
                "result": result_str,
                "duration_ms": duration_ms,
            })
            step_results[i] = result_str
            prev_result = _spill_if_large(_to_prev_currency(result), i)  # 파이프 이음매 통화 파생(D13) — results[]는 원형 · 임계 초과=자동 스필(M5)

            continue

        if "_fallback_chain" in step:
            # Fallback 실행
            try:
                result, fallback_log = _execute_fallback(step["_fallback_chain"], project_path,
                                                         prev_result, agent_id=agent_id)
            except Exception as e:
                results.append({
                    "step": i + 1, "type": "fallback",
                    "error": str(e),
                    "duration_ms": int((time.time() - step_start) * 1000),
                })
                _abort = _handle_failure(i, {
                    "success": False, "steps_completed": i, "steps_total": total,
                    "results": results, "final_result": None,
                    "error": f"Step {i+1} fallback 실행 예외: {str(e)}",
                })
                if _abort is not None:
                    return _abort
                prev_result = _after_failure(prev_result)
                continue

            duration_ms = int((time.time() - step_start) * 1000)
            result_str = _to_string(result)

            # fallback 결과에 에러가 있으면 (모든 체인 실패 — `_all_failed` 는 _execute_fallback 이 붙인다)
            is_err = isinstance(result, dict) and result.get("_all_failed") and _is_error_result(result)
            action_count += 1
            results.append({
                "step": i + 1, "type": "fallback",
                "chain_length": len(step["_fallback_chain"]),
                "attempts": fallback_log,
                "result": result_str,
                "duration_ms": duration_ms,
            })
            step_results[i] = result_str

            if is_err:
                _abort = _handle_failure(i, {
                    "success": False, "steps_completed": i, "steps_total": total,
                    "results": results, "final_result": result,
                    "error": f"Step {i+1} fallback 체인 전체 실패",
                })
                if _abort is not None:
                    return _abort
                prev_result = _after_failure(prev_result)
                continue

            prev_result = _spill_if_large(_to_prev_currency(result), i)  # 파이프 이음매 통화 파생(D13) — results[]는 원형 · 임계 초과=자동 스필(M5)
            continue

        # 일반 step (기존 로직)
        tool_input = dict(step)
        if "node" in tool_input and "_node" not in tool_input:
            tool_input["_node"] = tool_input.pop("node")

        # {{_prev_result}} 템플릿 치환
        tool_input = _inject_prev_result(tool_input, prev_result)

        # ★$items 집합 바인딩 (G1-③) — 값 바인딩, 텍스트 치환 아님. 실패는 정직한 step 실패.
        tool_input, _bind_err = _bind_items_params(tool_input, prev_result)
        if _bind_err:
            results.append({
                "step": i + 1,
                "node": _step_label(tool_input)[0],
                "action": _step_label(tool_input)[1],
                "error": _bind_err,
                "duration_ms": 0,
            })
            _abort = _handle_failure(i, {
                "success": False, "steps_completed": i, "steps_total": total,
                "results": results, "final_result": None,
                "error": f"Step {i+1} {_bind_err}",
            })
            if _abort is not None:
                return _abort
            prev_result = _after_failure(prev_result)
            continue

        # 파이프라인 자동 데이터 전달 (명시적 참조 없으면 params에 주입)
        tool_input = _auto_inject_prev(tool_input, prev_result)

        # >> 파이프 중간 단계는 raw로 실행 — postprocess:compress가 구조화 통화(records/table)를
        # 죽이지 않게. 압축은 에이전트가 보는 *최종* 출력에만(마지막 step). 중간은 다음 step이 소비하는
        # 기계용이라 구조 보존이 맞다. (앱·GUI가 쓰던 _raw 메커니즘 재사용)
        if i < total - 1:
            _p = tool_input.get("params")
            if not isinstance(_p, dict):
                _p = {}
                tool_input["params"] = _p
            _p["_raw"] = True

        # IBL 실행
        try:
            result = execute_ibl(tool_input, project_path, agent_id=agent_id)
        except Exception as e:
            results.append({
                "step": i + 1,
                "node": _step_label(tool_input)[0],
                "action": _step_label(tool_input)[1],
                "error": str(e),
                "duration_ms": int((time.time() - step_start) * 1000),
            })
            _abort = _handle_failure(i, {
                "success": False,
                "steps_completed": i,
                "steps_total": total,
                "results": results,
                "final_result": None,
                "error": f"Step {i+1} 실행 중 예외: {str(e)}",
            })
            if _abort is not None:
                return _abort
            prev_result = _after_failure(prev_result)
            continue

        duration_ms = int((time.time() - step_start) * 1000)

        # 결과를 문자열로 변환 (다음 step 주입용)
        result_str = _to_string(result)

        # 에러 확인 (단일 소스)
        is_err = _is_error_result(result)

        action_count += 1
        results.append({
            "step": i + 1,
            "node": _step_label(tool_input)[0],
            "action": _step_label(tool_input)[1],
            "result": result_str,
            "duration_ms": duration_ms,
        })
        step_results[i] = result_str
        # 블록 몸이 재할당한 바깥 변수(M6 repeat) — 루프 뒤 `$n` 이 최신값이 되게 되쓴다
        if isinstance(result, dict) and isinstance(result.get("_var_updates"), dict) and step.get("_vars"):
            for _n, _raw in result["_var_updates"].items():
                _ix = step["_vars"].get(_n)
                if _ix is not None:
                    step_results[int(_ix)] = _raw if isinstance(_raw, str) else json.dumps(_raw, ensure_ascii=False)

        if is_err:
            err_msg = result.get("error", "") if isinstance(result, dict) else str(result)
            _abort = _handle_failure(i, {
                "success": False,
                "steps_completed": i,
                "steps_total": total,
                "results": results,
                "final_result": result,
                "error": f"Step {i+1} 에러: {err_msg}",
            })
            if _abort is not None:
                return _abort
            prev_result = _after_failure(prev_result)
            continue

        # 다음 step으로 전달
        prev_result = _spill_if_large(_to_prev_currency(result), i)  # 파이프 이음매 통화 파생(D13) — results[]는 원형 · 임계 초과=자동 스필(M5)

    # 문장 경계를 넘어 계속 실행했더라도 실패는 숨기지 않는다 — 실패한 문장이 있으면 success=False.
    # (건너뛰기는 "계속 실행"이지 "없던 일"이 아니다. 스케줄러·평가자가 조용히 성공으로 읽으면 안 된다.)
    _failed = _seq["failed"]
    out = {
        "success": _failed == 0,
        "steps_completed": total,
        "steps_total": total,
        "_action_count": action_count,
        "results": results,
        "final_result": prev_result,
    }
    if _failed:
        out["statements_failed"] = _failed
        out["error"] = f"독립 문장 {_failed}개 실패(나머지는 계속 실행됨)"
    if _seq["skipped"]:
        out["skipped_steps"] = list(_seq["skipped"])
        out["warning"] = (f"[on_error] 로 step {', '.join(map(str, _seq['skipped']))} 실패를 건너뛰었습니다 — "
                          "결과는 부분입니다(results[] 의 skipped 표지·error 참조).")
    return out


# 병렬 실행 브랜치별 타임아웃 (초)
# 병렬(&) 분기 실행기는 형제 모듈로 분리 (2026-08-19, 1500줄 규칙 — G13-1 괄호 분기
# 파이프 추가로 초과). 재수출로 기존 import 경로 불변.
from workflow_parallel import PARALLEL_BRANCH_TIMEOUT, _execute_parallel  # noqa: F401


# 폴백(??) 실행기는 형제 모듈 workflow_fallback.py 로 분리 (2026-08-22, 1500줄 규칙 — M3 괄호 가지 추가로 초과).
from workflow_fallback import _execute_fallback  # noqa: E402,F401


# $var 바인딩 참조 패턴 — 파서(_resolve_variables)가 $var 를 {{_step_N_result}} 로,
# $var.field.path 를 {{_step_N_result.field.path}} 로 치환한다 (G1, 2026-08-16).
_STEP_RESULT_RE = re.compile(r"\{\{_step_(\d+)_result((?:\.\w+)*)\}\}")


def _extract_result_field(raw: str, path: str) -> str:
    """저장된 step 결과 문자열에서 .field.path 를 추출해 스칼라 문자열로.

    실패는 조용한 빈 문자열이 아니라 ValueError — 없는 필드가 침묵히 "" 로 치환되면
    하류가 빈 param 으로 "성공"하는 침묵 실패 부류가 된다(P 시리즈 원칙)."""
    obj: Any = raw
    if isinstance(obj, str):
        s = obj.strip()
        if s.startswith("{") or s.startswith("["):
            try:
                obj = json.loads(s)
            except (json.JSONDecodeError, ValueError):
                raise ValueError(
                    f"$변수 필드 추출 실패: 결과가 JSON 이 아니라 '{path}' 경로를 풀 수 없습니다.")
        else:
            raise ValueError(
                f"$변수 필드 추출 실패: 결과가 구조화 데이터가 아니라 '{path}' 경로를 풀 수 없습니다.")
    for key in path.lstrip(".").split("."):
        if isinstance(obj, dict) and key in obj:
            obj = obj[key]
        elif isinstance(obj, list) and key.isdigit() and int(key) < len(obj):
            obj = obj[int(key)]
        else:
            avail = list(obj.keys())[:12] if isinstance(obj, dict) else f"목록(길이 {len(obj)})" if isinstance(obj, list) else type(obj).__name__
            raise ValueError(
                f"$변수 필드 추출 실패: '{key}' 필드가 없습니다 (경로 {path}, 사용 가능: {avail}).")
    if isinstance(obj, (dict, list)):
        return json.dumps(obj, ensure_ascii=False)
    return "" if obj is None else str(obj)


def _v4_var_payload(raw: str) -> str:
    """bare `$var` 치환의 기본값 — v4 추출 계약 합류 (2026-08-20 상상훈련 17회차 F17-3 판정).

    옛 동작: 결과 봉투 JSON 전체를 문자열화 → write content 에 success 같은 배관 키까지
    박혔다(파이프 싱크의 v4 추출과 비대칭). 새 규약: message(산문 정본)/items(통화) 우선,
    폴백=봉투 원형. 명시 경로($var.field.path)는 불변 — 정밀 추출은 경로가 정본.
    규칙은 write v4(system_essentials)와 같은 게이트를 쓴다: 오분류는 항상 안전 방향
    (봉투=구조 보존)으로 떨어진다."""
    s = (raw or "").strip()
    if not s.startswith("{"):
        return raw
    try:
        obj = json.loads(s)
    except Exception:
        return raw
    if not isinstance(obj, dict):
        return raw
    msg = obj.get("message")
    has_msg = isinstance(msg, str) and bool(msg.strip())
    items = obj.get("items")
    items_nonempty = isinstance(items, list) and bool(items)
    other_payload = any(isinstance(v, (dict, list)) and v
                        for k, v in obj.items() if k not in ("items", "message"))
    if has_msg and not other_payload:
        doc_shaped = ("\n" in msg.strip()) or (len(msg) >= 200)
        if doc_shaped or not items_nonempty:
            return msg
    if items_nonempty and not other_payload:
        return json.dumps(items, ensure_ascii=False)
    return raw


def _inject_step_results(obj: Any, step_results: Dict[int, str]) -> Any:
    """{{_step_N_result[.path]}} 참조를 저장된 step 별 결과로 치환 (재귀 — branches/체인 포함).

    변수 바인딩($var)의 실제 구현(D4, 2026-08-05): 예전엔 $var 가 전부 {{_prev_result}} 로
    뭉개졌고, 문장 경계(_seq_boundary)가 prev_result 를 비워 문서화된 예제가 빈 문자열을
    치환받았다. 아직 실행되지 않았거나 예외로 결과가 없는 인덱스는 빈 문자열로 치환한다.
    .path 가 붙으면 결과(JSON)에서 그 필드를 추출한다 — 실패는 ValueError(정직 실패).
    bare 참조는 v4 추출(_v4_var_payload)을 태운다 (F17-3).
    """
    if isinstance(obj, str):
        def _sub(m):
            base = step_results.get(int(m.group(1)), "")
            p = m.group(2)
            if p:
                return _extract_result_field(base, p)
            return _v4_var_payload(base)
        return _STEP_RESULT_RE.sub(_sub, obj)
    if isinstance(obj, dict):
        # 블록은 건드리지 않는다 (M6): 몸은 안쪽 파이프의 인덱스 공간 — 바깥 치환은 실행기가 _vars/_var_values 로.
        if any(obj.get(k) for k in ("_condition", "_case", "_try", "_repeat", "_assign", "_goal")):
            return obj
        return {k: _inject_step_results(v, step_results) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_inject_step_results(v, step_results) for v in obj]
    return obj


# $items 집합 바인딩 행 수 상한 — 초과는 침묵 절단 대신 정직 거절(take 로 줄이라고 안내).
ITEMS_BIND_CAP = 500

_ITEMS_REF = re.compile(r'^\$items(?:\.(\w+))?$')


def _bind_items_params(tool_input: dict, prev_result: str):
    """★$items 집합 바인딩 (2026-08-16 상상훈련 G1-③ 판정).

    step 파라미터 *값*이 정확히 "$items"(전체 행) 또는 "$items.필드"(각 행에서 그 필드만)
    이면, 이전 step 결과의 items 리스트를 **실행 시점에 값으로** 바인딩한다.

    - 텍스트 치환이 아니다 — 데이터가 문장 텍스트를 통과하면 이스케이프·페이로드가
      깨진다(옛 shell-IBL 은퇴 사유와 동류). $it(each, 행 단위)의 짝인 집합 단위 규약.
    - 행동 액션(show_map 등)이 **핸들러 수정 없이** 파이프 하류에 서는 길:
        [sense:restaurant]{query:"청주 맛집"} >> [table:take]{n:3} >> [limbs:show_map]{markers: "$items"}
      (verb 마다 _prev_result 소비를 붙이면 F6 비대칭이 재생산된다 — 규약은 언어에 한 번.)
    - 상한 ITEMS_BIND_CAP 초과는 침묵 절단 대신 정직 거절: 앞에 take 를 끼우라고 안내.
    - ★파서의 $var 할당과 공존: `$items = ...` 로 직접 할당하면 파서 치환이 먼저라
      여기 도달하지 않는다 — $items 는 예약어로 쓰지 않기를 권장(가이드 명기).

    반환: (tool_input, error_str|None) — 참조가 없으면 원본 그대로, 바인딩 실패는 정직 에러.
    """
    params = tool_input.get("params")
    if not isinstance(params, dict):
        return tool_input, None
    refs = {k: m for k, v in params.items()
            if isinstance(v, str) and (m := _ITEMS_REF.match(v.strip()))}
    if not refs:
        return tool_input, None

    # 이전 결과에서 items 통화 추출 (prev_result 는 _to_prev_currency 가 이미 items 파생을 마친 JSON)
    items = None
    s = (prev_result or "").strip()
    if s:
        try:
            obj = json.loads(s)
        except Exception:
            obj = None
        # 스필 참조 봉투면 본문으로 (M5)
        from common.spill import resolve_ref
        obj, _ref_err = resolve_ref(obj)
        if _ref_err:
            return tool_input, f"$items 바인딩 실패: {_ref_err}"
        if isinstance(obj, list):
            items = obj
        elif isinstance(obj, dict) and isinstance(obj.get("items"), list):
            items = obj["items"]
    if items is None:
        return tool_input, ("$items 바인딩 실패: 이전 step 결과에 items 통화가 없습니다. "
                            "앞 액션이 통화를 내는 생산자/변환자인지 확인하세요.")
    if len(items) > ITEMS_BIND_CAP:
        return tool_input, (f"$items 바인딩 거절: 행 {len(items)}개 — 상한 {ITEMS_BIND_CAP}. "
                            f"앞에 [table:take]{{n: ...}} 또는 filter 로 줄여 주세요(침묵 절단 금지).")

    out = dict(tool_input)
    out["params"] = dict(params)
    for key, m in refs.items():
        field = m.group(1)
        if field:
            missing = [1 for r in items if not (isinstance(r, dict) and field in r)]
            if items and len(missing) == len(items):
                return tool_input, (f"$items.{field} 바인딩 실패: '{field}' 필드가 어느 행에도 없습니다. "
                                    f"실제 필드: {sorted(items[0].keys()) if isinstance(items[0], dict) else '비-dict 행'}")
            out["params"][key] = [r.get(field) for r in items if isinstance(r, dict)]
        else:
            out["params"][key] = items
    return out, None


def _inject_prev_result(tool_input: dict, prev_result: str) -> dict:
    """{{_prev_result}} 템플릿을 이전 결과로 치환"""
    injected = {}
    for key, val in tool_input.items():
        if isinstance(val, str):
            injected[key] = val.replace("{{_prev_result}}", prev_result)
        elif isinstance(val, dict):
            injected[key] = _inject_prev_result(val, prev_result)
        else:
            injected[key] = val
    return injected


def _has_prev_ref(tool_input: dict) -> bool:
    """tool_input 어디에든 {{_prev_result}} 참조가 남아있는지 확인"""
    for key, val in tool_input.items():
        if isinstance(val, str) and "{{_prev_result}}" in val:
            return True
        elif isinstance(val, dict) and _has_prev_ref(val):
            return True
    return False


def _auto_inject_prev(tool_input: dict, prev_result: str) -> dict:
    """
    파이프라인 자동 데이터 전달.

    prev_result가 있고, step에 {{_prev_result}} 명시 참조가 없으면
    params._prev_result로 자동 주입.

    이를 통해 [sense:web_search]{query: "A"} >> [engines:newspaper]{query: "B"} 같은 파이프라인에서
    step 2가 step 1의 결과를 자동으로 받을 수 있다.
    """
    if not prev_result:
        return tool_input

    # 이미 {{_prev_result}} 템플릿 치환이 끝난 후이므로,
    # 원본에 참조가 있었다면 이미 치환됨 → 자동 주입 불필요
    # 참조가 없었던 경우에만 자동 주입
    # (치환 전 원본을 검사하는 것이 이상적이나, 현재 구조에서는
    #  치환 후에 호출하므로 params에 _prev_result가 이미 있는지 확인)
    params = tool_input.get("params", {})
    if isinstance(params, dict) and "_prev_result" not in params:
        tool_input = dict(tool_input)
        tool_input["params"] = dict(params)
        tool_input["params"]["_prev_result"] = prev_result

    return tool_input


def _to_prev_currency(result: Any) -> str:
    """다음 step 주입용 문자열 — **파이프 이음매에서만** 단일 통화(items)를 파생한다.

    감사 D13(2026-08-05): currency.py 문서는 파생 관문을 _route_handler 로 적었지만 실제
    호출처는 렌더러 경계(api_ibl)와 body_ask 뿐이라, table/blocks 만 내는 생산자가
    `>> [table:sort]` 파이프 안에서 items 를 못 찾고 깨졌다. 관문을 _route_handler 로 옮기면
    에이전트 최종 tool-result 에도 파생본이 실려 토큰이 중복된다(api_ibl 주석의 의도된 회피).
    → 진짜 갭은 파이프 이음매: prev_result 로 다음 step 에 물릴 때만 파생한다.
    results[]/step_results(모델·호출자에게 보이는 쪽)는 원형 유지 = 토큰 중복 0.

    JSON 문자열 결과(대다수 핸들러)도 파싱→파생→재직렬화로 커버. 파싱 불가면 원형 그대로.
    """
    from common.currency import derive_items
    r = result
    if isinstance(r, str):
        s = r.strip()
        if not (s.startswith("{") and s.endswith("}")):
            return _to_string(result)
        try:
            r = json.loads(s)
        except Exception:
            return _to_string(result)
    if isinstance(r, dict):
        return _to_string(derive_items(r))
    return _to_string(result)


def _step_label(step: Any) -> Tuple[str, str]:
    """봉투 results[] 의 (node, action) 라벨 — 블록 step 은 if/case/goal + "block" (옛 "?").
    긴 문장이 "어느 step 에서 왜" 죽었는지 읽으려면 블록도 이름이 있어야 한다(2026-08-22 M2)."""
    if not isinstance(step, dict):
        return "?", "?"
    if step.get("_condition"):
        return "if", "block"
    if step.get("_case"):
        return "case", "block"
    if step.get("_goal"):
        return "goal", "block"
    if step.get("_try"):
        return "try", "block"
    if step.get("_repeat"):
        return "repeat", "block"
    if step.get("_assign"):
        return "assign", f"${step.get('name')}"
    return step.get("_node", step.get("node", "?")), step.get("action", "?")


def _to_string(result: Any) -> str:
    """결과를 문자열로 변환 (다음 step 의 _prev_result 로 주입)."""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        # 포워드된 결과 봉투 벗기기 — @hub/@노드 로 원격 실행된 bare-string 읽기는
        # {"result": "<본문>", "_forwarded_to": ...} 로 감싸져 온다. 다음 step 은 전송 봉투가
        # 아니라 *본문*을 원하므로 내부 본문만 넘긴다(크로스노드 이음매).
        # ★단 통화(items/table)가 있으면 벗기지 않는다 — 변환자(table:sort 등)가 통화를 소비해야
        #   하는데, text 같은 요약 문자열로 벗기면 통화가 사라진다(file_find@hub >> sort 회귀).
        if result.get("_forwarded_to") and "items" not in result and "table" not in result:
            for _k in ("result", "message", "markdown", "text", "content"):
                _v = result.get(_k)
                if isinstance(_v, str):
                    return _v
        return json.dumps(result, ensure_ascii=False)
    if isinstance(result, (list, tuple)):
        return json.dumps(result, ensure_ascii=False)
    return str(result)


# === 워크플로우 CRUD ===

def preflight_sentence(code: Any) -> Dict:
    """저장된 IBL 문장이 **지금의 어휘로** 실행 가능한지 검사 (2026-08-15).

    왜 필요한가 — 저장된 문장은 어휘가 진화하면 썩는다. 08-15 실측: 워크플로 원장에
    살아 있던 6건이 *전부* 죽은 참조였고(self:file·search_papers·search_stock·video_info·
    limbs:transcript = 은퇴 어휘) 전량 폐기됐다. 그런데 목록은 그동안 아무 신호도 주지
    않았다 — 04시 정기보고 트리거가 은퇴한 `[self:report]{op:new}` 를 부르며 매일 조용히
    실패하던 선례와 같은 부류다.

    `self:script`(참조 원장)는 이미 list 에서 pre-flight(파일 실존·인터프리터 해석)를 하고
    `runnable:false` + 사유를 붙인다. 문장 원장(workflow·trigger)에도 같은 창구를 단다.

    반환: {"runnable": bool, "problem": str|None, "dead_vocab": [..]}

    ★한계(실측): 파서가 관대하다 — `[sense:search]{query: ` 같은 미종료 문자열도 예외 없이
    파싱된다(params 만 빈 채로). 그러므로 이 검사는 **어휘 생존**을 보장하지 지 문장이
    의도대로 쓰였는지는 보장하지 않는다. 잡는 것은 "은퇴한 낱말을 부르는 문장"이다.
    """
    from ibl_parser import parse as _parse, IBLSyntaxError
    from ibl_engine import get_node_actions

    if isinstance(code, (list, tuple)):
        parts = [c for c in code if isinstance(c, str) and c.strip()]
        if not parts:                      # dict step 배열이면 문법 검사 대상이 아니다
            return {"runnable": True, "problem": None, "dead_vocab": []}
        code = "\n".join(parts)
    if not isinstance(code, str) or not code.strip():
        return {"runnable": False, "problem": "실행할 문장이 비어 있습니다.", "dead_vocab": []}

    try:
        steps = _parse(code)
    except IBLSyntaxError as e:
        return {"runnable": False, "problem": f"IBL 문법 오류: {e}", "dead_vocab": []}

    dead = []
    for st in steps:
        if not isinstance(st, dict) or st.get("_goal") or st.get("_condition") or st.get("_case") \
                or st.get("_try") or st.get("_repeat") or st.get("_assign"):
            continue                        # 복합 블록은 내부 분기를 정적으로 못 본다
        node, action = st.get("_node"), st.get("action")
        if not node or not action:
            continue
        if action not in (get_node_actions(node) or set()):
            q = f"{node}:{action}"
            if q not in dead:
                dead.append(q)
    if dead:
        return {"runnable": False,
                "problem": f"지금 사전에 없는 어휘: {', '.join(dead)} — 은퇴했거나 이름이 바뀌었습니다.",
                "dead_vocab": dead}
    return {"runnable": True, "problem": None, "dead_vocab": []}


def list_workflows() -> List[Dict]:
    """저장된 워크플로우 목록 (문장 pre-flight 동반 — preflight_sentence 참조)"""
    wf_path = _get_workflows_path()
    workflows = []
    for f in sorted(wf_path.glob("*.yaml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except Exception as e:
            # ★깨진 원장 항목을 조용히 감추지 않는다 — 목록에서 사라지면 "없는 것"이 된다.
            workflows.append({
                "id": f.stem, "name": f.stem, "description": "", "steps_count": 0,
                "file": str(f), "runnable": False,
                "problem": f"워크플로 파일을 읽을 수 없습니다: {e}",
            })
            continue
        steps = data.get("steps", []) or data.get("pipeline") or []
        # ★B1 동형: steps 가 문자열(저장 원문)이면 len()이 글자 수가 된다 — 목록에서
        # "스텝 121개"로 보이는 오표시 방지. 문장 하나 = 스텝 하나로 센다.
        if isinstance(steps, str):
            steps = [steps] if steps.strip() else []
        raw_steps = data.get("steps", []) or []
        if isinstance(raw_steps, str):
            raw_steps = [raw_steps] if raw_steps.strip() else []
        pf = preflight_sentence(steps)
        entry = {
            "id": f.stem,
            "name": data.get("name", f.stem),
            "description": data.get("description", ""),
            "steps_count": len(raw_steps),
            "file": str(f),
            "runnable": pf["runnable"],
        }
        if pf["problem"]:
            entry["problem"] = pf["problem"]
            if pf["dead_vocab"]:
                entry["dead_vocab"] = pf["dead_vocab"]
        workflows.append(entry)
    return workflows


def _resolve_workflow_id(name: str) -> str:
    """name(또는 id)을 저장된 워크플로우 id로 해소. 코퍼스/사용자가 이름으로 호출해도
    run/get/delete가 동작하도록 — id 정확일치 → 이름 일치 → slugify 순. 못 찾으면 입력 그대로."""
    name = str(name).strip()
    if not name:
        return ""
    wfs = list_workflows()
    ids = {w["id"] for w in wfs}
    if name in ids:
        return name
    for w in wfs:
        if w.get("name") == name:
            return w["id"]
    slug = _slugify(name)
    if slug in ids:
        return slug
    return name


def get_workflow(workflow_id: str) -> Optional[Dict]:
    """워크플로우 조회"""
    wf_path = _get_workflows_path() / f"{workflow_id}.yaml"
    if not wf_path.exists():
        return None
    try:
        data = yaml.safe_load(wf_path.read_text(encoding="utf-8"))
        data["id"] = workflow_id
        return data
    except Exception:
        return None


# === 등록 시점 문법 관문 (2026-08-17) ===
# save 가 do 를 검증 없이 저장해 "저장은 됐는데 돌리면 깨지는" 지연 실패를 냈다
# (실측: 따옴표가 잘린 do — `[self:discover]{query: "` — 가 success:true 로 저장되고
# run 에서야 엉뚱하게 실행됐다). [self:script]{op:"register"} 의 pre-flight 선례를
# 문장에 적용한다: 등록=문법 관문, 실행 가능성은 런타임 몫이라 파싱만 하고 실행 안 함.
#
# ★파서만으로는 못 잡는다(실측): 파서는 닫히지 않은 따옴표·중괄호를 관대하게 흡수해
#   위 잘린 문장을 query:"" 로 통과시킨다(_extract_bracket 의 "닫는 bracket 못 찾으면
#   원본 반환"). 그 관대함은 실행 경로의 기존 계약이라 건드리지 않고, 등록 관문에서만
#   균형을 따로 본다.

_SENTENCE_KEYS = ("steps", "pipeline", "do")


def _unclosed_reason(code: str) -> Optional[str]:
    """따옴표·중괄호 균형 검사. 반환: 오류 사유|None.

    문자열 상태를 줄 경계 너머로 승계하는 파서의 스캐너를 그대로 쓴다
    (주석 줄을 스캔에서 빼는 규칙도 _preprocess 와 동일 — 주석 속 따옴표가
    상태를 오염시키지 않게)."""
    from ibl_parser import _scan_line_state
    depth, in_string, string_char = 0, False, None
    for line in str(code).split('\n'):
        stripped = line.strip()
        if not in_string and (not stripped or stripped.startswith('#')):
            continue
        d, in_string, string_char = _scan_line_state(stripped, in_string, string_char)
        depth += d
    if in_string:
        return f"따옴표({string_char})가 닫히지 않았습니다"
    if depth > 0:
        return "중괄호 {가 닫히지 않았습니다"
    if depth < 0:
        return "여는 중괄호 없이 }가 있습니다"
    return None


def _validate_sentence(raw) -> Optional[str]:
    """저장 전 do(문장 또는 문장 배열) 문법 검사. 반환: 오류문|None.

    미할당 $변수는 합법(호출자 params 주입 자리)이라 파서가 리터럴로 통과시킨다.
    이미 파싱된 dict step 은 파서를 지나온 값이므로 통과."""
    from ibl_parser import parse as ibl_parse, IBLSyntaxError
    sentences = raw if isinstance(raw, list) else [raw]
    if not sentences:
        return "do 가 비어 있습니다 — 저장할 IBL 문장이 필요합니다."
    for one in sentences:
        if isinstance(one, dict):
            continue
        if not isinstance(one, str) or not one.strip():
            return "do 에 빈 문장이 있습니다 — 저장할 IBL 문장이 필요합니다."
        reason = _unclosed_reason(one)
        if reason:
            return f"do 문법 오류 — {reason}: {one[:120]}"
        try:
            ibl_parse(one)
        except IBLSyntaxError as e:
            return f"do 문법 오류 — {e}"
    return None


def save_workflow(workflow: dict) -> str:
    """
    워크플로우 저장

    Args:
        workflow: {name, description?, steps: [...], id?}

    Returns:
        워크플로우 ID
    """
    wf_id = workflow.get("id") or _slugify(workflow.get("name", "workflow"))
    wf_path = _get_workflows_path() / f"{wf_id}.yaml"

    # id 필드는 YAML에 저장하지 않음 (파일명이 ID)
    save_data = {k: v for k, v in workflow.items() if k != "id"}
    save_data["updated"] = datetime.now().isoformat()

    wf_path.write_text(
        yaml.dump(save_data, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    return wf_id


def delete_workflow(workflow_id: str) -> bool:
    """워크플로우 삭제"""
    wf_path = _get_workflows_path() / f"{workflow_id}.yaml"
    if wf_path.exists():
        wf_path.unlink()
        return True
    return False


def execute_workflow(workflow_id: str, project_path: str = ".",
                     params: Optional[dict] = None) -> dict:
    """
    저장된 워크플로우 실행

    Args:
        workflow_id: 워크플로우 ID (파일명)
        project_path: 프로젝트 경로
        params: 호출자 변수 {이름: 값} — 저장된 문장 안 미할당 $이름 자리에 주입 (선택).
                desc 가 선언만 하고 구현이 없어 침묵 유실되던 것(2026-08-17 B8 수리).

    Returns:
        파이프라인 실행 결과
    """
    wf = get_workflow(workflow_id)
    if not wf:
        return {"success": False, "error": f"워크플로우를 찾을 수 없습니다: {workflow_id}"}

    steps = wf.get("steps", [])

    # Phase 15: pipeline 문자열 지원 — steps가 없으면 pipeline 필드를 IBL 파서로 변환
    if not steps and wf.get("pipeline"):
        from ibl_parser import parse as ibl_parse, IBLSyntaxError
        try:
            steps = ibl_parse(wf["pipeline"])
        except IBLSyntaxError as e:
            return {"success": False, "error": f"워크플로우 pipeline 문법 오류: {str(e)}"}

    if not steps:
        return {"success": False, "error": "워크플로우에 steps 또는 pipeline이 없습니다."}

    inject_meta = None
    if params:
        steps, _perr = _normalize_steps_for_injection(steps)
        if _perr:
            return {"success": False, "error": f"워크플로우 문법 오류: {_perr}"}
        steps, inject_meta = _apply_caller_params(steps, params)

    result = execute_pipeline(steps, project_path)
    result["workflow_id"] = workflow_id
    result["workflow_name"] = wf.get("name", workflow_id)
    if inject_meta:
        result.update(inject_meta)
    return _promote_final_currency(result, steps)


# === IBL 노드 액션 핸들러 ===

def execute_workflow_action(action: str, params: dict,
                            project_path: str) -> Any:
    """
    ibl_engine에서 호출되는 워크플로우 노드 액션 핸들러

    Args:
        action: run, list/list_workflows, get/get_workflow, save/save_workflow,
                delete/delete_workflow, run_pipeline
        params: 파라미터 (workflow_id 등 포함)
    """
    # 단일 액션 패턴: workflow {op} 통합 액션. op로 다시 분기.
    if action == "workflow":
        op = (params.get("op") or "").strip()
        if not op:
            return {"error": "op 파라미터가 필요합니다. (list|get|save|delete|run)"}
        action = op

    workflow_id = params.get("workflow_id", "")
    # 코퍼스/사용자는 name으로도 호출 → 저장된 id로 해소 (run/get/delete round-trip).
    # save는 제외 (save_workflow가 name→slug로 새 id를 생성).
    if (not workflow_id
            and action in ("get", "get_workflow", "run", "delete", "delete_workflow")
            and (params.get("name") or params.get("id"))):
        workflow_id = _resolve_workflow_id(params.get("name") or params.get("id"))

    if action in ("list", "list_workflows"):
        return {"workflows": list_workflows(), "count": len(list_workflows())}

    elif action in ("get", "get_workflow"):
        if not workflow_id:
            return {"error": "workflow_id가 필요합니다."}
        wf = get_workflow(workflow_id)
        if not wf:
            return {"error": f"워크플로우를 찾을 수 없습니다: {workflow_id}"}
        return wf

    elif action == "run":
        # 호출자 params({변수: 값}) — 문장 안 미할당 $변수에 주입. desc 선언대로
        # 저장본·즉석 양 경로 동일 지원 (2026-08-17 B8 수리 — 전엔 침묵 유실).
        caller, _perr = _coerce_caller_params(params.get("params"))
        if _perr:
            return {"error": _perr}
        # 즉석 실행 (2026-08-05, 구 [self:run_pipeline] 흡수 — 변형=op 명명 헌법):
        # workflow_id 없이 steps/pipeline 이 오면 저장 없이 바로 실행.
        if not workflow_id and (params.get("steps") or params.get("pipeline")):
            return _run_inline(params, project_path, caller_params=caller)
        if not workflow_id:
            return {"error": "workflow_id(저장본) 또는 steps/pipeline(즉석 실행)이 필요합니다.",
                    "available": [w["id"] for w in list_workflows()]}
        return execute_workflow(workflow_id, project_path, params=caller)

    elif action in ("save", "save_workflow"):
        if not params:
            return {"error": "워크플로우 정의(params)가 필요합니다."}
        # 등록 시점 문법 관문 — 몸통이 없거나 깨졌으면 저장 자체를 거부한다.
        body_key = next((k for k in _SENTENCE_KEYS if params.get(k) is not None), None)
        if body_key is None:
            return {"success": False,
                    "error": "do 가 필요합니다 — 저장할 IBL 문장(또는 문장 배열).",
                    "hint": '[self:workflow]{op: "save", name: "이름", do: "[node:action]{...}"}'}
        err = _validate_sentence(params[body_key])
        if err:
            return {"success": False, "error": err,
                    "hint": "저장하지 않았습니다 — 문장을 고쳐 다시 save 하세요. "
                            "(등록은 문법만 봅니다; 실행 성공 여부는 run 이 판정합니다.)"}
        wf_data = dict(params)
        if workflow_id:
            wf_data["id"] = workflow_id
        wf_id = save_workflow(wf_data)
        return {"success": True, "workflow_id": wf_id, "message": f"워크플로우 '{wf_id}' 저장 완료"}

    elif action in ("delete", "delete_workflow"):
        if not workflow_id:
            return {"error": "workflow_id가 필요합니다."}
        ok = delete_workflow(workflow_id)
        if ok:
            return {"success": True, "message": f"워크플로우 '{workflow_id}' 삭제 완료"}
        return {"error": f"워크플로우를 찾을 수 없습니다: {workflow_id}"}

    elif action == "run_pipeline":
        # 내부 배관 진입점 (trigger_engine·calendar_actions·system_ai_plans 가 action 이름으로
        # 직접 호출 + 스케줄 event_action 어휘). IBL 표면 어휘 [self:run_pipeline] 은
        # 2026-08-05 [self:workflow]{op:"run", steps} 로 흡수 — 실행 본체는 _run_inline 공유.
        # params 주입도 run 과 일관 지원 (내부 호출자는 params 키를 안 쓰므로 무회귀).
        caller, _perr = _coerce_caller_params(params.get("params"))
        if _perr:
            return {"error": _perr}
        return _run_inline(params, project_path, caller_params=caller)

    return {"error": f"알 수 없는 워크플로우 액션: {action}", "available_actions": ["run", "list", "get", "save", "delete", "run_pipeline"]}


def _run_inline(params: dict, project_path: str,
                caller_params: Optional[dict] = None) -> Any:
    """즉석 파이프라인 실행 — pipeline(IBL 코드 문자열) 또는 steps(파싱된/코드 배열).
    caller_params 가 있으면 저장본 실행과 동일하게 $변수 주입."""
    pipeline = params.get("pipeline", "")
    if pipeline:
        from ibl_parser import parse as ibl_parse, IBLSyntaxError
        try:
            steps = ibl_parse(pipeline)
        except IBLSyntaxError as e:
            return {"error": f"IBL 문법 오류: {str(e)}"}
    else:
        steps = params.get("steps", [])

    if not steps:
        return {"error": "params.steps 또는 params.pipeline이 필요합니다."}

    inject_meta = None
    if caller_params:
        steps, _perr = _normalize_steps_for_injection(steps)
        if _perr:
            return {"error": _perr}
        steps, inject_meta = _apply_caller_params(steps, caller_params)

    result = execute_pipeline(steps, project_path)
    if inject_meta and isinstance(result, dict):
        result.update(inject_meta)
    return _promote_final_currency(result, steps)


def _promote_final_currency(out, steps: Optional[list] = None):
    """run 봉투 최상위로 마지막 문장의 통화(items)를 승격 — 워크플로우의 파이프 시민화.

    2026-08-17 통화 조건 판정(사용자 A안): [self:script] 의 stdout items 승격 선례
    (script_ops.py — 선언 items + 실려 있을 때만 승격, 아니면 하류 정직 에러)를
    워크플로우에 적용. final_result 는 이미 파이프 이음매(_to_prev_currency)가
    파생한 통화 문자열이라, items 가 실려 있으면 봉투 최상위로 올려
    `[self:workflow]{op:"run", name:…} >> [table:*]` 가 흐른다.
    몸통이 effect/scalar 로 끝나면 승격 없음 → 하류 변환자의 기존 정직 에러
    (새 침묵 경로 0). error 계약 불변 — 바깥 파이프의 실패 처리가 우선한다.
    """
    if not isinstance(out, dict):
        return out
    # `$return = …` 반환 규약 (M6 — 설계 §3 "반환 규약 보강"): 몸통에 $return 할당이 있으면 *그 문장의 결과*가
    # run 의 반환값이다(마지막 문장이 effect 로 끝나도 됨). 파서가 할당 문장의 끝 step 에 _assign_name 을 찍는다.
    if isinstance(steps, list) and out.get("success", True):
        for idx, st in enumerate(steps):
            if isinstance(st, dict) and st.get("_assign_name") == "return":
                for r in out.get("results") or []:
                    if isinstance(r, dict) and r.get("step") == idx + 1 and "result" in r:
                        out["final_result"] = r["result"]
                        out["returned"] = "$return"
                        break
                break
    fr = out.get("final_result")
    if not isinstance(fr, str) or not fr.strip().startswith("{"):
        return out
    try:
        obj = json.loads(fr)
    except Exception:
        return out
    if isinstance(obj, dict) and isinstance(obj.get("items"), list):
        out["items"] = obj["items"]
        out["count"] = len(obj["items"])
    return out


# === 호출자 params → $변수 주입 (2026-08-17 B8 수리) ===
# desc 는 "run — … + params 옵션(문장 안 $변수에 주입)" 을 선언해 왔지만 구현이 없어
# 호출자 params 가 침묵 유실됐다(워크플로우는 고정값으로 돌아 거짓 정상을 냈다).
# 주입 자리: 파서의 $var 기계장치는 *할당된* 변수만 {{_step_N_result}} 로 치환하고
# 미할당 $이름은 리터럴로 남긴다 — 그 리터럴 자리가 호출자 params 의 자리다.
# 파스 *후* dict 값 층에서 주입하므로 ①문장 안 할당($x = …)이 항상 이기고
# ②값에 따옴표·개행이 들어도 IBL 문법을 깨뜨리지 않는다.

# $it(each 행 참조)·$items(집합 바인딩) — 런타임 바인더 소유라 주입 금지.
_CALLER_VAR_RESERVED = {"it", "items"}


def _coerce_caller_params(raw) -> tuple:
    """run 의 params 를 dict 로 강제. 반환: (dict|None, 오류문|None).

    모델이 JSON *문자열*로 넘기는 경우를 관용 수용하되, 객체가 아니면
    침묵 무시 대신 정직 거절(B8 부류 재발 방지)."""
    if raw is None:
        return None, None
    if isinstance(raw, dict):
        return (raw or None), None
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None, None
        try:
            loaded = json.loads(s)
        except Exception:
            loaded = None
        if isinstance(loaded, dict):
            return (loaded or None), None
    return None, (f"params 는 {{변수명: 값}} 객체여야 합니다 (받은 형: {type(raw).__name__}). "
                  '예: [self:workflow]{op:"run", workflow_id:"x", params:{city:"청주"}}')


def _normalize_steps_for_injection(steps) -> tuple:
    """문자열 step 을 파싱해 dict 로 — 주입은 파싱된 값 층에서만 안전하다.
    execute_pipeline 입구 정규화와 같은 규칙(통짜 문자열 감싸기 + 원소별 파싱).
    반환: (steps|None, 오류문|None)."""
    if isinstance(steps, str):
        steps = [steps] if steps.strip() else []
    if not steps:
        return None, "steps가 비어있습니다."
    if not any(isinstance(s, str) for s in steps):
        return steps, None
    from ibl_parser import parse as ibl_parse, IBLSyntaxError
    normalized = []
    for s in steps:
        if isinstance(s, str):
            if not s.strip():
                continue
            try:
                normalized.extend(ibl_parse(s))
            except IBLSyntaxError as e:
                return None, f"IBL 문법 오류: {s} → {str(e)}"
        else:
            normalized.append(s)
    if not normalized:
        return None, "steps가 비어있습니다."
    return normalized, None


def _reserved_row_names(steps) -> set:
    """주입 금지 이름 — $it/$items + 문장 안 each 가 as 로 정한 커스텀 행 이름."""
    names = set(_CALLER_VAR_RESERVED)

    def _walk(obj):
        if isinstance(obj, dict):
            a = obj.get("as")
            if isinstance(a, str) and a.strip():
                names.add(a.strip())
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v)

    _walk(steps)
    return names


def _apply_caller_params(steps: list, caller: dict) -> tuple:
    """호출자 params 를 steps 의 $변수 자리에 주입. 반환: (새 steps, 정직 메타 dict).

    치환 규칙(파서 _resolve_variables 와 동일한 이름 경계):
      - 값이 정확히 "$key" 하나면 원시 타입 보존(숫자·리스트·dict 그대로)
      - 문자열 속에 섞여 있으면 문자열 임베드(dict/list 는 JSON)
    메타: params_injected(주입된 키) / params_warning(대응 $변수 없는 키·예약 이름 —
    조용히 버리지 않고 알린다)."""
    reserved = _reserved_row_names(steps)
    hits = set()

    def _embed(value) -> str:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    def _sub_str(s: str):
        for key, value in caller.items():
            if key in reserved:
                continue
            if s == f"${key}":
                hits.add(key)
                return value  # 통짜 참조 — 원시 타입 보존
            pattern = r'\$%s(?!\w)' % re.escape(key)
            if re.search(pattern, s):
                hits.add(key)
                s = re.sub(pattern, lambda _m, _v=value: _embed(_v), s)
        return s

    def _walk(obj):
        if isinstance(obj, str):
            return _sub_str(obj)
        if isinstance(obj, dict):
            return {k: _walk(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_walk(v) for v in obj]
        return obj

    new_steps = _walk(steps)
    meta = {}
    if hits:
        meta["params_injected"] = sorted(hits)
    unmatched = sorted(set(caller) - hits - reserved)
    skipped = sorted(set(caller) & reserved)
    warnings = []
    if unmatched:
        warnings.append(f"params {unmatched} 에 대응하는 $변수가 문장에 없어 주입되지 않았습니다.")
    if skipped:
        warnings.append(f"params {skipped} 는 예약 이름($it/$items/each as)이라 주입하지 않습니다.")
    if warnings:
        meta["params_warning"] = " ".join(warnings)
    return new_steps, meta


# === 유틸리티 ===

def _slugify(text: str) -> str:
    """텍스트를 파일명에 적합한 slug로 변환"""
    # 한글은 유지, 특수문자 제거
    slug = re.sub(r'[^\w가-힣\s-]', '', text)
    slug = re.sub(r'[\s]+', '_', slug).strip('_')
    return slug or "workflow"
