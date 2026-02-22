"""
collector_db.py - Web Collector DB 관리
=======================================
사이트별 수집 데이터를 JSON blob으로 저장.
FTS5 전문 검색, 중복 제거, 수집 로그 지원.
"""

import json
import os
import sqlite3
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "web_collector.db")


# =============================================================================
# DB 연결 및 스키마
# =============================================================================

def get_db() -> sqlite3.Connection:
    """DB 연결 생성 + 테이블/FTS5/트리거 초기화"""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row

    # 수집 항목 테이블 (JSON blob 방식)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id TEXT NOT NULL,
            item_key TEXT NOT NULL,
            data TEXT NOT NULL,
            search_text TEXT,
            collected_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(site_id, item_key)
        )
    """)

    # 사이트별 인덱스
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_items_site
        ON items(site_id)
    """)

    # FTS5 전문 검색
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
            search_text,
            content='items', content_rowid='id'
        )
    """)

    # FTS5 동기화 트리거
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS items_fts_insert
        AFTER INSERT ON items BEGIN
            INSERT INTO items_fts(rowid, search_text)
            VALUES (new.id, new.search_text);
        END
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS items_fts_delete
        AFTER DELETE ON items BEGIN
            INSERT INTO items_fts(items_fts, rowid, search_text)
            VALUES ('delete', old.id, old.search_text);
        END
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS items_fts_update
        AFTER UPDATE ON items BEGIN
            INSERT INTO items_fts(items_fts, rowid, search_text)
            VALUES ('delete', old.id, old.search_text);
            INSERT INTO items_fts(rowid, search_text)
            VALUES (new.id, new.search_text);
        END
    """)

    # 수집 로그 테이블
    conn.execute("""
        CREATE TABLE IF NOT EXISTS collection_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id TEXT NOT NULL,
            started_at TEXT DEFAULT (datetime('now','localtime')),
            finished_at TEXT,
            items_found INTEGER DEFAULT 0,
            items_new INTEGER DEFAULT 0,
            items_updated INTEGER DEFAULT 0,
            status TEXT DEFAULT 'running',
            error_message TEXT,
            params TEXT
        )
    """)

    conn.commit()
    return conn


# =============================================================================
# 헬퍼
# =============================================================================

def _build_search_text(data: dict) -> str:
    """JSON 데이터에서 텍스트 필드를 추출해 검색용 텍스트 생성"""
    texts = []
    for value in data.values():
        if isinstance(value, str) and value.strip():
            texts.append(value)
        elif isinstance(value, (int, float)):
            texts.append(str(value))
    return " ".join(texts)


def _row_to_dict(row: sqlite3.Row) -> dict:
    """sqlite3.Row를 dict로 변환, data 필드는 JSON 파싱"""
    d = dict(row)
    if "data" in d and isinstance(d["data"], str):
        try:
            d["data"] = json.loads(d["data"])
        except (json.JSONDecodeError, TypeError):
            pass
    return d


# =============================================================================
# UPSERT (저장/업데이트)
# =============================================================================

def upsert_item(site_id: str, item_key: str, data: dict) -> dict:
    """
    항목 저장 또는 업데이트 (site_id + item_key 기준 중복 제거).

    Returns:
        {"success": True, "item_id": int, "action": "created"|"updated"}
    """
    conn = None
    try:
        conn = get_db()
        data_json = json.dumps(data, ensure_ascii=False)
        search_text = _build_search_text(data)

        # 기존 항목 확인
        existing = conn.execute(
            "SELECT id, data FROM items WHERE site_id = ? AND item_key = ?",
            (site_id, item_key)
        ).fetchone()

        if existing:
            # 업데이트: 기존 데이터와 병합 (새 데이터 우선)
            old_data = json.loads(existing["data"]) if existing["data"] else {}
            merged = {**old_data, **data}
            merged_json = json.dumps(merged, ensure_ascii=False)
            merged_search = _build_search_text(merged)

            conn.execute("""
                UPDATE items
                SET data = ?, search_text = ?, updated_at = datetime('now','localtime')
                WHERE id = ?
            """, (merged_json, merged_search, existing["id"]))
            conn.commit()
            return {"success": True, "item_id": existing["id"], "action": "updated"}
        else:
            cursor = conn.execute("""
                INSERT INTO items (site_id, item_key, data, search_text)
                VALUES (?, ?, ?, ?)
            """, (site_id, item_key, data_json, search_text))
            conn.commit()
            return {"success": True, "item_id": cursor.lastrowid, "action": "created"}

    except Exception as e:
        logger.error(f"[WebCollector DB] upsert_item 오류: {e}")
        return {"success": False, "error": str(e)}
    finally:
        if conn:
            conn.close()


