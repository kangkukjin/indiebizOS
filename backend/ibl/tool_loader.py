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

from result_read_contract import read_result_schema
from vocabulary_state import active_paths, package_path, require_tool_active


# 도구 핸들러 캐시 (도구 이름 -> 핸들러 모듈)
_tool_handlers_cache: Dict[str, Any] = {}
# 패키지 ID -> 핸들러 모듈 캐시 (같은 패키지의 도구들이 모듈 인스턴스를 공유)
_package_handlers_cache: Dict[str, Any] = {}
# 패키지 ID -> handler.py mtime (로드 시점) — handler.py 편집의 자동 무효화용.
# ★왜 (2026-09-01): mtime 무효화가 tool.json 에만 걸려 있어, handler.py 만 고치면
# /packages/reload 나 재기동 전까지 메모리에 옛 모듈이 그대로 남았다(조용한 부정합).
# tool.json 의 기존 패턴(_scan_tool_json_mtimes)을 handler.py 로 확장한 것.
# 형제 모듈(tool_*.py 등)은 여전히 재기동 필요 — 이 무효화는 handler.py 만 본다.
_package_handler_mtimes: Dict[str, float] = {}
# 도구 이름 -> 패키지 ID 매핑
_tool_to_package_map: Dict[str, str] = {}
# tool.json mtime 스냅샷 (자동 캐시 무효화용 — 2026-05-28 추가)
# 패키지 ID -> tool.json의 mtime. _tool_to_package_map과 _all_tools_cache가
# tool.json 변경에 즉시 반응하도록 한다.
_tool_json_mtimes: Dict[str, float] = {}
# 전체 도구 정의 캐시
_all_tools_cache: List[Dict] = []
_all_tools_cache_time: float = 0
_all_tools_cache_mtimes: Dict[str, float] = {}
# agents.yaml 캐시 (project_path -> (캐시시간, 데이터))
_agents_yaml_cache: Dict[str, tuple] = {}
_CACHE_TTL: float = 60.0  # 60초 캐시 (mtime 변화 없을 때 상한)


def get_base_path() -> Path:
    """기본 경로 반환 (프로덕션: 환경변수, 개발: 상위 폴더)"""
    import os
    env_path = os.environ.get("INDIEBIZ_BASE_PATH")
    if env_path:
        return Path(env_path)
    return Path(__file__).parent.parent.parent


def get_tools_path() -> Path:
    """설치된 도구 패키지 경로 반환"""
    return get_base_path() / "data" / "packages" / "installed" / "tools"


def _scan_tool_json_mtimes() -> Dict[str, float]:
    """현재 모든 tool.json의 mtime 스냅샷.

    캐시 무효화 트리거 용도. 패키지 추가/삭제/수정 모두 감지.
    """
    tools_path = get_tools_path()
    out: Dict[str, float] = {}
    if not tools_path.exists():
        return out
    for pkg_dir in active_paths(get_base_path()):
        if not pkg_dir.is_dir() or pkg_dir.name.startswith('.'):
            continue
        tj = pkg_dir / "tool.json"
        if tj.exists():
            try:
                out[pkg_dir.name] = tj.stat().st_mtime
            except OSError:
                pass
    return out


