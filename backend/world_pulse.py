"""
world_pulse.py - World Pulse 모듈
IndieBiz OS Core

세계/사용자/자기 자신의 상태를 주기적으로 감지하고 축적합니다.

기능:
1. World Pulse 스냅샷: 세계 상태 (경제, 뉴스, 기술, 날씨)
2. World Pulse 수집: 매시간 세계/사용자/자신 상태 업데이트
3. 일일 건강 점검: ibl_health_check.py(정적+fixture+골든) 1회 + RED 면 알림 (AI 0)

사용:
    from world_pulse import ensure_today_pulse, collect_world_pulse, run_daily_health_check

    ensure_today_pulse()        # 시스템 기동 시
    collect_world_pulse()       # 매시간 펄스 수집
    run_daily_health_check()    # IBL 건강 점검 (config 카덴스, 기본 24h=하루 1회)

모듈화:
- world_pulse_collectors.py: 세계/사용자/시스템 데이터 수집, 스냅샷 관리
- world_pulse_health.py: Self-Check, 건강 모니터링, 가이드 파일 생성
"""

import json
import logging
import sqlite3
import threading
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from runtime_utils import get_base_path

logger = logging.getLogger(__name__)

BASE_PATH = get_base_path()
DATA_PATH = BASE_PATH / "data"
PULSE_DB_PATH = DATA_PATH / "world_pulse_db.json"
PULSE_CONFIG_PATH = DATA_PATH / "world_pulse_config.json"
PULSE_GUIDE_PATH = DATA_PATH / "guides" / "world_pulse.md"
CONSCIOUSNESS_DB_PATH = DATA_PATH / "world_pulse.db"

# 설정 캐시
_config_cache: Optional[Dict] = None


# ============================================================
# World Pulse DB (SQLite)
# ============================================================

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
            timestamp TEXT NOT NULL
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
    conn.close()


