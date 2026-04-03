"""
agent_communication.py - AgentRunner 통신/채널/위임 Mixin
IndieBiz OS Core

AgentRunner의 외부 채널 통신, 내부 메시지 처리, 위임 체인 보고 등
통신 관련 메서드를 분리한 Mixin 클래스입니다.
"""

import json
import re
import uuid
from datetime import datetime
from typing import List

from thread_context import (
    set_current_agent_id, set_current_agent_name, set_current_project_id,
    set_current_task_id, clear_current_task_id,
    did_call_agent, clear_called_agent,
    set_allowed_nodes
)


class AgentCommunicationMixin:
    """AgentRunner의 통신/채널/위임 관련 메서드 Mixin"""

    def _setup_channels(self) -> List:
        """
        채널 설정 (외부 에이전트용)
        Returns:
            list: Channel 인스턴스 리스트
        """
        from channels import get_channel

        channels = []
        agent_config = self.config

        # 방법 1: 단일 채널 (기존 호환)
        if 'channel' in agent_config:
            channel_type = agent_config['channel']
            channel_config = agent_config.get(channel_type, {}).copy()

            # 에이전트의 email 정보 추가
            if 'email' in agent_config:
                channel_config['email'] = agent_config['email']

            try:
                ch = get_channel(channel_type, channel_config)
                channels.append(ch)
                self._log(f"채널 로드: {channel_type}")
            except Exception as e:
                self._log(f"채널 로드 실패 ({channel_type}): {e}")

        # 방법 2: 멀티 채널
        elif 'channels' in agent_config:
            for ch_cfg in agent_config['channels']:
                try:
                    ch = get_channel(ch_cfg['type'], ch_cfg)
                    channels.append(ch)
                    self._log(f"채널 로드: {ch_cfg['type']}")
                except Exception as e:
                    self._log(f"채널 로드 실패: {e}")

        return channels

    def _log(self, message: str):
        """로그 출력"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        agent_name = self.config.get('name', '?')
        print(f"[{timestamp}] [{agent_name}] {message}")

    def _is_from_owner(self, from_addr: str, contact_type: str) -> bool:
        """메시지가 소유자(사용자)로부터 왔는지 확인 (환경변수 기반)"""
        import os
        from dotenv import load_dotenv

        # 환경변수 로드
        from runtime_utils import get_base_path
        env_path = get_base_path() / ".env"
        load_dotenv(env_path)

        from_addr_lower = from_addr.lower().strip()

        if contact_type == 'gmail':
            # 이메일 주소 비교 (< > 제거)
            email_match = re.search(r'<([^>]+)>', from_addr)
            if email_match:
                from_addr_lower = email_match.group(1).lower()

            # 환경변수에서 소유자 이메일 목록 확인
            owner_emails = os.getenv('OWNER_EMAILS', '')
            if owner_emails:
                emails = {e.strip().lower() for e in owner_emails.split(',') if e.strip()}
                return from_addr_lower in emails
            return False

        elif contact_type == 'nostr':
            # 환경변수에서 소유자 Nostr 공개키 목록 확인 (npub→hex 변환)
            owner_nostr = os.getenv('OWNER_NOSTR_PUBKEYS', '')
            if owner_nostr:
                pubkeys = set()
                for p in owner_nostr.split(','):
                    p = p.strip()
                    if not p:
                        continue
                    if p.startswith('npub'):
                        try:
                            from pynostr.key import PublicKey
                            pubkeys.add(PublicKey.from_npub(p).hex().lower())
                        except Exception:
                            pubkeys.add(p.lower())
                    else:
                        pubkeys.add(p.lower())
                return from_addr_lower in pubkeys
            return False

        return False

    def _run_loop(self):
        """백그라운드 루프 (내부 메시지 + 외부 채널 폴링)"""
        import time

        # 스레드별 에이전트 컨텍스트 설정
        set_current_agent_id(self.config.get("id"))
        set_current_agent_name(self.config.get("name"))
        set_current_project_id(self.project_id)

        # IBL 노드 접근 제어 설정 (Phase 16: 모든 에이전트)
        from ibl_access import resolve_allowed_nodes
        allowed = resolve_allowed_nodes(self.config.get("allowed_nodes"))
        set_allowed_nodes(allowed)

        # 에이전트 타입 확인
        agent_type = self.config.get('type', 'internal')

        # 외부 에이전트만 채널 초기화
        if agent_type == 'external':
            self.channels = self._setup_channels()

            if not self.channels:
                self._log("채널 없음 - 내부 메시지만 처리")
            else:
                self._log(f"채널 설정 완료: {[ch.__class__.__name__ for ch in self.channels]}")

                # 모든 채널 인증 및 실시간 채널 설정
                for channel in self.channels:
                    try:
                        if channel.authenticate():
                            info = channel.get_channel_info()
                            self._log(f"채널 연결: {info.get('type', 'unknown')} - {info.get('account', 'unknown')}")

                            # 실시간 채널이면 콜백 등록 및 리스닝 시작
                            if channel.is_realtime():
                                callback = self._make_channel_callback(channel)
                                channel.register_callback(callback)
                                channel.start_listening()
                                self._log(f"실시간 채널 활성화: {info.get('type', 'unknown')}")
                        else:
                            self._log(f"채널 인증 실패: {channel.__class__.__name__}")
                    except Exception as e:
                        import traceback
                        self._log(f"채널 인증 오류: {e}")
                        traceback.print_exc()

                # 외부 에이전트는 채널을 AI에게 전달
                if self.ai:
                    for channel in self.channels:
                        if channel.__class__.__name__ == 'GmailChannel':
                            self.ai.gmail = channel.client
                            self._log("Gmail 채널 AI 연결")
                        elif channel.__class__.__name__ == 'NostrChannel':
                            self.ai.nostr = channel
                            self._log("Nostr 채널 AI 연결")

        polling_interval = self.common_config.get('polling_interval', 10)

        while self.running and not self.cancel_event.is_set():
            try:
                # 1. 내부 메시지 확인
                self._check_internal_messages()

                # 2. 폴링 채널 확인 (외부 에이전트, 실시간 채널은 콜백으로 처리됨)
                if agent_type == 'external':
                    for channel in self.channels:
                        if not channel.is_realtime():
                            try:
                                messages = channel.poll_messages(max_count=5)
                                for msg in messages:
                                    msg_id = msg.get('id', '')
                                    if msg_id and msg_id not in self.processed_ids:
                                        self.processed_ids.add(msg_id)

                                        # 읽음 표시
                                        try:
                                            channel.mark_as_read(msg_id)
                                        except Exception as e:
                                            self._log(f"읽음 표시 실패: {e}")

                                        # 메시지 처리
                                        self._process_channel_message(channel, msg)
                            except Exception as e:
                                self._log(f"채널 폴링 오류 ({channel.__class__.__name__}): {e}")

                # 대기 (Event 기반 - 스핀락 대신)
                # cancel_event.wait()는 이벤트가 set되거나 timeout이 만료될 때까지 블로킹
                # 중간에 내부 메시지를 확인하기 위해 짧은 간격으로 나눔
                wait_interval = min(polling_interval, 5)  # 최대 5초 단위로 대기
                remaining = polling_interval
                while remaining > 0 and self.running and not self.cancel_event.is_set():
                    self.cancel_event.wait(timeout=wait_interval)
                    if self.cancel_event.is_set():
                        break
                    self._check_internal_messages()
                    remaining -= wait_interval

            except Exception as e:
                self._log(f"루프 에러: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(5)

        # 종료 시 실시간 채널 리스닝 중지
        for channel in self.channels:
            if channel.is_realtime():
                channel.stop_listening()

    def _make_channel_callback(self, channel):
        """채널별 콜백 함수 생성 (클로저 문제 해결)"""
        def callback(msg):
            self._process_channel_message(channel, msg)
        return callback

    def _process_channel_message(self, channel, msg):
        """외부 채널에서 받은 메시지 처리"""
        import time as time_module

        subject = msg.get('subject', '(제목 없음)')
        from_addr = msg.get('from', '')
        content = msg.get('body', '')

        # 시스템 메시지 필터링
        system_senders = ['mailer-daemon@', 'postmaster@', 'noreply@', 'no-reply@']
        if any(sender in from_addr.lower() for sender in system_senders):
            self._log(f"시스템 메시지 무시: {subject}")
            return

        self._log(f"새 메시지: {subject} (from: {from_addr})")

        try:
            # 채널 타입 파악
            channel_type = channel.__class__.__name__
            if 'Gmail' in channel_type:
                contact_type = 'gmail'
                reply_to = from_addr
            elif 'Nostr' in channel_type:
                contact_type = 'nostr'
                reply_to = from_addr
            else:
                contact_type = 'unknown'
                reply_to = from_addr

            # 사용자(소유자) 여부 확인
            is_from_owner = self._is_from_owner(from_addr, contact_type)

            # 소유자가 아니면 무시 (보안: 외부인 명령 차단)
            if not is_from_owner:
                self._log(f"외부인 메시지 무시: {from_addr}")
                return

            # 태스크 생성
            task_id = f"task_{uuid.uuid4().hex[:8]}"
            requester_info = f"{from_addr}@{contact_type}"

            try:
                self.db.create_task(
                    task_id=task_id,
                    requester=requester_info,
                    requester_channel=contact_type,
                    original_request=content,
                    delegated_to=self.config.get('name', '')
                )
                self._log(f"[외부채널] task 생성: {task_id}")
            except Exception as task_err:
                self._log(f"[외부채널] task 생성 실패: {task_err}")

            set_current_task_id(task_id)
            clear_called_agent()

            # 히스토리 로드 (GUI와 동일하게)
            self._log(f"사용자 명령으로 처리 (히스토리 적용)")
            agent_name = self.config.get('name', '')
            agent_id = self.db.get_or_create_agent(agent_name, "ai_agent")
            user_id = self.db.get_or_create_agent("user", "user")
            # conversation_db에 사용자 메시지 저장
            self.db.save_message(user_id, agent_id, content, contact_type=contact_type)
            # 히스토리 로드
            history = self.db.get_history_for_ai(agent_id, user_id)

            # AI 처리
            if self.ai:
                start_time = time_module.time()

                # 실행기억 생성 (RAG + discover + implementation, 1회)
                execution_memory = self._build_execution_memory(content)

                # 해마 최고 점수 저장 (경험 증류 판단용)
                from ibl_usage_rag import get_top_score as _get_top_score
                _hippocampus_score = _get_top_score(content)

                # 도구 호출 이력 초기화 (경험 증류용)
                from thread_context import clear_tool_calls, get_tool_calls
                clear_tool_calls()

                # 무의식 에이전트 — 실행형/판단형 분류 (반사 신경 + Reflex IBL)
                request_type, reflex_hint = self._classify_request(content, execution_memory)
                self._log(f"[무의식] 분류: {request_type}" + (f" (Reflex)" if reflex_hint else ""))

                # 판단형만 의식 에이전트 실행
                consciousness_output = None
                if request_type == "THINK":
                    consciousness_output = self._run_consciousness(
                        content, history, execution_memory
                    )
                if consciousness_output:
                    # 시스템 프롬프트 재구성 (의식 에이전트 출력 + 실행기억 반영)
                    role_file = self.project_path / f"agent_{agent_name}_role.txt"
                    role = role_file.read_text(encoding='utf-8') if role_file.exists() else ""
                    new_prompt = self._build_system_prompt(
                        role, consciousness_output, execution_memory
                    )
                    self.ai.system_prompt = new_prompt
                    if self.ai._provider:
                        self.ai._provider.system_prompt = new_prompt

                    # 히스토리 편집 (의식 에이전트 판단에 따라)
                    history = self._apply_consciousness_to_history(history, consciousness_output)
                elif execution_memory or reflex_hint:
                    # EXECUTE 경로: 실행기억(+reflex 힌트)만 시스템 프롬프트에 반영
                    _exec_mem = execution_memory or ""
                    if reflex_hint:
                        _exec_mem += (
                            f"\n\n<reflex_hint note=\"고확신 매칭된 IBL 패턴입니다. "
                            f"이 코드를 우선적으로 사용하세요.\">"
                            f"\n{reflex_hint}\n</reflex_hint>"
                        )
                    role_file = self.project_path / f"agent_{agent_name}_role.txt"
                    role = role_file.read_text(encoding='utf-8') if role_file.exists() else ""
                    new_prompt = self._build_system_prompt(
                        role, None, _exec_mem
                    )
                    self.ai.system_prompt = new_prompt
                    if self.ai._provider:
                        self.ai._provider.system_prompt = new_prompt

                response = self.ai.process_message_with_history(
                    message_content=content,
                    from_email=from_addr,
                    history=history,
                    reply_to=reply_to,
                    task_id=task_id
                )
                process_time = time_module.time() - start_time
                self._log(f"AI 응답 생성 ({process_time:.1f}초): {len(response)}자")

                # Goal 평가 루프 — 달성 기준이 있으면 평가 후 재시도
                if consciousness_output:
                    criteria = self._extract_achievement_criteria(consciousness_output)
                    if criteria:
                        from world_pulse import _load_config as _load_wp_config
                        _goal_cfg = _load_wp_config().get("goal_eval", {})
                        if _goal_cfg.get("enabled", True):
                            self._log(f"[GoalEval] 달성 기준 감지: {criteria[:80]}")
                            response = self._run_goal_evaluation_loop(
                                user_message=content,
                                criteria=criteria,
                                initial_response=response,
                                history=history,
                                consciousness_output=consciousness_output,
                                max_rounds=_goal_cfg.get("max_rounds", 3),
                                execution_memory=execution_memory,
                            )

                # call_agent 호출 여부 확인
                called_another = did_call_agent()

                if not called_another:
                    # 직접 처리 완료 → 채널로 응답 전송
                    try:
                        channel.send_message(
                            to=reply_to,
                            subject=f"Re: {subject}",
                            body=response
                        )
                        self._log(f"응답 전송 완료 → {reply_to}")

                        # 사용자 명령인 경우 응답도 conversation_db에 저장
                        if is_from_owner:
                            agent_name = self.config.get('name', '')
                            agent_id = self.db.get_or_create_agent(agent_name, "ai_agent")
                            user_id = self.db.get_or_create_agent("user", "user")
                            self.db.save_message(agent_id, user_id, response, contact_type=contact_type)

                        # 태스크 완료
                        self.db.complete_task(task_id, response[:500])
                    except Exception as send_err:
                        self._log(f"응답 전송 실패: {send_err}")
                else:
                    self._log("call_agent 호출됨 - 위임 결과 대기")

                # 경험 증류: 해마 점수가 낮은 성공 세션에서 새로운 패턴 학습
                _tool_calls = get_tool_calls()
                if response and _tool_calls:
                    try:
                        from ibl_usage_rag import distill_experience
                        distill_experience(content, _tool_calls, _hippocampus_score)
                    except Exception as distill_err:
                        self._log(f"[경험증류] 오류 (무시): {distill_err}")

            # 컨텍스트 정리
            clear_current_task_id()
            clear_called_agent()

        except Exception as e:
            import traceback
            self._log(f"채널 메시지 처리 실패: {e}")
            traceback.print_exc()

    def _check_internal_messages(self):
        """내부 메시지 확인 및 처리"""
        my_key = getattr(self, 'registry_key', None)
        my_name = self.config.get('name')
        if not my_key:
            return

        # 스레드 안전하게 메시지 가져오기
        from agent_runner import AgentRunner
        with AgentRunner._lock:
            messages = AgentRunner.internal_messages.get(my_key, [])
            if not messages:
                return
            msg_dict = messages.pop(0)

        while msg_dict:
            if not isinstance(msg_dict, dict):
                print(f"[AgentRunner] {my_name} 경고: 유효하지 않은 메시지 - 건너뛰기")
                # 다음 메시지 가져오기 (무한 루프 방지)
                with AgentRunner._lock:
                    messages = AgentRunner.internal_messages.get(my_key, [])
                    msg_dict = messages.pop(0) if messages else None
                continue

            try:
                from_agent = msg_dict.get('from_agent', 'unknown')
                content = msg_dict.get('content', '')
                task_id = msg_dict.get('task_id')

                print(f"[AgentRunner] {my_name} 내부 메시지 수신: {from_agent}로부터")
                print(f"   내용: {content[:100]}..." if len(content) > 100 else f"   내용: {content}")

                # 에이전트 간 수신 메시지 DB 기록
                try:
                    from_agent_db_id = self.db.get_or_create_agent(from_agent, "ai_agent")
                    my_agent_db_id = self.db.get_or_create_agent(my_name, "ai_agent")
                    self.db.save_message(from_agent_db_id, my_agent_db_id, content, contact_type='agent_to_agent')
                except Exception as db_err:
                    print(f"[AgentRunner] 수신 메시지 DB 기록 실패: {db_err}")

                # 태스크 ID 설정 (메시지에서 추출 또는 전달받은 것 사용)
                extracted_task_id = task_id
                if not extracted_task_id:
                    task_match = re.search(r'\[task:([^\]]+)\]', content)
                    if task_match:
                        extracted_task_id = task_match.group(1)

                if extracted_task_id:
                    set_current_task_id(extracted_task_id)
                    print(f"   [task_id] {extracted_task_id}")

                # call_agent 호출 플래그 초기화
                clear_called_agent()

                # 시스템 AI 위임 여부 확인
                is_from_system_ai = False
                if extracted_task_id:
                    task_info = self.db.get_task(extracted_task_id)
                    if task_info and task_info.get('requester_channel') == 'system_ai':
                        is_from_system_ai = True

                # 위임 컨텍스트 복원 (보고 메시지인 경우)
                delegation_context = None
                is_report_message = any(keyword in content for keyword in ['완료', '보고', '결과'])

                if is_report_message and extracted_task_id:
                    task = self.db.get_task(extracted_task_id)
                    if task and task.get('delegation_context'):
                        try:
                            delegation_context = json.loads(task['delegation_context'])
                            # 새 형식 (delegations 배열)
                            if 'delegations' in delegation_context:
                                delegations = delegation_context.get('delegations', [])
                                print(f"   [위임 컨텍스트 복원] {len(delegations)}개 위임의 결과 수신")
                            else:
                                # 구 형식
                                print(f"   [위임 컨텍스트 복원] {delegation_context.get('delegated_to', '?')}의 결과 수신")
                        except json.JSONDecodeError:
                            print(f"   [위임 컨텍스트] JSON 파싱 실패")

                # AI 처리
                if self.ai:
                    # 실행기억 생성 + 메시지 앞에 주입 (에이전트 간 경로)
                    exec_mem = self._build_execution_memory(content)
                    ai_message = f"{exec_mem}\n\n{content}" if exec_mem else content
                    history = []

                    # 시스템 AI 위임인 경우 파일 경로 원칙 추가
                    if is_from_system_ai:
                        ai_message = f"""[시스템 AI 위임 작업]
{content}