def upsert_items_batch(site_id: str, items: List[dict], key_field: str) -> dict:
    """
    배치 upsert. items의 각 dict에서 key_field 값을 item_key로 사용.

    Returns:
        {"success": True, "new": int, "updated": int, "skipped": int, "total": int}
    """
    conn = None
    new_count = 0
    updated_count = 0
    skipped = 0

    try:
        conn = get_db()

        for item in items:
            item_key = str(item.get(key_field, ""))
            if not item_key:
                skipped += 1
                continue

            data_json = json.dumps(item, ensure_ascii=False)
            search_text = _build_search_text(item)

            existing = conn.execute(
                "SELECT id, data FROM items WHERE site_id = ? AND item_key = ?",
                (site_id, item_key)
            ).fetchone()

            if existing:
                old_data = json.loads(existing["data"]) if existing["data"] else {}
                merged = {**old_data, **item}
                merged_json = json.dumps(merged, ensure_ascii=False)
                merged_search = _build_search_text(merged)

                conn.execute("""
                    UPDATE items
                    SET data = ?, search_text = ?, updated_at = datetime('now','localtime')
                    WHERE id = ?
                """, (merged_json, merged_search, existing["id"]))
                updated_count += 1
            else:
                conn.execute("""
                    INSERT INTO items (site_id, item_key, data, search_text)
                    VALUES (?, ?, ?, ?)
                """, (site_id, item_key, data_json, search_text))
                new_count += 1

        conn.commit()
        return {
            "success": True,
            "new": new_count,
            "updated": updated_count,
            "skipped": skipped,
            "total": new_count + updated_count
        }

    except Exception as e:
        logger.error(f"[WebCollector DB] upsert_items_batch 오류: {e}")
        return {"success": False, "error": str(e)}
    finally:
        if conn:
            conn.close()


# =============================================================================
# 조회
# =============================================================================

def search_items(query: str = None, site_id: str = None,
                 limit: int = 20, offset: int = 0) -> dict:
    """FTS5 전문 검색. site_id로 필터 가능."""
    conn = None
    try:
        conn = get_db()

        if query and query.strip():
            # FTS5 검색
            try:
                sql = """
                    SELECT i.id, i.site_id, i.item_key, i.data,
                           i.collected_at, i.updated_at
                    FROM items i
                    JOIN items_fts f ON i.id = f.rowid
                    WHERE items_fts MATCH ?
                """
                params = [query.strip()]

                if site_id:
                    sql += " AND i.site_id = ?"
                    params.append(site_id)

                sql += " ORDER BY rank LIMIT ? OFFSET ?"
                params.extend([limit, offset])

                rows = conn.execute(sql, params).fetchall()
            except Exception:
                # FTS 실패 시 LIKE 폴백
                sql = """
                    SELECT id, site_id, item_key, data,
                           collected_at, updated_at
                    FROM items
                    WHERE search_text LIKE ?
                """
                params = [f"%{query.strip()}%"]

                if site_id:
                    sql += " AND site_id = ?"
                    params.append(site_id)

                sql += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
                params.extend([limit, offset])

                rows = conn.execute(sql, params).fetchall()
        else:
            # 쿼리 없으면 전체 목록
            sql = "SELECT id, site_id, item_key, data, collected_at, updated_at FROM items"
            params = []

            if site_id:
                sql += " WHERE site_id = ?"
                params.append(site_id)

            sql += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            rows = conn.execute(sql, params).fetchall()

        items = [_row_to_dict(r) for r in rows]
        return {"success": True, "count": len(items), "items": items}

    except Exception as e:
        logger.error(f"[WebCollector DB] search_items 오류: {e}")
        return {"success": False, "error": str(e)}
    finally:
        if conn:
            conn.close()


