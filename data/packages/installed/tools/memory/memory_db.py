"""
memory_db.py - 에이전트별 메모리 SQLite 저장소
에이전트가 스스로 저장하고 필요할 때 검색해서 읽는 심층 메모리

검색 방식: LIKE 키워드 + 시맨틱(임베딩, vec0) 하이브리드
임베딩 모델: backend/ibl_usage_db.py의 fine-tuned 모델 공유 사용
"""
import os
import sys
import struct
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Tuple

EMBEDDING_DIM = 768
SEMANTIC_THRESHOLD = 0.4   # 시맨틱 유사도 컷오프 (이하 무시)
# 검색 전략: 해마(ibl_usage_db)와 동일하게 시맨틱 100% 우선, LIKE는 폴백
# - 시맨틱 결과가 임계값을 통과하면 그것만 사용 (정규화된 점수 0~1)
# - 시맨틱이 비었거나 모델 미준비 시 LIKE 폴백 (raw 매칭 순서)

# 기억 위생(정리 패스) 정책
# - 유효 카테고리: 이외 값은 저장 시 "기타"로 정규화 (드리프트 방지)
# - 보호 카테고리: 지속적 사실은 LRU 가지치기에서 제외. 오직 작업기록/기타만 가지치기 대상
VALID_CATEGORIES = {"사용자선호", "사용자정보", "작업기록", "의사결정", "중요날짜", "기타"}
PROTECTED_CATEGORIES = {"사용자선호", "사용자정보", "의사결정", "중요날짜"}
DEFAULT_MEMORY_CAP = 300   # 에이전트당 기억 상한 (초과 시 used_at LRU로 가지치기)
DUP_SIM_THRESHOLD = 0.85   # 근접중복 클러스터 코사인 임계


def normalize_category(category: str) -> str:
    """카테고리를 유효 집합으로 정규화. 빈 값/미지 값 → '기타'."""
    cat = (category or "").strip()
    return cat if cat in VALID_CATEGORIES else "기타"


# =============================================================================
# 모델/벡터 공유 (backend의 IBLUsageDB 재사용)
# =============================================================================

def _backend_path() -> str:
    """backend 디렉터리 절대경로"""
    # this file: data/packages/installed/tools/memory/memory_db.py
    # backend:   ../../../../../../backend
    return str(Path(__file__).resolve().parents[5] / "backend")


def _get_model():
    """공유 fine-tuned 임베딩 모델 반환 (없으면 None)"""
    try:
        bp = _backend_path()
        if bp not in sys.path:
            sys.path.insert(0, bp)
        from ibl_usage_db import IBLUsageDB
        if IBLUsageDB._model is None:
            IBLUsageDB._load_model_sync()
        return IBLUsageDB._model
    except Exception as e:
        print(f"[memory_db] 모델 로드 실패 (LIKE 검색만 사용): {e}")
        return None


def _embed(text: str) -> Optional[bytes]:
    """단일 텍스트 → 임베딩 blob (float[768])"""
    model = _get_model()
    if model is None:
        return None
    try:
        vec = model.encode(text, normalize_embeddings=True, convert_to_numpy=True)
        return struct.pack(f"{EMBEDDING_DIM}f", *vec.tolist())
    except Exception as e:
        print(f"[memory_db] 임베딩 생성 실패: {e}")
        return None


def _embed_batch(texts: List[str]) -> Optional[List[bytes]]:
    """배치 임베딩"""
    model = _get_model()
    if model is None:
        return None
    try:
        vecs = model.encode(texts, normalize_embeddings=True,
                            convert_to_numpy=True, batch_size=32)
        return [struct.pack(f"{EMBEDDING_DIM}f", *v.tolist()) for v in vecs]
    except Exception as e:
        print(f"[memory_db] 배치 임베딩 실패: {e}")
        return None


def _prepare_text(content: str, keywords: str = "", category: str = "") -> str:
    """검색용 텍스트 구성 (category + keywords + content)"""
    parts = []
    if category:
        parts.append(f"[{category}]")
    if keywords:
        parts.append(keywords)
    parts.append(content)
    return " ".join(parts)


