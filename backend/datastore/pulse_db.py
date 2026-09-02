"""pulse_db.py — world_pulse.db(의식 DB) 접속·스키마·건강기록 (2026-08-05 감사 ⑦ 후반부).

world_pulse(인지층)에서 이동: DB 경로·스키마 초기화·연결자와, 액션 건강기록의
쓰기(record_action_health)·정리(purge_action_records). ibl_engine(실행 후 기록)과
package_manager(제거 후 정리)가 이 *데이터 쓰기* 때문에 인지층을 import 하던 것이
매듭의 교차층 간선이었다 — 데이터는 데이터층에.
"""
import logging
import sqlite3
from datetime import datetime
from typing import Dict, List

from runtime_utils import get_base_path

logger = logging.getLogger(__name__)

CONSCIOUSNESS_DB_PATH = get_base_path() / "data" / "world_pulse.db"


# ── 알림 발사 원장 (2026-08-23) ──────────────────────────────────────────────
# DDL 을 상수로 한 벌만 둔다: 새 설치(_init_pulse_db)와 기존 설치(_ensure_notify_log 지연
# 마이그레이션)가 같은 스키마를 써야 한다 — 복제하면 한쪽만 늘어나 조용히 갈린다.
# (기존 DB 는 파일이 이미 있어 _init_pulse_db 를 다시 타지 않는다. action_health 의
#  channel·error 컬럼이 지연 마이그레이션으로 들어온 것과 같은 사정.)
_NOTIFY_LOG_DDL = """
    CREATE TABLE IF NOT EXISTS notify_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        type TEXT,
        title TEXT,
        message TEXT,
        emitter TEXT,
        source TEXT NOT NULL DEFAULT 'usage'
    );
    CREATE INDEX IF NOT EXISTS idx_notify_log_ts ON notify_log(timestamp);
"""


