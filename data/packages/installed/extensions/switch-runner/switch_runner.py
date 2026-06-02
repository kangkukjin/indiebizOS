"""
switch_runner.py - 스위치 독립 실행 엔진 (다중 에이전트 지원)

스위치에 저장된 설정만으로 에이전트를 실행합니다.
프로젝트 폴더가 없어도 동작합니다.
다른 에이전트에게 위임(call_agent)도 지원합니다.
"""

import sys
import json
import os
import threading
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from datetime import datetime


# 전역 변수: 현재 실행 중인 SwitchRunner (call_agent에서 참조)
_current_switch_runner: Optional['SwitchRunner'] = None


def get_current_switch_runner() -> Optional['SwitchRunner']:
    """현재 실행 중인 SwitchRunner 반환"""
    return _current_switch_runner


class SwitchRunner:
    """스위치 독립 실행 (다중 에이전트 지원)"""
    
    def __init__(self, switch: Dict, on_status: Callable[[str], None] = None):
        """
        Args:
            switch: 스위치 정보 (config 포함)
            on_status: 상태 콜백 함수
        """
        self.switch = switch
        self.config = switch.get("config", {})
        self.on_status = on_status or print
        
        # 작업 디렉토리 설정 - indiebiz 루트 사용
        self.work_dir = Path(__file__).parent
        
        # 다중 에이전트 지원
        self.agents: Dict[str, Any] = {}  # name -> AIAgent
        self.agent_configs: Dict[str, Dict] = {}  # name -> config
        
    def run(self) -> Dict[str, Any]:
        """
        스위치 실행
        
        Returns:
            실행 결과 {"success": bool, "message": str, "result": Any}
        """
        global _current_switch_runner
        _current_switch_runner = self
        
        self._status(f"🚀 스위치 '{self.switch['name']}' 실행 시작...")
        
        try:
            # 1. 환경 설정
            self._setup_environment()
            
            # 2. 모든 에이전트 초기화
            self._init_all_agents()
            
            # 3. 메인 에이전트로 명령 실행
            main_agent_name = self.config.get("agent_name", "집사")
            command = self.switch["command"]
            self._status(f"📝 명령: {command}")
            self._status(f"🎯 메인 에이전트: {main_agent_name}")
            
            result = self._execute_with_agent(main_agent_name, command)
            
            # 4. 실행 기록
            self._record_execution()
            
            self._status(f"✅ 완료!")
            
            return {
                "success": True,
                "message": "스위치 실행 완료",
                "result": result
            }
            
        except Exception as e:
            import traceback
            error_msg = f"스위치 실행 실패: {str(e)}\n{traceback.format_exc()}"
            self._status(f"❌ {error_msg}")
            
            return {
                "success": False,
                "message": error_msg,
                "result": None
            }
        finally:
            _current_switch_runner = None
    
    def run_async(self, callback: Callable[[Dict], None] = None):
        """비동기 실행"""
        def _run():
            result = self.run()
            if callback:
                callback(result)
        
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return thread
    
    def _status(self, message: str):
        """상태 메시지 전달"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.on_status(f"[{timestamp}] {message}")
    
    def _setup_environment(self):
        """환경 설정"""
        # 작업 디렉토리 설정
        if self.work_dir.exists():
            os.chdir(self.work_dir)
            if str(self.work_dir) not in sys.path:
                sys.path.insert(0, str(self.work_dir))
            self._status(f"📂 작업 디렉토리: {self.work_dir}")
        
        # API 키 환경변수 설정 (메인 에이전트 기준)
        ai_config = self.config.get("ai", {})
        
        if "gemini_api_key" in ai_config:
            os.environ["GEMINI_API_KEY"] = ai_config["gemini_api_key"]
        if "openai_api_key" in ai_config:
            os.environ["OPENAI_API_KEY"] = ai_config["openai_api_key"]
        if "anthropic_api_key" in ai_config:
            os.environ["ANTHROPIC_API_KEY"] = ai_config["anthropic_api_key"]
    
    def _init_all_agents(self):
        """모든 에이전트 초기화"""
        all_agents = self.config.get("all_agents", [])
        
        if not all_agents:
            # 하위 호환성: 단일 에이전트만 있는 경우
            self._status("⚠️ 단일 에이전트 모드 (레거시)")
            main_name = self.config.get("agent_name", "스위치")
            self.agent_configs[main_name] = {
                "name": main_name,
                "ai": self.config.get("ai", {}),
                "role": self.config.get("agent_role", ""),
                "note": self.config.get("agent_note", ""),
            }
            return
        
        self._status(f"🤖 {len(all_agents)}개 에이전트 준비 중...")
        
        for agent_info in all_agents:
            name = agent_info.get("name")
            if name:
                self.agent_configs[name] = agent_info
                self._status(f"   ✓ {name}")
        
        # 도구 배분 적용
        self._apply_tool_assignments()
    
    def _apply_tool_assignments(self):
        """저장된 도구 배분을 tool_selector에 적용"""
        tool_assignments = self.config.get("tool_assignments")
        
        if not tool_assignments:
            self._status("⚠️ 도구 배분 정보 없음 (기본 도구 사용)")
            return
        
        try:
            import tool_selector
            
            # 스위치용 가상 SystemDirector 생성
            class SwitchDirector:
                def __init__(self, assignments):
                    self.assignment_map = assignments
                
                def get_tools_for_agent(self, agent_name):
                    return self.assignment_map.get(agent_name, [])
            
            # tool_selector의 director_instance 설정
            tool_selector.director_instance = SwitchDirector(tool_assignments)
            
            self._status(f"🔧 도구 배분 적용 완료: {len(tool_assignments)}개 에이전트")
            for agent_name, tools in tool_assignments.items():
                self._status(f"   {agent_name}: {len(tools)}개 도구")
                
        except Exception as e:
            self._status(f"⚠️ 도구 배분 적용 실패: {e}")
    
    def _get_or_create_agent(self, agent_name: str):
        """에이전트 가져오기 (없으면 생성)"""
        if agent_name in self.agents:
            return self.agents[agent_name]
        
        agent_config = self.agent_configs.get(agent_name)
        if not agent_config:
            raise ValueError(f"에이전트 '{agent_name}'를 찾을 수 없습니다")
        
        # AIAgent 생성
        ai = self._create_ai_agent(agent_name, agent_config)
        self.agents[agent_name] = ai
        
        return ai
    
    def _create_ai_agent(self, agent_name: str, agent_config: Dict):
        """AIAgent 인스턴스 생성"""
        from ai import AIAgent
        
        ai_settings = agent_config.get("ai", {})
        provider = ai_settings.get("provider", "gemini")
        
        # API 키 결정
        if provider == "gemini":
            api_key = ai_settings.get("gemini_api_key") or os.getenv("GEMINI_API_KEY")
            ai_provider = "google"
        elif provider == "anthropic":
            api_key = ai_settings.get("anthropic_api_key") or os.getenv("ANTHROPIC_API_KEY")
            ai_provider = "anthropic"
        elif provider == "openai":
            api_key = ai_settings.get("openai_api_key") or os.getenv("OPENAI_API_KEY")
            ai_provider = "openai"
        else:
            api_key = ai_settings.get("gemini_api_key") or os.getenv("GEMINI_API_KEY")
            ai_provider = "google"
        
        ai_config = {
            "provider": ai_provider,
            "api_key": api_key,
            "model": ai_settings.get("model", "gemini-2.0-flash-exp")
        }
        
        # 시스템 프롬프트 구성
        system_prompt = self._build_system_prompt(agent_config)
        
        # agent_config 구성
        full_agent_config = {
            "name": agent_name,
            "id": agent_config.get("id", f"switch_{agent_name}")
        }
        
        ai = AIAgent(
            ai_config=ai_config,
            system_prompt=system_prompt,
            agent_type=agent_config.get("type", "internal"),
            agent_name=agent_name,
            agent_config=full_agent_config
        )
        
        # Gmail 클라이언트 연결 (메인 에이전트만)
        if agent_name == self.config.get("agent_name"):
            gmail = self._setup_gmail()
            if gmail:
                ai.gmail = gmail
        
        return ai
    
    def _build_system_prompt(self, agent_config: Dict) -> str:
        """시스템 프롬프트 구성"""
        parts = []
        
        # 공통 설정
        if "common_prompt" in self.config:
            parts.append(self.config["common_prompt"])
        
        # 에이전트 역할
        if "role" in agent_config:
            parts.append(agent_config["role"])
        
        # 에이전트 노트
        if "note" in agent_config:
            parts.append(agent_config["note"])
        
        # 스위치 모드 안내 + 사용 가능한 에이전트 목록
        available_agents = list(self.agent_configs.keys())
        parts.append(f"""
