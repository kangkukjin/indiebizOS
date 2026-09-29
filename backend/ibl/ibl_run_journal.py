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
import time
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


def call_resources(spec, contract, args, mode):
    """Resolve a complete declared footprint; None means an unknown resource set."""
    declaration = contract.get(mode + '_resources')
    if not declaration:
        return None
    resources = []
    for realm, param in declaration.items():
        value = args.get(param)
        if not isinstance(value, str) or not value.strip():
            return None
        # Bare output names can be redirected by the output-path policy.
        # Until the adapter declares that resolution, retain the broad barrier.
        if mode == 'write' and realm == 'file' and '/' not in value:
            return None
        identity = spec.resource_identity(realm, value) if spec.resource_identity else value
        if not isinstance(identity, str) or not identity:
            return None
        inode = None
        if realm == 'file':
            import member_runtime
            if member_runtime.is_member():
                return None  # A remote body's paths are not the hub's inode namespace.
            from runtime_utils import file_resource_identity
            identity = file_resource_identity(identity)
            try:
                stat = os.stat(identity)
                inode = [stat.st_dev, stat.st_ino]
            except OSError:
                pass
        resources.append([realm, identity, inode])
    return resources


def resources_overlap(reads, writes):
    """Unknown footprints conflict; file ancestors and hard links also overlap."""
    if reads is None or writes is None:
        return True
    for realm, path, inode in reads:
        for other_realm, other_path, other_inode in writes:
            if realm != other_realm:
                continue
            if path == other_path or inode is not None and inode == other_inode:
                return True
            if realm == 'file' and (path.startswith(other_path.rstrip('/') + '/')
                                    or other_path.startswith(path.rstrip('/') + '/')):
                return True
    return False


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
        self.started = False
        self.terminal = False

    def __enter__(self):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.root / (self.run_id + ".sqlite")
        if path.is_symlink() or (self.resuming and not path.is_file()):
            raise Fault("RESUME_NOT_FOUND", "이 문맥의 실행 기록이 없거나 보존 정책으로 정리되었습니다. 이 핸들로 재개할 수 없습니다.", kind="permission")
        self.file_lock = FileLock(str(path) + ".lock", timeout=0)
        try:
            self.file_lock.acquire()
        except Timeout as exc:
            raise Fault("RESUME_BUSY", "같은 실행이 이미 진행 중입니다.", kind="protocol") from exc
        try:
            if self.resuming and (path.is_symlink() or not path.is_file()):
                raise Fault("RESUME_NOT_FOUND", "기록이 정리되어 재개할 수 없습니다.", kind="permission")
            if not self.resuming:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
            self.db = sqlite3.connect(path, timeout=10, check_same_thread=False)  # cc-ok: begin/finish는 RLock, open/close는 워커 전후 단일 주체
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.executescript("CREATE TABLE IF NOT EXISTS meta(identity TEXT, blocked TEXT);"
                                 "CREATE TABLE IF NOT EXISTS calls(id TEXT PRIMARY KEY, request TEXT, receipt TEXT);"
                                 "CREATE TABLE IF NOT EXISTS lifecycle(created REAL, updated REAL, ended REAL, status TEXT, reason TEXT);")
            for table, column, declaration in (
                    ('calls', 'reusable', 'INTEGER NOT NULL DEFAULT 0'),
                    ('calls', 'state_change', 'INTEGER NOT NULL DEFAULT 1'),
                    ('calls', 'resources', 'TEXT'),
                    ('lifecycle', 'source_complete', 'INTEGER')):
                if column not in {r[1] for r in self.db.execute(f'PRAGMA table_info({table})')}:
                    self.db.execute(f'ALTER TABLE {table} ADD COLUMN {column} {declaration}')
            old = self.db.execute("SELECT identity,blocked FROM meta").fetchone()
            if self.resuming:
                if old is None or old[0] != self.identity:
                    raise Fault("RESUME_CHANGED", "소스·입력·함수·도구 구현·권한이 원래 실행과 다릅니다.", kind="protocol")
                if old[1]:
                    raise Fault("RESUME_CLEANED_UP", old[1], kind="protocol")
            else:
                self.db.execute("INSERT INTO meta VALUES(?,NULL)", (self.identity,))
                self.db.commit()
            now = time.time()
            if not self.db.execute('SELECT 1 FROM lifecycle').fetchone():
                self.db.execute('INSERT INTO lifecycle(created,updated,ended,status,reason) VALUES(?,?,NULL,?,NULL)',
                                (path.stat().st_mtime if self.resuming else now, now, 'running'))
            self.db.execute("UPDATE lifecycle SET updated=?, ended=NULL, status='running', reason=NULL, source_complete=NULL", (now,))
            self.db.commit()
            self.started = True
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *exc):
        try:
            if self.db is not None:
                try:
                    if self.started and not self.terminal:
                        self.complete({'success': False, 'error': '실행이 종료되었으나 최종 결과가 없습니다.'})
                finally:
                    self.db.close()
        finally:
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
    def begin(self, call_id, request_hash, cleanup=False, *, reusable=False, state_change=True, resources=None):
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
            # Invalidate reads that preceded this mutation, including unfinished
            # parallel reads. A read overlapping an in-flight mutation is also unsafe.
            if state_change:
                for old_id, footprint in self.db.execute('SELECT id,resources FROM calls WHERE reusable=1').fetchall():
                    if resources_overlap(json.loads(footprint) if footprint else None, resources):
                        self.db.execute('UPDATE calls SET reusable=0 WHERE id=?', (old_id,))
            pending_write = any(resources_overlap(resources, json.loads(row[0]) if row[0] else None)
                                for row in self.db.execute('SELECT resources FROM calls WHERE state_change=1 AND receipt IS NULL'))
            self.db.execute("INSERT INTO calls(id,request,receipt,reusable,state_change,resources) VALUES(?,?,NULL,?,?,?)",
                            (call_id, request_hash, int(reusable and not pending_write), int(state_change),
                             json.dumps(resources)))
            self.db.execute("UPDATE lifecycle SET updated=?", (time.time(),))
            self.db.commit()
            return None

    @durable
    def finish(self, call_id, receipt):
        with self.lock:
            self.db.execute("UPDATE calls SET receipt=? WHERE id=?", (json.dumps(receipt, ensure_ascii=False), call_id))
            self.db.execute("UPDATE lifecycle SET updated=?", (time.time(),))
            self.db.commit()

    @durable
    def complete(self, result):
        with self.lock:
            blocked = self.db.execute("SELECT blocked FROM meta").fetchone()[0]
            uncertain = self.db.execute("SELECT COUNT(*) FROM calls WHERE receipt IS NULL").fetchone()[0]
            status = "uncertain" if uncertain else "blocked" if blocked else "completed" if result.get("success") else "interrupted"
            source = result.get('source_complete')
            self.db.execute("UPDATE lifecycle SET updated=?, ended=?, status=?, reason=?, source_complete=?",
                            (time.time(), time.time(), status, blocked or result.get("error"),
                             int(source) if type(source) is bool else None))
            self.db.commit()
            self.terminal = True
            return status

    def reuse_summary(self):
        with self.lock:
            safe = self.db.execute("SELECT COUNT(*) FROM calls WHERE reusable=1 AND receipt IS NOT NULL AND json_type(receipt,'$.value') IS NOT NULL").fetchone()[0]
            changed = self.db.execute('SELECT 1 FROM calls WHERE state_change=1 LIMIT 1').fetchone()
        return {'read_calls': safe, 'state_change_possible': bool(changed)}


