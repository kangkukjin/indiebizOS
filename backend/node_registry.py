"""
node_registry.py - IBL 노드 레지스트리 (Phase 11)

모든 IBL 노드와 에이전트를 "노드"로 추상화하여 통일된 디스크립터를 제공합니다.
"Everything is a Node" — 리눅스의 "Everything is a file"과 같은 원리.

핵심 기능:
- list_nodes(): 모든 노드의 통일된 디스크립터 목록 (노드 + 에이전트)
- get_node(node_id): 특정 노드의 상세 디스크립터
- discover(query): 키워드로 적합한 노드/액션 자동 탐색

사용법:
    from node_registry import list_nodes, get_node, discover

    # 모든 노드 (일반 + 에이전트)
    nodes = list_nodes()

    # 일반 노드만
    nodes = list_nodes(include_agents=False)

    # 특정 노드 상세
    node = get_node("source")

    # 디스커버리: "이 작업을 할 수 있는 노드가 뭐야?"
    results = discover("주가 정보")
    # → [{"node": "source", ...}, {"node": "투자/투자컨설팅", ...}]
"""

import os
import re
import yaml
from pathlib import Path
from typing import Dict, List, Optional


# === 경로 ===

def _get_base_path() -> Path:
    env_path = os.environ.get("INDIEBIZ_BASE_PATH")
    if env_path:
        return Path(env_path)
    return Path(__file__).parent.parent


def _get_nodes_path() -> Path:
    return _get_base_path() / "data" / "ibl_nodes.yaml"


# === 캐시 ===

_node_cache: Optional[List[Dict]] = None
_agent_node_cache: Optional[List[Dict]] = None


def _invalidate_cache():
    global _node_cache, _typed_node_cache
    _node_cache = None
    _typed_node_cache = None


def invalidate_agent_cache():
    """에이전트 노드 캐시 무효화 (AgentRunner start/stop 시 호출)"""
    global _agent_node_cache
    _agent_node_cache = None


# === 노드 디스크립터 생성 ===

# 라우터 → 노드 타입 매핑
_ROUTER_TYPE_MAP = {
    "api_engine": "engine",
    "handler": "handler",
    "system": "system",
    "workflow_engine": "engine",
    "channel_engine": "engine",
    "web_collector": "engine",
    "event_engine": "engine",
    "driver": "driver",
    "stub": "stub",
}

# 라우터 → 프로토콜 매핑
_ROUTER_PROTOCOL_MAP = {
    "api_engine": "http",
    "handler": "mixed",
    "system": "internal",
    "workflow_engine": "internal",
    "channel_engine": "http/websocket",
    "web_collector": "http",
    "event_engine": "internal",
    "driver": "varies",
    "stub": "none",
}


def _build_node_descriptor(node_name: str, node_config: dict) -> dict:
    """노드 설정에서 노드 디스크립터 생성"""
    actions_config = node_config.get("actions", {})

    # 라우터 유형 결정 (가장 많이 사용된 라우터)
    router_counts = {}
    for ac in actions_config.values():
        r = ac.get("router", "unknown")
        router_counts[r] = router_counts.get(r, 0) + 1
    primary_router = max(router_counts, key=router_counts.get) if router_counts else "unknown"

    # 액션 디스크립터 리스트
    actions = []
    for action_name, action_cfg in actions_config.items():
        action_desc = {
            "name": action_name,
            "description": action_cfg.get("description", ""),
            "router": action_cfg.get("router", ""),
        }
        if action_cfg.get("target_description"):
            action_desc["target"] = action_cfg["target_description"]
        if action_cfg.get("tool"):
            action_desc["mapped_tool"] = action_cfg["tool"]
        actions.append(action_desc)

    # 설명에서 태그 추출
    description = node_config.get("description", "")
    tags = _extract_tags(description)

    return {
        "id": node_name,
        "type": _ROUTER_TYPE_MAP.get(primary_router, "unknown"),
        "protocol": _ROUTER_PROTOCOL_MAP.get(primary_router, "unknown"),
        "description": description,
        "actions": actions,
        "action_count": len(actions),
        "tags": tags,
    }


def _extract_tags(text: str) -> List[str]:
    """설명 텍스트에서 키워드 태그 추출"""
    if not text:
        return []
    # 괄호 내용, 쉼표로 분리된 항목 추출
    tags = []

    # 괄호 안 내용
    paren_matches = re.findall(r'\(([^)]+)\)', text)
    for m in paren_matches:
        for part in m.split(','):
            tag = part.strip().strip('"').strip("'")
            if tag and len(tag) < 20:
                tags.append(tag)

    # 쉼표로 분리된 항목
    for part in text.split(','):
        part = part.strip()
        if 2 <= len(part) <= 15:
            tags.append(part)

    return list(set(tags))[:10]


