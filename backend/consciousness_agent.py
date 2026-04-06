"""
consciousness_agent.py - 의식 에이전트

사용자 메시지가 AI 에이전트에 도달하기 전에 메타적 판단을 수행합니다.

역할:
    1. 히스토리 정제 — 문맥상 불필요한 턴 압축, 핵심 맥락 보존
    2. IBL 포커싱 — 관련 액션/노드에 대한 강조 힌트 생성
    3. 가이드 파일 선택 — 읽어야 할 가이드 파일 지정
    4. 태스크 프레이밍 — "지금 풀어야 할 문제"를 명확히 정의

흐름:
    사용자 메시지 → 의식 에이전트 (메타 판단) → 최적화된 프롬프트 → AI 에이전트
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ConsciousnessAgent:
    """의식 에이전트 — 프롬프트의 메타 편집자

    시스템 AI의 API 설정을 사용하여 가벼운 AI 호출로
    프롬프트 구성 요소들을 지능적으로 편집합니다.
    """

    def __init__(self):
        self._provider = None
        self._prompt = None
        self._init_provider()
        self._load_prompt()

    def _init_provider(self):
        """시스템 AI의 API 설정을 가져와 프로바이더 초기화"""
        try:
            from api_system_ai import load_system_ai_config
            from providers import get_provider

            config = load_system_ai_config()
            api_key = config.get("apiKey", "")
            if not api_key:
                logger.warning("[ConsciousnessAgent] API 키 없음 — 비활성 상태")
                return

            provider_name = config.get("provider", "anthropic")
            model = config.get("model", "claude-sonnet-4-20250514")

            self._provider = get_provider(
                provider_name,
                api_key=api_key,
                model=model,
                system_prompt="",  # 호출 시마다 설정
                tools=[],
            )
            self._provider.init_client()
            print(f"[ConsciousnessAgent] 초기화 완료 ({provider_name}/{model})")
        except Exception as e:
            print(f"[ConsciousnessAgent] 초기화 실패: {e}")
            self._provider = None

    def _load_prompt(self):
        """의식 에이전트 전용 프롬프트 로드 (베이스 프롬프트 불필요 — 도구를 쓰지 않고 JSON만 출력)"""
        from runtime_utils import get_base_path

        base_path = get_base_path()
        role_path = base_path / "data" / "common_prompts" / "consciousness_prompt.md"
        if role_path.exists():
            self._prompt = role_path.read_text(encoding='utf-8')
        else:
            logger.warning(f"[ConsciousnessAgent] 프롬프트 파일 없음: {role_path}")
            self._prompt = self._default_prompt()

        # 시스템 구조 문서 항상 주입
        structure_path = base_path / "data" / "system_docs" / "system_structure.md"
        if structure_path.exists():
            structure = structure_path.read_text(encoding='utf-8')
            self._prompt += f"\n\n<system_structure>\n{structure}\n</system_structure>"

    def _default_prompt(self) -> str:
        """기본 프롬프트 (파일이 없을 때 폴백)"""
        return """당신은 의식 에이전트입니다. AI 에이전트가 사용자의 문제를 잘 풀 수 있도록 프롬프트를 메타적으로 편집합니다.
