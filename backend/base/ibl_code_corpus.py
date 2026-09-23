"""Edition-aware original source ledger; private runtime observations only."""
from datetime import datetime
from ibl_edition import program_hash


_CORPUS_ERROR_CAP = 500
_CORPUS_DDL = """
    CREATE TABLE IF NOT EXISTS ibl_code_corpus (
        code_sha256 TEXT PRIMARY KEY,
        code TEXT NOT NULL,
        code_chars INTEGER NOT NULL,
        masked INTEGER NOT NULL DEFAULT 0,
        first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        seen_count INTEGER NOT NULL DEFAULT 0,
        success_count INTEGER NOT NULL DEFAULT 0,
        fail_count INTEGER NOT NULL DEFAULT 0,
        last_success INTEGER,
        last_ms INTEGER,
        last_error TEXT,
        last_agent TEXT,
        last_origin TEXT,
        source TEXT,
        edition INTEGER NOT NULL DEFAULT 1
    );
    CREATE INDEX IF NOT EXISTS idx_ibl_corpus_last_seen ON ibl_code_corpus(last_seen);
"""


def _ensure_corpus_table() -> None:
    """ibl_code_corpus 표 보장 (idempotent) — _ensure_episode_tables 가 부팅마다 함께 부른다."""
    import episode_logger as el
    try:
        conn = el._get_db()
        try:
            conn.executescript(_CORPUS_DDL)
            if "edition" not in {r[1] for r in conn.execute("PRAGMA table_info(ibl_code_corpus)")}:
                conn.execute("ALTER TABLE ibl_code_corpus ADD COLUMN edition INTEGER NOT NULL DEFAULT 1")
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        try:
            if el.EpisodeLogger._original_stdout:
                el.EpisodeLogger._original_stdout.write(f"[EpisodeLogger] 코퍼스 표 보장 실패: {e}\n")
        except Exception:
            pass


def record_ibl_code(code: str, success: bool, elapsed_ms=None, error="",
                    agent: str = "", origin: str = "", edition: int = 1) -> bool:
    """IBL 문장 원문 한 건을 코퍼스에 누적(upsert). 관측 훅 — 실패해도 실행을 깨지 않는다.

    반환 True=기록됨, False=빈 코드이거나 기록 실패(호출자는 무시해도 된다)."""
    import episode_logger as el
    from member_runtime import is_member
    if is_member():
        return False
    code = code if isinstance(code, str) else str(code or "")
    if not code.strip():
        return False
    try:
        sha = program_hash(code, edition)
        safe_code = el.mask_secrets(code)
        err = ""
        if error:
            err = el.mask_secrets(el.truncate_for_log(str(error), _CORPUS_ERROR_CAP))
        now = datetime.now().isoformat()
        ok = 1 if success else 0
        try:
            ms = int(elapsed_ms) if elapsed_ms is not None else None
        except (TypeError, ValueError):
            ms = None
        conn = el._get_db()
        try:
            conn.execute(
                """INSERT INTO ibl_code_corpus
                   (code_sha256, code, code_chars, masked, first_seen, last_seen, seen_count,
                    success_count, fail_count, last_success, last_ms, last_error,
                    last_agent, last_origin, source, edition)
                   VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(code_sha256) DO UPDATE SET
                     last_seen=excluded.last_seen,
                     seen_count=seen_count+1,
                     success_count=success_count+excluded.success_count,
                     fail_count=fail_count+excluded.fail_count,
                     last_success=excluded.last_success,
                     last_ms=excluded.last_ms,
                     last_error=CASE WHEN excluded.last_success=1
                                     THEN last_error ELSE excluded.last_error END,
                     last_agent=excluded.last_agent,
                     last_origin=excluded.last_origin,
                     source=CASE WHEN source='usage' THEN 'usage' ELSE excluded.source END""",
                (sha, safe_code, len(code), 0 if safe_code == code else 1, now, now,
                 ok, 1 - ok, ok, ms, err, str(agent or "")[:80], str(origin or "")[:40],
                 el._episode_source(), edition),
            )
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception:
        return False
