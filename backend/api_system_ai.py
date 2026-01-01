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
    SYSTEM_AI_TOOLS as SYSTEM_DOC_TOOLS,
    execute_system_tool as execute_doc_tool
)
from system_ai import (
    SYSTEM_AI_DEFAULT_PACKAGES,
    load_tools_from_packages,
    execute_system_tool as execute_system_ai_tool
)

router = APIRouter()

# 경로 설정
BACKEND_PATH = Path(__file__).parent
DATA_PATH = BACKEND_PATH.parent / "data"
SYSTEM_AI_CONFIG_PATH = DATA_PATH / "system_ai_config.json"


def get_all_system_ai_tools() -> List[Dict]:
    """시스템 AI가 사용할 모든 도구 로드 (문서 도구 + 패키지 도구)"""
    # 1. 문서/패키지 관리 도구 (system_docs.py)
    tools = list(SYSTEM_DOC_TOOLS)

    # 2. 패키지에서 동적 로딩 (system_essentials, python-exec, nodejs 등)
    package_tools = load_tools_from_packages(SYSTEM_AI_DEFAULT_PACKAGES)
    tools.extend(package_tools)

    return tools


def execute_system_tool(tool_name: str, tool_input: dict, work_dir: str = None) -> str:
    """
    시스템 AI 통합 도구 실행

    1. 문서 관련 도구 (system_docs)
    2. 시스템 전용 + 패키지 도구 (system_ai)
    """
    # 문서 관련 도구인지 확인
    doc_tool_names = [t["name"] for t in SYSTEM_DOC_TOOLS]
    if tool_name in doc_tool_names:
        return execute_doc_tool(tool_name, tool_input)

    # 시스템 AI 도구 실행 (시스템 전용 + 패키지)
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
    base_prompt = """# 정체성
이름: 시스템 AI
임무: 시스템 안내와 관리 그리고 도구 개발과 개선

당신은 IndieBiz OS의 시스템 AI입니다.

# 원칙
- 사용자의 이익을 최우선으로 한다.
- 시스템에 대한 지식을 기반으로 사용자에게 친절한 가이드를 제공한다.

# 역할
- IndieBiz를 처음 사용하는 사용자에게 친절하게 안내
- 도구 패키지 설치/제거 도움
- 새로운 도구 개발 및 개선 (사용자 요청 시)
- 프로젝트 생성/설정 도움
- 문제 해결 및 오류 진단

# 대화 스타일
- 친근하고 도움이 되는 톤
- 기술적 설명은 쉽게
- 단계별 안내
- 한국어로 대화

# 중요 경로 (현재 작업 디렉토리: backend/)
- 프로젝트 폴더: ../projects/[프로젝트명]/
- 설치된 도구: ../data/packages/installed/tools/[도구명]/
- 개발중 도구: ../data/packages/dev/tools/[도구명]/
- 시스템 문서: ../data/system_docs/

# 효율적인 도구 사용
- 프로젝트/도구 존재 여부는 inventory 문서로 먼저 확인
- inventory에 답이 있으면 추가 파일 탐색 불필요
- 불필요한 문서 읽기 자제 (overview, architecture는 시스템 설명 요청 시에만)

# 시스템 문서
필요할 때 read_system_doc 도구로 문서를 참조하세요:
- overview: 시스템 개요 (시스템 소개 요청 시에만)
- architecture: 시스템 구조 (구조 질문 시에만)
- inventory: 설치된 프로젝트, 에이전트, 도구 목록 (가장 자주 사용)
- technical: API, 설정 등 기술 상세
- packages: 패키지 설치/제거 및 개발 가이드

# 도구 패키지 관리
패키지 관련 도구:
- list_packages: 설치 가능한 도구 패키지 목록 조회
- get_package_info: 패키지 상세 정보 조회
- install_package: 패키지 설치 (반드시 사용자 동의 후!)

# 도구 개발 가이드
사용자가 새 도구를 만들어달라고 요청하면 직접 개발해주세요.

패키지 폴더 구조 (패키지는 한 곳에만 존재):
- 개발 폴더: ../data/packages/dev/tools/[도구이름]/
- 미설치 폴더: ../data/packages/not_installed/tools/[도구이름]/
- 설치 폴더: ../data/packages/installed/tools/[도구이름]/

패키지 파일 구성:
- tool.json: 도구 정의 (아래 형식 참고)
- handler.py: 도구 실행 코드 (def execute 함수)
- requirements.txt: 필요한 패키지 (선택)

tool.json 형식 (배열 형태 사용):
```json
[
  {
    "name": "도구이름",
    "description": "도구 설명",
    "input_schema": {
      "type": "object",
      "properties": {
        "param1": {"type": "string", "description": "설명"}
      },
      "required": ["param1"]
    }
  }
]
```
주의: {"tools": [...]} 형식이 아닌 배열 [...] 형식을 사용하세요.

중요: 패키지 관리 규칙
1. 설치 = not_installed → installed로 이동
2. 삭제 = installed → not_installed로 이동
3. 새 패키지 생성 시 installed 폴더에 직접 생성 (바로 사용 가능)
4. 작업 후 inventory.md가 자동 업데이트됨

handler.py 형식:
```python
def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    # 도구 로직
    return "결과"
```

## 코드 안전 규칙
- 금지: rm -rf, format, mkfs, dd if=, chmod 777
- 필수: 루프에 종료 조건, API 호출에 타임아웃, try-except 에러 핸들링
- 파일: encoding='utf-8' 명시"""

    # 사용자 정보가 있으면 추가
    if user_profile and user_profile.strip():
        base_prompt += f"\n\n# 사용자 정보\n{user_profile.strip()}"

    # 시스템 상태가 있으면 추가 (이미 추출된 섹션)
    if system_status and system_status.strip():
        base_prompt += f"\n\n# 현재 시스템 상태\n{system_status.strip()}"

    base_prompt += "\n\n지금부터 사용자와 대화합니다."

    return base_prompt


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


