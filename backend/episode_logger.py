"""
episode_logger.py - 에피소드 단위 실행 로그 기록
IndieBiz OS Core

사용자 명령 → 최종 응답까지를 하나의 에피소드로 기록한다.
stdout을 가로채서 에피소드 진행 중 print 출력을 버퍼에 수집하고,
에피소드 종료 시 DB에 저장한다.

★동시성: 에피소드는 **실행 컨텍스트별**로 격리된다(contextvars). 여러 프로젝트 창이
동시에 명령을 내려도(= 여러 asyncio 태스크/executor 스레드가 겹쳐 돌아도) 각자의 버퍼에
담겨 로그·요약이 섞이지 않는다. 한 에피소드가 이벤트루프 스레드(인지 파이프라인)와
executor 스레드(run_stream)에 걸쳐 있어도, executor 디스패치 시 `copy_context()`로
컨텍스트를 넘기면 같은 에피소드 객체로 모인다(api_websocket 의 run_stream submit 참조).

- episode_log: 전체 로그 (최근 1000개만 보존)
- episode_summary: 요약 지표 (영구 보존)
"""

import re
import sys
import sqlite3
import contextvars
from datetime import datetime, timedelta
from pathlib import Path

from runtime_utils import get_base_path

MAX_EPISODES = 1000

# 현재 실행 컨텍스트의 에피소드 — 태스크/스레드 로컬(asyncio 태스크별 격리, copy_context 로 전파).
# 전역 단일 _active/_buffer 를 대체한다(동시 에피소드 충돌·강제종료·교차오염 제거).
_current_episode: contextvars.ContextVar = contextvars.ContextVar(
    "indiebiz_episode", default=None
)


# ── 버퍼 무손실 청소 ──────────────────────────────────────────────────────
# 에피소드 *버퍼에만* 적용한다(터미널 출력은 _original 로 전문 유지 → 라이브 디버깅 무손실).
# ANSI 색상코드와 tqdm 진행바는 *의미 내용이 0* 인 순수 포맷팅이라 빼도 무손실 — 반성/판정
# 에이전트가 궤적을 읽을 때 노이즈에 파묻히지 않게 한다. httpx·라운드 로그 등 '의미적'
# 라인은 실패 진단의 증거일 수 있어 남긴다. 요약 추출기(_extract_and_save_summary)가 의존
# 하는 마커 라인([무의식]/[Gemini] 라운드/score=/latency= 등)은 평문이라 무영향.
_ANSI_RE = re.compile(
    r'\x1b\[[0-9;?]*[ -/]*[@-~]'          # CSI (색상·커서)
    r'|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)'  # OSC (하이퍼링크·타이틀)
    r'|\x1b[@-Z\\-_]'                      # 기타 Fe 이스케이프
)
_PROGRESS_RE = re.compile(r'\d+%\||\bit/s\]|Batches:\s')


def _denoise_for_buffer(text: str) -> str:
    """버퍼 적재용 무손실 청소 — ANSI/OSC 이스케이프 제거 + tqdm 진행바 스팸 제거.

    의미 내용은 보존한다(마커·httpx·에러 라인 그대로). 진행바는 캐리지리턴 갱신이라
    내용이 0 → 통째로 버린다. 이스케이프가 write 청크 경계에 걸려 조각날 수 있으나
    (best-effort) 대부분의 포맷 메시지는 한 청크 안에 온전히 들어온다."""
    text = _ANSI_RE.sub('', text)
    if '\r' in text and _PROGRESS_RE.search(text):
        return ''
    return text


class _Episode:
    """단일 에피소드의 격리 상태 — 컨텍스트별로 하나씩, 자기 버퍼를 소유한다."""
    __slots__ = ("agent", "user_message", "started_at", "buffer", "project_id")

    def __init__(self, agent: str, user_message: str, project_id: str = ""):
        self.agent = agent
        self.user_message = (user_message or "")[:500]
        self.started_at = datetime.now()
        self.buffer = []
        self.project_id = project_id or ""


