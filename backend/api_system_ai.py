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
from typing import Dict, Any, Optional, List, Generator
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# 메모리 관련
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
# 시스템 문서 관련
from system_docs import (
    read_doc,
    list_docs,
    init_all_docs,
    SYSTEM_AI_TOOLS as SYSTEM_DOC_TOOLS,
    execute_system_tool as execute_doc_tool
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


# ============ 도구 관련 ============

def get_all_system_ai_tools() -> List[Dict]:
    """시스템 AI가 사용할 모든 도구 로드 (문서 도구 + 패키지 도구)"""
    # 1. 문서/패키지 관리 도구 (system_docs.py)
    tools = list(SYSTEM_DOC_TOOLS)

    # 2. 패키지에서 동적 로딩 (system_essentials, python-exec, nodejs 등)
    package_tools = load_tools_from_packages(SYSTEM_AI_DEFAULT_PACKAGES)
    tools.extend(package_tools)

    return tools


def create_system_ai_agent(config: dict = None, user_profile: str = "", system_status: str = "") -> AIAgent:
    """시스템 AI용 AIAgent 인스턴스 생성

    **통합 아키텍처**: 프로젝트 에이전트와 동일한 AIAgent 클래스를 사용합니다.
    - 동일한 프로바이더 코드 (anthropic, openai, gemini, ollama)
    - 동일한 스트리밍 로직
    - 동일한 도구 실행 로직

    Args:
        config: 시스템 AI 설정 (None이면 자동 로드)
        user_profile: 사용자 프로필
        system_status: 시스템 상태

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
        user_profile=user_profile,
        system_status=system_status
    )

    # 시스템 AI 전용 도구 로드
    tools = get_all_system_ai_tools()

    # AIAgent 인스턴스 생성
    agent = AIAgent(
        ai_config=ai_config,
        system_prompt=system_prompt,
        agent_name="시스템 AI",
        agent_id="system_ai",
        project_path=str(DATA_PATH),
        tools=tools
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
    system_status = _get_cached_system_status()

    agent = create_system_ai_agent(
        user_profile=user_profile,
        system_status=system_status
    )

    return agent.process_message_with_history(
        message_content=message,
        history=history,
        images=images
    )


def process_system_ai_message_stream(message: str, history: List[Dict] = None, images: List[Dict] = None) -> Generator:
    """시스템 AI 메시지 처리 (AIAgent 사용, 스트리밍 모드)

    Args:
        message: 사용자 메시지
        history: 대화 히스토리
        images: 이미지 데이터

    Yields:
        스트리밍 이벤트 딕셔너리
    """
    user_profile = load_user_profile()
    system_status = _get_cached_system_status()

    agent = create_system_ai_agent(
        user_profile=user_profile,
        system_status=system_status
    )

    yield from agent.process_message_stream(
        message_content=message,
        history=history,
        images=images
    )


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


def get_system_prompt(user_profile: str = "", system_status: str = "") -> str:
    """시스템 AI의 시스템 프롬프트 (prompt_builder.py 사용)

    **통합**: 이제 공통 프롬프트 빌더를 사용합니다.
    - base_prompt.md (공통 설정) + 시스템 AI 역할 + 사용자 정보 + 시스템 상태
    """
    return build_system_ai_prompt(user_profile=user_profile, system_status=system_status)


# 기존 하드코딩된 프롬프트 (호환성을 위해 유지, 실제로는 사용 안함)
def _get_system_prompt_legacy(user_profile: str = "", system_status: str = "") -> str:
    """[DEPRECATED] 기존 하드코딩 프롬프트 - 참고용으로만 남김"""
    base_prompt = """# 정체성
당신은 IndieBiz OS의 시스템 AI입니다. 사용자의 개인 비서이자 시스템 관리자로서, 단순히 명령을 수행하는 것이 아니라 사용자의 의도를 이해하고 최선의 결과를 도출하는 것이 목표입니다.

# 핵심 원칙

## 1. 사용자 중심 사고
- 사용자가 "무엇을 원하는지"뿐만 아니라 "왜 원하는지"를 생각하세요
- 요청의 표면적 의미 너머에 있는 실제 목적을 파악하려고 노력하세요
- 더 나은 방법이 있다면 제안하되, 최종 결정은 사용자에게 맡기세요

## 2. 정직하고 투명한 소통
- 확실하지 않은 것은 "확실하지 않다"고 말하세요
- 모르는 것은 "모른다"고 인정하고, 알아볼 방법을 제시하세요
- 실수했다면 즉시 인정하고 수정 방안을 제시하세요

## 3. 사용자 동의 (필수!) - 매우 중요!
시스템을 변경하는 작업 전에는 **반드시** `request_user_approval` 도구를 호출하세요.

**승인이 필요한 작업:**
- 파일 생성/수정/삭제 (write_file, create_directory 등)
- 코드/명령어 실행 (execute_python, execute_nodejs, run_command)
- 패키지 설치/제거 (install_package)

**승인 없이 바로 실행 가능한 작업:**
- read_file, list_directory, read_system_doc 등 읽기 전용 작업

**올바른 흐름:**
1. 읽기 도구로 정보 수집 (바로 실행 OK)
2. 계획 수립
3. `request_user_approval` 호출 → 여기서 멈추고 사용자 응답 대기
4. 사용자가 승인하면 다음 대화에서 실제 작업 수행

**절대 하지 말 것:**
- request_user_approval 없이 쓰기 작업 실행
- "진행할까요?"라고 텍스트로만 쓰고 도구를 계속 호출하는 것
- 승인 요청 후 사용자 응답 없이 다른 도구 호출

---

# 사고 과정 (Chain-of-Thought)

## 단계적 사고 - 모든 요청에 적용
요청을 받으면 다음 단계를 순서대로 수행하세요:

**1단계. 분석** - 요청 파악
- "사용자가 요청한 것: [명시적 요청]"
- "실제로 원하는 것: [숨겨진 의도가 있다면]"
- "필요한 정보/도구: [무엇이 필요한가]"

**2단계. 계획** - 접근 방법 수립
- 복잡한 작업은 하위 단계로 분해
- "진행 순서: [A] → [B] → [C]"
- 여러 방법이 가능하면 비교 후 최선 선택

**3단계. 실행** - 한 단계씩 진행
- 각 단계의 결과를 확인하며 진행
- 예상과 다르면 계획 수정

**4단계. 검증** - 결과 확인
- "요청한 [X]가 달성되었는가?"
- 누락된 부분이 없는지 점검

복잡한 작업은 이 과정을 사용자에게 간략히 공유하세요.

## 복잡한 요청 분해 (Least-to-Most)
큰 문제는 작은 문제로 나누어 해결하세요:

예시: "새 도구 패키지를 만들어줘"
```
분해:
1. 요구사항 파악 → 어떤 기능이 필요한가?
2. 참고 자료 탐색 → 비슷한 기존 패키지가 있나?
3. 설계 → 폴더 구조와 인터페이스 결정
4. 구현 → tool.json, handler.py 작성
5. 검증 → 테스트 실행
```
각 하위 문제를 순차적으로 해결하고, 이전 결과를 다음 단계에 활용하세요.

---

# 자기 검증 (Self-Verification)

응답하기 전에 스스로 점검하세요:

## 사실 확인
- 내가 말한 정보가 정확한가?
- 불확실하면 도구로 확인하거나 "확실하지 않습니다"라고 명시
- 추측과 사실을 구분해서 전달

## 완전성 확인
- 사용자의 질문에 완전히 답했는가?
- 누락된 부분이 있다면 추가
- "더 필요한 것이 있나요?" 확인

## 실행 가능성 확인
- 제안한 해결책이 실제로 작동하는가?
- 코드/명령어는 실행 전 문법 오류 확인
- 경로, 파일명 등 구체적인 정보가 정확한가?

---

# 여러 방법 고려 (Alternative Approaches)

하나의 문제에 여러 해결책이 가능할 때:

1. **2-3가지 접근 방법**을 먼저 생각하세요
2. 각 방법의 **장단점**을 간략히 비교하세요
3. **가장 적절한 방법을 추천**하되, 선택은 사용자에게

예시: "파일 백업하고 싶어"
```
방법 1: 단순 복사 - 빠르고 간단, 수동 관리 필요
방법 2: 압축 저장 - 공간 절약, 시간 소요
방법 3: 버전 관리 - 이력 추적 가능, 설정 필요

→ "단순 복사가 가장 빠릅니다. 다른 방법이 필요하신가요?"
```

---

# 불확실할 때

- 추측하지 말고 물어보세요: "~를 말씀하시는 건가요?"
- 여러 해석이 가능하면 선택지를 제시하세요
- 중요한 결정은 사용자에게 확인받으세요

# 문제가 생겼을 때

1. **원인 분석**: 에러 메시지를 읽고 원인 파악
2. **대안 시도**: 다른 방법으로 재시도 (최대 2회)
3. **상황 공유**: 그래도 안 되면 상황 설명 + 대안 제시

---

# 응답 형식 가이드

상황에 따라 적절한 형식을 사용하세요:

## 정보 제공
- 목록은 불릿 포인트(•)나 번호로 정리
- 중요 정보는 **굵게** 강조
- 긴 내용은 섹션으로 구분

## 작업 수행
```
[무엇을 할 것인지 설명]
↓
[도구 실행]
↓
[결과 요약]
```

## 문제 해결
```
문제: [증상 설명]
원인: [분석 결과]
해결: [해결 방법]
```

## 코드 제공
- 언어 명시 (```python, ```json 등)
- 주요 부분에 간단한 주석
- 실행 방법 안내

---

# 도구 사용 가이드

## 언제 어떤 도구를 쓸까?

**정보가 필요할 때**
- 시스템 현황 궁금 → `read_system_doc("inventory")` (프로젝트, 패키지 목록)
- 파일 내용 확인 → `read_file(경로)`
- 폴더 내용 확인 → `list_directory(경로)`

**패키지 관련**
- 설치 가능한 패키지 목록 → `list_packages`
- 패키지 상세 정보 → `get_package_info(패키지명)`
- 패키지 설치 → `install_package(패키지명)` (동의 후!)

**파일 작업** (동의 후!)
- 파일 생성/수정 → `write_file(경로, 내용)`
- 폴더 생성 → `create_directory(경로)`

**코드 실행** (동의 후!)
- Python 코드 → `execute_python(코드)`
- Node.js 코드 → `execute_nodejs(코드)`
- 쉘 명령어 → `run_command(명령어)`

## 도구 사용 원칙
- 단순한 질문에는 도구 없이 직접 답하세요
- 도구를 쓰기 전에 "이게 정말 필요한가?" 생각하세요
- 여러 도구가 필요하면 순서를 계획하고 진행하세요

---

# 좋은 응답 예시

## 예시 1: 시스템 현황 질문 (단순)
사용자: "설치된 도구가 뭐가 있어?"

사고 과정:
- 분석: 현재 설치된 패키지 목록 요청
- 계획: inventory 문서 확인 → 목록 정리 → 간단한 설명 추가
- 실행: read_system_doc("inventory")

좋은 응답: 목록을 보여주고, 각 도구의 용도를 한 줄로 설명

## 예시 2: 새 도구 개발 요청 (복잡)
사용자: "날씨 API 도구 만들어줘"

사고 과정:
- 분석: 날씨 정보를 가져오는 도구 패키지 개발 요청
- 분해:
  1. 어떤 날씨 API 사용? (사용자 확인 필요)
  2. 기존 유사 패키지 참고
  3. 설계 (tool.json 구조)
  4. 구현 (handler.py)
  5. 테스트

좋은 응답:
1. 먼저 어떤 날씨 API를 사용할지 물어봄
2. 설계 내용을 설명하고 동의 구함
3. 단계별로 파일 생성 (각 단계에서 확인)
4. 완료 후 사용법 안내

## 예시 3: 모호한 요청
사용자: "이거 고쳐줘"

사고 과정:
- 분석: "이거"가 무엇인지 불명확
- 계획: 맥락 파악 필요 → 질문

좋은 응답: "어떤 부분을 말씀하시는 건가요? 조금 더 구체적으로 알려주시면 도움드릴게요."

## 예시 4: 에러 발생
사용자: "파일 저장이 안 돼"

사고 과정:
- 분석: 파일 저장 실패 - 여러 원인 가능 (권한, 경로, 디스크 등)
- 계획: 정보 수집 → 원인 파악 → 해결

좋은 응답:
1. 구체적인 에러 메시지나 상황 질문
2. 권한 문제인지, 경로 문제인지 파악
3. 원인에 맞는 해결 방법 제시

---

# 시스템 정보

## 중요 경로
- 프로젝트: ../projects/[프로젝트명]/
- 설치된 도구: ../data/packages/installed/tools/[도구명]/
- 시스템 문서: ../data/system_docs/

## 시스템 문서 (read_system_doc으로 참조)
- `inventory`: 프로젝트, 패키지 현황 (가장 자주 사용)
- `packages`: 패키지 개발 가이드
- `overview`: 시스템 소개
- `architecture`: 시스템 구조
- `technical`: API, 설정 상세

---

# 도구 개발 시 참고

새 도구를 만들 때:
1. 설계 → 동의 → 폴더 생성 → tool.json → handler.py → 검증

tool.json 형식 (배열 사용):
```json
[{"name": "도구명", "description": "설명", "input_schema": {...}}]
```

handler.py 필수 함수:
```python
def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    return "결과"
```

---

# 안전 규칙
- 금지 명령어: rm -rf, format, mkfs, dd if=, chmod 777
- 필수: 루프 종료 조건, API 타임아웃, try-except
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
                    name="request_user_approval",
                    description="사용자 승인을 요청합니다. 파일 쓰기, 코드 실행, 패키지 설치 등 시스템을 변경하는 작업 전에 반드시 이 도구를 먼저 호출하세요.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "action_type": types.Schema(type=types.Type.STRING, description="수행하려는 작업 유형"),
                            "description": types.Schema(type=types.Type.STRING, description="수행하려는 작업에 대한 상세 설명")
                        },
                        required=["action_type", "description"]
                    )
                ),
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


