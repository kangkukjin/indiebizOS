"""
trigger_engine.py - IBL 트리거 엔진
IndieBiz OS Core - Phase 8

트리거 소스(push)를 IBL로 관리합니다.
기존 시스템(channel_poller, calendar_manager, auto_response)을 감싸서
통합 트리거 인터페이스를 제공합니다.

트리거 타입:
- schedule: 시간 기반 (cron) → calendar_manager 연동
- channel: 메시지 수신 → channel_poller 규칙
- webhook: 외부 웹훅 (stub)
- file: 파일 변경 감지 (stub)

사용법:
    from trigger_engine import execute_trigger

    # 트리거 목록
    execute_trigger("list", {}, ".")

    # 감시 트리거 등록
    execute_trigger("watch", {
        "type": "schedule",
        "config": {"repeat": "daily", "time": "08:00"},
        "pipeline": '[sense:search]{source: "gnews", query: "AI"} >> [others:channel_send]{channel_type: "email", to: "me"}'
    }, ".")
"""

import json
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime_utils import get_base_path

BASE_PATH = get_base_path()
DATA_PATH = BASE_PATH / "data"
TRIGGERS_PATH = DATA_PATH / "event_triggers.json"
# 트리거 파일 load-modify-save 잠금 (B54-4: 동시 발화의 add_history 가 서로 덮어써 이력이 유실됐다)
_TRIGGERS_LOCK = threading.RLock()

_REPEATS = ("daily", "weekly", "monthly", "yearly", "none", "interval")
_WEEKDAY_NAMES = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
                  "월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}


def project_id_of_path(project_path) -> str:
    """구체 프로젝트 경로(`…/projects/<id>`)의 id. 시스템 AI(data/)·미지정(".")·그 밖은 ""(B54-1).

    트리거·스케줄이 발화할 때 "어느 프로젝트에서 등록됐나"를 알아야 패키지 도구
    (`[self:write]`·`[self:sheet]`·`[sense:stock]` …)의 활성 프로젝트 게이트를 지난다.
    """
    if not project_path:
        return ""
    try:
        p = Path(str(project_path))
    except Exception:
        return ""
    if str(p).strip() in ("", "."):
        return ""
    return p.name if p.parent.name == "projects" else ""


# === 트리거 저장소 ===

# cron 요일(0=일,1=월..6=토,7=일) → calendar weekdays(0=월..6=일) 변환
_CRON_DOW = {0: 6, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6}


