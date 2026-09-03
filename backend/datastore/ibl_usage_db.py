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

# DB 경로 — 검색 인덱스(용례+벡터). 프로덕션(INDIEBIZ_BASE_PATH)에선 userData 아래에 둔다:
#   번들 resources 는 읽기전용일 수 있고, ibl_usage.db 는 gitignore·미번들이라 거기 없다.
#   첫 실행 해마 공급(hippocampus_provision)이 릴리스에서 userData/data/ibl_usage.db 로 받아온다.
#   dev(맥, INDIEBIZ_BASE_PATH 미설정)에선 repo 의 data/ibl_usage.db (기존 동작 보존).
def _resolve_db_path() -> str:
    base = os.environ.get("INDIEBIZ_BASE_PATH")
    if base:
        return str(Path(base) / "data" / "ibl_usage.db")
    return str(Path(__file__).parent.parent.parent / "data" / "ibl_usage.db")

_BASE_DIR = Path(__file__).parent.parent.parent / "data"
DB_PATH = _resolve_db_path()


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
    avg_ms: float = -1.0      # 성공 실행시간 EWMA(-1=미측정) — 시간 선택압의 회상 표면
    avg_tokens: float = -1.0  # 성공 턴 토큰 EWMA(-1=미측정) — 토큰 선택압의 회상 표면


# =============================================================================
# 구문 검증자 슬롯 — 층 계약 역전 (2026-09-02)
# =============================================================================
# 원장 문 앞에서 "이게 IBL 로 파싱되나"를 물어야 하는데, 파서는 ibl 층에 살고
# datastore -> ibl 은 상향 간선이라 여기서 import 할 수 없다(층 가드 BASELINE 신규
# 추가 금지). 그래서 검사를 *주입*으로 받는다 — 조립 뿌리 boot_paths 가 모든 진입점의
# 첫 import 에서 검증자(ibl_param_vocab.code_syntax_error, 지연 import)를 이 슬롯에 꽂는다.
#
# ★슬롯이 비면 쓰기를 거절한다(RuntimeError). 비었을 때 통과시키면 이 관문은
#   '등록을 잊으면 조용히 사라지는 관문'이 되고, 그건 관문이 아니라 주석이다.
#   pre-commit 훅의 "게이트 고장이 곧 무검사가 된다"와 같은 결 — fail-closed.
#
# 왜 문에 두나(2026-09-02 실측): 기록기(ibl_usage_rag) 한 곳에만 두면 원장의 다른
# 살아있는 기록기(package_manager -> ibl_usage_generator 의 패키지 설치 시 자동 생성)가
# 무관문으로 남는다. 그건 관문이 아니라 '지금 내용이 마침 안전한 상태'다.
_CODE_VALIDATOR = None


def set_code_validator(fn) -> None:
    """구문 검증자 등록 — fn(ibl_code) -> 사유 문자열 | None(유효).

    등록처: boot_paths.wire_ledger_syntax_gate — 단 한 곳. 진입점(api·스크립트·conftest)이
    `import boot_paths` 하는 순간 배선된다. 시험은 이 함수로 가짜 검증자를 꽂을 수 있다.
    """
    global _CODE_VALIDATOR
    _CODE_VALIDATOR = fn


