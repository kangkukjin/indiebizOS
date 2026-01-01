"""
system_ai.py - 시스템 AI (도구 사용 가능)
IndieBiz OS Core

시스템 AI는 도구 패키지 설치, 도구 개발 등 시스템 관리 작업을 수행합니다.
도구는 동적으로 로딩되며, system_essentials 패키지의 도구들을 기본으로 사용합니다.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from ai_agent import AIAgent, execute_tool as execute_package_tool
from system_ai_memory import save_conversation, get_recent_conversations, load_user_profile

# 경로 설정
BACKEND_PATH = Path(__file__).parent
DATA_PATH = BACKEND_PATH.parent / "data"
SYSTEM_AI_CONFIG_PATH = DATA_PATH / "system_ai_config.json"
INSTALLED_TOOLS_PATH = DATA_PATH / "packages" / "installed" / "tools"


# 시스템 AI 기본 패키지 목록
SYSTEM_AI_DEFAULT_PACKAGES = ["system_essentials", "python-exec", "nodejs"]


def load_tools_from_packages(package_names: List[str] = None) -> List[Dict]:
    """
    설치된 패키지에서 도구 정의 로드

    Args:
        package_names: 로드할 패키지 이름 목록 (None이면 기본 패키지)

    Returns:
        도구 정의 목록
    """
    if package_names is None:
        package_names = SYSTEM_AI_DEFAULT_PACKAGES

    tools = []

    for pkg_name in package_names:
        pkg_path = INSTALLED_TOOLS_PATH / pkg_name / "tool.json"
        if pkg_path.exists():
            try:
                with open(pkg_path, 'r', encoding='utf-8') as f:
                    pkg_data = json.load(f)

                    # tools 배열이 있으면 여러 도구 패키지
                    if "tools" in pkg_data:
                        for tool in pkg_data["tools"]:
                            tools.append(tool)
                    # 단일 도구 패키지 (name 필드가 있으면)
                    elif "name" in pkg_data:
                        tools.append(pkg_data)
            except Exception as e:
                print(f"[시스템AI] 패키지 로드 실패 {pkg_name}: {e}")

    return tools


def execute_system_tool(tool_name: str, tool_input: dict, work_dir: str = ".") -> str:
    """
    시스템 AI 도구 실행 - 모든 도구를 패키지에서 동적 로딩
    """
    return execute_package_tool(tool_name, tool_input, work_dir)


def load_system_ai_config() -> dict:
    """시스템 AI 설정 로드"""
    if SYSTEM_AI_CONFIG_PATH.exists():
        try:
            with open(SYSTEM_AI_CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}


class SystemAI:
    """
    시스템 AI - 도구 사용이 가능한 시스템 관리 AI

    기능:
    - 도구 패키지 설치
    - 파일/디렉토리 관리
    - Python 코드 실행
    - 쉘 명령 실행
    """

    def __init__(self, work_dir: str = None):
        self.config = load_system_ai_config()
        self.work_dir = work_dir or str(DATA_PATH)
        self._agent = None

    def _get_system_prompt(self) -> str:
        """시스템 AI 프롬프트 (api_system_ai.py와 동일)"""
        user_profile = load_user_profile()

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
- 에이전트 생성/설정 도움
- 문제 해결 및 오류 진단

# 대화 스타일
- 친근하고 도움이 되는 톤
- 기술적 설명은 쉽게
- 단계별 안내
- 한국어로 대화

# 도구 개발 가이드
사용자가 새 도구를 만들어달라고 요청하면 직접 개발해주세요.

도구 패키지 구조:
- 폴더: data/packages/dev/tools/[도구이름]/
- tool.json: 도구 메타데이터 (name, description, input_schema)
- handler.py: 도구 실행 코드 (def execute 함수)
- requirements.txt: 필요한 패키지 (선택)

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

        if user_profile and user_profile.strip():
            base_prompt += f"\n\n# 사용자 정보\n{user_profile.strip()}"

        return base_prompt

    def _get_agent(self, task_prompt: str = None, extra_packages: List[str] = None) -> AIAgent:
        """
        AIAgent 인스턴스 생성

        Args:
            task_prompt: 추가 작업 프롬프트
            extra_packages: 추가로 로드할 패키지 이름 목록
        """
        ai_config = {
            "provider": self.config.get("provider", "google"),
            "api_key": self.config.get("apiKey") or self.config.get("api_key"),
            "model": self.config.get("model", "gemini-2.0-flash")
        }

        system_prompt = self._get_system_prompt()

        if task_prompt:
            system_prompt = f"{system_prompt}\n\n[현재 작업]\n{task_prompt}"

        # 도구 동적 로딩: 기본 패키지 + 추가 패키지
        packages = list(SYSTEM_AI_DEFAULT_PACKAGES)
        if extra_packages:
            packages.extend(extra_packages)

        tools = load_tools_from_packages(packages)

        return AIAgent(
            ai_config=ai_config,
            system_prompt=system_prompt,
            agent_name="시스템AI",
            agent_id="system-ai",
            project_path=self.work_dir,
            tools=tools
        )

    def execute(self, task: str, max_turns: int = 10) -> Dict[str, Any]:
        """
        작업 실행 (도구 사용 포함, 대화 히스토리 저장)

        Args:
            task: 수행할 작업 설명
            max_turns: 최대 대화 턴 수 (도구 호출 포함)

        Returns:
            {"success": bool, "result": str, "tool_calls": [...]}
        """
        agent = self._get_agent()

        tool_calls = []

        # 최근 대화 히스토리 로드 (5회) - 사용자 대화 DB와 동일
        recent_conversations = get_recent_conversations(limit=5)
        messages = []
        for conv in recent_conversations:
            role = conv["role"] if conv["role"] in ["user", "assistant"] else "user"
            messages.append({
                "role": role,
                "content": conv["content"]
            })

        # 사용자 메시지(작업 요청) 저장
        save_conversation("user", task)

        try:
            # 첫 요청 (히스토리 포함)
            response = agent.chat(task, conversation_history=messages)
            messages.append({"role": "user", "content": task})
            messages.append({"role": "assistant", "content": response})

            # 도구 호출이 있으면 반복
            turns = 0
            while turns < max_turns:
                # 응답에서 도구 호출 확인
                if not hasattr(agent, '_last_tool_calls') or not agent._last_tool_calls:
                    break

                for tool_call in agent._last_tool_calls:
                    tool_name = tool_call.get("name")
                    tool_input = tool_call.get("input", {})

                    # 도구 실행
                    result = execute_system_tool(tool_name, tool_input, self.work_dir)
                    tool_calls.append({
                        "tool": tool_name,
                        "input": tool_input,
                        "result": result
                    })

                    # 결과를 대화에 추가
                    messages.append({
                        "role": "user",
                        "content": f"[도구 결과: {tool_name}]\n{result}"
                    })

                # 다음 응답
                response = agent.chat("계속 진행해주세요.", conversation_history=messages)
                messages.append({"role": "assistant", "content": response})
                turns += 1

            # AI 최종 응답 저장
            save_conversation("assistant", response)

            return {
                "success": True,
                "result": response,
                "tool_calls": tool_calls
            }

        except Exception as e:
            error_msg = f"오류 발생: {str(e)}"
            save_conversation("assistant", error_msg)

            return {
                "success": False,
                "error": str(e),
                "tool_calls": tool_calls
            }

    def install_package(self, package_path: str) -> Dict[str, Any]:
        """
        도구 패키지 설치

        Args:
            package_path: 패키지 폴더 경로 (tool.json이 있는 폴더)
        """
        task = f"""
