"""
api_system_ai.py - 시스템 AI 대화 API
IndieBiz OS Core

시스템 AI는 IndieBiz의 관리자이자 안내자입니다:
- 첫 실행 시 사용법 안내
- 도구 패키지 분석, 설치, 제거
- 에이전트 생성, 수정, 삭제 도움
- 오류 진단 및 해결
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from system_ai_memory import (
    load_user_profile,
    load_system_status,
    init_system_status,
    save_conversation,
    get_recent_conversations,
    get_memory_context,
    save_memory,
    get_memories
)
from system_docs import (
    read_doc,
    list_docs,
    init_all_docs,
    SYSTEM_AI_TOOLS,
    execute_system_tool
)

router = APIRouter()

# 경로 설정
BACKEND_PATH = Path(__file__).parent
DATA_PATH = BACKEND_PATH.parent / "data"
SYSTEM_AI_CONFIG_PATH = DATA_PATH / "system_ai_config.json"


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


def get_system_prompt(user_profile: str = "", system_status: str = "") -> str:
    """시스템 AI의 시스템 프롬프트 (기본 + 사용자 정보 + 상태)"""
    base_prompt = """당신은 IndieBiz OS의 시스템 AI입니다.

# 원칙
- 사용자의 이익을 최우선으로 한다.
- 시스템에 대한 지식을 기반으로 사용자에게 친절한 가이드를 제공한다.

# 역할
- IndieBiz를 처음 사용하는 사용자에게 친절하게 안내
- 도구 패키지 설치/제거 도움
- 에이전트 생성/설정 도움
- 문제 해결 및 오류 진단

# 대화 스타일
- 친근하고 도움이 되는 톤
- 기술적 설명은 쉽게
- 단계별 안내
- 한국어로 대화

# 시스템 문서
필요할 때 read_system_doc 도구로 문서를 참조하세요:
- overview: 시스템 개요 및 현재 상태
- architecture: 시스템 구조 및 설계 의도
- inventory: 설치된 프로젝트, 에이전트, 도구 목록
- technical: API, 설정 등 기술 상세
- packages: 패키지 설치/제거 및 개발 가이드

사용자 질문에 따라 적절한 문서를 참조하세요:
- 사용법/안내 질문 → overview
- 구조/설계 질문 → architecture
- "뭐가 설치되어 있어?" → inventory
- API/설정 질문 → technical
- 패키지 설치/제거/개발 → packages (필수!)

# 도구 패키지 관리
**중요**: 패키지 설치, 제거, 개발 관련 작업 시 반드시 packages 문서를 먼저 읽으세요.

패키지 관련 도구:
- list_packages: 설치 가능한 도구 패키지 목록 조회
- get_package_info: 패키지 상세 정보 조회
- install_package: 패키지 설치 (반드시 사용자 동의 후!)

