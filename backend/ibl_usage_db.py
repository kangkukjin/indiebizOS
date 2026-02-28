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
    - DEFAULT_ALPHA = 0.7 (70% Semantic + 30% BM25)
    """

    EMBEDDING_DIM = 768
    EMBEDDING_MODEL = 'jhgan/ko-sroberta-multitask'
    DEFAULT_ALPHA = 0.7
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

    def promote_log_to_example(self, log_id: int, intent: str = None) -> Optional[int]:
        """실행 로그를 용례로 승격"""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM ibl_execution_logs WHERE id = ?", (log_id,)
            ).fetchone()
            if not row:
                return None

        use_intent = intent or row['user_input'] or row['generated_ibl']
        if not use_intent:
            return None

        # 노드 추출
        nodes = row['node'] or ''

        return self.add_example(
            intent=use_intent,
            ibl_code=row['generated_ibl'],
            nodes=nodes,
            category='single',
            difficulty=1,
            source='log',
        )

    def try_promote_session(self, user_input: str) -> bool:
        """단일 세션의 성공 로그를 용례로 승격 시도

        에이전트 대화 완료 후 호출하여 해당 세션의 로그만 승격.
        auto_promote_logs()보다 가볍고 빠름.

        Args:
            user_input: 사용자 원본 메시지

        Returns:
            승격 성공 여부
        """
        if not user_input or len(user_input.strip()) < 6:
            return False

        user_input = user_input.strip()

        # 이미 같은 intent 용례가 있으면 스킵
        with self._get_connection() as conn:
            existing = conn.execute(
                "SELECT 1 FROM ibl_examples WHERE LOWER(intent) = LOWER(?) LIMIT 1",
                (user_input,)
            ).fetchone()
            if existing:
                return False

            # 성공 로그 존재 확인
            has_success = conn.execute(
                "SELECT 1 FROM ibl_execution_logs WHERE user_input = ? AND success = 1 LIMIT 1",
                (user_input,)
            ).fetchone()
            if not has_success:
                return False

        # IBL 코드 추출
        ibl_code = self._extract_session_ibl(user_input)
        if not ibl_code:
            return False

        # 과도하게 긴 세션은 용례 가치 없음 (오매칭 유발)
        MAX_CODE_LEN = 500    # IBL 코드 최대 길이
        MAX_PIPE_STEPS = 5    # 파이프라인 최대 스텝 수
        pipe_count = ibl_code.count('>>')
        if len(ibl_code) > MAX_CODE_LEN or pipe_count > MAX_PIPE_STEPS:
            print(f"[IBL Auto] 승격 거부 (과대): len={len(ibl_code)}, pipes={pipe_count}, \"{user_input[:40]}\"")
            return False

        # 노드/카테고리 결정
        with self._get_connection() as conn:
            session_info = conn.execute("""
                SELECT COUNT(*) as total,
                       GROUP_CONCAT(DISTINCT node || ':' || action) as actions
                FROM ibl_execution_logs
                WHERE user_input = ? AND success = 1
            """, (user_input,)).fetchone()

        actions = session_info['actions'] or ''
        nodes = ','.join(sorted(set(
            a.split(':')[0] for a in actions.split(',')
            if a and ':' in a and a.split(':')[0] not in ('tool',)
        )))

        call_count = session_info['total']
        if call_count >= 3 or '>>' in ibl_code or '&' in ibl_code:
            category = 'pipeline'
        else:
            category = 'single'

        example_id = self.add_example(
            intent=user_input,
            ibl_code=ibl_code,
            nodes=nodes,
            category=category,
            difficulty=min(call_count, 5),
            source='auto_log',
            tags='auto_promoted',
        )

        if example_id:
            self._search_cache.clear()
            print(f"[IBL Auto] 세션 승격: \"{user_input[:40]}\" → {ibl_code[:60]}")
            return True

        return False

    def auto_promote_logs(self) -> Dict[str, Any]:
        """성공한 실행 로그를 자동으로 용례로 승격 (전체 배치)

        동일 user_input에 대한 성공 로그들을 세션으로 묶어
        대표 IBL 코드를 추출하고 용례 DB에 추가.
        이미 승격된 세션은 스킵 (중복 방지).

        Returns:
            {'promoted': 승격 수, 'skipped': 스킵 수, 'details': [...]}
        """
        promoted = 0
        skipped = 0
        details = []

        with self._get_connection() as conn:
            # 1. user_input별 성공 세션 집계
            #    - user_input이 비어있지 않고
            #    - 성공 로그가 있는 세션
            sessions = conn.execute("""
                SELECT user_input,
                       COUNT(*) as total_calls,
                       SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_calls,
                       SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as fail_calls,
                       GROUP_CONCAT(DISTINCT node || ':' || action) as actions,
                       MIN(created_at) as first_at
                FROM ibl_execution_logs
                WHERE user_input != '' AND LENGTH(user_input) >= 6
                GROUP BY user_input
                HAVING success_calls >= 1
                ORDER BY first_at DESC
            """).fetchall()

            if not sessions:
                return {'promoted': 0, 'skipped': 0, 'details': []}

            # 2. 기존 용례의 intent 집합 (중복 체크용)
            existing_intents = set()
            rows = conn.execute("SELECT intent FROM ibl_examples").fetchall()
            for row in rows:
                existing_intents.add(row['intent'].strip().lower())

        for session in sessions:
            user_input = session['user_input'].strip()
            intent_key = user_input.lower()

            # 이미 동일 intent로 용례가 존재하면 스킵
            if intent_key in existing_intents:
                skipped += 1
                continue

            # 3. 세션의 성공 로그에서 대표 IBL 코드 추출
            ibl_code = self._extract_session_ibl(user_input)
            if not ibl_code:
                skipped += 1
                continue

            # 과도하게 긴 세션은 용례 가치 없음 (오매칭 유발)
            pipe_count = ibl_code.count('>>')
            if len(ibl_code) > 500 or pipe_count > 5:
                skipped += 1
                details.append({'input': user_input[:40], 'status': 'too_large',
                                'code_len': len(ibl_code), 'pipes': pipe_count})
                continue

            # 4. 노드 목록 추출
            actions = session['actions'] or ''
            nodes = ','.join(sorted(set(
                a.split(':')[0] for a in actions.split(',')
                if a and ':' in a and a.split(':')[0] not in ('tool',)
            )))

            # 5. 카테고리 결정
            call_count = session['success_calls']
            if call_count >= 3:
                category = 'pipeline'
            elif '>>' in ibl_code or '&' in ibl_code:
                category = 'pipeline'
            else:
                category = 'single'

            # 6. 용례 추가
            example_id = self.add_example(
                intent=user_input,
                ibl_code=ibl_code,
                nodes=nodes,
                category=category,
                difficulty=min(call_count, 5),
                source='auto_log',
                tags='auto_promoted',
            )

            if example_id:
                promoted += 1
                existing_intents.add(intent_key)
                details.append({
                    'intent': user_input[:60],
                    'ibl_code': ibl_code[:80],
                    'category': category,
                    'example_id': example_id,
                })
                print(f"[IBL Auto] 승격: \"{user_input[:40]}\" → {ibl_code[:60]}")

        if promoted > 0:
            # 캐시 무효화
            self._search_cache.clear()

        return {'promoted': promoted, 'skipped': skipped, 'details': details}

    # action → 정석 node 역매핑 캐시
    _action_to_node_cache: dict = None

    @classmethod
    def _get_action_to_node_map(cls) -> dict:
        """ibl_nodes.yaml에서 action → node 역매핑 구축 (캐시)"""
        if cls._action_to_node_cache is not None:
            return cls._action_to_node_cache

        import yaml
        nodes_path = Path(__file__).parent.parent / "data" / "ibl_nodes.yaml"
        result = {}
        try:
            data = yaml.safe_load(nodes_path.read_text(encoding="utf-8"))
            for node_name, node_config in data.get("nodes", {}).items():
                for action_name in node_config.get("actions", {}):
                    result[action_name] = node_name
                # verb도 매핑
                for verb_name in node_config.get("verbs", {}):
                    if verb_name not in result:
                        result[verb_name] = node_name
        except Exception:
            pass
        cls._action_to_node_cache = result
        return result

    @classmethod
    def _normalize_ibl_nodes(cls, ibl_code: str) -> str:
        """IBL 코드에서 [ibl:action] → [정석node:action] 치환"""
        import re
        action_map = cls._get_action_to_node_map()

        def _replace(m):
            action = m.group(1)
            proper_node = action_map.get(action, "system")
            return f'[{proper_node}:{action}]'

        return re.sub(r'\[ibl:(\w+)\]', _replace, ibl_code)

    # 탐색/보조 액션 — 용례로서 가치 없음 (과정일 뿐, 결과가 아님)
    _EXPLORATORY_ACTIONS = frozenset({
        # 파일/디렉토리 탐색
        'read', 'read_file', 'list', 'find', 'grep', 'list_projects',
        # 시스템 메타 조회
        'todo', 'snapshot', 'registry', 'search_guide', 'launch',
        'agent_info', 'remotion_status', 'live_check', 'list_workflows',
        # 범용 get (type 파라미터에 따라 다양한 조회)
        'get',
    })
    # 탐색성 노드 (tool 노드 전체)
    _EXPLORATORY_NODES = frozenset({'tool'})

    def _extract_session_ibl(self, user_input: str) -> Optional[str]:
        """세션(같은 user_input)의 성공 로그에서 대표 IBL 코드 추출

        전략:
        1. code 모드([ibl:?])로 파이프라인을 실행한 경우 → 길이 제한 후 사용
        2. 개별 호출이면 → 탐색성 액션 제거 후 핵심 액션만 조합
        """
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT generated_ibl, node, action, target, params_json
                FROM ibl_execution_logs
                WHERE user_input = ? AND success = 1
                ORDER BY created_at
            """, (user_input,)).fetchall()

        if not rows:
            return None

        # code 모드 로그 찾기 (파이프라인 >> 또는 병렬 & 포함)
        code_entries = []
        individual_entries = []

        for row in rows:
            ibl = row['generated_ibl'] or ''
            action = row['action'] or ''
            node = row['node'] or ''
            target = row['target'] or ''

            if action == '?' and re.search(r'\[\w+:', ibl):
                # execute_ibl code 모드 — 원본 IBL 코드 추출
                inner = self._extract_inner_code(ibl)
                if inner and len(inner) <= 500:
                    code_entries.append(inner)
            elif (node not in self._EXPLORATORY_NODES
                  and node != ''
                  and action not in ('?', '')
                  and action not in self._EXPLORATORY_ACTIONS):
                # 핵심 액션만 수집 (탐색성 제외)
                params = {}
                try:
                    params = json.loads(row['params_json'] or '{}')
                except Exception:
                    pass
                # [ibl:action] → [정석node:action] 치환
                actual_node = node
                if node == 'ibl':
                    action_map = self._get_action_to_node_map()
                    actual_node = action_map.get(action, 'system')
                entry = f'[{actual_node}:{action}]'
                # target: 절대경로는 축약, 긴 것은 잘라냄
                if target:
                    t = target
                    if len(t) > 60:
                        t = t[:57] + '...'
                    entry += f'("{t}")'
                if params:
                    parts = []
                    for k, v in params.items():
                        if not v:
                            continue
                        if isinstance(v, list):
                            parts.append(f'{k}: [...]')        # 배열 → 플레이스홀더
                        elif isinstance(v, dict):
                            parts.append(f'{k}: {{...}}')      # 딕셔너리 → 플레이스홀더
                        elif len(str(v)) > 100:
                            parts.append(f'{k}: "<{k}>"')      # 긴 문자열 → 타입 힌트
                        else:
                            parts.append(f'{k}: "{str(v)[:40]}"')
                    param_str = ', '.join(parts)
                    if param_str:
                        entry += f' {{{param_str}}}'
                individual_entries.append(entry)

        # 우선순위: 파이프라인 코드 > 개별 호출 조합
        if code_entries:
            best = max(code_entries, key=len)
            return best

        if individual_entries:
            # 중복 제거: 같은 [node:action] 시그니처는 마지막 호출만 유지
            # (에이전트가 같은 액션을 파라미터 바꿔 재시도한 경우 최종 결과만)
            import re
            sig_pattern = re.compile(r'^\[[\w]+:[\w]+\]')
            last_by_sig = {}  # signature → (index, entry)
            for i, e in enumerate(individual_entries):
                m = sig_pattern.match(e)
                sig = m.group(0) if m else e
                last_by_sig[sig] = (i, e)
            # 원래 순서 유지하되 마지막 호출만
            unique = [entry for _, entry in sorted(last_by_sig.values())]
            if not unique:
                return None
            if len(unique) > 5:
                # 핵심만 남겨도 5개 초과면 포기
                return None
            if len(unique) == 1:
                return unique[0]
            return ' >> '.join(unique)

        return None

    def _extract_inner_code(self, ibl_str: str) -> Optional[str]:
        """[ibl:?]("...코드...") 에서 내부 IBL 코드 추출"""
        import re
        # [ibl:?](" 이후의 내용 추출 (또는 [source:?] 등)
        m = re.match(r'\[\w+:\?\]\("', ibl_str)
        if m:
            inner = ibl_str[m.end():]
            # 끝의 ")가 있으면 제거
            if inner.endswith('")'):
                inner = inner[:-2]
            # 노드 참조가 있는 유효한 IBL 코드인지 확인
            if re.search(r'\[\w+:', inner):
                # [ibl:action] → [정석node:action] 치환
                inner = self._normalize_ibl_nodes(inner)
                return inner
        return None

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
                safe_query = re.sub(r'[^\w\s가-힣]', ' ', query)
                # 한국어 조사 제거 후 토큰화
                stripped = self._strip_korean_particles(safe_query)
                tokens = [t for t in stripped.split() if len(t) >= 2]
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
        fts5_results = self.search_fts5(query, over_fetch)

        if not semantic_results and not fts5_results:
            return []

        if not semantic_results:
            effective_alpha = 0.0
        elif not fts5_results:
            effective_alpha = 1.0
        else:
            effective_alpha = alpha

        if effective_alpha == 0.0:
            scored = list(fts5_results)
        elif effective_alpha == 1.0:
            scored = list(semantic_results)
        else:
            scored = self._combine_scores(semantic_results, fts5_results, effective_alpha)

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
