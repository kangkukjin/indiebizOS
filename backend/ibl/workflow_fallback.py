"""workflow_fallback.py — 폴백(`??`) 체인 실행기 (2026-08-22 형제 모듈 분리, 1500줄 규칙).

workflow_engine 에서 verbatim 이동 + M3 괄호 파이프 가지(`A ?? (B >> C)`). 본체 함수들은 함수 안에서
지연 import(순환 간선 회피 — workflow_engine 이 로드 말미에 이 모듈을 재수출한다).
"""
import json
import time


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
    from workflow_engine import (execute_pipeline, _inject_prev_result, _auto_inject_prev,
                                 _is_error_result, _is_empty_result, _step_label)

    log = []
    last_result = None
    first_empty = None  # 첫 빈손 결과 — 뒤 시도가 고장나면 이것이 최선의 답(⑯)

    for idx, step in enumerate(chain):
        tool_input = dict(step)
        if "node" in tool_input and "_node" not in tool_input:
            tool_input["_node"] = tool_input.pop("node")
        tool_input = _inject_prev_result(tool_input, prev_result)
        tool_input = _auto_inject_prev(tool_input, prev_result)

        start = time.time()
        try:
            if step.get("_branch_steps"):
                # 괄호 파이프 가지 (M3): A ?? (B >> C) — 가지 안을 파이프로 돌려 final_result 를 가지의 결과로.
                env = execute_pipeline(list(step["_branch_steps"]), project_path,
                                       context={"_prev_result": prev_result}, agent_id=agent_id)
                if isinstance(env, dict) and not env.get("success", True):
                    result = {"error": f"괄호 가지 실패: {env.get('error')}", "_branch_envelope": env.get("results")}
                else:
                    result = env.get("final_result") if isinstance(env, dict) else env
                tool_input = {"_node": "pipe", "action": f"({len(step['_branch_steps'])}단)"}
            else:
                result = execute_ibl(tool_input, project_path, agent_id=agent_id)
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            log.append({
                "attempt": idx + 1,
                "node": _step_label(tool_input)[0],
                "action": _step_label(tool_input)[1],
                "status": "exception",
                "error": str(e),
                "duration_ms": duration_ms,
            })
            last_result = {"error": str(e)}
            continue

        duration_ms = int((time.time() - start) * 1000)

        # 에러 확인 — `>>` 와 **같은 함수**를 쓴다(갈라지면 폴백이 문자열 에러를 성공으로 센다)
        # + 빈손 확인 — `??` 전용 술어(⑯, 2026-08-08): 폴백의 의미는 "원하는 걸 못 얻으면
        #   딴 데로"이므로 0건(items:[]·total:0)도 다음 시도로 넘어간다. `>>` 는 불변.
        is_err = _is_error_result(result)
        is_empty = (not is_err) and _is_empty_result(result)
        entry = {
            "attempt": idx + 1,
            "node": _step_label(tool_input)[0],
            "action": _step_label(tool_input)[1],
            "status": "error" if is_err else ("empty" if is_empty else "ok"),
            "duration_ms": duration_ms,
        }
        if is_err:
            # 가지별 실패 사유 보존 (F17-2, 2026-08-20) — 전멸 시 마지막 가지 오류만 남으면
            # 진단이 반쪽부터 시작된다. 병렬(&)의 행별 오류와 같은 규율.
            _e = result.get("error") if isinstance(result, dict) else str(result)
            entry["error"] = str(_e)[:300] if _e else None
        log.append(entry)

        if not is_err and not is_empty:
            # 성공(내용 있는 결과)! 즉시 반환
            # 2차 이후 가지 성공이면 폴백 발동 표식 (F17-2 소품 — 침묵 대체 방지 신고)
            # 핸들러 대다수는 JSON *문자열*을 반환하므로 문자열 봉투도 마킹한다.
            if idx > 0:
                if isinstance(result, dict):
                    result.setdefault("_fallback_used", idx + 1)
                elif isinstance(result, str) and result.strip().startswith("{"):
                    try:
                        _obj = json.loads(result)
                        if isinstance(_obj, dict) and "_fallback_used" not in _obj:
                            _obj["_fallback_used"] = idx + 1
                            result = json.dumps(_obj, ensure_ascii=False)
                    except Exception:
                        pass
            return result, log

        if is_empty and first_empty is None:
            first_empty = result
        last_result = result

    # 모든 체인이 실패 또는 빈손
    if last_result is None:
        last_result = {"error": "fallback 체인이 비어있습니다.", "_all_failed": True}
        return last_result, log
    if not _is_error_result(last_result):
        # 마지막 시도가 빈손(에러 아님) — 정직한 0건이 답. 에러로 위장하지 않는다.
        return last_result, log
    if first_empty is not None:
        # 뒤 시도가 고장났어도 앞의 정직한 빈손이 있으면 그것이 더 나은 답
        return first_empty, log
    if not isinstance(last_result, dict):
        # 문자열 에러("Error: …")는 `_all_failed` 표식을 달 수 없어 호출부가 성공으로 세어 버린다
        # → 전체 실패 경로에서만 error dict 로 감싼다(성공 결과는 원형 그대로 반환되므로 무영향).
        last_result = {"error": str(last_result)}
    last_result["_all_failed"] = True
    # 전멸 시 가지별 실패 사유 동봉 (F17-2) — 마지막 가지 오류만으로는 1차가 왜 죽었는지 소실
    _branch_errors = [{"attempt": e["attempt"], "node": e.get("node"), "action": e.get("action"),
                       "error": e.get("error")}
                      for e in log if e.get("status") in ("error", "exception")]
    if _branch_errors:
        last_result["_branch_errors"] = _branch_errors
    return last_result, log
