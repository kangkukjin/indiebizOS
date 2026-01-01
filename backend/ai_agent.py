"""
ai_agent.py - AI 에이전트 (도구 사용 지원)
IndieBiz OS Core

Anthropic, OpenAI, Google Gemini를 지원하는 통합 AI 에이전트
- 도구(tool use) 지원
- 이미지 입력 지원
- 대화 히스토리 지원
"""

import json
import subprocess
import os
import sys
import importlib.util
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path


# ============ 시스템 도구 (필수, 삭제 불가) ============

SYSTEM_TOOLS = [
    {
        "name": "call_agent",
        "description": "다른 에이전트를 호출하여 작업을 요청합니다. 같은 프로젝트 내 에이전트 간 협업에 사용합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "호출할 에이전트 ID"
                },
                "message": {
                    "type": "string",
                    "description": "에이전트에게 전달할 메시지/요청"
                }
            },
            "required": ["agent_id", "message"]
        }
    },
    {
        "name": "list_agents",
        "description": "현재 프로젝트에서 사용 가능한 에이전트 목록을 가져옵니다.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "send_notification",
        "description": "사용자에게 알림을 보냅니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "알림 제목"
                },
                "message": {
                    "type": "string",
                    "description": "알림 내용"
                },
                "type": {
                    "type": "string",
                    "description": "알림 유형: info, success, warning, error. 기본: info"
                }
            },
            "required": ["title", "message"]
        }
    },
    {
        "name": "get_project_info",
        "description": "현재 프로젝트의 정보를 가져옵니다 (이름, 설명, 에이전트 목록 등).",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]


# ============ 설치된 도구 패키지에서 도구 로드 ============

def load_agent_tools(project_path: str, agent_id: str = None) -> List[Dict]:
    """
    에이전트별 도구 로드

    기본: 설치된 모든 도구 사용 가능
    제한: agents.yaml의 allowed_tools가 있으면 해당 도구만 사용
    """
    # 설치된 모든 도구 로드
    base_path = Path(__file__).parent.parent
    tools_path = base_path / "data" / "packages" / "installed" / "tools"

    all_tools = []
    if tools_path.exists():
        for pkg_dir in tools_path.iterdir():
            if not pkg_dir.is_dir() or pkg_dir.name.startswith('.'):
                continue
            tool_json_path = pkg_dir / "tool.json"
            if tool_json_path.exists():
                try:
                    tool_def = json.loads(tool_json_path.read_text(encoding='utf-8'))
                    # {"tools": [...]} 형식
                    if isinstance(tool_def, dict) and "tools" in tool_def:
                        all_tools.extend(tool_def["tools"])
                    # 배열 형식
                    elif isinstance(tool_def, list):
                        all_tools.extend(tool_def)
                    # 단일 도구 형식
                    elif isinstance(tool_def, dict) and "name" in tool_def:
                        all_tools.append(tool_def)
                except Exception as e:
                    print(f"[도구 스캔 실패] {pkg_dir.name}: {e}")

    # agents.yaml에서 에이전트별 allowed_tools 확인
    if agent_id and project_path:
        agents_yaml = Path(project_path) / "agents.yaml"
        if agents_yaml.exists():
            try:
                import yaml
                agents_data = yaml.safe_load(agents_yaml.read_text(encoding='utf-8'))
                for agent in agents_data.get("agents", []):
                    if agent.get("id") == agent_id:
                        allowed = agent.get("allowed_tools", [])
                        if allowed:
                            # allowed_tools가 있으면 해당 도구만 필터링
                            all_tools = [t for t in all_tools if t["name"] in allowed]
                        break
            except Exception as e:
                print(f"[agents.yaml 로드 실패] {e}")

    return all_tools


def load_installed_tools(base_path: str = None) -> List[Dict]:
    """시스템에 설치된 모든 도구 로드 (프로젝트 없을 때 fallback)"""
    if base_path is None:
        base_path = Path(__file__).parent.parent

    tools_path = Path(base_path) / "data" / "packages" / "installed" / "tools"
    extra_tools = []

    if tools_path.exists():
        for tool_dir in tools_path.iterdir():
            if tool_dir.is_dir():
                tool_json = tool_dir / "tool.json"
                if tool_json.exists():
                    try:
                        tool_def = json.loads(tool_json.read_text(encoding='utf-8'))
                        # 배열인 경우 (여러 도구가 한 패키지에)
                        if isinstance(tool_def, list):
                            for t in tool_def:
                                extra_tools.append(t)
                                print(f"[도구 로드] {t.get('name')}")
                        else:
                            extra_tools.append(tool_def)
                            print(f"[도구 로드] {tool_def.get('name')}")
                    except Exception as e:
                        print(f"[도구 로드 실패] {tool_dir.name}: {e}")

    return extra_tools


