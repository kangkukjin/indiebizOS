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


# === 파이프라인 실행 ===

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

    prev_result = context.get("_prev_result", "") if context else ""
    results = []
    total = len(steps)
    action_count = 0  # 실제 실행된 액션 수 (병렬 branches 포함)

    for i, step in enumerate(steps):
        step_start = time.time()

        # Phase 9: 특수 노드 처리 (병렬, fallback)
        if step.get("_parallel"):
            # 병렬 실행
            try:
                result = _execute_parallel(step["branches"], project_path, prev_result)
            except Exception as e:
                results.append({
                    "step": i + 1, "type": "parallel",
                    "error": str(e),
                    "duration_ms": int((time.time() - step_start) * 1000),
                })
                return {
                    "success": False, "steps_completed": i, "steps_total": total,
                    "results": results, "final_result": None,
                    "error": f"Step {i+1} 병렬 실행 예외: {str(e)}",
                }

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
                result, fallback_log = _execute_fallback(step["_fallback_chain"], project_path, prev_result)
            except Exception as e:
                results.append({
                    "step": i + 1, "type": "fallback",
                    "error": str(e),
                    "duration_ms": int((time.time() - step_start) * 1000),
                })
                return {
                    "success": False, "steps_completed": i, "steps_total": total,
                    "results": results, "final_result": None,
                    "error": f"Step {i+1} fallback 실행 예외: {str(e)}",
                }

            duration_ms = int((time.time() - step_start) * 1000)
            result_str = _to_string(result)

            # fallback 결과에 에러가 있으면 (모든 체인 실패)
            is_err = isinstance(result, dict) and "error" in result and result.get("_all_failed")
            action_count += 1
            results.append({
                "step": i + 1, "type": "fallback",
                "chain_length": len(step["_fallback_chain"]),
                "attempts": fallback_log,
                "result": result_str,
                "duration_ms": duration_ms,
            })

            if is_err:
                return {
                    "success": False, "steps_completed": i, "steps_total": total,
                    "results": results, "final_result": result,
                    "error": f"Step {i+1} fallback 체인 전체 실패",
                }

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
            return {
                "success": False,
                "steps_completed": i,
                "steps_total": total,
                "results": results,
                "final_result": None,
                "error": f"Step {i+1} 실행 중 예외: {str(e)}",
            }

        duration_ms = int((time.time() - step_start) * 1000)

        # 결과를 문자열로 변환 (다음 step 주입용)
        result_str = _to_string(result)

        # 에러 확인
        is_err = False
        if isinstance(result, dict):
            if "error" in result and result.get("status") != "not_implemented":
                is_err = True
        elif isinstance(result, str) and result.startswith("Error:"):
            is_err = True

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
            return {
                "success": False,
                "steps_completed": i,
                "steps_total": total,
                "results": results,
                "final_result": result,
                "error": f"Step {i+1} 에러: {err_msg}",
            }

        # 다음 step으로 전달
        prev_result = result_str

    return {
        "success": True,
        "steps_completed": total,
        "steps_total": total,
        "_action_count": action_count,
        "results": results,
        "final_result": prev_result,
    }


# 병렬 실행 브랜치별 타임아웃 (초)
PARALLEL_BRANCH_TIMEOUT = 90


def _execute_parallel(branches: list, project_path: str, prev_result: str) -> list:
    """
    병렬 실행 - 여러 IBL 액션을 동시에 실행 (Phase 9)
    각 브랜치에 타임아웃 적용 — 한 브랜치가 멈춰도 전체가 멈추지 않음.

    Args:
        branches: 병렬로 실행할 step 리스트
        project_path: 프로젝트 경로
        prev_result: 이전 step 결과 (모든 branch에 동일하게 주입)

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


def _execute_fallback(chain: list, project_path: str, prev_result: str) -> tuple:
    """
    Fallback 실행 - 첫 번째 성공하는 액션까지 순차 시도 (Phase 9)

    Args:
        chain: 순서대로 시도할 step 리스트
        project_path: 프로젝트 경로
        prev_result: 이전 step 결과

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

        # 에러 확인
        is_err = isinstance(result, dict) and "error" in result and result.get("status") != "not_implemented"
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
    if isinstance(last_result, dict):
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
    """결과를 문자열로 변환"""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
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
    workflow_id = params.get("workflow_id", "")

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
