"""IBL 노드 사전(레지스트리) 로더 — ibl_engine 에서 이동 (2026-08-05 감사 ⑦).

왜 분리: ibl_nodes.yaml 로드·캐시·몸-사전 설치 필터는 엔진(실행)보다 아래의
'사전' 층이다. capability_card(명함)·ibl_safety·ibl_param_vocab 등 사전만 필요한
소비자가 엔진 전체를 import 하면서 매듭의 가장 굵은 간선이 됐다(간선 하나에
매듭 -10 실측). 로드가 곧 설치 — 캐시(_nodes)는 여기가 단일 소유자다.
"""
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

import yaml

_nodes: Optional[Dict] = None
_nodes_path: Optional[Path] = None


# === api_registry.yaml 로더 — api_engine 에서 이동 (같은 절단의 일부) ===
# api_registry 도 사전의 일부(node 바인딩 액션이 노드 사전에 병합된다).
# 실행 엔진(api_engine)은 이것을 import 해 소비만 한다.

_registry: Optional[Dict] = None
_registry_path: Optional[Path] = None


def _get_registry_path() -> Path:
    """api_registry.yaml 경로 — 앵커는 runtime_utils.get_base_path 하나(2026-08-24)."""
    global _registry_path
    if _registry_path:
        return _registry_path
    from runtime_utils import get_base_path
    _registry_path = get_base_path() / "data" / "api_registry.yaml"
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

    try:
        with open(path, "r", encoding="utf-8") as f:
            _registry = yaml.safe_load(f) or {"services": {}, "tools": {}}
    except Exception as e:
        # 부재≠파손: 없는 파일은 조용히 빈 값이지만, 깨진 파일을 눙치면 node 바인딩
        # 액션이 통째로 증발한 채 몸이 돈다. ibl_access.load_nodes_raw 와 같은 방침.
        raise RuntimeError(
            f"API 레지스트리가 깨졌습니다 — {path} 를 읽을 수 없습니다: {e}\n"
            f"→ 빌드 중이었다면 잠시 후 재시도하세요."
        ) from e
    return _registry


def reload_registry():
    """레지스트리 강제 리로드"""
    global _registry
    _registry = None
    _load_registry()


def _get_nodes_path() -> Path:
    """ibl_nodes.yaml 경로 — 앵커는 runtime_utils.get_base_path 하나(2026-08-24)."""
    global _nodes_path
    if _nodes_path:
        return _nodes_path
    from runtime_utils import get_base_path
    _nodes_path = get_base_path() / "data" / "ibl_nodes.yaml"
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
            from runtime_utils import get_base_path   # 경로 앵커 단일화(2026-08-24)
            with open(get_base_path() / "data" / "phone_manifest.json",
                      "r", encoding="utf-8") as f:
                s = set(json.load(f).get("runnable_actions") or [])
        except Exception:
            s = None  # 매니페스트 없으면 가드 비활성(안전)
        _phone_runnable_cache["set"] = s
        _phone_runnable_cache["loaded"] = True
    rs = _phone_runnable_cache["set"]
    return True if rs is None else (f"{node}:{action}" in rs)


def load_nodes_installed() -> Dict:
    """**이 몸에 설치된** 사전 로드 (캐싱).

    사전 이음매(2026-08-24 계약화). 같은 ibl_nodes.yaml 을 읽는 로더가 둘인데 의미가 다르다:
      - `ibl_access.load_nodes_raw`  = 원본 사전집(생 yaml, 배포물 전체)
      - 이 함수                      = 설치본 = 원본 + api_registry 병합 + 몸-필터(prune)
    설치는 몸의 의미론(detect_body 기반)이라 언어(ibl 층)가 아니라 여기(datastore)에 산다.
    ibl 층이 소비하는 공개 표면: load_nodes_installed · invalidate_nodes · pruned_reason ·
    self_can_run · foreign_actions · code_is_own · _load_registry/reload_registry.
    """
    global _nodes
    if _nodes is not None:
        return _nodes

    path = _get_nodes_path()
    if not path.exists():
        _nodes = {"nodes": {}}
        return _nodes

    try:
        with open(path, "r", encoding="utf-8") as f:
            _nodes = yaml.safe_load(f) or {"nodes": {}}
    except Exception as e:
        # 부재≠파손 — ibl_access.load_nodes_raw 와 같은 방침. 깨진 원장을 {"nodes":{}} 로
        # 눙치면 이 몸의 설치 어휘가 통째로 0이 된 채 조용히 돈다.
        raise RuntimeError(
            f"어휘 원장이 깨졌습니다 — {path} 를 읽을 수 없습니다: {e}\n"
            f"→ 빌드 중이었다면 잠시 후 재시도, 아니면 "
            f"`python3 scripts/build_ibl_nodes.py` 로 재생성하세요."
        ) from e

    # api_registry에서 node 바인딩된 액션 자동 병합
    _merge_api_registry_actions(_nodes.get("nodes", {}))

    # 몸-사전 설치 필터(몸 독립 2단계): 배포물(yaml)=전체 사전집이지만, 이 몸의
    # 런타임에 설치되는 어휘는 자기 것만 — PC는 phone_only 를 모르고, 폰은 runnable
    # 만 안다. 남의 몸 능력은 명함(냄새)으로 알고 [others:ask] 로 부탁한다.
    # 코어(항상-on) 어휘는 양 몸 공통이라 @alias 크로스바디 포워딩이 그대로 산다.
    _prune_foreign_vocabulary(_nodes)

    return _nodes