def identity(plan, inputs, project_path, agent_id, *, input_evidence=None):
    import principal
    import member_runtime
    from thread_context import get_allowed_nodes
    p, state = principal.current(), member_runtime.current() or {}
    allowed = get_allowed_nodes()
    # 권한은 순서 없는 내부 메타데이터다. None(무제한)과 빈 집합은 구분한다.
    allowed = None if allowed is None else sorted(set(allowed))
    return digest({"protocol": "ibl-resume/1", "plan": plan.fingerprint, "inputs": pack(inputs),
                   **({"input_evidence": input_evidence} if input_evidence else {}),
                   "project": str(Path(project_path).resolve()), "agent": agent_id,
                   "principal": [p.key(), p.device_id, p.level], "allowed": allowed,
                   "member_task": state.get("local_task_id"), "member_policy": state.get("policy")})


def inspect_run(root, run_id):
    """Read only scoped metadata; never return inputs, values or receipt bodies."""
    if not isinstance(run_id, str) or not re.fullmatch(r'[0-9a-f]{32}', run_id):
        raise Fault('RESUME_ARGUMENT', '올바른 run_id가 필요합니다.', kind='compile')
    path = Path(root) / (run_id + '.sqlite')
    if path.is_symlink() or not path.is_file():
        return {'run_id': run_id, 'status': 'unavailable', 'resumable': False,
                'reason': '기록이 없거나 보존 정책으로 정리되었습니다.'}
    lock = FileLock(str(path) + '.lock', timeout=0)
    busy = False
    try:
        lock.acquire()
    except Timeout:
        busy = True
    try:
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=10) as db:
            db.execute('BEGIN')
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            life = db.execute('SELECT created,updated,ended,status,reason FROM lifecycle').fetchone() if 'lifecycle' in tables else None
            counts = db.execute('SELECT COUNT(*),SUM(receipt IS NULL) FROM calls').fetchone()
            last = db.execute('SELECT id FROM calls WHERE receipt IS NOT NULL ORDER BY rowid DESC LIMIT 1').fetchone()
            blocked = db.execute('SELECT blocked FROM meta').fetchone()
            source = (db.execute('SELECT source_complete FROM lifecycle').fetchone()
                      if 'lifecycle' in tables and 'source_complete' in
                      {r[1] for r in db.execute('PRAGMA table_info(lifecycle)')} else None)
        status = life[3] if life else 'interrupted'
        if busy:
            status = 'running'
        elif counts[1]:
            status = 'uncertain'
        elif blocked and blocked[0]:
            status = 'blocked'
        elif status == 'running':
            status = 'interrupted'
        return {'run_id': run_id, 'status': status, 'locked': busy,
                'source_complete': bool(source[0]) if source and source[0] is not None else None,
                'created_at': life[0] if life else None, 'updated_at': life[1] if life else None,
                'ended_at': life[2] if life else None, 'calls': counts[0], 'uncertain_calls': counts[1] or 0,
                'last_checkpoint': last[0] if last else None, 'reason': life[4] if life else None,
                'resumable': status in {'completed', 'interrupted'},
                'note': '재개는 원 소스·입력·의존성·권한의 일치를 다시 검사합니다.'}
    finally:
        if not busy:
            lock.release()