def _cron_to_config(cron: str) -> dict:
    """표준 cron(5필드: 분 시 일 월 요일) → calendar config 또는 {"error":...}.

    지원: 매일(m h * * *), 매주(m h * * dow[,dow]), 매월(m h dom * *),
          매년(m h dom mon *), N시간 간격(0 */N * * *), 매시간(m * * * *).
    미지원 패턴(분 단위 */N, 복합 일+요일 등)은 명확한 에러 → config로 직접 지정 유도.
    """
    if not cron or not isinstance(cron, str):
        return {"error": "cron 문자열이 필요합니다."}
    fields = cron.split()
    if len(fields) != 5:
        return {"error": f"cron은 5필드(분 시 일 월 요일)여야 합니다: '{cron}'"}
    minute, hour, dom, mon, dow = fields

    # ★B9 (2026-08-17 상상훈련 10회차): 분 필드가 '*'/'*/N' 인데 매시간으로 조용히
    # 해소하면 "매분"(* * * * *) 요청이 60배 성긴 스케줄로 위장된다 — docstring 의
    # "분 단위 미지원=명확한 에러" 의도대로 여기서 거절한다.
    if minute == "*" or minute.startswith("*/"):
        return {"error": f"분 단위 반복('{cron}')은 트리거가 지원하지 않습니다(최소 해상도=시간). "
                         "짧은 지연·반복은 [self:schedule]{seconds|minutes}를 쓰세요."}

    # N시간 간격: 시 = */N (일·월·요일 모두 *)
    m_interval = re.match(r"^\*/(\d+)$", hour)
    if m_interval and dom == "*" and mon == "*" and dow == "*":
        # ★B54-7 (54회차): 간격형은 캘린더에 분 자리가 없다 — `30 */2 * * *` 가 매 2시간
        #   **정각**으로 조용히 접혔다(B9 와 같은 속: 분 필드 침묵 소실). 분 0 만 받는다.
        if minute != "0":
            return {"error": f"간격형 cron('{cron}')은 분 0 만 지원합니다(캘린더 간격 반복엔 분 자리가 없음). "
                             "특정 분이 필요하면 [self:schedule]{repeat:\"interval\", time:\"HH:MM\", interval_hours:N} 로 시작 시각을 주세요."}
        return {"repeat": "interval", "interval_hours": int(m_interval.group(1))}
    # 매시간 (m * * * * — 매시 m분)
    if hour == "*" and dom == "*" and mon == "*" and dow == "*":
        if minute != "0":
            return {"error": f"매시 반복 cron('{cron}')은 분 0 만 지원합니다(간격 반복엔 분 자리가 없음). "
                             "특정 분이 필요하면 [self:schedule]{repeat:\"interval\", time:\"HH:MM\", interval_hours:1} 로."}
        return {"repeat": "interval", "interval_hours": 1}

    if not (minute.isdigit() and hour.isdigit()):
        return {"error": f"분·시는 숫자여야 합니다(또는 시 '*/N' 간격): '{cron}'"}
    time_str = f"{int(hour):02d}:{int(minute):02d}"

    # 매주 (요일 지정)
    if dow != "*":
        if dom != "*" or mon != "*":
            return {"error": "요일과 일/월을 동시 지정한 cron은 미지원입니다. config로 직접 지정하세요."}
        days = _parse_cron_dow(dow)
        if days is None:
            return {"error": f"요일 필드는 0-7 숫자·범위(1-5)·콤마(1,3,5)·간격(*/2)이어야 합니다: '{dow}'"}
        return {"repeat": "weekly", "weekdays": days, "time": time_str}

    # 매년 (일+월) / 매월 (일만)
    if dom != "*" and mon != "*":
        if not (dom.isdigit() and mon.isdigit()):
            return {"error": f"일·월은 숫자여야 합니다: '{cron}'"}
        return {"repeat": "yearly", "month": int(mon), "day": int(dom), "time": time_str}
    if dom != "*":
        if not dom.isdigit():
            return {"error": f"일은 숫자여야 합니다: '{cron}'"}
        return {"repeat": "monthly", "day": int(dom), "time": time_str}

    # 매일
    return {"repeat": "daily", "time": time_str}


def _parse_cron_dow(dow: str):
    """cron 요일 필드 → calendar weekdays(0=월..6=일) 정렬 목록. 표준 형태(F54-1, 54회차):
    숫자 `1` · 콤마 `1,3,5` · 범위 `1-5`(평일) · 간격 `*/2` · 이름 `mon-fri`. 못 읽으면 None."""
    names = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}

    def _num(tok: str):
        tok = tok.strip().lower()
        if tok.isdigit() and int(tok) in _CRON_DOW:
            return int(tok)
        return names.get(tok[:3]) if tok[:3] in names else None

    out = set()
    for part in str(dow).split(","):
        part = part.strip()
        if not part:
            return None
        m_step = re.match(r"^\*/(\d+)$", part)
        if m_step:
            step = int(m_step.group(1))
            if step <= 0:
                return None
            out.update(range(0, 7, step))
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            a, b = _num(a), _num(b)
            if a is None or b is None:
                return None
            a, b = (a % 7), (b % 7)
            rng = range(a, b + 1) if a <= b else list(range(a, 7)) + list(range(0, b + 1))
            out.update(rng)
            continue
        n = _num(part)
        if n is None:
            return None
        out.add(n)
    return sorted({_CRON_DOW[d] for d in out})


def normalize_schedule_config(config) -> dict:
    """트리거 `config` 직접 지정의 정규화·검증 한 벌 (B54-8, 54회차).

    옛 가이드가 가르친 형태(요일을 이름으로, 1회를 once 로)가 검증 없이 저장돼
    **영원히 안 도는 트리거가 성공으로 등록**됐다(캘린더는 요일을 정수 0=월 로만 비교하고
    `once` 라는 repeat 은 없다). 반환: {"config": …} 또는 {"error": …}.
    """
    if not isinstance(config, dict):
        return {"error": "config 는 객체여야 합니다(예: {repeat:\"daily\", time:\"09:00\"}). cron 문자열이 더 간단합니다."}
    cfg = dict(config)
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
            if isinstance(d, int) and 0 <= d <= 6:
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
    if repeat == "none" and not cfg.get("date"):
        return {"error": "1회(none) 는 date(YYYY-MM-DD)가 필요합니다."}
    if repeat == "yearly" and (cfg.get("month") is None or cfg.get("day") is None):
        return {"error": "yearly 는 month·day 가 필요합니다."}
    return {"config": cfg}


