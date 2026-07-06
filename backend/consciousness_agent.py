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
import re
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
        """모델 기어 '의식' 축으로 프로바이더 초기화.

        과거엔 system_ai_config 를 직접 읽어 시스템AI와 같은 모델로 용접돼 있었으나,
        이제 model_resolver.resolve('consciousness') 로 의식 축을 따로 해소한다(기어 프리셋이
        의식과 실행을 다른 티어로 가를 수 있음). 키/모델 비면 비활성(기존 동작 보존)."""
        try:
            from model_resolver import resolve
            from providers import get_provider

            d = resolve("consciousness")
            provider_name = d.get("provider") or "anthropic"
            model = d.get("model") or ""
            api_key = d.get("api_key") or ""

            # claude_code/ollama 는 자체 인증(OAuth/로컬)이라 키 불요. 그 외엔 키 없으면 비활성.
            no_key = {"claude_code", "claude-code", "claudecode", "ollama"}
            if not model or (not api_key and provider_name.lower() not in no_key):
                logger.warning(f"[ConsciousnessAgent] 모델/키 없음 — 비활성 (source={d.get('source')})")
                return

            self._provider = get_provider(
                provider_name,
                api_key=api_key,
                model=model,
                system_prompt="",  # 호출 시마다 설정
                tools=[],
            )
            self._provider.init_client()
            # 메타 역할 provider는 메인 에이전트와 session_key가 충돌하므로
            # claude_code provider의 세션 연속성 비활성화 (no-op on other providers)
            if hasattr(self._provider, "disable_session_persistence"):
                self._provider.disable_session_persistence = True
            print(f"[ConsciousnessAgent] 초기화 완료 ({provider_name}/{model}, {d.get('source')})")
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

        # 시스템 구조 문서(정체성 코어)만 항상 주입 — 디렉토리/파일 트리는
        # codebase_map 가이드로 분리(get_system_structure_core)
        try:
            from prompt_builder import get_system_structure_core
            structure = get_system_structure_core()
        except Exception:
            structure = ""
        if structure:
            self._prompt += f"\n\n<system_structure>\n{structure}\n</system_structure>"

        # IBL 환경 주입 — 문법서 + **액션 카탈로그(사전) 전체**.
        # 의식이 어떤 액션이 실재하는지 알아야 capability_focus.highlight_actions를 *검증 가능하게*
        # 줄 수 있다(prompt의 "실제 존재하는 액션만" 규칙이 비로소 지켜짐). build_environment =
        # 12_ibl_only.md(문법) + 노드별 카탈로그 → 별도 12_ibl_only 주입은 불필요(중복).
        # ★시스템 프롬프트(캐시 prefix)에 박히므로 비용은 캐시-읽기. 카탈로그가 바뀌면(/packages/reload)
        #  reset_consciousness_agent 로 재빌드해 stale 방지(api_packages 가 호출).
        try:
            from ibl_access import build_environment
            self._prompt += f"\n\n{build_environment()}"
        except Exception as e:
            logger.warning(f"[ConsciousnessAgent] IBL 환경 주입 실패, 문법서 폴백: {e}")
            ibl_only_path = base_path / "data" / "common_prompts" / "fragments" / "12_ibl_only.md"
            if ibl_only_path.exists():
                self._prompt += f"\n\n{ibl_only_path.read_text(encoding='utf-8')}"

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
        associative_memory: str,
        guide_list: List[str],
        world_pulse: str = "",
        agent_name: str = "",
        agent_role: str = "",
        agent_notes: str = "",
        available_tools: Optional[List[str]] = None,
    ) -> Optional[Dict]:
        """의식 에이전트 실행 — 메타 판단 수행

        Args:
            user_message: 사용자의 현재 메시지
            history: 대화 히스토리 원본 (정제 전)
            associative_memory: 연상기억 — <execution_memory>(해마) +
                <related_memory>(심층메모리) self-describing 묶음
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
                "capability_focus": {      # IBL 포커싱 (프롬프트 응답 형식 키)
                    "primary_nodes": list,     # 주요 노드
                    "highlight_actions": list, # 강조할 액션
                    "hint": str,               # AI에게 줄 힌트
                    "tools": list              # IBL 외 가용 도구
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
            user_message, history, associative_memory,
            guide_list, world_pulse, agent_name, agent_role, agent_notes,
            available_tools,
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
                # 의식이 추천한 도구를 실제 가용 도구로 필터링.
                # 가용 목록 밖의 도구를 추천하면 실행 에이전트가 헛걸음(ToolSearch 실패 등)
                # 한다 — 라벨지 케이스에서 ask_user_question이 그 사례.
                if available_tools is not None:
                    self._filter_unavailable_tools(result, available_tools)
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
        associative_memory: str,
        guide_list: List[str],
        world_pulse: str,
        agent_name: str,
        agent_role: str,
        agent_notes: str = "",
        available_tools: Optional[List[str]] = None,
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

        # 연상기억 — <execution_memory>(해마) + <related_memory>(심층메모리)
        # 내부 태그가 이미 self-describing이므로 외부 래퍼를 두지 않는다.
        if associative_memory:
            parts.append(associative_memory)

        # 가이드 파일 목록
        if guide_list:
            parts.append(f"<available_guides>\n{', '.join(guide_list)}\n</available_guides>")

        # 가용 도구 목록 — 의식이 capability_focus.tools에 추천할 때
        # 이 목록 밖의 도구를 적으면 실행 에이전트가 헛걸음한다.
        if available_tools:
            parts.append(
                "<available_tools note=\"capability_focus.tools에는 이 목록의 도구만 적어라. "
                "이외 도구를 추천하면 실행 에이전트가 도구를 찾지 못해 헛걸음한다.\">\n"
                f"{', '.join(available_tools)}\n"
                "</available_tools>"
            )

        # 사용자 메시지 (마지막에 — 가장 중요)
        parts.append(f"<user_message>\n{user_message}\n</user_message>")

        return "\n\n".join(parts)

    def _filter_unavailable_tools(self, result: Dict, available_tools: List[str]) -> None:
        """의식 출력의 capability_focus.tools에서 가용 도구 외 항목을 제거.

        의식 에이전트가 ask_user_question 같은 도구를 추천했는데 실제 에이전트에
        없으면, 실행 에이전트가 그 도구를 찾으려 헛걸음한다 (예: Claude Code의
        ToolSearch 실패). 사일런트하게 제거하지 않고 로그로 남겨서 의식 프롬프트
        개선의 단서로 쓴다.
        """
        cap = result.get("capability_focus")
        if not isinstance(cap, dict):
            return
        tools = cap.get("tools")
        if not isinstance(tools, list):
            return
        available_set = set(available_tools)
        kept = [t for t in tools if isinstance(t, str) and t in available_set]
        dropped = [t for t in tools if isinstance(t, str) and t not in available_set]
        if dropped:
            print(f"[ConsciousnessAgent] 가용하지 않은 도구 제거: {dropped} "
                  f"(가용: {sorted(available_set)})")
        cap["tools"] = kept

    def _parse_response(self, response: str) -> Optional[Dict]:
        """AI 응답에서 JSON 추출 및 파싱.

        엄격 파싱 실패 시 trailing comma 같은 흔한 LLM 오류를 정리해 재시도한다.
        의식 에이전트의 JSON 한 글자 오류가 평가 루프 전체를 무력화하는 fragility
        방지가 목적 (2026-05-28 사례: opus가 capability_focus 마지막 키 뒤에
        trailing comma를 붙여 consciousness_output=None 되어 평가 루프가 침묵).
        """
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

        # { 로 시작하는 부분만 추출 — `}` 누락 같은 깨진 응답은 None으로 graceful fail
        if "{" in text:
            brace_start = text.index("{")
            if "}" not in text[brace_start:]:
                logger.warning(
                    f"[ConsciousnessAgent] JSON 파싱 실패 (닫는 중괄호 없음)\n응답: {response[:200]}"
                )
                return None
            brace_end = text.rindex("}") + 1
            text = text[brace_start:brace_end]

        # 1차: 엄격 파싱
        try:
            result = json.loads(text)
        except json.JSONDecodeError as e1:
            # 2차: 흔한 LLM 출력 오류 청소 후 재시도.
            # - trailing comma: `,\s*[}\]]` → 닫기 괄호만 남김.
            # 다른 오류(single quote 등)는 의식 에이전트에서 거의 안 보여 대응 안 함.
            cleaned = re.sub(r",(\s*[}\]])", r"\1", text)
            if cleaned != text:
                try:
                    result = json.loads(cleaned)
                    # 어디서 청소가 일어났는지 가시화 — opus 출력 안정성 모니터링용.
                    print(f"[ConsciousnessAgent] JSON 청소 후 파싱 성공 (trailing comma 등 제거). 원본 오류: {e1}")
                except json.JSONDecodeError as e2:
                    logger.warning(
                        f"[ConsciousnessAgent] JSON 파싱 실패 (청소 후에도): {e2}\n응답: {response[:200]}"
                    )
                    return None
            else:
                logger.warning(
                    f"[ConsciousnessAgent] JSON 파싱 실패 (청소 대상 없음): {e1}\n응답: {response[:200]}"
                )
                return None

        # 필수 필드 검증
        if "task_framing" not in result:
            logger.warning("[ConsciousnessAgent] task_framing 누락")
            return None
        return result


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
            # 매칭 0건 — 키워드가 사용자 표현과 안 맞을 수 있으므로 전체 목록을 fallback으로 제공.
            # 의식 에이전트가 가이드 description을 보고 직접 고르도록.
            return [f"{g['file']} - {g['description']}" for g in guides if g.get("file")]

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
_lightweight_provider = None  # 경량 AI 전용 프로바이더 (싱글톤)
_lightweight_provider_initialized = False
_midtier_provider = None  # 중급 AI 전용 프로바이더 (싱글톤)
_midtier_provider_initialized = False
_system_oneshot_provider = None  # 본격(system_ai) 원샷 프로바이더 (싱글톤, 도구·세션 없음)
_system_oneshot_provider_initialized = False
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


def _get_lightweight_provider():
    """경량 AI 전용 프로바이더 반환. 설정이 없으면 None (의식 에이전트로 폴백)."""
    global _lightweight_provider, _lightweight_provider_initialized
    if _lightweight_provider_initialized:
        return _lightweight_provider

    _lightweight_provider_initialized = True
    try:
        from api_config import LIGHTWEIGHT_AI_CONFIG_PATH, UNCONSCIOUS_AI_CONFIG_PATH
        import json as _json

        # 하위호환: lightweight 없으면 unconscious 폴백
        config_path = LIGHTWEIGHT_AI_CONFIG_PATH if LIGHTWEIGHT_AI_CONFIG_PATH.exists() else UNCONSCIOUS_AI_CONFIG_PATH
        if not config_path.exists():
            return None

        with open(config_path, 'r', encoding='utf-8') as f:
            config = _json.load(f)

        api_key = config.get("apiKey", "").strip()
        if not api_key:
            return None

        provider_name = config.get("provider", "google").strip()
        model_name = config.get("model", "gemini-2.5-flash-lite").strip()

        from providers import get_provider
        _lightweight_provider = get_provider(
            provider_name,
            api_key=api_key,
            model=model_name,
            system_prompt="",
            tools=[],
        )
        _lightweight_provider.init_client()
        # 분류·평가·증류용 — 메인 에이전트와 session_key 충돌 방지를 위해 세션 비활성
        if hasattr(_lightweight_provider, "disable_session_persistence"):
            _lightweight_provider.disable_session_persistence = True
        print(f"[LightweightAI] 초기화 완료 ({provider_name}/{model_name})")
        return _lightweight_provider
    except Exception as e:
        print(f"[LightweightAI] 초기화 실패 (의식 에이전트로 폴백): {e}")
        return None


# 하위호환 별칭
_get_unconscious_provider = _get_lightweight_provider


def _get_midtier_provider():
    """reflex 프로바이더 반환 — 모델 기어 'reflex' 역할로 해소(2026-06-30부터 *경량 티어 고정*).
    ※ 함수명은 레거시(옛 중급). 실제 모델은 model_resolver 의 reflex→경량 고정이 정한다.

    reflex(해마 고확신) 경로가 provider 자체를 변이(system_prompt/tools/agent_id 복사)해
    ai._provider 로 스왑하므로 session 버킷(원샷과 객체 분리)으로 받는다. 같은 reflex 객체를
    여러 호출이 공유(옛 _midtier_provider 싱글턴과 동일 — 동기 호출이라 변이→사용이 밀착).
    리졸버 실패/모델 미설정 시 옛 midtier_ai_config 직접 로드로 폴백."""
    try:
        from model_resolver import get_provider_for
        prov, _d = get_provider_for("reflex", oneshot=False)
        if prov is not None:
            return prov
    except Exception as e:
        print(f"[MidtierAI] 리졸버 해소 실패(옛 config 폴백): {e}")
    return _get_midtier_provider_legacy()


def _get_midtier_provider_legacy():
    """옛 경로: midtier_ai_config 직접 로드(리졸버 폴백). 3단계서 제거 예정."""
    global _midtier_provider, _midtier_provider_initialized
    if _midtier_provider_initialized:
        return _midtier_provider

    _midtier_provider_initialized = True
    try:
        from api_config import MIDTIER_AI_CONFIG_PATH
        import json as _json

        if not MIDTIER_AI_CONFIG_PATH.exists():
            return None

        with open(MIDTIER_AI_CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = _json.load(f)

        if not config.get("enabled", True):
            return None

        provider_name = config.get("provider", "google").strip()
        model_name = config.get("model", "gemini-2.5-flash").strip()

        # API 키 없으면 시스템 AI 키 사용. 단 claude_code/ollama는 자체 인증 경로(OAuth/로컬)가
        # 있으므로 api_key 요구를 건너뛴다.
        api_key = config.get("apiKey", "").strip()
        providers_without_api_key = {"claude_code", "claude-code", "claudecode", "ollama"}
        if not api_key and provider_name.lower() not in providers_without_api_key:
            from api_config import SYSTEM_AI_CONFIG_PATH
            if SYSTEM_AI_CONFIG_PATH.exists():
                with open(SYSTEM_AI_CONFIG_PATH, 'r', encoding='utf-8') as f:
                    sys_config = _json.load(f)
                api_key = sys_config.get("apiKey", "").strip()
            if not api_key:
                return None

        from providers import get_provider
        _midtier_provider = get_provider(
            provider_name,
            api_key=api_key,
            model=model_name,
            system_prompt="",
            tools=[],
        )
        _midtier_provider.init_client()
        print(f"[MidtierAI] 초기화 완료 ({provider_name}/{model_name})")
        return _midtier_provider
    except Exception as e:
        print(f"[MidtierAI] 초기화 실패 (본격 모델 유지): {e}")
        return None


def _clear_resolver_cache():
    """모델 기어 리졸버의 provider 캐시도 비운다 — 티어 config 변경이 즉시 반영되도록.
    (리졸버 경로가 옛 싱글턴을 대체했으므로 reset 훅들이 이쪽도 비워야 핫리로드 유지.)"""
    try:
        from model_resolver import clear_provider_cache
        clear_provider_cache()
    except Exception:
        pass


def reset_midtier_provider():
    """중급/reflex 프로바이더 캐시 초기화 (설정 변경 시 호출)"""
    global _midtier_provider, _midtier_provider_initialized
    _midtier_provider = None
    _midtier_provider_initialized = False
    _clear_resolver_cache()


def reset_lightweight_provider():
    """경량 AI 프로바이더 캐시 초기화 (설정 변경 시 호출)"""
    global _lightweight_provider, _lightweight_provider_initialized
    _lightweight_provider = None
    _lightweight_provider_initialized = False
    _clear_resolver_cache()


def reset_consciousness_agent():
    """의식 에이전트 싱글턴 초기화 — 기어/설정 변경 시 호출(다음 호출에서 새 티어로 재구성).
    리졸버 캐시도 비워 의식 provider 가 새 모델로 다시 빌드되게 한다."""
    global _consciousness_instance
    _consciousness_instance = None
    _clear_resolver_cache()


def get_consciousness_agent() -> ConsciousnessAgent:
    """싱글톤 ConsciousnessAgent 인스턴스 반환"""
    global _consciousness_instance
    if _consciousness_instance is None:
        _consciousness_instance = ConsciousnessAgent()
    return _consciousness_instance


def _resolve_oneshot_provider(role: str):
    """모델 기어 리졸버로 role 에 맞는 *원샷* 프로바이더 획득.

    리졸버(model_resolver.get_provider_for)가 현재 기어→축→티어로 모델을 해소한다.
    원샷 계약(분류·평가·증류)이라 oneshot 버킷(세션 비활성)으로 획득 — 메인 에이전트와
    session_key 충돌 방지 + reflex 같은 변이형 provider 와 캐시 객체 분리.
    리졸버 실패/모델 미설정 시 None → 호출부가 옛 getter 로 폴백."""
    try:
        from model_resolver import get_provider_for
        provider, _desc = get_provider_for(role, oneshot=True)
    except Exception as e:
        logger.warning(f"[model_resolver] role={role} provider 획득 실패: {e}")
        return None
    return provider


def lightweight_ai_call(prompt: str, system_prompt: str = None,
                        images: list = None, role: str = "classify") -> Optional[str]:
    """경량 원샷 AI 호출 — 모델은 기어 리졸버가 role 로 해소한다.

    리졸버 프로바이더 우선 → 옛 경량 getter → 의식 에이전트 순으로 폴백.

    Args:
        prompt: 전달할 메시지
        system_prompt: 시스템 프롬프트 (지정 시 해당 프롬프트 사용)
        images: 멀티모달 입력 [{"base64": "...", "media_type": "image/png"}]
            지정 시 경량 모델이 이미지를 직접 본다(평가자가 시각 산출물을 검수할 때).
            경량 프로바이더(google gemini)가 비전 가능. None이면 기존 텍스트 전용 동작.
        role: 모델 기어 역할(classify/background/...). 기본 classify.
            분류·백그라운드(증류·포식·압축) 모두 분류 축→경량 티어로 해소(동일 동작).

    용도: 무의식 에이전트 분류, 경험 증류, 포식 정리 등 가벼운 AI 호출.
    """
    # 1차: 기어 리졸버 (role → 축 → 티어 → 모델)
    provider = _resolve_oneshot_provider(role)

    # 2차: 옛 경량 AI 전용 프로바이더 폴백
    if provider is None:
        provider = _get_lightweight_provider()

    # 3차: 의식 에이전트 프로바이더로 폴백
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
            images=images,
            execute_tool=None
        )
    except Exception as e:
        logger.warning(f"[lightweight_ai_call] 실패: {e}")
        return None
    finally:
        if original_system_prompt is not None:
            provider.system_prompt = original_system_prompt


def _get_system_oneshot_provider():
    """본격(system_ai) 원샷 프로바이더 — system_ai_config 기반, 도구·세션 없는 1회 호출용.

    의식 에이전트의 _provider(시스템 프롬프트·도구 적재)와 달리, 번역 같은 *원샷*용으로
    깨끗한 프로바이더를 따로 둔다(경량/중급 getter와 같은 패턴)."""
    global _system_oneshot_provider, _system_oneshot_provider_initialized
    if _system_oneshot_provider_initialized:
        return _system_oneshot_provider

    _system_oneshot_provider_initialized = True
    try:
        from api_config import SYSTEM_AI_CONFIG_PATH
        import json as _json
        if not SYSTEM_AI_CONFIG_PATH.exists():
            return None
        with open(SYSTEM_AI_CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = _json.load(f)

        provider_name = config.get("provider", "google").strip()
        model_name = config.get("model", "").strip()
        api_key = config.get("apiKey", "").strip()
        # claude_code/ollama 는 자체 인증(OAuth/로컬)이라 api_key 불요
        providers_without_api_key = {"claude_code", "claude-code", "claudecode", "ollama"}
        if not api_key and provider_name.lower() not in providers_without_api_key:
            return None

        from providers import get_provider
        _system_oneshot_provider = get_provider(
            provider_name,
            api_key=api_key,
            model=model_name,
            system_prompt="",
            tools=[],
        )
        _system_oneshot_provider.init_client()
        if hasattr(_system_oneshot_provider, "disable_session_persistence"):
            _system_oneshot_provider.disable_session_persistence = True
        print(f"[SystemAI oneshot] 초기화 완료 ({provider_name}/{model_name})")
        return _system_oneshot_provider
    except Exception as e:
        print(f"[SystemAI oneshot] 초기화 실패 (의식 에이전트로 폴백): {e}")
        return None


def reset_system_oneshot_provider():
    """본격 원샷 프로바이더 캐시 초기화 (system_ai_config 변경 시 호출)"""
    global _system_oneshot_provider, _system_oneshot_provider_initialized
    _system_oneshot_provider = None
    _system_oneshot_provider_initialized = False
    _clear_resolver_cache()


def system_ai_call(prompt: str, system_prompt: str = None,
                   images: list = None, role: str = "translate") -> Optional[str]:
    """원샷 호출 — 모델은 기어 리졸버가 role 로 해소한다(lightweight_ai_call 과 같은 계약).

    과거엔 무조건 system_ai(본격) 모델이었으나, 이제 role 로 티어가 갈린다:
      - translate(수동 번역) → 실행 축
      - evaluate(달성 기준 평가) → 평가 축(기어 프리셋상 경량 — opus→경량 개선)
    리졸버 프로바이더 우선 → 옛 system_ai 원샷 getter → 의식 에이전트(본격) 순 폴백.
    """
    provider = _resolve_oneshot_provider(role)
    if provider is None:
        provider = _get_system_oneshot_provider()
    if provider is None:
        agent = get_consciousness_agent()
        if not agent.is_ready or not agent._provider:
            return None
        provider = agent._provider

    original_system_prompt = None
    if system_prompt is not None:
        original_system_prompt = provider.system_prompt
        provider.system_prompt = system_prompt
    try:
        return provider.process_message(
            message=prompt, history=[], images=images, execute_tool=None
        )
    except Exception as e:
        logger.warning(f"[system_ai_call] 실패: {e}")
        return None
    finally:
        if original_system_prompt is not None:
            provider.system_prompt = original_system_prompt
