"""
world_pulse.py - 의식 모듈 (Consciousness Module)
IndieBiz OS Core

세계/사용자/자기 자신의 상태를 주기적으로 감지하고 축적합니다.

기능:
1. World Pulse: 세계 상태 스냅샷 (경제, 뉴스, 기술, 날씨)
2. Consciousness Pulse: 매시간 세계/사용자/자신 상태 업데이트
3. Self-Check: 주기적 IBL 액션 자가 점검 (면역 순찰)

사용:
    from world_pulse import ensure_today_pulse, collect_consciousness_pulse, run_self_check

    ensure_today_pulse()           # 시스템 기동 시
    collect_consciousness_pulse()  # 매시간 의식 펄스
    run_self_check()               # 매 6시간 자가 점검
"""

import json
import logging
import random
import sqlite3
import threading
import time as _time
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
CONSCIOUSNESS_DB_PATH = DATA_PATH / "consciousness_pulse.db"

# 수집 중 플래그 (중복 실행 방지)
_collecting = False
_collecting_lock = threading.Lock()

# 설정 캐시
_config_cache: Optional[Dict] = None


# ============================================================
# Consciousness DB (SQLite)
# ============================================================

def _init_consciousness_db():
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
    """)
    conn.close()


def _get_consciousness_db():
    """의식 DB 연결 반환"""
    if not CONSCIOUSNESS_DB_PATH.exists():
        _init_consciousness_db()
    conn = sqlite3.connect(str(CONSCIOUSNESS_DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def _cleanup_old_data():
    """오래된 의식 데이터 정리 (retention_days 기준)"""
    config = _load_config()
    cp_config = config.get("consciousness_pulse", {})
    retention = cp_config.get("retention_days", 30)
    cutoff = (datetime.now() - timedelta(days=retention)).isoformat()

    try:
        conn = _get_consciousness_db()
        conn.execute("DELETE FROM pulse_log WHERE timestamp < ?", (cutoff,))
        conn.execute("DELETE FROM self_checks WHERE timestamp < ?", (cutoff,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug(f"[Consciousness] 정리 실패: {e}")


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
# DB 관리
# ============================================================

def _load_db() -> Dict:
    """world_pulse_db.json 로드"""
    if PULSE_DB_PATH.exists():
        try:
            return json.loads(PULSE_DB_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[WorldPulse] DB 로드 실패: {e}")
    return {"snapshots": {}}


def _save_db(db: Dict):
    """world_pulse_db.json 저장"""
    PULSE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    PULSE_DB_PATH.write_text(
        json.dumps(db, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


# ============================================================
# 스냅샷 수집
# ============================================================

def _parse_handler_result(raw) -> dict:
    """핸들러 반환값을 dict로 파싱 (문자열이면 JSON 파싱)"""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return {}
    if isinstance(raw, dict):
        return raw
    return {}


def _collect_economy() -> Dict:
    """경제 지표 수집 — 주요 지수, 환율

    yf_stock_price 핸들러 반환 형태:
    {"success": True, "data": {"current_price": 2650.0, "change_percent": -1.2, ...}}
    """
    config = _load_config()
    econ_config = config.get("economy", {})
    if not econ_config.get("enabled", True):
        return {}

    results = {}
    symbols = econ_config.get("symbols", {
        "kospi": "^KS11", "kosdaq": "^KQ11",
        "sp500": "^GSPC", "nasdaq": "^IXIC",
        "usd_krw": "KRW=X", "gold": "GC=F", "wti": "CL=F",
    })

    try:
        from tool_loader import load_tool_handler
        handler = load_tool_handler("yf_stock_price")
        if handler and hasattr(handler, "execute"):
            for label, symbol in symbols.items():
                try:
                    raw = handler.execute("yf_stock_price", {"symbol": symbol}, ".")
                    parsed = _parse_handler_result(raw)

                    # 핸들러는 {"success": True, "data": {...}} 형태로 반환
                    data = parsed.get("data", parsed)

                    price = data.get("current_price")
                    change_pct = data.get("change_percent")

                    if price is not None:
                        results[label] = {
                            "price": price,
                            "change_pct": change_pct,
                        }
                    else:
                        logger.debug(f"[WorldPulse] {label}: price가 없음, 키 목록={list(data.keys())[:10]}")
                except Exception as e:
                    logger.debug(f"[WorldPulse] {label} 조회 실패: {e}")
    except ImportError:
        logger.warning("[WorldPulse] tool_loader import 실패")

    return results


def _collect_news() -> List[str]:
    """주요 뉴스 헤드라인 수집 — 구글 뉴스 검색

    google_news_search 핸들러 반환 형태:
    {"success": True, "query": "...", "count": 10, "results": [{"title": "...", "source": "...", ...}]}
    """
    config = _load_config()
    news_config = config.get("news", {})
    if not news_config.get("enabled", True):
        return []

    query = news_config.get("query", "오늘 주요 뉴스")
    count = news_config.get("count", 8)
    headlines = []

    try:
        from tool_loader import load_tool_handler
        handler = load_tool_handler("google_news_search")
        if handler and hasattr(handler, "execute"):
            raw = handler.execute("google_news_search", {"query": query, "count": count}, ".")
            parsed = _parse_handler_result(raw)

            results = parsed.get("results", [])
            for item in results[:8]:
                if isinstance(item, dict):
                    title = item.get("title", "")
                    source = item.get("source", "")
                    if title:
                        entry = f"{title} ({source})" if source else title
                        headlines.append(entry)
    except Exception as e:
        logger.warning(f"[WorldPulse] 뉴스 수집 실패: {e}")

    return headlines


def _collect_tech_news() -> List[str]:
    """기술 뉴스 수집

    ddgs_search 핸들러 반환 형태:
    {"success": True, "query": "...", "count": 5, "results": [{"title": "...", "snippet": "...", "url": "..."}]}
    """
    config = _load_config()
    tech_config = config.get("tech", {})
    if not tech_config.get("enabled", True):
        return []

    query = tech_config.get("query", "AI technology news today")
    count = tech_config.get("count", 5)
    headlines = []

    try:
        from tool_loader import load_tool_handler
        handler = load_tool_handler("ddgs_search")
        if handler and hasattr(handler, "execute"):
            raw = handler.execute("ddgs_search", {"query": query, "count": count}, ".")
            parsed = _parse_handler_result(raw)

            results = parsed.get("results", [])
            for item in results[:5]:
                if isinstance(item, dict):
                    title = item.get("title", "")
                    if title:
                        headlines.append(title)
    except Exception as e:
        logger.warning(f"[WorldPulse] 기술뉴스 수집 실패: {e}")

    return headlines


def _collect_weather() -> str:
    """날씨 수집 (설정의 location 기준)

    get_api_ninjas_data 핸들러 반환 형태는 API마다 다름.
    weather endpoint: {"temp": 12, "feels_like": 10, "humidity": 55, ...}
    또는 {"success": True, "data": {...}} wrapper 가능
    """
    config = _load_config()
    weather_config = config.get("weather", {})
    if not weather_config.get("enabled", True):
        return ""

    location = config.get("location", "Cheongju")

    try:
        from tool_loader import load_tool_handler
        handler = load_tool_handler("get_api_ninjas_data")
        if handler and hasattr(handler, "execute"):
            raw = handler.execute("get_api_ninjas_data", {
                "endpoint": "weather",
                "city": location
            }, ".")
            parsed = _parse_handler_result(raw)

            # wrapper 형태일 수 있음
            data = parsed.get("data", parsed)

            temp = data.get("temp")
            feels = data.get("feels_like")
            humidity = data.get("humidity")

            if temp is not None:
                parts = [f"{location} {temp}°C"]
                if feels is not None:
                    parts.append(f"체감 {feels}°C")
                if humidity is not None:
                    parts.append(f"습도 {humidity}%")
                return ", ".join(parts)
            else:
                logger.debug(f"[WorldPulse] 날씨 키 목록: {list(data.keys())[:10]}")
    except Exception as e:
        logger.warning(f"[WorldPulse] 날씨 수집 실패: {e}")

    return ""


def collect_snapshot() -> Dict:
    """전체 스냅샷 수집

    Returns:
        {
            "date": "2026-03-08",
            "collected_at": "2026-03-08T09:30:00",
            "economy": {...},
            "news": [...],
            "tech": [...],
            "weather": "..."
        }
    """
    global _collecting
    with _collecting_lock:
        if _collecting:
            return {"error": "이미 수집 중입니다."}
        _collecting = True

    try:
        logger.info("[WorldPulse] 스냅샷 수집 시작")

        snapshot = {
            "date": date.today().isoformat(),
            "collected_at": datetime.now().isoformat(),
            "economy": _collect_economy(),
            "news": _collect_news(),
            "tech": _collect_tech_news(),
            "weather": _collect_weather(),
        }

        logger.info("[WorldPulse] 스냅샷 수집 완료")
        return snapshot

    finally:
        with _collecting_lock:
            _collecting = False


# ============================================================
# 저장 & 조회
# ============================================================

def save_snapshot(snapshot: Dict):
    """스냅샷을 DB에 저장"""
    db = _load_db()
    date_key = snapshot.get("date", date.today().isoformat())
    db["snapshots"][date_key] = snapshot
    _save_db(db)
    logger.info(f"[WorldPulse] 스냅샷 저장: {date_key}")


def get_today_pulse() -> Optional[Dict]:
    """오늘의 스냅샷 반환 (없으면 None)"""
    db = _load_db()
    return db["snapshots"].get(date.today().isoformat())


def get_pulse_trend(days: int = 7) -> List[Dict]:
    """최근 N일간 스냅샷 반환 (날짜 내림차순)"""
    db = _load_db()
    snapshots = db.get("snapshots", {})

    result = []
    for i in range(days):
        d = (date.today() - timedelta(days=i)).isoformat()
        if d in snapshots:
            result.append(snapshots[d])

    return result


def get_pulse_summary(days: int = 7) -> str:
    """최근 N일간 스냅샷을 한 줄 요약 텍스트로 반환 (에이전트용)"""
    trend = get_pulse_trend(days)
    if not trend:
        return "축적된 세계 상태 정보가 없습니다."

    lines = []
    for snap in trend:
        date_str = snap.get("date", "?")
        economy = snap.get("economy", {})
        news = snap.get("news", [])
        weather = snap.get("weather", "")

        # 경제 요약
        econ_parts = []
        for label, data in economy.items():
            if isinstance(data, dict):
                price = data.get("price", "?")
                pct = data.get("change_pct")
                pct_str = f"({pct:+.1f}%)" if isinstance(pct, (int, float)) else ""
                label_kr = {
                    "kospi": "코스피", "kosdaq": "코스닥",
                    "sp500": "S&P500", "nasdaq": "나스닥",
                    "usd_krw": "원/달러", "gold": "금", "wti": "유가"
                }.get(label, label)
                if price and price != "?":
                    econ_parts.append(f"{label_kr} {price}{pct_str}")

        # 뉴스 요약 (상위 3개)
        news_top3 = news[:3] if news else []

        line = f"[{date_str}]"
        if econ_parts:
            line += f"\n  경제: {', '.join(econ_parts)}"
        if news_top3:
            line += f"\n  시사: {' / '.join(news_top3)}"
        if weather:
            line += f"\n  날씨: {weather}"

        lines.append(line)

    return "\n".join(lines)


# ============================================================
# 사용자 프로필 & 시스템 상태 수집
# ============================================================

def _collect_user_profile() -> Dict:
    """설정의 profile 섹션에서 사용자 정보 로드"""
    config = _load_config()
    profile = config.get("profile", {})
    # 비어있지 않은 항목만 반환
    return {k: v for k, v in profile.items() if v and str(v).strip()}


def _collect_system_status() -> Dict:
    """시스템 현재 상태 자동 수집 (간략)"""
    status = {}

    # 1) 프로젝트 & 에이전트 수
    try:
        from project_manager import ProjectManager
        pm = ProjectManager()
        projects = pm.list_projects()
        status["projects"] = len(projects)

        # 에이전트 수 (각 프로젝트의 agents.yaml 합산)
        import yaml
        total_agents = 0
        for proj in projects:
            agents_file = Path(proj.get("path", "")) / "agents.yaml"
            if agents_file.exists():
                try:
                    agents_data = yaml.safe_load(agents_file.read_text(encoding="utf-8"))
                    if isinstance(agents_data, dict):
                        total_agents += len(agents_data.get("agents", []))
                    elif isinstance(agents_data, list):
                        total_agents += len(agents_data)
                except Exception:
                    pass
        status["agents"] = total_agents
    except Exception as e:
        logger.debug(f"[WorldPulse] 프로젝트/에이전트 수집 실패: {e}")

    # 2) 최근 대화 주제 (system_ai_memory에서)
    try:
        from system_ai_memory import get_recent_conversations
        recent = get_recent_conversations(limit=5)
        topics = []
        for conv in recent:
            content = conv.get("content", "") if isinstance(conv, dict) else str(conv)
            if content and conv.get("role") == "user":
                # 첫 30자만
                topic = content[:30].replace("\n", " ").strip()
                if topic:
                    topics.append(topic)
        status["recent_topics"] = topics[:3]
    except Exception as e:
        logger.debug(f"[WorldPulse] 최근 대화 수집 실패: {e}")

    # 3) 오늘 예정 이벤트 (calendar_manager + event_triggers)
    try:
        from calendar_manager import get_calendar_manager
        cm = get_calendar_manager()
        all_events = cm.list_events()
        today_str = date.today().isoformat()
        today_events = []
        for evt in all_events:
            evt_date = evt.get("date", "")
            if evt_date == today_str and evt.get("enabled", True):
                title = evt.get("title", evt.get("name", ""))
                if title:
                    today_events.append(title)
        status["today_events"] = today_events
    except Exception as e:
        logger.debug(f"[WorldPulse] 이벤트 수집 실패: {e}")

    # 4) 디스크 여유 공간
    try:
        import shutil
        usage = shutil.disk_usage(str(BASE_PATH))
        free_gb = round(usage.free / (1024**3), 1)
        status["disk_free_gb"] = free_gb
    except Exception as e:
        logger.debug(f"[WorldPulse] 디스크 정보 수집 실패: {e}")

    return status


# ============================================================
# 가이드 파일 생성
# ============================================================

def generate_guide():
    """world_pulse.md 가이드 파일 생성/갱신

    오늘의 스냅샷 + 최근 추이를 마크다운으로 저장합니다.
    에이전트가 대화 시작 시 이 파일을 읽으면 세계 맥락을 알 수 있습니다.
    """
    today = get_today_pulse()
    if not today:
        return

    lines = [
        "# World Pulse — 오늘의 세계와 나 (자동 주입)",
        f"수집 시각: {today.get('collected_at', '?')[:16]}",
        "",
        "> 이 정보는 대화 시작 시 시스템 프롬프트에 자동 포함됩니다.",
        "> 사용자가 '요즘 세상은 어때', '오늘 경제 상황' 등을 물으면",
        "> 아래 데이터를 바로 활용하여 답하세요.",
        "> [sense:world_refresh]나 search_guide 호출은 불필요합니다.",
        "",
    ]

    # ── 사용자 프로필 ──
    profile = _collect_user_profile()
    if profile:
        lines.append("## 사용자")
        label_map = {"name": "이름", "occupation": "직업", "interests": "관심사", "memo": "메모"}
        for key, val in profile.items():
            label = label_map.get(key, key)
            lines.append(f"- {label}: {val}")
        # location도 포함
        config = _load_config()
        loc = config.get("location", "")
        if loc:
            lines.append(f"- 위치: {loc}")
        lines.append("")

    # ── 시스템 상태 ──
    sys_status = _collect_system_status()
    if sys_status:
        lines.append("## 시스템 상태")
        if "projects" in sys_status:
            agents_str = f", 에이전트 {sys_status['agents']}개" if sys_status.get("agents") else ""
            lines.append(f"- 프로젝트 {sys_status['projects']}개{agents_str} 활성")
        if sys_status.get("recent_topics"):
            topics = " / ".join(sys_status["recent_topics"])
            lines.append(f"- 최근 대화: {topics}")
        if sys_status.get("today_events"):
            events = ", ".join(sys_status["today_events"])
            lines.append(f"- 오늘 예정: {events}")
        else:
            lines.append("- 오늘 예정: 없음")
        if "disk_free_gb" in sys_status:
            lines.append(f"- 저장소 여유: {sys_status['disk_free_gb']}GB")
        lines.append("")

    # ── 사용자 현황 (의식 펄스) ──
    try:
        user_state = _collect_user_state()
        if user_state:
            lines.append("## 사용자 현황")
            conv_count = user_state.get("recent_conversations", 0)
            lines.append(f"- 최근 1시간 대화: {conv_count}건")
            pending = user_state.get("pending_tasks", 0)
            if pending > 0:
                lines.append(f"- 미처리 태스크: {pending}건")
            upcoming = user_state.get("upcoming_events", [])
            if upcoming:
                lines.append(f"- 예정 일정: {', '.join(upcoming)}")
            topics = user_state.get("recent_topics", [])
            if topics:
                lines.append(f"- 최근 주제: {' / '.join(topics)}")
            lines.append("")
    except Exception:
        pass

    # ── 시스템 건강 (의식 펄스) ──
    try:
        self_state = _collect_self_state()
        services = self_state.get("services", {})
        if services:
            lines.append("## 시스템 건강")
            for svc, alive in services.items():
                mark = "정상" if alive else "중단"
                lines.append(f"- {svc}: {mark}")
            # 자가점검 요약
            sc_summary = self_state.get("self_check_summary", {})
            if sc_summary:
                ok_count = sum(1 for v in sc_summary.values() if v.get("success_rate", 0) >= 80)
                lines.append(f"- 자가점검: {ok_count}/{len(sc_summary)}개 액션 정상")
                failing = [k for k, v in sc_summary.items() if v.get("success_rate", 100) < 80]
                if failing:
                    lines.append(f"- 주의 필요: {', '.join(failing)}")
            lines.append("")
    except Exception:
        pass

    # 경제
    economy = today.get("economy", {})
    if economy:
        lines.append("## 경제")
        label_map = {
            "kospi": "코스피", "kosdaq": "코스닥",
            "sp500": "S&P500", "nasdaq": "나스닥",
            "usd_krw": "원/달러", "gold": "금", "wti": "유가"
        }
        for key, data in economy.items():
            if isinstance(data, dict):
                price = data.get("price", "?")
                pct = data.get("change_pct")
                pct_str = f" ({pct:+.1f}%)" if isinstance(pct, (int, float)) else ""
                label = label_map.get(key, key)
                lines.append(f"- {label}: {price}{pct_str}")
        lines.append("")

    # 뉴스
    news = today.get("news", [])
    if news:
        lines.append("## 주요 뉴스")
        for headline in news[:6]:
            lines.append(f"- {headline}")
        lines.append("")

    # 기술
    tech = today.get("tech", [])
    if tech:
        lines.append("## 기술 동향")
        for headline in tech[:4]:
            lines.append(f"- {headline}")
        lines.append("")

    # 날씨
    weather = today.get("weather", "")
    if weather:
        lines.append(f"## 날씨\n{weather}")
        lines.append("")

    # 최근 추이 (경제 지표만 간단히)
    trend = get_pulse_trend(7)
    if len(trend) > 1:
        lines.append("## 최근 추이 (경제)")
        for snap in trend[1:]:  # 오늘 제외, 과거분
            d = snap.get("date", "?")
            econ = snap.get("economy", {})
            parts = []
            for key in ["kospi", "sp500", "usd_krw"]:
                data = econ.get(key, {})
                if isinstance(data, dict) and data.get("price"):
                    pct = data.get("change_pct")
                    pct_str = f"({pct:+.1f}%)" if isinstance(pct, (int, float)) else ""
                    label = {"kospi": "코스피", "sp500": "S&P500", "usd_krw": "원/달러"}.get(key, key)
                    parts.append(f"{label} {data['price']}{pct_str}")
            if parts:
                lines.append(f"- {d}: {', '.join(parts)}")
        lines.append("")

    # 파일 저장
    PULSE_GUIDE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PULSE_GUIDE_PATH.write_text("\n".join(lines), encoding="utf-8")
    logger.info("[WorldPulse] 가이드 파일 갱신 완료")


# ============================================================
# 공개 API
# ============================================================

def ensure_today_pulse() -> Dict:
    """오늘의 스냅샷이 없으면 수집하고, 가이드를 갱신합니다.

    시스템 기동 시 호출됩니다.
    수집은 백그라운드 스레드에서 실행되어 서버 기동을 블로킹하지 않습니다.

    Returns:
        {"status": "disabled"} — 설정에서 비활성화
        {"status": "exists"} — 이미 있음
        {"status": "collecting"} — 백그라운드 수집 시작
    """
    config = _load_config()
    if not config.get("enabled", True):
        logger.info("[WorldPulse] 비활성화 상태")
        return {"status": "disabled"}

    existing = get_today_pulse()
    if existing:
        logger.info("[WorldPulse] 오늘 스냅샷 이미 존재")
        # 가이드 파일은 항상 (재)생성 — 형식 변경 반영 + 파일 누락 방지
        generate_guide()
        return {"status": "exists", "date": date.today().isoformat()}

    # 서버 기동 시 수집 — 가이드 파일 준비를 위해 동기 실행
    # (lifespan 내에서 호출되므로 서버가 요청을 받기 전에 완료됨)
    logger.info("[WorldPulse] 스냅샷 수집 시작 (동기)")
    try:
        snapshot = collect_snapshot()
        if "error" not in snapshot:
            save_snapshot(snapshot)
            generate_guide()
            logger.info("[WorldPulse] 스냅샷 수집 & 가이드 생성 완료")
            return {"status": "collected", "date": date.today().isoformat()}
        else:
            logger.warning(f"[WorldPulse] 수집 실패: {snapshot}")
            return {"status": "error", "detail": snapshot.get("error")}
    except Exception as e:
        logger.error(f"[WorldPulse] 수집 실패: {e}")
        return {"status": "error", "detail": str(e)}


def execute_world_pulse(action: str, params: dict) -> Any:
    """IBL 액션 엔트리포인트

    [sense:world_pulse] — 오늘의 세계 상태 반환
    [sense:world_trend]{days: 7} — 최근 N일 추이 반환
    [sense:world_refresh] — 강제 재수집
    """
    if action == "world_pulse":
        pulse = get_today_pulse()
        if pulse:
            return pulse
        # 없으면 수집 시도
        result = ensure_today_pulse()
        if result.get("status") == "collecting":
            return {"message": "세계 상태를 수집 중입니다. 잠시 후 다시 조회해주세요."}
        return get_today_pulse() or {"message": "아직 수집된 데이터가 없습니다."}

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
    """프롬프트 주입용 — 가이드 파일 내용을 반환

    대화 시작 시 prompt_builder가 호출합니다.
    가이드 파일이 없거나 비어있으면 빈 문자열을 반환합니다.
    """
    if PULSE_GUIDE_PATH.exists():
        content = PULSE_GUIDE_PATH.read_text(encoding="utf-8").strip()
        if content:
            return content
    return ""


# ============================================================
# Consciousness Pulse — 매시간 세계/사용자/자신 상태 업데이트
# ============================================================

def _collect_user_state() -> Dict:
    """사용자 상태 수집 (DB 쿼리만, API 호출 없음)"""
    state = {}

    # 1) 최근 1시간 대화 수 및 주제
    try:
        from system_ai_memory import get_recent_conversations
        recent = get_recent_conversations(limit=20)
        one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
        recent_convs = [c for c in recent
                        if isinstance(c, dict) and c.get("timestamp", "") >= one_hour_ago]
        state["recent_conversations"] = len(recent_convs)

        topics = []
        for c in recent_convs:
            if c.get("role") == "user":
                topic = c.get("content", "")[:40].replace("\n", " ").strip()
                if topic:
                    topics.append(topic)
        state["recent_topics"] = topics[:3]
    except Exception as e:
        logger.debug(f"[Consciousness] 대화 수집 실패: {e}")

    # 2) 미처리 메시지 (시스템 AI 태스크)
    try:
        from system_ai_memory import get_pending_tasks
        tasks = get_pending_tasks()
        state["pending_tasks"] = len(tasks) if tasks else 0
    except Exception as e:
        logger.debug(f"[Consciousness] 태스크 수집 실패: {e}")
        state["pending_tasks"] = 0

    # 3) 다가오는 일정
    try:
        from calendar_manager import get_calendar_manager
        cm = get_calendar_manager()
        all_events = cm.list_events()
        now = datetime.now()
        upcoming = []
        for evt in all_events:
            if not evt.get("enabled", True):
                continue
            evt_date = evt.get("date", "")
            evt_time = evt.get("time", "")
            if evt_date == now.strftime("%Y-%m-%d") and evt_time > now.strftime("%H:%M"):
                upcoming.append(evt.get("title", ""))
        state["upcoming_events"] = upcoming[:5]
    except Exception as e:
        logger.debug(f"[Consciousness] 일정 수집 실패: {e}")

    return state


def _collect_self_state() -> Dict:
    """시스템 자기 상태 (내부 체크만, API 호출 없음)"""
    state = {}

    # 1) 서비스 alive 체크
    services = {}
    try:
        from calendar_manager import get_calendar_manager
        cm = get_calendar_manager()
        services["scheduler"] = cm.is_running()
    except Exception:
        services["scheduler"] = False

    try:
        from channel_poller import get_channel_poller
        poller = get_channel_poller()
        services["channel_poller"] = poller.running if hasattr(poller, "running") else False
    except Exception:
        services["channel_poller"] = False

    try:
        from system_ai_runner import SystemAIRunner
        instance = SystemAIRunner.get_instance()
        services["system_ai_runner"] = instance.running if instance else False
    except Exception:
        services["system_ai_runner"] = False

    state["services"] = services

    # 2) 디스크 여유 공간
    try:
        import shutil
        usage = shutil.disk_usage(str(BASE_PATH))
        state["disk_free_gb"] = round(usage.free / (1024**3), 1)
    except Exception:
        pass

    # 3) 최근 자가점검 결과 요약
    try:
        summary = get_action_health_summary()
        state["self_check_summary"] = summary
    except Exception:
        pass

    return state


def _collect_world_delta() -> Dict:
    """세계 변화분 수집 (경량 버전 — 경제 + 날씨만)"""
    delta = {}

    # 경제 지표 (매시간)
    economy = _collect_economy()
    if economy:
        delta["economy"] = economy

    # 날씨 (매시간)
    weather = _collect_weather()
    if weather:
        delta["weather"] = weather

    # 뉴스는 설정된 간격으로만 (기본 6시간)
    config = _load_config()
    cp_config = config.get("consciousness_pulse", {})
    news_interval = cp_config.get("world_news_interval_hours", 6)

    should_collect_news = False
    try:
        conn = _get_consciousness_db()
        row = conn.execute(
            "SELECT timestamp FROM pulse_log WHERE world LIKE '%news%' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row:
            last_news = datetime.fromisoformat(row[0])
            elapsed = (datetime.now() - last_news).total_seconds() / 3600
            should_collect_news = elapsed >= news_interval
        else:
            should_collect_news = True
    except Exception:
        should_collect_news = True

    if should_collect_news:
        news = _collect_news()
        if news:
            delta["news"] = news
        tech = _collect_tech_news()
        if tech:
            delta["tech"] = tech

    return delta


def collect_consciousness_pulse() -> Dict:
    """매시간 의식 펄스 수집 — 세계/사용자/자신 통합"""
    config = _load_config()
    cp_config = config.get("consciousness_pulse", {})
    if not cp_config.get("enabled", True):
        return {"status": "disabled"}

    logger.info("[Consciousness] 의식 펄스 수집 시작")

    pulse = {
        "timestamp": datetime.now().isoformat(),
        "world": _collect_world_delta(),
        "user_state": _collect_user_state(),
        "self_state": _collect_self_state(),
    }

    # 상태 판정
    services = pulse["self_state"].get("services", {})
    all_alive = all(services.values()) if services else True
    pulse["status"] = "healthy" if all_alive else "degraded"

    # DB 저장
    save_pulse(pulse)

    # 가이드 파일 갱신 (세계 스냅샷도 갱신)
    world = pulse["world"]
    if world.get("economy"):
        # 오늘의 daily 스냅샷도 갱신
        today = get_today_pulse()
        if today:
            today["economy"] = world["economy"]
            if world.get("weather"):
                today["weather"] = world["weather"]
            if world.get("news"):
                today["news"] = world["news"]
            if world.get("tech"):
                today["tech"] = world["tech"]
            today["collected_at"] = datetime.now().isoformat()
            save_snapshot(today)

    generate_guide()

    # 오래된 데이터 정리 (낮은 빈도로)
    if random.random() < 0.04:  # ~하루에 한번
        _cleanup_old_data()

    logger.info(f"[Consciousness] 의식 펄스 완료: {pulse['status']}")
    return pulse


def save_pulse(pulse: Dict):
    """의식 펄스 기록 저장"""
    try:
        conn = _get_consciousness_db()
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
        logger.warning(f"[Consciousness] 펄스 저장 실패: {e}")


def get_recent_pulses(hours: int = 24) -> List[Dict]:
    """최근 N시간 의식 펄스 조회"""
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    try:
        conn = _get_consciousness_db()
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
        logger.warning(f"[Consciousness] 펄스 조회 실패: {e}")
        return []


# ============================================================
# Self-Check — 주기적 IBL 액션 자가 점검 (면역 순찰)
# ============================================================

def _get_safe_actions() -> List[Dict]:
    """부작용 없는 안전한 테스트용 액션 목록"""
    config = _load_config()
    sc_config = config.get("self_check", {})
    safe_nodes = sc_config.get("safe_nodes", ["sense"])
    excluded = set(sc_config.get("excluded_actions", ["world_refresh"]))

    actions = []
    try:
        from ibl_engine import list_actions
        for node in safe_nodes:
            for action_info in list_actions(node):
                name = action_info.get("action", "")
                if name and name not in excluded:
                    actions.append({"node": node, "action": name, **action_info})
    except Exception as e:
        logger.warning(f"[SelfCheck] 액션 목록 조회 실패: {e}")

    return actions


def _evaluate_result(result, elapsed_ms: int) -> Dict:
    """LLM 없이 결과 평가"""
    is_error = isinstance(result, dict) and "error" in result
    is_empty = (result is None or result == "" or result == {} or result == [])

    if is_error:
        return {
            "success": False,
            "response_ms": elapsed_ms,
            "data_quality": "error",
            "error_message": str(result.get("error", ""))[:200],
        }
    elif is_empty:
        return {
            "success": True,
            "response_ms": elapsed_ms,
            "data_quality": "empty",
            "error_message": None,
        }
    else:
        return {
            "success": True,
            "response_ms": elapsed_ms,
            "data_quality": "ok",
            "error_message": None,
        }


def run_self_check() -> Dict:
    """랜덤 IBL 액션 자가 점검 (면역 순찰)"""
    config = _load_config()
    sc_config = config.get("self_check", {})
    if not sc_config.get("enabled", True):
        return {"status": "disabled"}

    actions_per_check = sc_config.get("actions_per_check", 2)
    failure_threshold = sc_config.get("failure_alert_threshold", 3)

    safe_actions = _get_safe_actions()
    if not safe_actions:
        return {"status": "no_safe_actions"}

    # 랜덤 선택
    selected = random.sample(safe_actions, min(actions_per_check, len(safe_actions)))
    results = []

    for action_info in selected:
        node = action_info["node"]
        action = action_info["action"]

        logger.info(f"[SelfCheck] 점검 중: [{node}:{action}]")

        start = _time.time()
        try:
            from ibl_engine import execute_ibl
            result = execute_ibl(
                {"_node": node, "action": action, "params": {}},
                ".",
                agent_id="__self_check__"
            )
        except Exception as e:
            result = {"error": str(e)}

        elapsed_ms = int((_time.time() - start) * 1000)
        evaluation = _evaluate_result(result, elapsed_ms)
        evaluation["node"] = node
        evaluation["action"] = action

        # DB 저장
        save_self_check(evaluation)
        results.append(evaluation)

        logger.info(
            f"[SelfCheck] [{node}:{action}] "
            f"{'OK' if evaluation['success'] else 'FAIL'} "
            f"({elapsed_ms}ms, {evaluation['data_quality']})"
        )

    # 연속 실패 알림 체크
    _check_failure_alerts(failure_threshold)

    return {
        "status": "completed",
        "checked": len(results),
        "results": results,
    }


def save_self_check(result: Dict):
    """자가점검 결과 저장"""
    try:
        conn = _get_consciousness_db()
        conn.execute(
            "INSERT INTO self_checks (timestamp, node, action, success, response_ms, error_message, data_quality) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now().isoformat(),
                result.get("node", ""),
                result.get("action", ""),
                1 if result.get("success") else 0,
                result.get("response_ms"),
                result.get("error_message"),
                result.get("data_quality"),
            )
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"[SelfCheck] 저장 실패: {e}")


def _check_failure_alerts(threshold: int = 3):
    """연속 실패 액션 감지 및 알림"""
    try:
        conn = _get_consciousness_db()
        # 각 액션의 최근 N회 결과 확인
        rows = conn.execute("""
            SELECT node, action, GROUP_CONCAT(success) as recent
            FROM (
                SELECT node, action, success,
                       ROW_NUMBER() OVER (PARTITION BY node, action ORDER BY id DESC) as rn
                FROM self_checks
            ) WHERE rn <= ?
            GROUP BY node, action
        """, (threshold,)).fetchall()
        conn.close()

        failing = []
        for row in rows:
            recent = row["recent"]  # e.g. "0,0,0"
            if recent:
                successes = [int(x) for x in recent.split(",")]
                if len(successes) >= threshold and all(s == 0 for s in successes):
                    failing.append(f"[{row['node']}:{row['action']}]")

        if failing:
            try:
                from notification_manager import get_notification_manager
                nm = get_notification_manager()
                nm.create(
                    title="자가점검 경고",
                    message=f"연속 {threshold}회 실패: {', '.join(failing)}",
                    type="warning",
                    source="self_check"
                )
            except Exception as e:
                logger.warning(f"[SelfCheck] 알림 발송 실패: {e}")
    except Exception as e:
        logger.debug(f"[SelfCheck] 실패 알림 체크 오류: {e}")


def get_action_health_summary() -> Dict:
    """액션별 건강 상태 요약"""
    try:
        conn = _get_consciousness_db()
        rows = conn.execute("""
            SELECT node, action,
                   COUNT(*) as total,
                   SUM(success) as successes,
                   AVG(response_ms) as avg_ms
            FROM self_checks
            WHERE timestamp >= ?
            GROUP BY node, action
        """, ((datetime.now() - timedelta(days=7)).isoformat(),)).fetchall()
        conn.close()

        summary = {}
        for row in rows:
            key = f"{row['node']}:{row['action']}"
            total = row["total"]
            successes = row["successes"] or 0
            summary[key] = {
                "total": total,
                "success_rate": round(successes / total * 100, 1) if total > 0 else 0,
                "avg_response_ms": round(row["avg_ms"]) if row["avg_ms"] else None,
            }
        return summary
    except Exception as e:
        logger.debug(f"[SelfCheck] 요약 조회 실패: {e}")
        return {}


def get_recent_self_checks(limit: int = 20) -> List[Dict]:
    """최근 자가점검 결과 조회"""
    try:
        conn = _get_consciousness_db()
        rows = conn.execute(
            "SELECT * FROM self_checks ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"[SelfCheck] 조회 실패: {e}")
        return []


def get_system_health() -> Dict:
    """시스템 전체 건강 요약 — API용"""
    self_state = _collect_self_state()
    health_summary = get_action_health_summary()
    recent_pulses = get_recent_pulses(hours=6)

    # 전체 상태 판정
    services = self_state.get("services", {})
    all_services_ok = all(services.values()) if services else True

    # 자가점검 성공률
    if health_summary:
        avg_rate = sum(v["success_rate"] for v in health_summary.values()) / len(health_summary)
    else:
        avg_rate = 100.0

    if not all_services_ok:
        overall = "degraded"
    elif avg_rate < 80:
        overall = "warning"
    else:
        overall = "healthy"

    return {
        "overall": overall,
        "services": services,
        "disk_free_gb": self_state.get("disk_free_gb"),
        "self_check_avg_success_rate": round(avg_rate, 1),
        "self_check_actions": health_summary,
        "pulse_count_6h": len(recent_pulses),
        "last_pulse": recent_pulses[0]["timestamp"] if recent_pulses else None,
    }


# ============================================================
# CalendarManager 연동 — 스케줄 등록
# ============================================================

def register_consciousness_tasks():
    """CalendarManager에 의식 펄스와 자가점검을 등록"""
    global _config_cache
    _config_cache = None  # 설정 캐시 무효화 (새 설정 반영)
    config = _load_config()
    cp_config = config.get("consciousness_pulse", {})
    sc_config = config.get("self_check", {})

    try:
        from calendar_manager import get_calendar_manager
        cm = get_calendar_manager()

        # 커스텀 액션 등록
        cm.actions["consciousness_pulse"] = lambda task: collect_consciousness_pulse()
        cm.actions["self_check"] = lambda task: run_self_check()

        # 기존에 등록된 의식 이벤트가 있는지 확인
        existing = {evt.get("title"): evt for evt in cm.list_events()}

        # 1) 의식 펄스 (매시간)
        if cp_config.get("enabled", True) and "[Consciousness] 의식 펄스" not in existing:
            interval = cp_config.get("interval_hours", 1)
            cm.add_event(
                title="[Consciousness] 의식 펄스",
                event_type="schedule",
                repeat="interval",
                interval_hours=interval,
                event_time=datetime.now().strftime("%H:%M"),
                action="consciousness_pulse",
                enabled=True,
                owner_project_id="__system_ai__",
                owner_agent_id="system_ai",
            )
            logger.info(f"[Consciousness] 의식 펄스 등록 (매 {interval}시간)")

        # 2) 자가점검 (매 6시간)
        if sc_config.get("enabled", True) and "[Consciousness] 자가점검" not in existing:
            interval = sc_config.get("interval_hours", 6)
            cm.add_event(
                title="[Consciousness] 자가점검",
                event_type="schedule",
                repeat="interval",
                interval_hours=interval,
                event_time=datetime.now().strftime("%H:%M"),
                action="self_check",
                enabled=True,
                owner_project_id="__system_ai__",
                owner_agent_id="system_ai",
            )
            logger.info(f"[Consciousness] 자가점검 등록 (매 {interval}시간)")

        # DB 초기화
        _init_consciousness_db()

        # 서버 시작 시: 최근 1시간 내 펄스가 없으면 수집
        import threading
        def _initial_pulse_if_needed():
            try:
                recent = get_recent_pulses(hours=1)
                if recent:
                    logger.info(f"[Consciousness] 최근 펄스 있음 ({len(recent)}건) — 건너뜀")
                    return
                collect_consciousness_pulse()
                logger.info("[Consciousness] 최근 펄스 없어서 수집 완료")
            except Exception as e:
                logger.error(f"[Consciousness] 시작 시 펄스 체크 실패: {e}")
        threading.Thread(target=_initial_pulse_if_needed, daemon=True, name="initial-consciousness").start()

    except Exception as e:
        logger.error(f"[Consciousness] 스케줄 등록 실패: {e}")