def cron_to_config(cron: str) -> dict:
    """공개명 — 검수기(api_ibl)가 실행기와 같은 cron 판정을 쓴다(F54-1, 층 가드: 사적 심볼은 계약이 아니다)."""
    return _cron_to_config(cron)


def _resolve_schedule_config(params: dict) -> dict:
    """params 에서 schedule config 산출. cron 우선 파싱, 없으면 config 직접 사용(정규화·검증).
    반환: config dict, 또는 파싱 실패 시 {"error":...} 포함 dict."""
    if params.get("config"):
        return normalize_schedule_config(params["config"])
    cron = params.get("cron")
    if cron:
        parsed = _cron_to_config(cron)
        if "error" in parsed:
            return {"error": parsed["error"]}
        return {"config": parsed}
    return {"config": {}}


def load_triggers() -> dict:
    """트리거 파일 로드 (손상 시 빈 설정으로 덮어쓰기 방지 — safe_store)"""
    from safe_store import safe_load_json
    return safe_load_json(TRIGGERS_PATH, {"triggers": [], "history": []})


def _save_triggers(data: dict):
    """트리거 파일 저장 (원자적 쓰기 + .bak — safe_store)"""
    DATA_PATH.mkdir(parents=True, exist_ok=True)
    from safe_store import safe_save_json
    safe_save_json(TRIGGERS_PATH, data)


# === 스케줄 연동 (calendar_manager) ===

def _sync_schedule_trigger(trigger: dict, action: str = "add"):
    """schedule 트리거를 calendar_manager와 동기화"""
    try:
        from calendar_manager import get_calendar_manager
        cm = get_calendar_manager()

        if action == "add":
            config = trigger.get("config", {})
            cm.add_event(
                title=f"[IBL] {trigger['name']}",
                event_type="schedule",
                repeat=config.get("repeat", "daily"),
                event_time=config.get("time", "09:00"),
                event_date=config.get("date"),
                weekdays=config.get("weekdays"),
                month=config.get("month"),
                day=config.get("day"),
                interval_hours=config.get("interval_hours"),
                action="run_pipeline",
                action_params={
                    "pipeline": trigger.get("pipeline", ""),
                    "trigger_id": trigger["id"]
                },
                enabled=trigger.get("enabled", True),
                description=f"IBL 트리거: {trigger['name']}",
                # B54-1: 등록 프로젝트를 싣는다 — 발화(레거시 직접 실행)가 이 경로에서 돈다.
                owner_project_id=trigger.get("project_id") or None,
            )
            return True

        elif action == "delete":
            # calendar_manager에서 해당 트리거 ID의 이벤트 찾아서 삭제
            events = cm.config.get("events", [])
            for evt in events:
                ap = evt.get("action_params", {})
                if ap.get("trigger_id") == trigger["id"]:
                    cm.delete_event(evt["id"])
                    return True
            return False

        elif action == "toggle":
            events = cm.config.get("events", [])
            for evt in events:
                ap = evt.get("action_params", {})
                if ap.get("trigger_id") == trigger["id"]:
                    cm.update_event(evt["id"], enabled=trigger.get("enabled", True))
                    return True
            return False

    except Exception as e:
        return {"error": f"calendar_manager 동기화 실패: {str(e)}"}


# === 실행 이력 ===

def add_history(trigger_id: str, trigger_name: str, success: bool,
                 result_summary: str = "", duration_ms: int = 0,
                 error: str = None, count: int = None, shape: str = None):
    """실행 이력 추가 — 잠금 안 load-modify-save (B54-4: 동시 발화가 서로 덮어써 행이 사라졌다).

    F54-4: `result_summary` 는 사람용 문자열이라 통화가 아니었다 — `error`·`count`·`shape` 를
    동반해 `history >> filter{success == false} >> select{time, error}` 가 선다.
    B54-6: 트리거 레코드의 `run_count`·`last_run` 이 죽은 필드였다 — 여기서 함께 갱신한다.
    """
    now = datetime.now().isoformat()
    with _TRIGGERS_LOCK:
        data = load_triggers()
        history = data.get("history", [])
        row = {
            "trigger_id": trigger_id,
            "trigger_name": trigger_name,
            "time": now,
            "success": bool(success),
            "result_summary": str(result_summary or "")[:500],
            "duration_ms": duration_ms,
        }
        if error:
            row["error"] = str(error)[:300]
        if count is not None:
            row["count"] = count
        if shape:
            row["shape"] = shape
        history.append(row)
        # 최근 200개만 유지
        data["history"] = history[-200:]
        for t in data.get("triggers", []):
            if t.get("id") == trigger_id:
                t["run_count"] = int(t.get("run_count") or 0) + 1
                t["last_run"] = now
                t["last_success"] = bool(success)
                break
        _save_triggers(data)