_pruned_foreign: Dict[str, str] = {}  # "node:action" → 사유 — 오류문 정직화용 (★F15)


def _prune_foreign_vocabulary(nodes_cfg: Dict) -> None:
    """카탈로그·해마 소유-필터의 실행층 완결판 — 로드가 곧 설치다."""
    try:
        from runtime_utils import detect_body
        profile = (detect_body() or {}).get("profile", "")
    except Exception:
        profile = ""
    _pruned_foreign.clear()
    for node_name, node_cfg in (nodes_cfg.get("nodes") or {}).items():
        actions = (node_cfg or {}).get("actions") or {}
        if profile == "phone":
            drop = [a for a in actions if not _phone_runnable(node_name, a)]
            reason = "이 폰 몸에서 실행 불가"
        else:
            drop = [a for a, c in actions.items()
                    if isinstance(c, dict) and c.get("runs_on") == "phone_only"]
            reason = "폰 전용(phone_only)"
        for a in drop:
            _pruned_foreign[f"{node_name}:{a}"] = reason
            del actions[a]


def pruned_reason(node: str, action: str) -> Optional[str]:
    """★F15 (2026-08-17 상상훈련 12회차): 이 액션이 사전집(yaml)에는 실존하지만 이 몸의
    설치에서 걷혔다면 그 사유. "액션이 없습니다"(유령)와 "이 몸의 사전에 없습니다"
    (다른 몸의 어휘)는 다른 상태다 — 전자로 접으면 오류문이 거짓말이 된다.
    """
    load_nodes_installed()  # prune 이 아직 안 돌았으면 채운다
    return _pruned_foreign.get(f"{node}:{action}")


def invalidate_nodes() -> None:
    """사전 캐시 무효화 — 다음 load_nodes_installed() 가 디스크에서 다시 읽는다.
    (ibl_engine.reload_nodes 의 캐시 리셋 부분이 여기로 위임)"""
    global _nodes
    _nodes = None


# === 사전 소유 판정 — capability_card 에서 이동 (2026-08-05 ⑦) ===
# "이 코드가 내 사전인가"는 사전(여기)의 질문 — 해마(ibl_usage_db)·카탈로그(ibl_access)
# 가 명함 모듈을 import 하지 않게 한다. 명함(카드 조립)은 capability_card 에 남는다.

def self_can_run(node: str, action: str, cfg: dict) -> bool:
    """이 몸이 이 액션을 실제 실행할 수 있는가 (명함=자기 능력만)."""
    if cfg.get("router") == "stub":
        return False
    if cfg.get("prompt_hidden"):
        return False  # 내 AI 어휘 밖 — 부탁이 와도 컴파일 못 함
    # 포크-가드: 프로파일 직접 분기 금지 — detect_body 경유(감지하되 적어주지 않음).
    try:
        from runtime_utils import detect_body
        profile = (detect_body() or {}).get("profile", "")
    except Exception:
        profile = ""
    if profile == "phone":
        return _phone_runnable(node, action)
    return cfg.get("runs_on") != "phone_only"


_ACT_RE = re.compile(r"\[([a-z_]+):([a-z_0-9]+)\]")


def foreign_actions(code: str) -> List[str]:
    """코드에서 이 몸이 실행할 수 없는 액션 목록 — 소유 판정의 단일 구현.

    ★미지 액션도 남의 어휘로 친다: 설치 필터(물리 분리, `_prune_foreign_vocabulary`)
    후 남의 몸 어휘는 이 몸의 레지스트리에 아예 없어 '미지'로 나타난다(맥의
    limbs:phone 실측). 사전에 없는 것 = 이 몸이 실행할 수 없는 것(폐어휘 포함).
    예외는 삼키지 않는다 — fail-open 이 필요한 호출자는 code_is_own 을 쓸 것.
    """
    nodes = load_nodes_installed().get("nodes") or {}
    bad: List[str] = []
    for node, action in _ACT_RE.findall(code or ""):
        cfg = (nodes.get(node, {}).get("actions") or {}).get(action)
        if cfg is None or not self_can_run(node, action, cfg):
            bad.append(f"{node}:{action}")
    return bad


def code_is_own(code: str) -> bool:
    """IBL 코드가 이 몸의 사전으로만 구성돼 있는가 — 소유-필터(해마 회상·학습)용.

    몸 독립 원칙: 남의 몸 어휘(맥의 phone_only, 폰의 비-runnable)는 학습·회상 대상이
    아니다. 상대 능력은 명함(냄새)으로 알고 [others:ask]로 부탁한다.
    ★미지=남의 것: 물리 분리 후 남의 어휘는 레지스트리에 없어 '미지'로만 보이므로,
    옛 '미지=판정 밖(열어둠)' 방침은 남의 용례를 통째로 통과시켰다(실측: 맥 해마가
    limbs:phone 용례를 회상 → 컴파일러가 남의 몸 어휘로 번역).
    """
    try:
        return not foreign_actions(code)
    except Exception:
        return True  # 판정 불가(레지스트리 로드 실패 등) 시 열어둠 — 소유-필터가 회상을 깨서는 안 됨


