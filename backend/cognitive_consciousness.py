"""
cognitive_consciousness.py - 의식·무의식(분류) 믹스인 + framing 캐시
IndieBiz OS Core

agent_cognitive.py 에서 분리(2026-07-17, 1500줄 규칙 모듈화). 3단 인지의
판단 층 — 무의식 분류(_decide_request_type/_classify_request, Reflex·태그 강제
포함), 의식 에이전트 실행/재사용(framing 캐시+fit 게이트), 의식 출력의 히스토리
적용·되묻기. SESSION_RESET 처리도 여기(세션 매핑+framing 캐시를 함께 비운다).
기존 import 경로(agent_cognitive)는 재수출로 유지된다.
"""

import json
from typing import Optional, Dict, Any


# ============================================================
# SESSION_RESET 핸들러 (모듈 레벨 — call site에서 직접 호출)
# ============================================================

SESSION_RESET_RESPONSE = "새 세션을 시작했습니다. 무엇을 도와드릴까요?"


# ============================================================
# 의식 framing 캐시 (연속 turn 재사용)
# ------------------------------------------------------------
# THINK 판정 = "framing이 필요하다"는 수요 선언이다. 같은 대화 맥락에서 이미
# 의식 에이전트가 만든 framing이 지금 질문에 맞으면, 그걸 재사용해 비싼 의식
# (Opus) 호출을 건너뛴다. 없거나 안 맞으면 의식 에이전트가 새로 만든다.
#   키: registry_key (project_id:agent_id)
#   값: {"output": dict, "ts": epoch_seconds}
# ============================================================

_FRAMING_CACHE: Dict[str, Dict[str, Any]] = {}
_FRAMING_TTL_SEC = 1800  # 30분 — 오래된 동선이 새 대화로 새지 않도록 만료


def framing_cache_get(key: str) -> Optional[dict]:
    """저장된 framing 조회 (TTL 경과 시 폐기하고 None)."""
    import time as _t
    entry = _FRAMING_CACHE.get(key)
    if not entry:
        return None
    if _t.time() - entry.get("ts", 0) > _FRAMING_TTL_SEC:
        _FRAMING_CACHE.pop(key, None)
        return None
    return entry.get("output")


def framing_cache_set(key: str, output: dict):
    """framing 저장 (빈 값·미완성 framing은 호출 측에서 걸러 보낼 것)."""
    import time as _t
    if key and output:
        _FRAMING_CACHE[key] = {"output": output, "ts": _t.time()}


def clear_framing_cache(key: str = None):
    """framing 캐시 무효화. key 없으면 전체."""
    if key:
        _FRAMING_CACHE.pop(key, None)
    else:
        _FRAMING_CACHE.clear()


def handle_session_reset() -> str:
    """SESSION_RESET 분류 후 호출.

    현재 thread_context의 agent에 해당하는 Claude Code 세션 매핑을 제거하여
    다음 호출이 fresh Claude Code 세션으로 시작되도록 한다.
    Claude Code provider가 아닌 경우 no-op (안전).

    Returns:
        사용자에게 보여줄 표준 응답 텍스트
    """
    try:
        from providers.claude_code import clear_session_for_agent
        from thread_context import get_current_registry_key
        key = get_current_registry_key() or "default"
        clear_session_for_agent(key)
        clear_framing_cache(key)  # 저장된 의식 framing도 함께 폐기
        print(f"[SESSION_RESET] 세션 매핑 클리어: {key}")
    except Exception as e:
        print(f"[SESSION_RESET] 매핑 클리어 실패 (무시): {e}")
    return SESSION_RESET_RESPONSE