def _get_pulse_db():
    """의식 DB 연결 반환"""
    if not CONSCIOUSNESS_DB_PATH.exists():
        _init_pulse_db()
    conn = sqlite3.connect(str(CONSCIOUSNESS_DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def _cleanup_old_data():
    """오래된 의식 데이터 정리 (retention_days 기준)"""
    config = _load_config()
    cp_config = config.get("pulse_schedule", {})
    retention = cp_config.get("retention_days", 30)
    cutoff = (datetime.now() - timedelta(days=retention)).isoformat()

    try:
        conn = _get_pulse_db()
        conn.execute("DELETE FROM pulse_log WHERE timestamp < ?", (cutoff,))
        conn.execute("DELETE FROM self_checks WHERE timestamp < ?", (cutoff,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug(f"[WorldPulse] 정리 실패: {e}")


# 오래된 데이터 정리는 하루 한 번이면 충분하다. 확률(random<0.04) 대신
# 마커 파일 기반 결정적 24h 게이트 — 누락도 중복도 없고, 마지막 정리 시각도 남는다.
_CLEANUP_MARKER = DATA_PATH / ".world_pulse_cleanup"
_CLEANUP_INTERVAL_HOURS = 24


def _cleanup_is_due() -> bool:
    """마지막 정리 후 _CLEANUP_INTERVAL_HOURS 경과했는지 (결정적)."""
    try:
        if not _CLEANUP_MARKER.exists():
            return True
        last = datetime.fromisoformat(_CLEANUP_MARKER.read_text(encoding="utf-8").strip())
        return datetime.now() - last >= timedelta(hours=_CLEANUP_INTERVAL_HOURS)
    except Exception:
        return True


def _touch_cleanup_marker():
    try:
        _CLEANUP_MARKER.write_text(datetime.now().isoformat(), encoding="utf-8")
    except Exception:
        pass


# ============================================================
# 설정 관리
# ============================================================

def _load_config() -> Dict:
    """world_pulse_config.json 로드 (캐시 사용)"""
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    default = {
        "enabled": True,
        "location": "Cheongju",
        "economy": {"enabled": True, "symbols": {
            "kospi": "^KS11", "kosdaq": "^KQ11",
            "sp500": "^GSPC", "nasdaq": "^IXIC",
            "usd_krw": "KRW=X", "gold": "GC=F", "wti": "CL=F",
        }},
        "news": {"enabled": True, "query": "오늘 주요 뉴스", "count": 8},
        "tech": {"enabled": True, "query": "AI technology news today", "count": 5},
        "weather": {"enabled": True},
    }

    if PULSE_CONFIG_PATH.exists():
        try:
            _config_cache = json.loads(PULSE_CONFIG_PATH.read_text(encoding="utf-8"))
            return _config_cache
        except Exception as e:
            logger.warning(f"[WorldPulse] 설정 로드 실패, 기본값 사용: {e}")

    _config_cache = default
    return _config_cache


def save_config(config: Dict):
    """설정 저장 및 캐시 갱신"""
    global _config_cache
    PULSE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    PULSE_CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    _config_cache = config
    logger.info("[WorldPulse] 설정 저장 완료")


def get_config() -> Dict:
    """현재 설정 반환 (외부 API용)"""
    return _load_config()


# ============================================================
# 하위 모듈 import (re-export)
# ============================================================

from world_pulse_collectors import (
    _parse_handler_result,
    _collect_economy, _collect_news, _collect_tech_news, _collect_weather,
    collect_snapshot, save_snapshot, get_today_pulse, get_pulse_trend, get_pulse_summary,
    _collect_user_profile, _collect_system_status,
    _collect_user_state, _collect_self_state, _collect_world_delta,
    _load_db, _save_db,
)
from world_pulse_health import (
    generate_guide,
    save_self_check, _check_failure_alerts,
    analyze_failure_patterns,
    get_action_health_summary, get_recent_self_checks, get_system_health,
    run_daily_health_check, run_ibl_health_check,
)


# ============================================================
# 공개 API
# ============================================================

def ensure_today_pulse() -> Dict:
    """오늘의 스냅샷이 없으면 수집하고, 가이드를 갱신합니다.

    시스템 기동 시 호출됩니다.

    Returns:
        {"status": "disabled"} — 설정에서 비활성화
        {"status": "exists"} — 이미 있음
        {"status": "collecting"} — 백그라운드 수집 시작
    """
    config = _load_config()
    if not config.get("enabled", True):
        logger.info("[WorldPulse] 비활성화 상태")
        return {"status": "disabled"}

    # 부팅 시엔 위치+금주일정만 fresh 로 당겨 world_pulse.md 생성 (경제·날씨 수집 폐지).
    try:
        generate_guide()
        logger.info("[WorldPulse] 기동 가이드 생성 완료 (위치+금주일정)")
        return {"status": "generated", "date": date.today().isoformat()}
    except Exception as e:
        logger.error(f"[WorldPulse] 가이드 생성 실패: {e}")
        return {"status": "error", "detail": str(e)}


def execute_world_pulse(action: str, params: dict) -> Any:
    """IBL 액션 엔트리포인트

    [sense:world] — 오늘의 세계 상태 반환 (op=snapshot 기본)
    [sense:world]{op: "trend", days: 7} — 최근 N일 추이 반환
    [sense:world]{op: "refresh"} — 강제 재수집
    (op→내부 action_name 매핑은 ibl_routing._route_system의 world_op 분기에서.)
    """
    if action == "world_pulse":
        # on-demand [sense:world] — 경제·날씨를 즉석 수집(정기 수집은 폐지). 호출 시 fresh.
        snapshot = collect_snapshot()
        if isinstance(snapshot, dict) and "error" not in snapshot:
            save_snapshot(snapshot)
            return snapshot
        return get_today_pulse() or {"message": "세계 상태 수집에 실패했습니다."}

    elif action == "world_trend":
        days = params.get("days", 7)
        trend = get_pulse_trend(int(days))
        if trend:
            return {
                "days_requested": days,
                "days_available": len(trend),
                "trend": trend,
                "summary": get_pulse_summary(int(days)),
            }
        return {"message": "축적된 데이터가 없습니다."}

    elif action == "world_refresh":
        snapshot = collect_snapshot()
        if "error" not in snapshot:
            save_snapshot(snapshot)
            generate_guide()
            return {"status": "refreshed", "snapshot": snapshot}
        return snapshot

    return {"error": f"알 수 없는 world_pulse 액션: {action}"}


def get_world_pulse_for_prompt() -> str:
    """프롬프트 주입용 — 가이드 파일 내용을 반환"""
    if PULSE_GUIDE_PATH.exists():
        content = PULSE_GUIDE_PATH.read_text(encoding="utf-8").strip()
        if content:
            return content
    return ""


# ============================================================
# World Pulse 수집 — 매시간 세계/사용자/자신 상태 업데이트
# ============================================================

def collect_world_pulse() -> Dict:
    """정기 World Pulse — 위치 + 금주 일정만 갱신 (2026-06-28 단순화).

    경제·뉴스·날씨·user_state·self_state 정기 수집 폐지. generate_guide 가
    위치([sense:here])·금주 일정을 매번 fresh 로 당겨 world_pulse.md 를 쓴다.
    (on-demand [sense:world]·계기판 live pull 은 별도 경로로 유지.)
    """
    config = _load_config()
    cp_config = config.get("pulse_schedule", {})
    if not cp_config.get("enabled", True):
        return {"status": "disabled"}

    logger.info("[WorldPulse] 정기 갱신 (위치+금주일정)")
    generate_guide()

    # 오래된 데이터 정리 (하루 한 번, 결정적 게이트)
    if _cleanup_is_due():
        _cleanup_old_data()
        _touch_cleanup_marker()

    return {"status": "ok", "timestamp": datetime.now().isoformat()}


# ============================================================
# Pulse 기록 & 조회
# ============================================================

def save_pulse(pulse: Dict):
    """World Pulse 기록 저장"""
    try:
        conn = _get_pulse_db()
        conn.execute(
            "INSERT INTO pulse_log (timestamp, world, user_state, self_state, status) VALUES (?, ?, ?, ?, ?)",
            (
                pulse["timestamp"],
                json.dumps(pulse.get("world", {}), ensure_ascii=False),
                json.dumps(pulse.get("user_state", {}), ensure_ascii=False),
                json.dumps(pulse.get("self_state", {}), ensure_ascii=False),
                pulse.get("status", "healthy"),
            )
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"[WorldPulse] 펄스 저장 실패: {e}")


def get_recent_pulses(hours: int = 24) -> List[Dict]:
    """최근 N시간 World Pulse 조회"""
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    try:
        conn = _get_pulse_db()
        rows = conn.execute(
            "SELECT * FROM pulse_log WHERE timestamp >= ? ORDER BY id DESC",
            (cutoff,)
        ).fetchall()
        conn.close()
        return [
            {
                "id": r["id"],
                "timestamp": r["timestamp"],
                "world": json.loads(r["world"]) if r["world"] else {},
                "user_state": json.loads(r["user_state"]) if r["user_state"] else {},
                "self_state": json.loads(r["self_state"]) if r["self_state"] else {},
                "status": r["status"],
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning(f"[WorldPulse] 펄스 조회 실패: {e}")
        return []


# ============================================================
# CalendarManager 연동 — 스케줄 등록
# ============================================================

def register_pulse_tasks():
    """CalendarManager에 World Pulse와 자가점검을 등록"""
    global _config_cache
    _config_cache = None  # 설정 캐시 무효화 (새 설정 반영)
    config = _load_config()
    cp_config = config.get("pulse_schedule", {})
    sc_config = config.get("self_check", {})

    try:
        from calendar_manager import get_calendar_manager
        cm = get_calendar_manager()

        # 커스텀 액션 등록
        cm.actions["world_pulse"] = lambda task: collect_world_pulse()
        cm.actions["self_check"] = lambda task: run_daily_health_check()  # 하위 호환 별칭
        cm.actions["ai_health_check"] = lambda task: run_daily_health_check()

        # 기존에 등록된 의식 이벤트가 있는지 확인
        existing = {evt.get("title"): evt for evt in cm.list_events()}

        # 1) World Pulse (매시간)
        if cp_config.get("enabled", True) and "[WorldPulse] 펄스 수집" not in existing:
            interval = cp_config.get("interval_hours", 1)
            cm.add_event(
                title="[WorldPulse] 펄스 수집",
                event_type="schedule",
                repeat="interval",
                interval_hours=interval,
                event_time=datetime.now().strftime("%H:%M"),
                action="world_pulse",
                enabled=True,
                owner_project_id="__system_ai__",
                owner_agent_id="system_ai",
            )
            logger.info(f"[WorldPulse] World Pulse 등록 (매 {interval}시간)")

        # 2) 일일 건강 체크 (카덴스=config self_check.interval_hours, 기본 24h=하루 1회).
        #    run_daily_health_check: 정적 정합성 + items 통화 단언 + 골든 파이프(전부 AI 0) 를
        #    먼저 돌리고, RED 가 있을 때만 SystemAI triage 1턴(§4 배치 원칙). 평상시 AI 비용 0.
        #    이벤트 title 은 호환 위해 유지("AI 건강체크") — 실제론 정적 우선 게이트.
        if sc_config.get("enabled", True):
            interval = sc_config.get("interval_hours", 24)
            _hc_evt = existing.get("[WorldPulse] AI 건강체크")
            if _hc_evt is None:
                next_time = (datetime.now() + timedelta(hours=interval)).strftime("%H:%M")
                cm.add_event(
                    title="[WorldPulse] AI 건강체크",
                    event_type="schedule",
                    repeat="interval",
                    interval_hours=interval,
                    event_time=next_time,
                    action="ai_health_check",
                    enabled=True,
                    owner_project_id="__system_ai__",
                    owner_agent_id="system_ai",
                )
                logger.info(f"[WorldPulse] AI 건강체크 등록 (매 {interval}시간, 다음 실행: {next_time})")
            elif _hc_evt.get("interval_hours") != interval:
                # config 카덴스 변경 반영 — skip-if-exists 드리프트 방지(2026-06-27 12h→24h)
                cm.update_event(_hc_evt.get("id"), interval_hours=interval)
                logger.info(f"[WorldPulse] AI 건강체크 카덴스 갱신 → 매 {interval}시간")

        # 기존 self_check 이벤트가 있으면 비활성화 (하위 호환)
        if "[WorldPulse] 자가점검" in existing:
            for evt in cm.config.get("events", []):
                if evt.get("title") == "[WorldPulse] 자가점검":
                    evt["enabled"] = False
                    break
            cm._save_config()

        # DB 초기화
        _init_pulse_db()

        # 서버 시작 시: 최근 1시간 내 펄스가 없으면 수집
        def _initial_pulse_if_needed():
            try:
                recent = get_recent_pulses(hours=1)
                if recent:
                    logger.info(f"[WorldPulse] 최근 펄스 있음 ({len(recent)}건) — 건너뜀")
                    return
                collect_world_pulse()
                logger.info("[WorldPulse] 최근 펄스 없어서 수집 완료")
            except Exception as e:
                logger.error(f"[WorldPulse] 시작 시 펄스 체크 실패: {e}")
        threading.Thread(target=_initial_pulse_if_needed, daemon=True, name="initial-world-pulse").start()


    except Exception as e:
        logger.error(f"[WorldPulse] 스케줄 등록 실패: {e}")
