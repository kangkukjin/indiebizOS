"""자아별 과제 원장: 현재 상태, 사건, 아직 요약되지 않은 턴을 함께 보존한다.

의미 판단은 호출자 몫. 이 층은 소유권, 원자적 버전 검사, 멱등성, 시간 순서만 소유한다.
늦은 요약은 후속 턴이 고친 필드를 되돌리지 못한다. 원문은 사건에 계속 남는다.
"""
import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

PROCESS = f"{os.getpid()}:{uuid.uuid4().hex}"
TEXT_LIMITS = {"title": 60, "framing": 3000, "approach": 1500,
               "goal_criteria": 1500, "progress": 3000, "next": 600, "origin": 500}
LIST_LIMITS = {"assumptions": 12, "open_questions": 8, "artifacts": 30}
SUMMARY_FIELDS = {"progress", "next", "open_questions", "artifacts"}
STATUSES = {"active", "parked", "done", "abandoned"}
PAGE_LIMIT = 100


def page_bounds(offset, limit):
    if type(offset) is not int or offset < 0:
        raise ValueError("offset은 0 이상의 정수여야 합니다")
    if type(limit) is not int or not 1 <= limit <= PAGE_LIMIT:
        raise ValueError(f"limit은 1~{PAGE_LIMIT}이어야 합니다. offset으로 다음 페이지를 읽으세요")
    return offset, limit


class Conflict(Exception):
    def __init__(self, current):
        self.current = current
        super().__init__(f"원장 version 충돌: 현재 {current['version']}")


def validate(patch):
    if not isinstance(patch, dict):
        raise ValueError("patch는 객체여야 합니다")
    allowed = set(TEXT_LIMITS) | set(LIST_LIMITS) | {"status", "waiting_for", "framing_meta"}
    if set(patch) - allowed:
        raise ValueError(f"허용되지 않은 과제 필드: {sorted(set(patch) - allowed)}")
    for key, value in patch.items():
        if key in TEXT_LIMITS and (not isinstance(value, str) or len(value) > TEXT_LIMITS[key]):
            raise ValueError(f"{key}: {TEXT_LIMITS[key]}자 이내로 압축해 다시 쓰세요")
        if key in {"title", "goal_criteria"} and not value.strip():
            raise ValueError(f"{key}는 비울 수 없습니다")
        if key in LIST_LIMITS:
            if not isinstance(value, list) or len(value) > LIST_LIMITS[key]:
                raise ValueError(f"{key}: {LIST_LIMITS[key]}항목 이내로 압축해 다시 쓰세요")
            if any(len(json.dumps(v, ensure_ascii=False)) > 2000 for v in value):
                raise ValueError(f"{key}: 항목당 2000자 제한")
            if key in {"open_questions", "artifacts"} and any(not isinstance(v, str) for v in value):
                raise ValueError(f"{key}: 문자열 목록이어야 합니다")
        if key == "status" and value not in STATUSES:
            raise ValueError("알 수 없는 과제 상태")
        if key == "waiting_for":
            if not isinstance(value, dict) or set(value) - {"text", "probe"}:
                raise ValueError("waiting_for는 text/probe 객체입니다")
            if not isinstance(value.get("text", ""), str) or len(value.get("text", "")) > 300:
                raise ValueError("waiting_for.text: 300자 제한")
            if not isinstance(value.get("probe", ""), str) or len(value.get("probe", "")) > 2000:
                raise ValueError("probe: 2000자 제한(저장만, 실행하지 않음)")
        if key == "framing_meta" and (not isinstance(value, dict)
                or len(json.dumps(value, ensure_ascii=False)) > 12000):
            raise ValueError("framing_meta: 12000자 객체 제한")
    for a in patch.get("assumptions", []):
        if not isinstance(a, dict) or a.get("status") not in {"holding", "broken"}:
            raise ValueError("assumptions 항목은 text/status/evidence/turn 객체입니다")
        if any(not isinstance(a.get(k, ""), str) for k in ("text", "evidence", "turn")):
            raise ValueError("전제의 text/evidence/turn은 문자열이어야 합니다")


