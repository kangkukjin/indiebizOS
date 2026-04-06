"""
episode_logger.py - 에피소드 단위 실행 로그 기록
IndieBiz OS Core

사용자 명령 → 최종 응답까지를 하나의 에피소드로 기록한다.
stdout을 가로채서 에피소드 진행 중 print 출력을 버퍼에 수집하고,
에피소드 종료 시 DB에 저장한다.

- episode_log: 전체 로그 (최근 100개만 보존)
- episode_summary: 요약 지표 (영구 보존)
"""

import re
import sys
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from runtime_utils import get_base_path

MAX_EPISODES = 1000


class EpisodeLogger:
    """stdout을 가로채서 에피소드 단위로 로그를 수집한다."""

    _buffer = []
    _active = False
    _started_at = None
    _agent = None
    _user_message = None
    _original_stdout = None
    _original_stderr = None
    _lock = threading.Lock()

    @classmethod
    def install(cls):
        """서버 시작 시 1회 호출. stdout/stderr를 래핑."""
        if cls._original_stdout is not None:
            return  # 이미 설치됨
        cls._original_stdout = sys.stdout
        cls._original_stderr = sys.stderr
        sys.stdout = _TeeWriter(cls._original_stdout, cls)
        sys.stderr = _TeeWriter(cls._original_stderr, cls)

    @classmethod
    def start_episode(cls, agent: str, user_message: str):
        """에피소드 시작"""
        with cls._lock:
            # 이전 에피소드가 종료되지 않았으면 강제 종료
            if cls._active:
                cls._force_end()
            cls._buffer = []
            cls._active = True
            cls._started_at = datetime.now()
            cls._agent = agent
            cls._user_message = (user_message or "")[:500]

    @classmethod
    def end_episode(cls):
        """에피소드 종료 → DB 저장 → 요약 추출 → 오래된 것 삭제"""
        with cls._lock:
            if not cls._active:
                return
            log_text = "".join(cls._buffer)
            started = cls._started_at
            agent = cls._agent
            user_msg = cls._user_message
            total_ms = int((datetime.now() - started).total_seconds() * 1000) if started else 0
            cls._active = False
            cls._buffer = []

        # DB 저장 (lock 밖에서)
        try:
            episode_id = _save_episode(started, agent, user_msg, log_text, total_ms)
            if episode_id:
                _extract_and_save_summary(episode_id, started, agent, user_msg, log_text, total_ms)
                _cleanup_old_episodes()
        except Exception as e:
            # 에피소드 기록 실패가 시스템에 영향 주면 안 됨
            if cls._original_stdout:
                cls._original_stdout.write(f"[EpisodeLogger] 저장 실패: {e}\n")

    @classmethod
    def _force_end(cls):
        """lock 내부에서 호출 — 미종료 에피소드 강제 저장"""
        if not cls._active:
            return
        log_text = "".join(cls._buffer)
        started = cls._started_at
        agent = cls._agent
        user_msg = cls._user_message
        total_ms = int((datetime.now() - started).total_seconds() * 1000) if started else 0
        cls._active = False
        cls._buffer = []

        # 별도 스레드로 저장 (lock 내부이므로)
        threading.Thread(
            target=lambda: _save_episode(started, agent, user_msg, log_text, total_ms),
            daemon=True
        ).start()


class _TeeWriter:
    """stdout/stderr를 원본 + 에피소드 버퍼 양쪽에 쓰는 래퍼"""

    def __init__(self, original, logger_cls):
        self._original = original
        self._logger = logger_cls

    def write(self, text):
        if text:
            self._original.write(text)
            if self._logger._active:
                try:
                    self._logger._buffer.append(text)
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
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


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

    # 무의식 판정 추출 (프로젝트 에이전트: [무의식], 시스템 AI: [시스템AI 무의식])
    # Reflex EXECUTE (모델 스킵) 패턴과 분류: EXECUTE/THINK 패턴 모두 캡처
    unconscious_decision = None
    unc_match = re.search(r'\[(?:시스템AI\s*)?무의식\] (?:Reflex\s+(EXECUTE)|분류:\s*(\w+))', log_text)
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

    # 평가 결과 추출
    evaluation_result = None
    eval_match = re.search(r'\[GoalEval\].*?평가 응답: (\w+)', log_text)
    if eval_match:
        evaluation_result = eval_match.group(1)

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
    """episode_log에서 100개 초과 시 오래된 것 삭제 (episode_summary는 유지)"""
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
