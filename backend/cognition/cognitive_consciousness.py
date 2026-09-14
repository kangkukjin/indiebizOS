"""
cognitive_consciousness.py - 의식·무의식(분류) 믹스인 + 과제 규정 검토
IndieBiz OS Core

agent_cognitive.py 에서 분리(2026-07-17, 1500줄 규칙 모듈화). 3단 인지의
판단 층 — 무의식 분류(_decide_request_type/_classify_request, Reflex·태그 강제
포함), 의식 에이전트 실행/재사용(영속 과제 선택+재검토), 의식 출력의 히스토리
적용·되묻기. SESSION_RESET은 CLI 세션 매핑을 비운다. 영속 과제는 대화 삭제·재설정과 독립이다.
기존 import 경로(agent_cognitive)는 재수출로 유지된다.
"""

import json
import re
from typing import Optional, Dict, Any


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
        """호환 진입점. 영속 기억을 참고하되 THINK/REPAIR는 현재 문제를 새로 규정한다."""
        from pursuit_bind import run_consciousness
        return run_consciousness(self, user_message, history, execution_memory, repair)

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
            _supervisor = _supervisor_current()
            result = agent.process(
                user_message=user_message,
                history=history,
                associative_memory=execution_memory,  # 연상기억(해마+지도 2종) 묶음 — 가이드는 <execution_map> 의 guide: 줄
                world_pulse=get_world_pulse_text(),
                agent_name=agent_name,
                agent_role=agent_role,
                agent_notes=agent_notes,
                available_tools=available_tools,
                repair=repair,
                revision=revision,
                **({"supervisor": _supervisor} if _supervisor else {}),
            )

            if result:
                self._log(f"[의식] 태스크{'(수리 교리 적재)' if repair else ''}: "
                          f"{result.get('task_framing', '')[:60]}")
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
        앞의 두 번은 파일 한 글자도 못 고치고 종료). 2026-09-06 판정 '여러 단계 또는 위험'과 동형 —
        거부권에 걸린 요청은 분류기로 내려가고, 분류기는 여러 단계를 THINK 로 올린다.

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
                return "EXECUTE"  # AI 미준비 시 기본값 — 판정이 아니라 고장이므로 값싼 경로(09-06 개정에서도 유지)

            result = response.strip().upper()
            # SESSION_RESET 우선 검사 (EXECUTE 키워드가 들어있는 경우와 충돌 방지)
            if "SESSION_RESET" in result or "RESET" == result:
                return "SESSION_RESET"
            if "REPAIR" in result:
                return "REPAIR"
            if result == "CONTEXT_UPDATE":
                return "CONTEXT_UPDATE"
            return "EXECUTE" if "EXECUTE" in result else "THINK"

        except Exception as e:
            self._log(f"[무의식] 분류 실패: {e}")
            return "EXECUTE"  # 실패 시 기본값 — 고장은 값싼 경로로. 판정 기준(여러 단계·위험=THINK)은 unconscious_prompt.md
