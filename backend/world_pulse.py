"""
world_pulse.py - 세계 상태 감각 모듈
IndieBiz OS Core

하루 한 번 세계의 현재 상태를 스냅샷으로 수집하고 DB에 축적합니다.
에이전트는 대화 시작 시 이 정보를 배경 지식으로 받아 세계 맥락을 알고 대화합니다.

수집 카테고리:
- 경제: 주요 지수, 환율
- 시사: 주요 뉴스 헤드라인
- 기술: 테크 뉴스
- 날씨: 현재 날씨

사용:
    from world_pulse import ensure_today_pulse, get_today_pulse, get_pulse_trend

    # 시스템 기동 시 (오늘치 없으면 수집)
    ensure_today_pulse()

    # 오늘 스냅샷 조회
    pulse = get_today_pulse()

    # 최근 N일 추이
    trend = get_pulse_trend(days=7)
"""

import json
import logging
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

# 수집 중 플래그 (중복 실행 방지)
_collecting = False
_collecting_lock = threading.Lock()

# 설정 캐시
_config_cache: Optional[Dict] = None


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
