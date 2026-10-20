"""동작별 실행 조건의 실행 전 검사 — 화면을 쓰는 탐색 도구의 호출 경계.

CONTROL_DRIVER_DESIGN_2026_10_20 §6. 실행 **후** 확인(verify_task·영수증 대조)과 다른 책임이다.
사용자와 공유하는 탭을 바꾸는 동작은 결과 확인이 아무리 정확해도 이미 방해한 뒤다.
그래서 동작마다 세 속성을 계약에 적고, 강제할 조건은 가이드가 아니라 **실행 직전 경계**가 검사한다.

- `needs_front`: 앞 앱·포커스를 요구한다. 화면을 쓸 수 없는 문맥(배경·정기 실행)이면 거절.
- `shared_state`: 사용자와 공유하는 상태(활성 탭·열린 문서·클립보드·음량)를 바꾼다.
  **요청된 효과면 실행한다.** 검사는 요청 범위 밖의 부수 간섭에만 한다.
- `isolated_resources`: 사용자 것과 분리된 **자원 목록**(screen·focus·session·account·files).
  면제권이 아니다 — 동작이 바꾸는 자원이 목록에 있을 때만 그 자원의 간섭 검사를 생략한다.

화면 사용 가능 여부는 **행위자 봉투의 출처**(thread_context.task_origin)로 판정한다.
위임 여부는 기준이 아니다 — 부모가 확보한 출처를 자식 봉투가 계승한다(delegation_tasks ENVELOPE).
`user`(주인의 직접 명령)·`training`·`test`(개발자가 입회한 리허설·검증)만 화면을 쓸 수 있고,
`scheduler`·미세팅(None: 정기 주입문·자율 경로·외부 채널)은 사용자의 손과 눈이 보는 상태를
건드릴 수 없다. 51회차의 무인 밤일 화면 찍기(L51-1)와 45회차의 입회 없는 데스크톱 입력이 이 자리다.
입력 유휴(idle_seconds)는 간섭의 크기를 가늠하는 보조 관측이지 거절 조건이 아니다.
"""
from typing import Dict, Optional

SCREEN_ORIGINS = frozenset({"user", "training", "test"})
RESOURCES = ("screen", "focus", "session", "account", "files", "clipboard")


def declare(*, needs_front: bool, shared_state: bool, isolated_resources=()) -> dict:
    """한 동작의 조건 선언. 핸들러·스크립트의 계약 표가 이 모양으로 적는다."""
    unknown = set(isolated_resources) - set(RESOURCES)
    if unknown:
        raise ValueError(f"알 수 없는 격리 자원: {sorted(unknown)}")
    return {"needs_front": bool(needs_front), "shared_state": bool(shared_state),
            "isolated_resources": sorted(isolated_resources)}


def screen_context() -> Dict:
    """지금 이 실행이 사용자의 화면을 쓸 수 있는 문맥인가. 모델 호출·OS 조회 없음."""
    try:
        import thread_context
        origin = thread_context.get_task_origin()
        chain = thread_context.get_delegation_chain()
    except Exception:
        origin, chain = None, []
    available = origin in SCREEN_ORIGINS
    return {"available": available, "origin": origin or "none",
            "delegated": bool(chain),
            "reason": None if available else (
                "정기·배경 실행" if origin == "scheduler" else
                "사용자의 직접 명령이 아닌 실행 문맥(출처 미세팅)")}


def refusal(op: str, condition: dict, context: dict, *, surface: str = "") -> Optional[dict]:
    """needs_front 동작을 화면 없는 문맥에서 거절한다. 거절이 아니면 None.

    shared_state 는 여기서 거절하지 않는다 — 동작이 곧 요청된 효과인 탐색 도구에서 핸들러는
    요청 범위를 모른다. 간섭 판단은 간섭 없는 통로를 고르는 호출자(가이드 §8 서열)의 몫이다.
    """
    if not condition.get("needs_front") or context.get("available"):
        return None
    return {
        "success": False,
        "error_code": "SCREEN_CONTEXT_UNAVAILABLE",
        "error": (f"{surface + ' ' if surface else ''}{op} 는 앞 앱·화면을 요구하는 동작(needs_front)인데 "
                  f"현재 실행 문맥({context.get('origin')})은 {context.get('reason')}이라 화면을 쓸 수 없습니다. "
                  "실행하지 않았습니다. 계약 통로(드라이버·스크립트)를 쓰거나 사용자가 입회한 턴에서 실행하세요."),
        "condition": dict(condition), "context": {k: context.get(k) for k in ("origin", "delegated")},
    }