def get_stats(site_id: str = None) -> dict:
    """수집 통계: 사이트별 항목 수, 최근 수집 시각 등."""
    conn = None
    try:
        conn = get_db()

        # 전체 항목 수
        if site_id:
            total = conn.execute(
                "SELECT COUNT(*) FROM items WHERE site_id = ?", (site_id,)
            ).fetchone()[0]
        else:
            total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]

        # 사이트별 통계
        site_stats = conn.execute("""
            SELECT site_id,
                   COUNT(*) as item_count,
                   MIN(collected_at) as first_collected,
                   MAX(updated_at) as last_updated
            FROM items
            GROUP BY site_id
            ORDER BY item_count DESC
        """).fetchall()

        sites = [dict(r) for r in site_stats]

        # 최근 수집 로그
        recent_logs = conn.execute("""
            SELECT site_id, started_at, finished_at, items_found,
                   items_new, items_updated, status, error_message
            FROM collection_log
            ORDER BY started_at DESC
            LIMIT 10
        """).fetchall()

        logs = [dict(r) for r in recent_logs]

        return {
            "success": True,
            "total_items": total,
            "sites": sites,
            "recent_collections": logs
        }

    except Exception as e:
        logger.error(f"[WebCollector DB] get_stats 오류: {e}")
        return {"success": False, "error": str(e)}
    finally:
        if conn:
            conn.close()


def get_recent(site_id: str = None, limit: int = 20) -> dict:
    """최근 수집/업데이트된 항목."""
    conn = None
    try:
        conn = get_db()

        sql = "SELECT id, site_id, item_key, data, collected_at, updated_at FROM items"
        params = []

        if site_id:
            sql += " WHERE site_id = ?"
            params.append(site_id)

        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        items = [_row_to_dict(r) for r in rows]

        return {"success": True, "count": len(items), "items": items}

    except Exception as e:
        logger.error(f"[WebCollector DB] get_recent 오류: {e}")
        return {"success": False, "error": str(e)}
    finally:
        if conn:
            conn.close()


def get_item_detail(item_id: int) -> dict:
    """특정 항목 상세 조회."""
    conn = None
    try:
        conn = get_db()

        row = conn.execute(
            "SELECT id, site_id, item_key, data, collected_at, updated_at FROM items WHERE id = ?",
            (item_id,)
        ).fetchone()

        if not row:
            return {"success": False, "error": f"항목을 찾을 수 없습니다: id={item_id}"}

        return {"success": True, "item": _row_to_dict(row)}

    except Exception as e:
        logger.error(f"[WebCollector DB] get_item_detail 오류: {e}")
        return {"success": False, "error": str(e)}
    finally:
        if conn:
            conn.close()


def delete_item(item_id: int) -> dict:
    """항목 삭제."""
    conn = None
    try:
        conn = get_db()

        row = conn.execute("SELECT site_id, item_key FROM items WHERE id = ?", (item_id,)).fetchone()
        if not row:
            return {"success": False, "error": f"항목을 찾을 수 없습니다: id={item_id}"}

        conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
        conn.commit()

        return {
            "success": True,
            "deleted": f"{row['site_id']}/{row['item_key']}",
            "item_id": item_id
        }

    except Exception as e:
        logger.error(f"[WebCollector DB] delete_item 오류: {e}")
        return {"success": False, "error": str(e)}
    finally:
        if conn:
            conn.close()


# =============================================================================
# 수집 로그
# =============================================================================

def log_collection_start(site_id: str, params: dict = None) -> int:
    """수집 시작 로그. Returns log_id."""
    conn = None
    try:
        conn = get_db()
        params_json = json.dumps(params, ensure_ascii=False) if params else None
        cursor = conn.execute(
            "INSERT INTO collection_log (site_id, params) VALUES (?, ?)",
            (site_id, params_json)
        )
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        logger.error(f"[WebCollector DB] log_collection_start 오류: {e}")
        return -1
    finally:
        if conn:
            conn.close()


def log_collection_end(log_id: int, items_found: int = 0,
                       items_new: int = 0, items_updated: int = 0,
                       error: str = None):
    """수집 완료 로그."""
    conn = None
    try:
        conn = get_db()
        status = "error" if error else "success"
        conn.execute("""
            UPDATE collection_log
            SET finished_at = datetime('now','localtime'),
                items_found = ?, items_new = ?, items_updated = ?,
                status = ?, error_message = ?
            WHERE id = ?
        """, (items_found, items_new, items_updated, status, error, log_id))
        conn.commit()
    except Exception as e:
        logger.error(f"[WebCollector DB] log_collection_end 오류: {e}")
    finally:
        if conn:
            conn.close()
