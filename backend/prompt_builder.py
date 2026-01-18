"""
prompt_builder.py - 시스템 프롬프트 빌더
IndieBiz OS Core

기본 프롬프트 + 조건부 프롬프트(git, delegation)를 조합합니다.
"""

from pathlib import Path
from typing import List, Dict


# 프롬프트 파일 경로
PROMPTS_PATH = Path(__file__).parent.parent / "data" / "common_prompts"


class PromptBuilder:
    """시스템 프롬프트 빌더

    base_prompt.md (항상 포함) + 조건부 프롬프트를 조합합니다.

    사용 예시:
        builder = PromptBuilder()
        prompt = builder.build(agent_count=3, git_enabled=True)
    """

    def __init__(self, prompts_path: Path = None):
        self.prompts_path = prompts_path or PROMPTS_PATH
        self._cache: Dict[str, str] = {}

    def _load_file(self, filename: str) -> str:
        """프롬프트 파일 로드 (캐시 사용)"""
        if filename in self._cache:
            return self._cache[filename]

        file_path = self.prompts_path / filename
        if file_path.exists():
            content = file_path.read_text(encoding='utf-8')
            self._cache[filename] = content
            return content
        return ""

    def build(self,
              agent_count: int = 1,
              git_enabled: bool = False,
              role_prompt: str = "",
              additional_context: str = "") -> str:
        """시스템 프롬프트 조합

        Args:
            agent_count: 프로젝트 내 에이전트 수 (2 이상이면 위임 프롬프트 포함)
            git_enabled: Git 관련 프롬프트 포함 여부
            role_prompt: 에이전트 역할 프롬프트
            additional_context: 추가 컨텍스트 (프로젝트 설정 등)

        Returns:
            조합된 시스템 프롬프트 문자열
        """
        parts = []

        # 1. 기본 프롬프트 (항상 포함)
        base = self._load_file("base_prompt_v2.md")
        if base:
            parts.append(base)

        # 2. Git 프롬프트 (조건부)
        if git_enabled:
            git = self._load_file("fragments/06_git.md")
            if git:
                parts.append(git)

        # 3. 위임 프롬프트 (에이전트가 2개 이상일 때)
        if agent_count > 1:
            delegation = self._load_file("fragments/09_delegation.md")
            if delegation:
                parts.append(delegation)

        # 4. 역할 프롬프트
        if role_prompt:
            parts.append(f"\n# Role\n{role_prompt}")

        # 5. 추가 컨텍스트
        if additional_context:
            parts.append(f"\n{additional_context}")

        return "\n\n".join(parts)

    def estimate_tokens(self, prompt: str) -> int:
        """프롬프트 토큰 수 추정 (대략 4자당 1토큰)"""
        return len(prompt) // 4

    def clear_cache(self):
        """파일 캐시 초기화"""
        self._cache.clear()


# 편의 함수들

def build_agent_prompt(
    agent_name: str,
    role: str = "",
    agent_count: int = 1,
    project_settings: str = "",
    agent_notes: str = "",
    git_enabled: bool = False
) -> str:
    """프로젝트 에이전트용 시스템 프롬프트 생성

    Args:
        agent_name: 에이전트 이름
        role: 에이전트 역할 설명
        agent_count: 프로젝트 내 에이전트 수
        project_settings: 프로젝트 공통 설정
        agent_notes: 에이전트별 메모
        git_enabled: Git 관련 프롬프트 포함 여부

    Returns:
        조합된 시스템 프롬프트
    """
    builder = PromptBuilder()

    # 역할 프롬프트 구성
    role_parts = [f"당신은 '{agent_name}'입니다."]
    if role:
        role_parts.append(role)
    role_prompt = "\n".join(role_parts)

    # 추가 컨텍스트 구성
    additional_parts = []
    if project_settings:
        additional_parts.append(f"# Project Guidelines\n{project_settings}")
    if agent_notes:
        additional_parts.append(f"# Notes\n{agent_notes}")
    additional_context = "\n\n".join(additional_parts)

    return builder.build(
        agent_count=agent_count,
        git_enabled=git_enabled,
        role_prompt=role_prompt,
        additional_context=additional_context
    )


def build_system_ai_prompt(
    user_profile: str = "",
    role: str = None
) -> str:
    """시스템 AI용 시스템 프롬프트 생성

    구조: 공통설정(base_prompt.md) + 개별역할(role) + 사용자정보

    Args:
        user_profile: 사용자 프로필
        role: 개별역할 프롬프트 (None이면 파일에서 로드)

    Returns:
        조합된 시스템 프롬프트
    """
    # 역할 프롬프트를 별도 파일에서 로드 (프로젝트 에이전트와 동일한 구조)
    if role is None:
        role_path = Path(__file__).parent.parent / "data" / "system_ai_role.txt"
        if role_path.exists():
            role = role_path.read_text(encoding='utf-8')
        else:
            role = ""

    builder = PromptBuilder()

    # 시스템 AI는 위임 기능 없음, Git도 기본 비활성화
    prompt = builder.build(
        agent_count=1,
        git_enabled=False
    )

    parts = [prompt]

    # 개별역할 추가 (프로젝트 에이전트의 role_description과 동일한 개념)
    if role and role.strip():
        parts.append(f"# Role\n{role.strip()}")

    # 시스템 메모 추가
    if user_profile and user_profile.strip():
        parts.append(f"# 시스템 메모\n{user_profile.strip()}")

    parts.append("지금부터 사용자와 대화합니다.")

    return "\n\n".join(parts)


# 테스트용
if __name__ == "__main__":
    builder = PromptBuilder()

    # 테스트 1: 기본 (위임 없음, git 없음)
    prompt1 = builder.build(agent_count=1)
    print(f"기본: {builder.estimate_tokens(prompt1)} 토큰")
    print()

    # 테스트 2: 위임 + Git
    prompt2 = builder.build(agent_count=3, git_enabled=True)
    print(f"위임 + Git: {builder.estimate_tokens(prompt2)} 토큰")
