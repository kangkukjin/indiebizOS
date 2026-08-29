"""decision_ledger.py — 사용자 판정 원장 회상 (결정 기억).

data/decisions.yaml(단일 원장)을 읽어 회상 0단계에 두 층으로 얹는다:

  ① 다이제스트(상시) — 활성 판정의 ruling 한 줄씩. 제안·설계는 턴 **중간**에
     생기므로(2026-08-29 실측: 외부 조사 턴이 노드 스코핑 기각을 모르고 재제안 —
     사용자 메시지에는 '스코핑'이 없어 키워드 게이트로는 못 잡는다) 질의 게이트
     없이 상시 노출한다. owner 냄새·손발 프레즌스와 같은 원리, 수 백 자 수준.
  ② 상세(질의 일치) — 질의가 entry 의 keywords 에 걸리면 why·source 까지 얹는다.

규약: 판정 이름·키워드는 전부 데이터(YAML) 소유 — 이 코드에 사안 어휘를 넣지
말 것(표준/사전 경계). 판정 개정은 삭제 아닌 status: superseded (반증 가능).
실패는 무시(빈 문자열) — 회상 파이프라인 불변.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

_LEDGER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "decisions.yaml")

# mtime 캐시 — 파일이 안 변하면 매 턴 파싱 생략
_cache: Dict[str, Any] = {"mtime": None, "entries": []}


def load() -> List[Dict[str, Any]]:
    """원장 로드 (mtime 캐시). 깨진 파일·부재 = 빈 목록 (회상 불변)."""
    try:
        mtime = os.path.getmtime(_LEDGER_PATH)
    except OSError:
        return []
    if _cache["mtime"] == mtime:
        return _cache["entries"]
    try:
        import yaml
        with open(_LEDGER_PATH, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or []
        entries = [e for e in raw
                   if isinstance(e, dict) and e.get("id") and e.get("ruling")]
    except Exception as e:
        print(f"[결정원장] 로드 실패 (무시): {e}")
        return []
    _cache["mtime"] = mtime
    _cache["entries"] = entries
    return entries


def _matches(entry: Dict[str, Any], query: str) -> bool:
    if not (query or "").strip():
        return False
    from common.value_semantics import text_match  # 값 판정 한 벌(B46) — 사설 정규화 금지
    return any(text_match("contains", query, str(kw))
               for kw in (entry.get("keywords") or []))


def scent_xml(query: str = "") -> str:
    """<decision_ledger> 블록 — 활성 판정 다이제스트 + 질의 일치 상세.

    원장이 비면 빈 문자열(0토큰). scent: false 항목은 다이제스트에서 빠지고
    질의 일치 때만 나온다."""
    entries = [e for e in load() if e.get("status", "active") == "active"]
    if not entries:
        return ""

    digest_rows: List[str] = []
    detail_rows: List[str] = []
    for e in entries:
        matched = _matches(e, query)
        if e.get("scent", True) or matched:
            verdict = e.get("verdict", "")
            date = e.get("date", "")
            digest_rows.append(
                f'  <ruling id="{e["id"]}" verdict="{verdict}" date="{date}">'
                f'{e["ruling"]}</ruling>')
        if matched:
            why = " ".join(str(e.get("why", "")).split())
            src = e.get("source", "")
            detail_rows.append(
                f'  <detail id="{e["id"]}" source="{src}">{why}</detail>')

    if not digest_rows and not detail_rows:
        return ""
    note = ("사용자가 이미 내린 설계 판정의 원장이다. 기각된 방향을 재제안하거나 "
            "결정된 사안을 재론하지 마라. 뒤집으려면 그 판정을 명시 인용하고 사용자에게 "
            "재판정을 청하라. 정본=data/decisions.yaml (date 가 오래된 판정은 낡았을 수 "
            "있음을 감안하되, 폐기 판단은 사용자 몫).")
    body = "\n".join(digest_rows + detail_rows)
    return f'<decision_ledger note="{note}">\n{body}\n</decision_ledger>'
