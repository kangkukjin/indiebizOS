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
            source TEXT
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
    """)
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


def record_action_health(node: str, action: str, success: bool, response_ms: int = None,
                         source: str = "usage", channel: str = None, error: str = None):
    """액션 실행 결과를 action_health 테이블에 기록 — 경량, 실패 시 무시"""
    if source == "usage" and _in_test_process():
        source = "test"   # 시험의 의도된 실패를 실사용 통계에서 격리 (B18-1)
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
