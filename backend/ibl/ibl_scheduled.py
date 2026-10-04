"""Saved source execution with scheduler identity; shared by timers and calendar."""
def execute_scheduled(steps, run_path, agent_id, edition=None, inputs=None):
    """직접 발화의 출처를 전달한다. 위임 종류별 원장은 해당 위임기가 소유한다."""
    import json
    import uuid
    import thread_context as tc
    from workflow_engine import execute_pipeline

    previous = tc.snapshot()
    try:
        # 정기 실행마다 독립 ID를 부여한다. 수리 권한도 실행 ID로 격리된다.
        # task_sysai_ 접두사는 시스템 AI 활성 작업 등록에 쓰이므로 피한다.
        with tc.actor_context(agent_id=agent_id or "system_ai",
                              task_id=f"task_schedule_{uuid.uuid4().hex[:8]}", origin="scheduler"):
            tc.clear_called_agent()
            tc.set_call_channel("scheduler", override=True)
            from ibl_v2_entry import handle_request
            result = (handle_request({"code": steps, "edition": edition, "inputs": inputs},
                                     run_path, agent_id=agent_id) if isinstance(steps, str) else None)
            if result is None:
                if isinstance(steps, str):
                    from ibl_parser import parse
                    steps = parse(steps)
                result = execute_pipeline(steps, run_path, agent_id=agent_id)
            # 비동기 접수와 실제 작업 완료를 구분한다(파이프라인 성공=호출 성공).
            values = [result.get("final_result")]
            values += [r.get("result") for r in result.get("results", [])]
            queued_tasks = []
            for value in values:
                if isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except (ValueError, TypeError):
                        continue
                if isinstance(value, dict) and value.get("queued") and value.get("task_id"):
                    if value["task_id"] not in queued_tasks:
                        queued_tasks.append(value["task_id"])
            if queued_tasks:
                result.update(queued=True, delegation_task_ids=queued_tasks)
            return result
    finally:
        tc.restore(previous)  # 호출자·재사용 스레드에 위임 플래그를 남기지 않는다.

