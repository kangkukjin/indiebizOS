"""
prompt_builder.py - 시스템 프롬프트 빌더
IndieBiz OS Core

기본 프롬프트 + 조건부 프롬프트(git, delegation)를 조합합니다.
"""

from pathlib import Path
from typing import List, Dict, Optional


# 프롬프트 파일 경로
from runtime_utils import get_base_path
PROMPTS_PATH = get_base_path() / "data" / "common_prompts"

# 싱글톤 인스턴스
_prompt_builder_instance: Optional['PromptBuilder'] = None


def get_prompt_builder() -> 'PromptBuilder':
    """싱글톤 PromptBuilder 인스턴스 반환"""
    global _prompt_builder_instance
    if _prompt_builder_instance is None:
        _prompt_builder_instance = PromptBuilder()
    return _prompt_builder_instance


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
              delegated_from_system_ai: bool = False,
              ibl_only: bool = False,
              allowed_nodes: list = None,
              project_path: str = None,
              agent_id: str = None,
              role_prompt: str = "",
              additional_context: str = "") -> str:
        """시스템 프롬프트 조합

        Args:
            agent_count: 프로젝트 내 에이전트 수 (2 이상이면 위임 프롬프트 포함)
            git_enabled: Git 관련 프롬프트 포함 여부
            delegated_from_system_ai: 시스템 AI로부터 위임받은 경우 (파일 경로 원칙 포함)
            ibl_only: IBL 전용 모드 (execute_ibl만 사용)
            allowed_nodes: IBL 노드 접근 제어
            project_path: 프로젝트 경로 (동료 에이전트 탐색용)
            agent_id: 현재 에이전트 ID (환경에서 자신 제외용)
            role_prompt: 에이전트 역할 프롬프트
            additional_context: 추가 컨텍스트 (프로젝트 설정 등)

        Returns:
            조합된 시스템 프롬프트 문자열
        """
        parts = []

        # 1. 기본 프롬프트 (항상 포함)
        base = self._load_file("base_prompt_v4.md")
        if base:
            parts.append(base)

        # 2. Git 프롬프트 (조건부)
        if git_enabled:
            git = self._load_file("fragments/06_git.md")
            if git:
                parts.append(git)

        # 3. 위임 프롬프트 (에이전트가 2개 이상이거나 시스템 AI가 위임한 경우)
        if agent_count > 1 or delegated_from_system_ai:
            delegation = self._load_file("fragments/09_delegation.md")
            if delegation:
                parts.append(delegation)

        # 4. IBL 환경 프롬프트 (Phase 16: 단일 경로)
        if ibl_only:
            from ibl_access import build_environment
            ibl = build_environment(allowed_nodes, project_path, agent_id)
            if ibl:
                parts.append(ibl)

        # 5. 역할 프롬프트
        if role_prompt:
            parts.append(f"\n# Role\n{role_prompt}")

        # 6. 추가 컨텍스트
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
    agent_notes: str = "",
    git_enabled: bool = False,
    delegated_from_system_ai: bool = False,
    ibl_only: bool = True,
    allowed_nodes: list = None,
    project_path: str = None,
    agent_id: str = None,
    **kwargs  # ibl_enabled 등 하위 호환 파라미터 무시
) -> str:
    """프로젝트 에이전트용 시스템 프롬프트 생성

    구조: base_prompt_v4.md + (조건부 위임) + IBL 환경 + 개별역할 + 영구메모

    Args:
        agent_name: 에이전트 이름
        role: 개별역할
        agent_count: 프로젝트 내 에이전트 수
        agent_notes: 영구메모
        git_enabled: Git 관련 프롬프트 포함 여부
        delegated_from_system_ai: 시스템 AI로부터 위임받은 경우
        ibl_only: IBL 전용 모드 (기본값 True, Phase 16 이후 모든 에이전트)
        allowed_nodes: IBL 노드 접근 제어 리스트
        project_path: 프로젝트 경로 (동료 에이전트 탐색용)
        agent_id: 현재 에이전트 ID (환경에서 자신 제외용)

    Returns:
        조합된 시스템 프롬프트
    """
    builder = get_prompt_builder()  # 싱글톤 사용

    # 개별역할 구성
    role_parts = [f"당신은 '{agent_name}'입니다."]
    if role:
        role_parts.append(role)
    role_prompt = "\n".join(role_parts)

    # 추가 컨텍스트 구성 (영구메모)
    additional_context = ""
    if agent_notes:
        additional_context = f"# Notes\n{agent_notes}"

    return builder.build(
        agent_count=agent_count,
        git_enabled=git_enabled,
        delegated_from_system_ai=delegated_from_system_ai,
        ibl_only=ibl_only,
        allowed_nodes=allowed_nodes,
        project_path=project_path,
        agent_id=agent_id,
        role_prompt=role_prompt,
        additional_context=additional_context
    )


def build_system_ai_prompt(
    user_profile: str = "",
    git_enabled: bool = False
) -> str:
    """시스템 AI용 시스템 프롬프트 생성

    구조: base_prompt_v2.md + (조건부 git) + 위임 프롬프트 + 개별역할 + 시스템메모

    Args:
        user_profile: 사용자 프로필 (시스템 메모)
        git_enabled: Git 관련 프롬프트 포함 여부

    Returns:
        조합된 시스템 프롬프트
    """
    # 개별역할 파일에서 로드
    role_path = get_base_path() / "data" / "system_ai_role.txt"
    role = role_path.read_text(encoding='utf-8') if role_path.exists() else ""

    builder = get_prompt_builder()  # 싱글톤 사용

    # 시스템 AI 기본 프롬프트 (git_enabled 조건부)
    prompt = builder.build(
        agent_count=1,
        git_enabled=git_enabled
    )

    parts = [prompt]

    # Phase 17: IBL 환경 주입 (시스템 AI는 모든 노드 접근 가능)
    from ibl_access import build_environment
    ibl_env = build_environment(allowed_nodes=None)  # None = 전체 노드
    if ibl_env:
        parts.append(ibl_env)

    # 시스템 AI 전용 위임 프롬프트 추가
    delegation_prompt = builder._load_file("fragments/10_system_ai_delegation.md")
    if delegation_prompt:
        parts.append(delegation_prompt)

    # 개별역할 추가 (프로젝트 에이전트의 role_description과 동일한 개념)
    if role and role.strip():
        parts.append(f"# Role\n{role.strip()}")

    # 시스템 메모 추가
    if user_profile and user_profile.strip():
        parts.append(f"# 시스템 메모\n{user_profile.strip()}")

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