@durable
def validate_resume(root, resume, expected_identity):
    """Check a resume handle without entering or resetting the journal."""
    journal = Journal(root, expected_identity, resume)
    path = Path(root) / (journal.run_id + '.sqlite')
    if path.is_symlink() or not path.is_file():
        raise Fault('RESUME_NOT_FOUND', '현재 문맥의 실행 기록이 없습니다.', kind='permission')
    try:
        with FileLock(str(path) + '.lock', timeout=0):
            with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=10) as db:
                row = db.execute('SELECT identity,blocked FROM meta').fetchone()
            if not row or row[0] != expected_identity:
                raise Fault('RESUME_CHANGED', '원 실행의 소스·입력·의존성·권한과 다릅니다.', kind='protocol')
            if row[1]:
                raise Fault('RESUME_CLEANED_UP', row[1], kind='protocol')
    except Timeout as exc:
        raise Fault('RESUME_BUSY', '같은 실행이 진행 중입니다.', kind='protocol') from exc


def reusable_receipts(root, run_id):
    """편집한 프로그램이 재사용할 후보: 이 문맥(주체·프로젝트)의 지난 실행이 남긴 완료 영수증, reuse_key 별.

    값을 돌려주지 않는다 — 실행기가 액션·인자·구현 지문이 맞고 읽기 효과인 호출에서만 꺼내 쓴다.
    진행 중(잠금)인 실행은 반쯤 쓴 상태를 빌려주지 않도록 거절한다. 옛 영수증(reuse_key 없음)은 후보가 아니다."""
    if not isinstance(run_id, str) or not re.fullmatch(r'[0-9a-f]{32}', run_id):
        raise Fault('REUSE_ARGUMENT', '올바른 run_id가 필요합니다.', kind='compile')
    path = Path(root) / (run_id + '.sqlite')
    if path.is_symlink() or not path.is_file():
        raise Fault('REUSE_NOT_FOUND', '이 문맥의 실행 기록이 없거나 보존 정책으로 정리되었습니다. 이 핸들의 영수증을 재사용할 수 없습니다.', kind='permission')
    lock = FileLock(str(path) + '.lock', timeout=0)
    try:
        lock.acquire()
    except Timeout as exc:
        raise Fault('REUSE_BUSY', '같은 실행이 아직 진행 중입니다. 끝난 뒤 재사용하세요.', kind='protocol') from exc
    try:
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=10) as db:
            # Old journals lack the mutation ordering evidence: do not guess.
            if 'reusable' not in {r[1] for r in db.execute('PRAGMA table_info(calls)')}:
                return {}
            rows = db.execute('SELECT receipt FROM calls WHERE reusable=1 AND receipt IS NOT NULL ORDER BY rowid').fetchall()
    except sqlite3.Error as exc:
        raise Fault('JOURNAL_IO', '실행 영수증 저장소를 읽을 수 없습니다.', kind='protocol') from exc
    finally:
        lock.release()
    out = {}
    for (raw,) in rows:
        try:
            receipt = json.loads(raw)
        except ValueError:
            continue
        if isinstance(receipt, dict) and 'value' in receipt and receipt.get('reuse_key'):
            out.setdefault(receipt['reuse_key'], receipt)
    return out


