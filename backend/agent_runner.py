"""
agent_runner.py - 에이전트 실행 엔진
IndieBiz OS Core

에이전트를 백그라운드에서 실행하고 AI 대화를 처리합니다.
"""

import threading
from pathlib import Path
from typing import Dict, Any, Optional

from ai_agent import AIAgent


class AgentRunner:
    """에이전트 실행기"""

    def __init__(self, agent_config: dict, common_config: dict = None):
        self.config = agent_config
        self.common_config = common_config or {}

        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.cancel_event = threading.Event()

        # AI 에이전트
        self.ai: Optional[AIAgent] = None

        # 프로젝트 정보
        self.project_path = Path(agent_config.get("_project_path", "."))
        self.project_id = agent_config.get("_project_id", "")

    def start(self):
        """에이전트 시작"""
        if self.running:
            return

        self.running = True
        self.cancel_event.clear()

        # AI 에이전트 초기화
        self._init_ai()

        # 백그라운드 스레드 시작 (채널 폴링 등)
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

        print(f"[AgentRunner] {self.config.get('name')} 시작됨")

    def stop(self):
        """에이전트 중지"""
        self.running = False
        self.cancel_event.set()

        if self.thread:
            self.thread.join(timeout=5)

        print(f"[AgentRunner] {self.config.get('name')} 중지됨")

    def cancel(self):
        """현재 작업 취소"""
        self.cancel_event.set()

    def _init_ai(self):
        """AI 에이전트 초기화"""
        ai_config = self.config.get("ai", {})
        agent_name = self.config.get("name", "에이전트")

        # 역할 로드
        role_file = self.project_path / f"agent_{agent_name}_role.txt"
        role = ""
        if role_file.exists():
            role = role_file.read_text(encoding='utf-8')

        # 시스템 프롬프트 생성
        system_prompt = self._build_system_prompt(role)

        # AIAgent 생성
        self.ai = AIAgent(
            ai_config=ai_config,
            system_prompt=system_prompt,
            agent_name=agent_name,
            project_path=str(self.project_path)
        )

    def _build_system_prompt(self, role: str) -> str:
        """시스템 프롬프트 구성"""
        agent_name = self.config.get("name", "에이전트")

        parts = [f"당신은 '{agent_name}'입니다."]

        if role:
            parts.append(f"\n# 역할\n{role}")

        # 공통 설정
        common_file = self.project_path / "common_settings.txt"
        if common_file.exists():
            common = common_file.read_text(encoding='utf-8')
            if common.strip():
                parts.append(f"\n# 공통 지침\n{common}")

        # 메모
        note_file = self.project_path / f"agent_{agent_name}_note.txt"
        if note_file.exists():
            note = note_file.read_text(encoding='utf-8')
            if note.strip():
                parts.append(f"\n# 메모\n{note}")

        return "\n".join(parts)

    def _run_loop(self):
        """백그라운드 루프 (채널 폴링 등)"""
        import time

        while self.running and not self.cancel_event.is_set():
            try:
                # TODO: 채널(이메일, Nostr 등) 폴링
                # 현재는 단순 대기
                time.sleep(1)

            except Exception as e:
                print(f"[AgentRunner] 루프 에러: {e}")
                time.sleep(5)