class EpisodeLogger:
    """stdout을 가로채서 에피소드 단위로 로그를 수집한다(실행 컨텍스트별 격리)."""

    _original_stdout = None
    _original_stderr = None

    @classmethod
    def install(cls):
        """서버 시작 시 1회 호출. stdout/stderr를 래핑 + 자기 스키마 보장."""
        if cls._original_stdout is not None:
            return  # 이미 설치됨
        cls._original_stdout = sys.stdout
        cls._original_stderr = sys.stderr
        sys.stdout = _TeeWriter(cls._original_stdout)
        sys.stderr = _TeeWriter(cls._original_stderr)
        # writer 가 자기 테이블을 소유 — 이전엔 world_pulse._init_pulse_db() 에만 있어,
        # 그게 안 도는 몸(폰 진입점)에선 INSERT 가 조용히 실패했다(테이블 부재).
        # 이제 로거가 직접 보장 → 어느 몸에서든 기록된다(world_pulse 의존 제거).
        _ensure_episode_tables()

    @classmethod
    def start_episode(cls, agent: str, user_message: str, project_id: str = ""):
        """에피소드 시작 — 현재 실행 컨텍스트에 새 에피소드를 건다.

        ★동시 실행은 충돌하지 않는다: contextvar 는 태스크/스레드 로컬이라, 다른 태스크가
        시작한 에피소드는 여기서 보이지 않는다(옛 전역 _active 의 '강제종료' 충돌이 사라짐).
        같은 컨텍스트에 미종료 에피소드가 남아 있으면(이른 return 등 누락) 먼저 박제해 보존한다.

        project_id: 종료 시 조종실 '액티브 프로젝트' 유령 청소용(_finalize). 창닫힘 뒤 thread-hop
        누수 방어 — sysai 청소와 대칭."""
        stale = _current_episode.get(None)
        if stale is not None:
            cls._finalize(stale)  # 같은 컨텍스트의 누락 에피소드 salvage (데이터 보존)
        ep = _Episode(agent, user_message, project_id)
        _current_episode.set(ep)
        # 시작 마커 — contextvar 가 ep 로 설정된 뒤 print → write() 가 ep.buffer 로 캡처
        _msg_preview = (user_message or "")[:80].replace("\n", " ")
        print(f"[Episode START] agent={agent} message={_msg_preview!r}")

    @classmethod
    def end_episode(cls):
        """현재 컨텍스트의 에피소드 종료 → DB 저장 → 요약 추출 → 오래된 것 삭제."""
        ep = _current_episode.get(None)
        if ep is None:
            return
        # 종료 마커 — contextvar 가 아직 ep 라 캡처되어 log_text 에 포함
        _total_ms = int((datetime.now() - ep.started_at).total_seconds() * 1000)
        print(f"[Episode END] agent={ep.agent} total_ms={_total_ms}")
        _current_episode.set(None)  # 컨텍스트 비움(같은 태스크 다음 메시지로 누수 방지)
        cls._finalize(ep)

    @classmethod
    def _finalize(cls, ep: "_Episode"):
        """에피소드 1건을 DB에 저장 + 요약 추출. 컨텍스트 토글과 무관한 순수 저장.

        end_episode 와 start_episode 의 salvage 가 모두 지나는 단일 choke point이므로,
        런 종료 시 조종실 '액티브 프로젝트'의 sysai 유령 등록을 여기서 확정 청소한다.
        (등록/해제 스레드가 달라 _active_work 스레드-키 대칭이 깨지는 누수 방어)."""
        # 저장과 독립적으로 먼저 청소 — 저장이 실패해도 유령은 반드시 사라진다.
        # 등록/해제 스레드가 갈리는 thread-hop(자기반성 턴 등) 누수를 에피소드 END 에서 확정 청소.
        if (ep.agent or "") == "system_ai":
            try:
                from thread_context import clear_sysai_active_work
                clear_sysai_active_work()
            except Exception:
                pass
        else:
            # 프로젝트 런: 이 에피소드의 project_id/agent 로 유령 청소(창닫힘 뒤 busy 오표시 방어).
            # started_at_max = 이 런 시작 이하만 → 같은 프로젝트의 더 나중 동시 런은 보존.
            try:
                from thread_context import clear_project_active_work
                clear_project_active_work(
                    project_id=ep.project_id, agent_name=(ep.agent or ""),
                    started_at_max=ep.started_at.timestamp() + 1.0)
            except Exception:
                pass
        try:
            log_text = "".join(ep.buffer)
            total_ms = int((datetime.now() - ep.started_at).total_seconds() * 1000)
            episode_id = _save_episode(ep.started_at, ep.agent, ep.user_message, log_text, total_ms)
            if episode_id:
                _extract_and_save_summary(episode_id, ep.started_at, ep.agent, ep.user_message, log_text, total_ms)
                _cleanup_old_episodes()
        except Exception as e:
            # 에피소드 기록 실패가 시스템에 영향 주면 안 됨
            if cls._original_stdout:
                cls._original_stdout.write(f"[EpisodeLogger] 저장 실패: {e}\n")


