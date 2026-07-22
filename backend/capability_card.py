"""capability_card.py — 몸의 명함 (실험 1: 몸 독립 소통 연구)

두 indiebizOS 가 서로의 어휘를 통째로 학습하는 대신, 각자 자기 레지스트리에서
파생한 자기소개(명함)를 주고받는다. 연구 질문: "공통어휘(표준 코어)는 주어졌다
치고, 명함 교환만으로 서로 소통할 수 있는가."

명함 원칙 (설계 결정):
- 손으로 쓰지 않는다 — 레지스트리(빌드 산출물=단일 진실)에서 파생. 진실과 어긋날 수 없음.
- 표준 코어(always_on 노드: self/others/table)는 싣지 않는다 — 공통어휘 전제.
  standard.core_nodes 로 목록만 표기(버전 대조용).
- desc 만 싣고 파라미터 시그니처는 싣지 않는다 — 상대는 내 코드를 조립하지 않는다.
  자연어로 부탁하고, params 는 내 컴파일러(내 AI + 내 사전)의 일.
- 각 몸은 자기가 실제 실행 가능한 것만 소개한다: 폰=phone_manifest.runnable_actions,
  컴퓨트 몸=phone_only 제외. AI 어휘 밖(prompt_hidden)·미구현(stub)도 제외 —
  부탁받아도 내 컴파일러가 못 찾는 것을 광고하지 않는다.
- dictionary_hash 로 신선도 대조(같은 사전=같은 명함, 어휘 변경=hash 변경 → 재교환).
"""
import hashlib
import json
import os
import re
import time
from typing import Any, Dict, List


def _registry() -> Dict:
    from ibl_engine import _load_nodes_config
    return _load_nodes_config() or {"nodes": {}}


def _self_can_run(node: str, action: str, cfg: dict) -> bool:
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
        from ibl_engine import _phone_runnable
        return _phone_runnable(node, action)
    return cfg.get("runs_on") != "phone_only"


_ACT_RE = re.compile(r"\[([a-z_]+):([a-z_0-9]+)\]")


def code_is_own(code: str) -> bool:
    """IBL 코드가 이 몸의 사전으로만 구성돼 있는가 — 소유-필터(해마 회상·카탈로그)용.

    몸 독립 원칙: 남의 몸 어휘(맥의 phone_only, 폰의 비-runnable)는 학습·회상 대상이
    아니다. 상대 능력은 명함(냄새)으로 알고 [others:ask]로 부탁한다.
    미지 액션은 소유 판정 밖(실행이 판정) — 여기선 '남의 것으로 확인된 것'만 거른다.
    """
    try:
        nodes = _registry().get("nodes") or {}
        for node, action in _ACT_RE.findall(code or ""):
            cfg = (nodes.get(node, {}).get("actions") or {}).get(action)
            if cfg is not None and not _self_can_run(node, action, cfg):
                return False
        return True
    except Exception:
        return True  # 판정 불가 시 열어둠 — 소유-필터가 실행을 깨서는 안 됨


def _action_entry(node: str, action: str, cfg: dict) -> Dict[str, Any]:
    entry: Dict[str, Any] = {"act": f"{node}:{action}",
                             "desc": cfg.get("description", "")}
    ops = cfg.get("ops")
    if isinstance(ops, dict) and isinstance(ops.get("values"), dict):
        entry["ops"] = list(ops["values"].keys())
    return entry


def build_card(detail: str = "full") -> Dict[str, Any]:
    """자기 명함 파생. detail: full(액션 desc 전부) | summary(노드·그룹 집계만)."""
    data = _registry()
    nodes = data.get("nodes", {})

    core_nodes = sorted(n for n, c in nodes.items() if c.get("always_on"))
    capabilities: List[Dict[str, Any]] = []
    total = 0
    for node_name, node_cfg in nodes.items():
        if node_cfg.get("always_on"):
            continue  # 표준 코어 — 공통어휘 전제, 소개 불필요
        actions = node_cfg.get("actions", {}) or {}
        entries = [
            _action_entry(node_name, a, c)
            for a, c in actions.items()
            if _self_can_run(node_name, a, c)
        ]
        if not entries:
            continue
        total += len(entries)
        cap: Dict[str, Any] = {
            "node": node_name,
            "desc": node_cfg.get("description", ""),
            "count": len(entries),
        }
        if detail == "summary":
            groups: Dict[str, int] = {}
            for a, c in actions.items():
                if _self_can_run(node_name, a, c):
                    g = c.get("group", "-")
                    groups[g] = groups.get(g, 0) + 1
            cap["groups"] = groups
        else:
            cap["actions"] = entries
        capabilities.append(cap)

    # hash 는 full 프로젝션 기준(사전의 지문) — detail 과 무관하게 동일해야
    # "명함이 낡았는가" 대조에 쓸 수 있다.
    full_proj = [
        _action_entry(n, a, c)
        for n, ncfg in nodes.items() if not ncfg.get("always_on")
        for a, c in (ncfg.get("actions", {}) or {}).items()
        if _self_can_run(n, a, c)
    ]
    canonical = json.dumps(full_proj, ensure_ascii=False, sort_keys=True)
    dictionary_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]

    try:
        from runtime_utils import detect_body
        body = detect_body()
    except Exception:
        body = {"profile": "unknown"}  # detect_body 불가 시 — 포크-가드: env 직접 참조 금지

    return {
        "kind": "indiebiz-capability-card",
        "version": 1,
        "body": body,
        "standard": {
            "core_nodes": core_nodes,   # 공통어휘 — 명함에 안 싣는 부분의 선언
            "grammar": "[node:action]{params} · 파이프 >> · 병렬 & · 폴백 ??",
        },
        "dictionary_hash": dictionary_hash,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "action_count": total,
        "capabilities": capabilities,
    }
