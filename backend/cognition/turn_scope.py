"""상태 통보의 범위를 기존 분류 호출과 사전의 선언으로 보존한다."""

CONTEXT_UPDATE = """<turn_scope kind="context_update">
사용자는 새 사실을 통보했다. 현재 사건의 관련 기억을 확인하고 통보한 사실·정정만 반영한다.
답에 필요한 모순 해소는 하되 요청하지 않은 경로·날씨·상품 등의 새 조사를 시작하지 않는다.
다른 사건의 과거 정보나 AI 권고를 현재 사용자의 결정으로 적용하지 않는다.
저장·예약했다고 말할 때는 실제 성공 영수증이 있어야 한다. 후속 작업도 등록 전에는 약속하지 않는다.
</turn_scope>"""


def context_program(code):
    from cognitive_trace import _ibl_steps
    from ibl_access import load_nodes_raw
    steps = _ibl_steps(code)
    if not steps:
        return False
    nodes = load_nodes_raw().get("nodes", {})
    for node, action, params in steps:
        spec = nodes.get(node, {}).get("actions", {}).get(action, {})
        ops = spec.get("context_update_ops", [])
        if not ops or params.get("op") not in ops:
            return False
    return True


def allows_context_tool(name, payload):
    name = name.rsplit("__", 1)[-1]
    if name == "pursuit":
        # 연결을 별도 전경 모델에서 현재 실행자로 옮겼다. 사실 통보도 관련 과제를
        # 읽고 연결·정정·분리할 수 있으나 새 과제/완료/재개로 일을 확대하지 않는다.
        return payload.get("op") in {"read", "bind", "note", "goal", "detach"}
    if name == "read_result":
        return True
    code = payload.get("code") or payload.get("pipeline") or ""
    return name == "execute_ibl" and (
        (not code and bool(payload.get("describe"))) or context_program(code))
