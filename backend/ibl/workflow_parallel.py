# -*- coding: utf-8 -*-
"""병렬(&) 분기 실행기 — workflow_engine 의 형제 모듈.

2026-08-19 분리(1500줄 규칙): G13-1 괄호 분기 파이프 추가로 본체가 1532줄이 되어
`_execute_parallel` 를 여기로 옮김. 이음매 헬퍼(_inject_prev_result 등)는 workflow_binding.py 소유·본체 재수출이라
호출 시점에 지연 import 한다(본체가 이 모듈을 top-level import 하므로 — 순환 회피).
"""

PARALLEL_BRANCH_TIMEOUT = 90


def _execute_parallel(branches: list, project_path: str, prev_result: str, raw: bool = False,
                      var_values: dict = None) -> list:
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
        var_values: 분기가 참조하는 `$변수`의 값 (`$a & $b`, 언어 개정 2026-09-01).
             실행기가 병렬 step 의 _vars 로 해소해 넘긴다 — 여기서 분기 **사본**에만
             싣는다(파싱된 프로그램을 건드리면 두 번째 실행이 옛 값을 본다).

    Returns:
        각 branch 결과를 리스트로 합침
    """
    from ibl_engine import execute_ibl
    from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
    from workflow_engine import (_inject_prev_result, _auto_inject_prev,
                                 is_error_result, _to_prev_currency)

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

    def _run_branch(branch):
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
        try:
            return execute_ibl(tool_input, project_path)
        except Exception as e:
            return {"error": str(e), "_node": tool_input.get("_node", "?"),
                    "action": tool_input.get("action", "?")}

    # ThreadPoolExecutor로 동시 실행 (타임아웃 적용)
    branch_results = [None] * len(branches)
    executor = ThreadPoolExecutor(max_workers=min(len(branches), 8))
    try:
        future_to_idx = {
            executor.submit(_run_branch, branch): idx
            for idx, branch in enumerate(branches)
        }
        try:
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
        except FuturesTimeoutError:
            # as_completed 자신의 타임아웃. 여기서 잡지 않으면 이 예외가 함수 밖으로 튀어
            # concurrent.futures 의 내부 문구("1 (of 2) futures unfinished")가 그대로 사용자
            # 봉투에 실리고, 아래의 "미완료 브랜치 처리"(어느 가지가 몇 초에 걸렸는지 말해 주는
            # 정직한 신고)는 영영 실행되지 않는 죽은 코드가 된다. (29회차 B29-3)
            print(f"[IBL] 병렬 전체 타임아웃 ({PARALLEL_BRANCH_TIMEOUT}초) — 미완료 브랜치를 개별 신고합니다")
    finally:
        # wait=False: 타임아웃이 벽시계를 실제로 묶는다. with 문의 암묵적
        # shutdown(wait=True)은 낙오 가지가 끝날 때까지 기다려 타임아웃을 무력화했다.
        executor.shutdown(wait=False, cancel_futures=True)

    # as_completed 자체가 타임아웃된 경우 미완료 브랜치 처리
    for idx, result in enumerate(branch_results):
        if result is None:
            node = branches[idx].get("node", branches[idx].get("_node", "?"))
            action = branches[idx].get("action", "?")
            branch_results[idx] = {
                "error": f"실행 시간 초과 ({PARALLEL_BRANCH_TIMEOUT}초): [{node}:{action}]. 다른 방법을 시도하세요."
            }

    return branch_results
