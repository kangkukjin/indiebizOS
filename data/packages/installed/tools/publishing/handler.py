"""출판 프로젝트 관리 패키지 핸들러"""

import json
import importlib.util
import os

_TOOL_MODULE_MAP = {
    "publish_list": "registry.py",
    "publish_create": "registry.py",
    "publish_status": "registry.py",
    "publish_export": "export.py",
    "publish_collect": "collect.py",
}

TOOLS = list(_TOOL_MODULE_MAP.keys())


def _load_module(module_file: str):
    tools_dir = os.path.join(os.path.dirname(__file__), "tools")
    module_path = os.path.join(tools_dir, module_file)
    spec = importlib.util.spec_from_file_location(module_file.replace(".py", ""), module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    module_file = _TOOL_MODULE_MAP.get(tool_name)
    if not module_file:
        return json.dumps({"success": False, "error": f"알 수 없는 도구: {tool_name}. 사용 가능: {TOOLS}"}, ensure_ascii=False)

    try:
        module = _load_module(module_file)

        if tool_name == "publish_list":
            result = module.run({"action": "list"})
        elif tool_name == "publish_create":
            tool_input["action"] = "create"
            result = module.run(tool_input)
        elif tool_name == "publish_status":
            tool_input["action"] = "status"
            result = module.run(tool_input)
        elif tool_name == "publish_export":
            result = module.run(tool_input)
        elif tool_name == "publish_collect":
            result = module.run(tool_input)
        else:
            result = {"success": False, "error": f"미구현 도구: {tool_name}"}

        return json.dumps(result, ensure_ascii=False, default=str)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
