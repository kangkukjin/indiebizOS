"""출판 프로젝트 관리 패키지 핸들러"""

import json
import importlib.util
import os

_TOOL_MODULE_MAP = {
    "publish_op": "registry.py",  # 2026-06-03 [engines:publish]{op} 통합
    "publish_export": "export.py",
    "publish_collect": "collect.py",
}

TOOLS = list(_TOOL_MODULE_MAP.keys())

# 단일 액션 op 키 메타데이터 (--check 가 src.ops.values 와 비교).
_OP_DISPATCHERS = {"publish_op": {"list": None, "create": None, "status": None}}
_OP_DEFAULTS = {"publish_op": "list"}


def _load_module(module_file: str):
    tools_dir = os.path.join(os.path.dirname(__file__), "tools")
    module_path = os.path.join(tools_dir, module_file)
    spec = importlib.util.spec_from_file_location(module_file.replace(".py", ""), module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def execute(tool_input: dict, context) -> str:
    """ToolContext 기반 신규 시그니처."""
    tool_name = context.tool_name
    module_file = _TOOL_MODULE_MAP.get(tool_name)
    if not module_file:
        return json.dumps({"success": False, "error": f"알 수 없는 도구: {tool_name}. 사용 가능: {TOOLS}"}, ensure_ascii=False)

    try:
        module = _load_module(module_file)

        if tool_name == "publish_op":
            op = (tool_input.get("op") or _OP_DEFAULTS["publish_op"]).strip()
            if op not in _OP_DISPATCHERS["publish_op"]:
                return json.dumps({"success": False, "error": f"알 수 없는 op '{op}'. 사용: list|create|status"}, ensure_ascii=False)
            ti = dict(tool_input)
            ti["action"] = op
            result = module.run(ti)
        elif tool_name == "publish_export":
            result = module.run(tool_input)
        elif tool_name == "publish_collect":
            result = module.run(tool_input)
        else:
            result = {"success": False, "error": f"미구현 도구: {tool_name}"}

        return json.dumps(result, ensure_ascii=False, default=str)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
