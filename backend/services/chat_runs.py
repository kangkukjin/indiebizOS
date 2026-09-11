"""채팅 실행의 수명. 연결 교체 뒤에도 이미 승인한 워커는 자기 취소/조향 문맥을 유지한다."""
import asyncio
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import Event
from typing import Any


@dataclass(eq=False)
class ChatRun:
    client_id: str
    connection: Any = None
    target: tuple = (None, None, None)
    cancelled: Event = field(default_factory=Event)
    task: asyncio.Task | None = None
    finished: bool = False


_current: ContextVar[ChatRun | None] = ContextVar("chat_run", default=None)


class ChatRuns:
    def __init__(self):
        self.active: dict[str, ChatRun] = {}
        self.background: set[asyncio.Task] = set()

    def current(self, client_id: str) -> ChatRun | None:
        run = _current.get()
        if run is not None and run.client_id == client_id:
            return run
        return self.active.get(client_id)

    def owned(self, client_id: str, connection) -> ChatRun | None:
        run = self.active.get(client_id)
        return run if run and not run.finished and run.connection is connection else None

    def begin(self, client_id: str, connection=None) -> ChatRun:
        if self.owned(client_id, connection) is not None:
            raise RuntimeError("이 연결에는 이미 실행 중인 작업이 있습니다")
        run = ChatRun(client_id, connection)
        self.active[client_id] = run
        return run

    def detach(self, client_id: str, connection) -> None:
        """연결별 조향 입구만 닫는다. 워커 취소는 사용자의 명시적 중단을 따른다."""
        if self.owned(client_id, connection) is not None:
            self.active.pop(client_id, None)

    async def invoke(self, run, handler, data, manager):
        token = _current.set(run)
        try:
            with manager.connection_scope(run.client_id, run.connection):
                return await handler(run.client_id, data)
        finally:
            run.finished = True
            if self.active.get(run.client_id) is run:
                self.active.pop(run.client_id, None)
            _current.reset(token)

    def start(self, handler, client_id, data, connection, manager):
        # 수신 루프가 다음 cancel을 읽기 전에 상태를 만든다. 시작 직전 취소도 잃지 않는다.
        run = self.begin(client_id, connection)
        task = asyncio.create_task(self.invoke(run, handler, data, manager))
        run.task = task
        self.background.add(task)

        def done(completed):
            self.background.discard(completed)
            # invoke에 진입하기 전 취소된 태스크도 정리한다.
            run.finished = True
            if self.active.get(client_id) is run:
                self.active.pop(client_id, None)
            if not completed.cancelled() and completed.exception():
                print(f"[채팅 실행 실패] {client_id}: {completed.exception()}")

        task.add_done_callback(done)
        return task

    async def call(self, handler, client_id, data, manager):
        """WS뿐 아니라 예약 작업의 직접 서비스 호출도 같은 수명 경계로 감싼다."""
        current = _current.get()
        if current is not None and current.client_id == client_id:
            return await handler(client_id, data)
        run = self.begin(client_id, manager.active_connections.get(client_id))
        run.task = asyncio.current_task()
        return await self.invoke(run, handler, data, manager)

    def bind_target(self, client_id, target):
        run = self.current(client_id)
        if run is not None:
            run.target = target

    def is_cancelled(self, client_id):
        run = self.current(client_id)
        return bool(run and run.cancelled.is_set())

    def cancel(self, client_id, connection):
        run = self.owned(client_id, connection)
        if run is not None:
            run.cancelled.set()


registry = ChatRuns()