async def chat_with_anthropic(message: str, api_key: str, model: str, user_profile: str = "", overview: str = "", images: List[Dict] = None, history: List[Dict] = None) -> str:
    """Anthropic Claude와 대화 (tool use 지원, 이미지 포함 가능, 히스토리 지원)"""
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


async def chat_with_google(message: str, api_key: str, model: str, user_profile: str = "", overview: str = "", images: List[Dict] = None, history: List[Dict] = None) -> str:
    """Google Gemini와 대화 (tool use 지원, 이미지 포함 가능, 히스토리 지원) - google-genai 버전"""
    try:
        from google import genai
        from google.genai import types
        import base64 as b64

        client = genai.Client(api_key=api_key)

        # 도구 정의 (새 API 형식)
        system_tools = [
            types.Tool(function_declarations=[
                types.FunctionDeclaration(
                    name="read_system_doc",
                    description="시스템 문서를 읽습니다. 사용 가능한 문서: overview(개요), architecture(구조), inventory(인벤토리), technical(기술), packages(패키지 가이드). 패키지 설치/제거 시에는 반드시 packages 문서를 먼저 읽으세요.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "doc_name": types.Schema(type=types.Type.STRING, description="읽을 문서 이름 (overview, architecture, inventory, technical, packages)")
                        },
                        required=["doc_name"]
                    )
                ),
                types.FunctionDeclaration(
                    name="list_packages",
                    description="설치 가능한 도구 패키지 목록을 조회합니다.",
                    parameters=types.Schema(type=types.Type.OBJECT, properties={})
                ),
                types.FunctionDeclaration(
                    name="get_package_info",
                    description="특정 패키지의 상세 정보를 조회합니다.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={"package_id": types.Schema(type=types.Type.STRING, description="패키지 ID")},
                        required=["package_id"]
                    )
                ),
                types.FunctionDeclaration(
                    name="install_package",
                    description="도구 패키지를 설치합니다. 반드시 사용자의 동의를 받은 후에만 사용하세요.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={"package_id": types.Schema(type=types.Type.STRING, description="설치할 패키지 ID")},
                        required=["package_id"]
                    )
                ),
                # 파일 시스템 도구
                types.FunctionDeclaration(
                    name="read_file",
                    description="파일의 내용을 읽습니다.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={"file_path": types.Schema(type=types.Type.STRING, description="읽을 파일의 경로")},
                        required=["file_path"]
                    )
                ),
                types.FunctionDeclaration(
                    name="write_file",
                    description="파일에 내용을 씁니다.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "file_path": types.Schema(type=types.Type.STRING, description="쓸 파일의 경로"),
                            "content": types.Schema(type=types.Type.STRING, description="파일에 쓸 내용")
                        },
                        required=["file_path", "content"]
                    )
                ),
                types.FunctionDeclaration(
                    name="list_directory",
                    description="디렉토리의 파일과 폴더 목록을 가져옵니다.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={"dir_path": types.Schema(type=types.Type.STRING, description="디렉토리 경로")}
                    )
                ),
                # 코드 실행 도구
                types.FunctionDeclaration(
                    name="execute_python",
                    description="Python 코드를 실행합니다.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={"code": types.Schema(type=types.Type.STRING, description="실행할 Python 코드")},
                        required=["code"]
                    )
                ),
                types.FunctionDeclaration(
                    name="execute_node",
                    description="Node.js JavaScript 코드를 실행합니다.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={"code": types.Schema(type=types.Type.STRING, description="실행할 JavaScript 코드")},
                        required=["code"]
                    )
                ),
                types.FunctionDeclaration(
                    name="run_command",
                    description="쉘 명령어를 실행합니다. (pip install, mkdir 등)",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={"command": types.Schema(type=types.Type.STRING, description="실행할 명령어")},
                        required=["command"]
                    )
                )
            ])
        ]

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

        for iteration in range(10):
            if not response.candidates or not response.candidates[0].content.parts:
                break

            has_function_call = False
            function_responses = []

            # 모든 function_call을 수집
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    has_function_call = True
                    fc = part.function_call
                    args = dict(fc.args) if fc.args else {}
                    result = execute_system_tool(fc.name, args)
                    result = result or ""  # None 방지
                    tool_results_collected.append({"tool": fc.name, "result": result})

                    function_responses.append(
                        types.Part.from_function_response(
                            name=fc.name,
                            response={"result": result}
                        )
                    )

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

    # 최근 대화 히스토리 로드 (5회)
    recent_conversations = get_recent_conversations(limit=5)
    history = []
    for conv in recent_conversations:
        # role은 user 또는 assistant
        role = conv["role"] if conv["role"] in ["user", "assistant"] else "user"
        history.append({
            "role": role,
            "content": conv["content"]
        })

    # 사용자 메시지 저장 (비동기로 처리 가능하지만 현재는 동기)
    save_conversation("user", chat.message)

    # 이미지 데이터 변환
    images_data = None
    if chat.images:
        images_data = [{"base64": img.base64, "media_type": img.media_type} for img in chat.images]

    # 프로바이더별 대화 (tool use 지원, 히스토리 포함)
    if provider == "anthropic":
        response_text = await chat_with_anthropic(chat.message, api_key, model, user_profile, system_status, images_data, history)
    elif provider == "openai":
        response_text = await chat_with_openai(chat.message, api_key, model, user_profile, system_status, images_data, history)
    elif provider == "google":
        response_text = await chat_with_google(chat.message, api_key, model, user_profile, system_status, images_data, history)
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
