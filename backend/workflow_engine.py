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
from typing import Any, Dict, List, Optional


# === 경로 ===

def _get_workflows_path() -> Path:
    """워크플로우 저장 디렉토리"""
    env_path = os.environ.get("INDIEBIZ_BASE_PATH")
    if env_path:
        base = Path(env_path)
    else:
        base = Path(__file__).parent.parent
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

    _seq = {"skip_until": -1, "failed": 0}

    def _handle_failure(idx: int, abort_payload: dict):
        """실패 처리. 뒤에 독립 문장이 있으면 거기로 건너뛰고 계속(None 반환),
        없으면 기존대로 중단할 payload 를 돌려준다."""
        b = _next_boundary(idx + 1)
        if b < 0:
            return abort_payload
        _seq["skip_until"] = b
        _seq["failed"] += 1
        return None

    for i, step in enumerate(steps):
        if i < _seq["skip_until"]:
            continue  # 실패한 문장의 남은 step — 건너뛴다(다음 문장 경계까지)
        if isinstance(step, dict) and step.get("_seq_boundary"):
            # 문장 경계 — 앞 문장이 성공했어도 결과를 넘기지 않는다(독립).
            # 실패 경로는 각 _handle_failure 뒤에서 리셋하지만, 성공 경로는 여기가 유일한 관문
            # (없으면 _auto_inject_prev 가 앞 문장 결과를 다음 문장 첫 step 에 무조건 주입한다).
            prev_result = ""
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
                prev_result = ""
                continue

            duration_ms = int((time.time() - step_start) * 1000)
            result_str = _to_string(result)

            action_count += len(step["branches"])
            results.append({
                "step": i + 1, "type": "parallel",
                "branches": len(step["branches"]),
                "result": result_str,
                "duration_ms": duration_ms,
            })
            prev_result = result_str

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
                prev_result = ""
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

            if is_err:
                _abort = _handle_failure(i, {
                    "success": False, "steps_completed": i, "steps_total": total,
                    "results": results, "final_result": result,
                    "error": f"Step {i+1} fallback 체인 전체 실패",
                })
                if _abort is not None:
                    return _abort
                prev_result = ""
                continue

            prev_result = result_str
            continue

        # 일반 step (기존 로직)
        tool_input = dict(step)
        if "node" in tool_input and "_node" not in tool_input:
            tool_input["_node"] = tool_input.pop("node")

        # {{_prev_result}} 템플릿 치환
        tool_input = _inject_prev_result(tool_input, prev_result)

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
                "node": tool_input.get("_node", "?"),
                "action": tool_input.get("action", "?"),
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
            prev_result = ""
            continue

        duration_ms = int((time.time() - step_start) * 1000)

        # 결과를 문자열로 변환 (다음 step 주입용)
        result_str = _to_string(result)

        # 에러 확인 (단일 소스)
        is_err = _is_error_result(result)

        action_count += 1
        results.append({
            "step": i + 1,
            "node": tool_input.get("_node", "?"),
            "action": tool_input.get("action", "?"),
            "result": result_str,
            "duration_ms": duration_ms,
        })

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
            prev_result = ""
            continue

        # 다음 step으로 전달
        prev_result = result_str

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
    return out


# 병렬 실행 브랜치별 타임아웃 (초)
PARALLEL_BRANCH_TIMEOUT = 90


