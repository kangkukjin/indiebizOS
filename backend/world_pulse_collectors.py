"""
world_pulse_collectors.py - World Pulse 수집 함수 모듈

world_pulse.py에서 분리된 데이터 수집/저장/조회 함수들을 포함합니다.

수집 대상:
- 경제 지표 (yfinance)
- 뉴스/기술 뉴스 (google_news, ddgs)
- 날씨 (api_ninjas)
- 사용자 상태 (대화, 일정)
- 시스템 상태 (서비스 alive, 디스크)
- 세계 변화분 (경제+날씨+뉴스 통합)
"""

import json
import logging
import threading
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from runtime_utils import get_base_path

logger = logging.getLogger(__name__)

BASE_PATH = get_base_path()
DATA_PATH = BASE_PATH / "data"

# world_pulse 모듈에서 경로/DB 접근이 필요한 경우 lazy import
# from world_pulse import _load_config, PULSE_DB_PATH, CONSCIOUSNESS_DB_PATH, _get_pulse_db

# 수집 중 플래그 (중복 실행 방지)
_collecting = False
_collecting_lock = threading.Lock()


# ============================================================
# DB 관리
# ============================================================

def _load_db() -> Dict:
    """world_pulse_db.json 로드"""
    from world_pulse import PULSE_DB_PATH
    if PULSE_DB_PATH.exists():
        try:
            return json.loads(PULSE_DB_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[WorldPulse] DB 로드 실패: {e}")
    return {"snapshots": {}}


def _save_db(db: Dict):
    """world_pulse_db.json 저장"""
    from world_pulse import PULSE_DB_PATH
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
    from world_pulse import _load_config
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
                        # 실제 데이터 날짜 추출 (prices 배열의 마지막 거래일)
                        prices = data.get("prices", [])
                        data_date = prices[-1].get("date", "") if prices else ""
                        results[label] = {
                            "price": price,
                            "change_pct": change_pct,
                            "data_date": data_date,
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
    from world_pulse import _load_config
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
    from world_pulse import _load_config
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
    from world_pulse import _load_config
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
                    data_date = data.get("data_date", "")
                    date_tag = f"[{data_date}]" if data_date else ""
                    econ_parts.append(f"{label_kr} {price}{pct_str}{date_tag}")

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
    from world_pulse import _load_config
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

    # 2) 최근 대화 주제 (전체 프로젝트 + 시스템 AI)
    try:
        all_topics = []

        # 시스템 AI
        from system_ai_memory import get_recent_conversations
        for conv in get_recent_conversations(limit=5):
            content = conv.get("content", "") if isinstance(conv, dict) else str(conv)
            if content and conv.get("role") == "user":
                topic = content[:30].replace("\n", " ").strip()
                if topic:
                    all_topics.append({"topic": topic, "project": "시스템 AI", "ts": conv.get("timestamp", "")})

        # 프로젝트별
        from project_manager import ProjectManager
        from conversation_db import ConversationDB
        _pm = ProjectManager()
        for proj in _pm.list_projects():
            try:
                proj_path = pm.projects_path / proj.get("id", "")
                db_path = proj_path / "conversations.db"
                if not db_path.exists():
                    continue
                db = ConversationDB(str(db_path))
                conn = db._get_conn()
                rows = conn.execute(
                    "SELECT content, timestamp FROM messages WHERE role='user' ORDER BY timestamp DESC LIMIT 2"
                ).fetchall()
                for row in rows:
                    topic = (row[0] or "")[:30].replace("\n", " ").strip()
                    if topic:
                        all_topics.append({"topic": topic, "project": proj.get("name", ""), "ts": row[1] or ""})
            except Exception:
                continue

        all_topics.sort(key=lambda x: x.get("ts", ""), reverse=True)
        status["recent_topics"] = [f"{t['topic']} ({t['project']})" for t in all_topics[:3]]
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
# World Pulse 수집 — 사용자/자기 상태
# ============================================================

def _collect_user_state() -> Dict:
    """사용자 상태 수집 (DB 쿼리만, API 호출 없음)"""
    state = {}

    # 1) 모든 프로젝트 + 시스템 AI에서 최근 대화 수집
    try:
        all_recent = []

        # 시스템 AI 대화
        from system_ai_memory import get_recent_conversations
        for c in get_recent_conversations(limit=5):
            if isinstance(c, dict) and c.get("role") == "user":
                all_recent.append({
                    "project": "시스템 AI",
                    "content": c.get("content", "")[:40].replace("\n", " ").strip(),
                    "timestamp": c.get("timestamp", ""),
                })

        # 프로젝트별 대화
        from project_manager import ProjectManager
        from conversation_db import ConversationDB
        pm = ProjectManager()
        for proj in pm.list_projects():
            try:
                proj_path = pm.projects_path / proj.get("id", "")
                db_path = proj_path / "conversations.db"
                if not db_path.exists():
                    continue
                db = ConversationDB(str(db_path))
                # 최근 user 메시지를 가져오기 위해 직접 쿼리
                conn = db._get_conn()
                rows = conn.execute(
                    "SELECT content, timestamp FROM messages WHERE role='user' ORDER BY timestamp DESC LIMIT 3"
                ).fetchall()
                for row in rows:
                    content = (row[0] or "")[:40].replace("\n", " ").strip()
                    if content:
                        all_recent.append({
                            "project": proj.get("name", proj.get("id", "")),
                            "content": content,
                            "timestamp": row[1] or "",
                        })
            except Exception:
                continue

        # 시간순 정렬 후 최근 3개
        all_recent.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
        recent_in_hour = [r for r in all_recent if r.get("timestamp", "") >= one_hour_ago]

        state["recent_conversations"] = len(recent_in_hour)
        state["recent_topics"] = [
            f"{r['content']} ({r['project']})" for r in all_recent[:3]
        ]
    except Exception as e:
        logger.debug(f"[WorldPulse] 대화 수집 실패: {e}")

    # 2) 다가오는 일정
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
        logger.debug(f"[WorldPulse] 일정 수집 실패: {e}")

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
        from world_pulse import get_action_health_summary
        summary = get_action_health_summary()
        state["self_check_summary"] = summary
    except Exception:
        pass

    # ============================================================
    # Digital Proprioception (실시간 body schema)
    # ============================================================
    proprioception = {}

    # 4) 프로세스 메모리 사용량
    try:
        import os
        import psutil
        proc = psutil.Process(os.getpid())
        mem = proc.memory_info()
        proprioception["memory_mb"] = round(mem.rss / (1024 * 1024), 1)
        proprioception["cpu_percent"] = proc.cpu_percent(interval=0.1)
        proprioception["threads"] = proc.num_threads()
    except Exception:
        try:
            import resource
            rusage = resource.getrusage(resource.RUSAGE_SELF)
            proprioception["memory_mb"] = round(rusage.ru_maxrss / 1024, 1)  # macOS: bytes
        except Exception:
            pass

    # 5) 활성/대기 태스크 수 (전체 프로젝트)
    try:
        from conversation_db import ConversationDB
        from project_manager import ProjectManager
        pm = ProjectManager()
        projects = pm.list_projects()
        active_tasks = 0
        pending_tasks = 0
        for proj in projects:
            try:
                pid = proj.get("id", "")
                db = ConversationDB(pid)
                pending = db.get_pending_tasks()
                pending_tasks += len(pending)
                # in_progress 태스크
                with db.get_connection() as conn:
                    row = conn.execute(
                        "SELECT COUNT(*) FROM tasks WHERE status = 'in_progress'"
                    ).fetchone()
                    active_tasks += row[0] if row else 0
            except Exception:
                continue
        proprioception["active_tasks"] = active_tasks
        proprioception["pending_tasks"] = pending_tasks
    except Exception:
        pass

    # 7) IBL 실행 통계 (오늘)
    try:
        from ibl_usage_db import IBLUsageDB
        db = IBLUsageDB()
        today = date.today().isoformat()
        conn = db._get_connection()
        # 오늘 실행 횟수
        row = conn.execute(
            "SELECT COUNT(*) FROM usage_log WHERE date(timestamp) = ?",
            (today,)
        ).fetchone()
        proprioception["ibl_executions_today"] = row[0] if row else 0
        conn.close()
    except Exception:
        pass

    if proprioception:
        state["proprioception"] = proprioception

    return state


def _collect_world_delta() -> Dict:
    """세계 변화분 수집 (경량 버전 — 경제 + 날씨만)"""
    from world_pulse import _load_config, _get_pulse_db

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
    cp_config = config.get("pulse_schedule", {})
    news_interval = cp_config.get("world_news_interval_hours", 6)

    should_collect_news = False
    try:
        conn = _get_pulse_db()
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