class PursuitLedger:
    def __init__(self, db_path, agent_key):
        if not agent_key:
            raise ValueError("과제 원장은 자아 신원이 필요합니다")
        self.db_path, self.agent_key = str(db_path), str(agent_key)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS pursuit (
                    id TEXT PRIMARY KEY, agent_key TEXT NOT NULL, state TEXT NOT NULL,
                    version INTEGER NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL,
                    last_turn_at REAL NOT NULL, status TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS pursuit_owner ON pursuit(agent_key, status);
                CREATE TABLE IF NOT EXISTS pursuit_event (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, pursuit_id TEXT NOT NULL,
                    event_key TEXT NOT NULL, task_id TEXT NOT NULL, kind TEXT NOT NULL,
                    payload TEXT NOT NULL, created_at REAL NOT NULL,
                    FOREIGN KEY(pursuit_id) REFERENCES pursuit(id) ON DELETE CASCADE,
                    UNIQUE(pursuit_id,event_key));
                CREATE TABLE IF NOT EXISTS pursuit_turn (
                    pursuit_id TEXT NOT NULL, task_id TEXT NOT NULL, source_order INTEGER NOT NULL,
                    process TEXT NOT NULL, state TEXT NOT NULL, input TEXT NOT NULL,
                    response TEXT NOT NULL DEFAULT '', tools TEXT NOT NULL DEFAULT '[]',
                    episode_id TEXT, error TEXT, updated_at REAL NOT NULL,
                    PRIMARY KEY(pursuit_id,task_id),
                    FOREIGN KEY(pursuit_id) REFERENCES pursuit(id) ON DELETE CASCADE);
            """)

    @contextmanager
    def connect(self, write=False):
        c = sqlite3.connect(self.db_path, timeout=15)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                c.execute("BEGIN IMMEDIATE")
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def _get(self, c, pid):
        r = c.execute("SELECT * FROM pursuit WHERE id=? AND agent_key=?",
                      (pid, self.agent_key)).fetchone()
        if r is None:
            raise KeyError("이 자아의 과제를 찾을 수 없습니다")
        result = json.loads(r["state"])
        result.update({k: r[k] for k in ("id", "agent_key", "version", "created_at",
                                        "updated_at", "last_turn_at", "status")})
        return result

    def get(self, pid):
        with self.connect() as c:
            return self._get(c, pid)

    def list(self, statuses=("active", "parked"), limit=50, offset=0):
        offset, limit = page_bounds(offset, limit)
        with self.connect() as c:
            sql = "SELECT id FROM pursuit WHERE agent_key=?"
            args = [self.agent_key]
            if statuses:
                sql += " AND status IN (" + ",".join("?" for _ in statuses) + ")"
                args.extend(statuses)
            total = c.execute(sql.replace("SELECT id", "SELECT count(*)"), args).fetchone()[0]
            rows = c.execute(sql + " ORDER BY (status='active') DESC,last_turn_at DESC,id LIMIT ? OFFSET ?",
                             args + [limit, offset]).fetchall()
            return {"items": [self._get(c, r[0]) for r in rows], "total": total,
                    "next_offset": offset + limit if offset + limit < total else None}

    def _event(self, c, pid, key, task, kind, payload):
        c.execute("INSERT OR IGNORE INTO pursuit_event "
                  "(pursuit_id,event_key,task_id,kind,payload,created_at) VALUES (?,?,?,?,?,?)",
                  (pid, key, task, kind, json.dumps(payload, ensure_ascii=False, default=str), time.time()))
        return c.execute("SELECT id FROM pursuit_event WHERE pursuit_id=? AND event_key=?",
                         (pid, key)).fetchone()[0]

    def create(self, title, goal_criteria, task_id, **fields):
        validate({"title": title, "goal_criteria": goal_criteria, **fields})
        if not title.strip() or not goal_criteria.strip() or not task_id:
            raise ValueError("title, goal_criteria, task_id가 필요합니다")
        # 같은 턴 생성 재시도는 같은 과제에 닿는다. UUID 전체를 써 장기 원장의 충돌을 피한다.
        pid = "pursuit_" + uuid.uuid5(uuid.NAMESPACE_URL, self.agent_key + ":" + task_id).hex
        now = time.time()
        with self.connect(True) as c:
            if c.execute("SELECT 1 FROM pursuit WHERE id=?", (pid,)).fetchone():
                return self._get(c, pid)
            state = {"title": title, "goal_criteria": goal_criteria, "framing": "", "approach": "",
                     "progress": "", "next": "", "assumptions": [], "open_questions": [],
                     "artifacts": [], "waiting_for": {}, "framing_meta": {}, "_field_order": {}, **fields}
            c.execute("INSERT INTO pursuit VALUES (?,?,?,?,?,?,?,?)",
                      (pid, self.agent_key, json.dumps(state, ensure_ascii=False), 1, now, now, now, "active"))
            self._event(c, pid, "created", task_id, "created", state)
            return self._get(c, pid)

    def begin_turn(self, pid, task_id, message, episode_id=None, execution=False):
        with self.connect(True) as c:
            self._get(c, pid)
            if execution and c.execute("SELECT 1 FROM pursuit_turn WHERE pursuit_id=? AND task_id!=? "
                                       "AND state='running' AND process=?", (pid, task_id, PROCESS)).fetchone():
                raise ValueError("이 과제의 다른 턴이 실행 중입니다. 종료 후 이어가세요")
            seq = self._event(c, pid, "turn:" + task_id, task_id, "turn.started", {"input": message})
            c.execute("INSERT OR IGNORE INTO pursuit_turn "
                      "(pursuit_id,task_id,source_order,process,state,input,episode_id,updated_at) "
                      "VALUES (?,?,?,?,'running',?,?,?)",
                      (pid, task_id, seq, PROCESS, message, str(episode_id or ""), time.time()))
            c.execute("UPDATE pursuit SET last_turn_at=? WHERE id=?", (time.time(), pid))
            return seq

    def finish_turn(self, pid, task_id, response, tools, interrupted=False):
        with self.connect(True) as c:
            self._get(c, pid)
            kind = "interrupted" if interrupted else "pending"
            self._event(c, pid, "end:" + task_id, task_id, "turn." + kind,
                        {"response": response, "tools": tools})
            c.execute("UPDATE pursuit_turn SET state=?,response=?,tools=?,updated_at=? "
                      "WHERE pursuit_id=? AND task_id=? AND state='running'",
                      (kind, response, json.dumps(tools, ensure_ascii=False, default=str),
                       time.time(), pid, task_id))

    def observe(self, pid, task_id, event, index):
        """응답/증류보다 먼저 도구 결말을 보존한다. 강제 종료 뒤에도 중복 실행을 피할 근거."""
        with self.connect(True) as c:
            self._get(c, pid)
            self._event(c, pid, f"tool:{task_id}:{index}", task_id, "tool.observed", event)
            r = c.execute("SELECT tools FROM pursuit_turn WHERE pursuit_id=? AND task_id=?",
                          (pid, task_id)).fetchone()
            if r:
                tools = json.loads(r[0])
                tools.append(event)
                c.execute("UPDATE pursuit_turn SET tools=?,updated_at=? WHERE pursuit_id=? AND task_id=?",
                          (json.dumps(tools, ensure_ascii=False, default=str), time.time(), pid, task_id))

    def turns(self, pid, pending_only=False):
        with self.connect() as c:
            self._get(c, pid)
            sql = "SELECT * FROM pursuit_turn WHERE pursuit_id=?"
            if pending_only:
                sql += " AND state != 'applied'"
            return [dict(r) | {"tools": json.loads(r["tools"])}
                    for r in c.execute(sql + " ORDER BY source_order", (pid,))]

    def events(self, pid, offset=0, limit=50):
        offset, limit = page_bounds(offset, limit)
        with self.connect() as c:
            self._get(c, pid)
            rows = c.execute("SELECT * FROM pursuit_event WHERE pursuit_id=? ORDER BY id LIMIT ? OFFSET ?",
                             (pid, limit, offset))
            return [dict(r) | {"payload": json.loads(r["payload"])} for r in rows]

    def apply(self, pid, task_id, base_version, patch, event_key, source_order,
              kind="note", why="", summary=False):
        validate(patch)
        if base_version is None or not event_key:
            raise ValueError("base_version과 event_key가 필요합니다")
        if summary and set(patch) - SUMMARY_FIELDS:
            raise ValueError("턴 요약은 진행 필드만 갱신할 수 있습니다")
        with self.connect(True) as c:
            row = self._get(c, pid)
            if c.execute("SELECT 1 FROM pursuit_event WHERE pursuit_id=? AND event_key=?",
                         (pid, event_key)).fetchone():
                return row  # 재시도 — 적용과 사건 적재가 같은 트랜잭션
            if row["version"] != base_version:
                raise Conflict(row)
            if "goal_criteria" in patch and patch["goal_criteria"] != row["goal_criteria"] and not why:
                raise ValueError("전체 완료 기준 변경에는 why가 필요합니다")
            if "status" in patch and not why:
                raise ValueError("상태 변경에는 why가 필요합니다")
            orders = row.get("_field_order", {})
            protected = [k for k in patch if source_order < orders.get(k, 0)]
            effective = {k: v for k, v in patch.items() if k not in protected}
            old_status = row["status"]
            row.update(effective)
            for k in effective:
                orders[k] = source_order
            row["_field_order"] = orders
            self._event(c, pid, event_key, task_id, kind,
                        {"patch": patch, "applied": effective, "superseded_fields": protected,
                         "why": why, "source_order": source_order})
            if "goal_criteria" in effective:
                self._event(c, pid, event_key + ":goal", task_id, "goal.changed",
                            {"goal_criteria": effective["goal_criteria"], "why": why})
            if old_status != "active" and row["status"] == "active":
                self._event(c, pid, event_key + ":revive", task_id, "revived", {"from": old_status, "why": why})
            state = {k: v for k, v in row.items() if k not in
                     {"id", "agent_key", "version", "created_at", "updated_at", "last_turn_at", "status"}}
            c.execute("UPDATE pursuit SET state=?,status=?,version=version+1,updated_at=? "
                      "WHERE id=? AND version=?",
                      (json.dumps(state, ensure_ascii=False), row["status"], time.time(), pid, base_version))
            if summary:
                c.execute("UPDATE pursuit_turn SET state='applied',error=NULL,updated_at=? "
                          "WHERE pursuit_id=? AND task_id=?", (time.time(), pid, task_id))
            return self._get(c, pid)

    def summary_failed(self, pid, task_id, error):
        with self.connect(True) as c:
            self._get(c, pid)
            c.execute("UPDATE pursuit_turn SET error=?,updated_at=? WHERE pursuit_id=? AND task_id=?",
                      (str(error), time.time(), pid, task_id))
            self._event(c, pid, f"merge_failed:{task_id}:{uuid.uuid4().hex}", task_id,
                        "merge_failed", {"error": str(error)})

    def recover(self):
        """이전 프로세스의 열린 턴만 중단으로 표시. 원문·미처리 요약은 만료하지 않는다."""
        with self.connect(True) as c:
            rows = c.execute("SELECT t.* FROM pursuit_turn t JOIN pursuit p ON p.id=t.pursuit_id "
                             "WHERE p.agent_key=? AND t.state='running' AND t.process!=?",
                             (self.agent_key, PROCESS)).fetchall()
            for r in rows:
                self._event(c, r["pursuit_id"], "orphan:" + r["task_id"], r["task_id"],
                            "turn.interrupted", {"note": "재기동으로 중단. 실제 산출물을 확인하기 전 재실행 금지"})
                c.execute("UPDATE pursuit_turn SET state='interrupted' WHERE pursuit_id=? AND task_id=?",
                          (r["pursuit_id"], r["task_id"]))
            return len(rows)

    def delete(self, pid, base_version):
        with self.connect(True) as c:
            row = self._get(c, pid)
            if row["version"] != base_version:
                raise Conflict(row)
            c.execute("DELETE FROM pursuit WHERE id=? AND agent_key=?", (pid, self.agent_key))

    def maintain(self, now=None):
        now = now or time.time()
        changed = 0
        rows, offset = [], 0
        while True:
            page = self.list(limit=100, offset=offset)
            rows.extend(page["items"])
            if page["next_offset"] is None:
                break
            offset = page["next_offset"]
        for row in rows:
            days = (now - row["last_turn_at"]) / 86400
            status = "abandoned" if days >= 120 else "parked" if days >= 30 else row["status"]
            if status != row["status"]:
                task = "lifecycle:" + uuid.uuid4().hex
                seq = self.begin_turn(row["id"], task, "과제 생명주기 순찰")
                self.apply(row["id"], task, row["version"], {"status": status}, task, seq,
                           kind="lifecycle", why=f"{int(days)}일 무접촉")
                with self.connect(True) as c:
                    c.execute("UPDATE pursuit SET last_turn_at=? WHERE id=?", (row["last_turn_at"], row["id"]))
                    c.execute("UPDATE pursuit_turn SET state='applied' WHERE pursuit_id=? AND task_id=?",
                              (row["id"], task))
                changed += 1
        return changed


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
