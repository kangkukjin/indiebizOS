"""
tool_loader.py - 도구 패키지 로딩 및 캐싱
IndieBiz OS Core

도구 패키지의 동적 로딩, 캐싱, 매핑을 담당
"""

import json
import time
import importlib.util
from pathlib import Path
from typing import Dict, List, Any, Optional


# 도구 핸들러 캐시 (도구 이름 -> 핸들러 모듈)
_tool_handlers_cache: Dict[str, Any] = {}
# 패키지 ID -> 핸들러 모듈 캐시 (같은 패키지의 도구들이 모듈 인스턴스를 공유)
_package_handlers_cache: Dict[str, Any] = {}
# 도구 이름 -> 패키지 ID 매핑
_tool_to_package_map: Dict[str, str] = {}
# 전체 도구 정의 캐시
_all_tools_cache: List[Dict] = []
_all_tools_cache_time: float = 0
# agents.yaml 캐시 (project_path -> (캐시시간, 데이터))
_agents_yaml_cache: Dict[str, tuple] = {}
_CACHE_TTL: float = 60.0  # 60초 캐시


def get_base_path() -> Path:
    """기본 경로 반환 (프로덕션: 환경변수, 개발: 상위 폴더)"""
    import os
    env_path = os.environ.get("INDIEBIZ_BASE_PATH")
    if env_path:
        return Path(env_path)
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


def build_execute_ibl_tool(allowed_nodes: Optional[List[str]] = None) -> Optional[dict]:
    """ibl_nodes.yaml에서 execute_ibl 도구 정의를 동적 생성.

    tool.json에 하드코딩하지 않고 ibl_nodes.yaml을 단일 진실 소스로 사용.
    노드가 추가/삭제되면 자동 반영됨.

    Args:
        allowed_nodes: agents.yaml의 allowed_nodes 설정.
                       None/[]이면 모든 노드 포함.
                       지정 시 해당 노드만 description/enum에 포함.
    """
    import yaml

    yaml_path = get_base_path() / "data" / "ibl_nodes.yaml"
    if not yaml_path.exists():
        return None

    try:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
    except Exception as e:
        print(f"[tool_loader] ibl_nodes.yaml 파싱 실패: {e}")
        return None

    all_nodes = data.get("nodes", {})
    meta = data.get("meta", {})

    # --- allowed_nodes 필터링 (ibl_access.resolve_allowed_nodes와 동일 로직 활용) ---
    if allowed_nodes:
        try:
            from ibl_access import resolve_allowed_nodes
            allowed_set = resolve_allowed_nodes(allowed_nodes)
        except ImportError:
            allowed_set = None
    else:
        allowed_set = None  # None = 모든 노드 허용

    if allowed_set is not None:
        nodes = {k: v for k, v in all_nodes.items() if k in allowed_set}
    else:
        nodes = all_nodes

    # --- 노드 요약 생성 ---
    node_lines = []
    node_names = []
    for name, node_def in nodes.items():
        node_names.append(name)
        desc = node_def.get("description", "")
        actions = node_def.get("actions", {})
        action_names = list(actions.keys())
        shown = ", ".join(action_names)
        node_lines.append(f"- {name}: {desc}\n  액션: {shown}")

    nodes_section = "\n".join(node_lines)

    # --- 사용 예시 ---
    usage_lines = []
    for section in meta.get("usage", []):
        usage_lines.append(section.get("section", ""))
        for ex in section.get("examples", []):
            usage_lines.append(f"  {ex}")

    # --- 파이프라인 연산자 ---
    pipe_lines = []
    for p in meta.get("pipeline", []):
        pipe_lines.append(f"{p['op']} ({p['name']}): {p.get('example', '')}")

    # --- description 조합 ---
    description = (
        f"IndieBiz 통합 도구. {len(nodes)}개 노드로 모든 기능 실행.\n"
        f"\n## 노드\n{nodes_section}\n"
        f"\n## 사용법\n" + "\n".join(usage_lines) + "\n"
        f"\n## 파이프라인\n" + "\n".join(pipe_lines) + "\n"
        f"\nnode를 모르면 system:discover로 검색."
    )

    return {
        "name": "execute_ibl",
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": f"노드 이름: {', '.join(node_names)}",
                    "enum": node_names if node_names else ["system"]
                },
                "action": {
                    "type": "string",
                    "description": "실행할 액션 (예: web_search, registry, read, play, send)"
                },
                "target": {
                    "type": "string",
                    "description": "대상 (검색어, URL, 파일 경로, 종목 코드 등)"
                },
                "params": {
                    "type": "object",
                    "description": "추가 파라미터"
                },
                "code": {
                    "type": "string",
                    "description": "IBL 코드 (파이프라인 모드: [node:action](target) >> ...)"
                }
            }
        }
    }