def build_tool_package_map(force: bool = False) -> Dict[str, str]:
    """
    설치된 도구 패키지에서 도구 이름 -> 패키지 ID 매핑 구축

    tool.json 변경 시 자동 무효화 (mtime 스냅샷 비교).

    Args:
        force: True면 캐시 무시하고 재구축

    Returns:
        도구 이름 -> 패키지 ID 매핑
    """
    global _tool_to_package_map, _tool_json_mtimes

    if _tool_to_package_map and not force:
        # 캐시가 있어도 tool.json 변경이 있으면 자동 무효화.
        cur_mtimes = _scan_tool_json_mtimes()
        if cur_mtimes == _tool_json_mtimes:
            return _tool_to_package_map
        print(f"[도구 매핑] tool.json 변경 감지 — 캐시 재구축")

    tools_path = get_tools_path()
    if not tools_path.exists():
        return _tool_to_package_map

    _tool_to_package_map.clear()

    for pkg_dir in active_paths(get_base_path()):
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

    # mtime 스냅샷 갱신 (다음 호출에서 변화 감지용)
    _tool_json_mtimes = _scan_tool_json_mtimes()
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

    from ibl_registry import load_nodes_installed
    data = load_nodes_installed()

    all_nodes = data.get("nodes", {})

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

    # --- 노드 이름만 수집 (enum용) ---
    node_names = sorted(nodes.keys())

    # --- description: IBL 코드 기반 실행 ---
    node_list = ', '.join(node_names)
    description = (
        f"현재 IBL로 새 코드를 실행합니다. 주 교재: ibl_composition.md. "
        f"사용 가능한 노드: {node_list}. "
        f"액션 계약은 describe=[node:action]으로 조회. code를 함께 주면 조회 성공 후 한 번 실행하고 descriptions를 덧붙임. 저장된 원문은 code 없이 read_result로 회수."
    )

    return {
        "name": "execute_ibl",
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": {
                "edition": {"type": "integer", "enum": [1, 2], "default": 2,
                            "description": "새 작성 기본값=2. 저장된 기존 원문의 재실행에만 1을 명시. 문법 오류로 자동 전환하지 않음."},
                "inputs": {"type": "object", "description": "명시 외부 이름→값. 이전 턴 변수는 자동 주입하지 않음."},
                "check": {"type": "boolean", "description": "실행 없이 같은 컴파일러로 검사."},
                "code": {
                    "type": "string",
                    "description": (
                        '명시 값·함수 문법. [def:두배]($x){return $x*2}; [fn:두배]{x:3}. '
                        '목록 >> [table:each]{parallel:4}{return $it}는 순서 보존 반복. '
                        '검색: $r=[sense:search]{query:"AI"}; return $r.items. '
                        '조건 필터: $rows >> [table:filter]{where:($r)=>$r.score>=5}. '
                        '변수는 한 프로그램의 값이며 외부 입력은 inputs. 반환은 value.'
                    )
                },
                "files": {"type": "array", "items": {"type": "string"}, "description": "기존 저장 코드(edition:1)의 인라인 파일 인자. 새 코드는 inputs에 값 전달."},
                "files_from": {"type": "array", "items": {"type": "string"}, "description": "기존 저장 코드(edition:1)의 파일 인자. 새 코드는 self:read의 text를 명시 전달."},
                "resume": {"type": "object", "description": "현재 IBL은 반환된 {run_id}와 동일 code·inputs로 재개. 완료 영수증을 재사용하며 결과 불명 외부 작업은 재실행하지 않는다. 기존 저장 코드의 재개 인자도 보존."},
                "describe": {"type": "array", "items": {"type": "string"}, "maxItems": 6,
                             "description": "액션 이름 1~6개의 계약 조회. code가 비면 조회만, 있으면 조회 성공 후 한 번 실행하고 descriptions를 반환."},
                "read_result": read_result_schema(),
            },
            "required": ["code"]
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

    tool_json_path = package_path(pkg_name) / "tool.json"
    if not tool_json_path.exists():
        return None

    try:
        tool_def = json.loads(tool_json_path.read_text(encoding='utf-8'))
    except Exception as e:
        # ★깨진 tool.json 을 None(="그런 도구 없음")으로 눙치지 않는다 — 패키지의
        # 액션 전체가 조용히 사라진다. 파일 부재(위의 exists 검사)와 구별한다. 2026-08-22.
        raise RuntimeError(
            f"도구 정의가 깨졌습니다 — {tool_json_path} 를 읽을 수 없습니다: {e}"
        ) from e

    # {"tools": [...]} 형식
    if isinstance(tool_def, dict) and "tools" in tool_def:
        for t in tool_def["tools"] or []:
            if isinstance(t, dict) and t.get("name") == tool_name:
                return t
    # 단일 도구
    elif isinstance(tool_def, dict) and tool_def.get("name") == tool_name:
        return tool_def
    return None  # 파일은 멀쩡한데 이 이름이 없다 = 진짜 없음


