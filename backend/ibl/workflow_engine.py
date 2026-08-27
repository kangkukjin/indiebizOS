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
# 정직 표지의 단일 소스 (B48-1/2) — 잎 모듈이라 순환 참조가 없다.
from ibl_honesty import markers_of as _honesty_markers_of  # noqa: F401


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

def is_error_result(result) -> bool:
    """도구 결과가 실패인지 판정한다 — `>>`·`??` 공용 **단일 소스**.

    도구가 실패를 알리는 방식이 **네 갈래**라 판정이 곳곳에 복제됐다가 갈라졌었다
    (2026-07-18: `??` 만 문자열 에러를 성공으로 세어, NameError 를 고친 뒤에도 폴백이 안 됨).
    새 소비자는 이 함수를 부를 것 — 판정을 다시 손으로 적지 말 것.

    실패로 치는 것:
      1. dict: `success is False`, 또는 최상위 `error` 키가 있고 success 가 참이 아님
      2. str `"Error:"`·`"오류:"` 접두 — system_essentials 계열(self:read/delete/copy).
         ★한글 접두는 2026-08-22 추가(B21-1): 영어판만 등록돼 있어 `"오류: …"` 를 내던
         media_producer 계열이 통째로 성공으로 샜다. 다만 이건 **그물**일 뿐이다 —
         같은 계열 26자리 중 10자리는 애초에 접두가 없었으므로(`FFmpeg 오류:`·
         `렌더링 중 오류 발생:`) 접두를 늘리는 것으로는 못 고친다. 진짜 수리는 그쪽
         핸들러를 error dict 계약으로 옮긴 것이고, 이 줄은 다음 위반자를 잡는 안전망이다.
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
        if s.startswith("Error:") or s.startswith("오류:"):
            return True
        # handler 라우터의 JSON 문자열 — 최상위만 파싱해 dict 규칙 재사용
        if s.startswith("{"):
            try:
                import json as _json
                parsed = _json.loads(s)
            except Exception:
                return False
            if isinstance(parsed, dict):
                return is_error_result(parsed)
        return False
    return False


def _is_empty_result(result) -> bool:
    """도구 결과가 **빈손**인지 판정한다 — `??` 전용 보조 술어 (2026-08-08, 실험 7 ⑯).

    두 연산자의 술어는 원래 다르다:
      - `>>` 순차: "앞이 죽었으면 멈춰라" → 고장(is_error_result)만. 0건은 죽음이
        아니고, 0건 위의 take/filter 가 0건을 내는 것이 정답이다.
      - `??` 폴백: "원하는 걸 못 얻었으면 딴 데로" → **빈손도 못 얻은 것**.
        폴백을 거는 대상은 대개 검색이고 목록형 검색의 흔한 실패 모드가 0건이라,
        고장 판정만으로는 발동해야 할 자리의 다수를 통과시킨다(실측: [sense:used]
        total:0 이 status ok 로 기록되고 뒤의 웹 검색이 손도 안 대진 채 남았다).
    2026-07-18 의 판정 통일(is_error_result 단일 소스)은 유지 — 이 술어는 or 로만 얹는다.

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

    _seq = {"skip_until": -1, "failed": 0, "last_mode": None, "skipped": [], "halted": [],
            "branches_failed": [], "empty_notes": [], "list_in_text": [],
            # ★F35-1 (35회차): `??` 가 갈아탄 사실을 봉투 최상위로 올리는 누산기.
            #   교재는 `_fallback_used` 를 정직 표지 **1번**으로 가르치는데 실물이 없었다.
            "fallback_used": [],
            # ★B48-2 (48회차): 병렬 가지가 *성공*으로 돌아왔을 때 그 안의 부분 실패
            #   (each 의 error_count·errors, truncated, _fallback_used …) 를 담는 누산기.
            "branch_honesty": []}

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
        # ★F24-1(24회차): 중단 payload 는 봉투 조립부를 거치지 않아 앞 step 에서 죽은 병렬
        # 분기가 통째로 사라졌다 — 괄호 분기가 죽으면 union 의 2차 증상("통화 종류가 다릅니다")
        # 만 보이고 진짜 원인(분기 사망)은 어디에도 없었다. 중단 경로에도 같이 싣는다.
        if _seq["branches_failed"]:
            abort_payload["branches_failed"] = list(_seq["branches_failed"])
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
                    # ★V49-1: 아직 **기록되지 않은** 슬롯은 싣지 않는다. 종전엔 `.get(i, "")` 라
                    #   슬롯이 비어 있어도 빈 문자열이 값으로 들어가, 안 탄 분기가 낳았어야 할
                    #   변수(`[if: false]{$k = 7}` 뒤의 `$k`)가 "미할당"이 아니라 **빈 값**으로
                    #   조건에 들어갔다 — 판정 불능이어야 할 자리가 조용히 거짓이 된다.
                    #   빠뜨리면 술어 언어가 기존대로 정직하게 "미할당"을 신고한다.
                    step["_var_values"] = {**(step.get("_var_values") or {}),
                                           **{n: step_results[int(i)] for n, i in step["_vars"].items()
                                              if int(i) in step_results}}
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
            # ★B24-1(24회차 상상훈련): **병렬만 실패 신고 키가 없었다.** 순차는
            # skipped_steps·statements_failed·halted_steps 로, 폴백은 attempts[] 로 신고하는데
            # 병렬은 가지가 하나 죽어도 전부 죽어도 봉투가 success: true 였다(침묵/거짓 성공
            # 부류의 여덟 번째 자리 — 하필 행동 기준 가장 많이 쓰이는 조합 문법 18.7%).
            # 판정은 단일 소스 is_error_result 로, 승격은 skipped_steps/halted_steps 와 같은 규약.
            _branches = result if isinstance(result, list) else []
            _bfail = []
            for _bi, _br in enumerate(_branches):
                if not is_error_result(_br):
                    continue
                _bs = step["branches"][_bi] if _bi < len(step["branches"]) else {}
                _bd = _br
                if isinstance(_bd, str):
                    try:
                        _bd = json.loads(_bd)
                    except Exception:
                        pass
                _bfail.append({
                    "branch": _bi + 1,
                    "node": (_bs.get("_node") or _bs.get("node") or "?") if isinstance(_bs, dict) else "?",
                    "action": (_bs.get("action") or "?") if isinstance(_bs, dict) else "?",
                    "error": (_bd.get("error") if isinstance(_bd, dict) else str(_bd))[:300],
                })
            _rec = {
                "step": i + 1, "type": "parallel",
                "branches": len(step["branches"]),
                "result": result_str,
                "duration_ms": duration_ms,
            }
            if _bfail:
                _rec["branches_failed"] = _bfail
                _seq["branches_failed"].append({"step": i + 1, "failed": _bfail,
                                                "of": len(_branches)})
            # ★B48-2(48회차 상상훈련): B24-1 이 고친 것은 가지가 **통째로** 죽은 경우뿐이다.
            #   가지가 success:true 로 돌아오면 그 안의 부분 실패는 봉투에서 통째로 증발했다:
            #     ([table:each]{2행, 1행 실패}) & [sense:host]{op:"status"} >> [table:union]
            #       → success:true, error_count 없음   ← "2종목 중 1종목 실패"가 "성공"이 된다
            #     같은 each 를 단독으로 돌리면 error_count:1 + errors[원 행] 로 정직하다.
            #   가지 봉투를 손에 쥔 유일한 자리가 여기이므로 여기서 걷는다(승격 규약은
            #   branches_failed 와 같다 — _seq 누산 후 최상위 + warning).
            _bhon = []
            for _bi, _br in enumerate(_branches):
                if is_error_result(_br):
                    continue          # 전체 실패는 위 branches_failed 가 이미 신고했다
                _m = _honesty_markers_of(_br)
                if _m:
                    _bhon.append({"branch": _bi + 1, "markers": _m})
            if _bhon:
                _rec["branches_honesty"] = _bhon
                _seq["branch_honesty"].append({"step": i + 1, "branches": _bhon,
                                               "of": len(_branches)})
            results.append(_rec)
            step_results[i] = result_str
            # 전 가지 실패 = 아무것도 못 가져온 것. 그것을 성공이라 부르면 그 뒤의 모든 단계가
            # 빈손 위에서 돈다 — 순차 step 실패와 같은 경로로 보낸다(resume 참조도 여기서 붙는다).
            # ★파괴적 변경: 사용자 판정(2026-08-22 '네 의견대로 고쳐'). 한 가지만 실패면
            # 부분 성공이 맞으므로 success: true + 경고 유지.
            if _branches and len(_bfail) == len(_branches):
                _why = "; ".join(f"분기 {b['branch']}([{b['node']}:{b['action']}]): {b['error'][:120]}"
                                 for b in _bfail)
                _abort = _handle_failure(i, {
                    "success": False, "steps_completed": i, "steps_total": total,
                    "results": results, "final_result": result_str,
                    "error": f"Step {i+1} 병렬 전 가지 실패({len(_bfail)}/{len(_branches)}): {_why}",
                })
                if _abort is not None:
                    return _abort
                prev_result = _after_failure(prev_result)
                continue
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
            is_err = isinstance(result, dict) and result.get("_all_failed") and is_error_result(result)
            action_count += 1
            _rec_fb = {
                "step": i + 1, "type": "fallback",
                "chain_length": len(step["_fallback_chain"]),
                "attempts": fallback_log,
                "result": result_str,
                "duration_ms": duration_ms,
            }
            # ★F35-1 (2026-08-23 상상훈련 35회차): 갈아탄 사실을 **봉투**에 단다.
            #   옛 배선은 표지를 *결과 안*에 넣었다(_execute_fallback: dict 면 키 추가,
            #   '{' 로 시작하는 JSON 문자열이면 파싱해 추가). 그래서 결과가 **평문 스칼라**면
            #   ─ 세 번째 모양 ─ 표지가 조용히 사라졌다. 실측: `[sense:stock]{ZZZZINVALID}
            #   ?? [self:time]` 의 final_result 는 '2026-08-23 21:05:31' 이고 최상위·
            #   final_result·results[0] 어디에도 `_fallback_used` 가 없었다.
            #   ★교재가 이 표지를 **정직 표지 1번**으로 가르치므로("데이터의 출처가 바뀌었다"),
            #     읽는 쪽은 없으면 '폴백 안 씀'으로 단정한다 — 34회차의 이 세션 자신이
            #     그 키를 세어 0 을 얻고 그렇게 읽었다(거짓 안심).
            #   처방은 결과 모양을 열거하지 않는다. 성패 판정의 진실 소스는 이미 `attempts`
            #   이므로 그것만 보고, 신고는 branches_failed 와 **같은 배선**(step 요약 →
            #   _seq 누산 → 최상위 승격 + warning)에 태운다.
            _fb_ok = [a for a in (fallback_log or []) if a.get("status") == "ok"]
            if _fb_ok and _fb_ok[0].get("attempt", 1) > 1:
                _fb_at = _fb_ok[0]["attempt"]
                _rec_fb["_fallback_used"] = _fb_at
                _seq["fallback_used"].append({
                    "step": i + 1, "attempt": _fb_at,
                    "action": f"{_fb_ok[0].get('node')}:{_fb_ok[0].get('action')}",
                    "skipped": [f"{a.get('node')}:{a.get('action')}" for a in (fallback_log or [])
                                if a.get("attempt", 0) < _fb_at],
                })
            results.append(_rec_fb)
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
        is_err = is_error_result(result)

        action_count += 1
        _rec = {
            "step": i + 1,
            "node": _step_label(tool_input)[0],
            "action": _step_label(tool_input)[1],
            "result": result_str,
            "duration_ms": duration_ms,
        }
        # ★F19-1: 조건 블록(if/case)이 side-channel 로 남긴 관측 메타(어느 가지·좌변값)를
        # step 기록에 싣는다 — 분기 결과가 스칼라라 통화에 못 실리는 경우에도 봉투로 보인다.
        _bmeta = tool_input.get("_branch_meta") if isinstance(tool_input, dict) else None
        if isinstance(_bmeta, dict):
            _rec.update(_bmeta)
        # ★G31-1(2026-08-23 판정): 문장 속 참조가 목록을 JSON 으로 넣은 사실을 step 기록과 봉투
        #   최상위 경고로 올린다. 표식은 바인딩·주입기·블록 실행기가 같은 키로 남기고, 번역은 여기
        #   한 번(_list_in_text_warning). 실패로 뒤집지 않는다 — 데이터를 AI 에 먹이는 정당한 용법이다.
        _lit = tool_input.get("_list_in_text") if isinstance(tool_input, dict) else None
        if isinstance(_lit, list) and _lit:
            _rec["list_in_text"] = list(_lit)
            _n, _a = _step_label(tool_input)
            _seq["list_in_text"].append({"step": i + 1, "action": f"{_n}:{_a}", "refs": list(_lit)})
        # ★F23-2(상상훈련 23회차): [repeat:] 가 종료 조건을 못 채우고 상한에 걸려 멈추면
        # 블록 결과는 halted 와 "성공 아님·실패 아님" note 를 정확히 싣는데, **파이프 봉투
        # 최상위는 success: true** 였다 — 자동화가 success 만 보면 "조건을 만족하고 끝났다"로
        # 읽는다. skipped_steps 와 같은 승격 규약으로 봉투 표면까지 올린다(실패로 뒤집지는
        # 않는다 — 통화는 실제로 나왔고 note 도 실패가 아니라고 말한다).
        if isinstance(result, dict) and result.get("halted") in ("max", "wall", "budget"):
            _seq["halted"].append({"step": i + 1, "halted": result["halted"],
                                   "iterations": result.get("iterations")})
        # ★29회차 관찰: **0행의 이유**는 통화에 실을 자리가 없어 파이프 중간에서 사라진다.
        # `[table:since]` 첫 검침은 "기준선 3행을 세웠다(그래서 0건)" 라고 정직하게 말하지만,
        # 뒤에 무엇이 오면 그 note 는 다음 step 의 결과에 덮여 사용자는 0건만 본다 —
        # *"처음이라 기준선만 세웠다"* 와 *"새 것이 없다"* 가 구별 불가능해진다.
        # 승격 규약은 halted/skipped_steps 와 같다. **모양으로만 판정**한다(어휘 이름을 엔진에
        # 심지 않는다): 통화가 0행인데 note 를 달고 있는 중간 step. 마지막 step 은
        # final_result 로 이미 보이므로 싣지 않는다(중복 토큰 0).
        if i < total - 1 and isinstance(result, dict):
            _note = result.get("note")
            if (isinstance(result.get("items"), list) and not result["items"]
                    and isinstance(_note, str) and _note.strip()):
                _n, _a = _step_label(tool_input)
                _seq["empty_notes"].append({"step": i + 1, "action": f"{_n}:{_a}",
                                            "note": _note.strip()})
        results.append(_rec)
        step_results[i] = result_str
        # 블록 몸이 재할당한 바깥 변수(M6 repeat) — 루프 뒤 `$n` 이 최신값이 되게 되쓴다
        if isinstance(result, dict) and isinstance(result.get("_var_updates"), dict) and step.get("_vars"):
            for _n, _raw in result["_var_updates"].items():
                _ix = step["_vars"].get(_n)
                if _ix is not None:
                    step_results[int(_ix)] = _raw if isinstance(_raw, str) else json.dumps(_raw, ensure_ascii=False)

        if is_err:
            err_msg = result.get("error", "") if isinstance(result, dict) else str(result)
            err_msg = _items_bound_note(tool_input, err_msg)   # ★B31-1: 집합 바인딩 사실을 실패에 실어 준다
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
    # 경고 생산자가 넷(repeat 상한·on_error 건너뜀·0행 사유·병렬 분기 실패)이라 한 키에
    # 덮어쓰면 뒤엣것이 앞엣것을 지운다 — 모아서 한 번에 싣는다(B24-1 이 세 번째 생산자를
    # 더하면서 드러났고, 29회차 0행 사유가 네 번째다).
    _warns = []
    if _seq["halted"]:
        out["halted_steps"] = list(_seq["halted"])
        _hs = ", ".join(f"step {h['step']}({h['halted']})" for h in _seq["halted"])
        _warns.append(f"[repeat] 상한으로 중단: {_hs} — 종료 조건은 충족되지 않았습니다"
                      "(성공 아님·실패 아님, 통화는 냄). success 만 보고 '조건 달성'으로 읽지 말 것.")
    if _seq["skipped"]:
        out["skipped_steps"] = list(_seq["skipped"])
        _warns.append(f"[on_error] 로 step {', '.join(map(str, _seq['skipped']))} 실패를 건너뛰었습니다 — "
                      "결과는 부분입니다(results[] 의 skipped 표지·error 참조).")
    if _seq["empty_notes"]:
        out["empty_notes"] = list(_seq["empty_notes"])
        _es = " / ".join(f"step {e['step']}[{e['action']}] {e['note']}" for e in _seq["empty_notes"])
        _warns.append(f"[0행 사유] {_es} — 0건이 '없다'는 뜻이 아닐 수 있습니다(중간 step 의 신고).")
    if _seq["branches_failed"]:
        out["branches_failed"] = list(_seq["branches_failed"])
        _bs = ", ".join(f"step {b['step']}({len(b['failed'])}/{b['of']} 분기)" for b in _seq["branches_failed"])
        _warns.append(f"[병렬] 분기 실패: {_bs} — 결과는 부분입니다"
                      "(살아남은 분기만 다음 step 으로 흐릅니다. results[] 의 branches_failed 참조).")
    if _seq["branch_honesty"]:
        # ★B48-2: 가지가 죽지 않았어도 가지 *안*에서 부분 실패가 있었다는 사실.
        #   이게 없으면 "3곳 다 조회했다"가 실제로는 "3곳 중 2곳"이다.
        out["branches_honesty"] = list(_seq["branch_honesty"])
        _bh = ", ".join(
            "step {}({}/{} 분기: {})".format(
                b["step"], len(b["branches"]), b["of"],
                ", ".join(sorted({k for br in b["branches"] for k in br["markers"]})))
            for b in _seq["branch_honesty"])
        _warns.append(f"[병렬] 살아남은 분기 안에 부분 실패·경로 변경 신고가 있습니다: {_bh} — "
                      "분기가 success 로 돌아왔다고 그 안이 온전한 것은 아닙니다"
                      "(results[] 의 branches_honesty 참조).")
    if _seq["fallback_used"]:
        # ★F35-1: `??` 가 갈아탄 사실 — 데이터의 **출처가 바뀌었다**는 뜻이라
        #   최상위에 없으면 읽는 쪽이 첫 가지 결과로 착각한다(교재의 정직 표지 1번).
        out["_fallback_used"] = list(_seq["fallback_used"])
        _fs = ", ".join(f"step {f['step']}({f['action']}, {f['attempt']}번째 가지)"
                        for f in _seq["fallback_used"])
        _warns.append(f"폴백 발동: {_fs} — 앞 가지를 버리고 갈아탔으므로 **데이터의 출처가 "
                      f"다릅니다**(건너뛴 가지는 results[] 의 attempts 참조).")
    if _seq["list_in_text"]:
        out["list_in_text"] = list(_seq["list_in_text"])
        _warns.append(_list_in_text_warning(_seq["list_in_text"]))
    # ★F48-7 (48회차 상상훈련, 수리 2026-08-27): **표지의 승격 규칙을 한 벌로.**
    #   종전엔 파이프 표지(_fallback_used·skipped_steps·halted…)만 최상위로 오르고,
    #   마지막 step 이 낸 표지(error_count·errors·rows_replaced·passthrough_rows·rows_in·
    #   truncated…)는 `final_result` **JSON 문자열** 안에만 살았다. 교재는 "보고 전에 이
    #   키들을 확인하라"고 한 줄로 가르치는데 읽는 쪽은 두 규칙을 동시에 외워야 했다
    #   (48회차 운용 실측: 이 턴의 계측기가 그걸 놓쳐 두 번 오독했다).
    #   이제 통화 안의 표지도 봉투 최상위로 올린다 — 걷는 쪽은 `HONESTY_KEYS` 한 벌
    #   (markers_of)이라 표지를 늘려도 승격이 자동으로 따라온다.
    #   ★통화(final_result)는 건드리지 않는다 — 복사만 한다(하류 계약 불변).
    _promoted = _honesty_markers_of(prev_result)
    _new = [k for k in _promoted if k not in out]
    for _k in _new:
        out[_k] = _promoted[_k]
    if _new:
        _warns.append("마지막 통화가 부분 실패·절단을 신고했습니다(" + ", ".join(sorted(_new)) +
                      ") — success 만 보고 '다 됐다'로 읽지 말 것.")
    if _warns:
        out["warning"] = " / ".join(_warns)
    return out


