"""CLI todo calls use the active execution turn and the existing todo handler."""
import json


def execute(todos, agent_id, task_id):
    from execution_turn import resolve_session
    from thread_context import snapshot, restore

    if not agent_id or not task_id:
        return {"success": False, "error": "할일 갱신에는 활성 실행자의 agent_id/task_id가 필요합니다"}
    try:
        binding = resolve_session(agent_id, task_id)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    previous = snapshot()
    try:
        from supervision_bus import current, wrap
        from system_tools import execute_tool
        supervisor = current(binding.agent, task_id)
        # The supervisor may have refreshed permissions since turn entry.
        restore(supervisor.context if supervisor else binding.context)
        from thread_context import set_current_agent_id, set_current_task_id
        set_current_agent_id(binding.agent)
        set_current_task_id(task_id)
        from providers.base import adopt_turn_token_ledger
        from model_call_context import adopt_call_context
        from conversation_sessions import scope
        with scope(binding.conversation), adopt_turn_token_ledger(binding.agent, task_id), \
                adopt_call_context(binding.agent, task_id):
            raw = wrap(execute_tool)("todo_write", {"todos": todos},
                str(binding.runner.project_path), agent_id=binding.agent,
                cancel_check=supervisor.cancelled if supervisor else None)
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except ValueError:
                from ibl_result_transport import tool_result_is_error
                return {"success": not tool_result_is_error(raw), "result": raw}
        return raw
    finally:
        restore(previous)
