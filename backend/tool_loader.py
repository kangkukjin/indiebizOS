"""
tool_loader.py - 도구 패키지 로딩 및 캐싱
IndieBiz OS Core

도구 패키지의 동적 로딩, 캐싱, 매핑을 담당
"""

import json
import importlib.util
from pathlib import Path
from typing import Dict, List, Any, Optional


# 도구 핸들러 캐시 (도구 이름 -> 핸들러 모듈)
_tool_handlers_cache: Dict[str, Any] = {}
# 도구 이름 -> 패키지 ID 매핑
_tool_to_package_map: Dict[str, str] = {}


def get_base_path() -> Path:
    """기본 경로 반환"""
    return Path(__file__).parent.parent


def get_tools_path() -> Path:
    """설치된 도구 패키지 경로 반환"""
    return get_base_path() / "data" / "packages" / "installed" / "tools"


def build_tool_package_map(force: bool = False) -> Dict[str, str]:
    """
    설치된 도구 패키지에서 도구 이름 -> 패키지 ID 매핑 구축

    Args:
        force: True면 캐시 무시하고 재구축

    Returns:
        도구 이름 -> 패키지 ID 매핑
    """
    global _tool_to_package_map

    if _tool_to_package_map and not force:
        return _tool_to_package_map

    tools_path = get_tools_path()
    if not tools_path.exists():
        return _tool_to_package_map

    _tool_to_package_map.clear()

    for pkg_dir in tools_path.iterdir():
        if not pkg_dir.is_dir() or pkg_dir.name.startswith('.'):
            continue

        tool_json = pkg_dir / "tool.json"
        if not tool_json.exists():
            continue

        try:
            tool_def = json.loads(tool_json.read_text(encoding='utf-8'))
            _register_tools_from_definition(tool_def, pkg_dir.name)
        except Exception as e:
            print(f"[도구 매핑 실패] {pkg_dir.name}: {e}")

    return _tool_to_package_map


def _register_tools_from_definition(tool_def: Any, package_name: str):
    """도구 정의에서 도구 이름 추출하여 매핑에 등록"""
    global _tool_to_package_map

    # {"tools": [...]} 형식
    if isinstance(tool_def, dict) and "tools" in tool_def:
        for t in tool_def["tools"]:
            _tool_to_package_map[t["name"]] = package_name
    # 배열 형식 (여러 도구가 한 패키지에)
    elif isinstance(tool_def, list):
        for t in tool_def:
            _tool_to_package_map[t["name"]] = package_name
    # 단일 도구
    elif isinstance(tool_def, dict) and "name" in tool_def:
        _tool_to_package_map[tool_def["name"]] = package_name


def load_tool_handler(tool_name: str) -> Optional[Any]:
    """
    도구 핸들러를 동적으로 로드

    Args:
        tool_name: 도구 이름

    Returns:
        핸들러 모듈 또는 None
    """
    global _tool_handlers_cache

    # 캐시에 있으면 반환
    if tool_name in _tool_handlers_cache:
        return _tool_handlers_cache[tool_name]

    # 매핑 구축
    build_tool_package_map()

    # 패키지 ID 찾기
    package_id = _tool_to_package_map.get(tool_name)
    if not package_id:
        return None

    # handler.py 경로
    handler_path = get_tools_path() / package_id / "handler.py"

    if not handler_path.exists():
        print(f"[도구 핸들러 없음] {tool_name} -> {handler_path}")
        return None

    try:
        # 동적 모듈 로드
        spec = importlib.util.spec_from_file_location(f"tool_handler_{package_id}", handler_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # 캐시에 저장
        _tool_handlers_cache[tool_name] = module
        print(f"[도구 핸들러 로드] {tool_name} <- {package_id}")

        return module

    except Exception as e:
        print(f"[도구 핸들러 로드 실패] {tool_name}: {e}")
        return None


def load_agent_tools(project_path: str, agent_id: str = None) -> List[Dict]:
    """
    에이전트별 도구 로드

    기본: 설치된 모든 도구 사용 가능
    제한: agents.yaml의 allowed_tools가 있으면 해당 도구만 사용

    Args:
        project_path: 프로젝트 경로
        agent_id: 에이전트 ID (필터링용)

    Returns:
        도구 정의 리스트
    """
    tools_path = get_tools_path()
    all_tools = []

    if tools_path.exists():
        for pkg_dir in tools_path.iterdir():
            if not pkg_dir.is_dir() or pkg_dir.name.startswith('.'):
                continue
            tool_json_path = pkg_dir / "tool.json"
            if tool_json_path.exists():
                try:
                    tool_def = json.loads(tool_json_path.read_text(encoding='utf-8'))
                    all_tools.extend(_extract_tools_from_definition(tool_def))
                except Exception as e:
                    print(f"[도구 스캔 실패] {pkg_dir.name}: {e}")

    # agents.yaml에서 에이전트별 allowed_tools 확인
    if agent_id and project_path:
        allowed = _get_allowed_tools(project_path, agent_id)
        if allowed:
            all_tools = [t for t in all_tools if t["name"] in allowed]

    return all_tools


def _extract_tools_from_definition(tool_def: Any) -> List[Dict]:
    """도구 정의에서 도구 리스트 추출"""
    # {"tools": [...]} 형식
    if isinstance(tool_def, dict) and "tools" in tool_def:
        return tool_def["tools"]
    # 배열 형식
    elif isinstance(tool_def, list):
        return tool_def
    # 단일 도구 형식
    elif isinstance(tool_def, dict) and "name" in tool_def:
        return [tool_def]
    return []


def _get_allowed_tools(project_path: str, agent_id: str) -> List[str]:
    """agents.yaml에서 에이전트의 allowed_tools 조회"""
    agents_yaml = Path(project_path) / "agents.yaml"
    if not agents_yaml.exists():
        return []

    try:
        import yaml
        agents_data = yaml.safe_load(agents_yaml.read_text(encoding='utf-8'))
        for agent in agents_data.get("agents", []):
            if agent.get("id") == agent_id:
                return agent.get("allowed_tools", [])
    except Exception as e:
        print(f"[agents.yaml 로드 실패] {e}")

    return []


def load_installed_tools(base_path: str = None) -> List[Dict]:
    """시스템에 설치된 모든 도구 로드 (프로젝트 없을 때 fallback)"""
    if base_path is None:
        tools_path = get_tools_path()
    else:
        tools_path = Path(base_path) / "data" / "packages" / "installed" / "tools"

    extra_tools = []

    if tools_path.exists():
        for tool_dir in tools_path.iterdir():
            if tool_dir.is_dir():
                tool_json = tool_dir / "tool.json"
                if tool_json.exists():
                    try:
                        tool_def = json.loads(tool_json.read_text(encoding='utf-8'))
                        tools = _extract_tools_from_definition(tool_def)
                        for t in tools:
                            extra_tools.append(t)
                            print(f"[도구 로드] {t.get('name')}")
                    except Exception as e:
                        print(f"[도구 로드 실패] {tool_dir.name}: {e}")

    return extra_tools


def get_all_tool_names() -> List[str]:
    """설치된 모든 도구 이름 반환"""
    build_tool_package_map()
    return list(_tool_to_package_map.keys())


def clear_cache():
    """캐시 초기화 (테스트/리로드용)"""
    global _tool_handlers_cache, _tool_to_package_map
    _tool_handlers_cache.clear()
    _tool_to_package_map.clear()