[스위치 모드]
이것은 스위치를 통한 자동화된 요청입니다.
요청을 처리하고 결과를 간략히 보고해주세요.

사용 가능한 에이전트: {', '.join(available_agents)}
다른 에이전트에게 작업을 위임하려면 call_agent 도구를 사용하세요.
""")
        
        return "\n\n".join(parts)
    
    def _setup_gmail(self):
        """Gmail 클라이언트 생성"""
        gmail_creds = self.config.get("gmail_credentials")
        gmail_token = self.config.get("gmail_token")
        
        if not gmail_creds:
            self._status("📧 Gmail credentials 없음")
            return None
        
        try:
            from gmail import GmailClient
            
            installed = gmail_creds.get("installed", {})
            
            gmail_config = {
                "client_id": installed.get("client_id"),
                "client_secret": installed.get("client_secret"),
                "token_file": "tokens/switch_token.json",
                "scopes": [
                    'https://www.googleapis.com/auth/gmail.readonly',
                    'https://www.googleapis.com/auth/gmail.send',
                    'https://www.googleapis.com/auth/gmail.modify'
                ]
            }
            
            token_path = self.work_dir / "tokens" / "switch_token.json"
            token_path.parent.mkdir(parents=True, exist_ok=True)
            
            if gmail_token:
                with open(token_path, "w", encoding="utf-8") as f:
                    json.dump(gmail_token, f)
            
            gmail = GmailClient(gmail_config)
            gmail.authenticate()
            
            if token_path.exists():
                with open(token_path, "r", encoding="utf-8") as f:
                    new_token = json.load(f)
                
                if new_token != gmail_token:
                    self._update_switch_token(new_token)
            
            self._status("📧 Gmail 연결 완료")
            return gmail
            
        except Exception as e:
            self._status(f"📧 Gmail 연결 실패: {e}")
            return None
    
    def _update_switch_token(self, new_token: dict):
        """스위치의 gmail_token 업데이트"""
        try:
            from switch_manager import SwitchManager
            sm = SwitchManager()
            sm.update_switch(self.switch["id"], {
                "config": {"gmail_token": new_token}
            })
            self._status("📧 Gmail 토큰 갱신됨")
        except Exception as e:
            self._status(f"⚠️ 토큰 저장 실패: {e}")
    
    def _execute_with_agent(self, agent_name: str, command: str) -> str:
        """특정 에이전트로 명령 실행"""
        ai = self._get_or_create_agent(agent_name)
        
        response = ai.process_message_with_history(
            message_content=command,
            from_email="switch@local",
            history=[]
        )
        
        return response
    
    def call_agent(self, target_agent: str, message: str) -> str:
        """
        다른 에이전트 호출 (call_agent 도구에서 사용)
        
        Args:
            target_agent: 대상 에이전트 이름
            message: 전달할 메시지
            
        Returns:
            에이전트 응답
        """
        self._status(f"📨 {target_agent}에게 위임: {message[:50]}...")
        
        try:
            response = self._execute_with_agent(target_agent, message)
            self._status(f"📩 {target_agent} 응답 수신")
            return response
        except Exception as e:
            error_msg = f"에이전트 '{target_agent}' 호출 실패: {e}"
            self._status(f"❌ {error_msg}")
            return error_msg
    
    def list_agents(self) -> list:
        """사용 가능한 에이전트 목록 반환"""
        return [
            {"name": name, "type": config.get("type", "internal")}
            for name, config in self.agent_configs.items()
        ]
    
    def _record_execution(self):
        """실행 기록"""
        try:
            from switch_manager import SwitchManager
            sm = SwitchManager()
            sm.record_run(self.switch["id"])
        except Exception as e:
            self._status(f"⚠️ 실행 기록 실패: {e}")


# 커맨드라인 실행 지원
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python switch_runner.py <switch_id>")
        sys.exit(1)
    
    switch_id = sys.argv[1]
    
    from switch_manager import SwitchManager
    sm = SwitchManager()
    switch = sm.get_switch(switch_id)
    
    if not switch:
        print(f"스위치를 찾을 수 없습니다: {switch_id}")
        sys.exit(1)
    
    runner = SwitchRunner(switch)
    result = runner.run()
    
    print(f"\n결과: {json.dumps(result, ensure_ascii=False, indent=2)}")