# === 에이전트 노드 디스크립터 생성 (Phase 11) ===

# 도구 → 노드 역매핑 (lazy load)
_TOOL_NODE_REVERSE_MAP: Optional[Dict] = None


def _get_tool_node_map() -> dict:
    """ibl_nodes.yaml에서 tool->노드 역매핑 테이블 생성 (캐시)"""
    global _TOOL_NODE_REVERSE_MAP
    if _TOOL_NODE_REVERSE_MAP is not None:
        return _TOOL_NODE_REVERSE_MAP
    path = _get_nodes_path()
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    mapping = {}
    for node_name, node_cfg in data.get("nodes", {}).items():
        for action_cfg in node_cfg.get("actions", {}).values():
            tool = action_cfg.get("tool")
            if tool:
                mapping[tool] = node_name
    _TOOL_NODE_REVERSE_MAP = mapping
    return mapping


def _map_tools_to_capabilities(allowed_tools: list) -> List[str]:
    """allowed_tools 목록을 IBL 노드 이름 집합으로 변환"""
    # allowed_tools → IBL 노드 capabilities 매핑
    tool_map = _get_tool_node_map()
    nodes = set()
    for tool_name in allowed_tools:
        if tool_name.startswith("ibl_"):
            nodes.add(tool_name.replace("ibl_", ""))
        elif tool_name in tool_map:
            nodes.add(tool_map[tool_name])
    return sorted(nodes)


def _extract_agent_tags(project_id: str, agent_name: str, role_desc: str) -> List[str]:
    """에이전트에서 태그 추출 (프로젝트명 + 에이전트명 + 역할설명)"""
    tags = [project_id, agent_name]
    if role_desc:
        tags.extend(_extract_tags(role_desc))
    return list(set(tags))[:10]


def _build_agent_descriptor(project_id: str, agent_config: dict) -> dict:
    """에이전트 설정에서 노드 디스크립터 생성"""
    agent_id = agent_config.get("id", "unknown")
    agent_name = agent_config.get("name", "unnamed")
    role_desc = agent_config.get("role_description", "")

    # allowed_tools → IBL 노드 capabilities 매핑
    capabilities = _map_tools_to_capabilities(agent_config.get("allowed_tools", []))

    # 태그: 프로젝트명 + 역할설명에서 추출
    tags = _extract_agent_tags(project_id, agent_name, role_desc)

    # 에이전트가 수행할 수 있는 "액션들" (고정: ask)
    actions = [
        {"name": "ask", "description": f"{agent_name}에게 질문/위임", "router": "system"}
    ]

    return {
        "id": f"{project_id}/{agent_name}",
        "type": "agent",
        "protocol": "delegation",
        "description": role_desc or f"{project_id} 프로젝트의 {agent_name}",
        "actions": actions,
        "action_count": len(actions),
        "tags": tags,
        # 에이전트 전용 필드
        "project_id": project_id,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "capabilities": capabilities,
        "active": agent_config.get("active", False),
    }


