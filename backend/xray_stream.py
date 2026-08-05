"""X-Ray 실시간 이벤트 스트림 허브 — api_xray 에서 이동 (2026-08-05 감사 ⑦).

왜 분리: push_xray_event 를 conversation_db·ibl_engine·system_tools 같은 아래층이
불러야 하는데, 그것이 라우터 모듈(api_xray)에 살아 아래층→표면 역방향 import 를
만들었다. 상태(클라이언트 집합·큐)와 푸시 함수만 여기(데이터층)로 내리고,
WS 엔드포인트(수신·배포 루프)는 api_xray 에 남는다 — 라우터는 얇게.
"""

import asyncio
from datetime import datetime
from typing import Set

from fastapi import WebSocket


class _XRayWS:
    """X-Ray WebSocket 상태를 클래스로 캡슐화 (Python 3.14 scoping 호환)"""
    def __init__(self):
        self.clients: Set[WebSocket] = set()
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=100)


_ws = _XRayWS()


def push_xray_event(event_type: str, data: dict):
    """동기 코드에서 X-Ray 이벤트 푸시 (system_tools 등에서 호출)"""
    if not _ws.clients:
        return
    event = {"type": event_type, "ts": datetime.now().strftime("%H:%M:%S"), **data}
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.call_soon_threadsafe(_ws.queue.put_nowait, event)
        else:
            _ws.queue.put_nowait(event)
    except Exception:
        pass
