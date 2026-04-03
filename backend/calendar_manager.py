"""
calendar_manager.py - 통합 캘린더/스케줄러 관리자
IndieBiz OS Core

모든 이벤트(기념일, 약속, 스케줄 작업)를 하나의 저장소에서 관리합니다.
calendar_events.json이 유일한 정보 원천(Single Source of Truth)입니다.

이벤트 타입:
- anniversary: 기념일
- birthday: 생일
- appointment: 약속
- reminder: 리마인더
- schedule: 스케줄 작업 (실행 목적)
- other: 기타

반복 유형:
- none: 1회
- daily: 매일
- weekly: 매주 (weekdays[] 사용)
- monthly: 매월
- yearly: 매년 (month/day 사용)
- interval: N시간 간격 (interval_hours 사용)

실행 가능 이벤트:
- action 필드가 있으면 실행 가능 (run_switch, send_notification 등)
- action이 null이면 순수 캘린더 이벤트 (정보 기록만)

모듈화:
- calendar_actions.py: 액션 핸들러 + 가시적 실행 시스템
- calendar_html.py: HTML 캘린더 생성
"""

import json
import time
import uuid
import threading
from datetime import datetime, date
from pathlib import Path
from typing import Callable, Dict, List, Optional

from runtime_utils import get_base_path

BASE_PATH = get_base_path()
DATA_PATH = BASE_PATH / "data"
OUTPUTS_PATH = BASE_PATH / "outputs"
CALENDAR_CONFIG_PATH = DATA_PATH / "calendar_events.json"

# 이벤트 타입 라벨
EVENT_TYPE_LABELS = {
    "anniversary": "기념일",
    "birthday": "생일",
    "appointment": "약속",
    "reminder": "리마인더",
    "schedule": "스케줄",
    "other": "기타",
}

EVENT_TYPE_COLORS = {
    "anniversary": "#e91e63",
    "birthday": "#9c27b0",
    "appointment": "#2196f3",
    "reminder": "#ff9800",
    "schedule": "#4caf50",
    "other": "#607d8b",
}

EVENT_TYPE_EMOJI = {
    "anniversary": "\U0001f48d",
    "birthday": "\U0001f382",
    "appointment": "\U0001f4cb",
    "reminder": "\U0001f514",
    "schedule": "\u26a1",
    "other": "\U0001f4cc",
}

# Mixin 모듈
from calendar_actions import CalendarActionsMixin
from calendar_html import CalendarHtmlMixin


