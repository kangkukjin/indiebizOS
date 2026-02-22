"""
ibl_action_manager.py - IBL 액션 자동 등록/해제

패키지 설치 시 ibl_actions.yaml을 읽어 ibl_nodes.yaml에 병합,
제거 시 해당 액션을 ibl_nodes.yaml에서 삭제.

_ibl_provenance.yaml로 액션 출처를 추적하여 깨끗한 제거 보장.
"""

import shutil
import yaml
from pathlib import Path
from typing import Dict, Optional


def _get_data_path() -> Path:
    return Path(__file__).parent.parent / "data"


def _get_nodes_path() -> Path:
    return _get_data_path() / "ibl_nodes.yaml"


def _get_provenance_path() -> Path:
    return _get_data_path() / "_ibl_provenance.yaml"


def _get_package_path(package_id: str) -> Path:
    return _get_data_path() / "packages" / "installed" / "tools" / package_id


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def _save_yaml(path: Path, data: dict, header: str = ""):
    with open(path, 'w', encoding='utf-8') as f:
        if header:
            f.write(header)
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _backup_nodes():
    """ibl_nodes.yaml 백업"""
    src = _get_nodes_path()
    if src.exists():
        shutil.copy2(src, src.with_suffix('.yaml.bak'))


def _load_provenance() -> dict:
    return _load_yaml(_get_provenance_path())


def _save_provenance(prov: dict):
    _save_yaml(_get_provenance_path(), prov,
               header="# 자동 생성 - 직접 편집하지 마세요\n# 액션 출처 추적: {node: {action: package_id}}\n")


def _reload_engine():
    """ibl_engine 노드 캐시 리로드"""
    try:
        from ibl_engine import reload_nodes
        reload_nodes()
    except Exception as e:
        print(f"[ibl_action_manager] reload_nodes 실패: {e}")


# ============ 메인 API ============

def register_actions(package_id: str) -> dict:
    """패키지의 ibl_actions.yaml을 ibl_nodes.yaml에 병합.

    Args:
        package_id: 패키지 ID (예: "real-estate")

    Returns:
        결과 dict (registered 액션 수, 경고 등)
    """
    pkg_path = _get_package_path(package_id)
    actions_file = pkg_path / "ibl_actions.yaml"

    if not actions_file.exists():
        return {"skipped": True, "reason": "ibl_actions.yaml 없음"}

    pkg_def = _load_yaml(actions_file)
    if not pkg_def:
        return {"skipped": True, "reason": "ibl_actions.yaml 비어있음"}

    # 패키지 정의 파싱: 단일 노드 또는 복수 노드
    node_actions = _parse_package_def(pkg_def)
    if not node_actions:
        return {"skipped": True, "reason": "등록할 액션 없음"}

    # ibl_nodes.yaml 로드 및 백업
    _backup_nodes()
    nodes_data = _load_yaml(_get_nodes_path())
    nodes = nodes_data.get("nodes", {})

    # provenance 로드
    prov = _load_provenance()

    registered = 0
    warnings = []

    for node_name, (actions, guides) in node_actions.items():
        if node_name not in nodes:
            warnings.append(f"노드 '{node_name}' 없음, 건너뜀")
            continue

        node_def = nodes[node_name]
        node_actions_dict = node_def.setdefault("actions", {})

        # provenance 노드 dict
        prov_node = prov.setdefault(node_name, {})

        for action_name, action_def in actions.items():
            # 충돌 체크: 다른 패키지 소유인 경우 경고
            existing_owner = prov_node.get(action_name)
            if existing_owner and existing_owner != package_id:
                warnings.append(
                    f"{node_name}:{action_name} 이미 '{existing_owner}' 소유, 건너뜀"
                )
                continue

            node_actions_dict[action_name] = action_def
            prov_node[action_name] = package_id
            registered += 1

        # guides 병합
        if guides:
            existing_guides = node_def.get("guides", [])
            for g in guides:
                if g not in existing_guides:
                    existing_guides.append(g)
            node_def["guides"] = existing_guides

    # 저장
    if registered > 0:
        _save_yaml(_get_nodes_path(), nodes_data)
        _save_provenance(prov)
        _reload_engine()

    result = {"registered": registered, "package": package_id}
    if warnings:
        result["warnings"] = warnings

    print(f"[ibl_action_manager] {package_id}: {registered}개 액션 등록")
    return result


def unregister_actions(package_id: str) -> dict:
    """패키지의 액션을 ibl_nodes.yaml에서 제거.

    Args:
        package_id: 패키지 ID

    Returns:
        결과 dict (removed 액션 수)
    """
    prov = _load_provenance()
    if not prov:
        return {"removed": 0, "reason": "provenance 없음"}

    # 이 패키지 소유 액션 찾기
    to_remove = {}  # {node_name: [action_names]}
    for node_name, actions in prov.items():
        owned = [a for a, owner in actions.items() if owner == package_id]
        if owned:
            to_remove[node_name] = owned

    if not to_remove:
        return {"removed": 0, "package": package_id}

    # ibl_nodes.yaml 로드 및 백업
    _backup_nodes()
    nodes_data = _load_yaml(_get_nodes_path())
    nodes = nodes_data.get("nodes", {})

    removed = 0

    for node_name, action_names in to_remove.items():
        if node_name not in nodes:
            continue

        node_actions = nodes[node_name].get("actions", {})
        prov_node = prov.get(node_name, {})

        for action_name in action_names:
            if action_name in node_actions:
                del node_actions[action_name]
                removed += 1
            if action_name in prov_node:
                del prov_node[action_name]

        # 빈 provenance 노드 정리
        if not prov_node:
            del prov[node_name]

    # guides 제거 (ibl_actions.yaml에서 확인)
    pkg_path = _get_package_path(package_id)
    actions_file = pkg_path / "ibl_actions.yaml"
    if actions_file.exists():
        pkg_def = _load_yaml(actions_file)
        pkg_nodes = _parse_package_def(pkg_def)
        for node_name, (_, guides) in pkg_nodes.items():
            if guides and node_name in nodes:
                existing = nodes[node_name].get("guides", [])
                nodes[node_name]["guides"] = [g for g in existing if g not in guides]

    # 저장
    if removed > 0:
        _save_yaml(_get_nodes_path(), nodes_data)
        _save_provenance(prov)
        _reload_engine()

    print(f"[ibl_action_manager] {package_id}: {removed}개 액션 제거")
    return {"removed": removed, "package": package_id}


def _parse_package_def(pkg_def: dict) -> Dict[str, tuple]:
    """패키지 정의에서 {node_name: (actions_dict, guides_list)} 추출.

    지원 형식:
    1. 단일 노드: node: "source", actions: {...}
    2. 복수 노드: nodes: {source: {actions: {...}}, forge: {actions: {...}}}
    """
    result = {}

    if "nodes" in pkg_def:
        # 복수 노드
        for node_name, node_def in pkg_def["nodes"].items():
            actions = node_def.get("actions", {})
            guides = node_def.get("guides", [])
            if actions:
                result[node_name] = (actions, guides)
    elif "node" in pkg_def:
        # 단일 노드
        node_name = pkg_def["node"]
        actions = pkg_def.get("actions", {})
        guides = pkg_def.get("guides", [])
        if actions:
            result[node_name] = (actions, guides)

    return result
