"""Local blog snapshot provenance, owned by the collection boundary."""
from contextlib import closing
from datetime import datetime, timezone

MAX_AGE_SECONDS = 86400


def record_collection(conn):
    """Called in the collector's transaction after a successful RSS read."""
    conn.execute("CREATE TABLE IF NOT EXISTS blog_collection_state "
                 "(id INTEGER PRIMARY KEY CHECK(id=1), as_of TEXT NOT NULL)")
    conn.execute("INSERT OR REPLACE INTO blog_collection_state VALUES (1, ?)",
                 (datetime.now(timezone.utc).isoformat(),))


def snapshot_metadata(*, now=None):
    from tool_blog_insight import get_db
    with closing(get_db(read_only=True)) as conn:
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                              "AND name='blog_collection_state'").fetchone()
        row = conn.execute("SELECT as_of FROM blog_collection_state WHERE id=1").fetchone() if exists else None
    as_of = row[0] if row else None
    age = None
    if as_of:
        try:
            timestamp = datetime.fromisoformat(as_of)
            if timestamp.tzinfo is not None:
                age = ((now or datetime.now(timezone.utc)) - timestamp).total_seconds()
        except ValueError:
            pass
    stale = age is None or age < 0 or age > MAX_AGE_SECONDS
    return {"source": "local_snapshot", "as_of": as_of, "stale": stale,
            "freshness": "unknown" if age is None or age < 0 else "stale" if stale else "recent_collection",
            "freshness_max_age_seconds": MAX_AGE_SECONDS,
            "freshness_note": ("수집 기준 시각이 없거나 24시간보다 오래됐습니다. 최신 글이 필요하면 op:check_new로 수집하세요(쓰기)."
                               if stale else "마지막 RSS 수집 기준입니다. 이후 원격 변경은 확인하지 않았습니다.")}


def validate_category(category):
    """Reject every missing category, even inside a partly matching list."""
    if category is None:
        return
    from tool_blog_insight import get_db
    from tool_blog_rag import category_clause
    values = category if isinstance(category, list) else [category]
    missing = []
    with closing(get_db(read_only=True)) as conn:
        for value in values:
            where, params = category_clause(value)
            if not where or not conn.execute("SELECT 1 FROM posts WHERE " + where + " LIMIT 1", params).fetchone():
                missing.append(value)
    if missing:
        raise ValueError(f"블로그에 없는 폴더: {missing}. op:posts로 실제 category를 확인하세요.")
