"""
tool_db.py - 지역 정보 SQLite DB 관리
======================================
가게/상점 정보 CRUD + FTS5 전문 검색.
언급 빈도 기반 평판 (많이 언급될수록 사람들이 많이 가는 가게).
"""

import os
import re
import sqlite3
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "local_info.db")


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

    # 가게 정보 테이블
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            address TEXT,
            phone TEXT,
            description TEXT,
            area TEXT DEFAULT '오송',
            source TEXT,
            source_url TEXT,
            rating REAL,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # 이름+주소 유니크 인덱스 (주소가 있는 경우만)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_stores_name_address
        ON stores(name, address) WHERE address IS NOT NULL AND address != ''
    """)

    # 커뮤니티 언급 테이블 (빈도 기록용)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mentions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id INTEGER REFERENCES stores(id) ON DELETE CASCADE,
            title TEXT,
            content TEXT,
            source TEXT,
            source_url TEXT,
            post_date TEXT,
            collected_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # FTS5 전문 검색
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS stores_fts USING fts5(
            name, category, address, description, notes,
            content='stores', content_rowid='id'
        )
    """)

    # FTS5 자동 동기화 트리거
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS stores_fts_insert
        AFTER INSERT ON stores BEGIN
            INSERT INTO stores_fts(rowid, name, category, address, description, notes)
            VALUES (new.id, new.name, new.category, new.address, new.description, new.notes);
        END
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS stores_fts_delete
        AFTER DELETE ON stores BEGIN
            INSERT INTO stores_fts(stores_fts, rowid, name, category, address, description, notes)
            VALUES ('delete', old.id, old.name, old.category, old.address, old.description, old.notes);
        END
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS stores_fts_update
        AFTER UPDATE ON stores BEGIN
            INSERT INTO stores_fts(stores_fts, rowid, name, category, address, description, notes)
            VALUES ('delete', old.id, old.name, old.category, old.address, old.description, old.notes);
            INSERT INTO stores_fts(rowid, name, category, address, description, notes)
            VALUES (new.id, new.name, new.category, new.address, new.description, new.notes);
        END
    """)

    conn.commit()
    return conn


# =============================================================================
# 가게 저장/수정
# =============================================================================

def normalize_name(name: str) -> str:
    """가게 이름 정규화 (비교용) - 공백/특수문자 제거"""
    if not name:
        return ""
    normalized = re.sub(r'[\s\-_·・&,./()（）【】\[\]]+', '', name)
    return normalized.strip().lower()


def save_store(name: str, category: str = None, address: str = None,
               phone: str = None, description: str = None, area: str = "오송",
               source: str = None, source_url: str = None,
               rating: float = None, notes: str = None) -> Dict[str, Any]:
    """가게 정보 저장 (중복 감지: 이름+주소 → 이름+지역 → 이름 정규화 매칭)"""
    if not name or not name.strip():
        return {"success": False, "error": "가게 이름은 필수입니다."}

    conn = get_db()
    try:
        existing = None

        # 1단계: 이름+주소 정확히 일치
        if address and address.strip():
            existing = conn.execute(
                "SELECT id FROM stores WHERE name = ? AND address = ?",
                (name.strip(), address.strip())
            ).fetchone()

        # 2단계: 이름+지역 일치
        if not existing:
            area_val = area or "오송"
            existing = conn.execute(
                "SELECT id FROM stores WHERE name = ? AND area = ?",
                (name.strip(), area_val)
            ).fetchone()

        # 3단계: 이름 정규화 매칭 (공백/특수문자 차이)
        if not existing:
            norm = normalize_name(name)
            if norm:
                candidates = conn.execute(
                    "SELECT id, name FROM stores WHERE area = ?",
                    (area or "오송",)
                ).fetchall()
                for c in candidates:
                    if normalize_name(c['name']) == norm:
                        existing = c
                        break

        if existing:
            store_id = existing['id']
            fields = []
            values = []
            for col, val in [("category", category), ("phone", phone),
                             ("description", description), ("area", area),
                             ("source", source), ("source_url", source_url),
                             ("rating", rating), ("notes", notes)]:
                if val is not None:
                    fields.append(f"{col} = ?")
                    values.append(val)
            # 주소가 새로 제공되고 기존에 없으면 업데이트
            if address and address.strip():
                fields.append("address = ?")
                values.append(address.strip())
            if fields:
                fields.append("updated_at = datetime('now','localtime')")
                values.append(store_id)
                conn.execute(
                    f"UPDATE stores SET {', '.join(fields)} WHERE id = ?",
                    values
                )
                conn.commit()
            return {"success": True, "store_id": store_id, "action": "updated"}
        else:
            cur = conn.execute("""
                INSERT INTO stores (name, category, address, phone, description,
                                    area, source, source_url, rating, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (name.strip(), category, address, phone, description,
                  area, source, source_url, rating, notes))
            conn.commit()
            return {"success": True, "store_id": cur.lastrowid, "action": "created"}
    except Exception as e:
        logger.error(f"[LocalInfo] 가게 저장 실패: {e}")
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


