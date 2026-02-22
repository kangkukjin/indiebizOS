"""
event_engine.py - IBL 이벤트/트리거 엔진
IndieBiz OS Core - Phase 8

이벤트 소스(push)를 IBL로 관리합니다.
기존 시스템(channel_poller, calendar_manager, auto_response)을 감싸서
통합 트리거 인터페이스를 제공합니다.

트리거 타입:
- schedule: 시간 기반 (cron) → calendar_manager 연동
- channel: 메시지 수신 → channel_poller 규칙
- webhook: 외부 웹훅 (stub)
- file: 파일 변경 감지 (stub)

사용법:
    from event_engine import execute_event

    # 트리거 목록
    execute_event("list", None, {}, ".")

    # 스케줄 트리거 생성
    execute_event("create", "매일 AI 뉴스", {
        "type": "schedule",
        "config": {"repeat": "daily", "time": "08:00"},
        "pipeline": '[informant:search_news]("AI") >> [channel:send](gmail) {"to": "me"}'
    }, ".")
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime_utils import get_base_path

BASE_PATH = get_base_path()
DATA_PATH = BASE_PATH / "data"
TRIGGERS_PATH = DATA_PATH / "event_triggers.json"


# === 트리거 저장소 ===

def _load_triggers() -> dict:
    """트리거 파일 로드"""
    if TRIGGERS_PATH.exists():
        try:
            with open(TRIGGERS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"triggers": [], "history": []}


def _save_triggers(data: dict):
    """트리거 파일 저장"""
    DATA_PATH.mkdir(parents=True, exist_ok=True)
    with open(TRIGGERS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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
        return {"error": "트리거 이름이 필요합니다."}

    trigger_type = params.get("type", "schedule")
    config = params.get("config", {})
    pipeline = params.get("pipeline", "")

    if not pipeline:
        return {"error": "pipeline이 필요합니다. IBL 코드를 지정하세요."}

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
            for key in ("name", "config", "pipeline", "enabled"):
                if key in params:
                    t[key] = params[key]

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


def _event_status() -> dict:
    """이벤트 시스템 전체 상태"""
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

def execute_event(action: str, target: str, params: dict,
                  project_path: str = ".") -> dict:
    """이벤트 노드 라우팅

    Args:
        action: list/list_events, get/get_event, create, update,
                delete/delete_event, enable, disable, status, history, save/save_event
        target: 트리거 ID 또는 이름
        params: 추가 파라미터
        project_path: 프로젝트 경로

    Returns:
        결과 dict

    Phase 19: orchestrator 통합으로 action 이름 변경됨
              (list→list_events, get→get_event, delete→delete_event, save→save_event)
              구 이름도 하위 호환 유지
    """
    if action in ("list", "list_events"):
        return _list_triggers(params)
    elif action in ("get", "get_event"):
        if not target:
            return {"error": "트리거 ID 또는 이름이 필요합니다."}
        return _get_trigger(target)
    elif action in ("create", "save_event"):
        return _create_trigger(target, params)
    elif action == "update":
        if not target:
            return {"error": "트리거 ID가 필요합니다."}
        return _update_trigger(target, params)
    elif action in ("delete", "delete_event"):
        if not target:
            return {"error": "트리거 ID 또는 이름이 필요합니다."}
        return _delete_trigger(target)
    elif action == "enable":
        if not target:
            return {"error": "트리거 ID 또는 이름이 필요합니다."}
        return _enable_trigger(target)
    elif action == "disable":
        if not target:
            return {"error": "트리거 ID 또는 이름이 필요합니다."}
        return _disable_trigger(target)
    elif action == "status":
        return _event_status()
    elif action == "history":
        return _trigger_history(target, params)
    else:
        return {
            "error": f"알 수 없는 이벤트 액션: {action}",
            "available_actions": ["list_events", "get_event", "create", "update",
                                  "delete_event", "save_event", "enable", "disable",
                                  "status", "history"]
        }
