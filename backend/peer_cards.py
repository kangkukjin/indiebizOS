"""peer_cards.py — 이웃 몸 명함 교환·캐시 (실험 3: 몸 독립 소통 연구)

상대 몸의 /nodes/card 를 가져와 캐시하고, 프롬프트에 넣을 냄새(요약)를 만든다.

원칙:
- 명함은 사전이 아니라 **냄새** — 절대 내 레지스트리에 합치지 않는다. 목적은
  "이 주제는 저 몸에 부탁할 수 있다"는 어포던스 인지(포식 owner_model 과 같은 지위).
- 캐시 = data/peer_cards/<alias>.json (명함 원문 + _fetched_at/_source_url).
  dictionary_hash 동일 → 본문 갱신 생략(시각만 갱신). 어휘 변경 → hash 변경 → 자동 교체.
- 프롬프트 주입은 요약(scent_text)만 — 노드 한 줄씩, 몸당 수백 토큰 이하.
"""
import json
import os
import re
import time
from typing import Dict, List, Optional


def _dir() -> str:
    base = os.environ.get("INDIEBIZ_BASE_PATH") or os.path.join(os.path.dirname(__file__), "..")
    d = os.path.join(base, "data", "peer_cards")
    os.makedirs(d, exist_ok=True)
    return d


def _safe_name(alias: str) -> str:
    return re.sub(r"[^\w가-힣.-]", "_", alias or "peer")[:40]


def fetch_and_cache(url: str, alias: str, headers: Optional[Dict] = None,
                    timeout: float = 10.0) -> Optional[Dict]:
    """상대 몸의 명함을 가져와 캐시. 실패=None(캐시 보존 — 명함은 낡아도 냄새로 유효)."""
    try:
        import requests
        r = requests.get(f"{url.rstrip('/')}/nodes/card", headers=headers or {},
                         timeout=timeout)
        if r.status_code != 200:
            return None
        card = r.json()
        if card.get("kind") != "indiebiz-capability-card":
            return None
    except Exception:
        return None

    path = os.path.join(_dir(), f"{_safe_name(alias)}.json")
    try:
        old = None
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                old = json.load(f)
        card["_source_url"] = url
        card["_alias"] = alias
        card["_fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        if old and old.get("dictionary_hash") == card.get("dictionary_hash"):
            old["_fetched_at"] = card["_fetched_at"]
            card = old  # 어휘 불변 — 본문 유지(시각만)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(card, f, ensure_ascii=False)
    except Exception:
        pass
    return card


def load_all() -> List[Dict]:
    out = []
    try:
        for fn in sorted(os.listdir(_dir())):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(_dir(), fn), "r", encoding="utf-8") as f:
                    out.append(json.load(f))
            except Exception:
                continue
    except Exception:
        pass
    return out


def scent_text() -> str:
    """캐시된 이웃 명함들의 냄새 요약 — 프롬프트 주입용. 없으면 ""(비용 0)."""
    cards = load_all()
    if not cards:
        return ""
    lines = ["# 이웃 몸 명함 (냄새 — 내 어휘 아님. 필요하면 자연어로 그 몸에 부탁)"]
    for c in cards:
        label = (c.get("body") or {}).get("label") or c.get("_alias") or "이웃 몸"
        caps = c.get("capabilities") or []
        node_bits = []
        for cap in caps:
            desc = (cap.get("desc") or "").split("—")[0].strip()
            node_bits.append(f"{cap.get('node')}({cap.get('count')}: {desc[:40]})")
        lines.append(f"- **{c.get('_alias', label)}** [{label}] 액션 {c.get('action_count')}개"
                     f" · 사전 {c.get('dictionary_hash')} · " + " / ".join(node_bits))
    return "\n".join(lines)
