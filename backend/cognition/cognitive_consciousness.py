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
import re
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

# fit 게이트의 framing 고쳐쓰기(amend) 방어 — 둘 다 **결정론**이다(의미 판단 없음).
_AMEND_MIN_LEN = 20        # 이보다 짧은 amended_framing 은 지도로 취급하지 않는다
_AMEND_CHAIN_MAX = 2       # 연속 고쳐쓰기 상한 — 넘으면 재사용 포기·의식 재각성(티어 역전 차단)


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


def clear_framing_for_agent(agent_id: str) -> list:
    """agent_id 가 같은 모든 registry_key(project:agent) 의 framing 재고 폐기. 반환=지운 키."""
    keys = [k for k in list(_FRAMING_CACHE) if k == agent_id or k.endswith(f":{agent_id}")]
    for k in keys:
        _FRAMING_CACHE.pop(k, None)
    return keys


def _on_system_conversations_cleared():
    """시스템 AI 대화 삭제 → 그 대화에서 뜬 framing 재고도 폐기 (2026-09-02).

    시스템 AI 대화에는 conversation id 가 없다 — '새 대화'의 경계는 SESSION_RESET·TTL·
    **삭제** 셋뿐인데 삭제만 캐시에 닿지 않아, 지운 대화의 지도가 30분 안의 다음 대화에
    재사용됐다(fit 게이트는 옛 지도가 '맞는지'만 보지 '어느 대화 것인지'는 모른다).
    """
    keys = clear_framing_for_agent("system_ai")
    if keys:
        print(f"[framing] 대화 삭제 → 재고 폐기: {', '.join(keys)}")


_HOOK_INSTALLED = False


def install():
    """datastore 층에 대화 삭제 훅 등록 (멱등 — 임포트 시 1회, history_checkpoint.install 선례)."""
    global _HOOK_INSTALLED
    if _HOOK_INSTALLED:
        return
    try:
        import system_ai_memory
        system_ai_memory.register_clear_hook(_on_system_conversations_cleared)
        _HOOK_INSTALLED = True
    except Exception:
        pass


