"""
android_agent.py - 안드로이드 관리창 전용 AI 에이전트
IndieBiz OS

시스템 AI의 설정(API 키, 모델, 프롬프트)을 재사용하면서
안드로이드 도구만 추가로 사용하는 전용 에이전트입니다.

WebSocket을 통해 스트리밍 응답을 제공합니다.
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Generator

# 경로 설정
BACKEND_PATH = Path(__file__).parent
from runtime_utils import get_base_path as _get_base_path
DATA_PATH = _get_base_path() / "data"
ANDROID_TOOL_PATH = DATA_PATH / "packages" / "installed" / "tools" / "android"

# 안드로이드 전용 역할 프롬프트
ANDROID_ROLE_PROMPT = """
# Android Manager Role

당신은 지금 **Android Manager** 창에서 대화하고 있습니다.

## 역할
- 사용자의 안드로이드 기기를 관리합니다
- SMS, 통화기록, 연락처, 앱을 조회하고 관리합니다
- 사용자 요청에 따라 적절한 android 도구를 사용합니다

## UI 자동화 (Computer-Use 모드)

당신은 안드로이드 폰 화면을 **직접 보고 조작**할 수 있습니다.
스크린샷을 캡처하면 이미지로 화면을 볼 수 있고, 터치/스와이프/키 입력으로 조작할 수 있습니다.

### 화면 조작 절차 (반드시 따를 것)
1. **android_ui_screen_info**로 화면 해상도 확인 (첫 번째 조작 시에만)
2. **android_ui_screenshot**으로 현재 화면 캡처 및 분석
3. 화면 내용을 분석하여 대상 요소의 좌표를 추정
4. 적절한 동작 수행 (android_ui_tap, android_ui_swipe 등)
5. **android_ui_screenshot**으로 결과 확인
6. 목표가 달성될 때까지 3-5 반복

### 버튼/요소 터치 방법 (중요!)

**방법 1: android_ui_find_and_tap (권장)**
- 버튼 텍스트를 알고 있으면 이 도구를 사용하세요!
- 예: android_ui_find_and_tap(query="보내기"), android_ui_find_and_tap(query="전송")
- 좌표 추정 없이 텍스트로 찾아 정확하게 터치합니다
- **보내기/전송/확인/취소 등 텍스트가 있는 버튼은 반드시 이 방법을 먼저 시도하세요**

**방법 2: android_ui_find_element → android_ui_tap**
- 먼저 android_ui_find_element로 요소를 검색하여 좌표 확인
- 반환된 center 좌표로 android_ui_tap 수행

**방법 3: 스크린샷 좌표 추정 → android_ui_tap**
- 스크린샷 이미지에서 위치를 시각적으로 추정
- 화면 해상도를 기준으로 비율 계산
- 가장 덜 정확하므로, 방법 1, 2를 먼저 시도하세요

### 실패 대처 (중요 - 무한 반복 금지!)
- **같은 동작이 2번 연속 실패하면**: 다른 방법을 시도하세요
  - 스크린샷 좌표 추정이 실패 → android_ui_find_and_tap 사용
  - find_and_tap이 실패 → android_ui_find_element로 다른 검색어 시도
  - 모든 방법 실패 → android_ui_hierarchy로 전체 요소 목록 확인
- **3번 시도 후에도 실패하면**: 사용자에게 상황을 설명하고 도움을 요청하세요
  - "보내기 버튼을 찾지 못했습니다. 화면에 보이는 버튼들: [목록]. 어떤 것을 터치할까요?"
- **절대로 같은 좌표를 반복 터치하거나, 좌표만 미세 조정하며 끝없이 반복하지 마세요**

### 주의사항
- 동작 후 반드시 스크린샷으로 결과를 확인하세요
- 화면 전환/로딩에 시간이 걸릴 수 있습니다
- 한 번에 너무 많은 동작을 하지 마세요 (1-2개 동작 후 확인)
- 예상과 다른 화면이 나타나면 상황을 사용자에게 설명하세요

