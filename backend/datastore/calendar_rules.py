"""Canonical recurrence validation shared by every calendar writer and checker."""
import re
from datetime import datetime

_REPEATS = ("daily", "weekly", "monthly", "yearly", "none", "interval")
_WEEKDAY_NAMES = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
                  "월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}


def split_date_time(event_date, event_time):
    """Accept the existing combined ISO date/time form at every entry point."""
    date = str(event_date).strip() if event_date else None
    time = str(event_time).strip() if event_time else None
    if time and (" " in time or "T" in time):
        try:
            parsed = datetime.fromisoformat(time.replace(" ", "T"))
            if not date:
                date = parsed.strftime("%Y-%m-%d")
            time = parsed.strftime("%H:%M")
        except (ValueError, TypeError):
            pass
    if date and (" " in date or "T" in date):
        try:
            parsed = datetime.fromisoformat(date.replace(" ", "T"))
            date = parsed.strftime("%Y-%m-%d")
            if not time:
                time = parsed.strftime("%H:%M")
        except (ValueError, TypeError):
            pass
    if time and len(time) == 8 and time.count(":") == 2:
        time = time[:5]
    return date, time


def normalize_schedule_config(config, *, require_date=True) -> dict:
    """트리거 `config` 직접 지정의 정규화·검증 한 벌 (B54-8, 54회차).

    옛 가이드가 가르친 형태(요일을 이름으로, 1회를 once 로)가 검증 없이 저장돼
    **영원히 안 도는 트리거가 성공으로 등록**됐다(캘린더는 요일을 정수 0=월 로만 비교하고
    `once` 라는 repeat 은 없다). 반환: {"config": …} 또는 {"error": …}.
    """
    if not isinstance(config, dict):
        return {"error": "config 는 객체여야 합니다(예: {repeat:\"daily\", time:\"09:00\"}). cron 문자열이 더 간단합니다."}
    cfg = dict(config)
    date, time = split_date_time(cfg.get("date"), cfg.get("time"))
    if date is not None:
        cfg["date"] = date
    if time is not None:
        cfg["time"] = time
    repeat = str(cfg.get("repeat", "daily") or "daily").strip().lower()
    if repeat == "once":
        repeat = "none"
    if repeat not in _REPEATS:
        return {"error": f"repeat '{cfg.get('repeat')}' 는 지원하지 않습니다. 가능: {', '.join(_REPEATS)} (1회는 none)."}
    cfg["repeat"] = repeat
    t = cfg.get("time")
    if t is not None:
        t = str(t).strip()
        m = re.match(r"^(\d{1,2}):(\d{2})(?::\d{2})?$", t)
        if not m or not (0 <= int(m.group(1)) <= 23 and 0 <= int(m.group(2)) <= 59):
            return {"error": f"time 은 HH:MM 이어야 합니다: '{t}'"}
        cfg["time"] = f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
    if repeat == "weekly":
        raw = cfg.get("weekdays")
        if not isinstance(raw, list) or not raw:
            return {"error": "weekly 는 weekdays 목록이 필요합니다(0=월..6=일 또는 mon..sun)."}
        days = []
        for d in raw:
            if type(d) is int and 0 <= d <= 6:
                days.append(d)
            elif isinstance(d, str) and d.strip().lower()[:3] in _WEEKDAY_NAMES:
                days.append(_WEEKDAY_NAMES[d.strip().lower()[:3]])
            elif isinstance(d, str) and d.strip() in _WEEKDAY_NAMES:
                days.append(_WEEKDAY_NAMES[d.strip()])
            elif isinstance(d, str) and d.strip().isdigit() and 0 <= int(d) <= 6:
                days.append(int(d))
            else:
                return {"error": f"weekdays 값을 읽을 수 없습니다: {d!r} (0=월..6=일 또는 mon..sun)"}
        cfg["weekdays"] = sorted(set(days))
    if repeat == "interval":
        try:
            ih = int(cfg.get("interval_hours") or 0)
        except (TypeError, ValueError):
            ih = 0
        if ih <= 0:
            return {"error": "interval 은 interval_hours(1 이상 정수)가 필요합니다."}
        cfg["interval_hours"] = ih
    if repeat == "none" and require_date and not cfg.get("date"):
        return {"error": "1회(none) 는 date(YYYY-MM-DD)가 필요합니다."}
    if cfg.get("date"):
        try:
            dt = datetime.strptime(cfg["date"], "%Y-%m-%d")
        except (ValueError, TypeError):
            return {"error": "date는 유효한 YYYY-MM-DD 날짜여야 합니다."}
        if repeat in ("monthly", "yearly"):
            cfg.setdefault("day", dt.day)
        if repeat == "yearly":
            cfg.setdefault("month", dt.month)
    if repeat in ("monthly", "yearly"):
        day = cfg.get("day")
        if type(day) is not int or not 1 <= day <= 31:
            return {"error": "monthly/yearly에는 day(1..31) 또는 date가 필요합니다. 없는 날짜는 건너뜁니다."}
    if repeat == "yearly":
        try:
            if type(cfg.get("month")) is not int:
                raise ValueError()
            datetime(2000, cfg["month"], cfg["day"])
        except (TypeError, ValueError):
            return {"error": "yearly의 month/day가 유효한 날짜가 아닙니다."}
    return {"config": cfg}



def normalized_event(event, changed=None):
    """Normalize before mutation; old date-only recurrences remain readable."""
    out = dict(event)
    if not out.get("action") and out.get("repeat", "none") == "none" and not out.get("date"):
        return out
    cfg = {k: out[k] for k in ("repeat", "date", "time", "month", "day", "weekdays", "interval_hours")
           if out.get(k) is not None}
    if out.get("execute_at"):
        stamp = datetime.fromisoformat(out["execute_at"])
        cfg.setdefault("date", stamp.strftime("%Y-%m-%d"))
        cfg.setdefault("time", stamp.strftime("%H:%M"))
    if changed and "date" in changed:
        for key in ("day", "month"):
            if key not in changed:
                cfg.pop(key, None)
    result = normalize_schedule_config(cfg)
    if result.get("error"):
        raise ValueError(result["error"])
    out.update(result["config"])
    return out