def migrate_completed_runs(root, *, backup_dir=None):
    """Repair old normal returns mislabelled interrupted; default is a dry run.

    Back up each qualifying SQLite under the caller's backup directory before
    changing metadata. Unknown effects, blocked runs and actual failures stay intact.
    """
    result = {'candidates': 0, 'updated': 0, 'skipped': 0}
    for path in Path(root).glob('*.sqlite'):
        if path.is_symlink() or not re.fullmatch(r'[0-9a-f]{32}', path.stem):
            continue
        try:
            with FileLock(str(path) + '.lock', timeout=0):
                with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=10) as db:
                    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    if not {'lifecycle', 'calls', 'meta'} <= tables:
                        continue
                    life = db.execute('SELECT ended,status,reason FROM lifecycle').fetchone()
                    if not life or life[0] is None or life[1] != 'interrupted' or life[2] is not None:
                        continue
                    meta = db.execute('SELECT blocked FROM meta').fetchone()
                    if (meta is None or meta[0] or
                            db.execute('SELECT 1 FROM calls WHERE receipt IS NULL LIMIT 1').fetchone()):
                        continue
                    result['candidates'] += 1
                    if backup_dir is None:
                        continue
                    saved = Path(backup_dir) / path.name
                    saved.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    fd = os.open(saved, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    os.close(fd)
                    with sqlite3.connect(saved, timeout=10) as backup:
                        db.backup(backup)
                with sqlite3.connect(path, timeout=10) as db:
                    if 'source_complete' not in {r[1] for r in db.execute('PRAGMA table_info(lifecycle)')}:
                        db.execute('ALTER TABLE lifecycle ADD COLUMN source_complete INTEGER')
                    db.execute("UPDATE lifecycle SET status='completed', source_complete=0 WHERE status='interrupted' AND reason IS NULL AND ended IS NOT NULL")
                result['updated'] += 1
        except (Timeout, OSError, sqlite3.Error):
            result['skipped'] += 1
    return result


def cleanup_runs(root, *, now=None, retention_days=30, max_bytes=512*1024*1024):
    """Prune completed receipts only, oldest first. Protected data may exceed cap."""
    now = time.time() if now is None else now
    root = Path(root)
    rows, total, removed = [], 0, 0
    for path in root.glob('*.sqlite'):
        if path.is_symlink() or not re.fullmatch(r'[0-9a-f]{32}', path.stem):
            continue
        size = path.stat().st_size
        total += size
        try:
            state = inspect_run(root, path.stem)
        except (sqlite3.Error, OSError):
            continue  # Unreadable is not known complete.
        if state['status'] == 'completed' and state['ended_at'] is not None:
            rows.append((state['ended_at'], path, size))
    for ended, path, size in sorted(rows):
        if now-ended < retention_days*86400 and total <= max_bytes:
            continue
        lock = FileLock(str(path)+'.lock', timeout=0)
        try:
            with lock:
                if not path.is_file() or path.is_symlink():
                    continue
                with sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=10) as db:
                    status = db.execute('SELECT status FROM lifecycle').fetchone()[0]
                    uncertain = db.execute('SELECT COUNT(*) FROM calls WHERE receipt IS NULL').fetchone()[0]
                    blocked = db.execute('SELECT blocked FROM meta').fetchone()[0]
                if status != 'completed' or uncertain or blocked:
                    continue
                path.unlink()
                # Keep the empty lock inode: removing it races another waiter.
                removed += 1
                total -= size
        except (Timeout, sqlite3.Error, OSError):
            continue
    return {'removed': removed, 'remaining_bytes': total, 'over_capacity': total > max_bytes,
            'retention_days': retention_days, 'max_bytes': max_bytes}


def maintain_owner_runs():
    import principal
    from runtime_utils import get_base_path
    if not principal.is_owner():
        return {'skipped': 'private-session-lifecycle'}
    root = get_base_path() / 'data/ibl_runs'
    return {p.name: cleanup_runs(p) for p in root.iterdir() if p.is_dir() and not p.is_symlink()} if root.exists() else {}
