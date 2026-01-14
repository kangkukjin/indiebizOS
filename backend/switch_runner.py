"""
switch_runner.py - 스위치 실행 엔진
IndieBiz OS Core

스위치에 저장된 설정으로 에이전트를 실행합니다.
"""

import threading
from datetime import datetime
from typing import Dict, Any, Optional, Callable

from ai_agent import AIAgent


class SwitchRunner:
    """스위치 실행기"""

    def __init__(self, switch: Dict, on_status: Callable[[str], None] = None):
        """
        Args:
            switch: 스위치 정보 (config 포함)
            on_status: 상태 콜백 함수
        """
        self.switch = switch
        self.config = switch.get("config", {})
        self.on_status = on_status or print
        self.running = False
        self.result = None

    def _status(self, message: str):
        """상태 메시지 전달"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.on_status(f"[{timestamp}] {message}")

    def run(self) -> Dict[str, Any]:
        """
        스위치 동기 실행

        Returns:
            {"success": bool, "message": str, "result": Any}
        """
        self.running = True
        self._status(f"스위치 '{self.switch.get('name', 'unknown')}' 실행 시작")

        try:
            # AI 설정
            ai_config = self.config.get("ai", {})

            if not ai_config.get("api_key"):
                return {
                    "success": False,
                    "message": "API 키가 설정되지 않았습니다.",
                    "result": None
                }

            # 에이전트 이름과 역할
            agent_name = self.config.get("agent_name", "스위치 에이전트")
            agent_role = self.config.get("agent_role", "")
            common_prompt = self.config.get("common_prompt", "")
            allowed_tools = self.config.get("tools", [])

            # 도구 로드
            from tool_loader import load_installed_tools
            all_tools = load_installed_tools()

            # allowed_tools가 있으면 필터링, 없으면 전체 사용
            if allowed_tools:
                tools = [t for t in all_tools if t.get("name") in allowed_tools]
            else:
                tools = all_tools

            self._status(f"도구 {len(tools)}개 로드됨")

            # 시스템 프롬프트 구성
            system_prompt = f"당신은 '{agent_name}'입니다.\n"
            if agent_role:
                system_prompt += f"\n# 역할\n{agent_role}\n"
            if common_prompt:
                system_prompt += f"\n# 공통 지침\n{common_prompt}\n"

            # AI 에이전트 생성
            agent = AIAgent(
                ai_config=ai_config,
                system_prompt=system_prompt,
                agent_name=agent_name,
                tools=tools
            )

            # 명령 실행
            command = self.switch.get("command", "")
            self._status(f"명령 실행: {command}")

            response = agent.process_message_with_history(
                message_content=command,
                from_email="switch@system",
                history=[]
            )

            self._status("실행 완료")
            self.result = {
                "success": True,
                "message": "스위치 실행 완료",
                "result": response
            }

        except Exception as e:
            import traceback
            error_msg = f"스위치 실행 실패: {str(e)}"
            self._status(error_msg)
            traceback.print_exc()

            self.result = {
                "success": False,
                "message": error_msg,
                "result": None
            }

        finally:
            self.running = False

        return self.result

    def run_async(self, callback: Callable[[Dict], None] = None):
        """비동기 실행"""
        def _run():
            result = self.run()
            if callback:
                callback(result)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return thread

    def is_running(self) -> bool:
        """실행 중 여부"""
        return self.running

    def get_result(self) -> Optional[Dict]:
        """결과 반환"""
        return self.result
