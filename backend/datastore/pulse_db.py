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
            source TEXT
        );
    """ + _NOTIFY_LOG_DDL)
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


# ── 격리 출처 — '의도된 실패'는 몸의 삶이 아니다 ────────────────────────────
# 시험(B18-1)과 리허설(상상 훈련)은 상한·오류·빈손 경로를 *일부러* 밟는다. 그 자국이
# 실사용과 같은 칸에 쌓이면 몸은 자기 삶을 잘못 읽는다. `self_check`(12시간 순찰)은
# **격리하지 않는다** — 그건 몸이 스스로를 실제로 재는 진짜 신호다.
# ★SQL 조각을 여기 한 벌만 둔다: 집계 질의가 두 곳(건강 요약·X-Ray)이라 복제하면
#   한쪽만 갱신돼 같은 액션에 두 성공률이 생긴다(27회차 B27-1 이 가르친 부류).
ISOLATED_SOURCES = ("test", "training")
NOT_ISOLATED_SQL = "COALESCE(source, 'usage') NOT IN ('test', 'training')"


def record_action_health(node: str, action: str, success: bool, response_ms: int = None,
                         source: str = "usage", channel: str = None, error: str = None):
    """액션 실행 결과를 action_health 테이블에 기록 — 경량, 실패 시 무시"""
    if source == "usage" and _in_test_process():
        source = "test"   # 시험의 의도된 실패를 실사용 통계에서 격리 (B18-1)
    elif source == "usage" and _in_rehearsal():
        source = "training"   # 리허설의 의도된 실패를 실사용 통계에서 격리 (2026-08-23)
    try:
        conn = _get_pulse_db()
        _ensure_action_health_cols(conn)
        err = (str(error)[:300] if error else None)
        try:
            conn.execute(
                "INSERT INTO action_health (node, action, success, response_ms, source, timestamp, channel, error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (node, action, 1 if success else 0, response_ms, source,
                 datetime.now().isoformat(), channel, err)
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
    elif _in_rehearsal():
        source = "training"
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