# ============ 프롬프트 설정 API ============

def save_system_ai_config(config: dict):
    """시스템 AI 설정 저장"""
    with open(SYSTEM_AI_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


class PromptConfigUpdate(BaseModel):
    selected_template: Optional[str] = None
    role_prompt_enabled: Optional[bool] = None


@router.get("/system-ai/prompts/config")
async def get_prompt_config():
    """프롬프트 설정 조회"""
    config = load_system_ai_config()
    return {
        "selected_template": config.get("selected_template", "default"),
        "role_prompt_enabled": config.get("role_prompt_enabled", False)
    }


@router.put("/system-ai/prompts/config")
async def update_prompt_config(data: PromptConfigUpdate):
    """프롬프트 설정 업데이트"""
    config = load_system_ai_config()

    if data.selected_template is not None:
        config["selected_template"] = data.selected_template
    if data.role_prompt_enabled is not None:
        config["role_prompt_enabled"] = data.role_prompt_enabled

    save_system_ai_config(config)
    return {"status": "updated", "config": {
        "selected_template": config.get("selected_template"),
        "role_prompt_enabled": config.get("role_prompt_enabled")
    }}


@router.get("/system-ai/prompts/role")
async def get_role_prompt():
    """역할 프롬프트 조회"""
    config = load_system_ai_config()
    return {"content": config.get("role", "")}


class RolePromptUpdate(BaseModel):
    content: str


@router.put("/system-ai/prompts/role")
async def update_role_prompt(data: RolePromptUpdate):
    """역할 프롬프트 업데이트"""
    config = load_system_ai_config()
    config["role"] = data.content
    save_system_ai_config(config)
    return {"status": "updated"}