반드시 JSON 형식으로만 응답하세요."""

    @property
    def is_ready(self) -> bool:
        return self._provider is not None and self._provider.is_ready

    def process(
        self,
        user_message: str,
        history: List[Dict],
        ibl_node_summary: str,
        guide_list: List[str],
        world_pulse: str = "",
        agent_name: str = "",
        agent_role: str = "",
        agent_notes: str = "",
    ) -> Optional[Dict]:
        """의식 에이전트 실행 — 메타 판단 수행

        Args:
            user_message: 사용자의 현재 메시지
            history: 대화 히스토리 원본 (정제 전)
            ibl_node_summary: IBL 노드/액션 요약 (노드명: [액션들])
            guide_list: 사용 가능한 가이드 파일 목록
            world_pulse: 현재 세계 상태 요약
            agent_name: 에이전트 이름
            agent_role: 에이전트 역할 (전문)
            agent_notes: 에이전트 영구메모

        Returns:
            의식 에이전트 출력 dict 또는 None (실패 시)
            {
                "history_summary": str,    # 히스토리 맥락 요약 (원본 대체)
                "task_framing": str,       # 지금 풀어야 할 문제 정의
                "achievement_criteria": str, # 달성 기준 (비어있으면 평가 루프 안 탐)
                "ibl_focus": {             # IBL 포커싱
                    "primary_nodes": list,     # 주요 노드
                    "highlight_actions": list, # 강조할 액션
                    "hint": str                # AI에게 줄 힌트
                },
                "guide_files": list[str],  # 읽어야 할 가이드 파일
                "context_notes": str       # 추가 상황 메모
            }
        """
        if not self.is_ready:
            print("[ConsciousnessAgent] 비활성 — 패스스루")
            return None

        # 입력 구성
        input_text = self._build_input(
            user_message, history, ibl_node_summary,
            guide_list, world_pulse, agent_name, agent_role, agent_notes
        )

        try:
            # 시스템 프롬프트 설정
            self._provider.system_prompt = self._prompt

            print(f"[ConsciousnessAgent] AI 호출 시작 (입력 {len(input_text)}자)")

            # AI 호출 (도구 없이, 히스토리 없이 — 원샷, 503 재시도)
            import time as _time
            response = ""
            max_retries = 2
            for attempt in range(max_retries + 1):
                response = self._provider.process_message(
                    message=input_text,
                    history=[],
                    images=None,
                    execute_tool=None
                )
                if response and response.strip():
                    break
                if attempt < max_retries:
                    wait_sec = 2 * (attempt + 1)
                    print(f"[ConsciousnessAgent] 빈 응답 (503 등), {wait_sec}초 후 재시도 ({attempt + 1}/{max_retries})")
                    _time.sleep(wait_sec)

            print(f"[ConsciousnessAgent] AI 응답 수신 ({len(response)}자)")
            print(f"[ConsciousnessAgent] 원본 응답:\n{response}")

            # JSON 파싱
            result = self._parse_response(response)
            if result:
                import json as _json
                print(f"[ConsciousnessAgent] 파싱 결과:\n{_json.dumps(result, ensure_ascii=False, indent=2)}")
            else:
                print(f"[ConsciousnessAgent] JSON 파싱 실패")
            return result

        except Exception as e:
            print(f"[ConsciousnessAgent] 처리 실패: {e}")
            return None

    def _build_input(
        self,
        user_message: str,
        history: List[Dict],
        ibl_node_summary: str,
        guide_list: List[str],
        world_pulse: str,
        agent_name: str,
        agent_role: str,
        agent_notes: str = "",
    ) -> str:
        """의식 에이전트에 전달할 입력 텍스트 구성"""
        parts = []

        # 에이전트 정보 (역할 전문 + 영구메모 — self_awareness 판단용)
        if agent_name:
            agent_parts = [f"<agent name=\"{agent_name}\">"]
            if agent_role:
                agent_parts.append(f"<role>\n{agent_role}\n</role>")
            if agent_notes:
                agent_parts.append(f"<notes>\n{agent_notes}\n</notes>")
            agent_parts.append("</agent>")
            parts.append("\n".join(agent_parts))

        # 세계 상태
        if world_pulse:
            parts.append(f"<world_pulse>\n{world_pulse}\n</world_pulse>")

        # 히스토리
        if history:
            parts.append("<history>")
            for i, turn in enumerate(history):
                role = turn.get("role", "unknown")
                content = turn.get("content", "")
                has_images = bool(turn.get("images"))
                # 긴 내용은 앞부분만 전달 (의식 에이전트는 판단만 하므로)
                if len(content) > 500:
                    content = content[:500] + f"... ({len(content)}자)"
                img_attr = ' has_images="true"' if has_images else ''
                parts.append(f"<turn index=\"{i}\" role=\"{role}\"{img_attr}>{content}</turn>")
            parts.append("</history>")

        # IBL 노드/액션 요약
        if ibl_node_summary:
            parts.append(f"<ibl_nodes>\n{ibl_node_summary}\n</ibl_nodes>")

        # 가이드 파일 목록
        if guide_list:
            parts.append(f"<available_guides>\n{', '.join(guide_list)}\n</available_guides>")

        # 사용자 메시지 (마지막에 — 가장 중요)
        parts.append(f"<user_message>\n{user_message}\n</user_message>")

        return "\n\n".join(parts)

    def _parse_response(self, response: str) -> Optional[Dict]:
        """AI 응답에서 JSON 추출 및 파싱"""
        if not response:
            return None

        # JSON 블록 추출 시도
        text = response.strip()

        # ```json ... ``` 블록 추출
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            text = text[start:end].strip()
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            text = text[start:end].strip()

        # { 로 시작하는 부분만 추출
        if "{" in text:
            brace_start = text.index("{")
            # 마지막 } 찾기
            brace_end = text.rindex("}") + 1
            text = text[brace_start:brace_end]

        try:
            result = json.loads(text)
            # 필수 필드 검증
            if "task_framing" not in result:
                logger.warning("[ConsciousnessAgent] task_framing 누락")
                return None
            return result
        except json.JSONDecodeError as e:
            logger.warning(f"[ConsciousnessAgent] JSON 파싱 실패: {e}\n응답: {response[:200]}")
            return None


# ============ 유틸리티 함수 ============


def get_guide_list(user_message: str = "") -> List[str]:
    """사용자 메시지 기반 관련 가이드 상위 10개 반환 (키워드 매칭)

    guide_db.json의 keywords와 사용자 메시지를 매칭하여
    관련도 높은 순으로 최대 10개를 "파일명 - 설명" 형태로 반환합니다.
    user_message가 없으면 전체 목록을 반환합니다 (하위 호환).
    """
    from runtime_utils import get_base_path

    guide_db_path = get_base_path() / "data" / "guide_db.json"
    if not guide_db_path.exists():
        return []

    try:
        import json as _json
        data = _json.loads(guide_db_path.read_text(encoding='utf-8'))
        guides = data.get("guides", [])
        if not guides:
            return []

        # 메시지가 없으면 전체 반환 (하위 호환)
        if not user_message:
            return [f"{g['file']} - {g['description']}" for g in guides if g.get("file")]

        # 키워드 매칭: 사용자 메시지에 키워드가 포함되면 점수 +1
        msg_lower = user_message.lower()
        scored = []
        for g in guides:
            score = 0
            for kw in g.get("keywords", []):
                if kw.lower() in msg_lower:
                    score += 1
            if score > 0:
                scored.append((score, g))

        # 점수 내림차순 정렬, 상위 10개
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:10]

        if not top:
            return []

        return [f"{g['file']} - {g['description']}" for _, g in top]

    except Exception as e:
        logger.warning(f"[ConsciousnessAgent] 가이드 목록 생성 실패: {e}")
        return []


def get_world_pulse_text() -> str:
    """World Pulse 텍스트 반환"""
    from runtime_utils import get_base_path
    pulse_path = get_base_path() / "data" / "guides" / "world_pulse.md"
    if pulse_path.exists():
        try:
            return pulse_path.read_text(encoding='utf-8').strip()
        except Exception:
            pass
    return ""


# ============ 싱글톤 ============

_consciousness_instance: Optional[ConsciousnessAgent] = None
_unconscious_provider = None  # 무의식 AI 전용 프로바이더 (싱글톤)
_unconscious_provider_initialized = False
_unconscious_prompt_cache: str = ""


def get_unconscious_prompt() -> str:
    """무의식 에이전트 프롬프트 로드 (캐시). 의식 에이전트와 동일한 패턴."""
    global _unconscious_prompt_cache
    if not _unconscious_prompt_cache:
        from runtime_utils import get_base_path
        prompt_path = get_base_path() / "data" / "common_prompts" / "unconscious_prompt.md"
        try:
            _unconscious_prompt_cache = prompt_path.read_text(encoding='utf-8')
        except FileNotFoundError:
            _unconscious_prompt_cache = "EXECUTE 또는 THINK 중 하나만 답하라."
    return _unconscious_prompt_cache


def _get_unconscious_provider():
    """무의식 AI 전용 프로바이더 반환. 설정이 없으면 None (의식 에이전트로 폴백)."""
    global _unconscious_provider, _unconscious_provider_initialized
    if _unconscious_provider_initialized:
        return _unconscious_provider

    _unconscious_provider_initialized = True
    try:
        from api_config import UNCONSCIOUS_AI_CONFIG_PATH
        import json as _json

        if not UNCONSCIOUS_AI_CONFIG_PATH.exists():
            return None

        with open(UNCONSCIOUS_AI_CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = _json.load(f)

        api_key = config.get("apiKey", "").strip()
        if not api_key:
            return None

        provider_name = config.get("provider", "google").strip()
        model_name = config.get("model", "gemini-2.0-flash-lite").strip()

        from providers import get_provider
        _unconscious_provider = get_provider(
            provider_name,
            api_key=api_key,
            model=model_name,
            system_prompt="",
            tools=[],
        )
        _unconscious_provider.init_client()
        print(f"[UnconsciousAI] 초기화 완료 ({config.get('provider')}/{config.get('model')})")
        return _unconscious_provider
    except Exception as e:
        print(f"[UnconsciousAI] 초기화 실패 (의식 에이전트로 폴백): {e}")
        return None


def get_consciousness_agent() -> ConsciousnessAgent:
    """싱글톤 ConsciousnessAgent 인스턴스 반환"""
    global _consciousness_instance
    if _consciousness_instance is None:
        _consciousness_instance = ConsciousnessAgent()
    return _consciousness_instance


def lightweight_ai_call(prompt: str, system_prompt: str = None) -> Optional[str]:
    """경량 원샷 AI 호출.

    무의식 AI 전용 프로바이더가 있으면 우선 사용하고,
    없으면 의식 에이전트의 프로바이더로 폴백한다.

    Args:
        prompt: 전달할 메시지
        system_prompt: 시스템 프롬프트 (지정 시 해당 프롬프트 사용)

    용도: 무의식 에이전트 분류, 달성 기준 평가 등 가벼운 AI 호출.
    """
    # 1차: 무의식 AI 전용 프로바이더
    provider = _get_unconscious_provider()

    # 2차: 의식 에이전트 프로바이더로 폴백
    if provider is None:
        agent = get_consciousness_agent()
        if not agent.is_ready or not agent._provider:
            return None
        provider = agent._provider

    # 시스템 프롬프트 임시 교체
    original_system_prompt = None
    if system_prompt is not None:
        original_system_prompt = provider.system_prompt
        provider.system_prompt = system_prompt

    try:
        return provider.process_message(
            message=prompt,
            history=[],
            images=None,
            execute_tool=None
        )
    except Exception as e:
        logger.warning(f"[lightweight_ai_call] 실패: {e}")
        return None
    finally:
        if original_system_prompt is not None:
            provider.system_prompt = original_system_prompt