# 병렬 실행 브랜치별 타임아웃 (초)
# 병렬(&) 분기 실행기는 형제 모듈로 분리 (2026-08-19, 1500줄 규칙 — G13-1 괄호 분기
# 파이프 추가로 초과). 재수출로 기존 import 경로 불변.
from workflow_parallel import PARALLEL_BRANCH_TIMEOUT, _execute_parallel  # noqa: F401


# 폴백(??) 실행기는 형제 모듈 workflow_fallback.py 로 분리 (2026-08-22, 1500줄 규칙 — M3 괄호 가지 추가로 초과).
from workflow_fallback import _execute_fallback  # noqa: E402,F401


# 변수·통화 바인딩 헬퍼는 형제 모듈 workflow_binding.py 로 분리 (2026-08-22, 1500줄 규칙 —
# 병렬 실패 신고(branches_failed) 추가로 초과). 재수출이라 기존 import 경로는 그대로.
from workflow_binding import (  # noqa: E402,F401
    _STEP_RESULT_RE, _ITEMS_REF,
    _extract_result_field, _v4_var_payload, _inject_step_results,
    _bind_items_params, _items_bound_note, _list_in_text_warning, _mark_list_in_text,
    _is_json_list, _inject_prev_result, _has_prev_ref, _auto_inject_prev,
    _to_prev_currency, _step_label, _to_string,
)


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
        steps = data.get("steps") or data.get("do") or data.get("pipeline") or []
        # ★B1 동형: steps 가 문자열(저장 원문)이면 len()이 글자 수가 된다 — 목록에서
        # "스텝 121개"로 보이는 오표시 방지. 문장 하나 = 스텝 하나로 센다.
        if isinstance(steps, str):
            steps = [steps] if steps.strip() else []
        raw_steps = data.get("steps") or data.get("do") or []
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
        # 시그니처 — 목록에서 "이 워크플로우가 무엇을 요구하는지"가 보여야 부를 수 있다.
        sig = data.get("params_required")
        if not isinstance(sig, list):
            sig = _signature_of(data.get("steps") or data.get("do") or data.get("pipeline"))
        if sig:
            entry["params_required"] = sig
        if isinstance(data.get("params_default"), dict) and data["params_default"]:
            entry["params_default"] = data["params_default"]
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
    except Exception as e:
        # ★파일이 있는데 못 읽은 것을 None(=없음)으로 눙치지 않는다 — 바로 위
        # list_workflows 가 이미 세운 계약과 같은 어휘로 신고한다(2026-08-22).
        return {"id": workflow_id, "name": workflow_id, "runnable": False,
                "problem": f"워크플로 파일을 읽을 수 없습니다: {e}"}
    if not isinstance(data, dict):
        return {"id": workflow_id, "name": workflow_id, "runnable": False,
                "problem": f"워크플로 파일이 매핑이 아닙니다(빈 파일?): {type(data).__name__}"}
    data["id"] = workflow_id
    return data


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
                     params: Optional[dict] = None,
                     stack: Optional[list] = None) -> dict:
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
    if wf.get("problem"):
        return {"success": False, "error": wf["problem"]}

    # 몸통 키는 save 관문(_SENTENCE_KEYS)과 **같은 집합**을 읽는다. 예전엔 save 는 do 를
    # 몸통으로 받아 그대로 저장하는데 run 은 steps/pipeline 만 봐서, IBL 표면(별칭 do→steps)이
    # 아닌 직접 호출로 저장한 do 워크플로우가 "저장 성공 → 실행 시 steps 없음" 으로 죽었다.
    steps = wf.get("steps") or wf.get("do") or []

    # Phase 15: pipeline 문자열 지원 — steps가 없으면 pipeline 필드를 IBL 파서로 변환
    if not steps and wf.get("pipeline"):
        from ibl_parser import parse as ibl_parse, IBLSyntaxError
        try:
            steps = ibl_parse(wf["pipeline"])
        except IBLSyntaxError as e:
            return {"success": False, "error": f"워크플로우 pipeline 문법 오류: {str(e)}"}

    if not steps:
        return {"success": False,
                "error": f"워크플로우 '{workflow_id}' 에 몸통이 없습니다 "
                         f"(do/steps/pipeline 중 하나가 필요). 저장된 키: "
                         f"{sorted(k for k in wf if not str(k).startswith('_'))}"}

    wf_name = wf.get("name", workflow_id)

    # 호출 스택 — 자기 자신을 (직접·간접으로) 부르는 워크플로우를 몸통 실행 전에 끊는다.
    stack, _serr = _wf_push(stack, workflow_id)
    if _serr:
        return {"success": False, "workflow_id": workflow_id,
                "workflow_name": wf_name, "error": _serr}

    # 스탬프·시그니처 판정 둘 다 dict step 을 요구한다 — 주입 여부와 무관하게 정규화.
    steps, _perr = _normalize_steps_for_injection(steps)
    if _perr:
        return {"success": False, "error": f"워크플로우 문법 오류: {_perr}"}

    # === 시그니처 검사 (2026-08-22) ===
    # 저장된 워크플로우에는 "선언하는 순간"(save)이 있으므로 인자 누락을 정직하게 거절한다.
    # 전엔 미할당 $이름이 리터럴로 흘러 "$city 맛집" 이 그대로 검색어가 되고도 success 였다.
    required = _free_vars(steps)
    defaults = wf.get("params_default")
    defaults = defaults if isinstance(defaults, dict) else {}
    effective = {**defaults, **(params or {})}
    missing = [n for n in required if n not in effective]
    if missing:
        example = ", ".join(f'"{n}": "값"' for n in missing)
        return {"success": False, "workflow_id": workflow_id, "workflow_name": wf_name,
                "params_required": required,
                "params_missing": missing,
                "error": (f"워크플로우 '{wf_name}' 인자 누락: "
                          f"{', '.join('$' + n for n in missing)}. "
                          f"이 워크플로우의 시그니처는 "
                          f"{', '.join('$' + n for n in required)} 입니다 — params 로 채우세요. "
                          f'예: [self:workflow]{{op: "run", workflow_id: "{workflow_id}", '
                          f'params: {{{example}}}}}'
                          + (" (기본값을 주려면 저장본에 params_default 를 두세요.)"
                             if not defaults else ""))}

    inject_meta = None
    if effective:
        steps, inject_meta = _apply_caller_params(steps, effective)

    _stamp_wf_stack(steps, stack)
    result = execute_pipeline(steps, project_path)
    result["workflow_id"] = workflow_id
    result["workflow_name"] = wf_name
    if required:
        result["params_required"] = required
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
            and action in ("detail", "get", "get_workflow", "run", "delete", "delete_workflow")
            and (params.get("name") or params.get("id"))):
        workflow_id = _resolve_workflow_id(params.get("name") or params.get("id"))

    if action in ("list", "list_workflows"):
        # 원장은 자기 list 를 통화로 낸다 (16회차 V16-2 원칙 — trigger·script·webapp·
        # notebook·goal·material 은 이미 items 병기). workflow 만 빠져 있어
        # `[self:workflow]{op:"list"} >> [table:filter] >> [table:each]`(저장해 둔 절차 중
        # 조건 맞는 것만 돌려라)가 표현 불가였다(V18-1). `items` 는 `workflows` 와 같은
        # 객체로 둔다 — 변환자의 거울 키 판정(동일성)이 둘을 함께 변환한다.
        wfs = list_workflows()
        return {"workflows": wfs, "items": wfs, "count": len(wfs)}

    elif action in ("detail", "get", "get_workflow"):   # detail=정본(2026-08-24 #repair B5), get=구어휘 수용
        if not workflow_id:
            return {"error": "workflow_id가 필요합니다."}
        wf = get_workflow(workflow_id)
        if not wf:
            return {"error": f"워크플로우를 찾을 수 없습니다: {workflow_id}"}
        if wf.get("problem"):
            return {"error": wf["problem"]}
        return wf

    elif action == "run":
        # 호출자 params({변수: 값}) — 문장 안 미할당 $변수에 주입. desc 선언대로
        # 저장본·즉석 양 경로 동일 지원 (2026-08-17 B8 수리 — 전엔 침묵 유실).
        caller, _perr = coerce_caller_params(params.get("params"))
        if _perr:
            return {"error": _perr}
        # 호출 스택 — ibl_engine 이 tool_input._wf_stack 을 params 로 내려 준다(재귀 가드).
        _stack = params.get("_wf_stack")
        # 즉석 실행 (2026-08-05, 구 [self:run_pipeline] 흡수 — 변형=op 명명 헌법):
        # workflow_id 없이 steps/pipeline 이 오면 저장 없이 바로 실행.
        if not workflow_id and (params.get("steps") or params.get("pipeline")):
            return _run_inline(params, project_path, caller_params=caller, stack=_stack)
        if not workflow_id:
            return {"error": "workflow_id(저장본) 또는 steps/pipeline(즉석 실행)이 필요합니다.",
                    "available": [w["id"] for w in list_workflows()]}
        return execute_workflow(workflow_id, project_path, params=caller, stack=_stack)

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
        # 시그니처 = 몸통의 자유 변수. 저장해 두면 list/get 이 "이 워크플로우가 무엇을
        # 요구하는지" 를 보여주고, run 은 실행 시점에 다시 계산해 판정한다(손 편집 대비).
        signature = _signature_of(params[body_key])
        declared_default = wf_data.get("params_default")
        declared_default = declared_default if isinstance(declared_default, dict) else {}
        if signature:
            wf_data["params_required"] = signature
        else:
            wf_data.pop("params_required", None)
        wf_id = save_workflow(wf_data)
        out = {"success": True, "workflow_id": wf_id,
               "message": f"워크플로우 '{wf_id}' 저장 완료"}
        if signature:
            out["params_required"] = signature
            need = [n for n in signature if n not in declared_default]
            out["message"] += (
                f" — 인자 {', '.join('$' + n for n in signature)} 를 받습니다"
                + (f'. 실행: [self:workflow]{{op: "run", workflow_id: "{wf_id}", '
                   f'params: {{{", ".join(chr(34) + n + chr(34) + ": 값" for n in need)}}}}}'
                   if need else " (전부 params_default 로 채워져 있습니다)"))
        return out

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
        caller, _perr = coerce_caller_params(params.get("params"))
        if _perr:
            return {"error": _perr}
        return _run_inline(params, project_path, caller_params=caller,
                           stack=params.get("_wf_stack"))

    return {"error": f"알 수 없는 워크플로우 액션: {action}", "available_actions": ["run", "list", "get", "save", "delete", "run_pipeline"]}