# === CRUD 함수 ===

def _list_triggers(params: dict) -> dict:
    """트리거 목록"""
    data = load_triggers()
    triggers = data.get("triggers", [])

    # 타입 필터
    trigger_type = params.get("type")
    if trigger_type:
        triggers = [t for t in triggers if t.get("type") == trigger_type]

    # 활성 필터
    enabled_only = params.get("enabled_only", False)
    if enabled_only:
        triggers = [t for t in triggers if t.get("enabled", True)]

    # 문장 pre-flight — 저장된 pipeline 이 *지금의 어휘로* 실행 가능한가 (2026-08-15).
    # 트리거는 새벽에 혼자 돌기 때문에 어휘 은퇴로 죽어도 아무도 모른다(04시 정기보고가
    # 은퇴한 [self:report]{op:new} 를 부르며 매일 실패하던 선례). 목록이 곧 점검 창구다.
    from workflow_engine import preflight_sentence
    triggers = [dict(t) for t in triggers]
    for t in triggers:
        pf = preflight_sentence(t.get("pipeline") or t.get("steps") or "")
        t["runnable"] = pf["runnable"]
        if pf["problem"]:
            t["problem"] = pf["problem"]
            if pf["dead_vocab"]:
                t["dead_vocab"] = pf["dead_vocab"]

    # calendar_manager의 schedule 이벤트도 수집 (IBL 트리거가 아닌 기존 이벤트)
    existing_events = _get_existing_schedule_events()

    # items 병행 방출 — self:agents(d74461b)·self:switch(8a6aacd)와 같은 이유·같은 방식.
    # `triggers` 만 내면 `>> [table:*]` 가 "items 통화를 찾지 못했습니다"로 끊긴다.
    # ★items = triggers 만이다. existing_schedules 는 calendar_manager 의 옛 이벤트로
    #   종류가 다르므로 한 통화에 섞지 않는다(합치는 건 통화 수리가 아니라 의미 결정).
    return {
        "triggers": triggers,
        "items": triggers,
        "count": len(triggers),
        "existing_schedules": existing_events,
        "existing_count": len(existing_events)
    }


def _get_existing_schedule_events() -> list:
    """calendar_manager에 이미 있는 스케줄 이벤트 목록 (IBL 트리거가 아닌 것)"""
    try:
        from calendar_manager import get_calendar_manager
        cm = get_calendar_manager()
        tasks = cm.get_tasks()  # action이 있는 이벤트만
        existing = []
        for task in tasks:
            ap = task.get("action_params", {})
            if ap.get("trigger_id"):
                continue  # IBL 트리거는 제외
            existing.append({
                "id": task["id"],
                "name": task.get("title", ""),
                "type": "schedule",
                "action": task.get("action", ""),
                "repeat": task.get("repeat", "none"),
                "time": task.get("time", ""),
                "enabled": task.get("enabled", True),
                "source": "calendar_manager"
            })
        return existing
    except Exception:
        return []


def _get_trigger(target: str) -> dict:
    """트리거 상세"""
    data = load_triggers()
    for t in data.get("triggers", []):
        if t["id"] == target or t.get("name") == target:
            return {"trigger": t}
    return {"error": f"트리거를 찾을 수 없습니다: {target}"}