# ============ 동적 도구 로더 ============

# 도구 핸들러 캐시 (도구 이름 -> 핸들러 모듈)
_tool_handlers_cache: Dict[str, Any] = {}
# 도구 이름 -> 패키지 ID 매핑
_tool_to_package_map: Dict[str, str] = {}


def _build_tool_package_map():
    """설치된 도구 패키지에서 도구 이름 -> 패키지 ID 매핑 구축"""
    global _tool_to_package_map

    if _tool_to_package_map:
        return  # 이미 구축됨

    base_path = Path(__file__).parent.parent
    tools_path = base_path / "data" / "packages" / "installed" / "tools"

    if not tools_path.exists():
        return

    for pkg_dir in tools_path.iterdir():
        if not pkg_dir.is_dir() or pkg_dir.name.startswith('.'):
            continue

        tool_json = pkg_dir / "tool.json"
        if not tool_json.exists():
            continue

        try:
            tool_def = json.loads(tool_json.read_text(encoding='utf-8'))

            # {"tools": [...]} 형식 처리
            if isinstance(tool_def, dict) and "tools" in tool_def:
                for t in tool_def["tools"]:
                    _tool_to_package_map[t["name"]] = pkg_dir.name
            # 배열인 경우 (여러 도구가 한 패키지에)
            elif isinstance(tool_def, list):
                for t in tool_def:
                    _tool_to_package_map[t["name"]] = pkg_dir.name
            # 단일 도구
            elif isinstance(tool_def, dict) and "name" in tool_def:
                _tool_to_package_map[tool_def["name"]] = pkg_dir.name

        except Exception as e:
            print(f"[도구 매핑 실패] {pkg_dir.name}: {e}")


