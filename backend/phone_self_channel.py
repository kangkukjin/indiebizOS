"""phone_self_channel.py — 맥↔폰-자아 역방향 제어 채널 (폰-자아 호스팅 away-case 해결).

문제: 폰이 LTE/외부 WiFi(NAT/CGNAT) 뒤에 있으면 맥이 폰을 *dial* 할 수 없다(공인 inbound 주소
없음). 그래서 claude_code(맥)가 폰-자아의 몸에서 execute_ibl 을 돌리려 해도 폰에 못 닿는다.

해법(사용자 정립): 방향을 뒤집는다. 폰이 맥의 *기존* Cloudflare 터널로 **outbound** WebSocket 을
열어두면(폰이 거는 건 NAT 통과), 맥은 그 열린 길로 execute_ibl 을 밀어넣어 폰에서 실행시킨다.
Cloudflare(맥 터널)가 중간 서버 역할 — 새 터널·바이너리 불필요. claude_code 의 도구 호출이
폰-자아의 몸에서 일어나게 하는 동기 RPC(요청 id 로 응답 페어링).

루프 방지: claude_code→맥 진입(route_to_phone_ws=True)만 폰으로 라우팅. 폰이 home_only 액션을
맥으로 forward(_forward_to_mac)할 땐 그 플래그가 없어 맥 로컬 실행 → 되돌아오지 않음.
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

# phone_id -> WebSocket (보통 단일 "phone"). req_id -> Future(결과 대기).
_conns: dict = {}
_pending: dict = {}
_seq = {"n": 0}


def is_connected(phone_id: str = "phone") -> bool:
    return phone_id in _conns


def register(phone_id: str, ws) -> None:
    _conns[phone_id] = ws
    logger.info(f"[phone-self 채널] WS 등록: {phone_id} (총 {len(_conns)})")


def unregister(phone_id: str) -> None:
    _conns.pop(phone_id, None)
    # 끊긴 연결의 대기중 요청을 전부 실패 처리(무한 대기 방지).
    for rid, fut in list(_pending.items()):
        if not fut.done():
            fut.set_exception(ConnectionError("phone-self WS 끊김"))
        _pending.pop(rid, None)
    logger.info(f"[phone-self 채널] WS 해제: {phone_id} (총 {len(_conns)})")


def resolve(req_id: str, result) -> None:
    """폰이 보낸 ibl_result 를 대기중 Future 에 연결."""
    fut = _pending.get(req_id)
    if fut and not fut.done():
        fut.set_result(result)


async def execute_on_phone(code: str, agent_id: str = None,
                           phone_id: str = "phone", timeout: float = 120.0):
    """폰 WS 로 IBL 실행을 보내고 결과를 동기 대기. 미연결/타임아웃이면 예외(호출부가 폴백)."""
    ws = _conns.get(phone_id)
    if ws is None:
        raise ConnectionError("phone-self WS 미연결")
    _seq["n"] += 1
    rid = f"r{_seq['n']}"
    fut = asyncio.get_event_loop().create_future()
    _pending[rid] = fut
    try:
        await ws.send_json({"type": "ibl_execute", "id": rid,
                            "code": code, "agent_id": agent_id})
        return await asyncio.wait_for(fut, timeout)
    finally:
        _pending.pop(rid, None)