# === 워크플로우 호출 계약 — 재귀·순환 가드 + 시그니처 (2026-08-22) ===
# 본체는 workflow_contract.py (1500줄 규칙). 이름은 여기서도 그대로 쓰인다.
from workflow_contract import (  # noqa: E402,F401
    MAX_WORKFLOW_DEPTH, _INLINE_FRAME, _wf_push, _stamp_wf_stack,
    _free_vars, _signature_of,
)


def _run_inline(params: dict, project_path: str,
                caller_params: Optional[dict] = None,
                stack: Optional[list] = None) -> Any:
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

    # 호출 스택 판정 먼저 — 몸통을 파싱하기 전에 순환을 끊는다.
    stack, _serr = _wf_push(stack if stack is not None else params.get("_wf_stack"),
                            _INLINE_FRAME)
    if _serr:
        return {"success": False, "error": _serr}

    # 스탬프는 dict step 에만 찍힌다 — 문자열 step 이 남아 있으면 가드에 구멍이 난다.
    # 그래서 주입 여부와 무관하게 여기서 한 번 정규화한다(execute_pipeline 입구 정규화와
    # 같은 규칙이라 무회귀).
    steps, _perr = _normalize_steps_for_injection(steps)
    if _perr:
        return {"error": _perr}

    inject_meta = None
    if caller_params:
        steps, inject_meta = _apply_caller_params(steps, caller_params)

    # 즉석 실행은 "선언하는 순간"이 없어 저장본처럼 거절하지 않는다 — 대신 채워지지 않은
    # 자유 변수를 정직하게 알린다(전엔 리터럴 `$이름` 이 그대로 하류로 흘러 침묵했다).
    _unfilled = _free_vars(steps)
    if _unfilled:
        _msg = (f"문장 안 {', '.join('$' + n for n in _unfilled)} 에 값이 주입되지 않아 "
                f"리터럴로 흘러갑니다 — params 로 채우거나 이름을 확인하세요.")
        inject_meta = dict(inject_meta or {})
        inject_meta["params_warning"] = (
            (inject_meta.get("params_warning", "") + " " + _msg).strip())

    _stamp_wf_stack(steps, stack)
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


# 호출자 params 주입기도 workflow_contract 로 이관(2026-08-22) — 시그니처와 같은 계약.
from workflow_contract import (  # noqa: E402,F401
    _CALLER_VAR_RESERVED, coerce_caller_params, _normalize_steps_for_injection,
    _reserved_row_names, _apply_caller_params,
)


# === 유틸리티 ===

def _slugify(text: str) -> str:
    """텍스트를 파일명에 적합한 slug로 변환"""
    # 한글은 유지, 특수문자 제거
    slug = re.sub(r'[^\w가-힣\s-]', '', text)
    slug = re.sub(r'[\s]+', '_', slug).strip('_')
    return slug or "workflow"
