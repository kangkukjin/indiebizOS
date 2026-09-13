"""외주 서비스·프리랜서 검색."""
import os
from common.response_formatter import format_json


def _handle_freelance(tool_input: dict) -> str:
    """[sense:freelance] — 프리랜서·외주 서비스 검색(source 분기). items 통화."""
    # /packages/reload 가 handler 만 갈고 서브모듈은 sys.modules
    # 캐시에 남으므로 파일에서 매번 fresh 로드.
    import importlib.util as _ilu
    _path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tool_freelance.py")
    _spec = _ilu.spec_from_file_location("tool_freelance", _path)
    _tf = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_tf)
    return format_json(_tf.search_freelance(tool_input))


def execute(tool_input: dict, context):
    if context.tool_name == "freelance_search":
        return _handle_freelance(tool_input)
    return format_json({"success": False, "error": f"알 수 없는 도구: {context.tool_name}"})