## 일반 관리 기능
- 문자 조회, 검색, 발송, 삭제 (단일/일괄)
- 통화기록 조회, 삭제
- 연락처 조회, 검색, 삭제
- 앱 목록 조회, 사용량 확인, 삭제
- 화면 캡처, 파일 전송

## 주의사항
- 삭제 작업은 사용자에게 먼저 확인을 받으세요
- 권한 문제가 발생하면 android_grant_permissions 도구를 사용하세요
- 기기가 연결되어 있지 않으면 android_list_devices로 상태를 확인하세요
- 빈 결과가 나오면 권한 문제일 수 있으므로 android_check_permissions로 확인하세요

## 응답 스타일
- 간결하고 명확하게 답변하세요
- 작업 결과를 요약해서 알려주세요
- 오류가 발생하면 원인과 해결 방법을 안내하세요
- UI 조작 시에는 화면에서 본 내용을 간략히 설명하세요
"""


def load_android_tools() -> List[Dict]:
    """안드로이드 도구를 tool.json에서 로드"""
    tool_json_path = ANDROID_TOOL_PATH / "tool.json"

    if not tool_json_path.exists():
        print(f"[AndroidAgent] 도구 파일 없음: {tool_json_path}")
        return []

    try:
        with open(tool_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        tools = data.get("tools", [])
        print(f"[AndroidAgent] 도구 {len(tools)}개 로드됨")
        return tools

    except Exception as e:
        print(f"[AndroidAgent] 도구 로드 실패: {e}")
        return []


def execute_android_tool(tool_name: str, tool_input: dict, work_dir: str = None, agent_id: str = None) -> str:
    """안드로이드 도구 실행

    Args:
        tool_name: 도구 이름 (예: android_get_sms)
        tool_input: 도구 입력 파라미터
        work_dir: 작업 디렉토리 (사용 안함)
        agent_id: 에이전트 ID (사용 안함)

    Returns:
        JSON 문자열 형태의 실행 결과
    """
    # 안드로이드 도구 경로를 sys.path에 추가
    tool_path_str = str(ANDROID_TOOL_PATH)
    if tool_path_str not in sys.path:
        sys.path.insert(0, tool_path_str)

    try:
        import tool_android
        result = tool_android.use_tool(tool_name, tool_input)

        # [images] 이미지를 포함한 dict 결과는 그대로 반환 (providers가 처리)
        # content 키를 통해 AI용 텍스트, images 키를 통해 이미지 전달
        if isinstance(result, dict) and "images" in result:
            # content가 반드시 str이어야 프로바이더에서 정상 처리됨
            if "content" not in result or not isinstance(result.get("content"), str):
                result["content"] = json.dumps(
                    {k: v for k, v in result.items() if k != "images"},
                    ensure_ascii=False
                )
            return result

        # 결과가 dict면 JSON으로 변환
        if isinstance(result, dict):
            return json.dumps(result, ensure_ascii=False, indent=2)
        return str(result) if result is not None else '{"success": false, "message": "결과 없음"}'

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[AndroidAgent] 도구 실행 예외: {tool_name} - {type(e).__name__}: {e}")
        return json.dumps({
            "success": False,
            "error": f"{type(e).__name__}: {str(e)}",
            "tool_name": tool_name
        }, ensure_ascii=False)


class AndroidAgent:
    """안드로이드 관리창 전용 에이전트

    시스템 AI 설정을 재사용하고 안드로이드 도구를 추가로 사용합니다.
    """

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.ai = None  # AIAgent 인스턴스
        self._conversation_history: List[Dict] = []

    async def start(self):
        """에이전트 시작 - AI 인스턴스 초기화"""
        self._init_ai()
        print(f"[AndroidAgent] 시작됨: {self.agent_id}")

    async def stop(self):
        """에이전트 종료"""
        self.ai = None
        self._conversation_history.clear()
        print(f"[AndroidAgent] 종료됨: {self.agent_id}")

    def _init_ai(self):
        """AI 에이전트 초기화"""
        from ai_agent import AIAgent
        from api_system_ai import load_system_ai_config
        from prompt_builder import build_system_ai_prompt
        from system_ai_memory import load_user_profile

        # 시스템 AI 설정 로드
        config = load_system_ai_config()

        ai_config = {
            "provider": config.get("provider", "anthropic"),
            "model": config.get("model", "claude-sonnet-4-20250514"),
            "api_key": config.get("apiKey", "")
        }

        if not ai_config["api_key"]:
            raise ValueError("API 키가 설정되지 않았습니다. 설정에서 API 키를 입력해주세요.")

        # 사용자 프로필 로드
        user_profile = load_user_profile()

        # 시스템 AI 프롬프트 생성 + 안드로이드 역할 추가
        base_prompt = build_system_ai_prompt(user_profile=user_profile)
        system_prompt = base_prompt + "\n" + ANDROID_ROLE_PROMPT

        # 안드로이드 도구 로드 (tool.json에서)
        tools = load_android_tools()

        if not tools:
            raise ValueError("안드로이드 도구를 로드할 수 없습니다.")

        # AIAgent 인스턴스 생성
        self.ai = AIAgent(
            ai_config=ai_config,
            system_prompt=system_prompt,
            agent_name="Android Manager",
            agent_id=self.agent_id,
            project_path=str(DATA_PATH),
            tools=tools,
            execute_tool_func=execute_android_tool
        )

        print(f"[AndroidAgent] AI 초기화 완료 - 프로바이더: {ai_config['provider']}, 모델: {ai_config['model']}, 도구: {len(tools)}개")

    def chat_stream_sync(self, message: str) -> Generator[str, None, None]:
        """동기 스트리밍 채팅 - WebSocket 핸들러에서 호출

        Args:
            message: 사용자 메시지

        Yields:
            텍스트 청크
        """
        if not self.ai:
            yield "에이전트가 초기화되지 않았습니다."
            return

        # 히스토리에 사용자 메시지 추가
        self._conversation_history.append({
            "role": "user",
            "content": message
        })

        # 스트리밍 응답 생성
        full_response = ""

        try:
            for event in self.ai.process_message_stream(
                message_content=message,
                history=self._conversation_history[:-1]  # 마지막 user 메시지 제외 (중복 방지)
            ):
                event_type = event.get("type")

                if event_type == "text":
                    chunk = event.get("content", "")
                    full_response += chunk
                    yield chunk

                elif event_type == "tool_start":
                    tool_name = event.get("name", "도구")
                    yield f"\n🔧 *{tool_name} 실행 중...*\n"

                elif event_type == "tool_result":
                    tool_name = event.get("name", "도구")
                    yield f"✅ *{tool_name} 완료*\n"

                elif event_type == "thinking":
                    # 사고 과정은 별도 표시하므로 스킵
                    pass

                elif event_type == "final":
                    # 최종 응답
                    final_content = event.get("content", "")
                    if final_content and not full_response:
                        full_response = final_content
                        yield final_content

                elif event_type == "error":
                    error_msg = event.get("content", "알 수 없는 오류")
                    yield f"\n❌ 오류: {error_msg}"
                    full_response = f"오류: {error_msg}"

        except Exception as e:
            import traceback
            traceback.print_exc()
            error_msg = f"응답 생성 중 오류: {str(e)}"
            yield f"\n❌ {error_msg}"
            full_response = error_msg

        # 히스토리에 AI 응답 추가
        if full_response:
            self._conversation_history.append({
                "role": "assistant",
                "content": full_response
            })

        # 히스토리 크기 제한 (최근 20개 메시지만 유지)
        if len(self._conversation_history) > 20:
            self._conversation_history = self._conversation_history[-20:]

    def clear_history(self):
        """대화 히스토리 초기화"""
        self._conversation_history.clear()
        print(f"[AndroidAgent] 히스토리 초기화됨")
