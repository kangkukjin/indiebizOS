"""
switch_runner.py - 스위치 실행 엔진
IndieBiz OS Core

스위치에 저장된 설정으로 에이전트를 실행합니다.
Phase 17: execute_ibl 단일 도구 + IBL 환경 프롬프트 방식
"""

import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List

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

    def _resolve_allowed_nodes(self) -> Optional[List[str]]:
        """스위치의 allowed_nodes를 결정.

        우선순위:
        1. 스위치 config에 allowed_nodes가 있으면 사용
        2. projectId로 프로젝트의 agents.yaml에서 가져옴
        3. 둘 다 없으면 None (전체 노드)
        """
        # 1. 스위치 자체 설정
        nodes = self.config.get("allowed_nodes")
        if nodes:
            return nodes

        # 2. 프로젝트 에이전트에서 가져오기
        project_id = self.config.get("projectId")
        agent_name = self.config.get("agentName") or self.config.get("agent_name")

        if project_id:
            try:
                from runtime_utils import get_base_path
                import yaml

                agents_yaml = get_base_path() / "projects" / project_id / "agents.yaml"
                if agents_yaml.exists():
                    data = yaml.safe_load(agents_yaml.read_text(encoding='utf-8'))
                    agents = data.get("agents", [])

                    # 이름이 일치하는 에이전트 찾기
                    for agent in agents:
                        if agent.get("name") == agent_name or agent.get("id") == agent_name:
                            return agent.get("allowed_nodes")

                    # 이름 매칭 실패 시 첫 번째 활성 에이전트
                    for agent in agents:
                        if agent.get("active", True) and agent.get("allowed_nodes"):
                            return agent.get("allowed_nodes")
            except Exception as e:
                print(f"[SwitchRunner] allowed_nodes 조회 실패: {e}")

        return None  # 전체 노드

    def _get_project_path(self) -> str:
        """스위치가 속한 프로젝트 경로 반환"""
        project_id = self.config.get("projectId")
        if project_id:
            try:
                from runtime_utils import get_base_path
                project_path = get_base_path() / "projects" / project_id
                if project_path.exists():
                    return str(project_path)
            except Exception:
                pass
        return "."

    def run(self) -> Dict[str, Any]:
        """
        스위치 동기 실행 (Phase 17: execute_ibl 단일 도구)

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

            # Phase 17: execute_ibl 단일 도구 로드
            from tool_loader import load_tool_schema
            ibl_schema = load_tool_schema("execute_ibl")
            tools = [ibl_schema] if ibl_schema else []

            self._status(f"IBL 도구 로드됨 (execute_ibl)")

            # Phase 17: IBL 환경 프롬프트 구성
            from prompt_builder import build_agent_prompt
            from ibl_access import build_environment

            # allowed_nodes 결정
            allowed_nodes = self._resolve_allowed_nodes()
            project_path = self._get_project_path()

            # 기본 프롬프트
            system_prompt = build_agent_prompt(
                agent_name=agent_name,
                role=agent_role or "",
                agent_count=1,
                agent_notes="",
                git_enabled=False
            )

            # IBL 환경 주입
            ibl_env = build_environment(
                allowed_nodes=allowed_nodes,
                project_path=project_path
            )
            if ibl_env:
                system_prompt = system_prompt + "\n\n" + ibl_env

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