def _create_trigger(target: str, params: dict, project_path: str = None) -> dict:
    """새 트리거 생성

    target: 트리거 이름
    params:
        type: schedule | channel | webhook | file
        config: 타입별 설정
        pipeline: IBL 파이프라인 코드
        enabled: 활성화 여부 (기본 True)
    project_path: 등록 프로젝트 경로 — 발화 문맥의 뿌리(B54-1). 구체 프로젝트면 id 를 저장한다.
    """
    if not target:
        return {"error": "트리거 이름(name)이 필요합니다."}

    trigger_type = params.get("type", "schedule")
    pipeline = params.get("pipeline", "")

    if not pipeline:
        return {"error": "pipeline이 필요합니다. 실행할 IBL 코드를 지정하세요."}

    # config 산출 — cron 문자열을 calendar config 로 내부 해소(없으면 config 직접 사용)
    cfg = _resolve_schedule_config(params)
    if "error" in cfg:
        return {"error": cfg["error"]}
    config = cfg["config"]

    trigger_id = f"trg_{uuid.uuid4().hex[:12]}"
    trigger = {
        "id": trigger_id,
        "name": target,
        "type": trigger_type,
        "config": config,
        "pipeline": pipeline,
        "enabled": params.get("enabled", True),
        "created_at": datetime.now().isoformat(),
        "last_run": None,
        "run_count": 0
    }
    _pid = (params.get("project_id") if isinstance(params.get("project_id"), str) else "") or project_id_of_path(project_path)
    if _pid:
        trigger["project_id"] = _pid

    # 트리거 저장
    with _TRIGGERS_LOCK:
        data = load_triggers()
        data.setdefault("triggers", []).append(trigger)
        _save_triggers(data)

    # 타입별 연동
    if trigger_type == "schedule":
        sync_result = _sync_schedule_trigger(trigger, "add")
        if isinstance(sync_result, dict) and sync_result.get("error"):
            return {"trigger": trigger, "warning": sync_result["error"]}

    return {
        "trigger": trigger,
        "message": f"트리거 '{target}' 생성 완료 (ID: {trigger_id})"
    }


def _update_trigger(target: str, params: dict) -> dict:
    """트리거 수정"""
    with _TRIGGERS_LOCK:
        return _update_trigger_locked(target, params)


def _update_trigger_locked(target: str, params: dict) -> dict:
    data = load_triggers()
    for t in data.get("triggers", []):
        if t["id"] == target or t.get("name") == target:
            # 수정 가능 필드
            for key in ("name", "pipeline", "enabled", "type"):
                if key in params:
                    t[key] = params[key]
            if params.get("config"):
                norm = normalize_schedule_config(params["config"])
                if "error" in norm:
                    return {"error": norm["error"]}
                t["config"] = norm["config"]

            # cron 문자열로 스케줄 수정 시 calendar config 로 내부 해소
            if params.get("cron") and not params.get("config"):
                parsed = _cron_to_config(params["cron"])
                if "error" in parsed:
                    return {"error": parsed["error"]}
                t["config"] = parsed

            _save_triggers(data)

            # schedule 타입이면 calendar_manager도 동기화
            if t["type"] == "schedule":
                # 기존 삭제 후 재등록
                _sync_schedule_trigger(t, "delete")
                _sync_schedule_trigger(t, "add")

            return {"trigger": t, "message": "트리거 수정 완료"}

    return {"error": f"트리거를 찾을 수 없습니다: {target}"}


def _delete_trigger(target: str) -> dict:
    """트리거 삭제"""
    with _TRIGGERS_LOCK:
        return _delete_trigger_locked(target)


def _delete_trigger_locked(target: str) -> dict:
    data = load_triggers()
    triggers = data.get("triggers", [])
    original_len = len(triggers)

    trigger_to_delete = None
    for t in triggers:
        if t["id"] == target or t.get("name") == target:
            trigger_to_delete = t
            break

    if not trigger_to_delete:
        return {"error": f"트리거를 찾을 수 없습니다: {target}"}

    # calendar_manager 연동 삭제
    if trigger_to_delete["type"] == "schedule":
        _sync_schedule_trigger(trigger_to_delete, "delete")

    data["triggers"] = [t for t in triggers if t["id"] != trigger_to_delete["id"]]
    _save_triggers(data)

    return {
        "message": f"트리거 '{trigger_to_delete['name']}' 삭제 완료",
        "deleted_id": trigger_to_delete["id"]
    }


def _enable_trigger(target: str) -> dict:
    """트리거 활성화"""
    return _toggle_trigger(target, True)


def _disable_trigger(target: str) -> dict:
    """트리거 비활성화"""
    return _toggle_trigger(target, False)


def _toggle_trigger(target: str, enabled: bool) -> dict:
    """트리거 활성화/비활성화"""
    with _TRIGGERS_LOCK:
        return _toggle_trigger_locked(target, enabled)


def _toggle_trigger_locked(target: str, enabled: bool) -> dict:
    data = load_triggers()
    for t in data.get("triggers", []):
        if t["id"] == target or t.get("name") == target:
            t["enabled"] = enabled
            _save_triggers(data)

            # schedule 연동
            if t["type"] == "schedule":
                _sync_schedule_trigger(t, "toggle")

            status = "활성화" if enabled else "비활성화"
            return {"message": f"트리거 '{t['name']}' {status}", "trigger": t}

    return {"error": f"트리거를 찾을 수 없습니다: {target}"}


