"""
api_system_ai.py - 시스템 AI 대화 API
IndieBiz OS Core

시스템 AI는 IndieBiz의 관리자이자 안내자입니다:
- 첫 실행 시 사용법 안내
- 도구 패키지 분석, 설치, 제거
- 에이전트 생성, 수정, 삭제 도움
- 오류 진단 및 해결

**통합 아키텍처**: AIAgent 클래스와 providers/ 모듈을 재사용하여
프로젝트 에이전트와 동일한 스트리밍/도구 실행 로직을 공유합니다.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional, List, Generator, Callable
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# 메모리 관련
from system_ai_memory import (
    load_user_profile,
    save_conversation,
    get_recent_conversations,
    get_memory_context,
    save_memory,
    get_memories
)
# 시스템 문서 관련
from system_docs import (
    read_doc,
    init_all_docs
)
# 도구 로딩
from system_ai import (
    SYSTEM_AI_DEFAULT_PACKAGES,
    load_tools_from_packages,
    execute_system_tool as execute_system_ai_tool
)
# 통합: AIAgent 클래스 사용
from ai_agent import AIAgent
# 통합: 프롬프트 빌더 사용
from prompt_builder import build_system_ai_prompt

router = APIRouter()

# 경로 설정
BACKEND_PATH = Path(__file__).parent
DATA_PATH = BACKEND_PATH.parent / "data"
SYSTEM_AI_CONFIG_PATH = DATA_PATH / "system_ai_config.json"


# ============ 설정 및 캐시 ============

def load_system_ai_config() -> dict:
    """시스템 AI 설정 로드"""
    if SYSTEM_AI_CONFIG_PATH.exists():
        with open(SYSTEM_AI_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "enabled": True,
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
        "apiKey": ""
    }


# ============ 도구 관련 ============

def get_all_system_ai_tools() -> List[Dict]:
    """시스템 AI가 사용할 모든 도구 로드 (패키지 도구만)

    NOTE: 시스템 AI 전용 도구들은 제거되었습니다.
    시스템 AI는 일반 에이전트와 동일한 도구를 사용하며,
    시스템 문서와 패키지 정보는 read_file, list_directory로 접근합니다.
    """
    # 패키지에서 동적 로딩 (system_essentials, python-exec, nodejs 등)
    tools = load_tools_from_packages(SYSTEM_AI_DEFAULT_PACKAGES)
    return tools


def create_system_ai_agent(config: dict = None, user_profile: str = "") -> AIAgent:
    """시스템 AI용 AIAgent 인스턴스 생성

    **통합 아키텍처**: 프로젝트 에이전트와 동일한 AIAgent 클래스를 사용합니다.
    - 동일한 프로바이더 코드 (anthropic, openai, gemini, ollama)
    - 동일한 스트리밍 로직
    - 동일한 도구 실행 로직

    Args:
        config: 시스템 AI 설정 (None이면 자동 로드)
        user_profile: 사용자 프로필

    Returns:
        AIAgent 인스턴스
    """
    if config is None:
        config = load_system_ai_config()

    # AI 설정
    ai_config = {
        "provider": config.get("provider", "anthropic"),
        "model": config.get("model", "claude-sonnet-4-20250514"),
        "api_key": config.get("apiKey", "")
    }

    # 시스템 프롬프트 생성 (공통 프롬프트 빌더 사용)
    system_prompt = build_system_ai_prompt(
        user_profile=user_profile
    )

    # 시스템 AI 전용 도구 로드
    tools = get_all_system_ai_tools()

    # AIAgent 인스턴스 생성 (시스템 AI 전용 도구 실행 함수 전달)
    agent = AIAgent(
        ai_config=ai_config,
        system_prompt=system_prompt,
        agent_name="시스템 AI",
        agent_id="system_ai",
        project_path=str(DATA_PATH),
        tools=tools,
        execute_tool_func=execute_system_tool
    )

    return agent


def process_system_ai_message(message: str, history: List[Dict] = None, images: List[Dict] = None) -> str:
    """시스템 AI 메시지 처리 (AIAgent 사용, 동기 모드)

    Args:
        message: 사용자 메시지
        history: 대화 히스토리
        images: 이미지 데이터

    Returns:
        AI 응답
    """
    user_profile = load_user_profile()

    agent = create_system_ai_agent(
        user_profile=user_profile
    )

    return agent.process_message_with_history(
        message_content=message,
        history=history,
        images=images
    )


def process_system_ai_message_stream(
    message: str,
    history: List[Dict] = None,
    images: List[Dict] = None,
    cancel_check: Callable = None
) -> Generator:
    """시스템 AI 메시지 처리 (AIAgent 사용, 스트리밍 모드)

    Args:
        message: 사용자 메시지
        history: 대화 히스토리
        images: 이미지 데이터
        cancel_check: 중단 여부를 확인하는 콜백 함수

    Yields:
        스트리밍 이벤트 딕셔너리
    """
    user_profile = load_user_profile()

    agent = create_system_ai_agent(
        user_profile=user_profile
    )

    yield from agent.process_message_stream(
        message_content=message,
        history=history,
        images=images,
        cancel_check=cancel_check
    )


def execute_system_tool(tool_name: str, tool_input: dict, work_dir: str = None, agent_id: str = None) -> str:
    """
    시스템 AI 도구 실행

    NOTE: 시스템 AI 전용 도구가 제거되어 이제 system_ai.py의
    execute_system_tool만 사용합니다.

    Args:
        tool_name: 도구 이름
        tool_input: 도구 입력
        work_dir: 작업 디렉토리
        agent_id: 에이전트 ID (프로바이더에서 전달, 시스템 AI는 "system_ai")
    """
    if work_dir is None:
        work_dir = str(DATA_PATH)
    return execute_system_ai_tool(tool_name, tool_input, work_dir)


class ImageData(BaseModel):
    base64: str
    media_type: str


class ChatMessage(BaseModel):
    message: str
    context: Optional[Dict[str, Any]] = None
    images: Optional[List[ImageData]] = None


class ChatResponse(BaseModel):
    response: str
    timestamp: str
    provider: str
    model: str


def get_system_prompt(user_profile: str = "") -> str:
    """시스템 AI의 시스템 프롬프트 (prompt_builder.py 사용)

    **통합**: 이제 공통 프롬프트 빌더를 사용합니다.
    - base_prompt.md (공통 설정) + 시스템 AI 역할 + 사용자 정보
    """
    return build_system_ai_prompt(user_profile=user_profile)


def get_anthropic_tools():
    """Anthropic 형식의 도구 정의 (동적 로딩)"""
    all_tools = get_all_system_ai_tools()

    # Anthropic 형식으로 변환 (parameters -> input_schema)
    anthropic_tools = []
    for tool in all_tools:
        t = {
            "name": tool["name"],
            "description": tool.get("description", "")
        }
        # input_schema 또는 parameters 사용
        if "input_schema" in tool:
            t["input_schema"] = tool["input_schema"]
        elif "parameters" in tool:
            t["input_schema"] = tool["parameters"]
        else:
            t["input_schema"] = {"type": "object", "properties": {}}
        anthropic_tools.append(t)

    return anthropic_tools


# ============ [DEPRECATED] 레거시 프로바이더별 함수들 ============
# 아래 함수들은 이제 AIAgent 클래스를 통해 처리됩니다.
# WebSocket 스트리밍에서 아직 참조할 수 있으므로 임시로 유지합니다.
# TODO: api_websocket.py도 통합 후 완전히 제거

async def _chat_with_anthropic_legacy(message: str, api_key: str, model: str, user_profile: str = "", overview: str = "", images: List[Dict] = None, history: List[Dict] = None) -> str:
    """[DEPRECATED] Anthropic Claude와 대화 - AIAgent로 대체됨"""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        messages = []

        # 대화 히스토리 추가 (ai_agent.py 방식 참조)
        if history:
            for h in history:
                messages.append({
                    "role": h["role"],
                    "content": h["content"]
                })

        # 이미지가 있으면 멀티모달 메시지 구성
        if images and len(images) > 0:
            content_blocks = []
            # 이미지 블록 추가
            for img in images:
                content_blocks.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": img.get("media_type", "image/jpeg"),
                        "data": img.get("base64", "")
                    }
                })
            # 텍스트 블록 추가
            content_blocks.append({
                "type": "text",
                "text": message
            })
            messages.append({"role": "user", "content": content_blocks})
        else:
            messages.append({"role": "user", "content": message})

        # 첫 번째 호출
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            system=get_system_prompt(user_profile, overview),
            tools=get_anthropic_tools(),
            messages=messages
        )

        # tool use 처리 (최대 5회 반복)
        approval_requested = False
        approval_message = ""

        for _ in range(5):
            if response.stop_reason != "tool_use":
                break

            # 응답에서 텍스트와 tool_use 블록 분리
            tool_results = []
            assistant_content = []

            for block in response.content:
                if block.type == "tool_use":
                    # 도구 실행
                    result = execute_system_tool(block.name, block.input)

                    # 승인 요청 감지 - 마커를 제거하고 루프 중단 플래그 설정
                    if result.startswith("[[APPROVAL_REQUESTED]]"):
                        approval_requested = True
                        result = result.replace("[[APPROVAL_REQUESTED]]", "")
                        approval_message = result

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })
                    assistant_content.append(block)
                elif block.type == "text":
                    assistant_content.append(block)

            # 승인 요청이 있으면 루프 중단 - 사용자에게 바로 반환
            if approval_requested:
                # 지금까지의 텍스트 응답 수집
                collected_text = []
                for block in response.content:
                    if hasattr(block, 'text') and block.text:
                        collected_text.append(block.text)

                # 승인 요청 메시지와 함께 반환
                final_response = "\n\n".join(collected_text) if collected_text else ""
                if final_response:
                    final_response += "\n\n"
                final_response += approval_message
                return final_response

            # 대화 이력 업데이트
            messages.append({"role": "assistant", "content": assistant_content})
            messages.append({"role": "user", "content": tool_results})

            # 다음 호출
            response = client.messages.create(
                model=model,
                max_tokens=2048,
                system=get_system_prompt(user_profile, overview),
                tools=get_anthropic_tools(),
                messages=messages
            )

        # 최종 텍스트 응답 추출
        for block in response.content:
            if hasattr(block, 'text'):
                return block.text

        return "응답을 생성할 수 없습니다."

    except ImportError:
        raise HTTPException(status_code=500, detail="anthropic 라이브러리가 설치되지 않았습니다. pip install anthropic")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Anthropic API 오류: {str(e)}")


def get_openai_tools():
    """OpenAI 형식의 도구 정의 (동적 로딩)"""
    all_tools = get_all_system_ai_tools()

    # OpenAI 형식으로 변환
    openai_tools = []
    for tool in all_tools:
        params = tool.get("input_schema") or tool.get("parameters") or {"type": "object", "properties": {}}
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": params
            }
        })

    return openai_tools


async def chat_with_openai(message: str, api_key: str, model: str, user_profile: str = "", overview: str = "", images: List[Dict] = None, history: List[Dict] = None) -> str:
    """OpenAI GPT와 대화 (tool use 지원, 이미지 포함 가능, 히스토리 지원)"""
    try:
        import openai
        client = openai.OpenAI(api_key=api_key)

        messages = [
            {"role": "system", "content": get_system_prompt(user_profile, overview)}
        ]

        # 대화 히스토리 추가 (ai_agent.py 방식 참조)
        if history:
            for h in history:
                messages.append({
                    "role": h["role"],
                    "content": h["content"]
                })

        # 이미지가 있으면 멀티모달 메시지 구성
        if images and len(images) > 0:
            content_blocks = [{"type": "text", "text": message}]
            for img in images:
                content_blocks.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{img.get('media_type', 'image/jpeg')};base64,{img.get('base64', '')}"
                    }
                })
            user_content = content_blocks
        else:
            user_content = message

        messages.append({"role": "user", "content": user_content})

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=get_openai_tools(),
            max_tokens=2048
        )

        # tool call 처리 (최대 5회)
        approval_requested = False
        approval_message = ""

        for _ in range(5):
            choice = response.choices[0]
            if choice.finish_reason != "tool_calls":
                break

            # 도구 호출 처리
            assistant_msg = choice.message
            messages.append(assistant_msg)

            for tool_call in assistant_msg.tool_calls:
                args = json.loads(tool_call.function.arguments)
                result = execute_system_tool(tool_call.function.name, args)

                # 승인 요청 감지
                if result.startswith("[[APPROVAL_REQUESTED]]"):
                    approval_requested = True
                    result = result.replace("[[APPROVAL_REQUESTED]]", "")
                    approval_message = result

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result
                })

            # 승인 요청이 있으면 루프 중단
            if approval_requested:
                # 기존 assistant 메시지 텍스트 + 승인 요청 메시지
                existing_text = assistant_msg.content or ""
                if existing_text:
                    return existing_text + "\n\n" + approval_message
                return approval_message

            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=get_openai_tools(),
                max_tokens=2048
            )

        return response.choices[0].message.content

    except ImportError:
        raise HTTPException(status_code=500, detail="openai 라이브러리가 설치되지 않았습니다. pip install openai")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI API 오류: {str(e)}")


async def chat_with_google(message: str, api_key: str, model: str, user_profile: str = "", overview: str = "", images: List[Dict] = None, history: List[Dict] = None) -> str:
    """[DEPRECATED] Google Gemini와 대화 - AIAgent로 대체됨

    NOTE: 이 함수는 레거시입니다. 새 코드에서는 AIAgent를 사용하세요.
    """
    try:
        from google import genai
        from google.genai import types
        import base64 as b64

        client = genai.Client(api_key=api_key)

        # 도구 동적 로딩 및 Gemini 형식으로 변환
        all_tools = get_all_system_ai_tools()

        def convert_schema(schema: dict):
            """JSON Schema를 Gemini Schema로 변환"""
            json_type = schema.get("type", "string")
            description = schema.get("description", "")

            type_map = {
                "string": types.Type.STRING,
                "number": types.Type.NUMBER,
                "integer": types.Type.INTEGER,
                "boolean": types.Type.BOOLEAN,
                "array": types.Type.ARRAY,
                "object": types.Type.OBJECT,
            }
            gemini_type = type_map.get(json_type, types.Type.STRING)

            if json_type == "object":
                props = schema.get("properties", {})
                converted_props = {k: convert_schema(v) for k, v in props.items()}
                return types.Schema(
                    type=types.Type.OBJECT,
                    description=description,
                    properties=converted_props,
                    required=schema.get("required", [])
                )
            elif json_type == "array":
                items = schema.get("items", {"type": "string"})
                return types.Schema(
                    type=types.Type.ARRAY,
                    description=description,
                    items=convert_schema(items)
                )
            return types.Schema(type=gemini_type, description=description)

        function_declarations = []
        for tool in all_tools:
            params = tool.get("input_schema") or tool.get("parameters") or {"type": "object", "properties": {}}
            function_declarations.append(
                types.FunctionDeclaration(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    parameters=convert_schema(params)
                )
            )

        system_tools = [types.Tool(function_declarations=function_declarations)] if function_declarations else None

        # 대화 히스토리 구성
        contents = []
        if history:
            for h in history:
                role = "user" if h["role"] == "user" else "model"
                contents.append(types.Content(role=role, parts=[types.Part.from_text(text=h["content"])]))

        # 현재 메시지 구성
        current_parts = []
        if images and len(images) > 0:
            for img in images:
                image_bytes = b64.b64decode(img.get("base64", ""))
                current_parts.append(types.Part.from_bytes(data=image_bytes, mime_type=img.get("media_type", "image/jpeg")))
        current_parts.append(types.Part.from_text(text=message))
        contents.append(types.Content(role="user", parts=current_parts))

        # 설정
        config = types.GenerateContentConfig(
            system_instruction=get_system_prompt(user_profile, overview),
            tools=system_tools
        )

        # API 호출 헬퍼 (재시도 로직 포함)
        import time
        def call_with_retry(contents_to_send, max_retries=3):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return client.models.generate_content(
                        model=model,
                        contents=contents_to_send,
                        config=config
                    )
                except Exception as e:
                    last_error = e
                    error_str = str(e)
                    # 500 INTERNAL 에러인 경우 재시도
                    if "500" in error_str or "INTERNAL" in error_str:
                        print(f"   [Gemini] 500 에러, 재시도 {attempt + 1}/{max_retries}...")
                        time.sleep(1 * (attempt + 1))  # 점진적 대기
                        continue
                    else:
                        raise e
            raise last_error

        # 첫 요청
        response = call_with_retry(contents)

        # function call 처리 (최대 10회)
        tool_results_collected = []
        approval_requested = False
        approval_message = ""

        for iteration in range(10):
            if not response.candidates or not response.candidates[0].content.parts:
                break

            has_function_call = False
            function_responses = []

            # 응답에서 텍스트 수집 (승인 요청 시 함께 반환하기 위해)
            collected_text_parts = []
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'text') and part.text:
                    collected_text_parts.append(part.text)

            # 모든 function_call을 수집
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    has_function_call = True
                    fc = part.function_call
                    args = dict(fc.args) if fc.args else {}
                    result = execute_system_tool(fc.name, args)
                    result = result or ""  # None 방지

                    # 승인 요청 감지
                    if result.startswith("[[APPROVAL_REQUESTED]]"):
                        approval_requested = True
                        result = result.replace("[[APPROVAL_REQUESTED]]", "")
                        approval_message = result

                    tool_results_collected.append({"tool": fc.name, "result": result})

                    function_responses.append(
                        types.Part.from_function_response(
                            name=fc.name,
                            response={"result": result}
                        )
                    )

            # 승인 요청이 있으면 루프 중단
            if approval_requested:
                final_text = "\n".join(collected_text_parts) if collected_text_parts else ""
                if final_text:
                    return final_text + "\n\n" + approval_message
                return approval_message

            if has_function_call and function_responses:
                # 도구 결과를 대화에 추가
                contents.append(response.candidates[0].content)
                contents.append(types.Content(role="user", parts=function_responses))
                response = call_with_retry(contents)
            else:
                break

        # 응답에서 텍스트 추출 (response.text 대신 parts에서 직접 추출)
        result_text = ""
        try:
            if hasattr(response, 'candidates') and response.candidates:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'text') and part.text:
                        result_text += part.text
        except Exception:
            pass

        # 텍스트가 없으면, 도구 결과를 기반으로 응답 요청
        if not result_text and tool_results_collected:
            summary_prompt = "위의 도구 호출 결과를 바탕으로 사용자의 질문에 한국어로 답변해주세요."
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=summary_prompt)]))
            try:
                summary_response = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config
                )
                if hasattr(summary_response, 'candidates') and summary_response.candidates:
                    for part in summary_response.candidates[0].content.parts:
                        if hasattr(part, 'text') and part.text:
                            result_text += part.text
            except Exception:
                result_text = f"도구 결과:\n\n{tool_results_collected[-1]['result']}"

        return result_text if result_text else "요청을 처리했습니다."

    except ImportError:
        raise HTTPException(status_code=500, detail="google-genai 라이브러리가 설치되지 않았습니다. pip install google-genai")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google API 오류: {str(e)}")


# 시스템 문서 초기화 플래그
_docs_initialized = False


@router.post("/system-ai/chat", response_model=ChatResponse)
async def chat_with_system_ai(chat: ChatMessage):
    """
    시스템 AI와 대화

    **통합 아키텍처**: AIAgent 클래스를 사용하여 프로젝트 에이전트와
    동일한 프로바이더 코드를 공유합니다. 모든 프로바이더(Anthropic, OpenAI,
    Google, Ollama)가 자동으로 지원됩니다.
    """
    global _docs_initialized

    config = load_system_ai_config()

    if not config.get("enabled", True):
        raise HTTPException(status_code=400, detail="시스템 AI가 비활성화되어 있습니다.")

    api_key = config.get("apiKey", "")
    if not api_key:
        raise HTTPException(status_code=400, detail="API 키가 설정되지 않았습니다. 설정에서 API 키를 입력해주세요.")

    provider = config.get("provider", "anthropic")
    model = config.get("model", "claude-sonnet-4-20250514")

    # 시스템 문서 초기화 (서버 시작 후 최초 1회만)
    if not _docs_initialized:
        init_all_docs()
        _docs_initialized = True

    # 최근 대화 히스토리 로드 (7회)
    recent_conversations = get_recent_conversations(limit=7)
    history = []
    for conv in recent_conversations:
        role = conv["role"] if conv["role"] in ["user", "assistant"] else "user"
        history.append({"role": role, "content": conv["content"]})

    # 사용자 메시지 저장
    save_conversation("user", chat.message)

    # 이미지 데이터 변환
    images_data = None
    if chat.images:
        images_data = [{"base64": img.base64, "media_type": img.media_type} for img in chat.images]

    # AIAgent를 사용한 통합 처리 (모든 프로바이더 자동 지원)
    try:
        response_text = process_system_ai_message(
            message=chat.message,
            history=history,
            images=images_data
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 응답 생성 실패: {str(e)}")

    # AI 응답 저장
    save_conversation("assistant", response_text)

    return ChatResponse(
        response=response_text,
        timestamp=datetime.now().isoformat(),
        provider=provider,
        model=model
    )


@router.get("/system-ai/welcome")
async def get_welcome_message():
    """
    첫 실행 시 환영 메시지
    (API 키 없이도 표시 가능한 정적 메시지)
    """
    return {
        "message": """안녕하세요! IndieBiz OS에 오신 걸 환영합니다.

