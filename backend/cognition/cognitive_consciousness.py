"""
cognitive_consciousness.py - 의식·무의식(분류) 믹스인 + 과제 규정 검토
IndieBiz OS Core

agent_cognitive.py 에서 분리(2026-07-17, 1500줄 규칙 모듈화). 3단 인지의
판단 층 — 무의식 분류(_decide_request_type/_classify_request, 태그 강제
포함), 의식 에이전트 실행/재사용(영속 과제 선택+재검토), 의식 출력의 히스토리
적용·되묻기. SESSION_RESET은 CLI 세션 매핑을 비운다. 영속 과제는 대화 삭제·재설정과 독립이다.
기존 import 경로(agent_cognitive)는 재수출로 유지된다.
"""

import json
import re
from typing import Optional, Dict, Any
from consciousness_agent import FramingContractError, ConsciousnessCallSkipped


# ============================================================
# SESSION_RESET 핸들러 (모듈 레벨 — call site에서 직접 호출)
# ============================================================

SESSION_RESET_RESPONSE = "새 세션을 시작했습니다. 무엇을 도와드릴까요?"


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
        from conversation_sessions import current
        binding = current()
        if binding:
            key += "@session:" + binding.session_id
        clear_cli_sessions_for_agent(key)
        print(f"[SESSION_RESET] 세션 매핑 클리어: {key}")
    except Exception as e:
        print(f"[SESSION_RESET] 매핑 클리어 실패 (무시): {e}")
    return SESSION_RESET_RESPONSE


