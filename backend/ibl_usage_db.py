"""
ibl_usage_db.py - IBL 용례 사전 DB
IndieBiz OS Core

합성 데이터 + 실행 로그를 저장하고 하이브리드 검색(Semantic + BM25)을 제공.
BlogHybridSearch 패턴을 재활용.

Dependencies:
  Required: sqlite3 (stdlib)
  Optional: sentence-transformers, sqlite-vec (시맨틱 검색용)
"""

import os
import re
import struct
import hashlib
import logging
import sqlite3
import json
import time
import threading
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime

logger = logging.getLogger(__name__)

# DB 경로
_BASE_DIR = Path(__file__).parent.parent / "data"
DB_PATH = str(_BASE_DIR / "ibl_usage.db")


# =============================================================================
# 데이터 클래스
# =============================================================================

@dataclass
class UsageExample:
    """용례 검색 결과"""
    id: int
    intent: str
    ibl_code: str
    nodes: str
    category: str
    difficulty: int
    score: float
    source: str
    success_rate: float


# =============================================================================
# IBLUsageDB 클래스
# =============================================================================

class IBLUsageDB:
    """IBL 용례 사전 DB (싱글톤)

    BlogHybridSearch와 동일한 패턴:
    - jhgan/ko-sroberta-multitask (768차원) 임베딩
    - sqlite-vec 벡터 검색 + FTS5 BM25 키워드 검색
    - DEFAULT_ALPHA = 1.0 (100% Semantic, BM25 폴백)
    """

    EMBEDDING_DIM = 768
    # 해마 (hippocampus): IBL 도메인 fine-tuned 모델 (Top-5 80.9%, 범용 대비 +28.3%p)
    EMBEDDING_MODEL = str(Path(__file__).parent.parent / 'data' / 'models' / 'ibl_embedding')
    DEFAULT_ALPHA = 1.0
    BATCH_SIZE = 32
    INTENT_REPEAT = 3  # intent 가중치 (제목 반복과 동일)

    _instance = None
    _model = None
    _model_load_attempted = False
    _model_loading = False  # 백그라운드 로딩 진행 중 플래그
    _sqlite_vec_available = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._search_cache = {}
            cls._instance._cache_time = {}
            cls._instance._cache_ttl = 300  # 5분
            cls._instance._init_db()
        return cls._instance

    # =========================================================================
    # DB 초기화
    # =========================================================================

    def _init_db(self):
        """DB 테이블 생성"""
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA journal_mode=WAL")

        # 용례 사전 테이블
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ibl_examples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                intent TEXT NOT NULL,
                ibl_code TEXT NOT NULL,
                nodes TEXT DEFAULT '',
                category TEXT DEFAULT 'single',
                difficulty INTEGER DEFAULT 1,
                source TEXT DEFAULT 'synthetic',
                success_count INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                tags TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # FTS5 키워드 인덱스
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS ibl_examples_fts USING fts5(
                intent, ibl_code,
                content='ibl_examples',
                content_rowid='id',
                tokenize='unicode61'
            )
        """)

        # FTS5 동기화 트리거
        conn.executescript("""
            CREATE TRIGGER IF NOT EXISTS ibl_examples_ai AFTER INSERT ON ibl_examples BEGIN
                INSERT INTO ibl_examples_fts(rowid, intent, ibl_code)
                VALUES (new.id, new.intent, new.ibl_code);
            END;

            CREATE TRIGGER IF NOT EXISTS ibl_examples_ad AFTER DELETE ON ibl_examples BEGIN
                INSERT INTO ibl_examples_fts(ibl_examples_fts, rowid, intent, ibl_code)
                VALUES ('delete', old.id, old.intent, old.ibl_code);
            END;

            CREATE TRIGGER IF NOT EXISTS ibl_examples_au AFTER UPDATE ON ibl_examples BEGIN
                INSERT INTO ibl_examples_fts(ibl_examples_fts, rowid, intent, ibl_code)
                VALUES ('delete', old.id, old.intent, old.ibl_code);
                INSERT INTO ibl_examples_fts(rowid, intent, ibl_code)
                VALUES (new.id, new.intent, new.ibl_code);
            END;
        """)

        # 실행 로그 테이블
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ibl_execution_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_input TEXT DEFAULT '',
                generated_ibl TEXT DEFAULT '',
                node TEXT DEFAULT '',
                action TEXT DEFAULT '',
                target TEXT DEFAULT '',
                params_json TEXT DEFAULT '{}',
                success INTEGER DEFAULT 1,
                error_message TEXT DEFAULT '',
                duration_ms INTEGER DEFAULT 0,
                agent_id TEXT DEFAULT '',
                project_id TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)

        # 인덱스
        conn.execute("CREATE INDEX IF NOT EXISTS idx_examples_category ON ibl_examples(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_examples_nodes ON ibl_examples(nodes)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_examples_source ON ibl_examples(source)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_created ON ibl_execution_logs(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_node_action ON ibl_execution_logs(node, action)")

        conn.commit()
        conn.close()
        logger.info(f"[IBL Usage DB] 초기화 완료: {DB_PATH}")

    # =========================================================================
    # DB 연결
    # =========================================================================

    @contextmanager
    def _get_connection(self):
        """일반 SQLite 연결"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _get_vec_connection(self) -> Optional[sqlite3.Connection]:
        """sqlite-vec 로드된 연결 반환, 불가능하면 None"""
        if not self._check_sqlite_vec():
            return None
        try:
            import sqlite_vec
            conn = sqlite3.connect(DB_PATH)
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
            conn.row_factory = sqlite3.Row
            return conn
        except Exception as e:
            logger.error(f"[IBL Usage DB] sqlite-vec 연결 실패: {e}")
            return None

    def _ensure_vec_table(self, conn):
        """vec0 가상 테이블 생성 (없으면)"""
        conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS ibl_examples_vec USING vec0(
                embedding float[{self.EMBEDDING_DIM}]
            )
        """)
        conn.commit()

    # =========================================================================
    # 모델/의존성 관리 (BlogHybridSearch와 동일 패턴)
    # =========================================================================

    @classmethod
    def _load_model(cls) -> bool:
        """sentence-transformers 모델이 이미 로드되었는지 확인 (블로킹하지 않음)"""
        if cls._model is not None:
            return True
        if not cls._model_load_attempted and not cls._model_loading:
            cls._start_background_model_load()
        return False

    @classmethod
    def _start_background_model_load(cls):
        """백그라운드 스레드에서 모델 로드 (서버 시작을 블로킹하지 않음)"""
        if cls._model_loading or cls._model_load_attempted:
            return
        cls._model_loading = True

        def _load():
            try:
                from sentence_transformers import SentenceTransformer
                print(f"[IBL Usage DB] 백그라운드 임베딩 모델 로딩 시작: {cls.EMBEDDING_MODEL}")
                cls._model = SentenceTransformer(cls.EMBEDDING_MODEL)
                print("[IBL Usage DB] 임베딩 모델 로딩 완료")
            except ImportError:
                logger.warning("[IBL Usage DB] sentence-transformers 미설치 → FTS5 검색만 사용")
            except Exception as e:
                logger.error(f"[IBL Usage DB] 모델 로드 실패: {e}")
            finally:
                cls._model_load_attempted = True
                cls._model_loading = False

        t = threading.Thread(target=_load, daemon=True, name="ibl-model-loader")
        t.start()

    @classmethod
    def _load_model_sync(cls) -> bool:
        """모델을 동기적으로 로드 (rebuild_index 등 명시적 요청용)"""
        if cls._model is not None:
            return True
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"[IBL Usage DB] 동기 모델 로딩: {cls.EMBEDDING_MODEL}")
            cls._model = SentenceTransformer(cls.EMBEDDING_MODEL)
            cls._model_load_attempted = True
            cls._model_loading = False
            logger.info("[IBL Usage DB] 동기 모델 로딩 완료")
            return True
        except ImportError:
            logger.warning("[IBL Usage DB] sentence-transformers 미설치")
            cls._model_load_attempted = True
            cls._model_loading = False
            return False
        except Exception as e:
            logger.error(f"[IBL Usage DB] 동기 모델 로드 실패: {e}")
            cls._model_load_attempted = True
            cls._model_loading = False
            return False

    @classmethod
    def _check_sqlite_vec(cls) -> bool:
        """sqlite-vec 확장 사용 가능 여부 확인"""
        if cls._sqlite_vec_available is not None:
            return cls._sqlite_vec_available
        try:
            import sqlite_vec
            cls._sqlite_vec_available = True
        except ImportError:
            cls._sqlite_vec_available = False
            logger.warning("[IBL Usage DB] sqlite-vec 미설치 → FTS5 검색만 사용")
        return cls._sqlite_vec_available

    @classmethod
    def is_semantic_available(cls) -> bool:
        """시맨틱 검색 가능 여부"""
        return cls._check_sqlite_vec() and cls._load_model()

    # =========================================================================
    # 임베딩 생성 (BlogHybridSearch 코드 재활용)
    # =========================================================================

    @staticmethod
    def _prepare_search_text(intent: str, ibl_code: str) -> str:
        """검색용 텍스트 준비 (intent 가중치 부여)"""
        clean_intent = intent.strip()
        title_part = ' '.join([clean_intent] * IBLUsageDB.INTENT_REPEAT)
        return f"{title_part} {ibl_code}"

    def _generate_embedding(self, text: str) -> Optional[bytes]:
        """단일 텍스트 임베딩 → packed bytes"""
        if not self.is_semantic_available():
            return None
        import numpy as np
        vector = self._model.encode(
            [text], convert_to_numpy=True, show_progress_bar=False
        )[0].astype('float32')
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        return struct.pack(f'{self.EMBEDDING_DIM}f', *vector)

    def _generate_embeddings_batch(self, texts: List[str]) -> List[bytes]:
        """배치 임베딩 생성 → packed bytes 리스트"""
        if not self.is_semantic_available():
            return []
        import numpy as np
        all_packed = []
        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i:i + self.BATCH_SIZE]
            batch_vectors = self._model.encode(
                batch, convert_to_numpy=True, show_progress_bar=False
            ).astype('float32')
            norms = np.linalg.norm(batch_vectors, axis=1, keepdims=True)
            norms[norms == 0] = 1
            batch_vectors = batch_vectors / norms
            for vec in batch_vectors:
                all_packed.append(struct.pack(f'{self.EMBEDDING_DIM}f', *vec))
            if i > 0 and i % (self.BATCH_SIZE * 10) == 0:
                logger.info(f"[IBL Usage DB] 임베딩 진행: {i}/{len(texts)}")
        return all_packed

    # =========================================================================
    # CRUD - 용례
    # =========================================================================

    def add_example(self, intent: str, ibl_code: str,
                    nodes: str = "", category: str = "single",
                    difficulty: int = 1, source: str = "synthetic",
                    tags: str = "") -> int:
        """용례 추가 (임베딩 자동 생성). Returns: example ID"""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO ibl_examples
                   (intent, ibl_code, nodes, category, difficulty, source, tags, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (intent, ibl_code, nodes, category, difficulty, source, tags, now, now)
            )
            example_id = cursor.lastrowid
            conn.commit()

        # 벡터 인덱스에 추가
        self._index_single(example_id, intent, ibl_code)
        return example_id

    def add_examples_batch(self, examples: List[Dict]) -> int:
        """배치 추가 (임베딩 배치 생성)

        Args:
            examples: [{intent, ibl_code, nodes?, category?, difficulty?, source?, tags?}]
        Returns: 추가된 수
        """
        if not examples:
            return 0

        now = datetime.now().isoformat()
        ids = []

        with self._get_connection() as conn:
            for ex in examples:
                cursor = conn.execute(
                    """INSERT INTO ibl_examples
                       (intent, ibl_code, nodes, category, difficulty, source, tags, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        ex['intent'], ex['ibl_code'],
                        ex.get('nodes', ''), ex.get('category', 'single'),
                        ex.get('difficulty', 1), ex.get('source', 'synthetic'),
                        ex.get('tags', ''), now, now
                    )
                )
                ids.append(cursor.lastrowid)
            conn.commit()

        # 배치 임베딩
        self._index_batch(ids, examples)
        logger.info(f"[IBL Usage DB] 배치 추가 완료: {len(ids)}개")
        return len(ids)

    def get_stats(self) -> Dict[str, Any]:
        """용례 사전 통계"""
        with self._get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM ibl_examples").fetchone()[0]
            by_category = conn.execute(
                "SELECT category, COUNT(*) as cnt FROM ibl_examples GROUP BY category"
            ).fetchall()
            by_source = conn.execute(
                "SELECT source, COUNT(*) as cnt FROM ibl_examples GROUP BY source"
            ).fetchall()
            log_count = conn.execute("SELECT COUNT(*) FROM ibl_execution_logs").fetchone()[0]
            log_success = conn.execute(
                "SELECT COUNT(*) FROM ibl_execution_logs WHERE success = 1"
            ).fetchone()[0]

        return {
            'total_examples': total,
            'by_category': {row['category']: row['cnt'] for row in by_category},
            'by_source': {row['source']: row['cnt'] for row in by_source},
            'execution_logs': log_count,
            'successful_logs': log_success,
            'semantic_available': self._model is not None
        }

    def update_success(self, example_id: int, success: bool):
        """성공/실패 카운트 업데이트"""
        field = "success_count" if success else "fail_count"
        with self._get_connection() as conn:
            conn.execute(
                f"UPDATE ibl_examples SET {field} = {field} + 1, updated_at = ? WHERE id = ?",
                (datetime.now().isoformat(), example_id)
            )
            conn.commit()

    # =========================================================================
    # CRUD - 실행 로그
    # =========================================================================

    def log_execution(self, user_input: str = "", generated_ibl: str = "",
                      node: str = "", action: str = "", target: str = "",
                      params: dict = None, success: bool = True,
                      error_message: str = "", duration_ms: int = 0,
                      agent_id: str = "", project_id: str = ""):
        """실행 로그 저장"""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """INSERT INTO ibl_execution_logs
                       (user_input, generated_ibl, node, action, target, params_json,
                        success, error_message, duration_ms, agent_id, project_id, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        user_input, generated_ibl, node, action, target,
                        json.dumps(params or {}, ensure_ascii=False),
                        1 if success else 0, error_message, duration_ms,
                        agent_id, project_id, datetime.now().isoformat()
                    )
                )
                conn.commit()
        except Exception as e:
            logger.error(f"[IBL Usage DB] 로그 저장 실패: {e}")

    def get_recent_logs(self, limit: int = 50, success_only: bool = False) -> List[Dict]:
        """최근 실행 로그 조회"""
        with self._get_connection() as conn:
            where = "WHERE success = 1" if success_only else ""
            rows = conn.execute(
                f"SELECT * FROM ibl_execution_logs {where} ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(row) for row in rows]

    # =========================================================================
    # 구 승격 시스템 제거됨 — 경험 증류(ibl_usage_rag.distill_experience)로 대체
    # promote_log_to_example, try_promote_session, auto_promote_logs,
    # _extract_session_ibl, _extract_inner_code 등은 삭제됨
    # =========================================================================

    # =========================================================================
    # 인덱싱
    # =========================================================================

    def _index_single(self, example_id: int, intent: str, ibl_code: str):
        """단일 용례 벡터 인덱싱"""
        conn = self._get_vec_connection()
        if conn is None:
            return
        try:
            self._ensure_vec_table(conn)
            text = self._prepare_search_text(intent, ibl_code)
            emb = self._generate_embedding(text)
            if emb:
                conn.execute(
                    "INSERT OR REPLACE INTO ibl_examples_vec(rowid, embedding) VALUES (?, ?)",
                    (example_id, emb)
                )
                conn.commit()
        except Exception as e:
            logger.error(f"[IBL Usage DB] 인덱싱 실패: {e}")
        finally:
            conn.close()

    def _index_batch(self, ids: List[int], examples: List[Dict]):
        """배치 벡터 인덱싱"""
        conn = self._get_vec_connection()
        if conn is None:
            return
        try:
            self._ensure_vec_table(conn)
            texts = [
                self._prepare_search_text(ex['intent'], ex['ibl_code'])
                for ex in examples
            ]
            embeddings = self._generate_embeddings_batch(texts)
            if not embeddings:
                return
            for eid, emb in zip(ids, embeddings):
                conn.execute(
                    "INSERT OR REPLACE INTO ibl_examples_vec(rowid, embedding) VALUES (?, ?)",
                    (eid, emb)
                )
            conn.commit()
            logger.info(f"[IBL Usage DB] 배치 인덱싱 완료: {len(embeddings)}개")
        except Exception as e:
            logger.error(f"[IBL Usage DB] 배치 인덱싱 실패: {e}")
        finally:
            conn.close()

    def rebuild_index(self) -> Dict[str, Any]:
        """벡터 인덱스 전체 재구축 (모델을 동기적으로 로드)"""
        IBLUsageDB._sqlite_vec_available = None
        IBLUsageDB._model_load_attempted = False
        IBLUsageDB._model_loading = False
        IBLUsageDB._model = None

        # rebuild_index는 명시적 요청이므로 동기적으로 모델 로드
        if not self._load_model_sync():
            return {'success': False, 'error': 'sqlite-vec 또는 sentence-transformers 미설치'}

        conn = self._get_vec_connection()
        if conn is None:
            return {'success': False, 'error': 'DB 연결 실패'}

        try:
            self._ensure_vec_table(conn)
            conn.execute("DELETE FROM ibl_examples_vec")
            conn.commit()

            rows = conn.execute(
                "SELECT id, intent, ibl_code FROM ibl_examples ORDER BY id"
            ).fetchall()
            conn.close()

            if not rows:
                return {'success': True, 'indexed_count': 0, 'message': '인덱싱할 용례 없음'}

            examples = [{'intent': r['intent'], 'ibl_code': r['ibl_code']} for r in rows]
            ids = [r['id'] for r in rows]

            start = time.time()
            self._index_batch(ids, examples)
            elapsed = time.time() - start

            self._search_cache.clear()
            return {
                'success': True,
                'indexed_count': len(rows),
                'elapsed_seconds': round(elapsed, 1),
                'message': f'{len(rows)}개 용례 인덱싱 완료 ({elapsed:.1f}초)'
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            try:
                conn.close()
            except:
                pass

    # =========================================================================
    # 검색
    # =========================================================================

    def search_semantic(self, query: str, top_k: int = 10) -> List[Tuple[int, float]]:
        """시맨틱 검색. (id, similarity_score) 리스트 반환"""
        emb = self._generate_embedding(query)
        if emb is None:
            return []
        conn = self._get_vec_connection()
        if conn is None:
            return []
        try:
            self._ensure_vec_table(conn)
            rows = conn.execute("""
                SELECT rowid, distance
                FROM ibl_examples_vec
                WHERE embedding MATCH ?
                  AND k = ?
                ORDER BY distance
            """, (emb, top_k)).fetchall()
            results = []
            for row in rows:
                dist = float(row['distance'])
                similarity = max(0.0, 1.0 - (dist * dist / 2.0))
                results.append((int(row['rowid']), similarity))
            return results
        except Exception as e:
            logger.error(f"[IBL Usage DB] 시맨틱 검색 실패: {e}")
            return []
        finally:
            conn.close()

    @staticmethod
    def _strip_korean_particles(text: str) -> str:
        """한국어 조사/어미를 제거하여 어근 추출 (FTS5 매칭률 향상)"""
        # 흔한 조사/어미 패턴 (긴 것부터 매칭)
        _PARTICLES = (
            "이라는", "에서는", "으로는", "에서의", "으로의",
            "하는", "되는", "하고", "해서", "해줘", "할까", "인지",
            "에서", "으로", "에게", "한테", "까지", "부터", "처럼", "만큼",
            "이나", "이랑", "하면", "에는", "와는",
            "는", "은", "이", "가", "를", "을", "의", "에", "도",
            "로", "와", "과", "나", "랑", "만", "야", "요",
        )
        words = text.split()
        result = []
        for word in words:
            stripped = word
            for p in _PARTICLES:
                if len(stripped) > len(p) + 1 and stripped.endswith(p):
                    stripped = stripped[:-len(p)]
                    break
            result.append(stripped)
        return ' '.join(result)

    def search_fts5(self, query: str, top_k: int = 10) -> List[Tuple[int, float]]:
        """FTS5 BM25 키워드 검색. (id, bm25_score) 리스트 반환"""
        with self._get_connection() as conn:
            try:
                from korean_utils import tokenize_korean
                # 한국어 정규화 토큰화: 조사 제거 + 복합어 분리
                tokens = [t for t in tokenize_korean(query) if len(t) >= 2]
                if not tokens:
                    return []
                fts_query = ' OR '.join(tokens)
                rows = conn.execute("""
                    SELECT e.id, bm25(ibl_examples_fts) as score
                    FROM ibl_examples_fts fts
                    JOIN ibl_examples e ON e.id = fts.rowid
                    WHERE ibl_examples_fts MATCH ?
                    ORDER BY score
                    LIMIT ?
                """, (fts_query, top_k)).fetchall()
                return [(int(row['id']), -float(row['score'])) for row in rows]
            except Exception as e:
                logger.error(f"[IBL Usage DB] FTS5 검색 실패: {e}")
                return []

    def _combine_scores(
        self,
        semantic_results: List[Tuple[int, float]],
        fts5_results: List[Tuple[int, float]],
        alpha: float
    ) -> List[Tuple[int, float]]:
        """하이브리드 스코어 결합 (max-normalization + 가중 합산)"""
        combined = {}

        max_sem = max((s for _, s in semantic_results), default=1.0) or 1.0
        for idx, score in semantic_results:
            combined[idx] = alpha * (score / max_sem)

        max_fts = max((s for _, s in fts5_results), default=1.0) or 1.0
        for idx, score in fts5_results:
            normalized = score / max_fts
            if idx in combined:
                combined[idx] += (1 - alpha) * normalized
            else:
                combined[idx] = (1 - alpha) * normalized

        return sorted(combined.items(), key=lambda x: x[1], reverse=True)

    def search_hybrid(self, query: str, top_k: int = 5,
                      alpha: float = None,
                      allowed_nodes: set = None,
                      category: str = None) -> List[UsageExample]:
        """메인 하이브리드 검색

        Args:
            query: 검색 쿼리 (자연어)
            top_k: 반환할 결과 수
            alpha: 시맨틱 비중 (기본 0.7)
            allowed_nodes: 허용된 노드 필터 (None=전체)
            category: 카테고리 필터 (None=전체)

        Returns:
            UsageExample 리스트 (점수 내림차순)
        """
        if alpha is None:
            alpha = self.DEFAULT_ALPHA

        # 캐시 확인
        cache_key = hashlib.md5(
            f"{query}_{top_k}_{alpha}_{allowed_nodes}_{category}".encode()
        ).hexdigest()
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        over_fetch = top_k * 3  # 필터링 후 충분한 결과를 위해 넉넉히
        use_semantic = self.is_semantic_available() and alpha > 0

        semantic_results = self.search_semantic(query, over_fetch) if use_semantic else []

        if semantic_results and alpha >= 1.0:
            # 시맨틱 100%: BM25 호출 생략
            scored = list(semantic_results)
        else:
            # 시맨틱 실패 시 BM25 폴백, 또는 하이브리드 모드
            fts5_results = self.search_fts5(query, over_fetch)

            if not semantic_results and not fts5_results:
                return []

            if not semantic_results:
                scored = list(fts5_results)
            elif not fts5_results:
                scored = list(semantic_results)
            else:
                scored = self._combine_scores(semantic_results, fts5_results, alpha)

        # 메타데이터 조회
        all_ids = [idx for idx, _ in scored]
        if not all_ids:
            return []

        with self._get_connection() as conn:
            placeholders = ','.join('?' * len(all_ids))
            rows = conn.execute(
                f"""SELECT id, intent, ibl_code, nodes, category, difficulty,
                           source, success_count, fail_count
                    FROM ibl_examples WHERE id IN ({placeholders})""",
                all_ids
            ).fetchall()
            meta_map = {row['id']: dict(row) for row in rows}

        results = []
        for idx, score in scored:
            meta = meta_map.get(idx)
            if not meta:
                continue

            # 노드 필터링
            if allowed_nodes:
                example_nodes = set(meta['nodes'].split(',')) if meta['nodes'] else set()
                if example_nodes and not example_nodes.intersection(allowed_nodes):
                    continue

            # 카테고리 필터링
            if category and meta['category'] != category:
                continue

            total = meta['success_count'] + meta['fail_count']
            success_rate = meta['success_count'] / max(total, 1)

            results.append(UsageExample(
                id=meta['id'],
                intent=meta['intent'],
                ibl_code=meta['ibl_code'],
                nodes=meta['nodes'],
                category=meta['category'],
                difficulty=meta['difficulty'],
                score=round(float(score), 4),
                source=meta['source'],
                success_rate=round(success_rate, 2)
            ))

            if len(results) >= top_k:
                break

        self._set_cached(cache_key, results)
        return results

    # =========================================================================
    # 캐시
    # =========================================================================

    def _get_cached(self, key: str):
        """캐시 조회 (TTL 기반)"""
        if key in self._search_cache:
            cached_time = self._cache_time.get(key, 0)
            if time.time() - cached_time < self._cache_ttl:
                return self._search_cache[key]
            else:
                del self._search_cache[key]
                del self._cache_time[key]
        return None

    def _set_cached(self, key: str, results):
        """캐시 저장"""
        self._search_cache[key] = results
        self._cache_time[key] = time.time()