def load_tool_schema(tool_name: str) -> Optional[dict]:
    """도구 스키마(input_schema 포함) 반환 (Phase 17)

    execute_ibl은 ibl_nodes.yaml에서 동적 생성.
    나머지는 tool.json에서 로드.
    """
    # execute_ibl은 동적 생성 (ibl_nodes.yaml 기반)
    if tool_name == "execute_ibl":
        return build_execute_ibl_tool()

    pkg_map = build_tool_package_map()
    pkg_name = pkg_map.get(tool_name)
    if not pkg_name:
        return None

    tool_json_path = get_tools_path() / pkg_name / "tool.json"
    if not tool_json_path.exists():
        return None

    try:
        tool_def = json.loads(tool_json_path.read_text(encoding='utf-8'))
        # {"tools": [...]} 형식
        if isinstance(tool_def, dict) and "tools" in tool_def:
            for t in tool_def["tools"]:
                if t.get("name") == tool_name:
                    return t
        # 단일 도구
        elif isinstance(tool_def, dict) and tool_def.get("name") == tool_name:
            return tool_def
    except Exception:
        pass
    return None


def load_tool_handler(tool_name: str) -> Optional[Any]:
    """
    도구 핸들러를 동적으로 로드

    같은 패키지의 도구들은 하나의 모듈 인스턴스를 공유합니다.
    (예: browser_navigate와 browser_snapshot은 같은 handler.py 모듈을 공유)

    Args:
        tool_name: 도구 이름

    Returns:
        핸들러 모듈 또는 None
    """
    global _tool_handlers_cache, _package_handlers_cache

    # 도구 이름 캐시에 있으면 반환
    if tool_name in _tool_handlers_cache:
        return _tool_handlers_cache[tool_name]

    # 매핑 구축
    build_tool_package_map()

    # 패키지 ID 찾기
    package_id = _tool_to_package_map.get(tool_name)
    if not package_id:
        return None

    # 같은 패키지의 다른 도구가 이미 로드했으면 그 모듈 인스턴스를 재사용
    if package_id in _package_handlers_cache:
        module = _package_handlers_cache[package_id]
        _tool_handlers_cache[tool_name] = module
        print(f"[도구 핸들러 재사용] {tool_name} <- {package_id} (공유 모듈)")
        return module

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

        # 패키지 캐시와 도구 캐시 모두에 저장
        _package_handlers_cache[package_id] = module
        _tool_handlers_cache[tool_name] = module
        print(f"[도구 핸들러 로드] {tool_name} <- {package_id}")

        return module

    except Exception as e:
        print(f"[도구 핸들러 로드 실패] {tool_name}: {e}")
        return None


def load_agent_tools(project_path: str, agent_id: str = None) -> List[Dict]:
    """
    에이전트별 도구 로드 (캐싱 지원)

    기본: 설치된 모든 도구 사용 가능
    제한: agents.yaml의 allowed_tools가 있으면 해당 도구만 사용

    Args:
        project_path: 프로젝트 경로
        agent_id: 에이전트 ID (필터링용)

    Returns:
        도구 정의 리스트
    """
    global _all_tools_cache, _all_tools_cache_time

    # 캐시가 유효하면 캐시 사용
    if _all_tools_cache and time.time() - _all_tools_cache_time < _CACHE_TTL:
        all_tools = _all_tools_cache.copy()
    else:
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
                        tools = _extract_tools_from_definition(tool_def)
                        # guide_file 필드는 AI에게 전달하지 않고 제거 (on-demand 로딩)
                        tools = _strip_guide_file_field(tools)
                        all_tools.extend(tools)
                    except Exception as e:
                        print(f"[도구 스캔 실패] {pkg_dir.name}: {e}")

        # 캐시 업데이트
        _all_tools_cache = all_tools.copy()
        _all_tools_cache_time = time.time()

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


# 가이드 파일 내용 캐시 (파일 경로 -> 내용)
_guide_content_cache: Dict[str, str] = {}


def _strip_guide_file_field(tools: List[Dict]) -> List[Dict]:
    """도구 정의에서 guide_file 필드를 제거 (AI에게 불필요한 필드)"""
    stripped = []
    for tool in tools:
        if "guide_file" in tool:
            tool = dict(tool)
            tool.pop("guide_file", None)
        stripped.append(tool)
    return stripped


# 도구 이름 -> guide_file 매핑 캐시
_tool_guide_map: Dict[str, str] = {}
_tool_guide_map_built: bool = False


