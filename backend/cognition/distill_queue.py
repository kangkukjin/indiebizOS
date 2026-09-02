"""증류 영속 큐 — 턴 종료 후 기억 쓰기(_after_response)의 유실 없는 배달 (2026-09-02).

왜: 증류(해마·심층·포식·가이드 되먹임)는 응답 뒤 데몬 스레드 하나로 돌았다. 스레드는
프로세스와 함께 죽고(리로드·창 닫힘=백엔드 종료), 실패는 print 한 줄로 끝났다 — 영속
큐도, 재시도 원장도, 종료 drain 도 없어 "그 턴의 경험이 기억이 됐는가"를 아무도 보증하지
못했다(기억관리 감사 2026-09-02, 증류 항목).

무엇: 작업을 world_pulse.db `distill_queue` 행으로 먼저 남기고(영속), 단일 워커 스레드가
순서대로 소비한다. 성공=행 삭제, 실패=attempts·last_error 기록 후 재시도(상한 3회 →
failed 로 남김), 종료=drain(유한 대기, 남은 행은 pending 그대로), 부팅=resume(이전
프로세스의 pending/running 행을 러너를 다시 찾아 재개 — 못 찾으면 orphaned 로 신고).
워커 하나 = 경량 프로바이더 원샷 잠금(_oneshot_call_lock)을 두고 증류끼리 다투지 않는다.

층: cognition. 러너 해소는 system AI(system_ai_core 싱글턴)·프로젝트(agent_registry)만 —
그 밖의 키는 orphaned(침묵 폐기 금지).
"""
import json
import queue
import threading
import time
from datetime import datetime
from typing import Any, Dict, Optional

MAX_ATTEMPTS = 3
RETRY_BACKOFF_SEC = (0, 5, 20)      # n번째 시도 전 대기(초). 시험은 (0,0,0) 으로 덮는다.
DRAIN_TIMEOUT_SEC = 10              # 종료 유예 — 넘으면 행을 남기고 떠난다(다음 부팅이 재개)
SYSTEM_AI_KEY = "system:system_ai"  # system_ai_core.get_system_ai_runner 의 registry_key

_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS distill_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        updated_at TEXT,
        registry_key TEXT,
        project_id TEXT,
        agent_id TEXT,
        agent_name TEXT,
        payload TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        attempts INTEGER NOT NULL DEFAULT 0,
        last_error TEXT
    )
