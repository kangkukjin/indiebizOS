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


# === 구문 검증자 슬롯 (2026-09-07 이동 — 1500줄 규칙, 서명 슬롯과 같은 성격) ===

# =============================================================================
# 원장 문 앞에서 "이게 IBL 로 파싱되나"를 물어야 하는데, 파서는 ibl 층에 살고
# datastore -> ibl 은 상향 간선이라 여기서 import 할 수 없다(층 가드 BASELINE 신규
# 추가 금지). 그래서 검사를 *주입*으로 받는다 — 조립 뿌리 boot_paths 가 모든 진입점의
# 첫 import 에서 검증자(ibl_param_vocab.code_syntax_error, 지연 import)를 이 슬롯에 꽂는다.
#
# ★슬롯이 비면 쓰기를 거절한다(RuntimeError). 비었을 때 통과시키면 이 관문은
#   '등록을 잊으면 조용히 사라지는 관문'이 되고, 그건 관문이 아니라 주석이다.
#   pre-commit 훅의 "게이트 고장이 곧 무검사가 된다"와 같은 결 — fail-closed.
#
# 왜 문에 두나(2026-09-02 실측): 기록기(ibl_usage_rag) 한 곳에만 두면 원장의 다른
# 살아있는 기록기(package_manager -> ibl_usage_generator 의 패키지 설치 시 자동 생성)가
# 무관문으로 남는다. 그건 관문이 아니라 '지금 내용이 마침 안전한 상태'다.
_CODE_VALIDATOR = None


def set_code_validator(fn) -> None:
    """구문 검증자 등록 — fn(ibl_code) -> 사유 문자열 | None(유효).

    등록처: boot_paths.wire_ledger_syntax_gate — 단 한 곳. 진입점(api·스크립트·conftest)이
    `import boot_paths` 하는 순간 배선된다. 시험은 이 함수로 가짜 검증자를 꽂을 수 있다.
    """
    global _CODE_VALIDATOR
    _CODE_VALIDATOR = fn


def _syntax_reason(ibl_code: str, function_body: bool = False) -> Optional[str]:
    """구문 사유 한 줄 (유효하면 None). 미등록이면 예외 — fail-closed.

    function_body: 관용구 골격처럼 **함수 몸**으로 읽을 것인가(2026-09-07 언어 개정) — 그 자리에선
    미할당 `$이름` 이 오타가 아니라 시그니처 슬롯이다."""
    if _CODE_VALIDATOR is None:
        raise RuntimeError(
            "[IBL Usage DB] 구문 검증자 미등록 — 원장 쓰기 거부(fail-closed). "
            "진입점이 `import boot_paths` 를 거쳤는지 확인할 것(배선처=boot_paths.wire_ledger_syntax_gate)."
        )
    try:
        return _CODE_VALIDATOR(ibl_code, function_body)
    except Exception as e:
        # 검증자 자체가 고장 = 검증 불가 = 거절. 침묵 통과는 관문의 자살.
        return f"검증자 예외: {e.__class__.__name__}: {e}"