def _load_agent_nodes() -> List[Dict]:
    """모든 프로젝트의 agents.yaml을 스캔하여 에이전트 노드 디스크립터 생성"""
    global _agent_node_cache
    if _agent_node_cache is not None:
        return _agent_node_cache

    projects_path = _get_base_path() / "projects"
    if not projects_path.exists():
        return []

    nodes = []
    for agents_file in sorted(projects_path.glob("*/agents.yaml")):
        project_id = agents_file.parent.name
        try:
            with open(agents_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            for agent in data.get("agents", []):
                descriptor = _build_agent_descriptor(project_id, agent)
                nodes.append(descriptor)
        except Exception:
            continue

    _agent_node_cache = nodes
    return nodes


def _enrich_agent_status(agent_nodes: List[Dict]):
    """실행 중인 에이전트 레지스트리에서 상태 주입"""
    try:
        from agent_runner import AgentRunner
        for node in agent_nodes:
            registry_key = f"{node['project_id']}:{node['agent_id']}"
            runner = AgentRunner.agent_registry.get(registry_key)
            node["running"] = runner is not None and runner.running
    except ImportError:
        for node in agent_nodes:
            node["running"] = False


# === Phase 12: 타입 노드 디스크립터 ===

def _build_typed_descriptor(node_type: str, sub_name: str, sub_config: dict) -> dict:
    """타입 노드 하위 소스/저장소의 디스크립터 생성"""
    actions = []
    for action_name in sub_config.get("actions", {}).keys():
        actions.append({"name": action_name, "description": "", "router": "mixed"})

    description = sub_config.get("description", "")
    return {
        "id": f"{node_type}:{sub_name}",
        "type": node_type,
        "protocol": "mixed",
        "description": description,
        "actions": actions,
        "action_count": len(actions),
        "tags": _extract_tags(description),
        "guide": sub_config.get("guide"),
    }


_typed_node_cache: Optional[List[Dict]] = None


def _load_node_typed_descriptors() -> List[Dict]:
    """nodes: 섹션에서 타입 노드 디스크립터 생성 (Phase 12)"""
    global _typed_node_cache
    if _typed_node_cache is not None:
        return _typed_node_cache

    path = _get_nodes_path()
    if not path.exists():
        return []

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    nodes_config = data.get("nodes", {})
    descriptors = []

    for node_name, node_config in nodes_config.items():
        ntype = node_config.get("type")
        if ntype == "info":
            for src, cfg in node_config.get("sources", {}).items():
                descriptors.append(_build_typed_descriptor("info", src, cfg))
        elif ntype == "store":
            # Legacy: photo, health, blog, memory가 librarian로 통합됨 (Phase 20)
            # store 타입 노드가 YAML에 남아 있으면 여전히 디스크립터 생성
            for store, cfg in node_config.get("stores", {}).items():
                descriptors.append(_build_typed_descriptor("store", store, cfg))
        elif ntype == "exec":
            all_acts = []
            for k in node_config.get("executors", {}).keys():
                all_acts.append({"name": k, "description": "", "router": "handler"})
            for k in node_config.get("programs", {}).keys():
                all_acts.append({"name": k, "description": "", "router": "handler"})
            descriptors.append({
                "id": "exec",
                "type": "exec",
                "protocol": "mixed",
                "description": node_config.get("description", ""),
                "actions": all_acts,
                "action_count": len(all_acts),
                "tags": _extract_tags(node_config.get("description", "")),
            })
        elif ntype == "output":
            for action_name, action_cfg in node_config.get("actions", {}).items():
                descriptors.append({
                    "id": f"output:{action_name}",
                    "type": "output",
                    "protocol": "internal",
                    "description": action_cfg.get("description", f"output {action_name}"),
                    "actions": [{"name": action_name, "description": action_cfg.get("description", ""), "router": "system"}],
                    "action_count": 1,
                    "tags": _extract_tags(action_cfg.get("description", "")),
                })

    _typed_node_cache = descriptors
    return descriptors


def invalidate_typed_cache():
    """타입 노드 캐시 무효화"""
    global _typed_node_cache
    _typed_node_cache = None


# === 공개 API ===

def _load_flat_nodes() -> List[Dict]:
    """플랫 노드 로딩 (캐시)"""
    global _node_cache
    if _node_cache is not None:
        return _node_cache

    path = _get_nodes_path()
    if not path.exists():
        return []

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    flat_nodes = data.get("nodes", {})
    nodes = []
    for name, config in flat_nodes.items():
        descriptor = _build_node_descriptor(name, config)
        nodes.append(descriptor)

    _node_cache = nodes
    return nodes


def list_nodes(include_agents: bool = True) -> List[Dict]:
    """
    모든 노드의 통일된 디스크립터 목록

    Args:
        include_agents: 에이전트 노드 포함 여부 (기본: True)

    Returns:
        노드 디스크립터 리스트. 각 노드:
        {id, type, protocol, description, actions, action_count, tags}
        에이전트 노드는 추가로: {project_id, agent_id, agent_name, capabilities, active, running}
    """
    flat_nodes = _load_flat_nodes()
    typed_nodes = _load_node_typed_descriptors()

    if include_agents:
        agent_nodes = _load_agent_nodes()
        # 라이브 상태 enrichment
        _enrich_agent_status(agent_nodes)
        return flat_nodes + typed_nodes + agent_nodes

    return flat_nodes + typed_nodes


def get_node(node_id: str) -> Optional[Dict]:
    """
    특정 노드의 상세 디스크립터

    Args:
        node_id: 노드 이름 (예: "source", "forge", "stream") 또는
                에이전트 ID (예: "투자/투자컨설팅")

    Returns:
        노드 디스크립터 또는 None
    """
    for node in list_nodes():
        if node["id"] == node_id:
            return node
    return None


def discover(query: str, limit: int = 10) -> List[Dict]:
    """
    키워드로 적합한 노드/액션 자동 탐색 (노드 + 에이전트)

    "이 작업을 할 수 있는 노드가 뭐야?"를 해결.
    액션 이름 직접 매칭, verb 라우팅 참조, 사용 예시 구문을 포함한 상세 결과를 제공.

    Args:
        query: 검색 키워드 (예: "주가", "날씨", "사진", "블로그 검색")
        limit: 최대 결과 수

    Returns:
        매칭 결과 리스트 (점수순):
        [{node, description, score, matching_actions, suggestion, action_details}]
    """
    if not query:
        return []

    query_lower = query.lower()
    # 한글/영어 토큰 분리
    tokens = re.findall(r'[\w가-힣]+', query_lower)
    nodes = list_nodes()
    results = []

    # 일반적 토큰 (많은 노드에 나타나는 단어) - 가중치 축소
    _GENERIC_TOKENS = {"정보", "관리", "검색", "조회", "데이터", "목록", "실행", "서비스", "기능"}

    # verb 라우팅 정보 로드 (lazy)
    verb_routes = _load_verb_routes()

    for node in nodes:
        score = 0
        matching_actions = []
        action_details = []  # 상세 액션 정보

        # 노드 ID 매칭 (가장 강력)
        if query_lower in node["id"].lower():
            score += 20

        # 노드 설명 매칭 (핵심 매칭)
        desc_lower = node["description"].lower()
        for token in tokens:
            weight = 5 if token in _GENERIC_TOKENS else 12
            if token in desc_lower:
                score += weight

        # 태그 매칭 (정확 매칭에 높은 가중치)
        for tag in node.get("tags", []):
            tag_lower = tag.lower()
            for token in tokens:
                if token == tag_lower:
                    score += 15  # 정확 매칭
                elif token in tag_lower:
                    score += 8   # 부분 매칭

        # 각 액션 매칭 (이름 직접 매칭 + 설명 매칭)
        for action in node["actions"]:
            action_name = action["name"]
            action_name_lower = action_name.lower()
            action_desc_lower = action.get("description", "").lower()
            action_target = action.get("target", "")
            action_target_lower = action_target.lower()
            action_matched = False
            action_score = 0

            # (1) 액션 이름 직접 매칭 — 가장 정확한 신호
            for token in tokens:
                if token in action_name_lower:
                    action_score += 18  # 이름에 토큰 포함: 강한 신호
                    action_matched = True
            # 전체 쿼리가 액션 이름에 포함
            if query_lower.replace(" ", "_") == action_name_lower:
                action_score += 25  # 정확 일치 보너스
                action_matched = True

            # (2) 액션 설명 매칭
            for token in tokens:
                weight = 2 if token in _GENERIC_TOKENS else 5
                if token in action_desc_lower:
                    action_score += weight
                    action_matched = True
                elif token in action_target_lower:
                    action_score += weight
                    action_matched = True

            if action_matched:
                score += action_score
                matching_actions.append(action_name)
                # 사용 예시 구문 생성
                target_hint = action_target if action_target else "대상"
                action_details.append({
                    "action": action_name,
                    "description": action.get("description", ""),
                    "example": f'[{node["id"]}:{action_name}]("{target_hint}")',
                    "score": action_score,
                })

        # 에이전트 노드: capabilities 매칭 (보너스)
        if node["type"] == "agent":
            for cap in node.get("capabilities", []):
                for token in tokens:
                    if token in cap:
                        score += 6

        if score > 0:
            matching_actions = list(dict.fromkeys(matching_actions))
            # 액션 상세를 점수순 정렬
            action_details.sort(key=lambda x: x["score"], reverse=True)
            best_action = action_details[0]["action"] if action_details else (
                matching_actions[0] if matching_actions else (
                    node["actions"][0]["name"] if node["actions"] else "?"
                )
            )
            best_target = ""
            if action_details:
                best_target = action_details[0].get("description", "")

            # verb 라우팅 힌트
            verb_hints = _find_verb_hints(tokens, verb_routes, node["id"])

            # suggestion: verb 힌트가 있으면 그 액션을 우선 사용
            suggestion_action = best_action
            if verb_hints:
                suggestion_action = verb_hints[0]["action"]

            result = {
                "node": node["id"],
                "description": node["description"],
                "score": score,
                "matching_actions": matching_actions[:5],
                "suggestion": f'[{node["id"]}:{suggestion_action}]',
                "action_details": action_details[:5],
            }

            if verb_hints:
                result["verb_hints"] = verb_hints

            results.append(result)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


# === discover 보조 함수 ===

_verb_routes_cache: Optional[Dict] = None

def _load_verb_routes() -> Dict:
    """ibl_nodes.yaml에서 verb 라우팅 정보를 로드 (캐시)"""
    global _verb_routes_cache
    if _verb_routes_cache is not None:
        return _verb_routes_cache

    path = _get_nodes_path()
    if not path.exists():
        _verb_routes_cache = {}
        return _verb_routes_cache

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        _verb_routes_cache = {}
        return _verb_routes_cache

    verbs = {}
    # source 노드의 verbs 섹션
    source = data.get("nodes", {}).get("source", {})
    for verb_name, verb_cfg in source.get("verbs", {}).items():
        routes = verb_cfg.get("routes", {})
        default = verb_cfg.get("default", "")
        description = verb_cfg.get("description", "")
        verbs[verb_name] = {
            "description": description,
            "default": default,
            "routes": routes,
        }

    _verb_routes_cache = verbs
    return _verb_routes_cache


def _find_verb_hints(tokens: List[str], verb_routes: Dict, node_id: str) -> List[Dict]:
    """토큰에서 verb 라우팅 힌트를 찾아 반환"""
    hints = []
    # 한글 → verb 매핑
    _KO_VERB_MAP = {
        "검색": "search", "찾기": "search", "찾아": "search", "찾아줘": "search",
        "조회": "get", "확인": "get", "보기": "get", "보여": "get",
        "목록": "list", "리스트": "list",
        "생성": "create", "만들기": "create", "만들어": "create",
        "저장": "save", "기록": "save",
        "삭제": "delete",
    }

    # 한글 type → 영어 route key 매핑
    _KO_TYPE_MAP = {
        "블로그": "blog", "메모리": "memory", "기억": "memory",
        "뉴스": "news", "주식": "stock", "사진": "photos",
        "날씨": "weather", "맛집": "restaurant", "건강": "health",
        "스킬": "skill", "웹": "web", "학술": "openalex",
        "법률": "legal", "통계": "kosis", "라디오": "radio",
        "지역": "local", "쇼핑": "shopping", "투자": "stock",
        "혈압": "health", "혈당": "health", "체중": "health",
    }

    # 토큰에서 verb 및 type 후보 추출
    found_verbs = set()
    type_candidates = set()  # 영어 route key로 정규화된 타입

    for token in tokens:
        is_verb = False
        # 한글 verb 탐지
        for ko, en in _KO_VERB_MAP.items():
            if ko in token:
                found_verbs.add(en)
                is_verb = True
        # 영어 verb 직접 매칭
        if token in verb_routes:
            found_verbs.add(token)
            is_verb = True
        # type 후보: 한글은 영어로 변환 (조사 포함 부분 매칭), 영어는 그대로
        if not is_verb:
            matched_type = False
            for ko, en in _KO_TYPE_MAP.items():
                if ko in token:  # "블로그에서" → "블로그" 매칭
                    type_candidates.add(en)
                    matched_type = True
                    break
            if not matched_type:
                type_candidates.add(token)

    # verb가 없으면 search를 기본으로
    if not found_verbs and type_candidates:
        found_verbs.add("search")

    for verb in found_verbs:
        if verb not in verb_routes:
            continue
        vr = verb_routes[verb]
        routes = vr.get("routes", {})
        default_action = vr.get("default", "")

        # type 후보와 routes 매칭
        for tc in type_candidates:
            tc_lower = tc.lower()
            if tc_lower in routes:
                action = routes[tc_lower]
                hints.append({
                    "verb": verb,
                    "type": tc_lower,
                    "action": action,
                    "syntax": f'{verb}("query") {{type: "{tc_lower}"}} → [{node_id}:{action}]',
                })

        # type 매칭이 없으면 기본 액션 안내
        if not type_candidates and default_action:
            hints.append({
                "verb": verb,
                "type": "default",
                "action": default_action,
                "syntax": f'{verb}("query") → [{node_id}:{default_action}]',
            })

    return hints


def node_summary() -> Dict:
    """노드 레지스트리 요약 통계"""
    nodes = list_nodes()
    total_actions = sum(n["action_count"] for n in nodes)
    type_counts = {}
    for n in nodes:
        t = n["type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    return {
        "total_nodes": len(nodes),
        "total_actions": total_actions,
        "types": type_counts,
        "nodes": [{"id": n["id"], "actions": n["action_count"], "type": n["type"]} for n in nodes],
    }