def _syntax_reason(ibl_code: str) -> Optional[str]:
    """구문 사유 한 줄 (유효하면 None). 미등록이면 예외 — fail-closed."""
    if _CODE_VALIDATOR is None:
        raise RuntimeError(
            "[IBL Usage DB] 구문 검증자 미등록 — 원장 쓰기 거부(fail-closed). "
            "진입점이 `import boot_paths` 를 거쳤는지 확인할 것(배선처=boot_paths.wire_ledger_syntax_gate)."
        )
    try:
        return _CODE_VALIDATOR(ibl_code)
    except Exception as e:
        # 검증자 자체가 고장 = 검증 불가 = 거절. 침묵 통과는 관문의 자살.
        return f"검증자 예외: {e.__class__.__name__}: {e}"


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
    # 해마 (hippocampus): IBL 도메인 fine-tuned 모델 (Top-5 95.3%, 범용 대비 +53.3%p / 2026-05-31 Modal GPU batch=16)
    # 경로 우선순위: userData(INDIEBIZ_BASE_PATH)/data/models — 첫 실행에 릴리스에서 받은 모델이 여기 온다.
    #   프로덕션 번들의 resources/data/models 는 비어 있으므로(모델은 gitignore·미번들), userData 를 봐야 한다.
    #   dev(맥)에선 INDIEBIZ_BASE_PATH 미설정 → repo 의 data/models 로 폴백(기존 동작 보존).
    @staticmethod
    def _resolve_model_dir() -> str:
        repo = Path(__file__).parent.parent.parent / 'data' / 'models' / 'ibl_embedding'
        base = os.environ.get("INDIEBIZ_BASE_PATH")
        if base:
            ud = Path(base) / 'data' / 'models' / 'ibl_embedding'
            # userData 에 실제 모델이 있으면 그걸, 없으면 repo 폴백(dev)
            if (ud / 'model.safetensors').exists() or (ud / 'config.json').exists():
                return str(ud)
        return str(repo)

    EMBEDDING_MODEL = str(Path(__file__).parent.parent.parent / 'data' / 'models' / 'ibl_embedding')
    DEFAULT_ALPHA = 1.0
    BATCH_SIZE = 32
    INTENT_REPEAT = 3  # intent 가중치 (제목 반복과 동일)

    _instance = None
    _model = None
    _model_load_attempted = False
    _model_loading = False  # 백그라운드 로딩 진행 중 플래그
    _sqlite_vec_available = None

    # 렌트 해마 (폰-자아 호스팅 §6): 로컬 model/sqlite-vec 가 없는 몸(폰)에서, 정적 인덱스를
    # 인메모리로 로드하고 질의 임베딩은 맥 /ibl/embed 로 렌트해 brute-force 코사인.
    # (인코더=공유 substrate, 인덱스=배포된 합성 코퍼스. export_hippo_index.py 가 정본→파생.)
    _rented_vecs = None        # np.ndarray (count, dim), L2 정규화
    _rented_metas = None       # list[dict] — 행 순서가 _rented_vecs 와 1:1
    _rented_load_attempted = False

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
        conn = sqlite3.connect(DB_PATH, timeout=10)
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
                avg_ms REAL DEFAULT -1.0,
                avg_tokens REAL DEFAULT -1.0,
                tags TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # 마이그레이션: 기존 DB 에 비용 축 컬럼 보강 — avg_ms(성공 실행시간 EWMA)·
        # avg_tokens(성공 턴 토큰 EWMA), 둘 다 -1=미측정. 시간·토큰을 비용으로 만드는 축 —
        # 같은 목표의 표현 중 싸고 빠른 쪽이 정리 패스에서 살아남고 회상 표면에 표시된다
        # (2026-08-30 시간·토큰 선택압).
        cols = {r[1] for r in conn.execute("PRAGMA table_info(ibl_examples)").fetchall()}
        for _col in ("avg_ms", "avg_tokens"):
            if _col not in cols:
                conn.execute(f"ALTER TABLE ibl_examples ADD COLUMN {_col} REAL DEFAULT -1.0")

        # 스키마 버전 레지스트리 — 옛 액션명 개편 등 데이터 마이그레이션은 여기서 자동 따라잡는다
        # (backend/datastore/schema_migrations.py, 2026-09-02). 실패 = 예외(반쯤 적용 금지).
        import schema_migrations
        schema_migrations.apply(conn, "ibl_usage")

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

        # ★실행 로그 테이블(ibl_execution_logs)은 2026-08-31 에 제거했다.
        # 스키마만 있고 호출자 0·0행으로 2026-07-03 부터 죽어 있었다. 같은 사실을
        # 적는 원장이 이미 셋 있다 — 어느 것도 이 테이블을 필요로 하지 않는다:
        #   · trajectory_event(world_pulse.db) — 전 IBL 실행의 초크포인트.
        #     ibl.started 가 액션 목록·조합 모양(pipes/nested)·해시를, ibl.finished 가
        #     성공·소요를 남긴다. **편향 없는 모집단은 여기다.**
        #   · action_usage_daily(이 DB) — 날짜×액션×origin 집계
        #   · episode_log(world_pulse.db) — 턴 원문(절단 표식 동반)
        # 살아 있는 자리를 두고 빈 테이블을 남겨 두면 "채우면 된다"는 미래형 주석이
        # 지표 문서에 박제된다(실측: vocab_composition_metrics 가 3주간 그 자리를
        # 가리키고 있었다). 되살릴 일이 생기면 이 무덤 표식을 지우고 새로 판다.

        # 인덱스
        conn.execute("CREATE INDEX IF NOT EXISTS idx_examples_category ON ibl_examples(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_examples_nodes ON ibl_examples(nodes)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_examples_source ON ibl_examples(source)")
        conn.execute("DROP INDEX IF EXISTS idx_logs_created")
        conn.execute("DROP INDEX IF EXISTS idx_logs_node_action")
        conn.execute("DROP TABLE IF EXISTS ibl_execution_logs")

        conn.commit()
        conn.close()
        logger.info(f"[IBL Usage DB] 초기화 완료: {DB_PATH}")

    # =========================================================================
    # DB 연결
    # =========================================================================

    @contextmanager
    def _get_connection(self):
        """일반 SQLite 연결"""
        conn = sqlite3.connect(DB_PATH, timeout=10)
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
            conn = sqlite3.connect(DB_PATH, timeout=10)
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
        # ★경로 해석은 스폰 시점(호출자 스레드)에 — 스레드 안에서 느린 import(수 초) 뒤에
        #   해석하면 그 사이 바뀐 상태(테스트의 monkeypatch·환경변수)를 주워 엉뚱한 경로를
        #   로드한다 (2026-08-26 실측: 다른 시험의 tmp_path 를 집어 g5 가 순서 의존으로 죽었다).
        _model_dir = cls._resolve_model_dir()

        def _load():
            try:
                from sentence_transformers import SentenceTransformer
                print(f"[IBL Usage DB] 백그라운드 임베딩 모델 로딩 시작: {_model_dir}")
                cls._model = SentenceTransformer(_model_dir)
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
            _model_dir = cls._resolve_model_dir()
            logger.info(f"[IBL Usage DB] 동기 모델 로딩: {_model_dir}")
            cls._model = SentenceTransformer(_model_dir)
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

    def embed_vectors(self, texts: List[str]) -> Optional[List[List[float]]]:
        """텍스트 배치 → L2 정규화된 768차원 float 벡터들 (폰-자아 해마의 인코더 렌트, /embed).

        `_generate_embeddings_batch` 와 *동일한* encode+정규화 — 다만 packed bytes 대신 float
        리스트를 돌려준다(JSON 직렬화). 문서 인덱스와 같은 벡터공간이라, 폰이 이 벡터로 자기
        로컬 인덱스에서 brute-force 코사인하면 맥 search_semantic 과 같은 결과를 얻는다.
        쿼리는 raw 텍스트로 인코딩됨(문서만 _prepare_search_text 로 intent 반복 — search_semantic 동일).
        모델 미가용(sentence-transformers 미설치 등) 시 None."""
        if self._model is None and not self._load_model_sync():
            return None
        import numpy as np
        vectors = self._model.encode(
            texts, convert_to_numpy=True, show_progress_bar=False
        ).astype('float32')
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1
        vectors = vectors / norms
        return vectors.tolist()

    # =========================================================================
    # CRUD - 용례
    # =========================================================================

    @staticmethod
    def _is_foreign_vocab(ibl_code: str) -> bool:
        """입구 소유-게이트: 이 몸이 실행 못 하는 어휘(미지 포함)가 담긴 용례인가.

        해마는 자기 사전만 배운다(몸 독립) — 코퍼스(전체 사전집)를 시딩·재임포트할 때
        남의 몸 용례가 이 몸의 라이브 해마로 들어오는 것을 입구에서 막는다.
        회상 게이트(ibl_usage_rag._own_only)의 쓰기 쪽 짝. 판정 불가 시 열어둠.
        """
        try:
            from ibl_registry import code_is_own
            return not code_is_own(ibl_code)
        except Exception:
            return False

    def add_example(self, intent: str, ibl_code: str,
                    nodes: str = "", category: str = "single",
                    difficulty: int = 1, source: str = "synthetic",
                    tags: str = "", avg_ms: float = -1.0,
                    avg_tokens: float = -1.0) -> int:
        """용례 추가 (임베딩 자동 생성). Returns: example ID (구문 불가·남의 어휘로 거부되면 0)

        avg_ms/avg_tokens: 출생 실측 — 증류 경로가 원 실행의 소요시간·그 턴의 토큰 소요를
        첫 관측으로 심는다. 미측정(-1)이면 이후 Reflex 귀속이 채운다."""
        _syn = _syntax_reason(ibl_code)
        if _syn:
            logger.warning(f"[IBL Usage DB] 파싱 불가 용례 거부(입구 구문-게이트): "
                           f"{_syn} / {ibl_code[:100]}")
            return 0
        if self._is_foreign_vocab(ibl_code):
            logger.warning(f"[IBL Usage DB] 남의 어휘 용례 거부(입구 소유-게이트): {ibl_code}")
            return 0
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO ibl_examples
                   (intent, ibl_code, nodes, category, difficulty, source, tags, avg_ms, avg_tokens, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (intent, ibl_code, nodes, category, difficulty, source, tags,
                 float(avg_ms) if avg_ms and avg_ms > 0 else -1.0,
                 float(avg_tokens) if avg_tokens and avg_tokens > 0 else -1.0, now, now)
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
        Returns: 추가된 수 (파싱 불가·남의 어휘 용례는 입구 게이트가 걸러 제외)
        """
        if not examples:
            return 0

        bad = [(ex['ibl_code'], _syntax_reason(ex['ibl_code'])) for ex in examples]
        bad = [(c, r) for c, r in bad if r]
        if bad:
            logger.warning(
                f"[IBL Usage DB] 파싱 불가 용례 {len(bad)}건 거부(입구 구문-게이트): "
                + "; ".join(f"{r} / {c[:60]}" for c, r in bad[:5])
                + (" …" if len(bad) > 5 else ""))
            _badset = {c for c, _ in bad}
            examples = [ex for ex in examples if ex['ibl_code'] not in _badset]
            if not examples:
                return 0

        dropped = [ex['ibl_code'] for ex in examples if self._is_foreign_vocab(ex['ibl_code'])]
        if dropped:
            logger.warning(
                f"[IBL Usage DB] 남의 어휘 용례 {len(dropped)}건 거부(입구 소유-게이트): "
                + "; ".join(dropped[:5]) + (" …" if len(dropped) > 5 else ""))
            examples = [ex for ex in examples if ex['ibl_code'] not in set(dropped)]
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

        return {
            'total_examples': total,
            'by_category': {row['category']: row['cnt'] for row in by_category},
            'by_source': {row['source']: row['cnt'] for row in by_source},
            'semantic_available': self._model is not None
        }

    # 시간 EWMA 가중: 최근 관측 30%. 몸·부하에 따른 요동을 흡수하면서도
    # 표현이 실제로 빨라지면(예: ai 한 칸→결정론 함수) 수 회 안에 반영된다.
    AVG_MS_ALPHA = 0.3

    def update_success(self, example_id: int, success: bool,
                       elapsed_ms: Optional[int] = None,
                       tokens: Optional[int] = None):
        """성공/실패 카운트 + (성공 시) 실행시간·턴 토큰 EWMA 갱신.

        elapsed_ms(IBL 실행의 빠르기)·tokens(그 턴의 모델 소요 — 불필요한 서치·재시도가
        찍히는 자리)는 성공 실행에서만 반영한다 — 실패의 비용은 '그 표현의 값'이 아니라
        실패 양상의 비용이라 섞으면 오염된다. -1(미측정)에서 첫 관측은 그대로 채택."""
        field = "success_count" if success else "fail_count"
        cost_sql = ""
        args: list = [datetime.now().isoformat()]
        _a = self.AVG_MS_ALPHA
        for col, val in (("avg_ms", elapsed_ms), ("avg_tokens", tokens)):
            if success and val is not None and val > 0:
                cost_sql += (f", {col} = CASE WHEN {col} IS NULL OR {col} < 0 THEN ? "
                             f"ELSE {col} * {1 - _a} + ? * {_a} END")
                args += [float(val), float(val)]
        args.append(example_id)
        with self._get_connection() as conn:
            conn.execute(
                f"UPDATE ibl_examples SET {field} = {field} + 1, updated_at = ?{cost_sql} "
                f"WHERE id = ?",
                args
            )
            conn.commit()

    def update_success_by_code(self, ibl_code: str, success: bool,
                               elapsed_ms: Optional[int] = None,
                               tokens: Optional[int] = None) -> bool:
        """ibl_code 정확 일치로 example을 찾아 성공/실패(+실행시간·턴 토큰)를 갱신.

        연상 Reflex 경로의 top-1 귀속용 — top_code(연상 최고점 항목의 코드)로
        해당 용례를 찾아 실행 결과를 피드백한다. 여러 개면 가장 최근 갱신본 하나.
        반환: 갱신 성공 여부(매칭 없으면 False)."""
        if not ibl_code:
            return False
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM ibl_examples WHERE ibl_code = ? ORDER BY updated_at DESC LIMIT 1",
                (ibl_code,)
            ).fetchone()
            if not row:
                return False
            example_id = row['id']
        self.update_success(example_id, success, elapsed_ms=elapsed_ms, tokens=tokens)
        return True

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
                # vec0 은 REPLACE/UPSERT 를 지원하지 않는다 — DELETE→INSERT 만 유효.
                # (INSERT OR REPLACE 는 기존 행에서 UNIQUE 오류 → 스테일 벡터가 조용히 잔존했다)
                conn.execute("DELETE FROM ibl_examples_vec WHERE rowid = ?", (example_id,))
                conn.execute(
                    "INSERT INTO ibl_examples_vec(rowid, embedding) VALUES (?, ?)",
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

    def _delete_examples(self, ids: List[int]):
        """용례 삭제 (행 + 벡터). FTS5는 DELETE 트리거로 자동 동기화되지만
        ibl_examples_vec는 트리거가 없어 수동 삭제한다."""
        if not ids:
            return
        ph = ",".join("?" * len(ids))
        with self._get_connection() as conn:
            conn.execute(f"DELETE FROM ibl_examples WHERE id IN ({ph})", ids)
            conn.commit()
        vconn = self._get_vec_connection()
        if vconn is not None:
            try:
                vconn.execute(f"DELETE FROM ibl_examples_vec WHERE rowid IN ({ph})", ids)
                vconn.commit()
            except Exception as e:
                logger.error(f"[IBL Usage DB] vec 삭제 실패: {e}")
            finally:
                vconn.close()
        self._search_cache.clear()

    @staticmethod
    def _dedup_quality(r: Dict) -> tuple:
        """근접중복 클러스터에서 살아남을 최선 1개의 정렬키 — max() 용.

        성공률 → 시도수 → **빠르기**(avg_ms) → **토큰 검약**(avg_tokens) → 최신(id).
        시간·토큰 선택압: 같은 목표를 같은 신뢰로 달성하면 싸고 빠른 표현이 생존한다.
        실측이 미측정을 이긴다(측정 없는 항목은 그 축 최하위). 비용이 성공률·검증량보다
        앞서지 않는 순서가 계약 — 싸지만 덜 검증된 표현이 검증된 표현을 밀어내면 안 되고,
        품질(성공률)을 깎아 비용을 아끼는 선택은 이 키에서 애초에 불가능하다."""
        total = r["success_count"] + r["fail_count"]
        sr = (r["success_count"] / total) if total else -1.0
        def _thrift(v):
            return -float(v) if (v is not None and v >= 0) else float("-inf")
        return (sr, total, _thrift(r.get("avg_ms")), _thrift(r.get("avg_tokens")), r["id"])

    def consolidate_distilled(self, cap: int = 200,
                              dup_threshold: float = 0.92,
                              min_fails_to_prune: int = 2) -> Dict[str, Any]:
        """자동증류분(source='distilled')만 정리하는 해마 위생 패스.

        학습 코퍼스(synthetic/balanced/manual_seed 등)는 절대 건드리지 않는다.
        세 가지 기계적 정리(LLM 불필요 — 증류물은 사실이 아니라 참고 코드):
          ⑤ 검증실패 가지치기: fail_count>=N 이고 success_count==0 인 '입증된 나쁜 사례' 삭제
          ③ 근접중복 제거: 임베딩 코사인>=threshold 클러스터에서 최선 1개만 유지
          상한: 남은 distilled가 cap 초과 시 미검증(trial 0)부터 오래된 순 삭제
        """
        with self._get_connection() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT id, intent, ibl_code, success_count, fail_count, avg_ms, avg_tokens, created_at "
                "FROM ibl_examples WHERE source='distilled'"
            ).fetchall()]

        stats = {"distilled": len(rows), "pruned_bad": 0, "deduped": 0,
                 "pruned_cap": 0, "deleted_total": 0}
        if not rows:
            return stats

        to_delete = set()

        # ⑤ 검증 실패 가지치기 (피드백 루프가 살아있어 가능)
        for r in rows:
            if r["fail_count"] >= min_fails_to_prune and r["success_count"] == 0:
                to_delete.add(r["id"])
        stats["pruned_bad"] = len(to_delete)

        by_id = {r["id"]: r for r in rows if r["id"] not in to_delete}
        alive_ids = set(by_id)

        # ③ 근접중복 제거 — union-find
        parent = {i: i for i in alive_ids}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        if self.is_semantic_available():
            for r in by_id.values():
                text = self._prepare_search_text(r["intent"], r["ibl_code"])
                for mid, sim in self.search_semantic(text, top_k=15):
                    if mid != r["id"] and mid in alive_ids and sim >= dup_threshold:
                        union(r["id"], mid)

            groups: Dict[int, List[int]] = {}
            for i in alive_ids:
                groups.setdefault(find(i), []).append(i)
            for g in groups.values():
                if len(g) < 2:
                    continue
                keep = max(g, key=lambda i: self._dedup_quality(by_id[i]))
                for i in g:
                    if i != keep:
                        to_delete.add(i)
                        stats["deduped"] += 1

        # 상한 — 미검증부터 오래된 순
        remaining = [r for r in rows if r["id"] not in to_delete]
        if len(remaining) > cap:
            prunable = sorted(
                [r for r in remaining if (r["success_count"] + r["fail_count"]) == 0],
                key=lambda r: r["created_at"]
            )
            need = len(remaining) - cap
            for r in prunable[:need]:
                to_delete.add(r["id"])
                stats["pruned_cap"] += 1

        if to_delete:
            self._delete_examples(list(to_delete))
        stats["deleted_total"] = len(to_delete)
        return stats

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

    # =========================================================================
    # 렌트 해마 (폰-자아 호스팅 §6) — 로컬 인코더/벡터스토어 없는 몸에서 검색
    # =========================================================================

    @classmethod
    def hippo_disabled(cls) -> bool:
        """해마(연상검색 + 경험증류) 비활성 여부.

        기본 = **렌트 모드**(로컬 인코더 없이 맥 /embed 로 질의 임베딩을 빌리는 몸)이면 비활성.
        렌트는 질의마다 네트워크 왕복이라 시스템 AI 응답을 느리게 하고, 증류(top_score<0.7 시
        LLM 1회 추가)까지 겹친다. → 속도 우선(사용자 결정 2026-06-14). 폰의 로컬 Gemini 는
        ibl_nodes.yaml 전체 어휘를 프롬프트로 가져 용례 없이도 IBL 생성 가능.

        ★capability-gate(프로파일 라벨 분기 아님 — 이음매 위 모듈이라 포크-가드 준수):
        폰(로컬 인코더 없음+맥 렌트)=렌트라 꺼지고, 맥(로컬 인코더)=렌트 아니라 켜지고, 맥 미연결
        폰=렌트 불가→로컬 FTS(빠름)라 켜진다. '폰이라서'가 아니라 '렌트라 느려서' 끈다.
        강제 토글: INDIEBIZ_HIPPO=on(켬)/off(끔). 심층기억 지도(_memory_map_scent=로컬 목차)는 별개."""
        force = (os.environ.get("INDIEBIZ_HIPPO") or "").strip().lower()
        if force in ("on", "1", "true", "yes"):
            return False
        if force in ("off", "0", "false", "no"):
            return True
        return cls._rented_mode()

    @classmethod
    def _has_local_encoder(cls) -> bool:
        """이 몸이 로컬 인코더를 **가졌는가** — 지금 로드돼 있는가가 아니다.

        ★2026-08-23 실측 결함: `_rented_mode` 가 능력을 `is_semantic_available()` 로 물었는데
        그 함수는 *준비 상태*를 답한다(`_load_model` 은 모델이 아직 안 올라왔으면 백그라운드
        로딩을 시작하고 False 를 돌려준다). 그래서 로컬 인코더를 가진 맥에서도 **모델이
        로딩 중인 동안**은 렌트(폰) 몸으로 오인됐고, `hippo_disabled()` 가 참이 되어
        `search_hybrid` 가 맨 앞에서 [] 를 반환했다 — FTS5 폴백까지 가지도 못한 채
        회상이 통째로 0건이 되고 **에러는 하나도 안 났다**.
        실측: 새 프로세스에서 fts5=3건인데 hybrid=0건 / 30개 일상 명령 전부 빈 실행기억.
        영향은 시험만이 아니다 — 백엔드는 코드를 고칠 때마다 리로드되고, 그 직후
        모델 로딩 창(수십 초~수 분) 동안 모든 턴의 연상 단계가 조용히 빈손이 된다.

        능력 질문은 능력으로 답한다: 모델이 올라와 있거나(확정), 로드 시도가 아직
        없었고 모델 폴더가 실재하면 '가졌다'. 시도했는데 없으면 진짜로 없는 것
        (폰·sentence-transformers 미설치·로드 실패) — 그때만 렌트가 옳다.
        """
        if cls._model is not None:
            return True
        if cls._model_load_attempted:
            return False
        try:
            d = Path(cls._resolve_model_dir())
            return (d / "model.safetensors").exists() or (d / "config.json").exists()
        except Exception:
            return False

    @classmethod
    def _rented_mode(cls) -> bool:
        """렌트 모드 여부: 로컬 시맨틱 스택(model+sqlite-vec)이 없고, 정적 인덱스를 로드할 수 있으며,
        질의 임베딩을 빌릴 맥(INDIEBIZ_MAC_URL)이 있을 때. capability 게이트(profile 분기 아님)."""
        if cls.is_semantic_available():
            return False
        if cls._has_local_encoder():
            return False        # 가졌는데 아직 안 올라왔을 뿐 — 렌트가 아니라 폴백이 답이다
        if not (os.environ.get("INDIEBIZ_MAC_URL") or "").strip():
            return False
        return cls._ensure_rented_index()

    @classmethod
    def _ensure_rented_index(cls) -> bool:
        """ibl_hippo_index.json + ibl_hippo_vecs.f32 를 인메모리로 1회 로드(numpy 행렬)."""
        if cls._rented_vecs is not None:
            return True
        if cls._rented_load_attempted:
            return cls._rented_vecs is not None
        cls._rented_load_attempted = True
        try:
            import numpy as np
            base = os.environ.get("INDIEBIZ_BASE_PATH") or str(Path(__file__).resolve().parent.parent.parent)
            data_dir = Path(base) / "data"
            idx = json.loads((data_dir / "ibl_hippo_index.json").read_text(encoding="utf-8"))
            n, dim = idx["count"], idx["dim"]
            raw = (data_dir / "ibl_hippo_vecs.f32").read_bytes()
            vecs = np.frombuffer(raw, dtype=np.float32)
            if vecs.size != n * dim:
                logger.error(f"[IBL 렌트해마] 벡터 크기 불일치: {vecs.size} != {n}x{dim}")
                return False
            cls._rented_vecs = vecs.reshape(n, dim)
            cls._rented_metas = idx["examples"]
            logger.info(f"[IBL 렌트해마] 인덱스 로드: {n}개 x {dim}차원 (질의는 맥 /embed 렌트)")
            return True
        except Exception as e:
            logger.warning(f"[IBL 렌트해마] 인덱스 로드 실패(렌트 검색 비활성): {e}")
            return False

    def _rent_query_vec(self, query: str):
        """맥 /ibl/embed 로 질의 텍스트→768벡터 렌트. 인증=원격 런처 세션(_forward_to_mac 패턴)."""
        mac_url = (os.environ.get("INDIEBIZ_MAC_URL") or "").rstrip("/")
        if not mac_url:
            return None
        import requests
        import numpy as np
        # 맥 세션 캐시 정본(runtime_utils)을 재사용 — 동일 프로세스 전역.
        try:
            from runtime_utils import mac_session_cache as _sess
        except Exception:
            _sess = {"session": None}

        def _post():
            headers = {"Content-Type": "application/json"}
            if _sess.get("session"):
                headers["X-Launcher-Session"] = _sess["session"]
            return requests.post(f"{mac_url}/ibl/embed", json={"text": query},
                                 headers=headers, timeout=20)

        def _login() -> bool:
            pw = os.environ.get("INDIEBIZ_MAC_PASSWORD")
            if not pw:
                return False
            try:
                r = requests.post(f"{mac_url}/launcher/auth/login", json={"password": pw}, timeout=15)
                if r.status_code == 200:
                    sid = (r.json() or {}).get("session_id")
                    if sid:
                        _sess["session"] = sid
                        return True
            except Exception:
                pass
            return False

        try:
            r = _post()
            if r.status_code in (401, 403) and _login():
                r = _post()
            if r.status_code != 200:
                logger.warning(f"[IBL 렌트해마] /embed 실패 HTTP {r.status_code}")
                return None
            vec = (r.json() or {}).get("vector")
            return np.array(vec, dtype=np.float32) if vec else None
        except Exception as e:
            logger.warning(f"[IBL 렌트해마] /embed 호출 실패: {e}")
            return None

    def _search_rented(self, query: str, top_k: int, allowed_nodes: set = None,
                       category: str = None) -> List["UsageExample"]:
        """렌트 모드 검색: 맥 /embed 질의벡터 + 인메모리 brute-force 코사인 → UsageExample.
        벡터·문서 모두 L2 정규화라 dot = 코사인. FTS5 없이 순수 시맨틱(handoff '브루트포스 코사인')."""
        if not self._ensure_rented_index():
            return []
        import numpy as np
        qv = self._rent_query_vec(query)
        if qv is None:
            return []
        sims = self._rented_vecs @ qv  # (count,)
        # over-fetch 후 필터링(노드/카테고리)
        over = min(len(sims), max(top_k * 5, top_k))
        cand = np.argpartition(-sims, over - 1)[:over]
        cand = cand[np.argsort(-sims[cand])]
        results: List[UsageExample] = []
        for i in cand:
            meta = self._rented_metas[int(i)]
            if allowed_nodes:
                ex_nodes = set(meta["nodes"].split(",")) if meta.get("nodes") else set()
                if ex_nodes and not ex_nodes.intersection(allowed_nodes):
                    continue
            if category and meta.get("category") != category:
                continue
            total = meta.get("success_count", 0) + meta.get("fail_count", 0)
            success_rate = (meta["success_count"] / total) if total else -1.0
            results.append(UsageExample(
                id=meta["id"], intent=meta["intent"], ibl_code=meta["ibl_code"],
                nodes=meta.get("nodes", ""), category=meta.get("category", "single"),
                difficulty=meta.get("difficulty", 1),
                score=round(float(sims[int(i)]), 4),
                source=meta.get("source", "synthetic"),
                success_rate=round(success_rate, 2) if total else -1.0,
                avg_ms=float(meta.get("avg_ms", -1.0)),
                avg_tokens=float(meta.get("avg_tokens", -1.0)),
            ))
            if len(results) >= top_k:
                break
        return results

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

        # 해마 비활성(폰 기본): 연상검색 자체를 건너뜀 → 맥 /embed 렌트 왕복 0.
        if self.hippo_disabled():
            return []

        # 캐시 확인
        cache_key = hashlib.md5(
            f"{query}_{top_k}_{alpha}_{allowed_nodes}_{category}".encode()
        ).hexdigest()
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        # 렌트 모드(폰-자아 §6): 로컬 시맨틱 스택이 없으면 맥 /embed 렌트 + 인메모리 brute-force.
        if self._rented_mode():
            results = self._search_rented(query, top_k, allowed_nodes, category)
            self._set_cached(cache_key, results)
            return results

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
                # FTS5 단독 폴백 — raw BM25 점수를 0~1로 정규화하여 일관성 확보
                max_fts = max((s for _, s in fts5_results), default=1.0) or 1.0
                scored = [(idx, s / max_fts) for idx, s in fts5_results]
            elif not fts5_results:
                # 시맨틱 단독 — search_semantic이 이미 0~1로 반환
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
                           source, success_count, fail_count, avg_ms, avg_tokens
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
            # 시도 이력이 없으면 -1.0 sentinel (미검증). 있으면 0~1 성공률.
            # 0.0(전부 실패)과 미검증을 구분해야 연상이 '실패한 사례'를 표시할 수 있다.
            success_rate = (meta['success_count'] / total) if total else -1.0

            results.append(UsageExample(
                id=meta['id'],
                intent=meta['intent'],
                ibl_code=meta['ibl_code'],
                nodes=meta['nodes'],
                category=meta['category'],
                difficulty=meta['difficulty'],
                score=round(float(score), 4),
                source=meta['source'],
                success_rate=round(success_rate, 2) if total else -1.0,
                avg_ms=round(float(meta['avg_ms']), 0) if (meta['avg_ms'] or -1) >= 0 else -1.0,
                avg_tokens=round(float(meta['avg_tokens']), 0) if (meta['avg_tokens'] or -1) >= 0 else -1.0
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


# =============================================================================
# 액션 사용 계수 (전 표면 포함) — 어휘 은퇴·압축 판단의 눈 (2026-08-05)
# =============================================================================
# episode_log(world_pulse.db)는 자율주행(에이전트 채팅) 경로만 기록해, 앱/조종실/
# 원격 표면의 /ibl/execute 직행이 측정 사각지대였다 — "에피소드에 없음"이 "미사용"이
# 아니었다(family_news·icon 등 실사용 반례). 이 계수는 _execute_ibl_unified(전 경로
# 단일 관문, system_tools_ibl.py)에서 매 실행마다 증가한다.
# 집계형(일×노드×액션×origin)이라 크기 유계 — 원문·파라미터는 저장하지 않는다.
# 싱글턴(IBLUsageDB)과 무관한 독립 함수: 임베딩 모델 기계를 안 건드리고, 호출마다
# 짧은 연결(WAL이라 회상 읽기와 경합 없음).

def bump_action_usage(pairs, origin: str):
    """실행된 (node, action) 쌍 목록의 오늘 계수를 각 +1.

    origin: app(앱 표면)/manual(조종실)/web(원격 기타)/agent(인지 파이프라인)/internal.
    관측일 뿐이므로 어떤 실패도 삼킨다 — 실행 경로에 전파 금지."""
    if not pairs:
        return
    try:
        day = datetime.now().strftime("%Y-%m-%d")
        conn = sqlite3.connect(DB_PATH, timeout=2.0)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS action_usage_daily (
                    day TEXT NOT NULL,
                    node TEXT NOT NULL,
                    action TEXT NOT NULL,
                    origin TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (day, node, action, origin)
                )""")
            conn.executemany(
                """INSERT INTO action_usage_daily (day, node, action, origin, count)
                   VALUES (?, ?, ?, ?, 1)
                   ON CONFLICT(day, node, action, origin)
                   DO UPDATE SET count = count + 1""",
                [(day, str(n), str(a), origin or "internal") for n, a in pairs])
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.debug(f"[IBL Usage] 사용 계수 실패(무해): {e}")


def action_usage_summary(days: int = 30) -> List[Dict]:
    """최근 N일 액션별·origin별 사용 합계 (은퇴/압축 감사용 조회)."""
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        conn = sqlite3.connect(DB_PATH, timeout=2.0)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """SELECT node, action, origin, SUM(count) AS uses,
                          MIN(day) AS first_day, MAX(day) AS last_day
                   FROM action_usage_daily WHERE day >= ?
                   GROUP BY node, action, origin
                   ORDER BY uses DESC""", (cutoff,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception:
        return []
