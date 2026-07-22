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
    # 최고 신뢰 전용 특권 선언 — 현 전송층(공유 비밀)이 사실상 집행 중이며,
    # 전송 신원이 npub 로 일반화될 때 이 선언이 실제 게이트가 된다.
    "core_delegation": 4,   # 코어 어휘 @alias 크로스바디 위임 (/ibl/execute)
    "data_sync": 4,         # business/health CRDT union 동기화
    "hippo_rent": 4,        # 해마 인덱스 렌트
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