def handle_session_reset() -> str:
    """SESSION_RESET 분류 후 호출.

    현재 thread_context의 agent에 해당하는 CLI 프로바이더 세션 매핑을 제거하여
    다음 호출이 fresh 세션으로 시작되도록 한다.
    CLI 프로바이더(claude_code·codex)가 아닌 경우 no-op (안전).

    Returns:
        사용자에게 보여줄 표준 응답 텍스트
    """
    try:
        from providers import clear_cli_sessions_for_agent
        from thread_context import get_current_registry_key
        key = get_current_registry_key() or "default"
        clear_cli_sessions_for_agent(key)
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

        # ★권한은 캐시로 상속되지 않는다 (2026-08-22, 22회차 사고).
        # `needs_repair` 는 파이프라인에서 **RED 자기수정 그랜트**(고급 모델 고정 +
        # 라이브 코어 쓰기 권한)로 환산된다. 그런데 재사용 경로는 `dict(prev)` 로
        # 통째로 물려주고 게이트는 criteria·amended_framing 만 새로 뽑으므로,
        # *의식이 본 적 없는 턴*이 앞 턴의 수리 권한을 그대로 쓰게 된다 —
        # 헌법 3조건의 '의식 각성'이 실제로는 빠진 채 승격되는 구멍이다
        # (`_consciousness_needs_repair` 주석의 "이 자리가 이미 충족" 은
        #  풀 의식 경로에서만 참이었다).
        # 실측: "상상훈련을 다시 한번 해줘" 에 직전 `#repair` 턴의 framing
        # (task_framing="…유효한 것만 수리해야 한다", criteria="…수정분은
        #  [self:patch]{op:apply} 로 통과시킬 것") 이 fits=true 로 재사용돼,
        # 보고만 해야 할 훈련 턴이 라이브 코어를 고치고 지연 적용까지 갔다
        # (task_sysai_6521f965 → workflow_contract.py 19:45:59 적용).
        # 대조군: 같은 지시라도 의식이 깬 21회차는 보고만 하고 끝났다.
        # → 수리 권한이 걸린 지도는 재사용하지 않는다. 값을 몰래 벗겨 지도만 쓰면
        #   "고쳐라" 라고 적힌 지도를 든 채 권한만 없는 상태가 되어 더 나쁘다.
        if prev and prev.get("needs_repair"):
            self._log("[의식] 재고 framing 이 needs_repair(수리 권한) 선언 — "
                      "재사용 금지, 의식 재각성 (권한은 캐시로 상속되지 않는다)")
            prev = None

        if prev:
            gate = self._consciousness_fit_gate(user_message, prev)
            if gate and gate.get("fits"):
                # 3값 게이트: fits=true 여도 산출물·범위가 커졌으면 지도를 고쳐 쓴다.
                # (이진이던 시절엔 criteria 만 새로 뽑히고 task_framing 은 첫 판 그대로라,
                #  옛 지도로 새 땅을 걷는 상태가 구조적으로 만들어졌다 — 2026-08-20 15:01 턴
                #  실례: '#repair 남겨둔 것 다 처리해' 에 어제의 '판정하라(코드 수정 금지)'
                #  framing 이 그대로 재사용됐다.)
                amended = str(gate.get("amended_framing") or "").strip()
                if amended and len(amended) < _AMEND_MIN_LEN:
                    # 결정론 하한만 본다. "핵심어가 남았나" 같은 의미 검사를 여기 두면
                    # 가드가 막으려는 병(경량 모델의 의미 오판)을 가드 안에 다시 들인다.
                    self._log(f"[의식] amended_framing 무시 (하한 미달 {len(amended)}자)")
                    amended = ""
                chain = int(prev.get("_amend_count") or 0)
                if amended and chain >= _AMEND_CHAIN_MAX:
                    # ★래칫 — 진짜 구조적 위험은 한 번의 나쁜 수정이 아니라 **누적 드리프트**다.
                    # 매 턴 경량 모델이 지도를 조금씩 고쳐 쓰면 N턴 뒤 framing 은 의식(고급
                    # 모델)의 산물이 아니라 경량 모델의 산물인데 겉보기엔 '재사용'이다
                    # (3단 인지의 티어 역전이 조용히 일어난다). 수정 사슬이 상한에 닿으면
                    # 재사용을 포기하고 의식을 깨워 지도를 새로 뜬다 — '고쳐 쓸 권한'과
                    # '지도의 저작권은 의식에 있다'를 양립시키는 자리.
                    self._log(f"[의식] amend 사슬 상한({chain}회) — 의식 재각성으로 지도 재작성")
                else:
                    reused = dict(prev)
                    if amended:
                        reused.setdefault("_framing_origin",
                                          prev.get("task_framing", ""))  # 드리프트 관측용 원본
                        reused["task_framing"] = amended
                        reused["_amend_count"] = chain + 1
                    reused["achievement_criteria"] = (
                        gate.get("criteria") or prev.get("achievement_criteria", "")
                    )
                    reused["history_summary"] = ""  # 실제 최근 history가 그대로 흐르도록
                    if amended:
                        framing_cache_set(key, reused)  # 갱신된 지도를 재고에도 반영
                    self._log(
                        f"[의식] framing {'갱신 재사용(amend %d)' % reused.get('_amend_count', 0) if amended else '재사용'}"
                        f" (Opus 스킵): {reused.get('task_framing', '')[:50]}"
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
            {"fits": bool, "amended_framing": str, "criteria": str}
            또는 None(실패 → 호출 측은 풀 의식 폴백)

        ★3값이다 — fits 는 '이 framing 을 버릴까'만 답하고, 버리지 않기로 했더라도
          범위가 커졌으면 amended_framing 으로 지도를 고쳐 준다. 이진이면 '맞다'와
          '틀렸다' 사이의 가장 흔한 경우(같은 일인데 더 커진 일)를 표현할 수 없다.
          게이트는 실패한 적이 없었다 — 판정 규칙 1이 시킨 대로 했고, 결함은 반환의
          표현력에 있었다. 소비 측 가드(_AMEND_MIN_LEN·_AMEND_CHAIN_MAX)와 한 쌍.
        """
        try:
            from consciousness_agent import oneshot_ai_call

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
3. ★fits=true 라도 **새 메시지가 할 일을 넓혔거나 다음 단계로 옮겨갔으면**(산출물이 늘었다·조건이 붙었다·'판정'에서 '적용'으로 넘어갔다 등) 옛 framing 을 그대로 두지 말고, 그 변화를 반영해 **고쳐 쓴 framing 전문**을 amended_framing 에 담아라. 그대로 충분하면 빈 문자열(""). 시험은 하나다 — 「이 framing 만 들고 새 메시지를 풀 수 있는가?」 아니면 고쳐 써라(지도가 낡은 채 재사용되면 옛 지도로 새 땅을 걷게 된다).
4. 이번 메시지의 구체적 달성 기준을 한 줄로 작성하라 — amended_framing 을 썼으면 그 기준도 새 범위에 맞춰라.

JSON으로만 응답: {{"fits": true/false, "amended_framing": "...", "criteria": "..."}}"""

            resp = oneshot_ai_call(
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
                "amended_framing": str(data.get("amended_framing", "") or ""),
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

    def _consciousness_needs_repair(self, consciousness_output: dict) -> bool:
        """의식이 '이 태스크는 RED 코어 코드를 바꿔야 한다'고 선언했는가.

        무의식 분류기의 REPAIR 감지는 '수리' 의미론(구역어+수리동사·분류 범주)이라
        코어를 건드리는 *개발* 명령("강의 창에 녹음 버튼 만들어줘")을 놓친다 —
        ep1264 에서 그랜트 없이 주행해 apply 가 거부됐다. 전체 맥락을 본 의식의
        이 선언이 마지막 그물: true 면 파이프라인이 THINK 경로에서도 수리 승격
        (고급 모델 + RED 그랜트)을 한다. 한도(시스템 AI + 사용자 출처)는
        REPAIR 분기와 동일하고, 헌법 3조건 중 의식 각성은 이 자리가 이미 충족.
        """
        if not consciousness_output:
            return False
        return bool(consciousness_output.get("needs_repair"))

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
        #repair → REPAIR(시스템 수리 경로), #think → THINK, #execute → EXECUTE (대소문자 무시).
        여럿이면 #repair > #think > #execute (보수적)."""
        low = (message or "").lower()
        if "#repair" in low:
            return "REPAIR"
        if "#think" in low:
            return "THINK"
        if "#execute" in low:
            return "EXECUTE"
        return None

    # 시스템 수리(REPAIR) 결정론 단서 — 구역어와 수리동사가 *함께* 나타날 때만
    # (한쪽만으로는 "백엔드가 뭐야?"·"사진 고쳐줘" 같은 무관 요청을 오폭한다).
    # 분류기(경량 LLM)보다 먼저 돌아 의식 OFF 경로에서도 REPAIR 를 잡는다.
    _REPAIR_ZONE_WORDS = (
        "시스템", "백엔드", "backend", "프론트엔드", "frontend",
        "코어", "런처", "api.py", "인지 파이프라인", "스케줄러 코드",
    )
    _REPAIR_VERB_WORDS = (
        "수리", "수정", "고쳐", "고치", "패치", "버그", "fix",
    )

    def _is_repair_cue(self, message: str) -> bool:
        """비-LLM 결정론 REPAIR 탐지(토큰 0) — 구역어+수리동사 동시 출현."""
        low = (message or "").lower()
        return (any(z in low for z in self._REPAIR_ZONE_WORDS)
                and any(v in low for v in self._REPAIR_VERB_WORDS))

    # 되돌리기 어렵거나 오래 걸리는 op — 회상된 코드 자체에서 읽는다(세계의 명사 아님).
    _LONGRUN_OPS = ('op: "deploy"', "op: 'deploy'", 'op: "build"', "op: 'build'",
                    'op: "publish"', "op: 'publish'")
    # 요구가 몇 개인지 문장 구조로 센다(주제어가 아니라 문형).
    # 부탁 종결: 보조용언 '주다' 계열이 대부분을 덮는다(해줘·찍어줘·띄워줘·보내주세요…).
    _DEMAND_RE = re.compile(r"줘|주세요|줄래|주라|해라|하라|해봐|해다오")
    # 순차 접속: 뒤에 또 하나의 요구가 온다는 표지("완성되면 …띄워줘" 처럼 종결이 하나여도).
    _SEQUENCE_RE = re.compile(
        r"그리고|그다음|그 다음|다음에|이어서|완성되면|끝나면|되면\s|한 뒤|한 후|하고 나서|하고나서")

    def _reflex_veto(self, message: str, top_code: str):
        """반사 금지 사유 — 없으면 None.

        반사의 정의는 "이미 찾은 답을 그대로 내보냄"이다. 아래 셋은 그 정의에 안 맞는데도
        해마 점수만으로 반사가 걸려 의식(달성 기준·진실 소스 정의)을 건너뛰던 자리다
        (ep1173/1176/1177: '홈페이지 업데이트'가 폰트 변경 용례 0.891 로 반사 → 12분 주행,
        앞의 두 번은 파일 한 글자도 못 고치고 종료). 2026-08-10 판정 '장기간 또는 위험'의 집행.

        ★주제어(홈페이지·배포 같은 세계의 명사)로 판정하지 않는다 — 요청과 회상의 *모양*으로
          판정한다. 그래야 새 도메인이 생겨도 목록을 늘릴 필요가 없다.
        """
        code = top_code or ""
        # ① 회상 자체가 다단계 — 한 방에 내보낼 답이 아니다
        if ">>" in code:
            return "회상이 다단계 파이프라인"
        # ② 되돌리기 어려운 작업(빌드·배포·발행) — 위험 축
        if any(op in code for op in self._LONGRUN_OPS):
            return "빌드·배포 등 되돌리기 어려운 작업"
        # ③ 요구는 여럿인데 회상은 단발 — 회상이 요청을 못 덮는다
        msg = message or ""
        demands = len(self._DEMAND_RE.findall(msg))
        if demands >= 2:
            return f"요구 {demands}개인데 회상은 단발"
        # 종결이 하나여도 순차 접속이 있으면 뒤에 또 하나의 요구가 있다
        # ("…업데이트해줘. 완성되면 브라우저에 띄워죠." — ep1173 실제 문장)
        if demands >= 1 and self._SEQUENCE_RE.search(msg):
            return "순차 요구(…한 다음 …)인데 회상은 단발"
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
        # 시스템 수리 단서 — Reflex 보다 먼저: 수리 명령이 해마 고확신 매칭으로
        # 경량 반사에 흘러가면 안 된다(수리=고급 모델+의식 각성 전용, 헌법 2026-08-05).
        # 의식 OFF 경로(분류기 스킵)에서도 이 결정론 검사가 REPAIR 를 잡는다.
        if self._is_repair_cue(message):
            print("[무의식] 분류: REPAIR (결정론 단서 — 구역어+수리동사)")
            return "REPAIR", None
        if (hippocampus_score or 0) >= self.REFLEX_SCORE_THRESHOLD and top_code:
            # 안전핀 — 점수가 높아도 '한 방에 내보낼 답'이 아니면 반사를 포기하고
            # 무의식 분류로 내려보낸다(THINK 로 갈 기회를 준다). REPAIR 핀과 대칭.
            veto = self._reflex_veto(message, top_code)
            if veto:
                print(f"[연상→실행] Reflex 보류 (score={hippocampus_score:.3f} — {veto})")
            else:
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
            from consciousness_agent import oneshot_ai_call, get_unconscious_prompt

            system_prompt = get_unconscious_prompt()
            response = oneshot_ai_call(user_message, system_prompt=system_prompt)

            if response is None:
                return "EXECUTE"  # AI 미준비 시 기본값 — 과잉 각성이 더 흔한 오류(2026-08-10 기준 상향)

            result = response.strip().upper()
            # SESSION_RESET 우선 검사 (EXECUTE 키워드가 들어있는 경우와 충돌 방지)
            if "SESSION_RESET" in result or "RESET" == result:
                return "SESSION_RESET"
            if "REPAIR" in result:
                return "REPAIR"
            return "EXECUTE" if "EXECUTE" in result else "THINK"

        except Exception as e:
            self._log(f"[무의식] 분류 실패: {e}")
            return "EXECUTE"  # 실패 시 기본값 — 실행 에이전트(본격 모델)가 감당, 의식은 장기·위험 전용


install()
