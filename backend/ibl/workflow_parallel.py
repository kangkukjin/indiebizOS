# -*- coding: utf-8 -*-
"""병렬(&) 분기 실행기 — workflow_engine 의 형제 모듈.

2026-08-19 분리(1500줄 규칙): G13-1 괄호 분기 파이프 추가로 본체가 1532줄이 되어
`_execute_parallel` 를 여기로 옮김. 이음매 헬퍼(_inject_prev_result 등)는 workflow_binding.py 소유·본체 재수출이라
호출 시점에 지연 import 한다(본체가 이 모듈을 top-level import 하므로 — 순환 회피).
"""

PARALLEL_MAX_WORKERS = 8
PARALLEL_TIMEOUT_GRACE = 5.0


def _action_timeout_budget() -> float:
    """병렬층 한 step 의 예산 — 실제 라우터 한도의 관찰자이지 별도 정책이 아니다.

    옛 90초 상수는 하위 액션의 정상 실행 한도(sync 300초·async 60초)보다 먼저 호출을
    잘랐다. 병렬층은 멈춘 워커를 수습하는 바깥 안전망만 맡고, 액션 한도보다 먼저
    판정하지 않는다. async 경로의 future.result 는 5초 여유를 이미 쓴다.
    """
    from ibl_routing import SYNC_TOOL_EXECUTION_TIMEOUT, TOOL_EXECUTION_TIMEOUT
    return float(max(SYNC_TOOL_EXECUTION_TIMEOUT, TOOL_EXECUTION_TIMEOUT + 5))


def _branch_step_count(branch: dict) -> int:
    steps = branch.get("_branch_steps") if isinstance(branch, dict) else None
    return max(1, len(steps) if isinstance(steps, list) else 1)


def _branch_budget(branch: dict) -> float:
    """괄호 파이프는 각 step 이 자기 라우터 한도를 온전히 쓸 수 있게 합산한다."""
    return _action_timeout_budget() * _branch_step_count(branch) + PARALLEL_TIMEOUT_GRACE