def _execute_parallel(branches: list, project_path: str, prev_result: str, raw: bool = False) -> list:
    """
    병렬 실행 - 여러 IBL 액션을 동시에 실행 (Phase 9)
    각 브랜치에 타임아웃 적용 — 한 브랜치가 멈춰도 전체가 멈추지 않음.

    Args:
        branches: 병렬로 실행할 step 리스트
        project_path: 프로젝트 경로
        prev_result: 이전 step 결과 (모든 branch에 동일하게 주입)
        raw: 병렬 step이 >> 파이프 중간단계일 때 True — 각 분기에 _raw 주입해
             postprocess:compress가 분기의 구조화 통화(records/table)를 죽이지 않게.
             ([A] & [B] >> [table:join/union/merge] 같은 이항 변환자가 분기 통화를 소비)

    Returns:
        각 branch 결과를 리스트로 합침
    """
    from ibl_engine import execute_ibl
    from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError

    # 부모 스레드의 thread_context를 캡처 (자식 스레드에 전파하기 위함)
    from thread_context import (
        get_current_task_id, set_current_task_id,
        get_current_agent_id, set_current_agent_id,
        get_current_agent_name, set_current_agent_name,
        get_current_project_id, set_current_project_id,
        get_allowed_nodes, set_allowed_nodes,
    )
    _parent_task_id = get_current_task_id()
    _parent_agent_id = get_current_agent_id()
    _parent_agent_name = get_current_agent_name()
    _parent_project_id = get_current_project_id()
    _parent_allowed_nodes = get_allowed_nodes()

    def _run_branch(branch):
        # 부모 스레드의 thread_context를 자식 스레드에 복원
        if _parent_task_id:
            set_current_task_id(_parent_task_id)
        if _parent_agent_id:
            set_current_agent_id(_parent_agent_id)
        if _parent_agent_name:
            set_current_agent_name(_parent_agent_name)
        if _parent_project_id:
            set_current_project_id(_parent_project_id)
        if _parent_allowed_nodes is not None:
            set_allowed_nodes(_parent_allowed_nodes)

        tool_input = dict(branch)
        if "node" in tool_input and "_node" not in tool_input:
            tool_input["_node"] = tool_input.pop("node")
        tool_input = _inject_prev_result(tool_input, prev_result)
        tool_input = _auto_inject_prev(tool_input, prev_result)
        if raw:  # 병렬 step이 중간단계 — 분기 통화를 다음 변환자가 소비하므로 압축 금지
            _p = tool_input.get("params")
            if not isinstance(_p, dict):
                _p = {}
                tool_input["params"] = _p
            _p["_raw"] = True
        try:
            return execute_ibl(tool_input, project_path)
        except Exception as e:
            return {"error": str(e), "_node": tool_input.get("_node", "?"),
                    "action": tool_input.get("action", "?")}

    # ThreadPoolExecutor로 동시 실행 (타임아웃 적용)
    branch_results = [None] * len(branches)
    with ThreadPoolExecutor(max_workers=min(len(branches), 8)) as executor:
        future_to_idx = {
            executor.submit(_run_branch, branch): idx
            for idx, branch in enumerate(branches)
        }
        for future in as_completed(future_to_idx, timeout=PARALLEL_BRANCH_TIMEOUT):
            idx = future_to_idx[future]
            try:
                branch_results[idx] = future.result(timeout=PARALLEL_BRANCH_TIMEOUT)
            except FuturesTimeoutError:
                node = branches[idx].get("node", branches[idx].get("_node", "?"))
                action = branches[idx].get("action", "?")
                print(f"[IBL] 병렬 브랜치 타임아웃: [{node}:{action}] ({PARALLEL_BRANCH_TIMEOUT}초)")
                branch_results[idx] = {
                    "error": f"실행 시간 초과 ({PARALLEL_BRANCH_TIMEOUT}초): [{node}:{action}]. 다른 방법을 시도하세요."
                }
            except Exception as e:
                branch_results[idx] = {"error": str(e)}

    # as_completed 자체가 타임아웃된 경우 미완료 브랜치 처리
    for idx, result in enumerate(branch_results):
        if result is None:
            node = branches[idx].get("node", branches[idx].get("_node", "?"))
            action = branches[idx].get("action", "?")
            branch_results[idx] = {
                "error": f"실행 시간 초과 ({PARALLEL_BRANCH_TIMEOUT}초): [{node}:{action}]. 다른 방법을 시도하세요."
            }

    return branch_results


