"""Durable effect receipts for deterministic continuation of checked programs.

A started receipt without an outcome is deliberately not retryable. The file
lock excludes concurrent resumptions; SQLite FULL commits bracket each effect.
Member contents remain in the existing private session store and its lifecycle.
"""
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
from functools import wraps
import uuid
from filelock import FileLock, Timeout
from ibl_v2_ir import Fault, digest, pack


def durable(operation):
    @wraps(operation)
    def wrapped(*args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except (sqlite3.Error, OSError) as exc:
            raise Fault("JOURNAL_IO", "실행 영수증 저장소를 확인할 수 없습니다. 외부 작업을 재시도하지 않습니다.", kind="protocol") from exc
    return wrapped


def journal_root(project_path):
    import member_runtime
    import principal
    from runtime_utils import get_base_path
    p = principal.current()
    if p.kind == principal.KIND_MEMBER:
        return member_runtime.private_path("ibl_runs")
    return get_base_path() / "data/ibl_runs" / digest([p.key(), str(Path(project_path).resolve())])


class Journal:
    def __init__(self, root, identity, resume=None):
        if resume is not None and (not isinstance(resume, dict) or set(resume) != {"run_id"}):
            raise Fault("RESUME_ARGUMENT", "resume에는 반환된 run_id만 지정하세요.", kind="compile")
        self.run_id = resume["run_id"] if resume else uuid.uuid4().hex
        if not isinstance(self.run_id, str) or not re.fullmatch(r"[0-9a-f]{32}", self.run_id):
            raise Fault("RESUME_ARGUMENT", "올바른 run_id가 필요합니다.", kind="compile")
        self.root, self.identity, self.resuming = Path(root), identity, resume is not None
        self.lock = threading.RLock()
        self.db = None

    def __enter__(self):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.root / (self.run_id + ".sqlite")
        if path.is_symlink() or (self.resuming and not path.is_file()):
            raise Fault("RESUME_NOT_FOUND", "이 문맥의 실행 기록이 없습니다.", kind="permission")
        self.file_lock = FileLock(str(path) + ".lock", timeout=0)
        try:
            self.file_lock.acquire()
        except Timeout as exc:
            raise Fault("RESUME_BUSY", "같은 실행이 이미 진행 중입니다.", kind="protocol") from exc
        try:
            if not self.resuming:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
            self.db = sqlite3.connect(path, timeout=10, check_same_thread=False)  # cc-ok: begin/finish는 RLock, open/close는 워커 전후 단일 주체
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.executescript("CREATE TABLE IF NOT EXISTS meta(identity TEXT, blocked TEXT);"
                                 "CREATE TABLE IF NOT EXISTS calls(id TEXT PRIMARY KEY, request TEXT, receipt TEXT);")
            old = self.db.execute("SELECT identity,blocked FROM meta").fetchone()
            if self.resuming:
                if old is None or old[0] != self.identity:
                    raise Fault("RESUME_CHANGED", "소스·입력·함수·도구 구현·권한이 원래 실행과 다릅니다.", kind="protocol")
                if old[1]:
                    raise Fault("RESUME_CLEANED_UP", old[1], kind="protocol")
            else:
                self.db.execute("INSERT INTO meta VALUES(?,NULL)", (self.identity,))
                self.db.commit()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *exc):
        if self.db is not None:
            self.db.close()
        self.file_lock.release()

    def announce(self, plan_hash):
        # Publish the handle before the first effect. A lost final HTTP response
        # can recover it through the existing ticket/trajectory, without rerun.
        import member_runtime
        if member_runtime.is_member():
            return
        data = {"edition": 2, "resume": {"run_id": self.run_id}, "plan_hash": plan_hash}
        try:
            from thread_context import get_progress_ticket
            from common.spill import ticket_progress
            ticket = get_progress_ticket()
            if ticket:
                ticket_progress(ticket, data)
            from episode_logger import record_trajectory_event
            record_trajectory_event("ibl.checkpoint", data)
        except Exception:
            pass  # The SQLite receipt remains authoritative.

    @durable
    def begin(self, call_id, request_hash, cleanup=False):
        with self.lock:
            row = self.db.execute("SELECT request,receipt FROM calls WHERE id=?", (call_id,)).fetchone()
            if row:
                if row[0] != request_hash:
                    raise Fault("RESUME_DIVERGED", "기록된 호출의 입력이 달라졌습니다.", kind="protocol")
                if row[1] is None:
                    raise Fault("EFFECT_UNCERTAIN", "외부 작업의 완료를 확인할 수 없습니다. 영수증을 확인하기 전에는 재실행하지 않습니다.",
                                kind="protocol", details={"run_id": self.run_id, "call_id": call_id})
                return json.loads(row[1])
            if cleanup:
                self.db.execute("UPDATE meta SET blocked=?", ("취소·예산 중단 후 finally가 외부 정리를 시작했습니다. 같은 실행의 재개는 허용하지 않습니다.",))
            self.db.execute("INSERT INTO calls VALUES(?,?,NULL)", (call_id, request_hash))
            self.db.commit()
            return None

    @durable
    def finish(self, call_id, receipt):
        with self.lock:
            self.db.execute("UPDATE calls SET receipt=? WHERE id=?", (json.dumps(receipt, ensure_ascii=False), call_id))
            self.db.commit()


def identity(plan, inputs, project_path, agent_id):
    import principal
    import member_runtime
    from thread_context import get_allowed_nodes
    p, state = principal.current(), member_runtime.current() or {}
    return digest({"protocol": "ibl-resume/1", "plan": plan.fingerprint, "inputs": pack(inputs),
                   "project": str(Path(project_path).resolve()), "agent": agent_id,
                   "principal": [p.key(), p.device_id, p.level], "allowed": get_allowed_nodes(),
                   "member_task": state.get("local_task_id"), "member_policy": state.get("policy")})