def _init_pulse_db():
    """의식 DB 초기화 — pulse_log + self_checks 테이블"""
    conn = sqlite3.connect(str(CONSCIOUSNESS_DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS pulse_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            world TEXT,
            user_state TEXT,
            self_state TEXT,
            status TEXT DEFAULT 'healthy'
        );
        CREATE TABLE IF NOT EXISTS self_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            node TEXT NOT NULL,
            action TEXT NOT NULL,
            success INTEGER DEFAULT 0,
            response_ms INTEGER,
            error_message TEXT,
            data_quality TEXT
        );
        CREATE TABLE IF NOT EXISTS action_health (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node TEXT NOT NULL,
            action TEXT NOT NULL,
            success INTEGER NOT NULL,
            response_ms INTEGER,
            source TEXT NOT NULL DEFAULT 'usage',
            timestamp TEXT NOT NULL,
            channel TEXT,
            error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_action_health_na ON action_health(node, action);
        CREATE INDEX IF NOT EXISTS idx_action_health_ts ON action_health(timestamp);
        CREATE TABLE IF NOT EXISTS episode_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            agent TEXT,
            user_message TEXT,
            log TEXT,
            total_ms INTEGER,
            task_id TEXT,
            run_id TEXT,
            parent_run_id TEXT,
            source TEXT,
            owner TEXT           -- 행의 주인(pid:시작시각) — 고아 회수 판정 (episode_logger)
        );
        CREATE TABLE IF NOT EXISTS episode_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            episode_id INTEGER,
            started_at TEXT NOT NULL,
            agent TEXT,
            user_message TEXT,
            hippocampus_score REAL,
            unconscious_decision TEXT,
            consciousness_ms INTEGER,
            execution_rounds INTEGER,
            total_ms INTEGER,
            evaluation_result TEXT,
            run_id TEXT,
            source TEXT
        );
        CREATE TABLE IF NOT EXISTS trajectory_event (
            run_id TEXT NOT NULL,
            event_seq INTEGER NOT NULL,
            episode_id INTEGER,
            task_id TEXT,
            parent_run_id TEXT,
            ts TEXT NOT NULL,
            kind TEXT NOT NULL,
            data TEXT,
            source TEXT,
            PRIMARY KEY (run_id, event_seq)
        );
        CREATE INDEX IF NOT EXISTS idx_trajectory_episode
            ON trajectory_event(episode_id, event_seq);
        CREATE INDEX IF NOT EXISTS idx_trajectory_task
            ON trajectory_event(task_id, event_seq);
    """ + _NOTIFY_LOG_DDL)
    # 스키마 버전 레지스트리(schema_migrations, 2026-09-02) — 옛 액션명 행 정리 등 자동 따라잡기.
    # 실패 = 예외(반쯤 적용 금지) → 호출한 서브시스템이 boot_status 에 실패로 기록한다.
    import schema_migrations
    schema_migrations.apply(conn, "world_pulse")
    conn.close()


def _get_pulse_db():
    """의식 DB 연결 반환"""
    if not CONSCIOUSNESS_DB_PATH.exists():
        _init_pulse_db()
    conn = sqlite3.connect(str(CONSCIOUSNESS_DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


_AH_COLS_ENSURED = False


def _ensure_action_health_cols(conn):
    """channel·error 컬럼 지연 마이그레이션 (2026-08-21 ③ 조사 — 멱등, 프로세스당 1회).

    channel = 호출 통로('agent'/'app'/'scheduler', thread_context.get_call_channel) —
    §1D 실사용 실패율에서 사용자가 겪은 실패와 앱·배터리를 가른다.
    error = 실패 시 오류문 절단본(300자) — 이게 없어서 ③ 분석의 절반이 막혔다
    (self:time 16% 미해명 부류: 실패 사유가 한 줄도 안 남아 재현 외엔 길이 없었다).
    shape = 결과 봉투의 통화 모양(ibl_envelope.classify_currency — 판정기는 하나, B27-1).
    2026-08-24: fixture 면제 액션(하드웨어·유료 LLM·인자 의존)은 주간 returns 스윕의
    측정 우주 밖이라 선언 드리프트가 영영 안 잡혔다(table:structure 실측). 실사용이
    돌 때마다 모양을 공짜로 적어 그 사각을 닫는다 — 면제는 '합성 실행 면제'일 뿐
    '측정 면제'가 아니게 된다.
    """
    global _AH_COLS_ENSURED
    if _AH_COLS_ENSURED:
        return
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(action_health)")}
        if "channel" not in cols:
            conn.execute("ALTER TABLE action_health ADD COLUMN channel TEXT")
        if "error" not in cols:
            conn.execute("ALTER TABLE action_health ADD COLUMN error TEXT")
        if "shape" not in cols:
            conn.execute("ALTER TABLE action_health ADD COLUMN shape TEXT")
        if "n_items" not in cols:
            # n_items = items 통화의 행 수(2026-09-02, 구성요소 생명주기). "성공했다"와
            # "쓸모가 있었다"는 다르다 — sense:search_local 은 계수 19 에 결과 0 이었다
            # (2026-08-15). 빈 items 성공은 생존 신호가 아니므로 행 수를 함께 적는다.
            conn.execute("ALTER TABLE action_health ADD COLUMN n_items INTEGER")
        _AH_COLS_ENSURED = True
    except Exception:
        pass  # 마이그레이션 실패 시 아래 INSERT 가 구 스키마 폴백으로 감


def _in_test_process() -> bool:
    """이 프로세스가 자기시험인가 — 판정 정본은 runtime_utils.in_test_process().

    ★왜 여기서 위임하나(2026-08-22): 같은 판정이 주행기록(episode_log)에도 필요해졌다.
    복제하면 두 원장의 '시험'이 조용히 다른 뜻으로 갈라진다(어느 쪽이 pytest 를 보고
    어느 쪽이 argv 를 보는지가 드리프트한다) — base 층 한 벌을 함께 부른다.
    B18-1 의 근거·설계 의도는 그 함수의 docstring 에 있다.
    """
    try:
        from runtime_utils import in_test_process
        return in_test_process()
    except Exception:
        return False


def _in_rehearsal() -> bool:
    """이 실행이 리허설(상상 훈련)인가 — 판정 정본은 thread_context.in_rehearsal().

    ★_in_test_process 와 같은 규율(2026-08-23): 판정을 여기에 복제하지 않는다. 복제하면
    '리허설'의 뜻이 원장마다 갈라진다. 근거·설계 의도는 그 함수 위 주석에 있다.
    """
    try:
        from thread_context import in_rehearsal
        return in_rehearsal()
    except Exception:
        return False


def _context_isolation_source() -> str:
    """HTTP body 등 행위자 봉투가 명시한 test/training 출처.

    프로세스 자체가 pytest인지 판정하는 `_in_test_process`와는 독립이다. 외부 검증기는
    pytest 프로세스가 아니므로 origin='test'를 이 경로로 읽어야 실사용으로 새지 않는다.
    """
    try:
        from thread_context import get_isolated_origin
        return get_isolated_origin()
    except Exception:
        return None


# ── 격리 출처 — '의도된 실패'는 몸의 삶이 아니다 ────────────────────────────
# 시험(B18-1)과 리허설(상상 훈련)은 상한·오류·빈손 경로를 *일부러* 밟는다. 그 자국이
# 실사용과 같은 칸에 쌓이면 몸은 자기 삶을 잘못 읽는다. `self_check`(12시간 순찰)은
# **격리하지 않는다** — 그건 몸이 스스로를 실제로 재는 진짜 신호다.
# ★SQL 조각을 여기 한 벌만 둔다: 집계 질의가 두 곳(건강 요약·X-Ray)이라 복제하면
#   한쪽만 갱신돼 같은 액션에 두 성공률이 생긴다(27회차 B27-1 이 가르친 부류).
ISOLATED_SOURCES = ("test", "training")
NOT_ISOLATED_SQL = "COALESCE(source, 'usage') NOT IN ('test', 'training')"


def record_action_health(node: str, action: str, success: bool, response_ms: int = None,
                         source: str = "usage", channel: str = None, error: str = None,
                         shape: str = None, n_items: int = None):
    """액션 실행 결과를 action_health 테이블에 기록 — 경량, 실패 시 무시"""
    if source == "usage" and _in_test_process():
        source = "test"   # 시험의 의도된 실패를 실사용 통계에서 격리 (B18-1)
    elif source == "usage":
        # 외부 HTTP 검증기는 pytest 프로세스가 아니다. body origin(test/training)을
        # actor_context가 복원하므로 그 명시 출처를 그대로 쓴다(B39-2차 수리).
        source = _context_isolation_source() or source
    try:
        conn = _get_pulse_db()
        _ensure_action_health_cols(conn)
        err = (str(error)[:300] if error else None)
        try:
            conn.execute(
                "INSERT INTO action_health (node, action, success, response_ms, source, timestamp, channel, error, shape, n_items) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (node, action, 1 if success else 0, response_ms, source,
                 datetime.now().isoformat(), channel, err, shape, n_items)
            )
        except sqlite3.OperationalError:
            # 구 스키마 폴백 (마이그레이션 실패 시에도 기록 자체는 산다)
            conn.execute(
                "INSERT INTO action_health (node, action, success, response_ms, source, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (node, action, 1 if success else 0, response_ms, source, datetime.now().isoformat())
            )
        conn.commit()
        conn.close()
    except Exception:
        pass  # 기록 실패가 액션 실행에 영향 주면 안 됨


_WF_RUN_ENSURED = False


def _ensure_workflow_run(conn):
    """workflow_run 지연 생성 (멱등, 프로세스당 1회).

    저장 워크플로우는 2026-09-02 까지 **실행 기록이 없었다** — 액션은 action_health 에,
    스크립트는 script_runs 로그에 남는데 워크플로우만 아무 원장이 없어 구성요소 생명주기
    (component_lifecycle)의 측정 밖이었다. 앱(단백질)의 생존 신호가 이 표다.
    action_health 에 node='workflow' 로 섞지 않는 이유: 좀비 청소가 어휘에 없는 (node,
    action) 행을 지우고, returns 스윕이 어휘 계약과 대조한다 — 워크플로우는 낱말이 아니다.
    """
    global _WF_RUN_ENSURED
    if _WF_RUN_ENSURED:
        return
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workflow_run (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id TEXT NOT NULL,
                success INTEGER NOT NULL,
                response_ms INTEGER,
                source TEXT NOT NULL DEFAULT 'usage',
                shape TEXT,
                timestamp TEXT NOT NULL
            )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_workflow_run_id ON workflow_run(workflow_id)")
        _WF_RUN_ENSURED = True
    except Exception:
        pass


def record_workflow_run(workflow_id: str, success: bool, response_ms: int = None,
                        shape: str = None, source: str = "usage"):
    """저장 워크플로우 실행 결과 기록 — 경량, 실패 시 무시. 출처 격리는 action_health 와 같은 규율."""
    if source == "usage" and _in_test_process():
        source = "test"
    elif source == "usage":
        source = _context_isolation_source() or source
    try:
        conn = _get_pulse_db()
        _ensure_workflow_run(conn)
        conn.execute(
            "INSERT INTO workflow_run (workflow_id, success, response_ms, source, shape, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(workflow_id), 1 if success else 0, response_ms, source, shape,
             datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


_NOTIFY_LOG_ENSURED = False


def _ensure_notify_log(conn):
    """notify_log 지연 마이그레이션 (멱등, 프로세스당 1회)."""
    global _NOTIFY_LOG_ENSURED
    if _NOTIFY_LOG_ENSURED:
        return
    try:
        conn.executescript(_NOTIFY_LOG_DDL)
        _NOTIFY_LOG_ENSURED = True
    except Exception:
        pass  # 원장이 없어도 알림 자체는 살아야 한다


def record_notification(kind: str, title: str, message: str, emitter: str = "system"):
    """발사된 알림 한 건을 notify_log 에 남긴다 — 경량, 실패 시 무시.

    왜 원장이 필요한가(2026-08-23 조사에서 실제로 막힌 자리): 알림함은
    notification_manager 의 deque(maxlen=100) 뿐이라 백엔드가 리로드되면 통째로
    사라진다. "이 알림이 자꾸 뜬다"는 물음에 '언제·무엇이·몇 번' 을 아무도 되짚을 수
    없었다 — 전달은 휘발해도 원장은 남는다. 입구가 하나(NotificationManager.create)
    이므로 기록도 한 곳이면 족하다.

    ★컬럼 이름 주의: `source` 는 이 DB 의 다른 원장과 **같은 뜻**(격리 출처
    usage/test/training)이라 NOT_ISOLATED_SQL 이 그대로 걸린다. 알림을 쏜 주체는
    `emitter`(scheduler·messenger·에이전트명 …) — notification 딕셔너리의 'source'
    필드가 이쪽이다. 두 낱말을 한 칸에 겹치면 집계가 조용히 갈린다.
    """
    source = "usage"
    if _in_test_process():
        source = "test"
    else:
        source = _context_isolation_source() or source
    try:
        conn = _get_pulse_db()
        _ensure_notify_log(conn)
        conn.execute(
            "INSERT INTO notify_log (timestamp, type, title, message, emitter, source) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (datetime.now().isoformat(), kind, title, (message or "")[:500], emitter, source)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # 기록 실패가 알림 전달에 영향 주면 안 됨


def purge_action_records(actions: List[str]) -> Dict:
    """제거된 액션의 건강기록을 world_pulse.db에서 삭제한다.

    action_health / self_checks 두 테이블의 `action` 컬럼은 `node:` 없는 **맨
    액션명**(예: 'chart', 'filter')이다. 액션을 제거하고도 이 기록을 남기면
    X-Ray에 존재하지 않는 액션이 계속 비정상으로 표시된다(action_removal.md 5번).
    패키지 제거 경로가 호출한다. 반환: {"action_health": n, "self_checks": n}.
    """
    result = {"action_health": 0, "self_checks": 0}
    names = [a for a in (actions or []) if a]
    if not names:
        return result
    ph = ",".join("?" * len(names))
    try:
        conn = _get_pulse_db()
        for table in ("action_health", "self_checks"):
            try:
                cur = conn.execute(
                    f"DELETE FROM {table} WHERE action IN ({ph})", names
                )
                result[table] = cur.rowcount
            except Exception as e:
                logger.warning(f"[SelfCheck] {table} 정리 실패: {e}")
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"[SelfCheck] 건강기록 정리 실패: {e}")
    return result