def _load_tool_handler(tool_name: str):
    """도구 핸들러를 동적으로 로드"""
    global _tool_handlers_cache

    # 캐시에 있으면 반환
    if tool_name in _tool_handlers_cache:
        return _tool_handlers_cache[tool_name]

    # 매핑 구축
    _build_tool_package_map()

    # 패키지 ID 찾기
    package_id = _tool_to_package_map.get(tool_name)
    if not package_id:
        return None

    # handler.py 경로
    base_path = Path(__file__).parent.parent
    handler_path = base_path / "data" / "packages" / "installed" / "tools" / package_id / "handler.py"

    if not handler_path.exists():
        print(f"[도구 핸들러 없음] {tool_name} -> {handler_path}")
        return None

    try:
        # 동적 모듈 로드
        spec = importlib.util.spec_from_file_location(f"tool_handler_{package_id}", handler_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # 캐시에 저장
        _tool_handlers_cache[tool_name] = module
        print(f"[도구 핸들러 로드] {tool_name} <- {package_id}")

        return module

    except Exception as e:
        print(f"[도구 핸들러 로드 실패] {tool_name}: {e}")
        return None


# ============ 도구 실행 함수들 ============

def execute_tool(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    """도구 실행 (동적 로딩 지원)"""
    try:
        # 1. 시스템 도구 처리 (call_agent, list_agents, send_notification, get_project_info)
        # ============ 에이전트 간 통신 ============
        if tool_name == "call_agent":
            agent_id = tool_input.get("agent_id", "")
            message = tool_input.get("message", "")

            try:
                # 프로젝트 경로에서 에이전트 설정 로드
                project_json = Path(project_path) / "project.json"
                if not project_json.exists():
                    return json.dumps({"success": False, "error": "프로젝트 설정을 찾을 수 없습니다."}, ensure_ascii=False)

                project_data = json.loads(project_json.read_text(encoding='utf-8'))
                agents = project_data.get("agents", [])

                target_agent = None
                for agent in agents:
                    if agent.get("id") == agent_id:
                        target_agent = agent
                        break

                if not target_agent:
                    return json.dumps({"success": False, "error": f"에이전트를 찾을 수 없습니다: {agent_id}"}, ensure_ascii=False)

                # 에이전트 호출 (agent_runner 사용)
                from agent_runner import AgentRunner
                runner = AgentRunner(project_path)
                response = runner.run_agent(agent_id, message)

                return json.dumps({"success": True, "response": response}, ensure_ascii=False)

            except Exception as e:
                return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

        elif tool_name == "list_agents":
            try:
                project_json = Path(project_path) / "project.json"
                if not project_json.exists():
                    return json.dumps({"success": False, "error": "프로젝트 설정을 찾을 수 없습니다."}, ensure_ascii=False)

                project_data = json.loads(project_json.read_text(encoding='utf-8'))
                agents = project_data.get("agents", [])

                agent_list = []
                for agent in agents:
                    agent_list.append({
                        "id": agent.get("id"),
                        "name": agent.get("name"),
                        "role": agent.get("role", ""),
                        "enabled": agent.get("enabled", True)
                    })

                return json.dumps({"success": True, "agents": agent_list}, ensure_ascii=False)

            except Exception as e:
                return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

        # ============ 알림 ============
        elif tool_name == "send_notification":
            title = tool_input.get("title", "")
            message = tool_input.get("message", "")
            noti_type = tool_input.get("type", "info")

            try:
                from notification_manager import get_notification_manager
                nm = get_notification_manager()
                notification = nm.create(title=title, message=message, type=noti_type)
                return json.dumps({"success": True, "notification_id": notification["id"]}, ensure_ascii=False)
            except Exception as e:
                return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

        # ============ 프로젝트 정보 ============
        elif tool_name == "get_project_info":
            try:
                project_json = Path(project_path) / "project.json"
                if not project_json.exists():
                    return json.dumps({"success": False, "error": "프로젝트 설정을 찾을 수 없습니다."}, ensure_ascii=False)

                project_data = json.loads(project_json.read_text(encoding='utf-8'))

                info = {
                    "name": project_data.get("name", ""),
                    "description": project_data.get("description", ""),
                    "agent_count": len(project_data.get("agents", [])),
                    "agents": [{"id": a.get("id"), "name": a.get("name")} for a in project_data.get("agents", [])],
                    "path": str(project_path)
                }

                return json.dumps({"success": True, "project": info}, ensure_ascii=False)

            except Exception as e:
                return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

        # 2. 동적 로딩된 도구 패키지에서 실행 시도
        else:
            handler = _load_tool_handler(tool_name)
            if handler and hasattr(handler, 'execute'):
                result = handler.execute(tool_name, tool_input, project_path)

                # 승인 필요 여부 확인
                if isinstance(result, str) and result.startswith("__REQUIRES_APPROVAL__:"):
                    command = result.replace("__REQUIRES_APPROVAL__:", "")
                    return json.dumps({
                        "requires_approval": True,
                        "command": command,
                        "message": f"⚠️ 위험한 명령어가 감지되었습니다:\n\n`{command}`\n\n이 명령어를 실행하려면 '승인' 또는 'yes'라고 답해주세요."
                    }, ensure_ascii=False)

                return result
            else:
                return json.dumps({"success": False, "error": f"알 수 없는 도구: {tool_name}"}, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


class AIAgent:
    """AI 에이전트 - 도구 사용 지원"""

    def __init__(
        self,
        ai_config: dict,
        system_prompt: str,
        agent_name: str = "에이전트",
        agent_id: str = None,
        project_path: str = ".",
        tools: List[Dict] = None
    ):
        self.config = ai_config
        self.system_prompt = system_prompt
        self.agent_name = agent_name
        self.agent_id = agent_id
        self.project_path = project_path

        # 시스템 도구 + 프로젝트 기본 도구 + 에이전트별 도구
        if tools is not None:
            self.tools = tools
        else:
            agent_tools = load_agent_tools(project_path, agent_id)
            self.tools = SYSTEM_TOOLS + agent_tools

        self.provider = ai_config.get("provider", "anthropic")
        self.model = ai_config.get("model", "claude-sonnet-4-20250514")
        self.api_key = ai_config.get("api_key", "")

        # 프로바이더별 클라이언트
        self._client = None
        self._init_client()

    def _init_client(self):
        """프로바이더별 클라이언트 초기화"""
        if not self.api_key:
            print(f"[AIAgent] {self.agent_name}: API 키 없음")
            return

        try:
            if self.provider == "anthropic":
                import anthropic
                self._client = anthropic.Anthropic(api_key=self.api_key)
                print(f"[AIAgent] {self.agent_name}: Anthropic 초기화 완료 (도구 {len(self.tools)}개)")

            elif self.provider == "openai":
                import openai
                self._client = openai.OpenAI(api_key=self.api_key)
                print(f"[AIAgent] {self.agent_name}: OpenAI 초기화 완료")

            elif self.provider in ["google", "gemini"]:
                from google import genai
                from google.genai import types

                # Gemini 클라이언트 및 설정 저장
                self._genai_client = genai.Client(api_key=self.api_key)
                self._genai_types = types
                self._client = self._genai_client  # 호환성을 위해
                print(f"[AIAgent] {self.agent_name}: Gemini 초기화 완료 (도구 {len(self.tools) if self.tools else 0}개)")

            else:
                print(f"[AIAgent] 지원하지 않는 프로바이더: {self.provider}")

        except ImportError as e:
            print(f"[AIAgent] 라이브러리 없음: {e}")
        except Exception as e:
            print(f"[AIAgent] 초기화 실패: {e}")

    def process_message_with_history(
        self,
        message_content: str,
        from_email: str = "",
        history: List[Dict] = None,
        reply_to: str = "",
        task_id: str = None,
        images: List[Dict] = None
    ) -> str:
        """
        메시지 처리 (히스토리 포함, 도구 사용 지원)

        Args:
            message_content: 사용자 메시지
            from_email: 발신자
            history: 대화 히스토리 [{"role": "user/assistant", "content": "..."}]
            reply_to: 답장 대상
            task_id: 태스크 ID
            images: 이미지 데이터 [{"base64": "...", "media_type": "image/png"}]

        Returns:
            AI 응답 텍스트
        """
        if not self._client:
            return "AI가 초기화되지 않았습니다. API 키를 확인해주세요."

        history = history or []

        try:
            if self.provider == "anthropic":
                return self._process_anthropic(message_content, history, images)

            elif self.provider == "openai":
                return self._process_openai(message_content, history, images)

            elif self.provider in ["google", "gemini"]:
                return self._process_gemini(message_content, history, images)

            else:
                return f"지원하지 않는 프로바이더: {self.provider}"

        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"AI 응답 생성 실패: {str(e)}"

    def _process_anthropic(self, message: str, history: List[Dict], images: List[Dict] = None) -> str:
        """Anthropic Claude 처리 (도구 사용 지원)"""
        messages = []

        # 히스토리 변환
        for h in history:
            messages.append({
                "role": h["role"],
                "content": h["content"]
            })

        # 현재 메시지
        if images:
            content = []
            for img in images:
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": img.get("media_type", "image/png"),
                        "data": img["base64"]
                    }
                })
            content.append({"type": "text", "text": message})
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": message})

        # 도구가 있으면 도구와 함께 호출
        if self.tools:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=self.system_prompt,
                tools=self.tools,
                messages=messages
            )
        else:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=self.system_prompt,
                messages=messages
            )

        # 도구 사용 처리
        return self._handle_anthropic_response(response, messages)

    def _handle_anthropic_response(self, response, messages: List[Dict], depth: int = 0) -> str:
        """Anthropic 응답 처리 (도구 사용 루프)"""
        if depth > 10:
            return "도구 사용 깊이 제한에 도달했습니다."

        result_parts = []
        tool_results = []

        # 응답 처리
        for block in response.content:
            if block.type == "text":
                result_parts.append(block.text)
            elif block.type == "tool_use":
                print(f"   [도구 사용] {block.name}")

                # 도구 실행
                tool_output = execute_tool(block.name, block.input, self.project_path)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": tool_output
                })

        # 도구 결과가 있으면 후속 호출
        if tool_results:
            # assistant 응답 추가
            messages.append({
                "role": "assistant",
                "content": response.content
            })

            # 도구 결과 추가
            messages.append({
                "role": "user",
                "content": tool_results
            })

            # 후속 호출
            if self.tools:
                followup = self._client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=self.system_prompt,
                    tools=self.tools,
                    messages=messages
                )
            else:
                followup = self._client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=self.system_prompt,
                    messages=messages
                )

            followup_text = self._handle_anthropic_response(followup, messages, depth + 1)
            result_parts.append(followup_text)

        return "\n".join(result_parts)

    def _process_openai(self, message: str, history: List[Dict], images: List[Dict] = None) -> str:
        """OpenAI GPT 처리"""
        messages = [{"role": "system", "content": self.system_prompt}]

        # 히스토리
        for h in history:
            messages.append({
                "role": h["role"],
                "content": h["content"]
            })

        # 현재 메시지
        if images:
            content = []
            for img in images:
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{img.get('media_type', 'image/png')};base64,{img['base64']}"
                    }
                })
            content.append({"type": "text", "text": message})
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": message})

        # OpenAI function calling (도구 지원)
        if self.tools:
            # OpenAI 형식으로 변환
            openai_tools = []
            for tool in self.tools:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("input_schema", {"type": "object", "properties": {}})
                    }
                })

            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=openai_tools,
                max_tokens=4096
            )
        else:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=4096
            )

        return self._handle_openai_response(response, messages)

    def _handle_openai_response(self, response, messages: List[Dict], depth: int = 0) -> str:
        """OpenAI 응답 처리 (도구 사용 루프)"""
        if depth > 10:
            return "도구 사용 깊이 제한에 도달했습니다."

        message = response.choices[0].message

        # 도구 호출이 있는 경우
        if message.tool_calls:
            messages.append(message)

            for tool_call in message.tool_calls:
                print(f"   [도구 사용] {tool_call.function.name}")

                tool_input = json.loads(tool_call.function.arguments)
                tool_output = execute_tool(tool_call.function.name, tool_input, self.project_path)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_output
                })

            # 후속 호출
            if self.tools:
                openai_tools = []
                for tool in self.tools:
                    openai_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool["name"],
                            "description": tool.get("description", ""),
                            "parameters": tool.get("input_schema", {"type": "object", "properties": {}})
                        }
                    })

                followup = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=openai_tools,
                    max_tokens=4096
                )
            else:
                followup = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=4096
                )

            return self._handle_openai_response(followup, messages, depth + 1)

        return message.content or ""

    def _convert_tools_to_gemini(self) -> list:
        """도구를 Gemini 형식으로 변환 (google-genai 버전)"""
        types = self._genai_types

        gemini_functions = []
        for tool in self.tools:
            # Gemini 형식 파라미터 변환
            params = tool.get("input_schema", {"type": "object", "properties": {}})

            gemini_functions.append(
                types.FunctionDeclaration(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            k: types.Schema(
                                type=types.Type.STRING,
                                description=v.get("description", "")
                            )
                            for k, v in params.get("properties", {}).items()
                        },
                        required=params.get("required", [])
                    )
                )
            )

        return gemini_functions

    def _process_gemini(self, message: str, history: List[Dict], images: List[Dict] = None) -> str:
        """Google Gemini 처리 (도구 사용 지원) - google-genai 버전"""
        import base64 as b64
        types = self._genai_types

        # 대화 히스토리 구성
        contents = []
        for h in history:
            role = "user" if h["role"] == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part.from_text(text=h["content"])]))

        # 현재 메시지 구성 (이미지 포함)
        current_parts = []
        if images:
            for img in images:
                img_bytes = b64.b64decode(img["base64"])
                current_parts.append(types.Part.from_bytes(data=img_bytes, mime_type=img.get("media_type", "image/png")))
        current_parts.append(types.Part.from_text(text=message))
        contents.append(types.Content(role="user", parts=current_parts))

        # 도구 설정
        gemini_tools = None
        if self.tools:
            gemini_tools = [types.Tool(function_declarations=self._convert_tools_to_gemini())]

        # 설정
        config = types.GenerateContentConfig(
            system_instruction=self.system_prompt,
            tools=gemini_tools
        )

        # 요청
        response = self._genai_client.models.generate_content(
            model=self.model,
            contents=contents,
            config=config
        )

        # 도구 사용 처리
        return self._handle_gemini_response(response, contents, config)

    def _handle_gemini_response(self, response, contents, config, depth: int = 0) -> str:
        """Gemini 응답 처리 (도구 사용 루프) - google-genai 버전"""
        types = self._genai_types

        if depth > 10:
            return "도구 사용 깊이 제한에 도달했습니다."

        # function_call 확인 - 모든 function_call을 한 번에 수집
        function_calls = []
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]

            if hasattr(candidate.content, 'parts'):
                for part in candidate.content.parts:
                    if hasattr(part, 'function_call') and part.function_call:
                        function_calls.append(part.function_call)

        # function_call이 있으면 모두 실행
        if function_calls:
            # 먼저 모델 응답을 contents에 추가
            contents.append(response.candidates[0].content)

            # 모든 function_call 실행 및 결과 수집
            function_response_parts = []
            for fc in function_calls:
                tool_input = dict(fc.args) if fc.args else {}
                tool_output = execute_tool(fc.name, tool_input, self.project_path)

                function_response_parts.append(
                    types.Part.from_function_response(
                        name=fc.name,
                        response={"result": tool_output}
                    )
                )

            # 모든 도구 결과를 한 번에 추가
            contents.append(types.Content(
                role="user",
                parts=function_response_parts
            ))

            # 후속 요청
            followup = self._genai_client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config
            )

            return self._handle_gemini_response(followup, contents, config, depth + 1)

        # 응답에서 텍스트 추출 (function_call만 있는 경우 대비)
        try:
            return response.text
        except ValueError:
            # function_call만 있고 텍스트가 없는 경우
            result_text = ""
            if hasattr(response, 'candidates') and response.candidates:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'text') and part.text:
                        result_text += part.text
            return result_text if result_text else "요청을 처리했습니다."
