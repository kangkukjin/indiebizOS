"""인지 감독의 실행 이음매. 아래층은 컨트롤러 구현을 모르며 agent+task로만 찾는다."""
import json
import threading

_lock = threading.RLock()
_channels = {}


def identity():
    from thread_context import execution_key
    return execution_key()


def register(controller, agents):
    with _lock:
        for agent in set(agents):
            if agent:
                key = (agent, controller.task)
                if key in _channels and _channels[key] is not controller:
                    raise RuntimeError("이미 감독 중인 실행입니다")
        for agent in set(agents):
            if agent:
                _channels[(agent, controller.task)] = controller


def unregister(controller):
    with _lock:
        for key in [k for k, v in _channels.items() if v is controller]:
            del _channels[key]


def current(agent_id=None, task_id=None):
    from thread_context import execution_key
    with _lock:
        return _channels.get(execution_key(agent_id, task_id))


def wrap(execute):
    """API 프로바이더의 실제 호출 경계. 모델의 보고나 스트림 도착 시각에 의존하지 않는다."""
    def call(name, payload, *args, **kwargs):
        controller = current(kwargs.get("agent_id"))
        if name == "supervision":
            if not controller:
                return json.dumps({"success": False, "error": "감독 턴이 없습니다"}, ensure_ascii=False)
            return controller.tool(payload, multimedia=True)
        if not controller:
            return execute(name, payload, *args, **kwargs)
        return controller.run_tool(name, payload, lambda: execute(name, payload, *args, **kwargs))
    return call


def progress(detail):
    controller = current()
    if controller:
        controller.progress(detail)


TOOL_SCHEMA = {
    "name": "supervision",
    "description": "의식·실행 공유 작업대. state는 최초 입력 이후 변경분(offset=사건 cursor). "
                   "evidence id=events는 사건, tool:이름은 도구 스키마, ibl:node:action은 액션 계약. "
                   "인계된 target_blocks 본문을 우선 사용하고, 누락·변경된 블록만 response로 읽는다. "
                   "response는 id로 특정 블록 하나를 읽는다(id 우선). id 생략 시 offset=블록 순번, limit=문자 예산으로 페이지를 읽는다. "
                   "calculate는 input:{expression,values,unit}의 사칙연산을 코드로 계산한다(unit=minutes면 시·분도 반환). "
                   "execute는 의식 전용이다. 실행자는 execute_ibl 등 자신의 도구를 직접 호출한다. "
                   # retired-ok: supervision 전용 페이지 한도이며 execute_ibl.read_result의 60000자 계약과 별개.
                   "limit는 문자 수 1~24000(기본 12000)이다. patch는 response의 블록 ID·해시·버전을 "
                   "지정해 변경 부분만 교체한다. 독립적인 여러 블록은 patches 한 배열, 같은 블록의 여러 수정은 replacements로 묶는다. "
                   "짧은 수정은 old_string/new_string으로 하며 나머지는 그대로 둔다. "
                   "keep는 보완 완료 신호. 별도 진행 보고는 불필요하다.",
    "input_schema": {"type": "object", "properties": {
        "op": {"type": "string", "enum": ["state", "evidence", "response", "execute", "patch", "keep", "calculate"]},
        "id": {"type": "string", "description": "evidence의 원문 ID 또는 response의 블록 ID"}, "offset": {"type": "integer", "minimum": 0},
        "limit": {"type": "integer", "minimum": 1, "maximum": 24000},
        "name": {"type": "string"}, "input": {"type": "object"},
        "version": {"type": "integer"},
        "patches": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "hash": {"type": "string"}, "text": {"type": "string"},
            "old_string": {"type": "string"}, "new_string": {"type": "string"},
            "replacements": {"type": "array", "maxItems": 50, "items": {"type": "object", "properties": {
                "old_string": {"type": "string"}, "new_string": {"type": "string"}},
                "required": ["old_string", "new_string"], "additionalProperties": False}},
        }, "required": ["id", "hash"], "additionalProperties": False}},
    }, "required": ["op"], "additionalProperties": False},
}


def execution_tool_schema():
    """실행자에게 허용되지 않는 감독 execute를 호출 선택지에서 제외한다."""
    from copy import deepcopy
    schema = deepcopy(TOOL_SCHEMA)
    schema["input_schema"]["properties"]["op"]["enum"].remove("execute")
    return schema