def _execute_fallback(chain: list, project_path: str, prev_result: str,
                      agent_id: str = None) -> tuple:
    """
    Fallback 실행 - 첫 번째 성공하는 액션까지 순차 시도 (Phase 9)

    Args:
        chain: 순서대로 시도할 step 리스트
        project_path: 프로젝트 경로
        prev_result: 이전 step 결과
        agent_id: 호출자 신원 — 일반 step 과 같게 전파(빠지면 NameError 로 ?? 가 통째로 죽는다)

    Returns:
        (result, log) - 성공한 결과 또는 마지막 에러, 시도 로그
    """
    from ibl_engine import execute_ibl

    log = []
    last_result = None

    for idx, step in enumerate(chain):
        tool_input = dict(step)
        if "node" in tool_input and "_node" not in tool_input:
            tool_input["_node"] = tool_input.pop("node")
        tool_input = _inject_prev_result(tool_input, prev_result)
        tool_input = _auto_inject_prev(tool_input, prev_result)

        start = time.time()
        try:
            result = execute_ibl(tool_input, project_path, agent_id=agent_id)
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            log.append({
                "attempt": idx + 1,
                "node": tool_input.get("_node", "?"),
                "action": tool_input.get("action", "?"),
                "status": "exception",
                "error": str(e),
                "duration_ms": duration_ms,
            })
            last_result = {"error": str(e)}
            continue

        duration_ms = int((time.time() - start) * 1000)

        # 에러 확인 — `>>` 와 **같은 함수**를 쓴다(갈라지면 폴백이 문자열 에러를 성공으로 센다)
        is_err = _is_error_result(result)
        log.append({
            "attempt": idx + 1,
            "node": tool_input.get("_node", "?"),
            "action": tool_input.get("action", "?"),
            "status": "error" if is_err else "ok",
            "duration_ms": duration_ms,
        })

        if not is_err:
            # 성공! 즉시 반환
            return result, log

        last_result = result

    # 모든 체인 실패
    if last_result is None:
        last_result = {"error": "fallback 체인이 비어있습니다."}
    if not isinstance(last_result, dict):
        # 문자열 에러("Error: …")는 `_all_failed` 표식을 달 수 없어 호출부가 성공으로 세어 버린다
        # → 전체 실패 경로에서만 error dict 로 감싼다(성공 결과는 원형 그대로 반환되므로 무영향).
        last_result = {"error": str(last_result)}
    last_result["_all_failed"] = True
    return last_result, log


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

def list_workflows() -> List[Dict]:
    """저장된 워크플로우 목록"""
    wf_path = _get_workflows_path()
    workflows = []
    for f in sorted(wf_path.glob("*.yaml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
            workflows.append({
                "id": f.stem,
                "name": data.get("name", f.stem),
                "description": data.get("description", ""),
                "steps_count": len(data.get("steps", [])),
                "file": str(f),
            })
        except Exception:
            pass
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


def execute_workflow(workflow_id: str, project_path: str = ".") -> dict:
    """
    저장된 워크플로우 실행

    Args:
        workflow_id: 워크플로우 ID (파일명)
        project_path: 프로젝트 경로

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

    result = execute_pipeline(steps, project_path)
    result["workflow_id"] = workflow_id
    result["workflow_name"] = wf.get("name", workflow_id)
    return result


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
        if not workflow_id:
            return {"error": "workflow_id가 필요합니다.", "available": [w["id"] for w in list_workflows()]}
        return execute_workflow(workflow_id, project_path)

    elif action in ("save", "save_workflow"):
        if not params:
            return {"error": "워크플로우 정의(params)가 필요합니다."}
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
        # IBL 파이프라인 모드: pipeline 파라미터가 있으면 파서로 파싱
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
            return {"error": "params.steps 또는 params.code가 필요합니다."}
        return execute_pipeline(steps, project_path)

    return {"error": f"알 수 없는 워크플로우 액션: {action}", "available_actions": ["run", "list", "get", "save", "delete", "run_pipeline"]}


# === 유틸리티 ===

def _slugify(text: str) -> str:
    """텍스트를 파일명에 적합한 slug로 변환"""
    # 한글은 유지, 특수문자 제거
    slug = re.sub(r'[^\w가-힣\s-]', '', text)
    slug = re.sub(r'[\s]+', '_', slug).strip('_')
    return slug or "workflow"