class _TeeWriter:
    """stdout/stderr를 원본 + (현재 컨텍스트의) 에피소드 버퍼 양쪽에 쓰는 래퍼.

    현재 실행 컨텍스트에 에피소드가 걸려 있으면 그 버퍼로만 보낸다 — 동시 실행 중인
    다른 에피소드(다른 컨텍스트)나 에피소드 밖 로그(WorldPulse 등)와 섞이지 않는다."""

    def __init__(self, original):
        self._original = original

    def write(self, text):
        if text:
            self._original.write(text)   # 터미널엔 전문(라이브 디버깅 손실 방지)
            ep = _current_episode.get(None)
            if ep is not None:
                cleaned = _denoise_for_buffer(text)  # 버퍼엔 무손실 청소본
                if cleaned:
                    try:
                        ep.buffer.append(cleaned)
                    except Exception:
                        pass

    def flush(self):
        self._original.flush()

    # io 호환 속성
    @property
    def encoding(self):
        return getattr(self._original, 'encoding', 'utf-8')

    @property
    def errors(self):
        return getattr(self._original, 'errors', 'strict')

    def fileno(self):
        return self._original.fileno()

    def isatty(self):
        return self._original.isatty()

    def readable(self):
        return False

    def writable(self):
        return True

    def seekable(self):
        return False


# ============ DB 함수 ============

def _get_db():
    """world_pulse.db 연결"""
    db_path = get_base_path() / "data" / "world_pulse.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_episode_tables():
    """episode_log / episode_summary 테이블 보장 (idempotent, CREATE IF NOT EXISTS).

    스키마는 world_pulse._init_pulse_db() 의 것과 동일하다. 거기에도 있지만, world_pulse
    가 안 도는 몸(폰)에서도 기록되도록 writer 가 자기 스키마를 직접 보장한다. 둘 다
    IF NOT EXISTS 라 충돌 없음. 에피소드 기록은 몸 독립이므로 이 의존을 끊는 게 맞다."""
    try:
        conn = _get_db()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS episode_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                agent TEXT,
                user_message TEXT,
                log TEXT,
                total_ms INTEGER
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
                evaluation_result TEXT
            );
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        try:
            if EpisodeLogger._original_stdout:
                EpisodeLogger._original_stdout.write(f"[EpisodeLogger] 테이블 보장 실패: {e}\n")
        except Exception:
            pass


