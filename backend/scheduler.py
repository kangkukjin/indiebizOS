"""
scheduler.py - 프로그램 스케줄러
IndieBiz OS Core

정해진 시간에 작업을 자동으로 실행합니다.
에이전트 없이 백그라운드에서 동작합니다.
"""

import json
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

# 설정 파일 경로
BASE_PATH = Path(__file__).parent.parent
DATA_PATH = BASE_PATH / "data"
SCHEDULE_CONFIG_PATH = DATA_PATH / "program_schedule.json"


class ProgramScheduler:
    """프로그램 스케줄러"""

    def __init__(self, log_callback: Callable[[str], None] = None):
        self.log_callback = log_callback or print
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.config = self._load_config()

        # 작업 함수 등록 (기본 작업)
        self.actions: Dict[str, Callable] = {
            "test": self._action_test,
        }

    def _log(self, message: str):
        """로그 출력"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        full_message = f"[스케줄러 {timestamp}] {message}"
        self.log_callback(full_message)

    def _load_config(self) -> dict:
        """설정 로드"""
        if SCHEDULE_CONFIG_PATH.exists():
            try:
                with open(SCHEDULE_CONFIG_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {"tasks": []}

    def _save_config(self):
        """설정 저장"""
        SCHEDULE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SCHEDULE_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    def get_tasks(self) -> List[dict]:
        """작업 목록 반환"""
        return self.config.get("tasks", [])

    def add_task(self, name: str, description: str, time_str: str,
                 action: str, enabled: bool = True) -> dict:
        """작업 추가"""
        task_id = f"task_{int(datetime.now().timestamp())}"
        task = {
            "id": task_id,
            "name": name,
            "description": description,
            "time": time_str,
            "enabled": enabled,
            "action": action,
            "last_run": None
        }
        self.config["tasks"].append(task)
        self._save_config()
        self._log(f"작업 추가됨: {name}")
        return task

    def update_task(self, task_id: str, **kwargs) -> bool:
        """작업 수정"""
        for task in self.config["tasks"]:
            if task["id"] == task_id:
                task.update(kwargs)
                self._save_config()
                self._log(f"작업 수정됨: {task.get('name', task_id)}")
                return True
        return False

    def delete_task(self, task_id: str) -> bool:
        """작업 삭제"""
        original_len = len(self.config["tasks"])
        self.config["tasks"] = [t for t in self.config["tasks"] if t["id"] != task_id]
        if len(self.config["tasks"]) < original_len:
            self._save_config()
            self._log(f"작업 삭제됨: {task_id}")
            return True
        return False

    def toggle_task(self, task_id: str) -> Optional[bool]:
        """작업 활성화/비활성화 토글"""
        for task in self.config["tasks"]:
            if task["id"] == task_id:
                task["enabled"] = not task["enabled"]
                self._save_config()
                status = "활성화" if task["enabled"] else "비활성화"
                self._log(f"작업 {status}: {task.get('name', task_id)}")
                return task["enabled"]
        return None

    def register_action(self, name: str, func: Callable):
        """작업 함수 등록"""
        self.actions[name] = func
        self._log(f"작업 함수 등록됨: {name}")

    def start(self):
        """스케줄러 시작"""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        self._log("프로그램 스케줄러 시작됨")

    def stop(self):
        """스케줄러 중지"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        self._log("프로그램 스케줄러 중지됨")

    def is_running(self) -> bool:
        """실행 중 여부"""
        return self.running

    def _run_loop(self):
        """스케줄러 메인 루프"""
        while self.running:
            now = datetime.now()
            current_time = now.strftime("%H:%M")

            for task in self.config.get("tasks", []):
                if not task.get("enabled", True):
                    continue

                if task.get("time") != current_time:
                    continue

                # 오늘 이미 실행했는지 확인
                last_run = task.get("last_run")
                if last_run:
                    try:
                        last_run_date = datetime.fromisoformat(last_run).date()
                        if last_run_date == now.date():
                            continue
                    except:
                        pass

                # 작업 실행 (별도 스레드)
                threading.Thread(
                    target=self._execute_task,
                    args=(task,),
                    daemon=True
                ).start()

            # 1분마다 체크
            time.sleep(60)

    def _execute_task(self, task: dict):
        """작업 실행"""
        action_name = task.get("action")
        action_func = self.actions.get(action_name)

        if not action_func:
            self._log(f"알 수 없는 작업: {action_name}")
            return

        self._log(f"작업 시작: {task['name']}")

        try:
            result = action_func(task)

            # 마지막 실행 시간 기록
            task["last_run"] = datetime.now().isoformat()
            self._save_config()

            self._log(f"작업 완료: {task['name']}")
            return result

        except Exception as e:
            self._log(f"작업 실패: {task['name']} - {str(e)}")
            return None

    def run_task_now(self, task_id: str) -> bool:
        """작업 즉시 실행"""
        for task in self.config["tasks"]:
            if task["id"] == task_id:
                threading.Thread(
                    target=self._execute_task,
                    args=(task,),
                    daemon=True
                ).start()
                return True
        return False

    # =========================================================================
    # 기본 작업 함수
    # =========================================================================

    def _action_test(self, task: dict):
        """테스트 작업"""
        self._log(f"테스트 작업 실행: {task.get('name', 'unknown')}")
        return {"success": True, "message": "테스트 완료"}


# 싱글톤 인스턴스
_scheduler_instance: Optional[ProgramScheduler] = None


def get_scheduler(log_callback: Callable[[str], None] = None) -> ProgramScheduler:
    """스케줄러 인스턴스 반환"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = ProgramScheduler(log_callback)
    return _scheduler_instance