def _get_vec_conn(db_path: str) -> Optional[sqlite3.Connection]:
    """sqlite-vec 확장 로드된 연결 반환 (불가 시 None)"""
    try:
        import sqlite_vec
        conn = sqlite3.connect(db_path)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        return None


def _ensure_vec_table(conn):
    """vec0 가상 테이블 생성"""
    conn.execute(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS memories_vec USING vec0(
            embedding float[{EMBEDDING_DIM}]
        )
    """)
    conn.commit()


def _index_one(db_path: str, mem_id: int, content: str,
               keywords: str = "", category: str = ""):
    """단일 메모리 항목 임베딩 인덱싱.

    sqlite-vec의 vec0 가상 테이블은 INSERT OR REPLACE를 제대로 지원하지 않아
    같은 rowid로 다시 INSERT 시 UNIQUE constraint failed가 발생한다.
    명시적 DELETE 후 INSERT 패턴을 사용해 업데이트 의미를 보장한다."""
    conn = _get_vec_conn(db_path)
    if conn is None:
        return
    try:
        _ensure_vec_table(conn)
        text = _prepare_text(content, keywords, category)
        emb = _embed(text)
        if emb:
            conn.execute("DELETE FROM memories_vec WHERE rowid = ?", (mem_id,))
            conn.execute(
                "INSERT INTO memories_vec(rowid, embedding) VALUES (?, ?)",
                (mem_id, emb)
            )
            conn.commit()
    except Exception as e:
        print(f"[memory_db] 인덱싱 실패 (id={mem_id}): {e}")
    finally:
        conn.close()


def _delete_vec(db_path: str, mem_id: int):
    """vec 인덱스에서 항목 삭제"""
    conn = _get_vec_conn(db_path)
    if conn is None:
        return
    try:
        conn.execute("DELETE FROM memories_vec WHERE rowid = ?", (mem_id,))
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def _search_semantic(db_path: str, query: str, top_k: int = 10) -> List[Tuple[int, float]]:
    """시맨틱 검색 — (memory_id, similarity) 리스트.
    similarity는 코사인 유사도 (1=일치, 0=무관).
    normalize_embeddings=True를 가정하므로 vec0의 distance(L2제곱)는
    L2^2 = 2 - 2*cos 이며, cos = 1 - distance/2 로 환산."""
    model = _get_model()
    if model is None:
        return []
    conn = _get_vec_conn(db_path)
    if conn is None:
        return []
    try:
        q_vec = model.encode(query, normalize_embeddings=True, convert_to_numpy=True)
        q_blob = struct.pack(f"{EMBEDDING_DIM}f", *q_vec.tolist())
        rows = conn.execute(
            "SELECT rowid, distance FROM memories_vec "
            "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
            (q_blob, top_k)
        ).fetchall()
        return [(int(r["rowid"]), 1.0 - float(r["distance"]) / 2.0) for r in rows]
    except Exception as e:
        return []
    finally:
        conn.close()


# =============================================================================
# DB 경로/연결
# =============================================================================

def _get_db_path(project_path: str, agent_id: str) -> str:
    """에이전트별 메모리 DB 경로

    프로젝트 에이전트: projects/{project_id}/memory_{agent_name}.db
    시스템 AI: data/system_ai_state/memory_system_ai.db
    """
    project_dir = Path(project_path).resolve()

    # 시스템 AI인지 확인
    if str(project_dir).endswith("data") or project_dir == Path(".").resolve():
        from runtime_utils import get_base_path
        db_dir = get_base_path() / "data" / "system_ai_state"
        db_dir.mkdir(parents=True, exist_ok=True)
        return str(db_dir / "memory_system_ai.db")
    else:
        agent_name = agent_id.replace("agent_", "") if agent_id and agent_id.startswith("agent_") else agent_id
        return str(project_dir / f"memory_{agent_name}.db")


def _ensure_schema(db_path: str):
    """memories 테이블 보장 — get_db 를 거치지 않는 읽기 경로(search 등)용.

    sqlite 는 connect 시 빈 파일을 생성하므로, 한 번도 save 한 적 없는 신규 프로젝트의
    첫 search/distill 이 '_search_like → SELECT FROM memories' 에서
    'no such table: memories' 로 죽던 버그를 막는다.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT DEFAULT '',
                keywords TEXT DEFAULT '',
                content TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                used_at DATETIME DEFAULT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_mem_keywords ON memories(keywords);
            CREATE INDEX IF NOT EXISTS idx_mem_category ON memories(category);
        ''')
        conn.commit()
    finally:
        conn.close()


def get_db(project_path: str, agent_id: str):
    """DB 연결 및 테이블 초기화"""
    db_path = _get_db_path(project_path, agent_id)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    conn.executescript('''
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT DEFAULT '',
            keywords TEXT DEFAULT '',
            content TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            used_at DATETIME DEFAULT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_mem_keywords ON memories(keywords);
        CREATE INDEX IF NOT EXISTS idx_mem_category ON memories(category);
    ''')

    # 기존 DB에 used_at 컬럼이 없으면 추가
    try:
        conn.execute("SELECT used_at FROM memories LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE memories ADD COLUMN used_at DATETIME DEFAULT NULL")

    return conn


# =============================================================================
# CRUD
# =============================================================================

def save(project_path: str, agent_id: str,
         content: str, keywords: str = "", category: str = "") -> int:
    """메모리 저장 (임베딩 자동 인덱싱)"""
    category = normalize_category(category)
    db_path = _get_db_path(project_path, agent_id)
    conn = get_db(project_path, agent_id)
    try:
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO memories (category, keywords, content, created_at) VALUES (?, ?, ?, ?)",
            (category, keywords, content, now)
        )
        conn.commit()
        mem_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    finally:
        conn.close()

    # 임베딩 인덱싱 (실패해도 저장은 성공으로 처리)
    _index_one(db_path, mem_id, content, keywords, category)
    return mem_id


def _search_like(db_path: str, query: str, category: str = None,
                 limit: int = 20) -> List[Dict]:
    """기존 LIKE 키워드 검색"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        words = query.strip().split()
        if not words:
            return []
        if len(words) > 20:
            words = words[:20]

        conditions, params = [], []
        for word in words:
            w = f"%{word}%"
            conditions.append("(keywords LIKE ? OR content LIKE ?)")
            params.extend([w, w])
        where = " OR ".join(conditions)
        if category:
            where = f"({where}) AND category = ?"
            params.append(category)

        first = f"%{words[0]}%"
        sql = f"""
            SELECT id, category, keywords,
                   SUBSTR(content, 1, 100) as preview,
                   created_at, used_at
            FROM memories
            WHERE {where}
            ORDER BY
                CASE WHEN keywords LIKE ? THEN 1 ELSE 2 END,
                created_at DESC
            LIMIT ?
        """
        params.extend([first, limit])
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def search(project_path: str, agent_id: str,
           query: str, category: str = None, limit: int = 10,
           semantic_only: bool = False, min_score: float = 0.0) -> List[Dict]:
    """시맨틱 우선 + LIKE 폴백 검색 (해마와 동일 패턴).

    1) 시맨틱(fine-tuned 임베딩) 검색을 먼저 시도. SEMANTIC_THRESHOLD 통과 항목이 있으면 그것만 반환.
    2) 시맨틱이 비었거나(모델 미준비/임계값 미달) 결과 0이면 LIKE 키워드 폴백.

    ★자동 회상(프롬프트 주입)용 점수 바닥:
      - semantic_only=True → LIKE 폴백을 끈다. LIKE 는 *점수 없이 키워드만 겹쳐도* 반환하므로
        자동 주입에선 관련성 게이트가 없는 노이즈원(예: 'kind:operator' 질의에 무의식-분류기
        기억이 키워드만 겹쳐 끌려옴). 시맨틱 바닥 미달이면 빈 결과 = 주입 안 함.
      - min_score → 시맨틱 컷오프를 SEMANTIC_THRESHOLD 위로 올린다(주입은 정밀도 우선).
    명시 검색(memory 액션)·증류 dedup 은 기본값(폴백 유지)이라 무영향.
    """
    db_path = _get_db_path(project_path, agent_id)
    _ensure_schema(db_path)  # 신규 프로젝트(미save) 빈 DB에서 LIKE 폴백이 죽지 않도록 테이블 보장

    eff_threshold = max(SEMANTIC_THRESHOLD, min_score)

    # 1. 시맨틱 우선
    sem_pairs = _search_semantic(db_path, query, top_k=limit * 2)
    sem_pairs = [(mid, s) for mid, s in sem_pairs if s >= eff_threshold]

    if sem_pairs:
        sorted_ids = [mid for mid, _ in sem_pairs[:limit]]
    elif semantic_only:
        # 자동 회상: 시맨틱 바닥 미달이면 LIKE 폴백 없이 빈 결과(노이즈 주입 방지).
        return []
    else:
        # 2. 시맨틱 미준비/매칭 0 → LIKE 폴백
        like_results = _search_like(db_path, query, category, limit=limit)
        if not like_results:
            return []
        sorted_ids = [r["id"] for r in like_results]

    if not sorted_ids:
        return []

    # 카테고리 필터 (시맨틱 경로에서도 적용)
    if category and sem_pairs:
        conn = sqlite3.connect(db_path)
        try:
            ph = ",".join("?" * len(sorted_ids))
            allowed = {r[0] for r in conn.execute(
                f"SELECT id FROM memories WHERE id IN ({ph}) AND category = ?",
                sorted_ids + [category]
            )}
            sorted_ids = [mid for mid in sorted_ids if mid in allowed]
        finally:
            conn.close()
        if not sorted_ids:
            return []

    # 메타 로드
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        ph = ",".join("?" * len(sorted_ids))
        rows = conn.execute(
            f"SELECT id, category, keywords, "
            f"SUBSTR(content,1,100) as preview, created_at, used_at "
            f"FROM memories WHERE id IN ({ph})",
            sorted_ids
        ).fetchall()
    finally:
        conn.close()

    by_id = {r["id"]: dict(r) for r in rows}
    return [by_id[mid] for mid in sorted_ids if mid in by_id]


def read(project_path: str, agent_id: str, memory_id: int) -> Optional[Dict]:
    """메모리 전문 조회 + used_at 갱신"""
    conn = get_db(project_path, agent_id)
    try:
        row = conn.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        if not row:
            return None

        now = datetime.now().isoformat()
        conn.execute("UPDATE memories SET used_at = ? WHERE id = ?", (now, memory_id))
        conn.commit()

        result = dict(row)
        result['used_at'] = now
        return result
    finally:
        conn.close()


def update(project_path: str, agent_id: str, memory_id: int,
           content: str = None, keywords: str = None, category: str = None) -> bool:
    """기존 항목 업데이트 (변경 필드만; used_at 자동 갱신; 임베딩 재생성)"""
    db_path = _get_db_path(project_path, agent_id)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        sets, params = [], []
        if content is not None:
            sets.append("content = ?"); params.append(content)
        if keywords is not None:
            sets.append("keywords = ?"); params.append(keywords)
        if category is not None:
            sets.append("category = ?"); params.append(normalize_category(category))

        if not sets:
            now = datetime.now().isoformat()
            conn.execute("UPDATE memories SET used_at = ? WHERE id = ?", (now, memory_id))
            conn.commit()
            return True

        now = datetime.now().isoformat()
        sets.append("used_at = ?"); params.append(now)
        params.append(memory_id)

        sql = f"UPDATE memories SET {', '.join(sets)} WHERE id = ?"
        cur = conn.execute(sql, params)
        conn.commit()
        if cur.rowcount == 0:
            return False

        # 의미가 바뀐 필드(content/keywords/category)가 있으면 재인덱싱
        row = conn.execute(
            "SELECT content, keywords, category FROM memories WHERE id = ?",
            (memory_id,)
        ).fetchone()
    finally:
        conn.close()

    if row:
        _index_one(db_path, memory_id, row["content"], row["keywords"], row["category"])
    return True


def delete(project_path: str, agent_id: str, memory_id: int) -> bool:
    """메모리 + vec 인덱스 동시 삭제"""
    db_path = _get_db_path(project_path, agent_id)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        conn.commit()
        ok = cur.rowcount > 0
    finally:
        conn.close()

    if ok:
        _delete_vec(db_path, memory_id)
    return ok


def count(project_path: str, agent_id: str) -> int:
    """메모리 총 개수"""
    conn = get_db(project_path, agent_id)
    try:
        return conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    finally:
        conn.close()


# =============================================================================
# 마이그레이션/유지보수
# =============================================================================

def rebuild_index(project_path: str, agent_id: str) -> Dict:
    """vec 인덱스 전체 재구축 (모든 memories 재인덱싱)"""
    db_path = _get_db_path(project_path, agent_id)

    # 메모리 항목 전수 조회
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, content, keywords, category FROM memories ORDER BY id"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"success": True, "indexed": 0, "message": "메모리 없음"}

    # vec 테이블 초기화
    vec_conn = _get_vec_conn(db_path)
    if vec_conn is None:
        return {"success": False, "error": "sqlite-vec 사용 불가"}
    try:
        _ensure_vec_table(vec_conn)
        vec_conn.execute("DELETE FROM memories_vec")
        vec_conn.commit()
    finally:
        vec_conn.close()

    # 배치 임베딩
    texts = [_prepare_text(r["content"], r["keywords"], r["category"]) for r in rows]
    embs = _embed_batch(texts)
    if not embs:
        return {"success": False, "error": "임베딩 생성 실패 (모델 없음)"}

    # 일괄 INSERT
    vec_conn = _get_vec_conn(db_path)
    if vec_conn is None:
        return {"success": False, "error": "vec 연결 실패"}
    try:
        for row, emb in zip(rows, embs):
            vec_conn.execute(
                "INSERT INTO memories_vec(rowid, embedding) VALUES (?, ?)",
                (row["id"], emb)
            )
        vec_conn.commit()
    finally:
        vec_conn.close()

    return {"success": True, "indexed": len(rows), "db_path": db_path}


# =============================================================================
# 정리(consolidation) 프리미티브 — db_path 직접 조작 (오케스트레이터용)
# 정리 패스는 쓰기 시점 중복제거의 배치/오프라인 짝이다. 여기 함수들은
# 기계적(무LLM) 부분만 담당하고, 의미 병합 판단은 backend 오케스트레이터가 한다.
# =============================================================================

def _ensure_meta(conn):
    """_meta(key,value) 테이블 보장 — 마지막 정리 시각 등 추적용."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _meta (key TEXT PRIMARY KEY, value TEXT)"
    )


def get_meta(db_path: str, key: str) -> Optional[str]:
    conn = sqlite3.connect(db_path)
    try:
        _ensure_meta(conn)
        row = conn.execute("SELECT value FROM _meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def set_meta(db_path: str, key: str, value: str):
    conn = sqlite3.connect(db_path)
    try:
        _ensure_meta(conn)
        conn.execute(
            "INSERT INTO _meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value)
        )
        conn.commit()
    finally:
        conn.close()


def list_all(db_path: str) -> List[Dict]:
    """전체 메모리 전문 조회 (정리 패스용)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, category, keywords, content, created_at, used_at "
            "FROM memories ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def count_at(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def prune_lru(db_path: str, cap: int = DEFAULT_MEMORY_CAP,
              protected: set = PROTECTED_CATEGORIES) -> int:
    """상한 초과 시 used_at LRU로 가지치기 (보호 카테고리 제외).

    used_at이 NULL이면 created_at을 사용. 보호 카테고리(지속적 사실)는
    절대 삭제하지 않으므로, 보호 항목만으로 cap을 넘으면 그대로 둔다.
    반환: 삭제된 개수."""
    total = count_at(db_path)
    if total <= cap:
        return 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # 가지치기 후보: 비보호 카테고리, 오래 안 쓰인 순(used_at/created_at 오름차순)
        ph = ",".join("?" * len(protected)) if protected else "''"
        rows = conn.execute(
            f"SELECT id FROM memories "
            f"WHERE category NOT IN ({ph}) "
            f"ORDER BY COALESCE(used_at, created_at) ASC",
            tuple(protected) if protected else ()
        ).fetchall()
    finally:
        conn.close()

    need = total - cap
    victims = [r["id"] for r in rows[:need]]
    if not victims:
        return 0

    conn = sqlite3.connect(db_path)
    try:
        ph = ",".join("?" * len(victims))
        conn.execute(f"DELETE FROM memories WHERE id IN ({ph})", victims)
        conn.commit()
    finally:
        conn.close()
    for vid in victims:
        _delete_vec(db_path, vid)
    return len(victims)


def _load_vectors(db_path: str) -> List[Tuple[int, list]]:
    """memories_vec에서 (id, 정규화 벡터 리스트) 전수 로드."""
    conn = _get_vec_conn(db_path)
    if conn is None:
        return []
    try:
        rows = conn.execute("SELECT rowid, embedding FROM memories_vec").fetchall()
        out = []
        for r in rows:
            blob = r["embedding"]
            vec = list(struct.unpack(f"{EMBEDDING_DIM}f", blob))
            out.append((int(r["rowid"]), vec))
        return out
    except Exception:
        return []
    finally:
        conn.close()


def find_duplicate_clusters(db_path: str,
                            threshold: float = DUP_SIM_THRESHOLD) -> List[List[int]]:
    """근접중복 클러스터 탐지 — 코사인 유사도 >= threshold 쌍을 union-find로 묶음.

    임베딩은 normalize_embeddings=True로 저장되므로 내적 = 코사인.
    반환: 크기 2 이상 클러스터의 id 리스트들 (각 클러스터 내부는 id 오름차순)."""
    vectors = _load_vectors(db_path)
    n = len(vectors)
    if n < 2:
        return []

    try:
        import numpy as np
        ids = [vid for vid, _ in vectors]
        mat = np.array([v for _, v in vectors], dtype=np.float32)
        sims = mat @ mat.T  # 정규화 벡터라 내적=코사인
    except Exception:
        # numpy 없으면 순수 파이썬 폴백
        ids = [vid for vid, _ in vectors]
        vecs = [v for _, v in vectors]
        sims = [[sum(a * b for a, b in zip(vecs[i], vecs[j])) for j in range(n)]
                for i in range(n)]

    # union-find
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        for j in range(i + 1, n):
            s = sims[i][j] if isinstance(sims, list) else float(sims[i][j])
            if s >= threshold:
                union(i, j)

    groups: Dict[int, List[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(ids[i])
    return [sorted(g) for g in groups.values() if len(g) > 1]


def get_by_id(db_path: str, memory_id: int) -> Optional[Dict]:
    """id로 메모리 전문 조회 (used_at 갱신 없음 — 정리 패스용)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT id, category, keywords, content, created_at, used_at "
            "FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def apply_merge(db_path: str, keep_id: int, content: str,
                keywords: str, category: str, drop_ids: List[int]) -> bool:
    """클러스터 병합 적용 — keep_id를 정규 병합본으로 덮어쓰고 나머지 삭제.

    content/keywords/category를 keep_id에 갱신하고 재인덱싱, drop_ids는
    행+vec 동시 삭제. 카테고리는 정규화된다."""
    category = normalize_category(category)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE memories SET content=?, keywords=?, category=? WHERE id=?",
            (content, keywords, category, keep_id)
        )
        if drop_ids:
            ph = ",".join("?" * len(drop_ids))
            conn.execute(f"DELETE FROM memories WHERE id IN ({ph})", drop_ids)
        conn.commit()
    finally:
        conn.close()

    _index_one(db_path, keep_id, content, keywords, category)
    for did in drop_ids:
        _delete_vec(db_path, did)
    return True


def normalize_all_categories(db_path: str) -> int:
    """비어있지 않은 무효 카테고리만 '기타'로 정규화. 반환: 변경된 행 수.

    빈 카테고리는 건드리지 않는다 — 빈칸이 실제로는 사용자 사실인 경우가 많아
    무조건 '기타'로 강등하면 보호를 잃기 때문. 빈칸 분류는 LLM 병합 단계에 맡긴다."""
    rows = list_all(db_path)
    changed = 0
    conn = sqlite3.connect(db_path)
    try:
        for r in rows:
            cur = (r.get("category") or "").strip()
            if not cur:
                continue  # 빈칸은 보존
            norm = normalize_category(cur)
            if norm != cur:
                conn.execute("UPDATE memories SET category=? WHERE id=?",
                             (norm, r["id"]))
                changed += 1
        if changed:
            conn.commit()
    finally:
        conn.close()
    return changed