저는 시스템 AI입니다. IndieBiz 사용을 도와드릴게요.

시작하려면 먼저 AI API 키를 설정해주세요:
1. 오른쪽 상단의 설정(⚙️) 버튼을 클릭
2. AI 프로바이더 선택 (Claude/GPT/Gemini)
3. API 키 입력

설정이 완료되면 저와 대화하면서 IndieBiz를 배워보세요!

무엇이든 물어보세요:
• "뭘 할 수 있어?"
• "새 프로젝트 만들어줘"
• "에이전트가 뭐야?"
• "도구 설치하려면?"
""",
        "needs_api_key": True
    }


@router.get("/system-ai/status")
async def get_system_ai_status():
    """시스템 AI 상태 확인"""
    config = load_system_ai_config()

    has_api_key = bool(config.get("apiKey", ""))

    return {
        "enabled": config.get("enabled", True),
        "provider": config.get("provider", "anthropic"),
        "model": config.get("model", "claude-sonnet-4-20250514"),
        "has_api_key": has_api_key,
        "ready": has_api_key and config.get("enabled", True)
    }


@router.get("/system-ai/providers")
async def get_available_providers():
    """사용 가능한 AI 프로바이더 목록"""
    return {
        "providers": [
            {
                "id": "anthropic",
                "name": "Anthropic Claude",
                "models": [
                    {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4 (추천)"},
                    {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet"},
                    {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku (빠름)"},
                ],
                "api_url": "https://console.anthropic.com"
            },
            {
                "id": "openai",
                "name": "OpenAI GPT",
                "models": [
                    {"id": "gpt-4o", "name": "GPT-4o (추천)"},
                    {"id": "gpt-4o-mini", "name": "GPT-4o Mini (빠름)"},
                    {"id": "gpt-4-turbo", "name": "GPT-4 Turbo"},
                ],
                "api_url": "https://platform.openai.com/api-keys"
            },
            {
                "id": "google",
                "name": "Google Gemini",
                "models": [
                    {"id": "gemini-2.0-flash-exp", "name": "Gemini 2.0 Flash (추천)"},
                    {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro"},
                    {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash (빠름)"},
                ],
                "api_url": "https://aistudio.google.com/apikey"
            }
        ]
    }


# ============ 메모리 관련 API ============

@router.get("/system-ai/conversations")
async def get_conversations(limit: int = 20):
    """시스템 AI 대화 이력 조회"""
    conversations = get_recent_conversations(limit)
    return {"conversations": conversations}


@router.get("/system-ai/conversations/recent")
async def get_conversations_recent(limit: int = 20):
    """시스템 AI 최근 대화 조회"""
    conversations = get_recent_conversations(limit)
    return {"conversations": conversations}


@router.get("/system-ai/conversations/dates")
async def get_conversation_dates():
    """대화가 있는 날짜 목록 조회 (날짜별 메시지 수 포함)"""
    import sqlite3
    from system_ai_memory import MEMORY_DB_PATH

    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT date(timestamp) as date, COUNT(*) as count
        FROM conversations
        GROUP BY date(timestamp)
        ORDER BY date DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    dates = [{"date": row[0], "count": row[1]} for row in rows if row[0]]
    return {"dates": dates}


@router.get("/system-ai/conversations/by-date/{date}")
async def get_conversations_by_date(date: str):
    """특정 날짜의 대화 조회"""
    import sqlite3
    from system_ai_memory import MEMORY_DB_PATH

    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, timestamp, role, content, summary, importance
        FROM conversations
        WHERE date(timestamp) = ?
        ORDER BY id ASC
    """, (date,))

    rows = cursor.fetchall()
    conn.close()

    conversations = []
    for row in rows:
        conversations.append({
            "id": row[0],
            "timestamp": row[1],
            "role": row[2],
            "content": row[3],
            "summary": row[4],
            "importance": row[5]
        })

    return {"conversations": conversations}