class CognitiveConsciousnessMixin:
    """의식(메타 판단)·무의식(분류) 메서드 모음."""

    def _run_consciousness_or_reuse(self, user_message: str, history: list,
                                    execution_memory: str = "",
                                    repair: bool = False) -> Optional[dict]:
        """새 요청은 규정하고, 승인된 자기수리의 재개는 기존 규정을 계승한다."""
        from repair_continuation import inherited_framing
        inherited = inherited_framing(user_message) if repair else None
        if inherited:
            from repair_resume import bind_pursuit
            bind_pursuit()
            return inherited
        # 명시적인 수리는 실행자가 직접 조사·검사한다. #think는 기존 의식을 유지한다.
        from thread_context import get_task_origin
        if (repair and get_task_origin() == "user" and re.search(r"(?i)#repair\b", user_message)
                and not re.search(r"(?i)#think\b", user_message)):
            from repair_policy import direct_framing
            return direct_framing(user_message)
        # 규정 계승(2026-10-07): 같은 문장의 정기 실행(직전 ACHIEVED) 또는 같은 과제의 후속 턴은
        # 직전 규정을 경량 패치로 잇는다 — 의식 각성(≈1분·10만 토큰)을 건너뛴다. 수리 턴은 제외
        # (수리는 repair_continuation 이 따로 계승한다). 포기하면 아래에서 전과 같이 깨운다.
        if not repair:
            from framing_inheritance import inherit
            inherited_turn = inherit(self, user_message, history)
            if inherited_turn:
                return inherited_turn
        from pursuit_bind import run_consciousness
        result = run_consciousness(self, user_message, history, execution_memory, repair)
        if repair and isinstance(result, dict) and get_task_origin() == "user":
            result["_repair_policy"] = 2
        return result

    def _run_consciousness(self, user_message: str, history: list,
                           execution_memory: str = "", repair: bool = False,
                           revision: dict = None) -> dict:
        """의식 에이전트 실행 — 메타 판단

        사용자 메시지와 히스토리를 분석하여 프롬프트 최적화 지침을 반환합니다.
        실패 시 None을 반환하고, 기존 방식으로 폴백합니다.

        Returns:
            의식 에이전트 출력 dict 또는 None
        """
        try:
            from consciousness_agent import (
                get_consciousness_agent,
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

            # 가용 도구 목록 — 의식이 hint 에서 이름을 부를 수 있는 도구의 범위.
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

            from supervision_bus import current as _supervisor_current
            from pursuit_bind import current as pursuit_current, validate_output
            _supervisor = _supervisor_current()
            binding = pursuit_current()
            row = binding.row if binding else None
            result = agent.process(
                user_message=user_message,
                history=history,
                associative_memory=execution_memory,  # 연상기억(해마+심층 지도+가이드 목차) 묶음 — 가이드는 <guide_map>
                world_pulse=get_world_pulse_text(),
                agent_name=agent_name,
                agent_role=agent_role,
                agent_notes=agent_notes,
                available_tools=available_tools,
                repair=repair,
                revision=revision,
                validate_framing=validate_output,
                pursuit_state={"bound": bool(row), "id": row["id"] if row else None},
                **({"supervisor": _supervisor} if _supervisor else {}),
            )

            if result:
                self._log(f"[의식] 태스크{'(수리 교리 적재)' if repair else ''}: "
                          f"{result.get('task_framing', '')[:60]}")
            return result

        except (FramingContractError, ConsciousnessCallSkipped):
            raise
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

        문자열 history_summary는 교체 결정이다. 빈 문자열은 관련 과거 없음이다.
        의식 미실행·필드 누락·잘못된 타입만 판단 부재로 보아 원본을 유지한다.
        비어 있지 않은 교체본의 내부 표식은 CLI가 옛 세션을 재개하지 않게 한다.
        """
        if not consciousness_output:
            return history

        history_summary = consciousness_output.get("history_summary")
        if not isinstance(history_summary, str):
            return history

        history_summary = history_summary.strip()
        if not history_summary:
            return []

        # 원본 히스토리를 의식 에이전트의 요약으로 대체
        return [{"role": "user", "content": f"[이전 대화 요약: {history_summary}]",
                 "_history_replacement": True}]

    # 의식 토글 OFF 일 때 분류기(경량 LLM) 대신 쓰는 세션 리셋 키워드 — 고정밀로 추림
    # (unconscious_prompt.md 의 SESSION_RESET 트리거에서). 리셋은 파괴적이므로 보수적:
    # 애매한 단어(맨 "리셋"/"초기화" 단독 — 액션 명령과 충돌)는 일부러 제외, 애매하면 EXECUTE.
    _RESET_PHRASES = (
        "새세션", "세션시작", "세션끝", "세션초기화", "세션리셋", "세션그만",
        "깨끗하게시작", "여기까지하자",
        "그만하자", "다른이야기하자", "새작업으로넘어가",
    )
    # 공백을 뺀 글자 수 상한 — 리셋 인사는 한두 문장이다. 그보다 길면 작업 지시로 본다(애매하면 EXECUTE).
    _RESET_MAX_CHARS = 60
    # "처음부터 다시"는 낱말만으로는 못 가른다 — "처음부터 다시 써줘·해줘·만들어줘"는 작업 지시다.
    # 문장 전체가 대상 없이 그 말(＋하자·시작하자)일 때만 리셋이고, 나머지는 EXECUTE 로 흘린다(2026-10-01).
    _RESET_WHOLE = re.compile(r"^(자|그럼|이제|우리)*처음부터다시(하자|시작하자|시작)?$")

    def _is_reset_keyword(self, message: str) -> bool:
        """의식 OFF 에서 분류기를 스킵하므로, 세션 리셋만 비-LLM 키워드로 대체 탐지(토큰 0)."""
        low = (message or "").lower().replace(" ", "")
        # 리셋은 대화에 대한 말이지 작업 지시의 조각이 아니다. 위임·예약 과제(`[task:…]`)와 긴 지시문 안의
        # 같은 글자열은 리셋이 아니다 — 2026-10-01 실측: 예약 위임 문구의 "처음부터 다시 훑지 말고"가
        # 받는 에이전트의 세션을 지우고 표준 응답만 돌려줬다(일은 하지 않음).
        if low.startswith("[task:") or len(low) > self._RESET_MAX_CHARS:
            return False
        if self._RESET_WHOLE.match(re.sub(r"[,.!?~…]", "", low)):
            return True
        return any(p in low for p in self._RESET_PHRASES)

    def _tag_override(self, message: str) -> Optional[str]:
        """명령에 박힌 명시 태그로 판정을 강제한다 — 사용자 결정이므로 분류를 이긴다.
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
        """직접 수리 단서만 강제한다. 인용·금지·가정은 일반 의도 판정에 남긴다."""
        low = (message or "").lower()
        # 인용된 요청/코드가 현재 사용자의 수리 요청이 되는 것을 막는다.
        low = re.sub(r'```[\s\S]*?```', ' ', low)
        def quoted(match):
            text = match.group()[1:-1]
            # 따옴표 친 파일/구역 이름은 직접 요청의 목적어일 수 있다.
            return (' ' if any(z in text for z in self._REPAIR_ZONE_WORDS)
                    and any(v in text for v in self._REPAIR_VERB_WORDS) else text)
        low = re.sub(r'`[^`]*`|"[^"\n]*"|“[^”]*”|‘[^’]*’|(?<!\w)\'[^\'\n]*\'(?!\w)', quoted, low)
        low = re.sub(r'(?m)^\s*>.*$', ' ', low)
        clauses = re.split(r'[;\n,]|[.!?。](?=\s|$)|(?<=말고)|(?<=않고)|(?<=지만)|\bbut\b', low)
        for clause in clauses:
            if not (any(z in clause for z in self._REPAIR_ZONE_WORDS)
                    and any(v in clause for v in self._REPAIR_VERB_WORDS)):
                continue
            if re.search(r'(?:하지|고치지)\s*(?:마|말|않)|안\s*(?:수리|수정|고치|고쳐|패치)|'
                         r'(?:수리|수정|패치)(?:은|는|을|를)?\s*안\s*|'
                         r'(?:수리|수정|패치)\s*(?:금지|불필요)|'
                         r'(?:요청|원하|필요로\s*하)지\s*않|필요(?:가|는)?\s*없|'
                         r'\b(?:do\s+not|don[’\x27]t|never|without|no\s+(?:fix|repair))\b', clause):
                continue
            if re.search(r'(?:수리|수정|패치)(?:한다면|하면|했다고\s*가정|할\s*경우)|고치면|'
                         r'\b(?:suppose|hypothetically|what\s+if)\b', clause):
                continue
            return True
        return False

    def _decide_request_type(self, message: str, hippocampus_score: float,
                             top_code: str, history=None, images=None) -> tuple:
        """요청 판정 단일 진입점 — 명시 태그(무조건) → 무의식 분류.

        4개 호출처(시스템AI×2·프로젝트 에이전트·채널)가 같은 결정을 쓰도록 중앙화.
        print 로 남기는 판정 로그는 episode_logger 가 정규식으로 읽어 episode_summary 에
        unconscious_decision 으로 적재하므로 형식([무의식] 분류: / [연상→실행])을 보존한다.

        해마 점수·코드 인자와 반환 튜플의 둘째 자리(None)는 호출부 호환을 위해 유지한다.
        기억 검색·주입은 별도 흐름이며 이 판정은 회상 점수에 의존하지 않는다.
        """
        tag = self._tag_override(message)
        if tag:
            # 태그 강제 — episode 추출이 잡도록 "[무의식] 분류: X" 형식 유지(+강제 표기)
            print(f"[무의식] 분류: {tag} (태그 #{tag.lower()} 강제 — 분류 무시)")
            return tag, None
        # 시스템 수리 단서: 수리 요청은 고급 모델·의식 경로로 보낸다.
        # 의식 OFF 경로(분류기 스킵)에서도 이 결정론 검사가 REPAIR 를 잡는다.
        if self._is_repair_cue(message):
            print("[무의식] 분류: REPAIR (결정론 단서 — 직접 수리 요청)")
            return "REPAIR", None
        # 위임받은 에이전트의 완료 통지(`[task:…] 완료.`)는 사실 통보다 — 분류기가 THINK 로 올려
        # 의식 29초+상태 조회 5라운드를 돌던 자리(ep4388, 2026-10-07). 통보 범위(turn_scope)로 처리.
        from framing_inheritance import is_delegation_report
        if is_delegation_report(message):
            print("[무의식] 분류: CONTEXT_UPDATE (결정론 단서 — 위임 완료 통지)")
            return "CONTEXT_UPDATE", None
        # 의식 토글 OFF는 분류를 생략한다. 해마 유사도는 실행 경로를 바꾸지 않는다.
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
        from turn_scope import classification_message
        request_type = self._classify_request(classification_message(message, history, images))
        if request_type == "CONTEXT_UPDATE" and images:
            # 첨부 내용을 보지 못한 글자 분류로 판독까지 금지할 수 없다.
            request_type = "EXECUTE"
            print("[무의식] 사실 통보 제한 제외: 현재 이미지 첨부의 판독 필요")
        print(f"[무의식] 분류: {request_type}")
        return request_type, None

    def _classify_request(self, user_message: str,
                          execution_memory: str = "") -> str:
        """사용자 요청을 SESSION_RESET / EXECUTE / THINK로 분류한다.

        무의식 에이전트 — 경량 AI 호출로 분류한다. 해마 고확신도 이 분류를 우회하지 않는다.

        execution_memory는 받지만 분류 입력에 합치지 않는다.
        호출자가 전달한 현재 메시지·짧은 직전 대화·첨부 유무만 판단한다.
        연상기억을 합치면 짧은 명령도 입력이 부풀어 모델이 단순 EXECUTE 판단을 못함.
        (인터페이스 호환을 위해 파라미터는 유지)

        Returns:
            "SESSION_RESET" / "EXECUTE" / "THINK"
        """
        try:
            from consciousness_agent import oneshot_ai_call, get_unconscious_prompt

            system_prompt = get_unconscious_prompt()
            response = oneshot_ai_call(user_message, system_prompt=system_prompt)

            if not isinstance(response, str) or not response.strip():
                self._log("[무의식] 분류 실패: 응답 없음 — EXECUTE 기본 경로")
                return "EXECUTE"  # 고장은 값싼 경로로(09-06 정책 유지).

            result = response.strip().upper()
            if result == "RESET":  # 기존 단일 토큰 별칭
                return "SESSION_RESET"
            if result in {"SESSION_RESET", "CONTEXT_UPDATE", "REFLEX", "EXECUTE", "THINK", "REPAIR"}:
                return result
            # 오류 문구·부분 토큰·설명문은 분류가 아니다. 포함 문자열로 경로를 추측하지 않는다.
            self._log("[무의식] 분류 실패: 허용된 단일 분류값이 아님 — EXECUTE 기본 경로")
            return "EXECUTE"

        except Exception as e:
            self._log(f"[무의식] 분류 실패: {e}")
            return "EXECUTE"  # 실패 시 기본값 — 고장은 값싼 경로로. 판정 기준(여러 단계·위험=THINK)은 unconscious_prompt.md
