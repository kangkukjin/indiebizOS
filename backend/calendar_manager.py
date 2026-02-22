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
"""

import json
import time
import uuid
import calendar
import subprocess
import platform
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


class CalendarManager:
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

    def list_events(self, year: int = None, month: int = None) -> List[dict]:
        """이벤트 목록 조회"""
        events = self.config.get("events", [])
        if year is None and month is None:
            return events

        result = []
        for evt in events:
            evt_date = evt.get("date", "")
            if not evt_date:
                # daily/interval 등 date 없이 time만 있는 이벤트
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
                # none (1회성)
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
                  interval_hours: int = None) -> dict:
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
        if event_time:
            event["time"] = event_time

        # 실행 가능 이벤트 필드
        if action:
            event["action"] = action
        if action_params:
            event["action_params"] = action_params

        # 반복 유형별 추가 필드
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
                      "month", "day", "interval_hours")
        events = self.config.get("events", [])
        for evt in events:
            if evt["id"] == event_id:
                for key, value in kwargs.items():
                    if key in valid_keys:
                        evt[key] = value
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
        # time 키를 매핑
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
    # 실행 루프 (기존 scheduler.py에서 이전)
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
                # action이 있는 이벤트만 실행 대상
                if not evt.get("action"):
                    continue
                if self._should_run_task(evt, now):
                    threading.Thread(
                        target=self._execute_task,
                        args=(evt,),
                        daemon=True
                    ).start()

            # 1분마다 체크
            time.sleep(60)

    def _should_run_task(self, task: dict, now: datetime) -> bool:
        """작업 실행 여부 판단"""
        if not task.get("enabled", True):
            return False

        current_time = now.strftime("%H:%M")
        repeat = task.get("repeat", "daily")

        # 시간 체크 (interval 제외)
        if repeat != "interval" and task.get("time") != current_time:
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
            # 1회: 지정 날짜가 오늘인지 + 아직 실행 안 했는지
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
            # 매월: date의 day와 현재 day 비교
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

            # 마지막 실행 시간 기록
            task["last_run"] = datetime.now().isoformat()

            # none 유형이면 실행 후 자동 비활성화
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

    # =========================================================================
    # 액션 함수 (기존 scheduler.py에서 이전)
    # =========================================================================

    def _action_test(self, task: dict):
        """테스트 작업"""
        self._log(f"테스트 작업 실행: {task.get('title', 'unknown')}")
        return {"success": True, "message": "테스트 완료"}

    def _action_run_switch(self, task: dict):
        """스위치 실행 작업"""
        params = task.get("action_params", {})
        switch_id = params.get("switch_id")

        if not switch_id:
            self._log(f"스위치 ID가 없습니다: {task.get('title')}")
            return {"success": False, "error": "switch_id 누락"}

        try:
            from switch_manager import SwitchManager
            from switch_runner import SwitchRunner

            sm = SwitchManager()
            switch = sm.get_switch(switch_id)

            if not switch:
                self._log(f"스위치를 찾을 수 없습니다: {switch_id}")
                return {"success": False, "error": f"스위치 없음: {switch_id}"}

            self._log(f"스위치 실행: {switch.get('name', switch_id)}")
            runner = SwitchRunner(switch, on_status=self._log)
            result = runner.run()

            sm.record_run(switch_id)

            try:
                from notification_manager import get_notification_manager
                nm = get_notification_manager()
                if result.get("success"):
                    nm.success(
                        title="스케줄 실행 완료",
                        message=f"'{switch.get('name')}' 스위치가 성공적으로 실행되었습니다.",
                        source="scheduler"
                    )
                else:
                    nm.warning(
                        title="스케줄 실행 실패",
                        message=f"'{switch.get('name')}' 스위치 실행 중 오류: {result.get('message', '알 수 없는 오류')}",
                        source="scheduler"
                    )
            except Exception:
                pass

            return result

        except Exception as e:
            self._log(f"스위치 실행 오류: {str(e)}")
            return {"success": False, "error": str(e)}

    def _action_run_workflow(self, task: dict):
        """워크플로우 실행 작업"""
        params = task.get("action_params", {})
        workflow_id = params.get("workflow_id")

        if not workflow_id:
            self._log(f"워크플로우 ID가 없습니다: {task.get('title')}")
            return {"success": False, "error": "workflow_id 누락"}

        try:
            from workflow_engine import execute_workflow

            self._log(f"워크플로우 실행: {workflow_id}")
            result = execute_workflow(workflow_id, ".")

            try:
                from notification_manager import get_notification_manager
                nm = get_notification_manager()
                if result.get("success"):
                    nm.success(
                        title="워크플로우 실행 완료",
                        message=f"'{workflow_id}' 워크플로우가 성공적으로 실행되었습니다. ({result.get('steps_completed', 0)}/{result.get('steps_total', 0)} steps)",
                        source="scheduler"
                    )
                else:
                    nm.warning(
                        title="워크플로우 실행 실패",
                        message=f"'{workflow_id}' 워크플로우 실행 중 오류: {result.get('error', '알 수 없는 오류')}",
                        source="scheduler"
                    )
            except Exception:
                pass

            return result

        except Exception as e:
            self._log(f"워크플로우 실행 오류: {str(e)}")
            return {"success": False, "error": str(e)}

    def _action_run_pipeline(self, task: dict):
        """IBL 파이프라인 실행 작업 (Phase 8: 이벤트 트리거)"""
        import time as _time

        params = task.get("action_params", {})
        pipeline = params.get("pipeline", "")
        trigger_id = params.get("trigger_id")

        if not pipeline:
            self._log(f"파이프라인이 없습니다: {task.get('title')}")
            return {"success": False, "error": "pipeline 누락"}

        try:
            from ibl_parser import parse as ibl_parse, IBLSyntaxError
            from workflow_engine import execute_pipeline

            start = _time.time()

            # IBL 코드 파싱
            try:
                steps = ibl_parse(pipeline)
            except IBLSyntaxError as e:
                self._log(f"IBL 문법 오류: {e}")
                return {"success": False, "error": f"IBL 문법 오류: {e}"}

            # 파이프라인 실행
            self._log(f"파이프라인 실행: {pipeline[:60]}...")
            result = execute_pipeline(steps, ".")
            duration_ms = int((_time.time() - start) * 1000)

            # 트리거 이력 기록
            if trigger_id:
                try:
                    from event_engine import _add_history
                    _add_history(
                        trigger_id=trigger_id,
                        trigger_name=task.get("title", ""),
                        success=result.get("success", False),
                        result_summary=str(result.get("final_result", ""))[:500],
                        duration_ms=duration_ms
                    )
                except Exception:
                    pass

            # 알림
            try:
                from notification_manager import get_notification_manager
                nm = get_notification_manager()
                if result.get("success"):
                    nm.success(
                        title="IBL 파이프라인 실행 완료",
                        message=f"'{task.get('title')}' ({result.get('steps_completed', 0)}/{result.get('steps_total', 0)} steps, {duration_ms}ms)",
                        source="scheduler"
                    )
                else:
                    nm.warning(
                        title="IBL 파이프라인 실행 실패",
                        message=f"'{task.get('title')}': {result.get('error', '알 수 없는 오류')}",
                        source="scheduler"
                    )
            except Exception:
                pass

            return result

        except Exception as e:
            self._log(f"파이프라인 실행 오류: {str(e)}")
            return {"success": False, "error": str(e)}

    def _action_send_notification(self, task: dict):
        """알림 전송 작업"""
        params = task.get("action_params", {})
        message = params.get("message", task.get("description", ""))
        title = params.get("title", task.get("title", "스케줄 알림"))
        noti_type = params.get("type", "info")

        try:
            from notification_manager import get_notification_manager
            nm = get_notification_manager()
            notification = nm.create(
                title=title,
                message=message,
                type=noti_type,
                source="scheduler"
            )
            self._log(f"알림 전송: {title}")
            return {"success": True, "notification_id": notification["id"]}
        except Exception as e:
            self._log(f"알림 전송 실패: {str(e)}")
            return {"success": False, "error": str(e)}

    # =========================================================================
    # 캘린더 보기 (HTML 생성)
    # =========================================================================

    def get_events_for_month(self, year: int, month: int) -> Dict[int, List[dict]]:
        """특정 월의 이벤트를 날짜별로 정리 (반복 이벤트 확장 포함)"""
        events = self.config.get("events", [])
        _, days_in_month = calendar.monthrange(year, month)
        result: Dict[int, List[dict]] = {}

        for evt in events:
            evt_date_str = evt.get("date", "")
            if not evt_date_str:
                continue

            try:
                evt_date = datetime.strptime(evt_date_str, "%Y-%m-%d").date()
            except ValueError:
                continue

            repeat = evt.get("repeat", "none")

            if repeat == "none":
                if evt_date.year == year and evt_date.month == month:
                    result.setdefault(evt_date.day, []).append(evt)

            elif repeat == "yearly":
                if evt_date.month == month and evt_date.day <= days_in_month:
                    result.setdefault(evt_date.day, []).append(evt)

            elif repeat == "monthly":
                if evt_date.day <= days_in_month:
                    result.setdefault(evt_date.day, []).append(evt)

            elif repeat == "weekly":
                target_weekday = evt_date.weekday()
                for d in range(1, days_in_month + 1):
                    if date(year, month, d).weekday() == target_weekday:
                        result.setdefault(d, []).append(evt)

            elif repeat == "daily":
                for d in range(1, days_in_month + 1):
                    result.setdefault(d, []).append(evt)

        return result

    def generate_calendar_html(self, year: int = None, month: int = None) -> str:
        """월간 달력 HTML 생성"""
        today = date.today()
        if year is None:
            year = today.year
        if month is None:
            month = today.month

        all_events = self.config.get("events", [])
        month_events = self.get_events_for_month(year, month)

        cal = calendar.Calendar(firstweekday=0)
        month_days = cal.monthdayscalendar(year, month)

        month_names = [
            "", "1월", "2월", "3월", "4월", "5월", "6월",
            "7월", "8월", "9월", "10월", "11월", "12월"
        ]
        weekday_names = ["월", "화", "수", "목", "금", "토", "일"]

        html = self._build_html(
            year, month, today, all_events, month_events,
            month_days, month_names, weekday_names
        )

        OUTPUTS_PATH.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUTS_PATH / "calendar.html"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        return str(output_path)

    def _build_html(self, year, month, today, all_events, month_events,
                    month_days, month_names, weekday_names) -> str:
        """HTML 달력 생성"""
        events_json = json.dumps(all_events, ensure_ascii=False)

        cells_html = ""
        for week in month_days:
            cells_html += "<tr>"
            for i, day_num in enumerate(week):
                if day_num == 0:
                    cells_html += '<td class="empty"></td>'
                else:
                    is_today = (year == today.year and month == today.month and day_num == today.day)
                    day_class = "today" if is_today else ""
                    if i >= 5:
                        day_class += " weekend"
                    if i == 6:
                        day_class += " sunday"

                    day_events = month_events.get(day_num, [])
                    events_html = ""
                    for evt in day_events[:3]:
                        evt_type = evt.get("type", "other")
                        emoji = EVENT_TYPE_EMOJI.get(evt_type, "")
                        color = EVENT_TYPE_COLORS.get(evt_type, "#607d8b")
                        evt_time = evt.get("time", "")
                        time_str = f"{evt_time} " if evt_time else ""
                        title = evt.get("title", "")
                        events_html += f'<div class="event" style="border-left: 3px solid {color};" title="{time_str}{title}">{emoji} {title}</div>'
                    if len(day_events) > 3:
                        events_html += f'<div class="event-more">+{len(day_events) - 3}개 더</div>'

                    cells_html += f'<td class="{day_class}"><div class="day-number">{day_num}</div>{events_html}</td>'
            cells_html += "</tr>"

        all_events_sorted = sorted(all_events, key=lambda e: e.get("date", "") or "9999")
        sidebar_html = ""
        for evt in all_events_sorted:
            evt_type = evt.get("type", "other")
            emoji = EVENT_TYPE_EMOJI.get(evt_type, "")
            color = EVENT_TYPE_COLORS.get(evt_type, "#607d8b")
            label = EVENT_TYPE_LABELS.get(evt_type, "기타")
            repeat = evt.get("repeat", "none")
            repeat_label = {"none": "", "yearly": "매년", "monthly": "매월", "weekly": "매주", "daily": "매일", "interval": "간격"}.get(repeat, "")
            evt_time = evt.get("time", "")
            action = evt.get("action")
            action_label = ""
            if action:
                action_label = f'<span class="event-action">{action}</span>'

            sidebar_html += f'''
            <div class="event-card">
                <div class="event-card-header">
                    <span class="event-emoji">{emoji}</span>
                    <span class="event-title">{evt.get("title", "")}</span>
                </div>
                <div class="event-card-meta">
                    <span class="event-date">{evt.get("date", "") or "매일"}</span>
                    {f'<span class="event-time">{evt_time}</span>' if evt_time else ''}
                    <span class="event-badge" style="background: {color}22; color: {color};">{label}</span>
                    {f'<span class="event-repeat">{repeat_label}</span>' if repeat_label else ''}
                    {action_label}
                </div>
                {f'<div class="event-desc">{evt.get("description", "")}</div>' if evt.get("description") else ''}
            </div>'''

        return f'''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>IndieBiz 캘린더 - {year}년 {month_names[month]}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans KR', sans-serif;
            background: #f5f0eb;
            color: #333;
        }}
        .container {{
            display: flex;
            height: 100vh;
            gap: 0;
        }}
        .calendar-main {{
            flex: 1;
            display: flex;
            flex-direction: column;
            padding: 24px;
            min-width: 0;
        }}
        .calendar-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 20px;
        }}
        .calendar-title {{
            font-size: 24px;
            font-weight: 700;
            color: #4a3f35;
        }}
        .nav-buttons {{
            display: flex;
            gap: 8px;
        }}
        .nav-btn {{
            padding: 8px 16px;
            border: 1px solid #d4c9bc;
            background: white;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            color: #6b5b4f;
            transition: all 0.2s;
        }}
        .nav-btn:hover {{
            background: #ede7df;
            border-color: #b8a99c;
        }}
        .nav-btn.today-btn {{
            background: #6b5b4f;
            color: white;
            border-color: #6b5b4f;
        }}
        .nav-btn.today-btn:hover {{
            background: #5a4a3f;
        }}
        .calendar-table {{
            width: 100%;
            border-collapse: collapse;
            table-layout: fixed;
            flex: 1;
        }}
        .calendar-table th {{
            padding: 10px 4px;
            text-align: center;
            font-size: 13px;
            font-weight: 600;
            color: #8b7d72;
            border-bottom: 2px solid #d4c9bc;
        }}
        .calendar-table th:nth-child(6) {{ color: #2196f3; }}
        .calendar-table th:nth-child(7) {{ color: #e91e63; }}
        .calendar-table td {{
            border: 1px solid #e8e0d8;
            vertical-align: top;
            padding: 4px 6px;
            height: 100px;
            background: white;
            transition: background 0.15s;
        }}
        .calendar-table td:hover {{ background: #faf8f5; }}
        .calendar-table td.empty {{ background: #f9f5f0; }}
        .calendar-table td.today {{ background: #fff8e1; border-color: #ffb74d; }}
        .calendar-table td.weekend {{ background: #fafafa; }}
        .day-number {{
            font-size: 14px;
            font-weight: 600;
            color: #4a3f35;
            margin-bottom: 4px;
        }}
        .today .day-number {{
            background: #ff9800;
            color: white;
            width: 26px;
            height: 26px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .sunday .day-number {{ color: #e91e63; }}
        .event {{
            font-size: 11px;
            padding: 2px 4px;
            margin-bottom: 2px;
            border-radius: 3px;
            background: #f8f5f1;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            cursor: default;
        }}
        .event-more {{ font-size: 10px; color: #999; padding: 1px 4px; }}
        .sidebar {{
            width: 320px;
            background: white;
            border-left: 1px solid #e0d8d0;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }}
        .sidebar-header {{
            padding: 20px 20px 16px;
            border-bottom: 1px solid #eee;
        }}
        .sidebar-header h3 {{ font-size: 16px; font-weight: 700; color: #4a3f35; }}
        .sidebar-header p {{ font-size: 12px; color: #999; margin-top: 4px; }}
        .sidebar-body {{ flex: 1; overflow-y: auto; padding: 12px; }}
        .event-card {{
            padding: 12px;
            border: 1px solid #eee;
            border-radius: 8px;
            margin-bottom: 8px;
            transition: box-shadow 0.2s;
        }}
        .event-card:hover {{ box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
        .event-card-header {{ display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }}
        .event-emoji {{ font-size: 16px; }}
        .event-title {{ font-size: 14px; font-weight: 600; color: #333; }}
        .event-card-meta {{ display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }}
        .event-date {{ font-size: 12px; color: #888; }}
        .event-time {{ font-size: 12px; color: #666; font-weight: 500; }}
        .event-badge {{ font-size: 10px; padding: 1px 6px; border-radius: 10px; font-weight: 500; }}
        .event-repeat {{ font-size: 10px; color: #999; background: #f5f5f5; padding: 1px 6px; border-radius: 10px; }}
        .event-action {{ font-size: 10px; color: #4caf50; background: #e8f5e9; padding: 1px 6px; border-radius: 10px; }}
        .event-desc {{ font-size: 12px; color: #777; margin-top: 6px; line-height: 1.4; }}
        .no-events {{ text-align: center; color: #999; padding: 40px 20px; font-size: 14px; }}
        @media (max-width: 900px) {{
            .container {{ flex-direction: column; height: auto; }}
            .sidebar {{ width: 100%; border-left: none; border-top: 1px solid #e0d8d0; }}
            .calendar-table td {{ height: 80px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="calendar-main">
            <div class="calendar-header">
                <div class="calendar-title" id="calendarTitle">{year}년 {month_names[month]}</div>
                <div class="nav-buttons">
                    <button class="nav-btn" onclick="changeMonth(-1)">&larr; 이전</button>
                    <button class="nav-btn today-btn" onclick="goToday()">오늘</button>
                    <button class="nav-btn" onclick="changeMonth(1)">다음 &rarr;</button>
                </div>
            </div>
            <table class="calendar-table">
                <thead>
                    <tr>
                        {''.join(f'<th>{d}</th>' for d in weekday_names)}
                    </tr>
                </thead>
                <tbody id="calendarBody">
                    {cells_html}
                </tbody>
            </table>
        </div>
        <div class="sidebar">
            <div class="sidebar-header">
                <h3>등록된 일정</h3>
                <p>{len(all_events)}개의 일정</p>
            </div>
            <div class="sidebar-body" id="sidebarBody">
                {sidebar_html if sidebar_html else '<div class="no-events">등록된 일정이 없습니다.<br><br>시스템 AI에게 기념일이나 약속을 알려주세요.</div>'}
            </div>
        </div>
    </div>

    <script>
        const allEvents = {events_json};
        let currentYear = {year};
        let currentMonth = {month};
        const todayDate = new Date();

        const monthNames = ["", "1월", "2월", "3월", "4월", "5월", "6월", "7월", "8월", "9월", "10월", "11월", "12월"];
        const typeEmojis = {json.dumps(EVENT_TYPE_EMOJI, ensure_ascii=False)};
        const typeColors = {json.dumps(EVENT_TYPE_COLORS, ensure_ascii=False)};

        function changeMonth(delta) {{
            currentMonth += delta;
            if (currentMonth > 12) {{ currentMonth = 1; currentYear++; }}
            if (currentMonth < 1) {{ currentMonth = 12; currentYear--; }}
            renderCalendar();
        }}

        function goToday() {{
            currentYear = todayDate.getFullYear();
            currentMonth = todayDate.getMonth() + 1;
            renderCalendar();
        }}

        function getDaysInMonth(y, m) {{ return new Date(y, m, 0).getDate(); }}

        function getFirstDayOfMonth(y, m) {{
            let d = new Date(y, m - 1, 1).getDay();
            return d === 0 ? 6 : d - 1;
        }}

        function getEventsForDay(y, m, d) {{
            const result = [];
            const targetDate = new Date(y, m - 1, d);
            const targetWeekday = targetDate.getDay() === 0 ? 6 : targetDate.getDay() - 1;

            allEvents.forEach(evt => {{
                if (!evt.date) {{
                    if (evt.repeat === 'daily') result.push(evt);
                    return;
                }}
                const parts = evt.date.split('-');
                const ey = parseInt(parts[0]);
                const em = parseInt(parts[1]);
                const ed = parseInt(parts[2]);
                const repeat = evt.repeat || 'none';

                if (repeat === 'none') {{
                    if (ey === y && em === m && ed === d) result.push(evt);
                }} else if (repeat === 'yearly') {{
                    if (em === m && ed === d) result.push(evt);
                }} else if (repeat === 'monthly') {{
                    if (ed === d) result.push(evt);
                }} else if (repeat === 'weekly') {{
                    const evtDate = new Date(ey, em - 1, ed);
                    const evtWeekday = evtDate.getDay() === 0 ? 6 : evtDate.getDay() - 1;
                    if (evtWeekday === targetWeekday) result.push(evt);
                }} else if (repeat === 'daily') {{
                    result.push(evt);
                }}
            }});
            return result;
        }}

        function renderCalendar() {{
            document.getElementById('calendarTitle').textContent = currentYear + '년 ' + monthNames[currentMonth];
            const daysInMonth = getDaysInMonth(currentYear, currentMonth);
            const firstDay = getFirstDayOfMonth(currentYear, currentMonth);

            let html = '';
            let dayCount = 1;
            const totalCells = Math.ceil((firstDay + daysInMonth) / 7) * 7;

            for (let i = 0; i < totalCells; i++) {{
                if (i % 7 === 0) html += '<tr>';
                if (i < firstDay || dayCount > daysInMonth) {{
                    html += '<td class="empty"></td>';
                }} else {{
                    const d = dayCount;
                    const isToday = (currentYear === todayDate.getFullYear() && currentMonth === todayDate.getMonth() + 1 && d === todayDate.getDate());
                    const weekdayIdx = i % 7;
                    let cls = '';
                    if (isToday) cls += ' today';
                    if (weekdayIdx >= 5) cls += ' weekend';
                    if (weekdayIdx === 6) cls += ' sunday';

                    const dayEvents = getEventsForDay(currentYear, currentMonth, d);
                    let evtHtml = '';
                    dayEvents.slice(0, 3).forEach(evt => {{
                        const t = evt.type || 'other';
                        const emoji = typeEmojis[t] || '';
                        const color = typeColors[t] || '#607d8b';
                        const timeStr = evt.time ? evt.time + ' ' : '';
                        evtHtml += '<div class="event" style="border-left: 3px solid ' + color + ';" title="' + timeStr + evt.title + '">' + emoji + ' ' + evt.title + '</div>';
                    }});
                    if (dayEvents.length > 3) {{
                        evtHtml += '<div class="event-more">+' + (dayEvents.length - 3) + '개 더</div>';
                    }}
                    html += '<td class="' + cls + '"><div class="day-number">' + d + '</div>' + evtHtml + '</td>';
                    dayCount++;
                }}
                if (i % 7 === 6) html += '</tr>';
            }}
            document.getElementById('calendarBody').innerHTML = html;
        }}
    </script>
</body>
</html>'''

    def open_in_browser(self, year: int = None, month: int = None) -> str:
        """캘린더 HTML 생성 후 브라우저에서 열기"""
        file_path = self.generate_calendar_html(year, month)

        system = platform.system()
        try:
            if system == 'Darwin':
                subprocess.run(['open', file_path], check=True)
            elif system == 'Windows':
                import os
                os.startfile(file_path)
            else:
                subprocess.run(['xdg-open', file_path], check=True)
        except Exception as e:
            print(f"[CalendarManager] 브라우저 열기 실패: {e}")

        return file_path


# ============ 싱글톤 ============

_calendar_instance: Optional[CalendarManager] = None


def get_calendar_manager(log_callback: Callable[[str], None] = None) -> CalendarManager:
    """CalendarManager 인스턴스 반환 (싱글톤)"""
    global _calendar_instance
    if _calendar_instance is None:
        _calendar_instance = CalendarManager(log_callback)
    return _calendar_instance