[중요: 파일 경로 원칙]
파일 위치를 보고할 때는 반드시 절대경로를 사용하세요.
시스템 AI와 프로젝트 에이전트의 작업 디렉토리가 다르므로, 상대경로로 보고하면 파일을 찾을 수 없습니다."""

                    if delegation_context:
                        original_request = delegation_context.get('original_request', '')
                        completed = delegation_context.get('completed', [])

                        # 완료된 위임 기록을 히스토리로 변환
                        history = self._build_history_from_completed(completed)

                        # 완료된 작업 목록 포맷팅
                        completed_summary = self._format_completed_delegations(completed)

                        ai_message = f"""[위임 결과]
{content}

---
{completed_summary}
원래 요청: {original_request}

위 결과를 바탕으로:
- 추가 작업이 필요하면 다른 에이전트에게 위임하세요.
- 모든 작업이 완료되었으면 요청자에게 결과를 보고하세요."""

                    response = self.ai.process_message_with_history(
                        message_content=ai_message,
                        from_email=f"{from_agent}@internal",
                        history=history,
                        reply_to=f"{from_agent}@internal"
                    )
                    print(f"[AgentRunner] {my_name} 응답 생성: {len(response)}자")

                    # 에이전트 간 응답 메시지 DB 기록
                    try:
                        my_agent_db_id = self.db.get_or_create_agent(my_name, "ai_agent")
                        from_agent_db_id = self.db.get_or_create_agent(from_agent, "ai_agent")
                        self.db.save_message(my_agent_db_id, from_agent_db_id, response, contact_type='agent_to_agent')
                    except Exception as db_err:
                        print(f"[AgentRunner] 응답 메시지 DB 기록 실패: {db_err}")

                    # call_agent 호출 여부 확인
                    called_another = did_call_agent()

                    if called_another:
                        # 다른 에이전트에게 위임함 → 자동 보고 스킵
                        print(f"[AgentRunner] {my_name} call_agent 호출됨 - 자동 보고 스킵, 위임 결과 대기")
                    else:
                        # 직접 처리 완료 → 자동 보고 (태스크 삭제됨)
                        if extracted_task_id:
                            self._auto_report_to_chain(extracted_task_id, response, from_agent)
                        else:
                            # 태스크 ID 없이 받은 메시지 - 발신자에게 직접 응답
                            self._send_response_to_sender(from_agent, response)

                # 컨텍스트 정리
                clear_current_task_id()
                clear_called_agent()

            except Exception as e:
                import traceback
                print(f"[AgentRunner] {my_name} 메시지 처리 실패: {e}")
                traceback.print_exc()

            # 다음 메시지 가져오기 (스레드 안전)
            with AgentRunner._lock:
                messages = AgentRunner.internal_messages.get(my_key, [])
                if not messages:
                    break
                msg_dict = messages.pop(0)

    def _send_to_external_channel(self, channel_type: str, requester: str, response: str, task_id: str):
        """
        외부 채널(email, nostr)로 최종 결과 전송 - 자기 채널 사용

        Args:
            channel_type: 'gmail' or 'nostr'
            requester: 요청자 정보 (예: "user@email.com@gmail" or "pubkey@nostr")
            response: 전송할 결과 메시지
            task_id: 작업 ID
        """
        # requester에서 주소 추출 (format: "address@channel_type")
        if requester.endswith(f"@{channel_type}"):
            address = requester[:-len(f"@{channel_type}")-1]
        else:
            address = requester.split('@')[0] if '@' in requester else requester

        # 해당 타입의 채널 찾기
        target_channel = None
        for ch in self.channels:
            ch_name = ch.__class__.__name__
            if channel_type == 'gmail' and 'Gmail' in ch_name:
                target_channel = ch
                break
            elif channel_type == 'nostr' and 'Nostr' in ch_name:
                target_channel = ch
                break

        if not target_channel:
            self._log(f"[외부채널] {channel_type} 채널을 찾을 수 없음")
            return

        try:
            target_channel.send_message(
                to=address,
                subject=f"[작업 완료] {task_id}",
                body=response
            )
            self._log(f"[외부채널] {channel_type} 전송 완료 → {address}")
        except Exception as e:
            self._log(f"[외부채널] {channel_type} 전송 실패: {e}")

    def _send_to_gui(self, ws_client_id: str, response: str):
        """WebSocket을 통해 GUI에 응답 전송"""
        import asyncio
        my_name = self.config.get('name', '')

        try:
            from websocket_manager import manager

            # 연결 확인
            if ws_client_id not in manager.active_connections:
                print(f"[GUI 전송] 클라이언트 연결 없음: {ws_client_id}")
                return

            # 비동기 전송 실행
            asyncio.run(manager.send_message(ws_client_id, {
                "type": "auto_report",
                "content": f"[작업 완료]\n{response}",
                "agent": my_name
            }))
            print(f"[GUI 전송] WebSocket 전송 완료: {ws_client_id}")

        except Exception as e:
            print(f"[GUI 전송] 실패: {e}")
            import traceback
            traceback.print_exc()

    def _send_to_system_ai(self, task_id: str, response: str, from_agent: str):
        """시스템 AI에게 결과 전송"""
        my_name = self.config.get('name', '')

        try:
            from system_ai_runner import SystemAIRunner

            # 시스템 AI에게 메시지 전송
            report_msg = f"[task:{task_id}] 완료.\n{response}"
            SystemAIRunner.send_message(
                content=report_msg,
                from_agent=my_name,
                task_id=task_id,
                project_id=self.project_id
            )
            print(f"[시스템 AI 전송] {my_name}@{self.project_id} → 시스템 AI: {task_id}")
            # DB 기록은 659번(agent_to_agent)에서 이미 수행됨 - 중복 저장 방지

        except Exception as e:
            print(f"[시스템 AI 전송] 실패: {e}")
            import traceback
            traceback.print_exc()

    def _send_response_to_sender(self, from_agent: str, response: str):
        """발신자에게 응답 전송"""
        from agent_runner import AgentRunner
        my_name = self.config.get('name', '')

        if not from_agent or from_agent == 'system':
            print(f"[AgentRunner] {my_name} 응답: {response[:200]}...")
            return

        # 같은 프로젝트 내에서 발신자 찾기
        target = AgentRunner.get_agent_by_name(from_agent, project_id=self.project_id)
        if target:
            target_key = target.registry_key
            reply_msg = f"[{my_name} 응답] {response}"

            msg_dict = {
                'content': reply_msg,
                'from_agent': my_name,
                'timestamp': datetime.now().isoformat()
            }

            with AgentRunner._lock:
                if target_key not in AgentRunner.internal_messages:
                    AgentRunner.internal_messages[target_key] = []
                AgentRunner.internal_messages[target_key].append(msg_dict)

            print(f"[AgentRunner] {my_name} → {from_agent}: 응답 전달 완료")
        else:
            print(f"[AgentRunner] {my_name} 응답 (발신자 '{from_agent}' 미발견): {response[:200]}...")

    def _build_history_from_completed(self, completed: list) -> list:
        """완료된 위임 기록을 AI 히스토리 형식으로 변환"""
        history = []
        for entry in completed:
            to_agent = entry.get('to', '')
            message = entry.get('message', '')
            result = entry.get('result', '')

            # 내가 위임한 내역
            history.append({
                "role": "assistant",
                "content": f"[위임] {to_agent}에게 요청: {message}"
            })

            # 에이전트의 응답
            if result:
                history.append({
                    "role": "user",
                    "content": f"[{to_agent} 응답] {result[:500]}..." if len(result) > 500 else f"[{to_agent} 응답] {result}"
                })

        return history

    def _format_completed_delegations(self, completed: list) -> str:
        """완료된 위임 기록을 텍스트로 포맷팅"""
        if not completed:
            return ""

        lines = ["[이미 완료된 작업]"]
        for i, entry in enumerate(completed, 1):
            to_agent = entry.get('to', '')
            result = entry.get('result', '')
            # 파일 경로가 포함된 결과는 그대로 표시, 아니면 500자로 요약
            if '파일로 저장' in result or '/outputs/' in result:
                result_summary = result[:800] if len(result) > 800 else result
            else:
                result_summary = result[:500] + "..." if len(result) > 500 else result
            lines.append(f"{i}. {to_agent}: {result_summary}")

        return "\n".join(lines) + "\n"

    def _auto_report_to_chain(self, task_id: str, response: str, from_agent: str):
        """
        자동 보고 체인: 작업 완료 시 위임 체인을 따라 결과 전달

        1. parent_task_id가 있으면 → 부모 태스크의 delegated_to에게 보고
        2. parent_task_id가 없으면 → 발신자에게 응답
        3. 병렬 위임 시 → 모든 응답 수집 후 통합 보고
        """
        from agent_runner import AgentRunner
        my_name = self.config.get('name', '')

        try:
            task = self.db.get_task(task_id)
            if not task:
                print(f"[자동 보고] task를 찾을 수 없음: {task_id}")
                # 태스크 없으면 발신자에게 직접 응답
                self._send_response_to_sender(from_agent, response)
                return

            parent_task_id = task.get('parent_task_id')
            requester = task.get('requester', '')
            channel = task.get('requester_channel', 'gui')

            # 결과 요약 (긴 응답은 파일로 저장)
            if len(response) > 2000:
                # 긴 응답은 파일로 저장하고 경로만 전달
                outputs_dir = self.project_path / "outputs"
                outputs_dir.mkdir(exist_ok=True)
                result_file = outputs_dir / f"result_{task_id}.txt"
                result_file.write_text(response, encoding='utf-8')
                result_summary = f"[작업 완료] 상세 결과가 파일로 저장되었습니다: {result_file}\n\n요약:\n{response[:500]}..."
                print(f"[자동 보고] 긴 응답({len(response)}자) → 파일 저장: {result_file}")
            else:
                result_summary = response

            # 1. parent_task_id가 있으면 → 부모 태스크에 응답 누적 + 조건부 보고
            if parent_task_id:
                # requester_channel에 따라 부모 태스크가 있는 DB에서 조회
                # - 'system_ai': 시스템 AI가 직접 위임 → system_ai_memory.db
                # - 'internal', 'gui' 등: 같은 프로젝트 내부 → conversations.db
                if channel == 'system_ai':
                    from system_ai_memory import get_task as get_system_ai_task
                    parent_task = get_system_ai_task(parent_task_id)
                else:
                    parent_task = self.db.get_task(parent_task_id)

                if parent_task:
                    # 부모 태스크의 delegation_context에 응답 누적
                    delegation_context_str = parent_task.get('delegation_context')
                    total_delegations = 0

                    if delegation_context_str:
                        try:
                            delegation_context = json.loads(delegation_context_str)

                            # 새 형식 (delegations 배열)
                            if 'delegations' in delegation_context:
                                total_delegations = len(delegation_context['delegations'])

                                # 새 응답 항목 구성
                                new_response = {
                                    'child_task_id': task_id,
                                    'from_agent': my_name,
                                    'response': result_summary,
                                    'completed_at': datetime.now().isoformat()
                                }

                                # pending_delegations 감소 및 응답 누적 (원자적 수행)
                                # Race Condition 방지: DB 트랜잭션 내에서 read-append-write
                                if channel == 'system_ai':
                                    from system_ai_memory import decrement_pending_and_update_context as sys_decrement
                                    remaining = sys_decrement(
                                        parent_task_id,
                                        new_response=new_response
                                    )
                                else:
                                    remaining = self.db.decrement_pending_and_update_context(
                                        parent_task_id,
                                        new_response=new_response
                                    )

                                print(f"[자동 보고] 응답 누적: {task_id} → {parent_task_id} (남은 위임: {remaining}/{total_delegations})")

                                # 병렬 위임 수집 모드: 동시에 2개 이상 위임이 진행 중일 때만
                                # 순차 위임: A 완료 → B 위임 → B 완료 (각 시점에서 pending은 항상 0 또는 1)
                                # 병렬 위임: A, B 동시 위임 → pending=2 → A 완료(pending=1) → B 완료(pending=0)
                                # 구분 방법: 현재 응답 도착 전 pending이 2 이상이었으면 병렬
                                pending_before_decrement = remaining + 1  # 감소 전 값

                                if pending_before_decrement >= 2:
                                    # 병렬 위임 모드 (이 응답 도착 전에 2개 이상 대기 중이었음)
                                    if remaining > 0:
                                        print(f"[자동 보고] 병렬 수집 모드 - 대기 중: {remaining}개 응답 더 필요")
                                        # 현재 태스크 삭제 후 리턴
                                        self.db.complete_task(task_id, result_summary)
                                        print(f"[자동 보고] 태스크 삭제: {task_id}")
                                        return  # 아직 다 안 모임 → 보고 스킵
                                    else:
                                        print(f"[자동 보고] 병렬 수집 모드 - 모든 응답 도착! 통합 보고 전송")
                                        # DB에서 최신 컨텍스트를 읽어 모든 응답 통합
                                        if channel == 'system_ai':
                                            from system_ai_memory import get_task as get_sys_task
                                            updated_parent = get_sys_task(parent_task_id)
                                        else:
                                            updated_parent = self.db.get_task(parent_task_id)
                                        if updated_parent and updated_parent.get('delegation_context'):
                                            updated_ctx = json.loads(updated_parent['delegation_context'])
                                            all_responses = updated_ctx.get('responses', [])
                                        else:
                                            all_responses = [new_response]
                                        combined_report = "[병렬 위임 결과 통합 보고]\n\n"
                                        for resp in all_responses:
                                            combined_report += f"◆ {resp['from_agent']}:\n{resp['response']}\n\n"
                                        result_summary = combined_report
                                # else: 순차 위임 모드 - 각 응답을 개별적으로 보고
                            else:
                                # 구버전 형식 - 기존 로직 사용
                                total_delegations = 1
                        except json.JSONDecodeError:
                            total_delegations = 1
                    else:
                        total_delegations = 1

                    # 부모 태스크의 delegated_to가 보고 받을 에이전트
                    report_to = parent_task.get('delegated_to')
                    if report_to:
                        # 시스템 AI 채널이고 보고 대상이 system_ai인 경우
                        if channel == 'system_ai' and report_to == 'system_ai':
                            # 시스템 AI에게 직접 보고
                            self._send_to_system_ai(parent_task_id, result_summary, my_name)
                            print(f"[자동 보고] {my_name} → 시스템 AI: {task_id} → {parent_task_id}")
                        else:
                            # 같은 프로젝트 내에서 보고 대상 찾기
                            target = AgentRunner.get_agent_by_name(report_to, project_id=self.project_id)
                            if target:
                                # 부모 태스크 ID로 보고
                                report_msg = f"[task:{parent_task_id}] 완료.\n{result_summary}"
                                target_key = target.registry_key

                                msg_dict = {
                                    'content': report_msg,
                                    'from_agent': my_name,
                                    'task_id': parent_task_id,
                                    'timestamp': datetime.now().isoformat()
                                }

                                with AgentRunner._lock:
                                    if target_key not in AgentRunner.internal_messages:
                                        AgentRunner.internal_messages[target_key] = []
                                    AgentRunner.internal_messages[target_key].append(msg_dict)

                                print(f"[자동 보고] {my_name} → {report_to}: {task_id} → {parent_task_id}")
                            else:
                                print(f"[자동 보고] 상위 에이전트를 찾을 수 없음: {report_to}")
                else:
                    print(f"[자동 보고] 부모 태스크를 찾을 수 없음: {parent_task_id}")

            # 2. parent_task_id가 없으면 → 최초 요청이므로 사용자에게 최종 응답
            else:
                if channel == 'gui':
                    # GUI 채널: WebSocket으로 직접 전송
                    ws_client_id = task.get('ws_client_id')
                    if ws_client_id:
                        self._send_to_gui(ws_client_id, result_summary)
                    else:
                        # ws_client_id가 없으면 발신자에게 응답
                        self._send_response_to_sender(from_agent, result_summary)
                elif channel == 'system_ai':
                    # 시스템 AI가 위임한 태스크인데 parent_task_id가 없으면 비정상
                    print(f"[자동 보고] 오류: system_ai 채널인데 parent_task_id가 없음 (task: {task_id})")
                    self._send_response_to_sender(from_agent, result_summary)
                elif channel == 'internal':
                    # 프로젝트 내부 위임인데 parent_task_id가 없으면 비정상
                    print(f"[자동 보고] 오류: internal 채널인데 parent_task_id가 없음 (task: {task_id})")
                    self._send_response_to_sender(from_agent, result_summary)
                elif channel in ('gmail', 'nostr'):
                    # 외부 채널: Gmail/Nostr로 전송
                    self._send_to_external_channel(channel, requester, result_summary, task_id)
                else:
                    # 알 수 없는 채널: 발신자에게 응답
                    self._send_response_to_sender(from_agent, result_summary)
                print(f"[자동 보고] 최초 태스크 완료: {task_id} (채널: {channel})")

            # 보고 완료 후 현재 태스크 삭제
            self.db.complete_task(task_id, result_summary)
            print(f"[자동 보고] 태스크 삭제: {task_id}")

        except Exception as e:
            import traceback
            print(f"[자동 보고] 오류: {e}")
            traceback.print_exc()
