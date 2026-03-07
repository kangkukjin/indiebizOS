"""
ibl_access.py - IBL Node Access Control & Environment Builder

에이전트의 IBL 환경을 정의하고 접근을 제어합니다.

핵심 개념:
    에이전트 = 허용된 노드들 + 각 노드의 액션들 + 동료 에이전트들
    IBL은 에이전트가 자신의 환경을 명확히 인식할 수 있게 하는 언어.

    환경 = 노드 (ibl_nodes.yaml)
         + 동료 에이전트 노드 (같은 프로젝트의 다른 에이전트)

함수:
    resolve_allowed_nodes() : allowed_nodes → 노드 집합
    check_node_access()     : 노드 접근 가능 여부 (hard enforcement)
    build_environment()     : 에이전트 환경 프롬프트 동적 생성 (soft enforcement)
"""

import os
import yaml
from pathlib import Path
from typing import List, Optional, Set, Dict


# 항상 허용되는 인프라 노드
# Phase 19-22: system, team
# Phase 23: 5-노드 체계 (system→self, team→others)
_ALWAYS_ALLOWED = {"self", "others"}


# ============ 접근 제어 ============

def resolve_allowed_nodes(allowed_nodes: Optional[List[str]]) -> Optional[Set[str]]:
    """
    agents.yaml의 allowed_nodes를 실제 노드 이름 집합으로 확장.

    Returns:
        허용된 노드 집합. None이면 모든 노드 허용.

    Examples:
        None / []           → None (제한 없음)
        ["sense"]           → {"sense", "self", "others"}
        ["sense", "engines"]  → {"sense", "engines", "self", "others"}
        ["limbs"]           → {"limbs", "self", "others"}
    """
    if not allowed_nodes:
        return None

    groups = _load_node_groups()
    resolved = set()

    for entry in allowed_nodes:
        entry = str(entry).strip()
        if entry in groups:
            resolved.update(groups[entry])
        elif entry.startswith("info:") or entry.startswith("store:"):
            # 하위 호환: "info:legal", "store:photo" 등 → sense
            resolved.add("sense")
        elif ":" in entry and not entry.endswith(":*"):
            _, sub = entry.split(":", 1)
            resolved.add(sub)
        else:
            resolved.add(entry)

    resolved.update(_ALWAYS_ALLOWED)
    return resolved


def check_node_access(node: str, allowed: Optional[Set[str]]) -> bool:
    """노드 접근 가능 여부. allowed가 None이면 항상 True."""
    if allowed is None:
        return True
    return node in allowed


def get_denied_message(node: str, allowed: Set[str]) -> dict:
    """접근 거부 에러 메시지"""
    user_nodes = sorted(allowed - _ALWAYS_ALLOWED)
    return {
        "error": f"노드 '{node}'에 대한 접근 권한이 없습니다.",
        "allowed_nodes": user_nodes,
        "hint": "agents.yaml의 allowed_nodes에 해당 노드를 추가하세요."
    }


# ============ 환경 프롬프트 생성 ============

def build_environment(
    allowed_nodes: Optional[List[str]] = None,
    project_path: Optional[str] = None,
    agent_id: Optional[str] = None
) -> str:
    """
    에이전트의 IBL 환경 프롬프트를 동적 생성.

    에이전트는 이 프롬프트를 통해 자신의 환경을 인식합니다:
    1. 노드: ibl_nodes.yaml에서 허용된 노드와 액션
    2. 동료 에이전트 노드: 같은 프로젝트의 다른 에이전트 (위임 가능)

    Args:
        allowed_nodes: agents.yaml의 allowed_nodes. None/[]이면 전체 노드.
        project_path: 프로젝트 경로 (동료 에이전트 탐색용)
        agent_id: 현재 에이전트 ID (자신을 제외하기 위해)

    Returns:
        환경 프롬프트 문자열
    """
    nodes_data = _load_nodes_data()
    if not nodes_data:
        return ""

    allowed = resolve_allowed_nodes(allowed_nodes)
    nodes = nodes_data.get("nodes", {})

    # 허용된 노드만 필터링
    if allowed is not None:
        visible = {k: v for k, v in nodes.items() if k in allowed}
    else:
        visible = nodes

    if not visible:
        return ""

    parts = []
    parts.append("<ibl_executor>")

    # 환경 선언
    node_names = sorted(visible.keys())
    constraint = nodes_data.get("meta", {}).get("constraint", "")
    parts.append(f'<nodes available="{", ".join(node_names)}">')
    if constraint:
        parts.append(f"<constraint>{constraint}</constraint>")

    # 사용법: YAML meta.usage에서 동적 로드
    usage = nodes_data.get("meta", {}).get("usage", [])
    if usage:
        parts.append("<usage>")
        for mode in usage:
            section = mode['section']
            parts.append(f"<mode name=\"{section}\">")
            for ex in mode.get("examples", []):
                parts.append(f"  {ex}")
            if mode.get("note"):
                parts.append(f"  NOTE: {mode['note']}")
            parts.append("</mode>")
        parts.append("</usage>")

    # 노드 상세
    for node_name, node_config in visible.items():
        desc = node_config.get("description", "")
        actions = node_config.get("actions", {})
        if not actions:
            continue

        parts.append(f'<node name="{node_name}" description="{desc}">')

        # category별 그룹화 (프롬프트 가독성용, 런타임 매핑 없음)
        categorized = {}  # category -> [action_name, ...]
        uncategorized = []  # [(action_name, action_config), ...]
        for action_name, action_config in actions.items():
            cat = action_config.get("category") if isinstance(action_config, dict) else None
            if cat:
                categorized.setdefault(cat, []).append(action_name)
            else:
                uncategorized.append((action_name, action_config))

        if categorized:
            parts.append("<action-categories>")
            for cat_name, action_names in categorized.items():
                if len(action_names) > 10:
                    names_str = ", ".join(action_names[:7]) + f" 등 {len(action_names)}개"
                else:
                    names_str = ", ".join(action_names)
                parts.append(f'  <category name="{cat_name}" actions="{names_str}"/>')
            parts.append("</action-categories>")

        if uncategorized:
            parts.append("<actions>")
            for action_name, action_config in uncategorized:
                action_desc = action_config.get("description", "") if isinstance(action_config, dict) else ""
                parts.append(f'  <action name="{action_name}" description="{action_desc}"/>')
            parts.append("</actions>")

        parts.append("</node>")

    parts.append("</nodes>")

    # 동료 에이전트 노드
    peers = _load_peer_agents(project_path, agent_id)
    if peers:
        parts.append("<peers>")
        for peer in peers:
            name = peer["name"]
            role = peer.get("role", "")
            parts.append(f'  <agent name="{name}" role="{role}" call=\'[others:delegate]{{agent_id: "{name}", message: "..."}}\'/>')
        parts.append("</peers>")

    # 파이프라인: YAML meta.pipeline에서 동적 로드
    pipeline = nodes_data.get("meta", {}).get("pipeline", [])
    if pipeline:
        parts.append("<pipeline>")
        for p in pipeline:
            parts.append(f'  <op symbol="{p["op"]}" name="{p["name"]}" example="{p["example"]}"/>')
        parts.append("</pipeline>")

    # 핵심 원칙: YAML meta.principles에서 동적 로드
    principles = nodes_data.get("meta", {}).get("principles", [])
    if principles:
        parts.append("<principles>")
        for p in principles:
            parts.append(f"  <rule>{p}</rule>")
        if peers:
            parts.append(f"  <rule>Use [others:delegate] to delegate tasks to peer agents ({len(peers)} available)</rule>")
        parts.append("</principles>")

    parts.append("</ibl_executor>")

    return "\n".join(parts)


