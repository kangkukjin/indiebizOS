"""body_trust.py — 몸 신뢰 원장 (이웃 통합: "몸도 이웃이다")

폰↔맥의 특별함은 배관이 아니라 **관계(레벨)** 여야 한다 — 낯선 두 indiebizOS 가
만나 어떤 절차로 신뢰를 허용받으면 소통하듯, 내 몸들도 같은 절차를 거친다.
차이는 부여식이 자동 성립한다는 것뿐(프로비저닝 = USB 물리 점유 + 소유주의 설치
행위 = 증명). 그래야 폰↔맥이 낯선 두 indiebizOS 소통의 모델이 된다.

원장 = 이웃 명부: neighbors.info_level(숫자 0~4, 의미 라벨 금지 — 의미는 사용자가
정함) + 접점 contacts(contact_type='body', value=device_id). 창고주소 선례 그대로 —
몸의 기기 신원도 그 이웃에 닿는 접점의 한 종류다. business.db 라 두 몸이 CRDT
동기화로 같은 명부를 공유한다(자기 항목이 자기 명부에 있는 것은 무해).

전송(auth)과 신뢰(trust)의 분리: 전송층(토큰·세션)은 "너는 너다"까지만,
"무엇까지 허용되나"는 이 원장이 답한다. npub 서명 전환 때 identity 만 갈아끼운다.
"""
import time
from typing import Any, Dict, Optional

# === 정책 (숫자 레벨만) ===
ASK_MIN_LEVEL = 1           # 부탁(ask) 수신 허용 최소 레벨
PRIVILEGE_LEVELS = {
    # ★소멸 예정 특권 목록 (2026-07-22 사용자 확정 — docs/NO_PRIVILEGED_RAILS_HANDOFF.md):
    # 이 선언은 더 이상 "레벨로 집행할 게이트"가 아니라 **철거 대상 배관의 목록**이다.
    # 특권은 감독(레벨 게이트)이 아니라 소멸이 목표 — 몸 간 문법은 이웃 문법 하나
    # (명함·[others:ask]·신뢰레벨·창고)로 통일된다. 각 항목은 이웃-문법 재표현 후 제거.
    "core_delegation": 4,   # → [others:ask] (관문 자동위임 매장, 핸드오프 #2)
    "data_sync": 4,         # → 교환 문법(ask/창고/릴레이 계약, 핸드오프 #4)
    "hippo_rent": 4,        # → 폰 자기 키·자기 축적(핸드오프 #3)
}

_CONTACT_TYPE = "body"


def get_body_level(device_id: str) -> Optional[int]:
    """몸-신원 → 신뢰 레벨. 원장에 없으면 None(낯선 몸)."""
    if not device_id:
        return None
    try:
        from business_manager import BusinessManager
        n = BusinessManager().get_neighbor_by_contact(_CONTACT_TYPE, str(device_id))
        if not n:
            return None
        return int(n.get("info_level") or 0)
    except Exception:
        return None  # 원장 미가용 = 낯선 몸 취급 (fail-closed)


def grant_body(device_id: str, name: str, level: int = 4,
               granted_by: str = "provision") -> Dict[str, Any]:
    """부여식 — 몸-신원을 이웃 명부에 레벨과 함께 기록(멱등: 이미 있으면 무변경).

    레벨 조정·회수는 이웃 관리(메신저 계기)와 같은 문 — 부여식은 첫 기록만 담당.
    """
    if not device_id:
        return {"granted": False, "error": "device_id 없음"}
    from business_manager import BusinessManager
    bm = BusinessManager()
    existing = bm.get_neighbor_by_contact(_CONTACT_TYPE, str(device_id))
    if existing:
        return {"granted": False, "existing": True,
                "neighbor_id": existing.get("id"),
                "level": int(existing.get("info_level") or 0)}
    n = bm.create_neighbor(
        name=name or f"몸-{device_id[:6]}",
        info_level=int(level),
        additional_info=(f"몸(body) — 신뢰 부여식 {granted_by} "
                         f"{time.strftime('%Y-%m-%dT%H:%M:%S')}"))
    bm.add_contact(n["id"], _CONTACT_TYPE, str(device_id))
    return {"granted": True, "neighbor_id": n["id"], "level": int(level)}


def attach_npub(device_id: str, npub_hex: str) -> bool:
    """몸-이웃에 npub 접점("npub:<hex>") 부착 — 서명 신원의 원장 합류.

    우편함(ask_mailbox — Nostr DM)의 발신자는 npub 로 증명되므로, 부여식을 거친
    몸의 npub 를 같은 이웃의 접점으로 붙여야 우편함 부탁이 그 몸의 레벨로 판정된다.
    (device_id 자기보고 → npub 서명으로의 신원 승격 경로. 멱등.)
    """
    if not device_id or not npub_hex:
        return False
    key = f"npub:{npub_hex}"
    try:
        from business_manager import BusinessManager
        bm = BusinessManager()
        if bm.get_neighbor_by_contact(_CONTACT_TYPE, key):
            return True  # 이미 부착됨
        n = bm.get_neighbor_by_contact(_CONTACT_TYPE, str(device_id))
        if not n:
            return False  # 부여식 전 — npub 만으로 명부에 올리지 않는다
        bm.add_contact(n["id"], _CONTACT_TYPE, key)
        return True
    except Exception:
        return False