@router.delete("/system-ai/conversations")
async def clear_conversations():
    """시스템 AI 대화 이력 삭제"""
    import sqlite3
    from system_ai_memory import MEMORY_DB_PATH

    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM conversations")
    conn.commit()
    conn.close()

    return {"status": "cleared"}




# ============ 프롬프트 설정 API ============

def save_system_ai_config(config: dict):
    """시스템 AI 설정 저장"""
    with open(SYSTEM_AI_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


class PromptConfigUpdate(BaseModel):
    selected_template: Optional[str] = None


@router.get("/system-ai/prompts/config")
async def get_prompt_config():
    """프롬프트 설정 조회"""
    config = load_system_ai_config()
    return {
        "selected_template": config.get("selected_template", "default")
    }


@router.put("/system-ai/prompts/config")
async def update_prompt_config(data: PromptConfigUpdate):
    """프롬프트 설정 업데이트"""
    config = load_system_ai_config()

    if data.selected_template is not None:
        config["selected_template"] = data.selected_template

    save_system_ai_config(config)
    return {"status": "updated", "config": {
        "selected_template": config.get("selected_template")
    }}


# 시스템 AI 역할 파일 경로
SYSTEM_AI_ROLE_PATH = DATA_PATH / "system_ai_role.txt"


@router.get("/system-ai/prompts/role")
async def get_role_prompt():
    """역할 프롬프트 조회 (별도 파일에서 로드)"""
    if SYSTEM_AI_ROLE_PATH.exists():
        content = SYSTEM_AI_ROLE_PATH.read_text(encoding='utf-8')
    else:
        content = ""
    return {"content": content}


class RolePromptUpdate(BaseModel):
    content: str


@router.put("/system-ai/prompts/role")
async def update_role_prompt(data: RolePromptUpdate):
    """역할 프롬프트 업데이트 (별도 파일에 저장)"""
    SYSTEM_AI_ROLE_PATH.write_text(data.content, encoding='utf-8')
    return {"status": "updated"}