def _save_episode(started_at, agent, user_message, log_text, total_ms):
    """에피소드 전체 로그를 DB에 저장. Returns: episode_id"""
    try:
        conn = _get_db()
        cursor = conn.execute(
            """INSERT INTO episode_log (started_at, ended_at, agent, user_message, log, total_ms)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                started_at.isoformat() if started_at else datetime.now().isoformat(),
                datetime.now().isoformat(),
                agent,
                user_message,
                log_text,
                total_ms,
            )
        )
        episode_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return episode_id
    except Exception as e:
        try:
            if EpisodeLogger._original_stdout:
                EpisodeLogger._original_stdout.write(f"[EpisodeLogger] DB 저장 실패: {e}\n")
        except Exception:
            pass
        return None


def _extract_and_save_summary(episode_id, started_at, agent, user_message, log_text, total_ms):
    """로그 텍스트에서 요약 지표를 정규식으로 추출하여 episode_summary에 저장"""

    # 해마 최고 점수 추출
    hippocampus_score = None
    score_matches = re.findall(r'score="([\d.]+)"', log_text)
    if score_matches:
        hippocampus_score = max(float(s) for s in score_matches)

    # 무의식 판정 추출
    # - 분류 마커: [무의식] / [시스템AI 무의식] (분류: EXECUTE|THINK|SESSION_RESET)
    # - Reflex 마커: [연상→실행] / [시스템AI 연상→실행] (Reflex EXECUTE)
    #   Reflex는 무의식 모델을 거치지 않아 로그 마커가 다름.
    unconscious_decision = None
    unc_match = re.search(
        r'\[(?:시스템AI\s*)?(?:무의식|연상→실행)\] (?:Reflex\s+(EXECUTE)|분류:\s*(\w+))',
        log_text,
    )
    if unc_match:
        unconscious_decision = unc_match.group(1) or unc_match.group(2)

    # 의식 소요시간 추출 — ConsciousnessAgent 직후의 Gemini latency
    consciousness_ms = None
    cons_match = re.search(r'\[ConsciousnessAgent\] AI 호출 시작.*?\[ConsciousnessAgent\] AI 응답 수신', log_text, re.DOTALL)
    if cons_match:
        # 해당 구간 내 latency 추출
        latency_match = re.search(r'latency=(\d+)ms', cons_match.group(0))
        if latency_match:
            consciousness_ms = int(latency_match.group(1))

    # 실행 라운드 수 추출
    execution_rounds = None
    round_matches = re.findall(r'\[Gemini\] 라운드 (\d+)/\d+ 시작', log_text)
    # 메인 실행의 라운드 (의식/무의식/평가 라운드는 별도이므로 마지막 값)
    if round_matches:
        execution_rounds = max(int(r) for r in round_matches)

    # 평가 결과 추출 — 평가 루프가 여러 라운드면 마지막 라운드 결과가 최종 결과
    # (재실행 후 ACHIEVED로 통과한 경우 첫 NOT_ACHIEVED만 저장되는 버그 수정)
    evaluation_result = None
    eval_matches = re.findall(r'\[GoalEval\].*?평가 응답: (\w+)', log_text)
    if eval_matches:
        evaluation_result = eval_matches[-1]

    try:
        conn = _get_db()
        conn.execute(
            """INSERT INTO episode_summary
               (episode_id, started_at, agent, user_message,
                hippocampus_score, unconscious_decision, consciousness_ms,
                execution_rounds, total_ms, evaluation_result)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                episode_id,
                started_at.isoformat() if started_at else None,
                agent,
                user_message,
                hippocampus_score,
                unconscious_decision,
                consciousness_ms,
                execution_rounds,
                total_ms,
                evaluation_result,
            )
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _cleanup_old_episodes():
    """episode_log에서 MAX_EPISODES(1000)개 초과 시 오래된 것 삭제 (episode_summary는 유지)"""
    try:
        conn = _get_db()
        count = conn.execute("SELECT COUNT(*) FROM episode_log").fetchone()[0]
        if count > MAX_EPISODES:
            delete_count = count - MAX_EPISODES
            conn.execute(
                "DELETE FROM episode_log WHERE id IN (SELECT id FROM episode_log ORDER BY id ASC LIMIT ?)",
                (delete_count,)
            )
            conn.commit()
        conn.close()
    except Exception:
        pass


# ============ 조회 함수 ============