def _invalidate_stale_handler(package_id: str) -> bool:
    """handler.py 가 로드 시점보다 새로우면 그 패키지의 핸들러 캐시를 비운다(True=비움).

    비교 실패(파일 소실 등)는 무효화하지 않는다 — 로드된 모듈이 마지막 진실이다."""
    try:
        mtime = (package_path(package_id) / "handler.py").stat().st_mtime
    except OSError:
        return False
    if _package_handler_mtimes.get(package_id) == mtime:
        return False
    if package_id not in _package_handlers_cache:
        _package_handler_mtimes[package_id] = mtime   # 기록만 낡음 — 비울 캐시가 없다
        return False
    _package_handlers_cache.pop(package_id, None)
    _package_handler_mtimes.pop(package_id, None)
    for _t, _p in list(_tool_to_package_map.items()):
        if _p == package_id:
            _tool_handlers_cache.pop(_t, None)
    print(f"[도구 핸들러 무효화] {package_id}: handler.py 변경 감지 — 다음 호출이 재로드")
    return True


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
    require_tool_active(tool_name)

    # 도구 이름 캐시에 있으면 반환 — 단 handler.py 가 디스크에서 바뀌었으면 낡은 모듈이다
    # 로컬 참조를 잡는다. 병렬 호출의 무효화/clear_cache가 dict 항목을 지워도
    # 이미 시작한 호출은 유효한 모듈 스냅샷으로 완료하고 다음 호출이 새 버전을 받는다.
    cached = _tool_handlers_cache.get(tool_name)
    if cached is not None:
        _pkg = _tool_to_package_map.get(tool_name)
        if not (_pkg and _invalidate_stale_handler(_pkg)):
            return cached
        # 낡음 — 캐시가 비워졌으니 아래 재로드 경로로 계속

    # 매핑 구축
    build_tool_package_map()

    # 패키지 ID 찾기
    package_id = _tool_to_package_map.get(tool_name)
    if not package_id:
        return None

    # 같은 패키지의 다른 도구가 이미 로드했으면 그 모듈 인스턴스를 재사용
    module = _package_handlers_cache.get(package_id)
    if module is not None and not _invalidate_stale_handler(package_id):
        _tool_handlers_cache[tool_name] = module
        print(f"[도구 핸들러 재사용] {tool_name} <- {package_id} (공유 모듈)")
        return module

    # handler.py 경로
    handler_path = package_path(package_id) / "handler.py"

    if not handler_path.exists():
        print(f"[도구 핸들러 없음] {tool_name} -> {handler_path}")
        return None

    try:
        # 동적 모듈 로드 — mtime 은 exec **전에** 뜬다(로드 중 편집이면 다음 호출이 재로드)
        try:
            _mtime = handler_path.stat().st_mtime
        except OSError:
            _mtime = 0.0
        spec = importlib.util.spec_from_file_location(f"tool_handler_{package_id}", handler_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # 패키지 캐시와 도구 캐시 모두에 저장
        _package_handlers_cache[package_id] = module
        _package_handler_mtimes[package_id] = _mtime
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
    global _all_tools_cache, _all_tools_cache_time, _all_tools_cache_mtimes

    # 캐시 유효성 검사: TTL 내 + tool.json mtime 변화 없음 (2026-05-28 추가)
    cache_fresh = (
        _all_tools_cache
        and time.time() - _all_tools_cache_time < _CACHE_TTL
        and _scan_tool_json_mtimes() == _all_tools_cache_mtimes
    )
    if cache_fresh:
        all_tools = _all_tools_cache.copy()
    else:
        tools_path = get_tools_path()
        all_tools = []

        if tools_path.exists():
            for pkg_dir in active_paths(get_base_path()):
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

        # 캐시 업데이트 (mtime 스냅샷 동반 — tool.json 변경 시 자동 무효화)
        _all_tools_cache = all_tools.copy()
        _all_tools_cache_time = time.time()
        _all_tools_cache_mtimes = _scan_tool_json_mtimes()

    from vocabulary_state import inventory, is_active
    owners = inventory()["tools"]
    all_tools = [t for t in all_tools if not owners.get(t.get("name")) or is_active(owners[t["name"]])]

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

    for pkg_dir in active_paths(get_base_path()):
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
        for tool_dir in active_paths(Path(base_path) if base_path else get_base_path()):
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
    global _tool_handlers_cache, _package_handlers_cache, _tool_to_package_map, _tool_json_mtimes, _all_tools_cache, _all_tools_cache_time, _all_tools_cache_mtimes, _agents_yaml_cache, _guide_content_cache, _tool_guide_map, _tool_guide_map_built
    _tool_handlers_cache.clear()
    _package_handlers_cache.clear()
    _package_handler_mtimes.clear()
    _tool_to_package_map.clear()
    _tool_json_mtimes.clear()
    _all_tools_cache = []
    _all_tools_cache_time = 0
    _all_tools_cache_mtimes.clear()
    _agents_yaml_cache.clear()
    _guide_content_cache.clear()
    _tool_guide_map.clear()
    _tool_guide_map_built = False
