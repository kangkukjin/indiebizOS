"""Validate and atomically replace a todo plan; callers own its session path."""
import json
from datetime import datetime


def write(tool_input, path, file_io):
    # Validate the whole replacement before opening the previous plan.
    todos = tool_input.get("todos")
    if not isinstance(todos, list):
        raise ValueError("todos는 필수 배열입니다. 비우려면 []를 명시하세요.")
    for todo in todos:
        if (not isinstance(todo, dict)
                or any(not isinstance(todo.get(key), str)
                       for key in ("content", "activeForm", "status"))
                or todo["status"] not in {"pending", "in_progress", "completed"}):
            raise ValueError("각 할일에는 content·activeForm 문자열과 유효한 status가 필요합니다.")
    if sum(todo["status"] == "in_progress" for todo in todos) > 1:
        raise ValueError("in_progress 할일은 한 번에 하나만 지정할 수 있습니다.")

    # 상태 저장
    state = {
        "todos": todos,
        "updated_at": datetime.now().isoformat()
    }

    # 결과 포맷팅 (텍스트 기반, Anthropic 스타일)
    result_lines = ["Todo list updated:"]
    for i, todo in enumerate(todos, 1):
        status = todo["status"]
        if status == "in_progress":
            result_lines.append(f"  {i}. [in_progress] {todo['activeForm']}")
        elif status == "completed":
            result_lines.append(f"  {i}. [completed] {todo['content']}")
        else:
            result_lines.append(f"  {i}. [pending] {todo['content']}")

    encoded = json.dumps(state, ensure_ascii=False, indent=2)
    with file_io.file_lock(path):
        file_io.atomic_write_text(path, encoded)
    from execution_situation import emit
    emit({'kind': 'plan', 'path': str(path)}, 'todos', todos,
         source='todo', basis='model_interpretation', observed_at=state['updated_at'])
    return "\n".join(result_lines)