# =============================================================================
# 커뮤니티 언급 저장 (빈도 기록)
# =============================================================================

def save_mention(store_id: int, title: str = None, content: str = None,
                 source: str = None, source_url: str = None,
                 post_date: str = None) -> Dict[str, Any]:
    """
    가게에 대한 커뮤니티 언급 기록.
    같은 source_url 또는 같은 제목이면 중복 저장하지 않음.
    """
    conn = get_db()
    try:
        store = conn.execute("SELECT id, name FROM stores WHERE id = ?", (store_id,)).fetchone()
        if not store:
            return {"success": False, "error": f"가게 ID {store_id}를 찾을 수 없습니다."}

        # URL 기반 중복 체크
        existing = None
        if source_url and source_url.strip():
            existing = conn.execute(
                "SELECT id FROM mentions WHERE store_id = ? AND source_url = ?",
                (store_id, source_url.strip())
            ).fetchone()

        # 제목 기반 중복 체크
        if not existing and title and title.strip():
            existing = conn.execute(
                "SELECT id FROM mentions WHERE store_id = ? AND title = ?",
                (store_id, title.strip())
            ).fetchone()

        if existing:
            return {
                "success": True,
                "mention_id": existing['id'],
                "store_name": store['name'],
                "action": "already_exists"
            }
        else:
            cur = conn.execute("""
                INSERT INTO mentions (store_id, title, content, source, source_url, post_date)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (store_id, title, content, source, source_url, post_date))
            conn.commit()
            return {
                "success": True,
                "mention_id": cur.lastrowid,
                "store_name": store['name'],
                "action": "created"
            }
    except Exception as e:
        logger.error(f"[LocalInfo] 언급 저장 실패: {e}")
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


# =============================================================================
# 조회/검색
# =============================================================================

def query_stores(query: str = None, category: str = None,
                 area: str = None, limit: int = 20) -> Dict[str, Any]:
    """가게 검색 (FTS5 또는 필터). 언급 횟수 포함."""
    conn = get_db()
    try:
        if query and query.strip():
            safe_query = re.sub(r'[^\w\s가-힣]', ' ', query)
            tokens = [t for t in safe_query.split() if len(t) >= 1]
            if not tokens:
                return {"success": True, "count": 0, "stores": []}
            fts_query = ' OR '.join(tokens)

            try:
                sql = """
                    SELECT s.*, bm25(stores_fts) as relevance,
                           (SELECT COUNT(*) FROM mentions m WHERE m.store_id = s.id) as mention_count
                    FROM stores_fts fts
                    JOIN stores s ON s.id = fts.rowid
                    WHERE stores_fts MATCH ?
                """
                params: list = [fts_query]
                if category:
                    sql += " AND s.category = ?"
                    params.append(category)
                if area:
                    sql += " AND s.area = ?"
                    params.append(area)
                sql += " ORDER BY relevance LIMIT ?"
                params.append(limit)
                rows = conn.execute(sql, params).fetchall()
            except Exception:
                sql = """
                    SELECT s.*,
                           (SELECT COUNT(*) FROM mentions m WHERE m.store_id = s.id) as mention_count
                    FROM stores s
                    WHERE (s.name LIKE ? OR s.description LIKE ? OR s.category LIKE ?)
                """
                like_pat = f"%{query}%"
                params = [like_pat, like_pat, like_pat]
                if category:
                    sql += " AND s.category = ?"
                    params.append(category)
                if area:
                    sql += " AND s.area = ?"
                    params.append(area)
                sql += " ORDER BY s.updated_at DESC LIMIT ?"
                params.append(limit)
                rows = conn.execute(sql, params).fetchall()
        else:
            sql = """
                SELECT s.*,
                       (SELECT COUNT(*) FROM mentions m WHERE m.store_id = s.id) as mention_count
                FROM stores s WHERE 1=1
            """
            params = []
            if category:
                sql += " AND s.category = ?"
                params.append(category)
            if area:
                sql += " AND s.area = ?"
                params.append(area)
            sql += " ORDER BY s.updated_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()

        stores = []
        for row in rows:
            store = dict(row)
            store.pop('relevance', None)
            stores.append(store)

        return {"success": True, "count": len(stores), "stores": stores}
    except Exception as e:
        logger.error(f"[LocalInfo] 검색 실패: {e}")
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def get_store_with_mentions(store_id: int) -> Dict[str, Any]:
    """가게 상세 정보 + 관련 언급 목록"""
    conn = get_db()
    try:
        store = conn.execute("SELECT * FROM stores WHERE id = ?", (store_id,)).fetchone()
        if not store:
            return {"success": False, "error": f"가게 ID {store_id}를 찾을 수 없습니다."}

        mentions = conn.execute(
            "SELECT * FROM mentions WHERE store_id = ? ORDER BY collected_at DESC",
            (store_id,)
        ).fetchall()

        return {
            "success": True,
            "store": dict(store),
            "mention_count": len(mentions),
            "mentions": [dict(m) for m in mentions]
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def get_stats() -> Dict[str, Any]:
    """DB 통계"""
    conn = get_db()
    try:
        total_stores = conn.execute("SELECT COUNT(*) as cnt FROM stores").fetchone()['cnt']
        total_mentions = conn.execute("SELECT COUNT(*) as cnt FROM mentions").fetchone()['cnt']

        categories = conn.execute("""
            SELECT category, COUNT(*) as cnt FROM stores
            WHERE category IS NOT NULL
            GROUP BY category ORDER BY cnt DESC
        """).fetchall()

        areas = conn.execute("""
            SELECT area, COUNT(*) as cnt FROM stores
            GROUP BY area ORDER BY cnt DESC
        """).fetchall()

        # 가장 많이 언급된 가게 TOP 5
        top_mentioned = conn.execute("""
            SELECT s.name, s.category, COUNT(m.id) as cnt
            FROM stores s JOIN mentions m ON m.store_id = s.id
            GROUP BY s.id ORDER BY cnt DESC LIMIT 5
        """).fetchall()

        return {
            "success": True,
            "total_stores": total_stores,
            "total_mentions": total_mentions,
            "categories": {row['category']: row['cnt'] for row in categories},
            "areas": {row['area']: row['cnt'] for row in areas},
            "top_mentioned": [{"name": r['name'], "category": r['category'], "mentions": r['cnt']} for r in top_mentioned]
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def get_recent(limit: int = 10) -> Dict[str, Any]:
    """최근 추가/수정된 가게"""
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT s.*,
                   (SELECT COUNT(*) FROM mentions m WHERE m.store_id = s.id) as mention_count
            FROM stores s
            ORDER BY s.updated_at DESC LIMIT ?
        """, (limit,)).fetchall()

        return {
            "success": True,
            "count": len(rows),
            "stores": [dict(r) for r in rows]
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def delete_store(store_id: int) -> Dict[str, Any]:
    """가게 삭제 (관련 언급도 CASCADE 삭제)"""
    conn = get_db()
    try:
        store = conn.execute("SELECT name FROM stores WHERE id = ?", (store_id,)).fetchone()
        if not store:
            return {"success": False, "error": f"가게 ID {store_id}를 찾을 수 없습니다."}

        conn.execute("DELETE FROM stores WHERE id = ?", (store_id,))
        conn.commit()
        return {"success": True, "deleted": store['name']}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()
