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
        "pipeline": '[sense:search_gnews]{query: "AI"} >> [others:channel_send]{channel_type: "email", to: "me"}'
    }, ".")
"""

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime_utils import get_base_path

BASE_PATH = get_base_path()
DATA_PATH = BASE_PATH / "data"
TRIGGERS_PATH = DATA_PATH / "event_triggers.json"


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

    # N시간 간격: 시 = */N (일·월·요일 모두 *)
    m_interval = re.match(r"^\*/(\d+)$", hour)
    if m_interval and dom == "*" and mon == "*" and dow == "*":
        return {"repeat": "interval", "interval_hours": int(m_interval.group(1))}
    # 매시간
    if hour == "*" and dom == "*" and mon == "*" and dow == "*":
        return {"repeat": "interval", "interval_hours": 1}

    if not (minute.isdigit() and hour.isdigit()):
        return {"error": f"분·시는 숫자여야 합니다(또는 시 '*/N' 간격): '{cron}'"}
    time_str = f"{int(hour):02d}:{int(minute):02d}"

    # 매주 (요일 지정)
    if dow != "*":
        if dom != "*" or mon != "*":
            return {"error": "요일과 일/월을 동시 지정한 cron은 미지원입니다. config로 직접 지정하세요."}
        days = []
        for part in dow.split(","):
            if not part.isdigit() or int(part) not in _CRON_DOW:
                return {"error": f"요일 필드는 0-7 숫자(콤마 구분)여야 합니다: '{dow}'"}
            days.append(_CRON_DOW[int(part)])
        return {"repeat": "weekly", "weekdays": sorted(set(days)), "time": time_str}

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


def _resolve_schedule_config(params: dict) -> dict:
    """params 에서 schedule config 산출. cron 우선 파싱, 없으면 config 직접 사용.
    반환: config dict, 또는 cron 파싱 실패 시 {"error":...} 포함 dict."""
    if params.get("config"):
        return {"config": params["config"]}
    cron = params.get("cron")
    if cron:
        parsed = _cron_to_config(cron)
        if "error" in parsed:
            return {"error": parsed["error"]}
        return {"config": parsed}
    return {"config": {}}


def _load_triggers() -> dict:
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
                description=f"IBL 트리거: {trigger['name']}"
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

def _add_history(trigger_id: str, trigger_name: str, success: bool,
                 result_summary: str = "", duration_ms: int = 0):
    """실행 이력 추가"""
    data = _load_triggers()
    history = data.get("history", [])
    history.append({
        "trigger_id": trigger_id,
        "trigger_name": trigger_name,
        "time": datetime.now().isoformat(),
        "success": success,
        "result_summary": result_summary[:500],
        "duration_ms": duration_ms
    })
    # 최근 200개만 유지
    data["history"] = history[-200:]
    _save_triggers(data)


# === CRUD 함수 ===

def _list_triggers(params: dict) -> dict:
    """트리거 목록"""
    data = _load_triggers()
    triggers = data.get("triggers", [])

    # 타입 필터
    trigger_type = params.get("type")
    if trigger_type:
        triggers = [t for t in triggers if t.get("type") == trigger_type]

    # 활성 필터
    enabled_only = params.get("enabled_only", False)
    if enabled_only:
        triggers = [t for t in triggers if t.get("enabled", True)]

    # calendar_manager의 schedule 이벤트도 수집 (IBL 트리거가 아닌 기존 이벤트)
    existing_events = _get_existing_schedule_events()

    return {
        "triggers": triggers,
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
    data = _load_triggers()
    for t in data.get("triggers", []):
        if t["id"] == target or t.get("name") == target:
            return {"trigger": t}
    return {"error": f"트리거를 찾을 수 없습니다: {target}"}


def _create_trigger(target: str, params: dict) -> dict:
    """새 트리거 생성

    target: 트리거 이름
    params:
        type: schedule | channel | webhook | file
        config: 타입별 설정
        pipeline: IBL 파이프라인 코드
        enabled: 활성화 여부 (기본 True)
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

    # 트리거 저장
    data = _load_triggers()
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
    data = _load_triggers()
    for t in data.get("triggers", []):
        if t["id"] == target or t.get("name") == target:
            # 수정 가능 필드
            for key in ("name", "config", "pipeline", "enabled", "type"):
                if key in params:
                    t[key] = params[key]

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
    data = _load_triggers()
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
    data = _load_triggers()
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
    data = _load_triggers()
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

    # channel_poller 상태
    poller_status = {"running": False, "channels": []}
    try:
        from channel_poller import get_channel_poller
        poller = get_channel_poller()
        poller_status = {
            "running": poller.running,
            "channels": list(poller.threads.keys())
        }
    except Exception:
        pass

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

    # auto_response 상태
    auto_response_status = {"running": False}
    try:
        from auto_response import get_auto_response_service
        ar = get_auto_response_service()
        auto_response_status = {"running": ar._running}
    except Exception:
        pass

    return {
        "triggers": stats,
        "channel_poller": poller_status,
        "scheduler": scheduler_status,
        "auto_response": auto_response_status
    }


def _trigger_history(target: str, params: dict) -> dict:
    """트리거 실행 이력"""
    data = _load_triggers()
    history = data.get("history", [])

    if target:
        # 특정 트리거의 이력
        history = [h for h in history if h.get("trigger_id") == target]

    limit = params.get("limit", 20)
    history = history[-limit:]
    history.reverse()  # 최신 순

    return {
        "history": history,
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
    elif action in ("get", "get_trigger", "get_event"):
        if not trigger_id:
            return {"error": "trigger_id가 필요합니다."}
        return _get_trigger(trigger_id)
    elif action in ("watch", "create"):
        # 생성은 이름(name) 기준. 후방호환으로 trigger_id 도 수용.
        return _create_trigger(params.get("name") or trigger_id, params)
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