"""


def _now() -> str:
    return datetime.now().isoformat()


def _conn():
    from pulse_db import _get_pulse_db
    conn = _get_pulse_db()
    conn.execute(_TABLE_SQL)
    return conn


class _Job:
    __slots__ = ("row_id", "runner", "payload", "ident", "ctx", "ep", "attempts")

    def __init__(self, row_id, runner, payload, ident, ctx=None, ep=None, attempts=0):
        self.row_id, self.runner, self.payload, self.ident = row_id, runner, payload, ident
        self.ctx, self.ep, self.attempts = ctx, ep, attempts


class DistillQueue:
    _instance: Optional["DistillQueue"] = None
    _instance_lock = threading.Lock()

    def __init__(self):
        self._q: "queue.Queue[_Job]" = queue.Queue()
        self._worker: Optional[threading.Thread] = None
        self._worker_lock = threading.Lock()
        self._idle = threading.Event()   # 큐 비었고 실행 중인 작업 없음
        self._idle.set()
        self._resume_armed = False       # 부팅 주체(boot_common)만 무장 — 프로브는 재개 금지

    @classmethod
    def get(cls) -> "DistillQueue":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    # ---------- 적재 ----------

    def enqueue(self, runner, payload: Dict[str, Any], *, ident: Dict[str, Any],
                ctx=None, ep=None) -> int:
        """행을 먼저 남기고(영속) 워커에 넘긴다. 반환=행 id."""
        conn = _conn()
        try:
            cur = conn.execute(
                "INSERT INTO distill_queue (created_at, registry_key, project_id, agent_id, "
                "agent_name, payload, status) VALUES (?, ?, ?, ?, ?, ?, 'pending')",
                (_now(), ident.get("registry_key"), ident.get("project_id"),
                 ident.get("agent_id"), ident.get("agent_name"),
                 json.dumps(payload, ensure_ascii=False, default=str)))
            conn.commit()
            row_id = cur.lastrowid
        finally:
            conn.close()
        self._put(_Job(row_id, runner, payload, ident, ctx=ctx, ep=ep))
        return row_id

    def _put(self, job: _Job):
        self._idle.clear()
        self._q.put(job)
        self._ensure_worker()

    def _ensure_worker(self):
        with self._worker_lock:
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._loop, daemon=True,
                                                name="distill-queue")
                self._worker.start()

    # ---------- 소비 ----------

    def _loop(self):
        while True:
            try:
                job = self._q.get(timeout=1.0)
            except queue.Empty:
                self._idle.set()
                continue
            try:
                self._run_job(job)
            finally:
                self._q.task_done()
                if self._q.empty():
                    self._idle.set()

    def _run_job(self, job: _Job):
        job.attempts += 1
        backoff = RETRY_BACKOFF_SEC[min(job.attempts - 1, len(RETRY_BACKOFF_SEC) - 1)]
        if backoff:
            time.sleep(backoff)
        self._mark(job.row_id, "running", attempts=job.attempts)
        try:
            self._execute(job)
            self._delete(job.row_id)
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            if job.attempts < MAX_ATTEMPTS:
                self._mark(job.row_id, "pending", attempts=job.attempts, error=err)
                print(f"[증류큐] #{job.row_id} 실패 {job.attempts}/{MAX_ATTEMPTS} — 재시도: {err[:120]}")
                self._put(job)
            else:
                self._mark(job.row_id, "failed", attempts=job.attempts, error=err)
                print(f"[증류큐] #{job.row_id} 실패 상한 — failed 로 남김: {err[:120]}")
        finally:
            if job.ep is not None:
                try:
                    from episode_logger import EpisodeLogger
                    EpisodeLogger.refresh_episode(job.ep)
                except Exception:
                    pass

    @staticmethod
    def _execute(job: _Job):
        from thread_context import (set_current_agent_id, set_current_project_id,
                                    set_current_agent_name, set_goal_eval_outcome)
        p, ident = job.payload, job.ident
        if ident.get("agent_id"):
            set_current_agent_id(ident["agent_id"])
        if ident.get("project_id"):
            set_current_project_id(ident["project_id"])
        if ident.get("agent_name"):
            set_current_agent_name(ident["agent_name"])
        ge = p.get("goal_eval")
        if ge is not None:
            set_goal_eval_outcome(ge.get("achieved", True), ge.get("severity", 0) or 0)

        def _call():
            job.runner._after_response(
                p.get("user_message", ""), p.get("response", ""),
                tool_calls=p.get("tool_calls"), hippo_score=p.get("hippo_score"),
                top_code=p.get("top_code"), guides_used=p.get("guides_used"),
                turn_tokens=p.get("turn_tokens"),
            )
        if job.ctx is not None:
            job.ctx.run(_call)
        else:
            _call()

    # ---------- 원장 ----------

    @staticmethod
    def _mark(row_id: int, status: str, *, attempts: int, error: str = None):
        conn = _conn()
        try:
            conn.execute(
                "UPDATE distill_queue SET status = ?, attempts = ?, updated_at = ?, "
                "last_error = COALESCE(?, last_error) WHERE id = ?",
                (status, attempts, _now(), error, row_id))
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _delete(row_id: int):
        conn = _conn()
        try:
            conn.execute("DELETE FROM distill_queue WHERE id = ?", (row_id,))
            conn.commit()
        finally:
            conn.close()

    def stats(self) -> Dict[str, int]:
        conn = _conn()
        try:
            rows = conn.execute(
                "SELECT status, COUNT(*) FROM distill_queue GROUP BY status").fetchall()
        finally:
            conn.close()
        out = {r[0]: r[1] for r in rows}
        out["in_memory"] = self._q.qsize()
        return out

    # ---------- 수명 ----------

    def drain(self, timeout: float = DRAIN_TIMEOUT_SEC) -> Dict[str, Any]:
        """종료 전 유한 대기. 못 끝낸 작업은 행(pending/running)으로 남아 다음 부팅이 재개한다."""
        done = self._idle.wait(timeout)
        left = self._q.qsize() + (0 if done else 1)
        if done:
            print("[증류큐] drain 완료 — 남은 작업 0")
        else:
            print(f"[증류큐] drain {timeout}s 초과 — 남은 작업 {left}건은 행으로 남김(다음 부팅이 재개)")
        return {"drained": done, "left": left}

    def arm_resume(self):
        """부팅 주체가 호출 — resume 허가. 두 단계인 이유: 주체 판정은 boot_common(다른 몸이
        떠 있으면 프로브)이 알고, 재개 시점은 system AI 러너가 선 뒤(start_system_ai_runner)
        여야 한다 — boot_common 시점에 러너를 만들면 패키지·프롬프트가 서기 전의 러너가
        싱글턴으로 굳는다."""
        self._resume_armed = True

    def resume(self, force: bool = False) -> Dict[str, Any]:
        """이전 프로세스가 남긴 pending/running 행을 러너를 다시 찾아 재개.

        arm_resume 없이는 건너뛴다(force 는 시험용). 러너 해소: system AI 키 → system_ai_core
        싱글턴, 그 밖 → agent_registry 의 살아있는 러너. 못 찾으면 orphaned 로 표시하고 이유를
        남긴다(침묵 폐기 금지). 재개 행은 attempts 를 이어 센다(무한 재시도 방지).
        """
        if not (force or self._resume_armed):
            return {"skipped": "not armed"}
        self._resume_armed = False
        conn = _conn()
        try:
            rows = conn.execute(
                "SELECT id, registry_key, project_id, agent_id, agent_name, payload, attempts "
                "FROM distill_queue WHERE status IN ('pending', 'running') ORDER BY id").fetchall()
        finally:
            conn.close()
        resumed = orphaned = exhausted = 0
        for r in rows:
            row_id, key = r[0], r[1]
            ident = {"registry_key": key, "project_id": r[2], "agent_id": r[3], "agent_name": r[4]}
            attempts = int(r[6] or 0)
            if attempts >= MAX_ATTEMPTS:
                self._mark(row_id, "failed", attempts=attempts, error="재개 시 시도 상한 초과")
                exhausted += 1
                continue
            runner = self._resolve_runner(key)
            if runner is None:
                self._mark(row_id, "orphaned", attempts=attempts,
                           error=f"재개 시 러너 없음: {key}")
                orphaned += 1
                continue
            try:
                payload = json.loads(r[5])
            except Exception as e:
                self._mark(row_id, "failed", attempts=attempts, error=f"payload 손상: {e}")
                exhausted += 1
                continue
            self._put(_Job(row_id, runner, payload, ident, attempts=attempts))
            resumed += 1
        if rows:
            print(f"[증류큐] 재개 {resumed}건 · 러너 없음 {orphaned}건 · 상한/손상 {exhausted}건")
        return {"resumed": resumed, "orphaned": orphaned, "exhausted": exhausted}

    @staticmethod
    def _resolve_runner(registry_key: Optional[str]):
        if not registry_key:
            return None
        if registry_key == SYSTEM_AI_KEY:
            try:
                from system_ai_core import get_system_ai_runner
                return get_system_ai_runner()
            except Exception:
                return None
        try:
            from agent_registry import runner_registry
            return runner_registry.get(registry_key)
        except Exception:
            return None
