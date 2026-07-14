"""
agent_pipeline.py - 인지 파이프라인 공유 드라이버 (Task B 통합)
IndieBiz OS Core

파이프라인(연상→분류→의식→실행→평가→반성) 오케스트레이션이 진입점(WS 프로젝트/시스템AI
스트림, 블로킹, 이메일/통신)마다 복사-붙여넣기 되어 있던 것을 **하나의 제너레이터**로
통합한다. 진입점은 이벤트를 pump(스트림)하거나 drain(블로킹)하는 얇은 transport 어댑터가
된다 — 기능 하나(예: 반성)를 더할 때 한 곳만 고치면 전 경로가 상속한다.
([[architecture_entrypoint_drift_shared_boot]], docs/COGNITIVE_PIPELINE_UNIFY_HANDOFF.md)

이벤트 어휘 = ai_agent.process_message_stream 과 동일(text/tool_start/tool_result/
thinking/final/error) + 추가 2종:
  - cognition   : 작업전 공개(계기판 신뢰 보정) — 클라이언트 전달용
  - _turn_meta  : 턴 종료 메타(도구이력 등) — 내부용, 클라이언트 미전달

transport에 남는 것: 에피소드 start/end, thread_context 설정, event pump/drain,
DB save_message, 태스크·세션·클라이언트 관리, 취소/타임아웃 처리.
"""

from typing import Generator, Dict, Any, List, Optional


def _extract_map_tag_texts(text: str) -> List[str]:
    """응답 텍스트에 실린 [MAP:{...}] 지도 태그를 원문 그대로 추출 (대괄호 짝 맞춤 —
    프론트 parseMapData 와 동일 규칙). 반성 턴이 응답을 교체할 때 이월용."""
    tags, i = [], 0
    while True:
        i = text.find("[MAP:", i)
        if i < 0:
            break
        depth, j = 0, i + 5
        while j < len(text):
            ch = text[j]
            if ch == "[":
                depth += 1
            elif ch == "]":
                if depth == 0:
                    break
                depth -= 1
            j += 1
        if j < len(text):
            tags.append(text[i:j + 1])
            i = j + 1
        else:
            break
    return tags


def drain_stream(gen) -> Dict[str, Any]:
    """블로킹 진입점용 어댑터 — 제너레이터를 소비해 최종 응답만 취한다.

    반성·평가도 제너레이터 안에서 일어나므로, 블로킹 경로(이메일·논스트림)가
    스트림 경로의 기능을 자동 상속한다(Task B의 payoff).

    Returns:
        {"final": str, "error": str|None, "tool_calls": list, "clarify": bool,
         "session_reset": bool}
    """
    final = ""
    error = None
    tool_calls: List[Dict] = []
    clarify = False
    session_reset = False
    for ev in gen:
        et = ev.get("type")
        if et == "final":
            final = ev.get("content", "")
        elif et == "error":
            error = ev.get("content", "")
        elif et == "_turn_meta":
            tool_calls.extend(ev.get("tool_calls") or [])
            clarify = bool(ev.get("clarify"))
            session_reset = bool(ev.get("session_reset"))
    return {"final": final, "error": error, "tool_calls": tool_calls,
            "clarify": clarify, "session_reset": session_reset}