def _trigger_status() -> dict:
    """트리거 시스템 전체 상태"""
    data = load_triggers()
    triggers = data.get("triggers", [])

    # 트리거 통계
    stats = {
        "total_triggers": len(triggers),
        "enabled_triggers": sum(1 for t in triggers if t.get("enabled", True)),
        "by_type": {}
    }
    for t in triggers:
        typ = t.get("type", "unknown")
        stats["by_type"][typ] = stats["by_type"].get(typ, 0) + 1

    # channel_poller 상태 — 서비스가 등록한 프로브로 조회(직접 import 금지, ⑦ 후반부)
    from service_status import probe
    poller_status = probe("channel_poller", {"running": False, "channels": []})

    # calendar_manager 상태
    scheduler_status = {"running": False, "tasks": 0}
    try:
        from calendar_manager import get_calendar_manager
        cm = get_calendar_manager()
        scheduler_status = {
            "running": cm.running,
            "tasks": len(cm.get_tasks()),
            "total_events": len(cm.config.get("events", []))
        }
    except Exception:
        pass

    # auto_response 상태 — 프로브 조회
    auto_response_status = probe("auto_response", {"running": False})

    return {
        "triggers": stats,
        "channel_poller": poller_status,
        "scheduler": scheduler_status,
        "auto_response": auto_response_status
    }


def _trigger_history(target: str, params: dict) -> dict:
    """트리거 실행 이력"""
    data = load_triggers()
    history = data.get("history", [])

    if target:
        # 특정 트리거의 이력
        history = [h for h in history if h.get("trigger_id") == target]

    limit = params.get("limit", 20)
    history = history[-limit:]
    history.reverse()  # 최신 순

    # list 와 같은 이유의 items 병행 방출(history op 도 목록이다).
    return {
        "history": history,
        "items": history,
        "count": len(history)
    }


# === 메인 실행 함수 ===

def execute_trigger(action: str, params: dict,
                    project_path: str = ".") -> dict:
    """트리거 노드 라우팅

    Args:
        action: list/list_triggers, get/get_trigger, watch/create, update,
                delete/delete_trigger, enable, disable, status/trigger_status, history/trigger_history
        params: 파라미터 (trigger_id 등 포함)
        project_path: 프로젝트 경로

    Returns:
        결과 dict
    """
    # 단일 액션 패턴: trigger {op} 통합 액션. op로 다시 분기.
    if action == "trigger":
        op = (params.get("op") or "").strip()
        if not op:
            return {"error": "op 파라미터가 필요합니다. (list|get|create|update|delete|enable|disable|status|history)"}
        action = op

    trigger_id = params.get("trigger_id", "")

    if action in ("list", "list_triggers", "list_events"):
        return _list_triggers(params)
    elif action in ("detail", "get", "get_trigger", "get_event"):   # detail=정본(2026-08-24 #repair B5)
        if not trigger_id:
            return {"error": "trigger_id가 필요합니다."}
        return _get_trigger(trigger_id)
    elif action in ("watch", "create"):
        # 생성은 이름(name) 기준. 후방호환으로 trigger_id 도 수용.
        return _create_trigger(params.get("name") or trigger_id, params, project_path=project_path)
    elif action == "update":
        if not trigger_id:
            return {"error": "trigger_id가 필요합니다."}
        return _update_trigger(trigger_id, params)
    elif action in ("delete", "delete_trigger", "delete_event"):
        if not trigger_id:
            return {"error": "trigger_id가 필요합니다."}
        return _delete_trigger(trigger_id)
    elif action == "enable":
        if not trigger_id:
            return {"error": "trigger_id가 필요합니다."}
        return _enable_trigger(trigger_id)
    elif action == "disable":
        if not trigger_id:
            return {"error": "trigger_id가 필요합니다."}
        return _disable_trigger(trigger_id)
    elif action in ("status", "trigger_status", "event_status"):
        return _trigger_status()
    elif action in ("history", "trigger_history", "event_history"):
        return _trigger_history(trigger_id, params)
    else:
        return {
            "error": f"알 수 없는 트리거 액션: {action}",
            "available_actions": ["list_triggers", "get_trigger", "create", "update",
                                  "delete_trigger", "enable", "disable",
                                  "trigger_status", "trigger_history"]
        }

# 하위 호환: 기존 event_engine 호출 지원
execute_event = execute_trigger