다음 도구 패키지를 설치해줘:
경로: {package_path}

1. tool.json을 읽어서 도구 정보 확인
2. handler.py가 있으면 그대로 사용, 없으면 tool.json의 설명을 보고 생성
3. requirements.txt가 있으면 pip install -r requirements.txt 실행
4. 패키지를 {INSTALLED_TOOLS_PATH}로 복사

설치가 완료되면 결과를 알려줘.
"""
        return self.execute(task)

    def create_tool(self, name: str, description: str, implementation_hint: str = "") -> Dict[str, Any]:
        """
        새 도구 생성

        Args:
            name: 도구 이름
            description: 도구 설명
            implementation_hint: 구현 힌트 (참고 코드 등)
        """
        task = f"""
새 도구를 만들어줘:

이름: {name}
설명: {description}
구현 힌트: {implementation_hint}

1. {DATA_PATH}/packages/dev/tools/{name}/ 폴더 생성
2. tool.json 작성 (name, description, input_schema)
3. handler.py 작성 (async def execute 함수)
4. 필요하면 requirements.txt 작성

완료되면 생성된 파일들을 알려줘.
"""
        return self.execute(task)

    def test_tool(self, tool_name: str, test_input: dict) -> Dict[str, Any]:
        """
        도구 테스트 실행

        Args:
            tool_name: 테스트할 도구 이름
            test_input: 테스트 입력값
        """
        task = f"""
도구를 테스트해줘:

도구: {tool_name}
입력: {json.dumps(test_input, ensure_ascii=False)}

1. 도구의 handler.py를 찾아서 실행
2. 결과 확인
3. 에러가 있으면 원인 분석

테스트 결과를 알려줘.
"""
        return self.execute(task)


# 전역 인스턴스
_system_ai = None

def get_system_ai(work_dir: str = None) -> SystemAI:
    """시스템 AI 인스턴스 반환"""
    global _system_ai
    if _system_ai is None or work_dir:
        _system_ai = SystemAI(work_dir)
    return _system_ai