class CalendarManager(CalendarActionsMixin, CalendarHtmlMixin):
    """통합 캘린더/스케줄러 관리자"""

    def __init__(self, log_callback: Callable[[str], None] = None):
        self.log_callback = log_callback or print
        self.config = self._load_config()
        self.running = False
        self.thread: Optional[threading.Thread] = None

        # 실행 가능 액션 등록
        self.actions: Dict[str, Callable] = {
            "test": self._action_test,
            "run_switch": self._action_run_switch,
            "run_workflow": self._action_run_workflow,
            "run_pipeline": self._action_run_pipeline,
            "send_notification": self._action_send_notification,
            "run_goal": self._action_run_goal,  # Phase 26: 목표 반복 실행
        }

    def _log(self, message: str):
        """로그 출력"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        full_message = f"[스케줄러 {timestamp}] {message}"
        self.log_callback(full_message)

    # =========================================================================
    # 설정 파일 관리
    # =========================================================================

    def _load_config(self) -> dict:
        """설정 파일 로드"""
        if CALENDAR_CONFIG_PATH.exists():
            try:
                with open(CALENDAR_CONFIG_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[CalendarManager] 설정 로드 실패: {e}")
        return {"events": []}

    def _save_config(self):
        """설정 파일 저장"""
        DATA_PATH.mkdir(parents=True, exist_ok=True)
        with open(CALENDAR_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    # =========================================================================
    # 이벤트 CRUD (캘린더 + 스케줄 통합)
    # =========================================================================

    def list_agent_schedules(self, owner_project_id: str, owner_agent_id: str = None) -> List[dict]:
        """특정 에이전트의 스케줄만 조회"""
        events = self.config.get("events", [])
        result = []
        for evt in events:
            if evt.get("owner_project_id") != owner_project_id:
                continue
            if owner_agent_id and evt.get("owner_agent_id") != owner_agent_id:
                continue
            result.append(evt)
        return result

    def list_events(self, year: int = None, month: int = None) -> List[dict]:
        """이벤트 목록 조회"""
        events = self.config.get("events", [])
        if year is None and month is None:
            return events

        result = []
        for evt in events:
            evt_date = evt.get("date", "")
            if not evt_date:
                repeat = evt.get("repeat", "none")
                if repeat in ("daily", "interval"):
                    result.append(evt)
                continue

            try:
                d = datetime.strptime(evt_date, "%Y-%m-%d").date()
            except ValueError:
                continue

            repeat = evt.get("repeat", "none")

            if repeat == "yearly":
                if month and d.month == month:
                    result.append(evt)
                elif year and not month:
                    result.append(evt)
            elif repeat == "monthly":
                if year and month:
                    result.append(evt)
                elif year:
                    result.append(evt)
            elif repeat in ("weekly", "daily", "interval"):
                result.append(evt)
            else:
                if year and month:
                    if d.year == year and d.month == month:
                        result.append(evt)
                elif year:
                    if d.year == year:
                        result.append(evt)

        return result

    def add_event(self, title: str, event_date: str = None, event_type: str = "other",
                  repeat: str = "none", description: str = "", event_time: str = None,
                  action: str = None, action_params: dict = None,
                  enabled: bool = True, weekdays: List[int] = None,
                  month: int = None, day: int = None,
                  interval_hours: int = None,
                  owner_project_id: str = None, owner_agent_id: str = None) -> dict:
        """이벤트 추가 (캘린더 이벤트 + 실행 가능 이벤트 모두)"""
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        event = {
            "id": event_id,
            "title": title,
            "date": event_date,
            "type": event_type,
            "repeat": repeat,
            "description": description,
            "created_at": datetime.now().isoformat(),
            "enabled": enabled,
        }
        if owner_project_id:
            event["owner_project_id"] = owner_project_id
        if owner_agent_id:
            event["owner_agent_id"] = owner_agent_id
        if event_time:
            event["time"] = event_time
        if action:
            event["action"] = action
        if action_params:
            event["action_params"] = action_params
        if repeat == "weekly" and weekdays:
            event["weekdays"] = weekdays
        if repeat == "yearly":
            if month is not None:
                event["month"] = month
            if day is not None:
                event["day"] = day
        if repeat == "interval" and interval_hours:
            event["interval_hours"] = interval_hours

        self.config.setdefault("events", []).append(event)
        self._save_config()

        if action:
            self._log(f"실행 이벤트 추가: {title} ({repeat}, {event_time or ''})")
        return event

    def update_event(self, event_id: str, **kwargs) -> bool:
        """이벤트 수정"""
        valid_keys = ("title", "date", "type", "repeat", "description", "time",
                      "action", "action_params", "enabled", "weekdays",
                      "month", "day", "interval_hours",
                      "owner_project_id", "owner_agent_id")
        events = self.config.get("events", [])
        for evt in events:
            if evt["id"] == event_id:
                for key, value in kwargs.items():
                    if key in valid_keys:
                        evt[key] = value
                self._save_config()
                return True
        return False

    def add_goal_schedule(self, goal_id: str, goal_name: str,
                         every_frequency: str = None, schedule_at: str = None) -> dict:
        """Phase 26: Goal의 every/schedule 설정을 캘린더 이벤트로 등록"""
        action_params = {"goal_id": goal_id}

        if schedule_at:
            try:
                dt = datetime.fromisoformat(schedule_at)
                return self.add_event(
                    title=f"[Goal] {goal_name}",
                    event_date=dt.strftime("%Y-%m-%d"),
                    event_time=dt.strftime("%H:%M"),
                    event_type="schedule",
                    repeat="none",
                    action="run_goal",
                    action_params=action_params,
                    description=f"목표 실행: {goal_name}",
                )
            except ValueError:
                return {"error": f"잘못된 schedule_at 형식: {schedule_at}"}

        if every_frequency:
            freq = every_frequency.strip().lower()
            interval_hours = self._parse_frequency_to_hours(freq)

            if interval_hours is None:
                return {"error": f"지원하지 않는 빈도 형식: {every_frequency}"}

            now = datetime.now()
            return self.add_event(
                title=f"[Goal] {goal_name}",
                event_date=now.strftime("%Y-%m-%d"),
                event_time=now.strftime("%H:%M"),
                event_type="schedule",
                repeat="interval",
                interval_hours=interval_hours,
                action="run_goal",
                action_params=action_params,
                description=f"목표 반복 실행: {goal_name} (매 {every_frequency})",
            )

        return {"error": "every_frequency 또는 schedule_at 중 하나가 필요합니다."}

    def _parse_frequency_to_hours(self, freq: str) -> Optional[int]:
        """빈도 문자열을 시간(hours) 단위로 변환"""
        import re
        m = re.match(r'^(\d+)\s*(m|min|h|hr|hour|d|day|w|week)s?$', freq)
        if not m:
            return None

        value = int(m.group(1))
        unit = m.group(2)

        if unit in ("m", "min"):
            return max(1, value // 60) if value >= 60 else 1
        elif unit in ("h", "hr", "hour"):
            return max(1, value)
        elif unit in ("d", "day"):
            return value * 24
        elif unit in ("w", "week"):
            return value * 24 * 7
        return None

    def remove_goal_schedule(self, goal_id: str) -> bool:
        """특정 goal의 스케줄 이벤트 제거"""
        events = self.config.get("events", [])
        original_len = len(events)
        self.config["events"] = [
            e for e in events
            if not (e.get("action") == "run_goal" and
                    e.get("action_params", {}).get("goal_id") == goal_id)
        ]
        if len(self.config["events"]) < original_len:
            self._save_config()
            return True
        return False

    def delete_event(self, event_id: str) -> bool:
        """이벤트 삭제"""
        events = self.config.get("events", [])
        original_len = len(events)
        self.config["events"] = [e for e in events if e["id"] != event_id]
        if len(self.config["events"]) < original_len:
            self._save_config()
            return True
        return False

    # =========================================================================
    # 스케줄러 호환 메서드 (기존 ProgramScheduler 인터페이스)
    # =========================================================================

    def get_tasks(self) -> List[dict]:
        """실행 가능한 이벤트만 반환 (action이 있는 것)"""
        events = self.config.get("events", [])
        return [e for e in events if e.get("action")]

    def add_task(self, name: str, description: str = "", time_str: str = "09:00",
                 action: str = "test", enabled: bool = True,
                 repeat: str = "daily", weekdays: List[int] = None,
                 date: str = None, month: int = None, day: int = None,
                 interval_hours: int = None,
                 action_params: dict = None) -> dict:
        """스케줄러 호환 - add_event 래퍼"""
        return self.add_event(
            title=name,
            event_date=date,
            event_type="schedule",
            repeat=repeat,
            description=description,
            event_time=time_str,
            action=action,
            action_params=action_params,
            enabled=enabled,
            weekdays=weekdays,
            month=month,
            day=day,
            interval_hours=interval_hours
        )

    def update_task(self, task_id: str, **kwargs) -> bool:
        """스케줄러 호환 - update_event 래퍼"""
        if "time" in kwargs:
            kwargs["time"] = kwargs["time"]
        return self.update_event(task_id, **kwargs)

    def delete_task(self, task_id: str) -> bool:
        """스케줄러 호환 - delete_event 래퍼"""
        return self.delete_event(task_id)

    def toggle_task(self, task_id: str) -> Optional[bool]:
        """작업 활성화/비활성화 토글"""
        events = self.config.get("events", [])
        for evt in events:
            if evt["id"] == task_id:
                evt["enabled"] = not evt.get("enabled", True)
                self._save_config()
                status = "활성화" if evt["enabled"] else "비활성화"
                self._log(f"작업 {status}: {evt.get('title', task_id)}")
                return evt["enabled"]
        return None

    def register_action(self, name: str, func: Callable):
        """작업 함수 등록"""
        self.actions[name] = func
        self._log(f"작업 함수 등록됨: {name}")

    # =========================================================================
    # 실행 루프
    # =========================================================================

    def start(self):
        """스케줄러 시작"""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        self._log("통합 스케줄러 시작됨")

    def stop(self):
        """스케줄러 중지"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        self._log("통합 스케줄러 중지됨")

    def is_running(self) -> bool:
        """실행 중 여부"""
        return self.running

    def _run_loop(self):
        """스케줄러 메인 루프"""
        while self.running:
            now = datetime.now()

            for evt in self.config.get("events", []):
                if not evt.get("action"):
                    continue
                if self._should_run_task(evt, now):
                    threading.Thread(
                        target=self._execute_task,
                        args=(evt,),
                        daemon=True
                    ).start()

            time.sleep(60)

    @staticmethod
    def _normalize_time(raw: str) -> str:
        """어떤 형태의 시간이든 HH:MM으로 정규화."""
        if not raw:
            return ""
        raw = raw.strip()
        for sep in (" ", "T"):
            if sep in raw:
                raw = raw.split(sep)[-1]
                break
        return raw[:5]

    def _should_run_task(self, task: dict, now: datetime) -> bool:
        """작업 실행 여부 판단"""
        if not task.get("enabled", True):
            return False

        current_time = now.strftime("%H:%M")
        repeat = task.get("repeat", "daily")

        task_time = self._normalize_time(task.get("time", ""))
        if repeat != "interval" and task_time != current_time:
            return False

        last_run = task.get("last_run")

        if repeat == "daily":
            if last_run:
                try:
                    last_run_date = datetime.fromisoformat(last_run).date()
                    if last_run_date == now.date():
                        return False
                except (ValueError, TypeError):
                    pass
            return True

        elif repeat == "weekly":
            weekdays = task.get("weekdays", [])
            if now.weekday() not in weekdays:
                return False
            if last_run:
                try:
                    last_run_date = datetime.fromisoformat(last_run).date()
                    if last_run_date == now.date():
                        return False
                except (ValueError, TypeError):
                    pass
            return True

        elif repeat == "none":
            target_date = task.get("date")
            if not target_date:
                return False
            try:
                target = datetime.strptime(target_date, "%Y-%m-%d").date()
                if now.date() != target:
                    return False
                if last_run:
                    return False
                return True
            except ValueError:
                return False

        elif repeat == "yearly":
            target_month = task.get("month")
            target_day = task.get("day")
            if target_month is None or target_day is None:
                return False
            if now.month != target_month or now.day != target_day:
                return False
            if last_run:
                try:
                    last_run_date = datetime.fromisoformat(last_run).date()
                    if last_run_date == now.date():
                        return False
                except (ValueError, TypeError):
                    pass
            return True

        elif repeat == "monthly":
            evt_date_str = task.get("date", "")
            if evt_date_str:
                try:
                    evt_day = datetime.strptime(evt_date_str, "%Y-%m-%d").day
                    if now.day != evt_day:
                        return False
                except ValueError:
                    return False
            if last_run:
                try:
                    last_run_date = datetime.fromisoformat(last_run).date()
                    if last_run_date == now.date():
                        return False
                except (ValueError, TypeError):
                    pass
            return True

        elif repeat == "interval":
            interval_hours = task.get("interval_hours", 1)
            if not last_run:
                if task.get("time") == current_time:
                    return True
                return False
            try:
                last_run_dt = datetime.fromisoformat(last_run)
                elapsed = (now - last_run_dt).total_seconds() / 3600
                return elapsed >= interval_hours
            except (ValueError, TypeError):
                return False

        return False

    def _execute_task(self, task: dict):
        """작업 실행"""
        action_name = task.get("action")
        action_func = self.actions.get(action_name)

        if not action_func:
            self._log(f"알 수 없는 작업: {action_name}")
            return

        self._log(f"작업 시작: {task.get('title', task.get('name', 'unknown'))}")

        try:
            result = action_func(task)

            task["last_run"] = datetime.now().isoformat()

            if task.get("repeat") == "none":
                task["enabled"] = False
                self._log(f"1회 작업 완료, 비활성화됨: {task.get('title')}")

            self._save_config()
            self._log(f"작업 완료: {task.get('title')}")
            return result

        except Exception as e:
            self._log(f"작업 실패: {task.get('title')} - {str(e)}")
            return None

    def run_task_now(self, task_id: str) -> bool:
        """작업 즉시 실행"""
        for evt in self.config.get("events", []):
            if evt["id"] == task_id and evt.get("action"):
                threading.Thread(
                    target=self._execute_task,
                    args=(evt,),
                    daemon=True
                ).start()
                return True
        return False


# ============ 싱글톤 ============

_calendar_instance: Optional[CalendarManager] = None


def get_calendar_manager(log_callback: Callable[[str], None] = None) -> CalendarManager:
    """CalendarManager 인스턴스 반환 (싱글톤)"""
    global _calendar_instance
    if _calendar_instance is None:
        _calendar_instance = CalendarManager(log_callback)
    return _calendar_instance
