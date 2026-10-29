"""은퇴한 과제 원문의 읽기 전용 조회. 실행·초기화·수정 경로 없음."""

def read_trace_bindings(db_path, *, episode_id=None, task_id=None, owner=None):
    """Explicit source scope + agent_key + pursuit_turn key; never recover or maintain."""
    from trace_read import bounded_rows, guarded, readonly, result
    def read():
        where, args = ("t.episode_id=?", [str(episode_id)]) if episode_id is not None else (
            "t.task_id=?", [task_id])
        if owner is not None:
            where += " AND p.agent_key=?"
            args.append(owner)
        with readonly(db_path) as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pursuit_turn'").fetchone():
                return result("pursuits", status="missing", reason="ledger_schema_missing")
            rows = bounded_rows(conn,
                "SELECT t.pursuit_id,t.task_id,t.episode_id,t.state AS turn_state,"
                "p.agent_key,p.version,p.status FROM pursuit_turn t JOIN pursuit p "
                "ON p.id=t.pursuit_id WHERE " + where + " ORDER BY t.source_order", args)
            return result("pursuits", rows)
    return guarded("pursuits", read)


def read_trace_events(db_path, task_id, owner, cursor=None, limit=50):
    from trace_read import sql_page
    return sql_page("pursuit_events", db_path, "pursuit_event", "id,pursuit_id,task_id,kind,created_at",
                    "task_id=? AND pursuit_id IN (SELECT id FROM pursuit WHERE agent_key=?)",
                    (task_id, owner), cursor, limit)


def read_trace_text(db_path, pursuit_id, task_id, owner, field, offset, limit):
    from trace_read import ReadFault, fingerprint, guarded, readonly, result
    def read():
        if field not in {"input", "response"}:
            raise ReadFault("forbidden", "invalid_reference")
        where = "pursuit_id=? AND task_id=? AND pursuit_id IN (SELECT id FROM pursuit WHERE agent_key=?)"
        args = (pursuit_id, task_id, owner)
        with readonly(db_path) as conn:
            row = conn.execute(f"SELECT length({field}) FROM pursuit_turn WHERE " + where, args).fetchone()
            if row is None:
                return result("pursuits", status="missing", reason="turn_missing")
            if (row[0] or 0) > 1024 * 1024:
                raise ReadFault("partial", "document_size_budget")
            text = conn.execute(f"SELECT {field} FROM pursuit_turn WHERE " + where, args).fetchone()[0] or ""
            return result("pursuits", [{"chars": len(text), "text": text[offset:offset + limit]}],
                          high_water=fingerprint(text))
    return guarded("pursuits", read)