def _execute_parallel(branches: list, project_path: str, prev_result: str, raw: bool = False,
                      var_values: dict = None) -> list:
    """
    병렬 실행 - 여러 IBL 액션을 동시에 실행 (Phase 9).

    최대 8개씩 실행하되 시간 예산은 제출 시점이 아니라 각 워커의 실제 시작 시점부터
    흐른다. 괄호 분기 파이프는 step 수만큼 액션 예산을 합산한다. 한 가지가 한도를
    넘으면 그 가지만 현재 하위 step 이름으로 실패하고, 완료된 가지 결과는 보존한다.

    Args:
        branches: 병렬로 실행할 step 리스트
        project_path: 프로젝트 경로
        prev_result: 이전 step 결과 (모든 branch에 동일하게 주입)
        raw: 병렬 step이 >> 파이프 중간단계일 때 True — 각 분기에 _raw 주입해
             postprocess:compress가 분기의 구조화 통화(records/table)를 죽이지 않게.
             ([A] & [B] >> [table:join/union/merge] 같은 이항 변환자가 분기 통화를 소비)
        var_values: 분기가 참조하는 `$변수`의 값 (`$a & $b`, 언어 개정 2026-09-01).
             실행기가 병렬 step 의 _vars 로 해소해 넘긴다 — 여기서 분기 **사본**에만
             싣는다(파싱된 프로그램을 건드리면 두 번째 실행이 옛 값을 본다).

    Returns:
        각 branch 결과를 입력 순서대로 합친 리스트
    """
    from ibl_engine import execute_ibl
    from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
    from workflow_engine import (_inject_prev_result, _auto_inject_prev,
                                 is_error_result, _to_prev_currency)
    import threading
    import time

    # 부모 스레드의 thread_context 를 **통째로** 떠서 자식 스레드에 승계한다.
    #
    # ★손으로 칸을 열거하지 않는다. 옛 코드는 5칸(task_id·agent_id·agent_name·
    #   project_id·allowed_nodes)만 골라 날랐고, 뒤에 추가된 `task_origin`
    #   (= in_rehearsal() 이 읽는 칸)이 그 목록에 없어서 **병렬 가지에서만**
    #   리허설 표식이 사라졌다 — 훈련이 일부러 밟은 실패가 `source='usage'` 로
    #   라이브 건강 원장에 쌓였다(실측 2026-08-23: 훈련 창 44행이 usage 로 기록,
    #   그중 실패 5건). 단일 액션·`??` 폴백·`[table:each]`·`[try]` 는 같은 스레드라
    #   멀쩡했고 병렬만 샜다 — threading.local 은 스레드를 안 건넌다.
    #
    # ★같은 저장소의 다른 스레드 경계 둘은 이미 이 관용을 쓴다:
    #   ibl_engine._run_router_safely · ibl_routing 의 워커(“snapshot/restore 로
    #   워커 스레드에 승계한다”). 이탈은 여기 하나뿐이었으므로 여기로 맞춘다.
    #
    # ★열거 대신 통째 승계인 이유: 열거 목록은 반드시 뒤처진다. 새 컨텍스트 칸이
    #   생길 때마다 이 파일을 고쳐야 하는 구조 자체가 결함의 원인이었다.
    import thread_context as _tc
    _parent_ctx = _tc.snapshot()

    branch_results = [None] * len(branches)
    budgets = [_branch_budget(b) for b in branches]
    states = [
        {"started_at": None, "step": 1, "steps": _branch_step_count(b),
         "node": "?", "action": "?"}
        for b in branches
    ]
    state_lock = threading.Lock()

    def _mark_step(idx: int, step_no: int, steps: int, tool_input: dict) -> None:
        node = tool_input.get("_node") or tool_input.get("node") or "?"
        action = tool_input.get("action") or "?"
        with state_lock:
            state = states[idx]
            if state["started_at"] is None:
                state["started_at"] = time.monotonic()
            state.update({"step": step_no, "steps": steps, "node": node, "action": action})

    def _run_branch(idx: int, branch: dict):
        _tc.restore(_parent_ctx)   # 부모 컨텍스트 승계 (origin 포함 — 열거 없음)

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
                _mark_step(idx, j + 1, len(subs), ti)
                try:
                    last = execute_ibl(ti, project_path)
                except Exception as e:
                    return {"error": f"괄호 분기 {j + 1}/{len(subs)} 단계 실패: {e}",
                            "_node": ti.get("_node", "?"), "action": ti.get("action", "?")}
                # 단계 실패 위에 다음 단계를 쌓지 않는다 — 실패 위 파이프는 거짓 (정직 전파)
                if is_error_result(last):
                    _fail = last if isinstance(last, dict) else {"error": str(last)[:400]}
                    return {**_fail,
                            "_branch_step_failed": f"{j + 1}/{len(subs)}",
                            "_node": ti.get("_node", "?"), "action": ti.get("action", "?")}
                sub_prev = _to_prev_currency(last)
            return last

        tool_input = dict(branch)
        if tool_input.get("_var_emit") and var_values:
            # 변수 분기 — 값은 실행기가 해소해 넘긴 것을 쓴다(분기 사본에만 싣는다).
            tool_input["_var_values"] = {**var_values, **(tool_input.get("_var_values") or {})}
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
        _mark_step(idx, 1, 1, tool_input)
        try:
            return execute_ibl(tool_input, project_path)
        except Exception as e:
            return {"error": str(e), "_node": tool_input.get("_node", "?"),
                    "action": tool_input.get("action", "?")}

    def _timeout_result(idx: int) -> dict:
        with state_lock:
            state = dict(states[idx])
        budget = budgets[idx]
        started = state.get("started_at")
        elapsed = max(0.0, time.monotonic() - started) if started is not None else 0.0
        node, action = state.get("node", "?"), state.get("action", "?")
        budget_s, elapsed_s = round(budget, 3), round(elapsed, 3)
        print(f"[IBL] 병렬 가지 시간 예산 소진: [{node}:{action}] "
              f"({elapsed_s:g}/{budget_s:g}초)")
        out = {
            "success": False,
            "error": (f"병렬 가지 실행 시간 초과 — 시간 예산 소진 "
                      f"({elapsed_s:g}/{budget_s:g}초): [{node}:{action}]. "
                      "다른 방법을 시도하세요."),
            "_node": node,
            "action": action,
            "budget_s": budget_s,
            "elapsed_s": elapsed_s,
        }
        if state.get("steps", 1) > 1:
            out["_branch_step_failed"] = f"{state.get('step', 1)}/{state['steps']}"
        return out

    # 8개씩 명시적으로 시작한다. 옛 단일 executor는 9번째 이후 future도 제출 시점부터
    # 전역 90초를 소비해, 실행을 시작하기 전에 이미 타임아웃될 수 있었다. 배치는 워커
    # 상한을 지키면서도 각 가지의 시계를 실제 시작점에 건다. 시간 초과 스레드는 파이썬이
    # 강제 종료할 수 없어 daemon으로 완주하지만, 다음 배치는 새 executor라 굶지 않는다.
    for batch_start in range(0, len(branches), PARALLEL_MAX_WORKERS):
        indices = list(range(batch_start,
                             min(batch_start + PARALLEL_MAX_WORKERS, len(branches))))
        executor = ThreadPoolExecutor(max_workers=len(indices))
        try:
            future_to_idx = {
                executor.submit(_run_branch, idx, branches[idx]): idx
                for idx in indices
            }
            pending = set(future_to_idx)
            while pending:
                now = time.monotonic()
                with state_lock:
                    started = {idx: states[idx]["started_at"] for idx in indices}
                remaining = [
                    max(0.0, started[idx] + budgets[idx] - now)
                    for idx in indices
                    if started[idx] is not None
                    and any(future_to_idx[f] == idx for f in pending)
                ]
                wait_s = max(0.001, min(remaining)) if remaining else 0.01
                done, _ = wait(pending, timeout=wait_s, return_when=FIRST_COMPLETED)
                for future in done:
                    pending.discard(future)
                    idx = future_to_idx[future]
                    try:
                        branch_results[idx] = future.result()
                    except Exception as e:
                        with state_lock:
                            state = dict(states[idx])
                        branch_results[idx] = {
                            "error": str(e), "_node": state.get("node", "?"),
                            "action": state.get("action", "?"),
                        }

                now = time.monotonic()
                for future in list(pending):
                    if future.done():
                        continue
                    idx = future_to_idx[future]
                    with state_lock:
                        began = states[idx]["started_at"]
                    if began is not None and now - began >= budgets[idx]:
                        pending.remove(future)
                        future.cancel()
                        branch_results[idx] = _timeout_result(idx)
        finally:
            # wait=False: 시간 예산을 넘긴 워커를 다시 기다려 바깥 안전망을 무력화하지 않는다.
            executor.shutdown(wait=False, cancel_futures=True)

    return branch_results
