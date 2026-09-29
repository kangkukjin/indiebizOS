"""Canonical recurrence validation shared by every calendar writer and checker.

한 벌 원칙(75회차 후속, 2026-09-29): 캘린더에 실행 이벤트를 쓰는 입구(trigger·schedule·manage_events·
REST·goal)와 판본 2 check 는 **같은 함수**로 판정한다 — `schedule_request`·`calendar_request` 는 도구 인자를
이벤트 필드로 옮기는 순수 함수이고, 등록 런타임과 `ibl_value_checks.value_problems` 가 둘 다 부른다.
저장 직전의 마지막 관문은 `normalized_event`(add_event/update_event). 관문: scripts/iblbuild_schedule_rules.py.
"""
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


def normalize_schedule_config(config, *, require_date=True, executable=False) -> dict:
    """트리거 `config` 직접 지정의 정규화·검증 한 벌 (B54-8, 54회차).

    옛 가이드가 가르친 형태(요일을 이름으로, 1회를 once 로)가 검증 없이 저장돼
    **영원히 안 도는 트리거가 성공으로 등록**됐다(캘린더는 요일을 정수 0=월 로만 비교하고
    `once` 라는 repeat 은 없다). 반환: {"config": …} 또는 {"error": …}.

    executable: 실행 이벤트(action 있음)면 시각이 필수다 — 발화 판정은 시각 없는 레코드를 **영원히**
    거짓으로 본다(75회차 후속: `repeat:"daily"` 만 준 예약이 성공으로 저장되고 한 번도 안 돌았다).
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
            return {"error": "monthly/yearly에는 day(1..31) 또는 date가 필요합니다."}
    if repeat == "yearly":
        try:
            if type(cfg.get("month")) is not int:
                raise ValueError()
            datetime(2000, cfg["month"], cfg["day"])
        except (TypeError, ValueError):
            return {"error": "yearly의 month/day가 유효한 날짜가 아닙니다."}
    if executable and not cfg.get("time"):
        return {"error": "실행 예약에는 time(HH:MM)이 필요합니다 — 반복이면 매번 도는 시각, interval 이면 첫 실행 시각."}
    return {"config": cfg}


_SHORT_MONTHS = {29: "2월(평년)", 30: "2월", 31: "2·4·6·9·11월"}


def recurrence_notice(cfg) -> str | None:
    """등록은 되지만 어떤 주기에는 돌지 않는 규칙을 등록 응답에서 말한다(75회차 B75-1 제안 3).

    짧은 달의 없는 날은 건너뛴다(말일로 접지 않는다 — 말일 의미는 V75-1 후보). 조용히 건너뛰지 않게
    등록 시점에 한 번 말한다."""
    repeat, day = cfg.get("repeat"), cfg.get("day")
    if repeat == "monthly" and isinstance(day, int) and day >= 29:
        return f"매월 {day}일 — {_SHORT_MONTHS[day]}처럼 {day}일이 없는 달에는 실행하지 않습니다."
    if repeat == "yearly" and cfg.get("month") == 2 and day == 29:
        return "매년 2월 29일 — 윤년에만 실행됩니다."
    return None


def _past_one_shot(cfg, now):
    if cfg.get("repeat") != "none" or not cfg.get("date") or not cfg.get("time"):
        return None
    target = datetime.strptime(f"{cfg['date']} {cfg['time']}", "%Y-%m-%d %H:%M")
    if target <= now:
        return (f"예정 시각 {cfg['date']} {cfg['time']} 이(가) 이미 지났습니다. "
                "내일이면 date 를 명시하고, 잠깐 뒤면 minutes/seconds 지연을 쓰세요.")
    return None


_RECURRENCE_KEYS = ("weekdays", "month", "day", "interval_hours")


def schedule_request(params, now=None, *, check_past=True) -> dict:
    """`[self:schedule]` 인자 → 등록할 이벤트. 등록 런타임과 판본 2 check 가 이 함수 하나로 판정한다.

    반환: {"delay": 초, "execute_at": datetime, "fields": …} (지연) · {"fields": …, "notice": …} (시각/반복)
    · {"error": …}. check_past=False 는 check 용 — "이미 지난 시각"은 실행 순간의 사실이라 문장 계약이 아니다.
    """
    from datetime import timedelta
    now = now or datetime.now()
    p = dict(params)
    at = p.get("at")
    if at and not p.get("date") and not p.get("time"):
        at_str = str(at).replace("T", " ").strip()
        if " " in at_str:
            try:
                parsed = datetime.fromisoformat(at_str.replace(" ", "T"))
            except (ValueError, TypeError):
                return {"error": f"at 을 읽을 수 없습니다: '{at}' (YYYY-MM-DD HH:MM 또는 HH:MM)"}
            p["date"], p["time"] = parsed.strftime("%Y-%m-%d"), parsed.strftime("%H:%M")
        else:
            p["time"] = at_str[:5]
    repeat = str(p.get("repeat") or "none").strip().lower()
    if repeat == "once":
        repeat = "none"
    try:
        total = float(p.get("minutes") or 0) * 60 + float(p.get("seconds") or 0)
    except (ValueError, TypeError):
        return {"error": "minutes/seconds 는 숫자여야 합니다."}
    if total < 0:
        return {"error": "minutes/seconds 는 0 이상이어야 합니다."}
    if total > 0:
        if total > 86400:
            return {"error": "지연은 24시간 이내만 가능합니다."}
        if repeat != "none":
            return {"error": f"지연(minutes/seconds)과 반복(repeat '{p.get('repeat')}')은 함께 쓸 수 없습니다 — "
                             "반복이면 time 과 repeat 으로, 한 번이면 repeat 을 빼세요."}
        execute_at = now + timedelta(seconds=total)
        return {"delay": total, "execute_at": execute_at,
                "fields": {"repeat": "none", "date": execute_at.strftime("%Y-%m-%d"),
                           "time": execute_at.strftime("%H:%M")}}
    date, time = split_date_time(p.get("date"), p.get("time"))
    start = p.get("start_time")
    if start and (not date or not time):
        try:
            parsed = datetime.fromisoformat(str(start))
            date = date or parsed.strftime("%Y-%m-%d")
            time = time or parsed.strftime("%H:%M")
        except (ValueError, TypeError):
            return {"error": f"start_time 을 읽을 수 없습니다: '{start}'"}
    if repeat == "none":
        if not time:
            return {"error": "time(HH:MM) 또는 minutes가 필요합니다."}
        date = date or now.strftime("%Y-%m-%d")
    fields = {"repeat": repeat, "date": date, "time": time,
              **{k: p[k] for k in _RECURRENCE_KEYS if p.get(k) is not None}}
    result = normalize_schedule_config({k: v for k, v in fields.items() if v is not None}, executable=True)
    if result.get("error"):
        return result
    cfg = result["config"]
    past = _past_one_shot(cfg, now) if check_past else None
    if past:
        return {"error": past}
    return {"fields": cfg, "notice": recurrence_notice(cfg)}


def calendar_request(params, now=None, *, executable=False, check_past=True) -> dict:
    """`[self:manage_events]{op:"create"}` 인자 → 이벤트 필드. 등록 런타임과 판본 2 check 가 공유한다.

    executable: do/event_action 이 있는 실행 이벤트. 일정(실행 없음)은 날짜만 있으면 되고 시각은 선택이다."""
    now = now or datetime.now()
    date, time = split_date_time(params.get("date"), params.get("time"))
    start = params.get("start_time")
    if start and (not date or not time):
        try:
            parsed = datetime.fromisoformat(str(start))
            date = date or parsed.strftime("%Y-%m-%d")
            time = time or parsed.strftime("%H:%M")
        except (ValueError, TypeError):
            return {"error": f"start_time 을 읽을 수 없습니다: '{start}'"}
    if not date and not executable:
        return {"error": "date는 필수입니다. (YYYY-MM-DD)"}
    repeat = params.get("repeat") or "none"
    fields = {"repeat": repeat, "date": date, "time": time,
              **{k: params[k] for k in _RECURRENCE_KEYS if params.get(k) is not None}}
    fields = {k: v for k, v in fields.items() if v is not None}
    if not executable and str(repeat).strip().lower() in ("none", "once") and not any(
            k in fields for k in _RECURRENCE_KEYS):
        # 일정 1건 — 날짜 표기만 검사한다(지난 날짜의 기록도 일정이다).
        result = normalize_schedule_config(fields)
        return result if result.get("error") else {"fields": result["config"], "notice": None}
    result = normalize_schedule_config(fields, executable=executable)
    if result.get("error"):
        return result
    cfg = result["config"]
    past = _past_one_shot(cfg, now) if (executable and check_past) else None
    if past:
        return {"error": past}
    return {"fields": cfg, "notice": recurrence_notice(cfg)}



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
    result = normalize_schedule_config(cfg, executable=bool(out.get("action")))
    if result.get("error"):
        raise ValueError(result["error"])
    out.update(result["config"])
    return out