class CognitivePipelineMixin:
    """AgentRunner용 인지 파이프라인 드라이버 — 프로젝트/시스템AI 공용.

    차이는 self.config['_is_system_ai'] 플래그와 파라미터로 흡수한다(별도 집 없음).
    """

    def _collect_thread_tool_calls(self, tool_calls_log: list):
        """thread_context에 쌓인 node/action/ms 도구 이력을 수집(X-Ray용)하고 비운다."""
        try:
            from thread_context import get_tool_calls, clear_tool_calls
            _tc = get_tool_calls()
            if _tc:
                tool_calls_log.extend(_tc)
            clear_tool_calls()
        except Exception:
            pass

    def cognitive_stream(
        self,
        message: str,
        history: Optional[list] = None,
        *,
        images: Optional[list] = None,
        action_hint: Optional[str] = None,
        extra_role: str = "",
        force_role: str = "",
        allowed_set=None,
        cancel_check=None,
        agent_name: Optional[str] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """인지 파이프라인 전체를 한 번만 수행하는 제너레이터.

        연상 → 분류(SESSION_RESET 포함) → 의식(THINK)/모델스왑(reflex·force_role) →
        clarification fast-path → 프롬프트 갱신 → 실행 → 평가(THINK) → 반성(EXECUTE) →
        메모리 쓰기(_after_response). 진입점은 이 이벤트를 pump/drain만 한다.

        Args:
            extra_role/force_role/allowed_set: 시스템 AI 표면 전용(앱메이커·포식 등).
            agent_name: 프로젝트 에이전트 역할파일(agent_{name}_role.txt) 해소용.
        """
        is_system_ai = bool(self.config.get("_is_system_ai"))
        history = history or []
        agent_name = agent_name or self.config.get("name", "")

        # 1. 연상 — 해마+심층+포식+디스크골격 (검색 1회로 점수/코드까지 확보)
        # ★포식(force_role="forage")은 심층 관련기억 주입을 끈다 — 필터버블 드리프트 방지.
        execution_memory, hippo_score, top_code = self._build_execution_memory(
            message, action_hint=action_hint, include_related=(force_role != "forage")
        )

        # 2. 분류 — 명시 태그(#think/#execute) → Reflex(해마 고확신) → 무의식 분류
        if force_role:
            # 표면 강제 EXECUTE(포식 등): 무의식 분류기(경량 LLM 1회)를 건너뛴다.
            request_type, reflex_hint = "EXECUTE", None
            print(f"[무의식] 분류: EXECUTE (force_role={force_role} — 분류기 건너뜀)")
        else:
            request_type, reflex_hint = self._decide_request_type(message, hippo_score, top_code)

        # SESSION_RESET — Claude Code 세션 매핑만 제거하고 표준 응답 (AI 호출 없음)
        if request_type == "SESSION_RESET":
            from agent_cognitive import handle_session_reset
            reset_text = handle_session_reset()
            print(f"[SESSION_RESET] {agent_name}: 표준 응답 반환, AI 호출 스킵")
            yield {"type": "text", "content": reset_text}
            yield {"type": "final", "content": reset_text}
            yield {"type": "_turn_meta", "tool_calls": [], "session_reset": True}
            return

        # 3. 의식(THINK) / reflex·force_role 모델 스왑
        # 스왑 헬퍼는 runner-제네릭(시스템AI 전용 아님) — system_ai_core에 기거할 뿐.
        from system_ai_core import _switch_to_midtier, _switch_to_role, _restore_provider
        consciousness_output = None
        original_provider = None
        if force_role:
            # 표면별 전용 에이전트: 의식 건너뛰고 지정 모델(기본 경량)로 바로 실행.
            original_provider = _switch_to_role(self, force_role)
        elif request_type == "THINK":
            consciousness_output = self._run_consciousness_or_reuse(message, history, execution_memory)
        elif reflex_hint:
            # reflex만 중급 모델 — 무의식 EXECUTE 오분류여도 본격 모델이 받아 품질 방어
            original_provider = _switch_to_midtier(self)

        # Clarification fast-path — 의식이 정보 부족으로 확인을 요청하면 실행 스킵
        _clarify_text = self._consciousness_clarification(consciousness_output) if consciousness_output else None
        if _clarify_text:
            print(f"[의식] clarification fast-path: 실행 에이전트 스킵")
            _restore_provider(self, original_provider)
            yield {"type": "text", "content": _clarify_text}
            yield {"type": "final", "content": _clarify_text}
            yield {"type": "_turn_meta", "tool_calls": [], "clarify": True}
            return

        # 작업전 공개(계기판) — 실행 직전 "무슨 판단·얼마나 확신·무슨 연상"을 노출
        try:
            _decision = "reflex" if reflex_hint else ("think" if request_type == "THINK" else "execute")
            _criteria = ""
            if consciousness_output:
                _criteria = self._extract_achievement_criteria(consciousness_output) or ""
            yield {
                "type": "cognition",
                "decision": _decision,
                "score": round(float(hippo_score or 0.0), 3),
                "action": (reflex_hint or top_code or ""),
                "criteria": _criteria,
            }
        except Exception as _ce:
            print(f"[인지] 작업전 공개(cognition) 생성 실패 (무시): {_ce}")

        # 4. 프롬프트 갱신 — 안정/가변 분리 (캐시 prefix 보존) + 사용자 명령 융합
        augmented_message = message
        if is_system_ai:
            role = self._load_role()
            if consciousness_output or execution_memory or reflex_hint or extra_role:
                _exec_mem = execution_memory
                if reflex_hint:
                    _exec_mem = (f"{execution_memory}\n\n[Reflex 매칭] {reflex_hint}"
                                 if execution_memory else f"[Reflex 매칭] {reflex_hint}")
                stable_prompt, dynamic_context = self._build_system_ai_prompt_split(
                    role, consciousness_output, _exec_mem,
                    extra_role=extra_role, allowed_set=allowed_set
                )
                self.ai.system_prompt = stable_prompt
                if self.ai._provider:
                    self.ai._provider.system_prompt = stable_prompt
                if consciousness_output:
                    from prompt_builder import compile_user_command
                    _fused = compile_user_command(message, consciousness_output)
                    augmented_message = f"{dynamic_context}\n\n{_fused}" if dynamic_context else _fused
                elif dynamic_context:
                    augmented_message = f"{dynamic_context}\n\n{message}"
        else:
            if consciousness_output:
                role_file = self.project_path / f"agent_{agent_name}_role.txt"
                role = role_file.read_text(encoding='utf-8') if role_file.exists() else ""
                stable_prompt, dynamic_context = self._build_system_prompt_split(
                    role, consciousness_output, execution_memory
                )
                self.ai.system_prompt = stable_prompt
                if self.ai._provider:
                    self.ai._provider.system_prompt = stable_prompt
                from prompt_builder import compile_user_command
                fused_command = compile_user_command(message, consciousness_output)
                augmented_message = f"{dynamic_context}\n\n{fused_command}" if dynamic_context else fused_command
            elif execution_memory or reflex_hint:
                # EXECUTE 경로: 실행기억(+reflex 힌트)만 가변 컨텍스트로 반영
                _exec_mem = execution_memory or ""
                if reflex_hint:
                    _exec_mem += (
                        f"\n\n<reflex_hint note=\"고확신 매칭된 IBL 패턴입니다. "
                        f"이 코드를 우선적으로 사용하세요.\">"
                        f"\n{reflex_hint}\n</reflex_hint>"
                    )
                role_file = self.project_path / f"agent_{agent_name}_role.txt"
                role = role_file.read_text(encoding='utf-8') if role_file.exists() else ""
                stable_prompt, dynamic_context = self._build_system_prompt_split(role, None, _exec_mem)
                self.ai.system_prompt = stable_prompt
                if self.ai._provider:
                    self.ai._provider.system_prompt = stable_prompt
                if dynamic_context:
                    augmented_message = f"{dynamic_context}\n\n{message}"

        # 히스토리 편집 (의식 요약 있으면 대체, 없으면 원본 유지)
        history = self._apply_consciousness_to_history(history, consciousness_output)

        # 5~8. 실행 → 평가(THINK) → 반성(EXECUTE) — 궤적을 수집하며 이벤트 yield
        final_content = ""
        eval_tool_calls: List[Dict] = []   # 평가/반성용 trace ({name,input,result,is_error})
        tool_results_log: List[str] = []   # legacy — 결과 문자열만
        tool_calls_log: List[Dict] = []    # 경험 증류·X-Ray용 구조화 이력
        _error_text = None

        def _collect(ev: dict):
            """tool_start/tool_result 이벤트를 궤적으로 페어링 수집 (MCP prefix 정규화)"""
            et = ev.get("type")
            if et == "tool_start":
                _raw = ev.get("name", "")
                _name = _raw[len("mcp__indiebizos__"):] if _raw.startswith("mcp__indiebizos__") else _raw
                tool_calls_log.append({"tool_name": _name, "input": ev.get("input", {}), "success": True})
                eval_tool_calls.append({"name": _name, "input": ev.get("input", {}),
                                        "result": "", "is_error": False})
            elif et == "tool_result":
                _rt = ev.get("result", "")
                tool_results_log.append(_rt)
                # 가장 최근 trace 항목에 결과 페어링 (도구 순차 실행)
                if eval_tool_calls and not eval_tool_calls[-1]["result"]:
                    eval_tool_calls[-1]["result"] = _rt
                    eval_tool_calls[-1]["is_error"] = bool(ev.get("is_error", False))

        try:
            from thread_context import clear_tool_calls as _clear_tc
            _clear_tc()  # 턴 시작 — 이전 턴 잔여 이력 제거

            # 6. 실행
            for event in self.ai.process_message_stream(
                message_content=augmented_message,
                history=history,
                images=images,
                cancel_check=cancel_check,
            ):
                _collect(event)
                if event.get("type") == "final":
                    final_content = event.get("content", "")
                yield event

            # 7. 평가 루프 (THINK 경로) — 달성 기준이 있으면 평가 후 재시도
            if consciousness_output and final_content:
                criteria = self._extract_achievement_criteria(consciousness_output)
                if criteria:
                    from world_pulse import _load_config as _load_wp_config
                    _goal_cfg = _load_wp_config().get("goal_eval", {})
                    if _goal_cfg.get("enabled", True):
                        print(f"[GoalEval] 달성 기준 감지: {criteria[:80]}")
                        evaluated = self._run_goal_evaluation_loop(
                            user_message=message,
                            criteria=criteria,
                            initial_response=final_content,
                            history=history,
                            consciousness_output=consciousness_output,
                            max_rounds=_goal_cfg.get("max_rounds", 3),
                            tool_results=tool_results_log,
                            tool_calls=eval_tool_calls,
                            execution_memory=execution_memory,
                        )
                        if evaluated and evaluated.strip() and evaluated != final_content:
                            final_content = evaluated
                            yield {"type": "text", "content": "\n\n---\n[평가 피드백 반영 재실행]\n\n"}
                            yield {"type": "text", "content": evaluated}
                            yield {"type": "final", "content": evaluated}
                            print(f"[GoalEval] 재실행 결과 전송 완료 ({len(evaluated)}자)")

            # 8. 자기반성 턴 (EXECUTE 경로) — 의식이 없으면 평가가 안 돌아 실패 인식이
            # 통째로 빠진다(에피소드 727/728). 실행 에이전트 *자신*이 같은 세션(resume)을
            # 이어받아 자기 궤적을 입력으로 받고 스스로 반성·재행동한다(판정자 아님).
            # 도구를 실제로 부른 턴만 · reflex/force_role 제외 · 1회(반성의 반성 없음).
            elif final_content and eval_tool_calls and not reflex_hint and not force_role:
                try:
                    from world_pulse import _load_config as _load_wp_config
                    _refl_cfg = _load_wp_config().get("execution_reflection", {})
                except Exception:
                    _refl_cfg = {}
                if _refl_cfg.get("enabled", True):
                    from agent_cognitive import build_reflection_message
                    _refl_msg = build_reflection_message(final_content, eval_tool_calls)
                    print(f"[SelfReflect] 자기반성 턴 시작 — 실행 에이전트가 자기 궤적 재검토 (도구 {len(eval_tool_calls)}회)")
                    yield {"type": "text", "content": "\n\n---\n[자기반성]\n\n"}
                    _refl_final = ""
                    # 같은 에이전트·같은 세션(resume) 이어서 — 실행 부분만 재호출(파이프라인
                    # 재진입 아님). 자기 도구를 그대로 들고 스스로 판단·재행동.
                    for ev in self.ai.process_message_stream(
                        message_content=_refl_msg,
                        history=history,
                        images=None,
                        cancel_check=cancel_check,
                    ):
                        _collect(ev)
                        if ev.get("type") == "final":
                            _refl_final = ev.get("content", "")
                        yield ev
                    if _refl_final and _refl_final.strip():
                        # 원 응답 끝의 [MAP:] 지도 태그(프로바이더가 도구 결과에서 수확해
                        # 재주입한 표시 봉투)는 반성 턴 출력에 없으므로 이월한다 —
                        # 교체가 지도를 삼키던 유실 지점(에피소드 767). 전송 계층(WS)은
                        # *final 이벤트*의 content 를 저장·전송하므로 갱신 final 을 다시 흘린다.
                        _lost_maps = [t for t in _extract_map_tag_texts(final_content)
                                      if t not in _refl_final]
                        if _lost_maps:
                            _refl_final = _refl_final.rstrip() + "\n\n" + "\n".join(_lost_maps)
                            print(f"[SelfReflect] 지도 태그 {len(_lost_maps)}건 이월")
                            yield {"type": "final", "content": _refl_final}
                        final_content = _refl_final
                        print(f"[SelfReflect] 반성 후 최종 응답 갱신 ({len(_refl_final)}자)")

        except GeneratorExit:
            # 소비자 조기 종료(취소·타임아웃) — finally에서 뒷정리만 하고 전파
            raise
        except Exception as e:
            print(f"[인지 파이프라인] 예외: {e}")
            _error_text = str(e)
        finally:
            # 중급/역할 모델 사용 후 원래 provider 복원
            _restore_provider(self, original_provider)
            # thread_context의 node/action/ms 이력 합류 (X-Ray·증류용)
            self._collect_thread_tool_calls(tool_calls_log)
            # 턴 종료 메모리 쓰기(경험+심층+포식) — 초크포인트 한 곳(_after_response).
            # ★force_role 표면(포식 등)은 제외 — stateless 검색이 심층/의미 메모리를
            # 더럽히지 않도록 메모리 정책을 진입점이 직접 관장한다(포식 브라우저는
            # assume_forage 포식 증류만 자체 수행 — api_system_ai 포식 스레드 참조).
            if not force_role:
                self._after_response(
                    message, final_content,
                    tool_calls=tool_calls_log, hippo_score=hippo_score, top_code=top_code,
                )

        if _error_text is not None:
            yield {"type": "error", "content": _error_text}
        yield {"type": "_turn_meta", "tool_calls": list(tool_calls_log)}
