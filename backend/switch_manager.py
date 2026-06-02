"""
switch_manager.py - 스위치 관리 모듈
IndieBiz OS Core

스위치는 프로젝트 독립적인 "원클릭 실행" 명령입니다.
"""

import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any


class SwitchManager:
    """스위치 저장/로드/관리"""

    def __init__(self):
        # 데이터 경로 (프로덕션에서는 환경변수 사용)
        import os
        base = Path(os.environ.get("INDIEBIZ_BASE_PATH", str(Path(__file__).parent.parent)))
        self.data_path = base / "data"
        self.switches_file = self.data_path / "switches.json"

        # 디렉토리 생성
        self.data_path.mkdir(parents=True, exist_ok=True)

        # switches.json 없으면 생성
        if not self.switches_file.exists():
            self._save_switches([])

    def _load_switches(self) -> List[Dict]:
        """스위치 목록 로드"""
        try:
            with open(self.switches_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save_switches(self, switches: List[Dict]):
        """스위치 목록 저장"""
        with open(self.switches_file, "w", encoding="utf-8") as f:
            json.dump(switches, f, ensure_ascii=False, indent=2)

    def list_switches(self) -> List[Dict]:
        """모든 스위치 목록 반환"""
        return self._load_switches()

    def get_switch(self, switch_id: str) -> Optional[Dict]:
        """특정 스위치 조회"""
        switches = self._load_switches()
        for switch in switches:
            if switch["id"] == switch_id:
                return switch
        return None

    def create_switch(
        self,
        name: str,
        command: str,
        config: Dict[str, Any],
        icon: str = "⚡",
        description: str = ""
    ) -> Dict:
        """새 스위치 생성"""
        switches = self._load_switches()

        switch = {
            "id": str(uuid.uuid4())[:8],
            "name": name,
            "type": "switch",
            "icon": icon,
            "description": description,
            "command": command,
            "created": datetime.now().isoformat(),
            "last_run": None,
            "run_count": 0,
            "icon_position": [100, 100],
            "parent_folder": None,
            "in_trash": False,
            "config": config
        }

        switches.append(switch)
        self._save_switches(switches)

        return switch

    def update_switch(self, switch_id: str, updates: Dict) -> Optional[Dict]:
        """스위치 업데이트"""
        switches = self._load_switches()

        for i, switch in enumerate(switches):
            if switch["id"] == switch_id:
                if "config" in updates:
                    switch["config"].update(updates.pop("config"))
                switch.update(updates)
                switches[i] = switch
                self._save_switches(switches)
                return switch

        return None

    def delete_switch(self, switch_id: str) -> bool:
        """스위치 삭제"""
        switches = self._load_switches()
        original_len = len(switches)
        switches = [s for s in switches if s["id"] != switch_id]

        if len(switches) < original_len:
            self._save_switches(switches)
            return True
        return False

    def record_run(self, switch_id: str):
        """실행 기록 업데이트"""
        switches = self._load_switches()

        for i, switch in enumerate(switches):
            if switch["id"] == switch_id:
                switch["last_run"] = datetime.now().isoformat()
                switch["run_count"] = switch.get("run_count", 0) + 1
                switches[i] = switch
                self._save_switches(switches)
                return

    def update_position(self, switch_id: str, x: int, y: int):
        """스위치 위치 업데이트"""
        switches = self._load_switches()

        for i, switch in enumerate(switches):
            if switch["id"] == switch_id:
                switch["icon_position"] = [x, y]
                switches[i] = switch
                self._save_switches(switches)
                return

    def move_to_trash(self, switch_id: str):
        """스위치를 휴지통으로 이동"""
        switches = self._load_switches()

        for i, switch in enumerate(switches):
            if switch["id"] == switch_id:
                switch["in_trash"] = True
                switch["parent_folder"] = None
                switches[i] = switch
                self._save_switches(switches)
                return True
        return False

    def restore_from_trash(self, switch_id: str):
        """스위치를 휴지통에서 복원"""
        switches = self._load_switches()

        for i, switch in enumerate(switches):
            if switch["id"] == switch_id:
                switch["in_trash"] = False
                switches[i] = switch
                self._save_switches(switches)
                return True
        return False

    def list_trashed_switches(self) -> List[Dict]:
        """휴지통의 스위치 목록"""
        switches = self._load_switches()
        return [s for s in switches if s.get("in_trash", False)]

    def empty_trash(self):
        """휴지통 비우기 (스위치 영구 삭제)"""
        switches = self._load_switches()
        switches = [s for s in switches if not s.get("in_trash", False)]
        self._save_switches(switches)

    def rename_switch(self, switch_id: str, new_name: str) -> Optional[Dict]:
        """스위치 이름 변경"""
        if not new_name or not new_name.strip():
            return None

        new_name = new_name.strip()
        switches = self._load_switches()

        for i, switch in enumerate(switches):
            if switch["id"] == switch_id:
                switch["name"] = new_name
                switches[i] = switch
                self._save_switches(switches)
                return switch

        return None

    def copy_switch(self, switch_id: str, new_position: tuple = None) -> Optional[Dict]:
        """스위치 복사"""
        switches = self._load_switches()

        for switch in switches:
            if switch["id"] == switch_id:
                import copy as copy_module
                new_switch = copy_module.deepcopy(switch)
                new_switch["id"] = str(uuid.uuid4())[:8]
                new_switch["name"] = f"{switch['name']} 사본"
                new_switch["created"] = datetime.now().isoformat()
                new_switch["last_run"] = None
                new_switch["run_count"] = 0

                if new_position:
                    new_switch["icon_position"] = list(new_position)
                else:
                    pos = switch.get("icon_position", [100, 100])
                    new_switch["icon_position"] = [pos[0] + 30, pos[1] + 30]

                switches.append(new_switch)
                self._save_switches(switches)
                return new_switch

        return None
