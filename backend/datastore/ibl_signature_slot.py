"""ibl_signature_slot.py — 이름 붙은 프로그램의 호출 서명 계산자 슬롯 (2026-09-06).

원장(datastore)에서 떼어 낸 이유는 두 가지다: ①`ibl_usage_db` 가 1500줄 규칙에 닿았고
②서명 계약은 원장의 저장 로직과 별개의 한 가지 일이라 한 파일이 맞다. 원장은 이 모듈의
`signature_of`/`parse_signature` 를 그대로 쓰고, 조립 뿌리(boot_paths)가 계산자를 꽂는다.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# =============================================================================
# 서명 계산자 슬롯 — 층 계약 역전 (2026-09-06)
# =============================================================================
# 이름 붙은 프로그램의 *서명*(바깥에서 줘야 하는 $이름 목록)은 실행기가 정한다
# (workflow_contract._free_vars — `[fn:이름]` 이 인자 누락을 판정하는 바로 그 함수).
# 표시 쪽이 `${…}` 정규식으로 따로 세면 두 소스가 갈라진다: 09-06 실측으로 이름 붙은
# 45건 중 10건(22%)의 표시 서명이 실행 요구와 어긋났고, 그중 5건은 표시가 `{}` 라
# 가르친 대로 부르면 100% "인자 누락"으로 거절됐다 — 이것이 `[fn:]` 호출 0 의 뿌리다.
#
# 그래서 서명은 원장 *문*에서 한 번 계산해 저장한다(기록기마다가 아니라 문에 —
# 구문 게이트가 문에 있는 것과 같은 이유: 다른 기록기가 무관문으로 남지 않게).
# 파서가 없는 몸(폰 번들)은 계산자가 안 꽂혀 NULL 로 남고, 표시 쪽이 '미상'으로 읽어
# 옛 정규식 폴백을 쓴다 — 거짓 `{}` 를 가르치는 것보다 낫다.
_SIGNATURE_FN = None


def set_signature_computer(fn) -> None:
    """서명 계산자 등록 — fn(ibl_code) -> list[str] | None(계산 불가).

    등록처: boot_paths.wire_ledger_signature — 단 한 곳(조립 뿌리).
    """
    global _SIGNATURE_FN
    _SIGNATURE_FN = fn


def signature_of(ibl_code: str) -> Optional[str]:
    """서명 문자열(공백 구분) 또는 None(미계산 — 계산자 미등록·파스 실패)."""
    if _SIGNATURE_FN is None:
        return None
    try:
        names = _SIGNATURE_FN(ibl_code)
    except Exception as e:
        logger.debug(f"[IBL Usage DB] 서명 계산 실패: {e.__class__.__name__}: {e}")
        return None
    if names is None:
        return None
    return " ".join(str(n) for n in names)


def parse_signature(raw):
    """저장된 서명 → (names, known). known=False 면 미계산(표시 쪽이 폴백해야 한다)."""
    if raw is None:
        return ([], False)
    raw = str(raw).strip()
    if not raw:
        return ([], True)          # 계산됐고 인자가 없다 — `[fn:이름]{}` 가 참인 자리
    return (raw.split(), True)


