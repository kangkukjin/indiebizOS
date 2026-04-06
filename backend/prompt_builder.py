"""
prompt_builder.py - 시스템 프롬프트 빌더
IndieBiz OS Core

기본 프롬프트 + 조건부 프롬프트(git, delegation)를 조합합니다.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Optional


# 프롬프트 파일 경로
from runtime_utils import get_base_path
PROMPTS_PATH = get_base_path() / "data" / "common_prompts"

logger = logging.getLogger(__name__)

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

    def _load_system_doc(self, filename: str) -> str:
        """data/system_docs/ 폴더에서 시스템 문서 로드 (캐시 사용)"""
        cache_key = f"__sysdoc__{filename}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        doc_path = get_base_path() / "data" / "system_docs" / filename
        if doc_path.exists():
            content = doc_path.read_text(encoding='utf-8')
            self._cache[cache_key] = content
            return content
        return ""

    def _load_guide_file(self, guide_filename: str) -> str:
        """data/guides/ 폴더에서 가이드 파일 로드 (캐시 사용)"""
        cache_key = f"__guide__{guide_filename}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        guide_path = get_base_path() / "data" / "guides" / guide_filename
        if guide_path.exists():
            content = guide_path.read_text(encoding='utf-8')
            self._cache[cache_key] = content
            return content
        return ""

    def _load_world_pulse(self) -> str:
        """World Pulse 로드 — 오늘의 세계 상태 요약

        data/guides/world_pulse.md가 존재하면 내용을 반환합니다.
        대화 시작 시 1회 주입되어 에이전트가 세계 맥락을 알고 시작합니다.
        파일이 없거나 비어있으면 빈 문자열을 반환합니다.

        주의: 캐시하지 않음 — 백그라운드 수집 완료 후 파일이 갱신될 수 있으므로
        매번 디스크에서 읽습니다. (대화 시작 시 1회만 호출되어 성능 영향 없음)
        """
        pulse_path = get_base_path() / "data" / "guides" / "world_pulse.md"
        if not pulse_path.exists():
            logger.debug("[PromptBuilder] World Pulse 파일 없음")
            return ""

        try:
            content = pulse_path.read_text(encoding='utf-8').strip()
            if not content:
                logger.debug("[PromptBuilder] World Pulse 파일이 비어있음")
                return ""
            logger.info(f"[PromptBuilder] World Pulse 주입: ~{len(content)}자")
            return content
        except Exception as e:
            logger.warning(f"[PromptBuilder] World Pulse 로드 실패: {e}")
            return ""

    def _build_resource_list(self) -> str:
        """자원 목록 생성 — guide_db.json에서 가이드 제목을 읽어 한 줄 목록으로 반환

        에이전트가 '어떤 가이드가 존재하는지' 배경 지식으로 기억하게 하여,
        능동적 검색(read_guide) 없이도 관련 가이드를 떠올릴 수 있게 합니다.
        """
        cache_key = "__resource_list__"
        if cache_key in self._cache:
            return self._cache[cache_key]

        guide_db_path = get_base_path() / "data" / "guide_db.json"
        if not guide_db_path.exists():
            return ""

        try:
            data = json.loads(guide_db_path.read_text(encoding='utf-8'))
            guides = data.get("guides", [])
            if not guides:
                return ""

            names = [g["name"] for g in guides if g.get("name")]
            if not names:
                return ""

            resource_text = "# 자원 목록\n참고 가능한 가이드: " + " / ".join(names)
            self._cache[cache_key] = resource_text
            logger.debug(f"[PromptBuilder] 자원 목록 생성: {len(names)}개 가이드, ~{len(resource_text)}자")
            return resource_text
        except Exception as e:
            logger.warning(f"[PromptBuilder] 자원 목록 생성 실패: {e}")
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
              additional_context: str = "",
              consciousness_output: dict = None,
              model_name: str = "",
              execution_memory: str = "") -> str:
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
            consciousness_output: 의식 에이전트 출력 (태스크 프레이밍, IBL 포커싱 등)
            execution_memory: 실행기억 (IBL 코드 사례 + 추천 도구 + implementation)

        Returns:
            조합된 시스템 프롬프트 문자열
        """
        parts = []

        # 0. 현재 날짜/시간 (모든 에이전트가 현재 시점을 알도록)
        from datetime import datetime
        now = datetime.now()
        date_info = f"# 현재 시점\n현재 날짜: {now.strftime('%Y년 %m월 %d일 %A')}\n현재 시간: {now.strftime('%H:%M')}"
        parts.append(date_info)

        # 1. 기본 프롬프트 (항상 포함)
        base = self._load_file("base_prompt_v5.md")
        if base:
            parts.append(base)

        # 1.5. 시스템 구조 문서 (항상 포함 — 파일 위치, 아키텍처, 패키지 목록 등)
        sys_structure = self._load_system_doc("system_structure.md")
        if sys_structure:
            parts.append(f"<system_structure>\n{sys_structure}\n</system_structure>")

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

        # 4.1 실행기억 (IBL 코드 사례 + 추천 도구 + implementation)
        if execution_memory:
            parts.append(execution_memory)

        # 4.3 의식 에이전트 출력 — IBL 포커싱 힌트 + 태스크 프레이밍
        if consciousness_output:
            consciousness_parts = []

            # 태스크 프레이밍 (지금 풀어야 할 문제 정의)
            task_framing = consciousness_output.get("task_framing", "")
            if task_framing:
                consciousness_parts.append(f"# 현재 태스크\n{task_framing}")

            # 달성 기준 (실행 에이전트가 목표를 알고 행동하도록)
            achievement_criteria = consciousness_output.get("achievement_criteria", "")
            if achievement_criteria:
                consciousness_parts.append(f"# 달성해야 할 목표의 기준\n{achievement_criteria}\n\n이 기준을 모두 충족하도록 응답을 구성하라. 응답 완성 전에 각 항목을 스스로 점검하라.")

            # NOTE: history_summary는 messages 파라미터에서 원본 히스토리를 대체하므로 여기엔 넣지 않음

            # IBL 포커싱 힌트 (제한이 아닌 초점 설정)
            ibl_focus = consciousness_output.get("ibl_focus", {})
            if ibl_focus:
                focus_parts = []
                primary = ibl_focus.get("primary_nodes", [])
                highlight = ibl_focus.get("highlight_actions", [])
                hint = ibl_focus.get("hint", "")
                if primary:
                    focus_parts.append(f"주요 노드: {', '.join(primary)}")
                if highlight:
                    focus_parts.append(f"주목할 액션: {', '.join(highlight)}")
                if hint:
                    focus_parts.append(f"접근 방향: {hint}")
                if focus_parts:
                    consciousness_parts.append(
                        "<focus note=\"참고용 힌트 — 다른 액션도 자유롭게 사용 가능\">\n"
                        + "\n".join(focus_parts)
                        + "\n</focus>"
                    )

            # 상황 메모
            context_notes = consciousness_output.get("context_notes", "")
            if context_notes:
                consciousness_parts.append(f"# 상황 메모\n{context_notes}")

            # 자기 인식 (의식 에이전트의 메타 판단 — 이 상황에서 나의 능력과 한계)
            self_awareness = consciousness_output.get("self_awareness", "")
            if self_awareness:
                sa_text = f"# 자기 인식\n{self_awareness}"
                if model_name:
                    sa_text += f"\n- AI 모델: {model_name}"
                consciousness_parts.append(sa_text)
            elif model_name:
                consciousness_parts.append(f"# 자기 인식\n- AI 모델: {model_name}")

            # 세계 상태 (의식 에이전트가 맥락에 맞게 압축한 world_pulse)
            world_state = consciousness_output.get("world_state", "")
            if world_state:
                consciousness_parts.append(f"# 세계 상태\n{world_state}")

            if consciousness_parts:
                parts.append("\n".join(consciousness_parts))

            # 의식 에이전트가 지정한 가이드 파일 로드 & 주입
            guide_files = consciousness_output.get("guide_files", [])
            for guide in guide_files:
                content = self._load_guide_file(guide)
                if content:
                    parts.append(f"# 가이드: {guide}\n{content}")

        # 4.5 자원 목록 (가이드 제목 배경 지식)
        resource_list = self._build_resource_list()
        if resource_list:
            parts.append(resource_list)

        # 4.6 World Pulse (세계 상태 배경 지식 — 대화 시작 시 1회 주입)
        # 의식 에이전트가 활성이면 world_state로 대체됨 (위에서 주입)
        if not consciousness_output:
            world_pulse = self._load_world_pulse()
            if world_pulse:
                parts.append(world_pulse)
            # 의식 에이전트 없을 때도 모델 이름은 주입
            if model_name:
                parts.append(f"# 자기 인식\n- AI 모델: {model_name}")

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
    consciousness_output: dict = None,
    model_name: str = "",
    execution_memory: str = "",
    **kwargs  # ibl_enabled 등 하위 호환 파라미터 무시
) -> str:
    """프로젝트 에이전트용 시스템 프롬프트 생성

    구조: base_prompt_v4.md + (조건부 위임) + IBL 환경 + 실행기억 + 의식 에이전트 출력 + 개별역할 + 영구메모

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
        consciousness_output: 의식 에이전트 출력 (태스크 프레이밍, IBL 포커싱 등)
        execution_memory: 실행기억 (IBL 코드 사례 + 추천 도구 + implementation)

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
        additional_context=additional_context,
        consciousness_output=consciousness_output,
        model_name=model_name,
        execution_memory=execution_memory,
    )


def build_system_ai_prompt(
    user_profile: str = "",
    git_enabled: bool = False,
    consciousness_output: dict = None,
    model_name: str = "",
    execution_memory: str = "",
) -> str:
    """시스템 AI용 시스템 프롬프트 생성

    구조: base_prompt_v2.md + (조건부 git) + IBL 환경 + 실행기억 + 의식 에이전트 출력
          + 위임 프롬프트 + 개별역할 + 시스템메모

    Args:
        user_profile: 사용자 프로필 (시스템 메모)
        git_enabled: Git 관련 프롬프트 포함 여부
        consciousness_output: 의식 에이전트 출력 (태스크 프레이밍, IBL 포커싱 등)
        execution_memory: 실행기억 (IBL 코드 사례 + 추천 도구 + implementation)

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

    # 실행기억 (IBL 코드 사례 + 추천 도구 + implementation)
    if execution_memory:
        parts.append(execution_memory)

    # 의식 에이전트 출력 반영
    if consciousness_output:
        consciousness_parts = []

        task_framing = consciousness_output.get("task_framing", "")
        if task_framing:
            consciousness_parts.append(f"# 현재 태스크\n{task_framing}")

        # 달성 기준 (실행 에이전트가 목표를 알고 행동하도록)
        achievement_criteria = consciousness_output.get("achievement_criteria", "")
        if achievement_criteria:
            consciousness_parts.append(f"# 달성해야 할 목표의 기준\n{achievement_criteria}\n\n이 기준을 모두 충족하도록 응답을 구성하라. 응답 완성 전에 각 항목을 스스로 점검하라.")

        ibl_focus = consciousness_output.get("ibl_focus", {})
        if ibl_focus:
            focus_parts = []
            primary = ibl_focus.get("primary_nodes", [])
            highlight = ibl_focus.get("highlight_actions", [])
            hint = ibl_focus.get("hint", "")
            if primary:
                focus_parts.append(f"주요 노드: {', '.join(primary)}")
            if highlight:
                focus_parts.append(f"주목할 액션: {', '.join(highlight)}")
            if hint:
                focus_parts.append(f"접근 방향: {hint}")
            if focus_parts:
                consciousness_parts.append(
                    "<focus note=\"참고용 힌트 — 다른 액션도 자유롭게 사용 가능\">\n"
                    + "\n".join(focus_parts)
                    + "\n</focus>"
                )

        context_notes = consciousness_output.get("context_notes", "")
        if context_notes:
            consciousness_parts.append(f"# 상황 메모\n{context_notes}")

        # 자기 인식 + 모델 이름
        self_awareness = consciousness_output.get("self_awareness", "")
        if self_awareness:
            sa_text = f"# 자기 인식\n{self_awareness}"
            if model_name:
                sa_text += f"\n- AI 모델: {model_name}"
            consciousness_parts.append(sa_text)
        elif model_name:
            consciousness_parts.append(f"# 자기 인식\n- AI 모델: {model_name}")

        # 세계 상태 (의식 에이전트가 맥락에 맞게 압축한 world_pulse)
        world_state = consciousness_output.get("world_state", "")
        if world_state:
            consciousness_parts.append(f"# 세계 상태\n{world_state}")

        if consciousness_parts:
            parts.append("\n".join(consciousness_parts))

        # 의식 에이전트가 지정한 가이드 파일 로드 & 주입
        guide_files = consciousness_output.get("guide_files", [])
        for guide in guide_files:
            content = builder._load_guide_file(guide)
            if content:
                parts.append(f"# 가이드: {guide}\n{content}")

    else:
        # 의식 에이전트 없을 때도 모델 이름은 주입
        if model_name:
            parts.append(f"# 자기 인식\n- AI 모델: {model_name}")

    # 자원 목록 (가이드 제목 배경 지식)
    resource_list = builder._build_resource_list()
    if resource_list:
        parts.append(resource_list)

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
