"""IBL 노드 사전(레지스트리) 로더 — ibl_engine 에서 이동 (2026-08-05 감사 ⑦).

왜 분리: ibl_nodes.yaml 로드·캐시·몸-사전 설치 필터는 엔진(실행)보다 아래의
'사전' 층이다. capability_card(명함)·ibl_safety·ibl_param_vocab 등 사전만 필요한
소비자가 엔진 전체를 import 하면서 매듭의 가장 굵은 간선이 됐다(간선 하나에
매듭 -10 실측). 로드가 곧 설치 — 캐시(_nodes)는 여기가 단일 소유자다.
"""
import json
import os
from pathlib import Path
from typing import Dict, Optional

import yaml

_nodes: Optional[Dict] = None
_nodes_path: Optional[Path] = None


# === api_registry.yaml 로더 — api_engine 에서 이동 (같은 절단의 일부) ===
# api_registry 도 사전의 일부(node 바인딩 액션이 노드 사전에 병합된다).
# 실행 엔진(api_engine)은 이것을 import 해 소비만 한다.

_registry: Optional[Dict] = None
_registry_path: Optional[Path] = None


def _get_registry_path() -> Path:
    """api_registry.yaml 경로"""
    global _registry_path
    if _registry_path:
        return _registry_path
    env_path = os.environ.get("INDIEBIZ_BASE_PATH")
    if env_path:
        _registry_path = Path(env_path) / "data" / "api_registry.yaml"
    else:
        _registry_path = Path(__file__).parent.parent / "data" / "api_registry.yaml"
    return _registry_path


def _load_registry() -> Dict:
    """레지스트리 로드 (캐싱)"""
    global _registry
    if _registry is not None:
        return _registry

    path = _get_registry_path()
    if not path.exists():
        _registry = {"services": {}, "tools": {}}
        return _registry

    with open(path, "r", encoding="utf-8") as f:
        _registry = yaml.safe_load(f) or {"services": {}, "tools": {}}
    return _registry


def reload_registry():
    """레지스트리 강제 리로드"""
    global _registry
    _registry = None
    _load_registry()


def _get_nodes_path() -> Path:
    """ibl_nodes.yaml 경로"""
    global _nodes_path
    if _nodes_path:
        return _nodes_path
    env_path = os.environ.get("INDIEBIZ_BASE_PATH")
    if env_path:
        _nodes_path = Path(env_path) / "data" / "ibl_nodes.yaml"
    else:
        _nodes_path = Path(__file__).parent.parent / "data" / "ibl_nodes.yaml"
    return _nodes_path


def _merge_api_registry_actions(nodes_config: Dict):
    """api_registry의 node 필드 기반 노드 액션 자동 병합.

    api_registry.yaml 도구에 node/action_name이 선언되어 있으면
    해당 노드의 actions dict에 in-place 병합한다.
    YAML 앵커(&id005 등)가 가리키는 동일 dict를 직접 변경하므로
    nodes 섹션에도 자동 반영된다.
    """
    registry = _load_registry()
    tools = registry.get("tools", {})

    for tool_name, tool_cfg in tools.items():
        node_name = tool_cfg.get("node")
        if not node_name:
            continue

        action_name = tool_cfg.get("action_name", tool_name)
        node_cfg = nodes_config.get(node_name)
        if not node_cfg:
            continue

        actions = node_cfg.get("actions")
        if actions is None:
            actions = {}
            node_cfg["actions"] = actions

        # 수동 정의가 이미 있으면 덮어쓰지 않음
        if action_name in actions:
            continue

        action = {"router": "api_engine", "tool": tool_name}
        if tool_cfg.get("description"):
            action["description"] = tool_cfg["description"]
        if tool_cfg.get("target_key"):
            action["target_key"] = tool_cfg["target_key"]

        actions[action_name] = action


# 폰 프로파일(#3 runs_on) — runnable 액션 집합 캐시.
_phone_runnable_cache = {"loaded": False, "set": None}


def _phone_runnable(node: str, action: str) -> bool:
    """폰 프로파일이면 phone_manifest.runnable_actions 막을 적용. PC면 항상 True."""
    if os.environ.get("INDIEBIZ_PROFILE") != "phone":
        return True
    if not _phone_runnable_cache["loaded"]:
        s = None
        try:
            base = os.environ.get("INDIEBIZ_BASE_PATH") or os.path.join(os.path.dirname(__file__), "..")
            with open(os.path.join(base, "data", "phone_manifest.json"), "r", encoding="utf-8") as f:
                s = set(json.load(f).get("runnable_actions") or [])
        except Exception:
            s = None  # 매니페스트 없으면 가드 비활성(안전)
        _phone_runnable_cache["set"] = s
        _phone_runnable_cache["loaded"] = True
    rs = _phone_runnable_cache["set"]
    return True if rs is None else (f"{node}:{action}" in rs)


def _load_nodes_config() -> Dict:
    """노드 정의 로드 (캐싱)"""
    global _nodes
    if _nodes is not None:
        return _nodes

    path = _get_nodes_path()
    if not path.exists():
        _nodes = {"nodes": {}}
        return _nodes

    with open(path, "r", encoding="utf-8") as f:
        _nodes = yaml.safe_load(f) or {"nodes": {}}

    # api_registry에서 node 바인딩된 액션 자동 병합
    _merge_api_registry_actions(_nodes.get("nodes", {}))

    # 몸-사전 설치 필터(몸 독립 2단계): 배포물(yaml)=전체 사전집이지만, 이 몸의
    # 런타임에 설치되는 어휘는 자기 것만 — PC는 phone_only 를 모르고, 폰은 runnable
    # 만 안다. 남의 몸 능력은 명함(냄새)으로 알고 [others:ask] 로 부탁한다.
    # 코어(항상-on) 어휘는 양 몸 공통이라 @alias 크로스바디 포워딩이 그대로 산다.
    _prune_foreign_vocabulary(_nodes)

    return _nodes


def _prune_foreign_vocabulary(nodes_cfg: Dict) -> None:
    """카탈로그·해마 소유-필터의 실행층 완결판 — 로드가 곧 설치다."""
    try:
        from runtime_utils import detect_body
        profile = (detect_body() or {}).get("profile", "")
    except Exception:
        profile = ""
    for node_name, node_cfg in (nodes_cfg.get("nodes") or {}).items():
        actions = (node_cfg or {}).get("actions") or {}
        if profile == "phone":
            drop = [a for a in actions if not _phone_runnable(node_name, a)]
        else:
            drop = [a for a, c in actions.items()
                    if isinstance(c, dict) and c.get("runs_on") == "phone_only"]
        for a in drop:
            del actions[a]


def invalidate_nodes() -> None:
    """사전 캐시 무효화 — 다음 _load_nodes_config() 가 디스크에서 다시 읽는다.
    (ibl_engine.reload_nodes 의 캐시 리셋 부분이 여기로 위임)"""
    global _nodes
    _nodes = None