# ============ 내부 함수 ============

_node_groups_cache = None
_nodes_data_cache = None


def _load_peer_agents(project_path: Optional[str], agent_id: Optional[str]) -> List[Dict]:
    """
    같은 프로젝트의 다른 에이전트 목록 로드.

    에이전트는 동료 에이전트를 인식하여 [others:delegate]로 위임할 수 있다.
    자기 자신은 제외한다.

    Args:
        project_path: 프로젝트 경로
        agent_id: 현재 에이전트 ID (제외용)

    Returns:
        동료 에이전트 정보 리스트: [{name, role, id}, ...]
    """
    if not project_path:
        return []

    agents_file = Path(project_path) / "agents.yaml"
    if not agents_file.exists():
        return []

    try:
        with open(agents_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return []

    agents = data.get("agents", [])
    peers = []

    for agent in agents:
        aid = agent.get("id", "")
        # 자기 자신 제외, 비활성 에이전트 제외
        if aid == agent_id:
            continue
        if not agent.get("active", True):
            continue

        peers.append({
            "id": aid,
            "name": agent.get("name", aid),
            "role": agent.get("role", agent.get("role_description", "")),
        })

    return peers


def _get_base_path() -> Path:
    env_path = os.environ.get("INDIEBIZ_BASE_PATH")
    if env_path:
        return Path(env_path)
    return Path(__file__).parent.parent


def _get_nodes_path() -> Path:
    return _get_base_path() / "data" / "ibl_nodes.yaml"


def _load_nodes_data() -> dict:
    """ibl_nodes.yaml 전체 로드 (캐시)"""
    global _nodes_data_cache
    if _nodes_data_cache is not None:
        return _nodes_data_cache

    path = _get_nodes_path()
    if not path.exists():
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        _nodes_data_cache = data
        return data
    except Exception:
        return {}


def _load_node_groups() -> dict:
    """nodes: 섹션에서 그룹 매핑 로드 (캐시)

    하위 호환:
      - "info:*", "store:*" 등 그룹 접두어 → resolve_allowed_nodes에서 처리
      - 5-노드 체계: sense, self, limbs, others, engines
    """
    global _node_groups_cache
    if _node_groups_cache is not None:
        return _node_groups_cache

    data = _load_nodes_data()
    groups = {}
    nodes = data.get("nodes", {})

    for node_name, node_config in nodes.items():
        ntype = node_config.get("type")
        if ntype == "store":
            # 하위 호환: store:* → self (Phase 25: librarian → self로 통합됨)
            groups["store:*"] = ["self"]
        elif ntype == "exec":
            groups["exec:*"] = ["fs"]
        elif ntype == "output":
            groups["output:*"] = ["output"]

    # 하위 호환: info 그룹 → sense 노드로 매핑
    # (info 타입 노드 → informant → sense로 통합됨, Phase 25)
    groups["info:*"] = ["sense"]

    _node_groups_cache = groups
    return groups


def invalidate_cache():
    """모든 캐시 무효화"""
    global _node_groups_cache, _nodes_data_cache
    _node_groups_cache = None
    _nodes_data_cache = None
