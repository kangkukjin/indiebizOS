# -*- coding: utf-8 -*-
"""병렬(&) 분기 실행기 — workflow_engine 의 형제 모듈.

2026-08-19 분리(1500줄 규칙): G13-1 괄호 분기 파이프 추가로 본체가 1532줄이 되어
`_execute_parallel` 를 여기로 옮김. 이음매 헬퍼(_inject_prev_result 등)는 본체 소유라
호출 시점에 지연 import 한다(본체가 이 모듈을 top-level import 하므로 — 순환 회피).
"""

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
    from workflow_engine import (_inject_prev_result, _auto_inject_prev,
                                 _is_error_result, _to_prev_currency)

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

        # 괄호 분기 파이프 (G13-1, 2026-08-19 상상훈련 13회차): (A >> B >> C) —
        # 분기 안을 순차 실행해 마지막 결과를 이 분기의 출력으로 낸다. 분기별
        # 전처리(교차 소스 rename 등)의 표현력. 중간 이음매는 항상 _raw(통화 보존).
        if isinstance(branch, dict) and branch.get("_branch_steps"):
            subs = branch["_branch_steps"]
            sub_prev = prev_result
            last = None
            for j, sub in enumerate(subs):
                ti = dict(sub)
                if "node" in ti and "_node" not in ti:
                    ti["_node"] = ti.pop("node")
                ti = _inject_prev_result(ti, sub_prev)
                ti = _auto_inject_prev(ti, sub_prev)
                if raw or j < len(subs) - 1:
                    _p = ti.get("params")
                    if not isinstance(_p, dict):
                        _p = {}
                        ti["params"] = _p
                    _p["_raw"] = True
                try:
                    last = execute_ibl(ti, project_path)
                except Exception as e:
                    return {"error": f"괄호 분기 {j + 1}/{len(subs)} 단계 실패: {e}",
                            "_node": ti.get("_node", "?"), "action": ti.get("action", "?")}
                # 단계 실패 위에 다음 단계를 쌓지 않는다 — 실패 위 파이프는 거짓 (정직 전파)
                if _is_error_result(last):
                    _fail = last if isinstance(last, dict) else {"error": str(last)[:400]}
                    return {**_fail,
                            "_branch_step_failed": f"{j + 1}/{len(subs)}",
                            "_node": ti.get("_node", "?"), "action": ti.get("action", "?")}
                sub_prev = _to_prev_currency(last)
            return last

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
