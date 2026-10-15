"""채팅 실행의 수명. 연결 교체 뒤에도 이미 승인한 워커는 자기 취소/조향 문맥을 유지한다."""
import asyncio
import runtime_work
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
    lease: Any = None
    session_binding: Any = None
    workers: list = field(default_factory=list)


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
        lease = runtime_work.reserve("chat")
        run = ChatRun(client_id, connection, lease=lease)
        self.active[client_id] = run
        return run

    def detach(self, client_id: str, connection) -> None:
        """연결별 조향 입구만 닫는다. 워커 취소는 사용자의 명시적 중단을 따른다."""
        if self.owned(client_id, connection) is not None:
            self.active.pop(client_id, None)

    async def invoke(self, run, handler, data, manager):
        token = _current.set(run)
        store = binding = None
        execution_error = None
        from conversation_sessions import Binding, scope
        import chat_session_service as sessions
        try:
            if data.get("session_id"):
                store = sessions.from_data(data)
                binding = data.get("_session_binding")
                if not isinstance(binding, Binding):
                    binding = store.begin(data["session_id"])
                sessions.attach(run, binding)
            with scope(binding), run.lease.activate(), manager.connection_scope(run.client_id, run.connection):
                try:
                    return await handler(run.client_id, data)
                finally:
                    # 타임아웃 뒤에도 실행기는 살아 있다. 실제 워커가 끝나야 세션 잠금을 푼다.
                    if binding:
                        for worker in run.workers:
                            await asyncio.wrap_future(worker)
        except Exception as exc:
            execution_error = str(exc) or type(exc).__name__
            try:
                with scope(binding):
                    await manager.send_message(run.client_id, {"type": "error", "message": execution_error})
            except Exception as notify_error:
                print(f"[채팅 오류 알림 실패] {run.client_id}: {notify_error}")
            raise
        finally:
            if store and binding:
                from conversation_sessions import connection
                with connection(store.path) as conn:
                    failed = conn.execute("SELECT 1 FROM conversation_events WHERE turn_id=? AND payload LIKE ? LIMIT 1",
                                          (binding.turn_id, '%"type": "error"%')).fetchone()
                store.finish(binding, "cancelled" if run.cancelled.is_set() else
                             "failed" if execution_error or failed else "completed", error=execution_error)
            sessions.detach(run)
            run.finished = True
            if self.active.get(run.client_id) is run:
                self.active.pop(run.client_id, None)
            _current.reset(token)
            run.lease.close()

    def start(self, handler, client_id, data, connection, manager):
        # 수신 루프가 다음 cancel을 읽기 전에 상태를 만든다. 시작 직전 취소도 잃지 않는다.
        run = self.begin(client_id, connection)
        try:
            task = asyncio.create_task(self.invoke(run, handler, data, manager))
        except BaseException:
            run.lease.close()
            self.active.pop(client_id, None)
            raise
        run.task = task
        self.background.add(task)

        def done(completed):
            self.background.discard(completed)
            # invoke에 진입하기 전 취소된 태스크도 정리한다.
            run.finished = True
            run.lease.close()
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
            from conversation_sessions import bind_task
            if target[2]:
                bind_task(target[2])

    def is_cancelled(self, client_id):
        run = self.current(client_id)
        return bool(run and run.cancelled.is_set())

    def cancel(self, client_id, connection):
        run = self.owned(client_id, connection)
        if run is not None:
            run.cancelled.set()


registry = ChatRuns()
