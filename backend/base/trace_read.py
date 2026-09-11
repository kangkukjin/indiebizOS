"""Read-only primitives for ledger owners. No schema setup, recovery, or logging hooks."""
import hashlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SQL_SECONDS = 0.35
JSON_BYTES = 1024 * 1024
LINE_BYTES = 64 * 1024
PAGE_LIMIT = 100


class ReadFault(Exception):
    def __init__(self, status, reason):
        self.status, self.reason = status, reason
        super().__init__(reason)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     default=str).encode()).hexdigest()


def file_identity(stat):
    return [stat.st_dev, stat.st_ino, stat.st_ctime_ns]


def result(source, rows=None, status=None, reason=None, **fields):
    rows = [] if rows is None else rows
    return {"source": source, "status": status or ("ok" if rows else "empty"),
            "observed_at": stamp(), "rows": rows, "reason": reason, **fields}


def guarded(source, fn):
    try:
        return fn()
    except ReadFault as exc:
        return result(source, status=exc.status, reason=exc.reason)
    except FileNotFoundError:
        return result(source, status="missing", reason="source_missing")
    except PermissionError:
        return result(source, status="forbidden", reason="access_denied")
    except (json.JSONDecodeError, UnicodeError, TypeError, ValueError, KeyError):
        return result(source, status="malformed", reason="invalid_source_record")
    except sqlite3.DatabaseError as exc:
        unavailable = getattr(exc, "sqlite_errorcode", None) in {
            sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED, sqlite3.SQLITE_INTERRUPT, sqlite3.SQLITE_CANTOPEN}
        return result(source, status="unavailable" if unavailable else "malformed",
                      reason="read_budget_or_lock" if unavailable else "invalid_schema_or_database")
    except OSError:
        return result(source, status="unavailable", reason="source_io_error")


@contextmanager
def readonly(path):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.1)
    conn.row_factory = sqlite3.Row
    deadline = time.monotonic() + SQL_SECONDS
    conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        yield conn
    finally:
        conn.rollback()
        conn.close()


def bounded_rows(conn, sql, args=(), limit=200):
    rows = conn.execute(sql + " LIMIT ?", (*args, limit + 1)).fetchall()
    if len(rows) > limit:
        raise ReadFault("partial", "identity_or_metadata_budget")
    return [dict(row) for row in rows]


def sql_page(source, path, table, columns, where, args, cursor=None, limit=50):
    """Owner supplies SQL constants. Append-only rowid watermark; counts detect retention."""
    def read():
        if cursor and cursor.get("absent"):
            if Path(path).exists():
                raise ReadFault("partial", "cursor_expired")
            raise FileNotFoundError
        with readonly(path) as conn:
            ino = list(file_identity(Path(path).stat())[:2])
            high = (cursor or {}).get("high")
            if high is None:
                high = conn.execute(f"SELECT COALESCE(MAX(rowid),0) FROM {table} WHERE {where}", args).fetchone()[0]
            count = conn.execute(f"SELECT count(*) FROM {table} WHERE ({where}) AND rowid<=?", (*args, high)).fetchone()[0]
            water = {"high": high, "count": count, "file": ino}
            if cursor and any(cursor[k] != water[k] for k in water):
                raise ReadFault("partial", "cursor_expired")
            after = (cursor or {}).get("after", 0)
            rows = [dict(r) for r in conn.execute(
                f"SELECT rowid AS _rowid,{columns} FROM {table} WHERE ({where}) "
                "AND rowid>? AND rowid<=? ORDER BY rowid LIMIT ?", (*args, after, high, limit + 1))]
            more = len(rows) > limit
            rows = rows[:limit]
            water["after"] = rows[-1]["_rowid"] if rows else after
            water["done"] = not more
            return result(source, rows, high_water=water, more=more)
    return guarded(source, read)


def jsonl_page(source, path, cursor=None, limit=50, predicate=lambda row: True):
    """Fixed open-file upper bound. Offsets identify repeated identical lines separately."""
    def read():
        if cursor and cursor.get("absent"):
            if Path(path).exists():
                raise ReadFault("partial", "cursor_expired")
            raise FileNotFoundError
        if cursor and not Path(path).exists():
            raise ReadFault("partial", "cursor_expired")
        with Path(path).open("rb") as stream:
            st = os.fstat(stream.fileno())
            # ctime changes on append: inode + frozen prefix hash define this generation.
            head_size = (cursor or {}).get("head_size", min(st.st_size, 4096))
            head = hashlib.sha256(stream.read(head_size)).hexdigest()
            high = (cursor or {}).get("high", st.st_size)
            stream.seek(max(0, high - 4096))
            tail = hashlib.sha256(stream.read(min(high, 4096))).hexdigest()
            water = {"file": list(file_identity(st)[:2]), "head": head, "head_size": head_size,
                     "tail": tail, "high": high}
            if cursor and (st.st_size < high or any(cursor[k] != water[k] for k in water)):
                raise ReadFault("partial", "cursor_expired")
            after = (cursor or {}).get("after", 0)
            stream.seek(after)
            rows, diagnostics, scanned = [], [], 0
            discarding = (cursor or {}).get("discarding", False)
            deadline = time.monotonic() + SQL_SECONDS
            while stream.tell() < high and len(rows) < limit and scanned < JSON_BYTES:
                if time.monotonic() > deadline:
                    break
                offset = stream.tell()
                line = stream.readline(min(LINE_BYTES + 1, high - offset))
                scanned += len(line)
                if discarding or len(line) > LINE_BYTES:
                    discarding = not line.endswith(b"\n")
                    diagnostics.append("oversize_record")
                    continue
                if not line.endswith(b"\n"):
                    diagnostics.append("truncated_tail")
                    break
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError
                    if predicate(row):
                        rows.append({**row, "_offset": offset, "_hash": hashlib.sha256(line).hexdigest()})
                except (ValueError, UnicodeError, TypeError):
                    diagnostics.append("malformed_record")
            water["after"] = stream.tell()
            water["discarding"] = discarding
            water["done"] = water["after"] >= high
            return result(source, rows, status="partial" if diagnostics or not water["done"] else None,
                          reason=("page_budget" if not water["done"] and not diagnostics else None) or ",".join(sorted(set(diagnostics))) or None,
                          high_water=water, more=not water["done"], scanned_bytes=scanned)
    return guarded(source, read)


def safe_child(root, *parts):
    root = Path(root).resolve()
    candidate = root.joinpath(*parts)
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root) or any(p in {"", ".", ".."} for p in parts):
        raise ReadFault("forbidden", "access_denied")
    # No symlinks in the requested descendants, including links that stay in root.
    current = root
    for part in candidate.relative_to(root).parts:
        current /= part
        if current.is_symlink():
            raise ReadFault("forbidden", "access_denied")
    return resolved
