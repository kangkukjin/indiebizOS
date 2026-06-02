"""
Blog Hybrid RAG Search - Self-contained
========================================
하이브리드 검색 (Semantic + FTS5 BM25) for blog posts.
KThoughtsSystemV2의 핵심 알고리즘을 이식, 외부 의존성 없이 독립 동작.

Dependencies:
  Required: sqlite3 (stdlib)
  Optional: sentence-transformers, sqlite-vec (시맨틱 검색용)

Graceful degradation:
  sentence-transformers/sqlite-vec 미설치 시 → FTS5 키워드 검색만 사용
"""

import os
import sys
import re
import struct
import hashlib
import logging
import sqlite3
import time
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, asdict

# common 유틸리티 사용
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "blog_insight.db")

BLOG_URL = "https://irepublic.tistory.com"


# =============================================================================
# 데이터 클래스
# =============================================================================

@dataclass
class SearchResult:
    """검색 결과"""
    post_id: str
    title: str
    content_preview: str
    score: float
    publish_date: str
    category: str
    search_type: str = "hybrid"
    relevance: str = ""
    key_insight: str = ""


# =============================================================================
# BlogHybridSearch 클래스
# =============================================================================

class BlogHybridSearch:
    """
    블로그 하이브리드 검색 엔진 (싱글톤).
    KThoughts HybridSearchEngineV2의 핵심 알고리즘 이식.
    """

    # 텍스트 전처리 설정 (KThoughts에서 이식)
    TITLE_REPEAT = 3
    MAX_TEXT_LENGTH = 800

    # 임베딩 설정
    EMBEDDING_DIM = 768
    EMBEDDING_MODEL = 'jhgan/ko-sroberta-multitask'
    BATCH_SIZE = 32

    # 검색 설정
    DEFAULT_ALPHA = 0.7  # 70% 시맨틱 + 30% BM25
    MIN_CONTENT_LENGTH = 200  # 최소 글 길이

    # 싱글톤
    _instance = None
    _model = None
    _model_load_attempted = False
    _sqlite_vec_available = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._search_cache = {}
            cls._instance._cache_time = {}
            cls._instance._cache_ttl = 300  # 5분
        return cls._instance

    # =========================================================================
    # 텍스트 전처리 (KThoughts hybrid_search_engine_v2.py에서 이식)
    # =========================================================================

    @staticmethod
    def smart_truncate(text: str, max_chars: int = 800) -> str:
        """문장 경계에서 텍스트 절단 (한글 문장 종결어미 기반)"""
        if len(text) <= max_chars:
            return text
        truncated = text[:max_chars]
        # 한글 문장 종결어미 탐색
        sentence_endings = ['. ', '다. ', '요. ', '까. ', '나. ', '다.\n', '요.\n']
        last_pos = 0
        for ending in sentence_endings:
            pos = truncated.rfind(ending)
            if pos > last_pos:
                last_pos = pos
        # 80% 이상 지점에서 문장 끝을 찾았으면 그곳에서 절단
        if last_pos > max_chars * 0.8:
            return text[:last_pos + 2].strip()
        return truncated

    @staticmethod
    def prepare_search_text(title: str, content: str) -> str:
        """검색용 텍스트 준비 (제목 가중치 + 본문 절단)"""
        clean_title = title.strip()
        clean_content = BlogHybridSearch.smart_truncate(
            content, BlogHybridSearch.MAX_TEXT_LENGTH
        )
        # 제목 3회 반복으로 중요도 증가
        title_part = ' '.join([clean_title] * BlogHybridSearch.TITLE_REPEAT)
        return f"{title_part} {clean_content}"

    # =========================================================================
    # 모델/의존성 관리 (Lazy loading)
    # =========================================================================

    @classmethod
    def _load_model(cls):
        """sentence-transformers 모델 로드 (1회, lazy)"""
        if cls._model_load_attempted:
            return cls._model is not None
        cls._model_load_attempted = True
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"[Blog RAG] 임베딩 모델 로딩: {cls.EMBEDDING_MODEL}")
            cls._model = SentenceTransformer(cls.EMBEDDING_MODEL)
            logger.info("[Blog RAG] 모델 로딩 완료")
            return True
        except ImportError:
            logger.warning("[Blog RAG] sentence-transformers 미설치 → FTS5 검색만 사용")
            return False
        except Exception as e:
            logger.error(f"[Blog RAG] 모델 로드 실패: {e}")
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
            logger.warning("[Blog RAG] sqlite-vec 미설치 → FTS5 검색만 사용")
        return cls._sqlite_vec_available

    @classmethod
    def is_semantic_available(cls) -> bool:
        """시맨틱 검색 가능 여부"""
        return cls._check_sqlite_vec() and cls._load_model()

    @classmethod
    def _reset_availability_cache(cls):
        """의존성 캐시 초기화 (패키지 설치 후 재확인용)"""
        cls._sqlite_vec_available = None
        cls._model_load_attempted = False
        cls._model = None

    # =========================================================================
    # DB 연결
    # =========================================================================

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
            logger.error(f"[Blog RAG] sqlite-vec 연결 실패: {e}")
            return None

    def _get_plain_connection(self) -> sqlite3.Connection:
        """일반 SQLite 연결 반환"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_vec_table(self, conn):
        """vec0 가상 테이블 생성 (없으면)"""
        conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS posts_vec USING vec0(
                embedding float[{self.EMBEDDING_DIM}]
            )
        """)
        conn.commit()

    # =========================================================================
    # 임베딩 생성
    # =========================================================================

    def generate_embedding(self, text: str) -> Optional[bytes]:
        """단일 텍스트 임베딩 생성 → packed bytes 반환"""
        if not self.is_semantic_available():
            return None
        import numpy as np
        vector = self._model.encode(
            [text], convert_to_numpy=True, show_progress_bar=False
        )[0].astype('float32')
        # L2 정규화 (KThoughts와 동일)
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        return struct.pack(f'{self.EMBEDDING_DIM}f', *vector)

    def generate_embeddings_batch(self, texts: List[str]) -> List[bytes]:
        """배치 임베딩 생성 → packed bytes 리스트 반환"""
        if not self.is_semantic_available():
            return []
        import numpy as np
        all_packed = []
        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i:i + self.BATCH_SIZE]
            batch_vectors = self._model.encode(
                batch, convert_to_numpy=True, show_progress_bar=False
            ).astype('float32')
            # L2 정규화
            norms = np.linalg.norm(batch_vectors, axis=1, keepdims=True)
            norms[norms == 0] = 1
            batch_vectors = batch_vectors / norms
            for vec in batch_vectors:
                all_packed.append(struct.pack(f'{self.EMBEDDING_DIM}f', *vec))
            if i > 0 and i % (self.BATCH_SIZE * 10) == 0:
                logger.info(f"[Blog RAG] 임베딩 진행: {i}/{len(texts)}")
        return all_packed

    # =========================================================================
    # 인덱스 관리
    # =========================================================================

    def index_posts(self, post_rows: List[Dict]) -> int:
        """포스트 배치 인덱싱 (임베딩 생성 + vec0 저장)"""
        conn = self._get_vec_connection()
        if conn is None:
            return 0
        try:
            self._ensure_vec_table(conn)
            texts = [
                self.prepare_search_text(r['title'], r['content'])
                for r in post_rows
            ]
            embeddings = self.generate_embeddings_batch(texts)
            if not embeddings:
                return 0
            for row, emb in zip(post_rows, embeddings):
                conn.execute(
                    "INSERT OR REPLACE INTO posts_vec(rowid, embedding) VALUES (?, ?)",
                    (row['id'], emb)
                )
                conn.execute(
                    "INSERT OR REPLACE INTO search_index_status"
                    "(post_id, indexed_at, embedding_version) "
                    "VALUES (?, datetime('now'), 'v1')",
                    (row['post_id'],)
                )
            conn.commit()
            return len(embeddings)
        except Exception as e:
            logger.error(f"[Blog RAG] 인덱싱 실패: {e}")
            return 0
        finally:
            conn.close()

    def index_new_posts(self) -> int:
        """미인덱싱 포스트만 인덱싱"""
        conn = self._get_vec_connection()
        if conn is None:
            return 0
        try:
            self._ensure_vec_table(conn)
            rows = conn.execute("""
                SELECT p.id, p.post_id, p.title, p.content
                FROM posts p
                LEFT JOIN search_index_status s ON p.post_id = s.post_id
                WHERE s.post_id IS NULL AND p.char_count >= ?
                ORDER BY p.pub_date DESC
            """, (self.MIN_CONTENT_LENGTH,)).fetchall()
            if not rows:
                return 0
            conn.close()  # index_posts에서 새 연결 사용
            post_rows = [dict(r) for r in rows]
            return self.index_posts(post_rows)
        except Exception as e:
            logger.error(f"[Blog RAG] 신규 인덱싱 실패: {e}")
            return 0
        finally:
            try:
                conn.close()
            except:
                pass

    def rebuild_index(self) -> Dict[str, Any]:
        """벡터 검색 인덱스 전체 재구축"""
        # 캐시 초기화 후 재확인 (패키지 설치 후 서버 재시작 없이도 감지)
        self._reset_availability_cache()
        if not self.is_semantic_available():
            return {
                'success': False,
                'error': 'sqlite-vec 또는 sentence-transformers가 설치되지 않았습니다. '
                         'pip install sqlite-vec sentence-transformers 실행 후 다시 시도하세요.'
            }
        conn = self._get_vec_connection()
        if conn is None:
            return {'success': False, 'error': 'DB 연결 실패'}
        try:
            self._ensure_vec_table(conn)
            # 기존 인덱스 삭제
            conn.execute("DELETE FROM posts_vec")
            conn.execute("DELETE FROM search_index_status")
            conn.commit()
            # 전체 포스트 로드
            rows = conn.execute(
                "SELECT id, post_id, title, content FROM posts "
                "WHERE char_count >= ? ORDER BY pub_date DESC",
                (self.MIN_CONTENT_LENGTH,)
            ).fetchall()
            post_rows = [dict(r) for r in rows]
            conn.close()
            logger.info(f"[Blog RAG] 전체 인덱스 재구축 시작: {len(post_rows)}개 포스트")
            start = time.time()
            count = self.index_posts(post_rows)
            elapsed = time.time() - start
            self._search_cache.clear()
            return {
                'success': True,
                'indexed_count': count,
                'total_posts': len(post_rows),
                'elapsed_seconds': round(elapsed, 1),
                'message': f'{count}개 포스트 인덱싱 완료 ({elapsed:.1f}초)'
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
        """시맨틱 검색. (posts.id, similarity_score) 리스트 반환"""
        emb = self.generate_embedding(query)
        if emb is None:
            return []
        conn = self._get_vec_connection()
        if conn is None:
            return []
        try:
            self._ensure_vec_table(conn)
            rows = conn.execute("""
                SELECT rowid, distance
                FROM posts_vec
                WHERE embedding MATCH ?
                  AND k = ?
                ORDER BY distance
            """, (emb, top_k)).fetchall()
            # L2 정규화된 벡터에서: cos_sim = 1 - (distance^2 / 2)
            results = []
            for row in rows:
                dist = float(row['distance'])
                similarity = max(0.0, 1.0 - (dist * dist / 2.0))
                results.append((int(row['rowid']), similarity))
            return results
        except Exception as e:
            logger.error(f"[Blog RAG] 시맨틱 검색 실패: {e}")
            return []
        finally:
            conn.close()

    def search_fts5(self, query: str, top_k: int = 10) -> List[Tuple[int, float]]:
        """FTS5 BM25 키워드 검색. (posts.id, bm25_score) 리스트 반환"""
        conn = self._get_plain_connection()
        try:
            # FTS5 특수문자 이스케이프
            safe_query = re.sub(r'[^\w\s가-힣]', ' ', query)
            tokens = [t for t in safe_query.split() if len(t) >= 2]
            if not tokens:
                return []
            fts_query = ' OR '.join(tokens)
            rows = conn.execute("""
                SELECT p.id, bm25(posts_fts) as score
                FROM posts_fts fts
                JOIN posts p ON p.id = fts.rowid
                WHERE posts_fts MATCH ?
                ORDER BY score
                LIMIT ?
            """, (fts_query, top_k)).fetchall()
            # bm25()은 음수 반환 (더 관련 있을수록 더 작음) → 양수로 변환
            results = [(int(row['id']), -float(row['score'])) for row in rows]
            return results
        except Exception as e:
            logger.error(f"[Blog RAG] FTS5 검색 실패: {e}")
            return []
        finally:
            conn.close()

    def _combine_scores(
        self,
        semantic_results: List[Tuple[int, float]],
        fts5_results: List[Tuple[int, float]],
        alpha: float
    ) -> List[Tuple[int, float]]:
        """
        하이브리드 스코어 결합 (KThoughts에서 이식).
        각 스코어 타입별 max-normalization 후 가중 합산.
        """
        combined = {}

        # 시맨틱 스코어 (max-normalized)
        max_sem = max((s for _, s in semantic_results), default=1.0) or 1.0
        for idx, score in semantic_results:
            combined[idx] = alpha * (score / max_sem)

        # FTS5 BM25 스코어 (max-normalized)
        max_fts = max((s for _, s in fts5_results), default=1.0) or 1.0
        for idx, score in fts5_results:
            normalized = score / max_fts
            if idx in combined:
                combined[idx] += (1 - alpha) * normalized
            else:
                combined[idx] = (1 - alpha) * normalized

        return sorted(combined.items(), key=lambda x: x[1], reverse=True)

    def search_hybrid(
        self, query: str, top_k: int = 5, alpha: Optional[float] = None
    ) -> List[SearchResult]:
        """메인 하이브리드 검색"""
        if alpha is None:
            alpha = self.DEFAULT_ALPHA

        # 캐시 확인
        cache_key = hashlib.md5(
            f"{query}_{top_k}_{alpha}".encode()
        ).hexdigest()
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        over_fetch = top_k * 2
        use_semantic = self.is_semantic_available() and alpha > 0

        # 각 검색 실행
        semantic_results = (
            self.search_semantic(query, over_fetch) if use_semantic else []
        )
        fts5_results = self.search_fts5(query, over_fetch)

        # 유효 알파 결정
        if not semantic_results and not fts5_results:
            return []
        elif not semantic_results:
            effective_alpha = 0.0
        elif not fts5_results:
            effective_alpha = 1.0
        else:
            effective_alpha = alpha

        # 스코어 결합
        if effective_alpha == 0.0:
            scored = list(fts5_results)
        elif effective_alpha == 1.0:
            scored = list(semantic_results)
        else:
            scored = self._combine_scores(
                semantic_results, fts5_results, effective_alpha
            )

        # 상위 K개 포스트 메타데이터 조회
        top_ids = [idx for idx, _ in scored[:top_k]]
        if not top_ids:
            return []

        conn = self._get_plain_connection()
        try:
            placeholders = ','.join('?' * len(top_ids))
            rows = conn.execute(
                f"SELECT id, post_id, title, category, pub_date, content "
                f"FROM posts WHERE id IN ({placeholders})",
                top_ids
            ).fetchall()
            post_map = {row['id']: dict(row) for row in rows}
        finally:
            conn.close()

        search_type = (
            "hybrid" if 0 < effective_alpha < 1
            else "semantic" if effective_alpha == 1
            else "fts5"
        )

        results = []
        for idx, score in scored[:top_k]:
            post = post_map.get(idx)
            if not post:
                continue
            results.append(SearchResult(
                post_id=str(post['post_id']),
                title=post['title'],
                content_preview=str(post['content'] or '')[:300] + '...',
                score=round(float(score), 4),
                publish_date=str(post.get('pub_date', '')),
                category=str(post.get('category', '')),
                search_type=search_type,
                relevance=self._relevance_label(score),
                key_insight=self._extract_key_insight(
                    str(post.get('content', '')), query
                )
            ))

        self._set_cached(cache_key, results)
        return results

    # =========================================================================
    # 캐시
    # =========================================================================

    def _get_cached(self, key: str) -> Optional[List[SearchResult]]:
        """캐시에서 결과 조회 (TTL 기반)"""
        if key in self._search_cache:
            cached_time = self._cache_time.get(key, 0)
            if time.time() - cached_time < self._cache_ttl:
                return self._search_cache[key]
            else:
                del self._search_cache[key]
                del self._cache_time[key]
        return None

    def _set_cached(self, key: str, results: List[SearchResult]):
        """결과를 캐시에 저장"""
        self._search_cache[key] = results
        self._cache_time[key] = time.time()

    # =========================================================================
    # 유틸리티
    # =========================================================================

    @staticmethod
    def _relevance_label(score: float) -> str:
        """스코어를 관련도 레이블로 변환"""
        if score >= 0.8:
            return "매우 높음"
        elif score >= 0.6:
            return "높음"
        elif score >= 0.4:
            return "보통"
        elif score >= 0.2:
            return "낮음"
        else:
            return "매우 낮음"

    @staticmethod
    def _extract_key_insight(content: str, query: str) -> str:
        """콘텐츠에서 쿼리 관련 핵심 문장 추출"""
        if not content or len(content) < 50:
            return ""
        query_words = [w for w in query.split() if len(w) > 1]
        sentences = [s.strip() for s in content.split('.') if len(s.strip()) > 30]
        relevant = []
        for sentence in sentences:
            score = sum(1 for w in query_words if w in sentence)
            if score > 0:
                relevant.append((sentence, score))
        relevant.sort(key=lambda x: x[1], reverse=True)
        if relevant:
            return '. '.join(s[0] for s in relevant[:2]) + '.'
        return sentences[0] + '.' if sentences else content[:200]

    def get_search_status(self) -> Dict[str, Any]:
        """검색 인덱스 상태 조회"""
        conn = self._get_plain_connection()
        try:
            total_posts = conn.execute(
                "SELECT COUNT(*) FROM posts"
            ).fetchone()[0]
            eligible_posts = conn.execute(
                "SELECT COUNT(*) FROM posts WHERE char_count >= ?",
                (self.MIN_CONTENT_LENGTH,)
            ).fetchone()[0]
            indexed_posts = conn.execute(
                "SELECT COUNT(*) FROM search_index_status"
            ).fetchone()[0]
            fts_count = conn.execute(
                "SELECT COUNT(*) FROM posts_fts"
            ).fetchone()[0]
            semantic_available = self.is_semantic_available()
            return {
                'success': True,
                'total_posts': total_posts,
                'eligible_posts': eligible_posts,
                'indexed_posts': indexed_posts,
                'fts5_indexed': fts_count,
                'semantic_available': semantic_available,
                'search_mode': 'hybrid' if semantic_available and indexed_posts > 0
                    else 'fts5',
                'embedding_model': self.EMBEDDING_MODEL if semantic_available else None
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            conn.close()


# =============================================================================
# 모듈 레벨 API (handler.py에서 호출)
# =============================================================================

def search_blog(query: str, limit: int = 5) -> dict:
    """하이브리드 검색 (메인 진입점)"""
    try:
        engine = BlogHybridSearch()
        results = engine.search_hybrid(query, top_k=limit)

        if not results:
            return {
                'success': True,
                'results': [],
                'message': f'검색 결과가 없습니다: {query}'
            }

        formatted = []
        for i, r in enumerate(results):
            formatted.append({
                'rank': i + 1,
                'title': r.title,
                'content': r.content_preview,
                'similarity': r.score,
                'search_type': r.search_type,
                'post_id': r.post_id,
                'date': r.publish_date,
                'category': r.category,
                'relevance': r.relevance,
                'key_insight': r.key_insight
            })

        return {
            'success': True,
            'query': query,
            'results': formatted,
            'message': f'{len(formatted)}개의 관련 글을 찾았습니다. ({results[0].search_type} 검색)'
        }
    except Exception as e:
        logger.error(f"[Blog RAG] search_blog 오류: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'results': [], 'message': f'검색 실패: {str(e)}'}


def search_blog_semantic(query: str, limit: int = 5) -> dict:
    """시맨틱 검색만 사용"""
    try:
        engine = BlogHybridSearch()
        results = engine.search_hybrid(query, top_k=limit, alpha=1.0)

        formatted = []
        for i, r in enumerate(results):
            formatted.append({
                'rank': i + 1,
                'title': r.title,
                'content': r.content_preview,
                'similarity': r.score,
                'search_type': r.search_type,
                'relevance': r.relevance
            })

        return {
            'success': True,
            'results': formatted,
            'message': f'{len(formatted)}개 발견 (Semantic Search)'
        }
    except Exception as e:
        return {'success': False, 'results': [], 'message': f'실패: {str(e)}'}


def get_post_content(post_id: str) -> dict:
    """포스트 전체 내용 조회 (ID 또는 제목으로)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        # 숫자면 post_id로, 아니면 제목으로 검색
        if post_id.isdigit():
            row = conn.execute(
                "SELECT * FROM posts WHERE post_id = ?", (post_id,)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM posts WHERE title LIKE ?",
                (f'%{post_id}%',)
            ).fetchone()

        conn.close()

        if not row:
            return {'success': False, 'message': f'포스트를 찾을 수 없습니다: {post_id}'}

        return {
            'success': True,
            'title': row['title'],
            'content': row['content'],
            'date': str(row['pub_date']),
            'post_id': str(row['post_id']),
            'category': row['category'] or '',
            'link': f"{BLOG_URL}/{row['post_id']}"
        }
    except Exception as e:
        return {'success': False, 'message': f'실패: {str(e)}'}


def rebuild_search_index() -> dict:
    """벡터 검색 인덱스 재구축"""
    engine = BlogHybridSearch()
    return engine.rebuild_index()


def get_search_status() -> dict:
    """검색 인덱스 상태 조회"""
    engine = BlogHybridSearch()
    return engine.get_search_status()
