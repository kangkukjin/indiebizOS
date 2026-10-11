"""Episode/trajectory owner's strict read API; compatibility readers remain untouched."""
import json

from trace_read import bounded_rows, guarded, readonly, result, sql_page


def read_episode_identity(path, *, episode_id=None, task_id=None, run_id=None):
    def read():
        field, value = ("id", episode_id) if episode_id is not None else (
            ("task_id", task_id) if task_id else ("run_id", run_id))
        with readonly(path) as conn:
            rows = bounded_rows(conn, "SELECT id,task_id,run_id,parent_run_id,ended_at,started_at "
                                f"FROM episode_log WHERE {field}=? ORDER BY id", (value,))
            return result("episode", rows)
    return guarded("episode", read)


def read_trajectory_page(path, episode_ids, cursor=None, limit=50):
    if not episode_ids:
        return result("trajectory", status="missing", reason="scoped_episode_identity_missing")
    page = sql_page("trajectory", path, "trajectory_event", "*",
                    "episode_id IN (" + ",".join("?" for _ in episode_ids) + ")",
                    tuple(episode_ids), cursor, limit)
    for row in page["rows"]:
        try:
            row["data"] = json.loads(row.get("data") or "{}")
            if not isinstance(row["data"], dict):
                raise ValueError
        except (ValueError, TypeError):
            row["data"] = {}
            row["_diagnostic"] = "malformed_event_data"
            page.update(status="partial", reason="malformed_event_data")
    return page


def read_episode_text(path, episode_id, offset, limit):
    from trace_read import ReadFault, fingerprint
    def read():
        with readonly(path) as conn:
            row = conn.execute("SELECT length(log) AS chars FROM episode_log WHERE id=?", (episode_id,)).fetchone()
            if row is None:
                return result("episode", status="missing", reason="episode_missing")
            if (row["chars"] or 0) > 1024 * 1024:
                raise ReadFault("partial", "document_size_budget")
            text = conn.execute("SELECT log FROM episode_log WHERE id=?", (episode_id,)).fetchone()[0] or ""
            return result("episode", [{"chars": len(text), "text": text[offset:offset + limit]}],
                          high_water=fingerprint(text))
    return guarded("episode", read)


def read_trace_store_links(path, episode_ids):
    """Discover only explicit handles up front so all file bounds freeze on page one."""
    if not episode_ids:
        return result("store_links", status="missing", reason="episode_identity_missing")
    def read():
        with readonly(path) as conn:
            # Discover handles, not every mirrored event. A single long-running
            # store must not exhaust the metadata budget with repeated references.
            # SQLite's single MIN aggregate retains the first row's provenance.
            rows = bounded_rows(conn,
                "WITH candidates AS (SELECT rowid AS position,run_id,event_seq,"
                "CASE WHEN json_valid(data) THEN CASE WHEN json_type(data)='object' "
                "THEN data END END AS data FROM trajectory_event WHERE episode_id IN ("
                + ",".join("?" for _ in episode_ids)
                + ") AND kind LIKE 'supervision.%') "
                "SELECT MIN(position),run_id,event_seq,data FROM candidates "
                "WHERE data IS NULL OR json_extract(data,'$.store') IS NOT NULL "
                "GROUP BY json_extract(data,'$.store') ORDER BY MIN(position)",
                episode_ids, limit=2000)
            links, bad = [], False
            for row in rows:
                try:
                    data = json.loads(row['data'])
                    if data.get('store') and not isinstance(data['store'], str):
                        raise ValueError
                    if data.get('store'):
                        links.append({'store': data['store'], 'seq': data.get('seq'),
                                      'record': f"pulse:{row['run_id']}:{row['event_seq']}"})
                except (ValueError, TypeError, AttributeError):
                    bad = True
            return result("store_links", links, status="partial" if bad else None,
                          reason="malformed_store_link" if bad else None)
    return guarded("store_links", read)