def _build_tool_guide_map():
    """tool.json의 guide_file 필드에서 도구 이름 -> 가이드 파일 경로 매핑 구축"""
    global _tool_guide_map, _tool_guide_map_built

    if _tool_guide_map_built:
        return

    tools_path = get_tools_path()
    if not tools_path.exists():
        _tool_guide_map_built = True
        return

    for pkg_dir in tools_path.iterdir():
        if not pkg_dir.is_dir() or pkg_dir.name.startswith('.'):
            continue

        tool_json = pkg_dir / "tool.json"
        if not tool_json.exists():
            continue

        try:
            tool_def = json.loads(tool_json.read_text(encoding='utf-8'))

            # 패키지 레벨 guide_file
            pkg_guide_file = None
            if isinstance(tool_def, dict):
                pkg_guide_file = tool_def.get("guide_file")

            # 개별 도구에서 guide_file 매핑
            tools = _extract_tools_from_definition(tool_def)
            for t in tools:
                guide_file = t.get("guide_file") or pkg_guide_file
                if guide_file:
                    guide_path = str(pkg_dir / guide_file)
                    _tool_guide_map[t["name"]] = guide_path
        except Exception:
            pass

    _tool_guide_map_built = True


def get_tool_guide(tool_name: str) -> Optional[str]:
    """도구의 가이드 파일 내용을 반환 (on-demand 로딩)

    tool.json에 guide_file이 지정된 도구의 가이드 내용을 반환합니다.
    가이드가 없으면 None을 반환합니다.

    Args:
        tool_name: 도구 이름

    Returns:
        가이드 파일 내용 또는 None
    """
    _build_tool_guide_map()

    guide_path_str = _tool_guide_map.get(tool_name)
    if not guide_path_str:
        return None

    guide_path = Path(guide_path_str)
    return _load_guide_content(guide_path)


def get_tool_guide_path(tool_name: str) -> Optional[str]:
    """도구의 가이드 파일 경로를 반환 (중복 주입 방지용)

    같은 guide_file을 공유하는 도구들은 동일한 경로를 반환하므로,
    가이드 주입 시 패키지 레벨로 중복을 방지할 수 있습니다.

    Args:
        tool_name: 도구 이름

    Returns:
        가이드 파일 경로 문자열 또는 None
    """
    _build_tool_guide_map()
    return _tool_guide_map.get(tool_name)


def _load_guide_content(guide_path: Path) -> Optional[str]:
    """가이드 파일 내용을 로드 (캐싱 지원)"""
    global _guide_content_cache

    path_str = str(guide_path)

    if path_str in _guide_content_cache:
        return _guide_content_cache[path_str]

    if not guide_path.exists():
        _guide_content_cache[path_str] = None
        return None

    try:
        content = guide_path.read_text(encoding='utf-8')
        _guide_content_cache[path_str] = content
        print(f"[도구 가이드 로드] {guide_path.name}")
        return content
    except Exception as e:
        print(f"[도구 가이드 로드 실패] {guide_path}: {e}")
        _guide_content_cache[path_str] = None
        return None


def _get_allowed_tools(project_path: str, agent_id: str) -> List[str]:
    """agents.yaml에서 에이전트의 allowed_tools 조회 (캐싱 지원)"""
    global _agents_yaml_cache

    agents_yaml = Path(project_path) / "agents.yaml"
    if not agents_yaml.exists():
        return []

    # 캐시 확인
    cache_key = str(project_path)
    if cache_key in _agents_yaml_cache:
        cache_time, agents_data = _agents_yaml_cache[cache_key]
        if time.time() - cache_time < _CACHE_TTL:
            for agent in agents_data.get("agents", []):
                if agent.get("id") == agent_id:
                    return agent.get("allowed_tools", [])
            return []

    try:
        import yaml
        agents_data = yaml.safe_load(agents_yaml.read_text(encoding='utf-8'))

        # 캐시 업데이트
        _agents_yaml_cache[cache_key] = (time.time(), agents_data)

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
                        tools = _strip_guide_file_field(tools)
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
    global _tool_handlers_cache, _package_handlers_cache, _tool_to_package_map, _all_tools_cache, _all_tools_cache_time, _agents_yaml_cache, _guide_content_cache, _tool_guide_map, _tool_guide_map_built
    _tool_handlers_cache.clear()
    _package_handlers_cache.clear()
    _tool_to_package_map.clear()
    _all_tools_cache = []
    _all_tools_cache_time = 0
    _agents_yaml_cache.clear()
    _guide_content_cache.clear()
    _tool_guide_map.clear()
    _tool_guide_map_built = False
