"""대화 HTTP 입구의 턴 확보 — 턴을 열지 못한 요청은 모델 호출·원격 제출 전에 명시 응답으로 끝난다."""
from fastapi import HTTPException

import conversation_sessions as sessions


def open_turn(path, table, owner, surface):
    """같은 소유자의 현재 세션에 턴을 연다. 반환 (store, binding).

    실행 중인 턴이 있으면 409, 대화 저장소 장애면 재시도 가능한 503 이다. 세션 채팅 입구
    (api_chat_sessions.send)와 같은 동시성 정책이며 새 자동 세션이나 별도 큐를 만들지 않는다.
    내부 IBL 재진입(/ibl/execute)은 부모 턴의 binding 을 채택할 뿐 이 함수를 지나지 않는다."""
    try:
        return sessions.open_turn(path, table, owner)
    except sessions.TurnUnavailable as exc:
        from episode_logger import record_trajectory_event
        record_trajectory_event("conversation.binding_refused", {
            "surface": surface, "owner": owner, "kind": exc.kind, "reason": str(exc)})
        raise HTTPException(status_code=exc.status_code, detail=str(exc),
                            headers={"Retry-After": "5"} if exc.kind == "storage" else None) from exc


abandon = sessions.abandon_turn