class CognitiveConsciousnessMixin:
    """의식(메타 판단)·무의식(분류) 메서드 모음."""

    def _run_consciousness_or_reuse(self, user_message: str, history: list,
                                    execution_memory: str = "") -> Optional[dict]:
        """THINK 경로의 의식 진입점 — framing 재고가 있으면 재사용, 없으면 생성.

        THINK 판정은 "framing이 필요하다"는 수요다. 같은 대화에서 이미 만든
        framing이 지금 질문에 맞으면(fit 게이트, 경량 1회) 재사용하고 의식(Opus)
        호출을 건너뛴다. 없거나 안 맞으면 의식 에이전트가 새로 만들어 저장한다.
        per-turn으로 바뀌는 achievement_criteria만 게이트가 새로 뽑는다.
        """
        from thread_context import get_current_registry_key
        key = get_current_registry_key() or "default"

        # 후속 turn(히스토리 존재) + 저장된 framing 있을 때만 재사용 시도
        prev = framing_cache_get(key) if history else None
        if prev:
            gate = self._consciousness_fit_gate(user_message, prev)
            if gate and gate.get("fits"):
                reused = dict(prev)
                reused["achievement_criteria"] = (
                    gate.get("criteria") or prev.get("achievement_criteria", "")
                )
                reused["history_summary"] = ""  # 실제 최근 history가 그대로 흐르도록
                self._log(
                    f"[의식] framing 재사용 (Opus 스킵): {reused.get('task_framing', '')[:50]}"
                )
                return reused

        # 없거나 안 맞음 → 의식 에이전트가 새로 만든다
        out = self._run_consciousness(user_message, history, execution_memory)
        # 미완성 framing(clarification 요청)은 재고로 쌓지 않는다
        if out and not out.get("needs_clarification"):
            framing_cache_set(key, out)
        return out

    def _consciousness_fit_gate(self, user_message: str, prev_framing: dict) -> Optional[dict]:
        """저장된 framing이 현재 질문에 맞는지 경량 모델로 판정 + 이번 turn 달성 기준 생성.

        Returns:
            {"fits": bool, "criteria": str} 또는 None(실패 → 호출 측은 풀 의식 폴백)
        """
        try:
            from consciousness_agent import lightweight_ai_call

            task_framing = (prev_framing or {}).get("task_framing", "")
            if not task_framing:
                return None

            prompt = f"""아래는 직전까지 진행 중인 태스크의 정의(framing)다.

[진행 중 태스크]
{task_framing}

[사용자의 새 메시지]
{user_message}

판정하라:
1. 이 framing이 새 메시지를 푸는 데 그대로 맞는가? 같은 태스크의 연장·변주(조건/방향/대상만 바뀐 경우)면 맞고(fits=true), 주제가 바뀌었으면 안 맞다(fits=false).
2. ★같은 주제라도, 사용자가 직전 결론·전제를 **반박**하거나("아니야", "다시 찾아봐", "있어/없어" 단언, "틀렸어") 자신의 직접 경험으로 새 사실을 단언하면 fits=false다 — 기존 framing의 전제가 무너졌으므로 새 정보를 반영해 처음부터 다시 프레이밍해야 한다. 재사용은 이전 접근이 여전히 유효할 때만 정당하다.
3. 맞다면 이번 메시지의 구체적 달성 기준을 한 줄로 작성하라.

JSON으로만 응답: {{"fits": true/false, "criteria": "..."}}"""

            resp = lightweight_ai_call(
                prompt,
                system_prompt="진행 중 태스크 framing의 적합성 판정기. JSON으로만 응답.",
                role="background",
            )
            if not resp:
                return None

            cleaned = resp.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()

            data = json.loads(cleaned)
            if not isinstance(data, dict) or "fits" not in data:
                return None
            return {
                "fits": bool(data.get("fits")),
                "criteria": str(data.get("criteria", "") or ""),
            }
        except Exception as e:
            self._log(f"[의식] fit 게이트 실패 (풀 의식 폴백): {e}")
            return None

    def _run_consciousness(self, user_message: str, history: list,
                           execution_memory: str = "") -> dict:
        """의식 에이전트 실행 — 메타 판단

        사용자 메시지와 히스토리를 분석하여 프롬프트 최적화 지침을 반환합니다.
        실패 시 None을 반환하고, 기존 방식으로 폴백합니다.

        Returns:
            의식 에이전트 출력 dict 또는 None
        """
        try:
            from consciousness_agent import (
                get_consciousness_agent,
                get_guide_list,
                get_world_pulse_text,
            )

            agent = get_consciousness_agent()
            if not agent.is_ready:
                return None

            agent_name = self.config.get("name", "")

            # 역할 전문 로드 (잘리지 않고 전체 전달 — self_awareness 판단용)
            agent_role = self._load_role()

            # 영구메모 로드 — 시스템 AI는 사용자 프로필 사용
            if self.config.get("_is_system_ai"):
                from system_ai_memory import load_user_profile
                agent_notes = load_user_profile()
            else:
                agent_notes = self.config.get("notes", "")

            # 가용 도구 목록 — 의식이 capability_focus.tools에 추천할 수 있는 범위.
            # 시스템 AI는 system_ai_tools, 프로젝트 에이전트는 _get_available_tools().
            try:
                if self.config.get("_is_system_ai"):
                    from system_ai_tools import get_all_system_ai_tools
                    available_tools = [t.get("name", "") for t in get_all_system_ai_tools()
                                       if isinstance(t, dict) and t.get("name")]
                else:
                    available_tools = self._get_available_tools()
            except Exception as e:
                self._log(f"[의식] 가용 도구 목록 조회 실패 (검증 스킵): {e}")
                available_tools = None

            result = agent.process(
                user_message=user_message,
                history=history,
                associative_memory=execution_memory,  # 연상기억(해마+심층메모리) 묶음
                guide_list=get_guide_list(user_message),
                world_pulse=get_world_pulse_text(),
                agent_name=agent_name,
                agent_role=agent_role,
                agent_notes=agent_notes,
                available_tools=available_tools,
            )

            if result:
                self._log(f"[의식] 태스크: {result.get('task_framing', '')[:60]}")
            return result

        except Exception as e:
            self._log(f"[의식] 실행 실패 (폴백): {e}")
            return None

    def _consciousness_clarification(self, consciousness_output: dict) -> Optional[str]:
        """의식이 needs_clarification=true로 판단했다면 사용자에게 보낼 질문을 반환.

        반환값이 None이 아니면 호출자는 실행 에이전트 호출을 건너뛰고 이 문자열을
        그대로 응답으로 노출해야 한다 (평가 루프도 안 탄다).

        Returns:
            clarification_question 문자열 또는 None
        """
        if not consciousness_output:
            return None
        if not consciousness_output.get("needs_clarification"):
            return None
        question = consciousness_output.get("clarification_question", "")
        if isinstance(question, str) and question.strip():
            return question.strip()
        # needs_clarification=true인데 질문이 비어있으면 task_framing 폴백
        task_framing = consciousness_output.get("task_framing", "")
        if isinstance(task_framing, str) and task_framing.strip():
            return task_framing.strip()
        return None

    def _apply_consciousness_to_history(self, history: list, consciousness_output: dict) -> list:
        """의식 에이전트의 판단에 따라 히스토리를 편집합니다.

        history_summary가 있으면 원본 히스토리를 요약으로 대체합니다.
        요약이 비어있으면 원본 히스토리를 그대로 반환합니다.
        """
        if not consciousness_output:
            return history

        history_summary = consciousness_output.get("history_summary", "")
        if not history_summary:
            return history

        # 원본 히스토리를 의식 에이전트의 요약으로 대체
        return [{"role": "user", "content": f"[이전 대화 요약: {history_summary}]"}]

    # ============================================================
    # Reflex 임계값 — 단계 0 결과의 top_score가 이 값 이상이면
    # 무의식(경량 AI) 호출을 건너뛰고 즉시 EXECUTE.
    # 분기는 호출 측(_process_channel_message)이 책임진다.
    # 0.88 → 0.85: 한계 사례(0.85~0.88)도 학습된 패턴이면 EXECUTE로 흘림.
    # ============================================================
    REFLEX_SCORE_THRESHOLD = 0.85

    # 의식 토글 OFF 일 때 분류기(경량 LLM) 대신 쓰는 세션 리셋 키워드 — 고정밀로 추림
    # (unconscious_prompt.md 의 SESSION_RESET 트리거에서). 리셋은 파괴적이므로 보수적:
    # 애매한 단어(맨 "리셋"/"초기화" 단독 — 액션 명령과 충돌)는 일부러 제외, 애매하면 EXECUTE.
    _RESET_PHRASES = (
        "새세션", "세션시작", "세션끝", "세션초기화", "세션리셋", "세션그만",
        "처음부터다시", "깨끗하게시작", "여기까지하자",
        "그만하자", "다른이야기하자", "새작업으로넘어가",
    )

    def _is_reset_keyword(self, message: str) -> bool:
        """의식 OFF 에서 분류기를 스킵하므로, 세션 리셋만 비-LLM 키워드로 대체 탐지(토큰 0)."""
        low = (message or "").lower().replace(" ", "")
        return any(p in low for p in self._RESET_PHRASES)

    def _tag_override(self, message: str) -> Optional[str]:
        """명령에 박힌 명시 태그로 판정을 강제한다 — 사용자 결정이므로 Reflex·분류를 모두 이긴다.
        #think → THINK, #execute → EXECUTE (대소문자 무시). 둘 다면 #think 우선(보수적)."""
        low = (message or "").lower()
        if "#think" in low:
            return "THINK"
        if "#execute" in low:
            return "EXECUTE"
        return None

    def _decide_request_type(self, message: str, hippocampus_score: float,
                             top_code: str) -> tuple:
        """요청 판정 단일 진입점 — 명시 태그(무조건) → Reflex(해마 고확신) → 무의식 분류.

        4개 호출처(시스템AI×2·프로젝트 에이전트·채널)가 같은 결정을 쓰도록 중앙화.
        print 로 남기는 판정 로그는 episode_logger 가 정규식으로 읽어 episode_summary 에
        unconscious_decision 으로 적재하므로 형식([무의식] 분류: / [연상→실행])을 보존한다.

        Returns: (request_type, reflex_hint)  # reflex_hint 는 Reflex EXECUTE 일 때만 top_code
        """
        tag = self._tag_override(message)
        if tag:
            # 태그 강제 — episode 추출이 잡도록 "[무의식] 분류: X" 형식 유지(+강제 표기)
            print(f"[무의식] 분류: {tag} (태그 #{tag.lower()} 강제 — Reflex·분류 무시)")
            return tag, None
        if (hippocampus_score or 0) >= self.REFLEX_SCORE_THRESHOLD and top_code:
            print(f"[연상→실행] Reflex EXECUTE (score={hippocampus_score:.3f})")
            return "EXECUTE", top_code
        # 의식 토글 OFF → 무의식 분류(THINK 판정)를 건너뛰고 바로 EXECUTE. 반사는 위에서 이미 처리됨.
        # SESSION_RESET 만 비-LLM 키워드로 살림(분류기가 잡던 걸 OFF 에서 대체). 확정 2026-06-30.
        try:
            from model_resolver import consciousness_enabled
            _conscious = consciousness_enabled()
        except Exception:
            _conscious = True
        if not _conscious:
            if self._is_reset_keyword(message):
                print("[무의식] 분류: SESSION_RESET (키워드 · 의식 OFF)")
                return "SESSION_RESET", None
            print("[무의식] 분류: EXECUTE (의식 OFF — THINK 경로 차단)")
            return "EXECUTE", None
        request_type = self._classify_request(message)
        print(f"[무의식] 분류: {request_type}")
        return request_type, None

    def _classify_request(self, user_message: str,
                          execution_memory: str = "") -> str:
        """사용자 요청을 SESSION_RESET / EXECUTE / THINK로 분류한다.

        무의식 에이전트 — 경량 AI 호출만 담당. Reflex 판정은
        호출 측에서 단계 0(_build_execution_memory)의 top_score로 미리 분기한다.

        execution_memory는 받지만 분류 입력에 합치지 않는다.
        unconscious_prompt.md 규칙: "현재 메시지만으로 판단한다."
        연상기억을 합치면 짧은 명령도 입력이 부풀어 모델이 단순 EXECUTE 판단을 못함.
        (인터페이스 호환을 위해 파라미터는 유지)

        Returns:
            "SESSION_RESET" / "EXECUTE" / "THINK"
        """
        try:
            from consciousness_agent import lightweight_ai_call, get_unconscious_prompt

            system_prompt = get_unconscious_prompt()
            response = lightweight_ai_call(user_message, system_prompt=system_prompt)

            if response is None:
                return "THINK"  # AI 미준비 시 안전하게 판단형으로

            result = response.strip().upper()
            # SESSION_RESET 우선 검사 (EXECUTE 키워드가 들어있는 경우와 충돌 방지)
            if "SESSION_RESET" in result or "RESET" == result:
                return "SESSION_RESET"
            return "EXECUTE" if "EXECUTE" in result else "THINK"

        except Exception as e:
            self._log(f"[무의식] 분류 실패: {e}")
            return "THINK"  # 실패 시 안전하게 판단형으로