패키지 설치 시 주의사항:
1. packages 문서를 읽어 설치 절차 확인
2. 패키지 정보를 먼저 설명하고 사용자 동의를 받으세요
3. 의존성이나 추가 요구사항이 있으면 미리 알려주세요
4. 설치 후 결과를 확인하고 안내하세요"""

    # 사용자 정보가 있으면 추가
    if user_profile and user_profile.strip():
        base_prompt += f"\n\n# 사용자 정보\n{user_profile.strip()}"

    # 시스템 상태가 있으면 추가 (이미 추출된 섹션)
    if system_status and system_status.strip():
        base_prompt += f"\n\n# 현재 시스템 상태\n{system_status.strip()}"

    base_prompt += "\n\n지금부터 사용자와 대화합니다."

    return base_prompt


def get_anthropic_tools():
    """Anthropic 형식의 도구 정의"""
    return [
        {
            "name": "read_system_doc",
            "description": "시스템 문서를 읽습니다. 사용 가능한 문서: overview(개요), architecture(구조), inventory(인벤토리), technical(기술), packages(패키지 가이드). 패키지 설치/제거 시에는 반드시 packages 문서를 먼저 읽으세요.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "doc_name": {
                        "type": "string",
                        "enum": ["overview", "architecture", "inventory", "technical", "packages"],
                        "description": "읽을 문서 이름"
                    }
                },
                "required": ["doc_name"]
            }
        },
        {
            "name": "list_packages",
            "description": "설치 가능한 도구 패키지 목록을 조회합니다.",
            "input_schema": {
                "type": "object",
                "properties": {}
            }
        },
        {
            "name": "get_package_info",
            "description": "특정 패키지의 상세 정보를 조회합니다.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "package_id": {
                        "type": "string",
                        "description": "패키지 ID"
                    }
                },
                "required": ["package_id"]
            }
        },
        {
            "name": "install_package",
            "description": "도구 패키지를 설치합니다. 반드시 사용자의 동의를 받은 후에만 사용하세요.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "package_id": {
                        "type": "string",
                        "description": "설치할 패키지 ID"
                    }
                },
                "required": ["package_id"]
            }
        }
    ]


async def chat_with_anthropic(message: str, api_key: str, model: str, user_profile: str = "", overview: str = "", images: List[Dict] = None) -> str:
    """Anthropic Claude와 대화 (tool use 지원, 이미지 포함 가능)"""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

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
            messages = [{"role": "user", "content": content_blocks}]
        else:
            messages = [{"role": "user", "content": message}]

        # 첫 번째 호출
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            system=get_system_prompt(user_profile, overview),
            tools=get_anthropic_tools(),
            messages=messages
        )

        # tool use 처리 (최대 3회 반복)
        for _ in range(3):
            if response.stop_reason != "tool_use":
                break

            # 응답에서 텍스트와 tool_use 블록 분리
            tool_results = []
            assistant_content = []

            for block in response.content:
                if block.type == "tool_use":
                    # 도구 실행
                    result = execute_system_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })
                    assistant_content.append(block)
                elif block.type == "text":
                    assistant_content.append(block)

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
    """OpenAI 형식의 도구 정의"""
    return [
        {
            "type": "function",
            "function": {
                "name": "read_system_doc",
                "description": "시스템 문서를 읽습니다. 사용 가능한 문서: overview(개요), architecture(구조), inventory(인벤토리), technical(기술), packages(패키지 가이드). 패키지 설치/제거 시에는 반드시 packages 문서를 먼저 읽으세요.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "doc_name": {
                            "type": "string",
                            "enum": ["overview", "architecture", "inventory", "technical", "packages"],
                            "description": "읽을 문서 이름"
                        }
                    },
                    "required": ["doc_name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_packages",
                "description": "설치 가능한 도구 패키지 목록을 조회합니다.",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_package_info",
                "description": "특정 패키지의 상세 정보를 조회합니다.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "package_id": {
                            "type": "string",
                            "description": "패키지 ID"
                        }
                    },
                    "required": ["package_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "install_package",
                "description": "도구 패키지를 설치합니다. 반드시 사용자의 동의를 받은 후에만 사용하세요.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "package_id": {
                            "type": "string",
                            "description": "설치할 패키지 ID"
                        }
                    },
                    "required": ["package_id"]
                }
            }
        }
    ]


async def chat_with_openai(message: str, api_key: str, model: str, user_profile: str = "", overview: str = "", images: List[Dict] = None) -> str:
    """OpenAI GPT와 대화 (tool use 지원, 이미지 포함 가능)"""
    try:
        import openai
        client = openai.OpenAI(api_key=api_key)

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

        messages = [
            {"role": "system", "content": get_system_prompt(user_profile, overview)},
            {"role": "user", "content": user_content}
        ]

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=get_openai_tools(),
            max_tokens=2048
        )

        # tool call 처리 (최대 3회)
        for _ in range(3):
            choice = response.choices[0]
            if choice.finish_reason != "tool_calls":
                break

            # 도구 호출 처리
            assistant_msg = choice.message
            messages.append(assistant_msg)

            for tool_call in assistant_msg.tool_calls:
                args = json.loads(tool_call.function.arguments)
                result = execute_system_tool(tool_call.function.name, args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result
                })

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


async def chat_with_google(message: str, api_key: str, model: str, user_profile: str = "", overview: str = "", images: List[Dict] = None) -> str:
    """Google Gemini와 대화 (tool use 지원, 이미지 포함 가능)"""
    try:
        import google.generativeai as genai
        import base64
        genai.configure(api_key=api_key)

        # Gemini 도구 정의
        system_tools = genai.protos.Tool(
            function_declarations=[
                genai.protos.FunctionDeclaration(
                    name="read_system_doc",
                    description="시스템 문서를 읽습니다. 사용 가능한 문서: overview(개요), architecture(구조), inventory(인벤토리), technical(기술), packages(패키지 가이드). 패키지 설치/제거 시에는 반드시 packages 문서를 먼저 읽으세요.",
                    parameters=genai.protos.Schema(
                        type=genai.protos.Type.OBJECT,
                        properties={
                            "doc_name": genai.protos.Schema(
                                type=genai.protos.Type.STRING,
                                description="읽을 문서 이름 (overview, architecture, inventory, technical, packages)"
                            )
                        },
                        required=["doc_name"]
                    )
                ),
                genai.protos.FunctionDeclaration(
                    name="list_packages",
                    description="설치 가능한 도구 패키지 목록을 조회합니다.",
                    parameters=genai.protos.Schema(
                        type=genai.protos.Type.OBJECT,
                        properties={}
                    )
                ),
                genai.protos.FunctionDeclaration(
                    name="get_package_info",
                    description="특정 패키지의 상세 정보를 조회합니다.",
                    parameters=genai.protos.Schema(
                        type=genai.protos.Type.OBJECT,
                        properties={
                            "package_id": genai.protos.Schema(
                                type=genai.protos.Type.STRING,
                                description="패키지 ID"
                            )
                        },
                        required=["package_id"]
                    )
                ),
                genai.protos.FunctionDeclaration(
                    name="install_package",
                    description="도구 패키지를 설치합니다. 반드시 사용자의 동의를 받은 후에만 사용하세요.",
                    parameters=genai.protos.Schema(
                        type=genai.protos.Type.OBJECT,
                        properties={
                            "package_id": genai.protos.Schema(
                                type=genai.protos.Type.STRING,
                                description="설치할 패키지 ID"
                            )
                        },
                        required=["package_id"]
                    )
                )
            ]
        )

        gemini_model = genai.GenerativeModel(
            model_name=model,
            system_instruction=get_system_prompt(user_profile, overview),
            tools=[system_tools]
        )

        chat = gemini_model.start_chat()

        # 이미지가 있으면 멀티모달 메시지 구성
        if images and len(images) > 0:
            import base64 as b64
            content_parts = [message]
            for img in images:
                # base64를 바이트로 디코딩
                image_bytes = b64.b64decode(img.get("base64", ""))
                content_parts.append({
                    "mime_type": img.get("media_type", "image/jpeg"),
                    "data": image_bytes
                })
            response = chat.send_message(content_parts)
        else:
            response = chat.send_message(message)

        # function call 처리 (최대 10회)
        tool_results_collected = []

        for iteration in range(10):
            if not response.candidates or not response.candidates[0].content.parts:
                print(f"   [Gemini] 반복 {iteration}: 응답 parts 없음")
                break

            has_function_call = False
            function_responses = []

            # 모든 function_call을 수집
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    has_function_call = True
                    fc = part.function_call
                    args = dict(fc.args)
                    print(f"   [Gemini] 도구 호출: {fc.name}, 인자: {args}")
                    result = execute_system_tool(fc.name, args)
                    print(f"   [Gemini] 도구 결과: {result[:200]}..." if len(result) > 200 else f"   [Gemini] 도구 결과: {result}")
                    tool_results_collected.append({"tool": fc.name, "result": result})

                    function_responses.append(
                        genai.protos.Part(
                            function_response=genai.protos.FunctionResponse(
                                name=fc.name,
                                response={"result": result}
                            )
                        )
                    )

            if has_function_call and function_responses:
                # 모든 function response를 한번에 전송
                print(f"   [Gemini] {len(function_responses)}개의 도구 결과 전송")
                response = chat.send_message(
                    genai.protos.Content(parts=function_responses)
                )
            else:
                print(f"   [Gemini] 반복 {iteration}: function_call 없음, 루프 종료")
                break

        # 응답에서 텍스트 추출
        result_text = ""
        try:
            result_text = response.text
            print(f"   [Gemini] 최종 텍스트 응답: {result_text[:100]}..." if len(result_text) > 100 else f"   [Gemini] 최종 텍스트 응답: {result_text}")
        except (ValueError, AttributeError) as e:
            print(f"   [Gemini] response.text 오류: {e}")
            # function_call만 있고 텍스트가 없는 경우 - parts에서 텍스트 추출 시도
            if hasattr(response, 'candidates') and response.candidates:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'text') and part.text:
                        result_text += part.text

            # 여전히 텍스트가 없으면, 도구 결과를 기반으로 응답 요청
            if not result_text and tool_results_collected:
                print(f"   [Gemini] 텍스트 없음, 도구 결과 기반으로 재요청")
                # AI에게 도구 결과를 요약해달라고 요청
                summary_prompt = "위의 도구 호출 결과를 바탕으로 사용자의 질문에 한국어로 답변해주세요."
                try:
                    summary_response = chat.send_message(summary_prompt)
                    result_text = summary_response.text
                    print(f"   [Gemini] 요약 응답: {result_text[:100]}..." if len(result_text) > 100 else f"   [Gemini] 요약 응답: {result_text}")
                except Exception as summary_error:
                    print(f"   [Gemini] 요약 요청 실패: {summary_error}")
                    # 마지막 수단: 도구 결과 직접 반환
                    result_text = f"패키지 정보를 조회했습니다:\n\n{tool_results_collected[-1]['result']}"

        return result_text

    except ImportError:
        raise HTTPException(status_code=500, detail="google-generativeai 라이브러리가 설치되지 않았습니다. pip install google-generativeai")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google API 오류: {str(e)}")


# 캐시: 시스템 상태 (5분간 유효)
_system_status_cache = {
    "status": None,
    "timestamp": None,
    "ttl_seconds": 300  # 5분
}

def _get_cached_system_status() -> str:
    """캐시된 시스템 상태 반환 (overview의 '현재 상태' 섹션만)"""
    import time
    now = time.time()

    # 캐시가 유효하면 반환
    if (_system_status_cache["status"] is not None and
        _system_status_cache["timestamp"] is not None and
        now - _system_status_cache["timestamp"] < _system_status_cache["ttl_seconds"]):
        return _system_status_cache["status"]

    # overview에서 '현재 상태' 섹션만 추출
    overview = read_doc("overview")
    status_section = ""
    if overview and "## 현재 상태" in overview:
        try:
            status_section = overview.split("## 현재 상태")[1].split("---")[0].strip()
        except:
            pass

    # 캐시 업데이트
    _system_status_cache["status"] = status_section
    _system_status_cache["timestamp"] = now

    return status_section


def invalidate_system_status_cache():
    """시스템 상태 캐시 무효화 (패키지 설치/제거 등 변경 시 호출)"""
    _system_status_cache["status"] = None
    _system_status_cache["timestamp"] = None


# 시스템 문서 초기화 플래그
_docs_initialized = False


@router.post("/system-ai/chat", response_model=ChatResponse)
async def chat_with_system_ai(chat: ChatMessage):
    """
    시스템 AI와 대화

    시스템 AI는 IndieBiz의 안내자이자 관리자입니다.
    설정된 AI 프로바이더(Anthropic/OpenAI/Google)를 사용합니다.
    도구(tool use)를 통해 시스템 문서를 필요할 때 참조합니다.
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

    # 메모리 로드 (가벼움)
    user_profile = load_user_profile()

    # 시스템 문서 초기화 (서버 시작 후 최초 1회만)
    if not _docs_initialized:
        init_all_docs()
        _docs_initialized = True

    # 캐시된 시스템 상태만 로드 (overview 전체 대신)
    system_status = _get_cached_system_status()

    # 사용자 메시지 저장 (비동기로 처리 가능하지만 현재는 동기)
    save_conversation("user", chat.message)

    # 이미지 데이터 변환
    images_data = None
    if chat.images:
        images_data = [{"base64": img.base64, "media_type": img.media_type} for img in chat.images]

    # 프로바이더별 대화 (tool use 지원)
    # overview 대신 system_status만 전달
    if provider == "anthropic":
        response_text = await chat_with_anthropic(chat.message, api_key, model, user_profile, system_status, images_data)
    elif provider == "openai":
        response_text = await chat_with_openai(chat.message, api_key, model, user_profile, system_status, images_data)
    elif provider == "google":
        response_text = await chat_with_google(chat.message, api_key, model, user_profile, system_status, images_data)
    else:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 프로바이더: {provider}")

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


@router.delete("/system-ai/conversations")
async def clear_conversations():
    """시스템 AI 대화 이력 삭제"""
    import sqlite3
    from system_ai_memory import MEMORY_DB_PATH

    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    cursor = conn.cursor()
    cursor.execute("DELETE FROM conversations")
    conn.commit()
    conn.close()

    return {"status": "cleared"}


@router.get("/system-ai/system-status")
async def get_system_status():
    """시스템 현황 문서 조회"""
    content = init_system_status()
    return {"content": content}


@router.put("/system-ai/system-status")
async def update_system_status(data: Dict[str, str]):
    """시스템 현황 문서 업데이트"""
    from system_ai_memory import save_system_status

    content = data.get("content", "")
    save_system_status(content)
    return {"status": "updated"}
