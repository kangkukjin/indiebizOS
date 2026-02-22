"""
SQLite 드라이버

로컬 DB에 저장된 정보 소스들을 IBL 패턴으로 접근한다.
photo, health, blog, contact, memory 노드가 이 드라이버를 공유한다.

각 노드는 _NODE_HANDLERS에 등록된 핸들러 함수를 통해 실행된다.
핸들러 함수는 기존 도구 패키지의 함수를 호출하되,
"어디서"만 담당하고 "어떻게/무엇을"은 파이프라인이나 AI에 맡긴다.
"""
import os
import sys
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

from drivers.base import Driver

# 기존 backend 모듈 접근
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from runtime_utils import get_base_path


class SqliteDriver(Driver):
    """SQLite 기반 로컬 데이터 소스 드라이버"""

    def __init__(self):
        self._base_path = get_base_path()

    def execute(self, action: str, target: str, params: dict) -> dict:
        """노드별 핸들러에 위임"""
        node = params.pop("_node", None)
        if not node:
            return self._err("_node 파라미터가 필요합니다")

        handler = _NODE_HANDLERS.get(node)
        if not handler:
            return self._err(f"지원하지 않는 노드: {node}")

        return handler(self, action, target, params)

    def list_actions(self) -> list:
        return list(_NODE_HANDLERS.keys())

    def _get_db(self, db_path: str) -> Optional[sqlite3.Connection]:
        """DB 연결 (없으면 None)"""
        if not os.path.exists(db_path):
            return None
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ─────────────────────────────────────────
    # photo 노드
    # ─────────────────────────────────────────
    def _handle_photo(self, action: str, target: str, params: dict) -> dict:
        scan_dir = self._base_path / "data" / "photo_scans"
        scans_json = scan_dir / "scans.json"

        if not scans_json.exists():
            return self._err("사진 스캔 데이터가 없습니다. photo-manager로 먼저 스캔하세요.")

        with open(scans_json, 'r', encoding='utf-8') as f:
            scans = json.load(f)

        if action == "list_scans":
            return self._ok(
                [{"id": s.get("id"), "path": s.get("root_path"), "count": s.get("file_count", 0)} for s in scans],
                f"사진 스캔 {len(scans)}개"
            )

        # scan_id 결정
        scan_id = params.get("scan_id")
        if not scan_id and scans:
            scan_id = scans[0].get("id")
        if not scan_id:
            return self._err("scan_id가 필요합니다")

        db_path = scan_dir / f"scan_{scan_id}.db"
        conn = self._get_db(str(db_path))
        if not conn:
            return self._err(f"스캔 DB를 찾을 수 없습니다: scan_{scan_id}.db")

        try:
            if action in ("search", "search_photos"):
                return self._photo_search(conn, target, params)
            elif action in ("get", "photo_detail"):
                return self._photo_get(conn, target)
            elif action == "timeline":
                return self._photo_timeline(conn, params)
            elif action == "stats":
                return self._photo_stats(conn)
            else:
                return self._err(f"photo 노드에 '{action}' 액션이 없습니다")
        finally:
            conn.close()

    def _photo_search(self, conn, query: str, params: dict) -> dict:
        media_type = params.get("media_type", "all")
        limit = params.get("limit", 20)
        sort_by = params.get("sort_by", "taken_date DESC")

        sql = "SELECT id, path, filename, media_type, taken_date, camera_model, width, height, size FROM media_files WHERE 1=1"
        args = []

        if query:
            sql += " AND (filename LIKE ? OR camera_model LIKE ?)"
            args.extend([f"%{query}%", f"%{query}%"])
        if media_type != "all":
            sql += " AND media_type = ?"
            args.append(media_type)

        sql += f" ORDER BY {sort_by} LIMIT ?"
        args.append(limit)

        rows = conn.execute(sql, args).fetchall()
        items = [dict(r) for r in rows]
        return self._ok(items, f"사진 검색 '{query}' → {len(items)}건")

    def _photo_get(self, conn, media_id: str) -> dict:
        row = conn.execute("SELECT * FROM media_files WHERE id = ?", (media_id,)).fetchone()
        if not row:
            return self._err(f"미디어 ID {media_id}를 찾을 수 없습니다")
        return self._ok(dict(row))

    def _photo_timeline(self, conn, params: dict) -> dict:
        rows = conn.execute("""
            SELECT strftime('%Y-%m', taken_date) as month, COUNT(*) as count, media_type
            FROM media_files
            WHERE taken_date IS NOT NULL
            GROUP BY month, media_type
            ORDER BY month DESC
        """).fetchall()
        items = [dict(r) for r in rows]
        return self._ok(items, f"타임라인 {len(items)}개 월")

    def _photo_stats(self, conn) -> dict:
        total = conn.execute("SELECT COUNT(*) as cnt FROM media_files").fetchone()["cnt"]
        photos = conn.execute("SELECT COUNT(*) as cnt FROM media_files WHERE media_type='photo'").fetchone()["cnt"]
        videos = conn.execute("SELECT COUNT(*) as cnt FROM media_files WHERE media_type='video'").fetchone()["cnt"]
        return self._ok(
            {"total": total, "photos": photos, "videos": videos},
            f"총 {total}개 (사진 {photos}, 동영상 {videos})"
        )

    # ─────────────────────────────────────────
    # health 노드
    # ─────────────────────────────────────────
    def _handle_health(self, action: str, target: str, params: dict) -> dict:
        db_path = self._base_path / "data" / "health" / "health_records.db"
        conn = self._get_db(str(db_path))
        if not conn:
            return self._err("건강 기록 DB가 없습니다")

        try:
            person = params.get("person", "기본")
            person_id = self._get_person_id(conn, person)

            if action == "query":
                return self._health_query(conn, target, params, person_id)
            elif action == "log":
                return self._health_log(conn, target, params, person_id)
            elif action == "summary":
                return self._health_summary(conn, params, person_id, person)
            elif action == "history":
                return self._health_history(conn, target, params, person_id)
            else:
                return self._err(f"health 노드에 '{action}' 액션이 없습니다")
        finally:
            conn.close()

    def _get_person_id(self, conn, name: str) -> Optional[int]:
        row = conn.execute("SELECT id FROM persons WHERE name = ?", (name,)).fetchone()
        return row["id"] if row else None

    def _health_query(self, conn, category: str, params: dict, person_id: int) -> dict:
        if not person_id:
            return self._err("등록된 사용자가 없습니다")

        days = params.get("days", 30)
        limit = params.get("limit", 50)
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        if category in ("blood_pressure", "blood_sugar", "weight", "heart_rate", "temperature", "oxygen"):
            rows = conn.execute("""
                SELECT id, category, value_json, measured_at, note
                FROM measurements
                WHERE person_id = ? AND category = ? AND measured_at >= ?
                ORDER BY measured_at DESC LIMIT ?
            """, (person_id, category, since, limit)).fetchall()
            items = []
            for r in rows:
                item = dict(r)
                try:
                    item["value"] = json.loads(item.pop("value_json", "{}"))
                except:
                    pass
                items.append(item)
            return self._ok(items, f"{category} 기록 {len(items)}건 (최근 {days}일)")

        elif category in ("symptom", "symptoms"):
            rows = conn.execute("""
                SELECT id, category, description, severity, started_at, ended_at, note
                FROM symptoms
                WHERE person_id = ? AND started_at >= ?
                ORDER BY started_at DESC LIMIT ?
            """, (person_id, since, limit)).fetchall()
            items = [dict(r) for r in rows]
            return self._ok(items, f"증상 기록 {len(items)}건")

        elif category in ("medication", "medications"):
            rows = conn.execute("""
                SELECT id, name, dosage, frequency, reason, started_at, ended_at, is_active, note
                FROM medications
                WHERE person_id = ?
                ORDER BY started_at DESC LIMIT ?
            """, (person_id, limit)).fetchall()
            items = [dict(r) for r in rows]
            return self._ok(items, f"약물 기록 {len(items)}건")

        else:
            # 범용 검색
            return self._health_search_all(conn, category, person_id, limit)

    def _health_search_all(self, conn, keyword: str, person_id: int, limit: int) -> dict:
        results = []
        # measurements
        rows = conn.execute("""
            SELECT 'measurement' as type, category, value_json as detail, measured_at as date, note
            FROM measurements WHERE person_id = ? AND (category LIKE ? OR note LIKE ?)
            ORDER BY measured_at DESC LIMIT ?
        """, (person_id, f"%{keyword}%", f"%{keyword}%", limit)).fetchall()
        results.extend([dict(r) for r in rows])

        # symptoms
        rows = conn.execute("""
            SELECT 'symptom' as type, category, description as detail, started_at as date, note
            FROM symptoms WHERE person_id = ? AND (category LIKE ? OR description LIKE ? OR note LIKE ?)
            ORDER BY started_at DESC LIMIT ?
        """, (person_id, f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", limit)).fetchall()
        results.extend([dict(r) for r in rows])

        return self._ok(results, f"건강 검색 '{keyword}' → {len(results)}건")

    def _health_log(self, conn, category: str, params: dict, person_id: int) -> dict:
        if not person_id:
            # 기본 사용자 생성
            conn.execute("INSERT OR IGNORE INTO persons (name) VALUES (?)", ("기본",))
            conn.commit()
            person_id = conn.execute("SELECT id FROM persons WHERE name = '기본'").fetchone()["id"]

        value = params.get("value", {})
        note = params.get("note", "")
        measured_at = params.get("measured_at", datetime.now().strftime("%Y-%m-%d %H:%M"))

        conn.execute("""
            INSERT INTO measurements (person_id, category, value_json, measured_at, note)
            VALUES (?, ?, ?, ?, ?)
        """, (person_id, category, json.dumps(value, ensure_ascii=False), measured_at, note))
        conn.commit()

        return self._ok({"category": category, "value": value, "measured_at": measured_at},
                        f"{category} 기록 완료: {value}")

    def _health_summary(self, conn, params: dict, person_id: int, person_name: str) -> dict:
        if not person_id:
            return self._err("등록된 사용자가 없습니다")

        days = params.get("days", 30)
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        summary = {"person": person_name, "period_days": days}

        # 측정값 요약
        cats = conn.execute("""
            SELECT category, COUNT(*) as cnt
            FROM measurements WHERE person_id = ? AND measured_at >= ?
            GROUP BY category
        """, (person_id, since)).fetchall()
        summary["measurements"] = {r["category"]: r["cnt"] for r in cats}

        # 활성 증상
        symptoms = conn.execute("""
            SELECT category, severity, started_at
            FROM symptoms WHERE person_id = ? AND ended_at IS NULL
        """, (person_id,)).fetchall()
        summary["active_symptoms"] = [dict(r) for r in symptoms]

        # 현재 복용 약
        meds = conn.execute("""
            SELECT name, dosage, frequency
            FROM medications WHERE person_id = ? AND is_active = 1
        """, (person_id,)).fetchall()
        summary["current_medications"] = [dict(r) for r in meds]

        return self._ok(summary, f"{person_name}의 건강 요약 (최근 {days}일)")

    def _health_history(self, conn, category: str, params: dict, person_id: int) -> dict:
        return self._health_query(conn, category, params, person_id)

    # ─────────────────────────────────────────
    # blog 노드
    # ─────────────────────────────────────────
    def _handle_blog(self, action: str, target: str, params: dict) -> dict:
        # blog RAG DB
        blog_db_path = self._base_path / "data" / "packages" / "installed" / "tools" / "blog" / "data" / "blog_insight.db"
        conn = self._get_db(str(blog_db_path))
        if not conn:
            return self._err("블로그 DB가 없습니다")

        try:
            if action == "search":
                return self._blog_search(conn, target, params)
            elif action == "get_post":
                return self._blog_get_post(conn, target)
            elif action == "list":
                return self._blog_list(conn, params)
            elif action == "stats":
                return self._blog_stats(conn)
            else:
                return self._err(f"blog 노드에 '{action}' 액션이 없습니다")
        finally:
            conn.close()

    def _blog_search(self, conn, query: str, params: dict) -> dict:
        limit = params.get("limit", 10)

        # FTS5 검색 시도
        try:
            rows = conn.execute("""
                SELECT p.post_id, p.title, substr(p.content, 1, 200) as preview,
                       p.pub_date, p.category
                FROM posts_fts f
                JOIN posts p ON p.rowid = f.rowid
                WHERE posts_fts MATCH ?
                ORDER BY rank LIMIT ?
            """, (query, limit)).fetchall()
            items = [dict(r) for r in rows]
            search_type = "fts5"
        except:
            # FTS5 실패 시 LIKE 검색
            rows = conn.execute("""
                SELECT post_id, title, substr(content, 1, 200) as preview,
                       pub_date, category
                FROM posts
                WHERE title LIKE ? OR content LIKE ?
                ORDER BY pub_date DESC LIMIT ?
            """, (f"%{query}%", f"%{query}%", limit)).fetchall()
            items = [dict(r) for r in rows]
            search_type = "keyword"

        return self._ok(
            {"results": items, "search_type": search_type, "query": query},
            f"블로그 검색 '{query}' → {len(items)}건 ({search_type})"
        )

    def _blog_get_post(self, conn, post_id: str) -> dict:
        row = conn.execute("""
            SELECT post_id, title, content, pub_date, category, char_count
            FROM posts WHERE post_id = ?
        """, (post_id,)).fetchone()
        if not row:
            return self._err(f"포스트 '{post_id}'를 찾을 수 없습니다")
        return self._ok(dict(row))

    def _blog_list(self, conn, params: dict) -> dict:
        limit = params.get("limit", 20)
        category = params.get("category")

        sql = "SELECT post_id, title, pub_date, category, char_count FROM posts"
        args = []
        if category:
            sql += " WHERE category = ?"
            args.append(category)
        sql += " ORDER BY pub_date DESC LIMIT ?"
        args.append(limit)

        rows = conn.execute(sql, args).fetchall()
        items = [dict(r) for r in rows]
        return self._ok(items, f"블로그 글 {len(items)}건")

    def _blog_stats(self, conn) -> dict:
        total = conn.execute("SELECT COUNT(*) as cnt FROM posts").fetchone()["cnt"]
        cats = conn.execute("""
            SELECT category, COUNT(*) as cnt FROM posts
            GROUP BY category ORDER BY cnt DESC
        """).fetchall()
        return self._ok(
            {"total_posts": total, "categories": {r["category"]: r["cnt"] for r in cats}},
            f"블로그 총 {total}개 글"
        )

    # ─────────────────────────────────────────
    # contact 노드
    # ─────────────────────────────────────────
    def _handle_contact(self, action: str, target: str, params: dict) -> dict:
        db_path = self._base_path / "data" / "business.db"
        conn = self._get_db(str(db_path))
        if not conn:
            return self._err("연락처 DB가 없습니다")

        try:
            if action == "search":
                return self._contact_search(conn, target, params)
            elif action == "get":
                return self._contact_get(conn, target)
            elif action == "list":
                return self._contact_list(conn, params)
            elif action == "messages":
                return self._contact_messages(conn, target, params)
            else:
                return self._err(f"contact 노드에 '{action}' 액션이 없습니다")
        finally:
            conn.close()

    def _contact_search(self, conn, query: str, params: dict) -> dict:
        limit = params.get("limit", 20)
        rows = conn.execute("""
            SELECT n.id, n.name, n.rating, n.additional_info, n.info_level,
                   GROUP_CONCAT(c.contact_type || ':' || c.contact_value, ', ') as contacts
            FROM neighbors n
            LEFT JOIN contacts c ON c.neighbor_id = n.id
            WHERE n.name LIKE ? OR n.additional_info LIKE ?
            GROUP BY n.id
            ORDER BY n.rating DESC, n.name
            LIMIT ?
        """, (f"%{query}%", f"%{query}%", limit)).fetchall()
        items = [dict(r) for r in rows]
        return self._ok(items, f"연락처 검색 '{query}' → {len(items)}건")

    def _contact_get(self, conn, neighbor_id: str) -> dict:
        row = conn.execute("""
            SELECT id, name, rating, info_level, additional_info, business_doc,
                   favorite, created_at
            FROM neighbors WHERE id = ?
        """, (neighbor_id,)).fetchone()
        if not row:
            return self._err(f"연락처 ID {neighbor_id}를 찾을 수 없습니다")

        result = dict(row)
        # 연락 수단
        contacts = conn.execute(
            "SELECT contact_type, contact_value FROM contacts WHERE neighbor_id = ?",
            (neighbor_id,)
        ).fetchall()
        result["contacts"] = [dict(c) for c in contacts]
        return self._ok(result)

    def _contact_list(self, conn, params: dict) -> dict:
        limit = params.get("limit", 50)
        favorite_only = params.get("favorite", False)

        sql = """
            SELECT n.id, n.name, n.rating, n.info_level,
                   GROUP_CONCAT(c.contact_type || ':' || c.contact_value, ', ') as contacts
            FROM neighbors n
            LEFT JOIN contacts c ON c.neighbor_id = n.id
        """
        args = []
        if favorite_only:
            sql += " WHERE n.favorite = 1"
        sql += " GROUP BY n.id ORDER BY n.name LIMIT ?"
        args.append(limit)

        rows = conn.execute(sql, args).fetchall()
        items = [dict(r) for r in rows]
        return self._ok(items, f"연락처 {len(items)}명")

    def _contact_messages(self, conn, neighbor_id: str, params: dict) -> dict:
        limit = params.get("limit", 20)
        rows = conn.execute("""
            SELECT id, subject, content, message_time, is_from_user, contact_type, status
            FROM messages
            WHERE neighbor_id = ?
            ORDER BY message_time DESC LIMIT ?
        """, (neighbor_id, limit)).fetchall()
        items = [dict(r) for r in rows]
        return self._ok(items, f"메시지 {len(items)}건")

    # ─────────────────────────────────────────
    # memory 노드
    # ─────────────────────────────────────────
    def _handle_memory(self, action: str, target: str, params: dict) -> dict:
        project_path = params.get("project_path", "")
        if not project_path:
            return self._err("project_path가 필요합니다 (대화 DB 위치)")

        db_path = os.path.join(project_path, "conversations.db")
        conn = self._get_db(db_path)
        if not conn:
            return self._err(f"대화 DB를 찾을 수 없습니다: {db_path}")

        try:
            if action == "search":
                return self._memory_search(conn, target, params)
            elif action == "recent":
                return self._memory_recent(conn, params)
            elif action == "agents":
                return self._memory_agents(conn)
            else:
                return self._err(f"memory 노드에 '{action}' 액션이 없습니다")
        finally:
            conn.close()

    def _memory_search(self, conn, keyword: str, params: dict) -> dict:
        limit = params.get("limit", 20)
        agent = params.get("agent")

        sql = """
            SELECT m.id, a_from.name as from_agent, a_to.name as to_agent,
                   substr(m.content, 1, 300) as content_preview,
                   m.message_time
            FROM messages m
            LEFT JOIN agents a_from ON m.from_agent_id = a_from.id
            LEFT JOIN agents a_to ON m.to_agent_id = a_to.id
            WHERE m.content LIKE ?
        """
        args = [f"%{keyword}%"]

        if agent:
            sql += " AND (a_from.name = ? OR a_to.name = ?)"
            args.extend([agent, agent])

        sql += " ORDER BY m.message_time DESC LIMIT ?"
        args.append(limit)

        rows = conn.execute(sql, args).fetchall()
        items = [dict(r) for r in rows]
        return self._ok(items, f"대화 검색 '{keyword}' → {len(items)}건")

    def _memory_recent(self, conn, params: dict) -> dict:
        limit = params.get("limit", 10)
        agent = params.get("agent")

        sql = """
            SELECT m.id, a_from.name as from_agent, a_to.name as to_agent,
                   substr(m.content, 1, 300) as content_preview,
                   m.message_time
            FROM messages m
            LEFT JOIN agents a_from ON m.from_agent_id = a_from.id
            LEFT JOIN agents a_to ON m.to_agent_id = a_to.id
        """
        args = []
        if agent:
            sql += " WHERE a_from.name = ? OR a_to.name = ?"
            args.extend([agent, agent])

        sql += " ORDER BY m.message_time DESC LIMIT ?"
        args.append(limit)

        rows = conn.execute(sql, args).fetchall()
        items = [dict(r) for r in rows]
        return self._ok(items, f"최근 대화 {len(items)}건")

    def _memory_agents(self, conn) -> dict:
        rows = conn.execute("SELECT id, name, type FROM agents ORDER BY name").fetchall()
        items = [dict(r) for r in rows]
        return self._ok(items, f"에이전트 {len(items)}명")


# ─────────────────────────────────────────
# 노드 → 핸들러 매핑
# ─────────────────────────────────────────
_NODE_HANDLERS = {
    "photo": SqliteDriver._handle_photo,
    "health": SqliteDriver._handle_health,
    "blog": SqliteDriver._handle_blog,
    "contact": SqliteDriver._handle_contact,
    "memory": SqliteDriver._handle_memory,
}


# 싱글톤 인스턴스
_instance = None

def get_driver() -> SqliteDriver:
    global _instance
    if _instance is None:
        _instance = SqliteDriver()
    return _instance