def get_episode_list(limit: int = 20):
    """최근 에피소드 목록 반환"""
    try:
        conn = _get_db()
        rows = conn.execute(
            """SELECT id, started_at, ended_at, agent,
                      SUBSTR(user_message, 1, 100) as user_message, total_ms
               FROM episode_log ORDER BY id DESC LIMIT ?""",
            (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_episode_journal(limit: int = 30):
    """주행기록계 — 분석 가능한(전체 로그 보존) 에피소드를 요약 지표와 함께 반환.

    episode_log(전체 로그, 최근 1000개 cap) LEFT JOIN episode_summary(지표, 영구)로
    각 주행의 시간·에이전트·요청·해마점수·판단·평가결과·라운드·소요를 한 줄에 담는다.
    분석 스위치가 쓰는 목록이라 log 가 남아있는 episode_log 기준(요약만 남은 옛 주행 제외).
    """
    try:
        conn = _get_db()
        rows = conn.execute(
            """SELECT e.id, e.started_at, e.agent,
                      SUBSTR(e.user_message, 1, 120) as user_message,
                      e.total_ms,
                      s.hippocampus_score, s.unconscious_decision,
                      s.execution_rounds, s.evaluation_result
               FROM episode_log e
               LEFT JOIN episode_summary s ON s.episode_id = e.id
               ORDER BY e.id DESC LIMIT ?""",
            (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_episode_detail(episode_id: int):
    """특정 에피소드의 전체 로그 반환"""
    try:
        conn = _get_db()
        row = conn.execute(
            "SELECT * FROM episode_log WHERE id = ?", (episode_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        return None


def get_episode_summaries(limit: int = 50):
    """에피소드 요약 지표 목록 (영구 보존분)"""
    try:
        conn = _get_db()
        rows = conn.execute(
            """SELECT * FROM episode_summary ORDER BY id DESC LIMIT ?""",
            (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_cognitive_trends(days: int = 7) -> dict:
    """최근 N일 vs 이전 N일 인지 품질 추세 비교 (순수 SQL, AI 비용 0)

    Returns:
        {
            "period": {"recent_days": 7, "compare_days": 7},
            "recent": { episode_count, avg_hippocampus_score, execute_ratio, ... },
            "previous": { ... },
            "trends": { hippocampus, speed, efficiency }
        }
    """
    now = datetime.now()
    recent_start = (now - timedelta(days=days)).isoformat()
    previous_start = (now - timedelta(days=days * 2)).isoformat()
    recent_end = now.isoformat()
    previous_end = recent_start

    def _aggregate(conn, start, end):
        row = conn.execute("""
            SELECT
                COUNT(*) as cnt,
                AVG(hippocampus_score) as avg_hippo,
                AVG(execution_rounds) as avg_rounds,
                AVG(total_ms) as avg_ms
            FROM episode_summary
            WHERE started_at >= ? AND started_at < ?
        """, (start, end)).fetchone()

        # EXECUTE 비율
        unc_row = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN unconscious_decision = 'EXECUTE' THEN 1 ELSE 0 END) as exec_count
            FROM episode_summary
            WHERE started_at >= ? AND started_at < ?
              AND unconscious_decision IS NOT NULL
        """, (start, end)).fetchone()

        # 평가 달성률
        eval_row = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN evaluation_result = 'ACHIEVED' THEN 1 ELSE 0 END) as achieved
            FROM episode_summary
            WHERE started_at >= ? AND started_at < ?
              AND evaluation_result IS NOT NULL
        """, (start, end)).fetchone()

        cnt = row["cnt"] or 0
        unc_total = unc_row["total"] or 0
        eval_total = eval_row["total"] or 0

        return {
            "episode_count": cnt,
            "avg_hippocampus_score": round(row["avg_hippo"], 3) if row["avg_hippo"] else None,
            "execute_ratio": round(unc_row["exec_count"] / unc_total, 3) if unc_total > 0 else None,
            "avg_execution_rounds": round(row["avg_rounds"], 2) if row["avg_rounds"] else None,
            "avg_total_ms": round(row["avg_ms"]) if row["avg_ms"] else None,
            "evaluation_achieved_ratio": round(eval_row["achieved"] / eval_total, 3) if eval_total > 0 else None,
        }

    MIN_DATA = 3  # 추세 판정에 필요한 최소 에피소드 수

    def _judge_trend(recent_val, previous_val, higher_is_better=True, threshold=0.10):
        """두 값 비교 → improving/stable/declining/insufficient_data"""
        if recent_val is None or previous_val is None:
            return "insufficient_data"
        if previous_val == 0:
            return "stable" if recent_val == 0 else "improving"
        ratio = (recent_val - previous_val) / abs(previous_val)
        if higher_is_better:
            if ratio > threshold:
                return "improving"
            elif ratio < -threshold:
                return "declining"
        else:
            if ratio < -threshold:
                return "improving"
            elif ratio > threshold:
                return "declining"
        return "stable"

    try:
        conn = _get_db()
        recent = _aggregate(conn, recent_start, recent_end)
        previous = _aggregate(conn, previous_start, previous_end)
        conn.close()
    except Exception:
        return {
            "period": {"recent_days": days, "compare_days": days},
            "recent": {"episode_count": 0},
            "previous": {"episode_count": 0},
            "trends": {},
        }

    # 데이터 부족 시 추세 판정 스킵
    if recent["episode_count"] < MIN_DATA or previous["episode_count"] < MIN_DATA:
        trends = {
            "hippocampus": "insufficient_data",
            "speed": "insufficient_data",
            "efficiency": "insufficient_data",
        }
    else:
        trends = {
            "hippocampus": _judge_trend(recent["avg_hippocampus_score"], previous["avg_hippocampus_score"], higher_is_better=True),
            "speed": _judge_trend(recent["avg_total_ms"], previous["avg_total_ms"], higher_is_better=False),
            "efficiency": _judge_trend(recent["avg_execution_rounds"], previous["avg_execution_rounds"], higher_is_better=False),
        }

    return {
        "period": {"recent_days": days, "compare_days": days},
        "recent": recent,
        "previous": previous,
        "trends": trends,
    }
