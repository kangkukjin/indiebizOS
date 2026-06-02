"""
agent_runner.py - 에이전트 실행 로직
개별 에이전트 실행 및 내부 메시지 처리
"""

import threading
from datetime import datetime
from channels import get_channel
from ai import AIAgent
from tools import InternalMessageHandler, set_current_agent_id, set_current_task_id, get_current_task_id, clear_current_task_id, did_call_agent, clear_called_agent

from my_conversations import MyConversations
from conversation_db import HISTORY_LIMIT_AGENT


class AgentRunner:
    """개별 에이전트 실행기"""

    # 클래스 변수
    internal_messages = {}  # agent_id -> [메시지 dict]
    agent_registry = {}  # agent_id -> AgentRunner
    _lock = threading.Lock()  # 스레드 안전성을 위한 Lock
    
    def __init__(self, agent_config: dict, common_config: dict, log_callback=None):
        self.config = agent_config
        self.common = common_config
        self.running = False
        self.cancel_requested = False  # 중단 요청 플래그
        self.thread = None
        self.log_callback = log_callback
        self.channels = []  # 멀티 채널 지원
        self.ai = None
        self.processed_ids = set()


        # 대화 관리 초기화 (프로젝트별 DB 경로 사용)
        project_path = agent_config.get('_project_path')
        db_path = None
        if project_path:
            import os
            db_path = os.path.join(project_path, 'conversations.db')

        self.conversations = MyConversations(
            agent_name=agent_config['name'],
            agent_type='ai_agent',
            db_path=db_path
        )
        self.neighbor_cache = {}  # email -> neighbor_id 캐싱
        
        # 레지스트리에 등록 (스레드 안전)
        with AgentRunner._lock:
            AgentRunner.agent_registry[agent_config['id']] = self
            AgentRunner.internal_messages[agent_config['id']] = []
        
        # 내부 메시지 핸들러 설정
        InternalMessageHandler.register(agent_config["id"], self._handle_send_message, self._handle_list_agents)
    
    def _handle_send_message(self, agent_name: str, message: str) -> dict:
        """내부 메시지 전송 (비동기)"""
        target = AgentRunner.get_agent_by_name(agent_name)
        if not target:
            return {
                'success': False,
                'message': f'"{agent_name}" 에이전트를 찾을 수 없습니다. 사용 가능: {AgentRunner.get_all_agent_names()}'
            }
        
        # 메시지 큐에 추가 (스레드 안전)
        msg_dict = {
            'content': message,
            'from_agent': self.config['name'],
            'timestamp': datetime.now().isoformat()
        }

        with AgentRunner._lock:
            AgentRunner.internal_messages[target.config['id']].append(msg_dict)
        self.log(f"내부 메시지 전송: {agent_name}")
        
        return {
            'success': True,
            'message': f'{agent_name}에게 메시지를 전송했습니다.'
        }

    def _handle_list_agents(self) -> list:
        """에이전트 목록 핸들러"""
        return AgentRunner.get_all_agent_names()
    
    def log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        full_message = f"[{timestamp}] [{self.config['name']}] {message}"
        print(full_message)
        if self.log_callback:
            self.log_callback(full_message)
    
    def start(self):
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        self.log("시작됨")
    
    def stop(self):
        self.running = False

        # 실시간 채널 리스닝 중지
        for channel in self.channels:
            if channel.is_realtime():
                channel.stop_listening()

        self.log("중지됨")

    def cancel(self):
        """작업 중단 요청 (진행 중인 AI 호출도 중단)"""
        self.cancel_requested = True
        self.running = False

        # AI에게 중단 요청 전달
        if self.ai:
            self.ai.request_cancel()

        # 실시간 채널 리스닝 중지
        for channel in self.channels:
            if channel.is_realtime():
                channel.stop_listening()

        self.log("중단됨")
    
    def _setup_channels(self, agent_config: dict) -> list:
        """
        채널 설정 (단일/멀티 지원)
        Returns:
            list: Channel 인스턴스 리스트
        """
        channels = []
        
        # 방법 1: 단일 채널 (기존 호환)
        if 'channel' in agent_config:
            channel_type = agent_config['channel']
            channel_config = agent_config.get(channel_type, {}).copy()  # 복사본 생성
            
            # 에이전트의 email 정보 추가
            if 'email' in agent_config:
                channel_config['email'] = agent_config['email']
            
            try:
                ch = get_channel(channel_type, channel_config)
                channels.append(ch)
                self.log(f"채널 로드: {channel_type}")
            except Exception as e:
                self.log(f"채널 로드 실패 ({channel_type}): {e}")
        
        # 방법 2: 멀티 채널
        elif 'channels' in agent_config:
            for ch_cfg in agent_config['channels']:
                try:
                    ch = get_channel(ch_cfg['type'], ch_cfg)
                    channels.append(ch)
                    self.log(f"채널 로드: {ch_cfg['type']}")
                except Exception as e:
                    self.log(f"채널 로드 실패: {e}")
        
        return channels
    
    def _run_loop(self):
        import os

        # 프로젝트 폴더로 작업 디렉토리 변경 (파일 저장이 프로젝트별로 되도록)
        project_path = self.config.get('_project_path')
        if project_path:
            os.chdir(project_path)
            self.log(f"작업 디렉토리: {project_path}")

        # 스레드별 에이전트 ID 설정
        set_current_agent_id(self.config["id"])

        # 에이전트 타입 확인
        agent_type = self.config.get('type', 'external')
        
        # 외부 에이전트만 채널 초기화
        if agent_type == 'external':
            self.channels = self._setup_channels(self.config)
            
            if not self.channels:
                self.log("채널 없음 - 중지")
                self.running = False
                return
            
            # 채널 설정 완료
            self.log(f"채널 설정 완료: {[ch.__class__.__name__ for ch in self.channels]}")
            
            # 모든 채널 인증 및 실시간 채널 설정
            for channel in self.channels:
                try:
                    if channel.authenticate():
                        info = channel.get_channel_info()
                        self.log(f"채널 연결: {info.get('type', 'unknown')} - {info.get('account', 'unknown')}")
                        
                        # 실시간 채널이면 콜백 등록 및 리스닝 시작
                        if channel.is_realtime():
                            # 클로저 문제 해결: channel을 기본 인자로 고정
                            callback = self._make_channel_callback(channel)
                            channel.register_callback(callback)
                            channel.start_listening()
                            self.log(f"실시간 채널 활성화: {info.get('type', 'unknown')}")
                    else:
                        self.log(f"채널 인증 실패: {channel.__class__.__name__}")
                except Exception as e:
                    import traceback
                    self.log(f"채널 인증 오류: {e}")
                    self.log(traceback.format_exc())
        else:
            self.log("내부 워커 (채널 없음)")
        
        # AI 초기화 (에이전트별 설정 사용)
        ai_config = self.config.get('ai', self.common.get('claude', {}))
        # 기존 형식 호환성 (공통 설정에서 가져오는 경우)
        if 'provider' not in ai_config:
            ai_config = {
                'provider': 'anthropic',
                'api_key': ai_config.get('api_key'),
                'model': ai_config.get('model', 'claude-sonnet-4-20250514')
            }
        # 시스템 프롬프트는 히스토리에 포함되므로 빈 문자열
        # (규칙은 load_rules_history에서 히스토리 형식으로 로드됨)
        self.log("프롬프트: 히스토리 방식 (중복 제거)")
        
        self.ai = AIAgent(ai_config, "", agent_type, agent_name=self.config['name'], agent_config=self.config)
        
        # 외부 에이전트는 채널들을 AI에게 전달
        if agent_type == "external" and self.channels:
            for channel in self.channels:
                if channel.__class__.__name__ == 'GmailChannel':
                    self.ai.gmail = channel.client  # GmailClient 객체
                    self.log("Gmail 채널 AI 연결")
                elif channel.__class__.__name__ == 'NostrChannel':
                    self.ai.nostr = channel  # NostrChannel 객체
                    self.log("Nostr 채널 AI 연결")
        
        self.log("AI 준비 완료")
        
        # 폴링 루프
        while self.running:
            try:
                # 1. 내부 메시지 확인
                self._check_internal_messages()
                
                # 2. 폴링 채널만 확인 (실시간 채널은 콜백으로 처리됨)
                if agent_type == 'external':
                    for channel in self.channels:
                        # 폴링 채널만 처리
                        if not channel.is_realtime():
                            try:
                                messages = channel.poll_messages(max_count=5)
                                
                                for msg in messages:
                                    msg_id = msg.get('id', '')
                                    if msg_id and msg_id not in self.processed_ids:
                                        self.processed_ids.add(msg_id)
                                        
                                        # 중복 방지: 처리 시작 즉시 읽음 표시
                                        try:
                                            channel.mark_as_read(msg_id)
                                            self.log(f"메시지 읽음 표시: {msg_id[:12]}...")
                                        except Exception as e:
                                            self.log(f"읽음 표시 실패: {e}")
                                        
                                        # 메시지 처리 (시간 측정)
                                        import time
                                        start_time = time.time()
                                        self._process_channel_message(channel, msg)
                                        process_time = time.time() - start_time
                                        self.log(f"처리 완료 ({process_time:.1f}초)")
                            
                            except Exception as e:
                                self.log(f"채널 폴링 오류 ({channel.__class__.__name__}): {e}")
                
            except Exception as e:
                self.log(f"오류: {e}")
            
            # 대기 (내부 메시지는 1초마다 확인)
            for _ in range(self.common['polling_interval']):
                if not self.running:
                    break
                threading.Event().wait(1)
                self._check_internal_messages()

    def _check_internal_messages(self):
        """내부 메시지 확인 및 처리"""
        # 중단 요청 시 새 메시지 처리 안 함
        if self.cancel_requested:
            return

        my_id = self.config['id']

        # 스레드 안전하게 메시지 가져오기
        with AgentRunner._lock:
            messages = AgentRunner.internal_messages.get(my_id, [])
            if not messages:
                return
            msg_dict = messages.pop(0)

        while msg_dict:
            
            # 딕셔너리가 아니면 건너뛰기
            if not isinstance(msg_dict, dict):
                self.log(f"경고: 유효하지 않은 메시지 - 건너뛰기")
                continue
            
            try:
                # 메시지 내용 가져오기
                from_agent = msg_dict.get('from_agent', 'unknown')
                content = msg_dict.get('content', '')

                self.log(f"[내부 메시지] {from_agent}로부터: {content[:100]}..." if len(content) > 100 else f"[내부 메시지] {from_agent}로부터: {content}")

                # ✅ 시스템 자동화: 메시지에서 task_id 추출하여 스레드 로컬에 설정
                import re
                import json
                task_match = re.search(r'\[task:([^\]]+)\]', content)
                extracted_task_id = None
                delegation_context = None

                if task_match:
                    extracted_task_id = task_match.group(1)
                    set_current_task_id(extracted_task_id)
                    self.log(f"[task_id 추출] {extracted_task_id}")

                    # ✅ 위임 컨텍스트 복원: "왜 이 일을 시켰는지" 기억 로드
                    # 보고 메시지 ([task:xxx] 완료) 수신 시에만 컨텍스트 복원
                    is_report_message = '완료' in content or '보고' in content or '결과' in content
                    if is_report_message:
                        try:
                            from conversation_db import ConversationDB
                            db = ConversationDB()
                            task = db.get_task(extracted_task_id)

                            if task and task.get('delegation_context'):
                                delegation_context = json.loads(task['delegation_context'])
                                self.log(f"[컨텍스트 복원] 위임 컨텍스트 로드됨: {extracted_task_id}")
                        except Exception as ctx_err:
                            self.log(f"[컨텍스트 복원] 실패: {ctx_err}")

                # ✅ 보낸 사람을 agents에서 찾기
                sender_agent_id = self.conversations.find_agent_by_name(from_agent)
                if not sender_agent_id:
                    # agents 테이블에 등록되지 않은 에이전트면 추가
                    with self.conversations.db.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO agents (name, type)
                            VALUES (?, 'ai_agent')
                        """, [from_agent])
                        conn.commit()
                        sender_agent_id = cursor.lastrowid
                    self.log(f"[DB] 새 에이전트 등록: {from_agent} (ID={sender_agent_id})")

                # ✅ 에이전트 간 내부 메시지는 HISTORY_LIMIT_AGENT 사용
                # (conversation_db.py에서 관리)
                raw_history = self.conversations.get_history_for_ai(sender_agent_id, limit=HISTORY_LIMIT_AGENT)
                history = self._build_history_with_rules(raw_history)

                # ✅ 위임 컨텍스트가 있으면 히스토리 앞에 주입
                # AI가 "왜 이 일을 시켰는지" 이해할 수 있게 함
                if delegation_context:
                    context_reminder = f"""[시스템 알림 - 위임 컨텍스트 복원]
당신이 이전에 '{delegation_context.get('delegated_to', '다른 에이전트')}'에게 작업을 위임했을 때의 상황입니다:

- 원래 요청자: {delegation_context.get('requester', '알 수 없음')}
- 요청 채널: {delegation_context.get('requester_channel', 'gui')}
- 원래 요청 내용: {delegation_context.get('original_request', '알 수 없음')}
- 위임 시 메시지: {delegation_context.get('delegation_message', '')[:200]}

이제 위임한 작업의 결과가 도착했습니다.
위임 결과를 확인하고 남은 작업을 처리하세요.
(시스템이 자동으로 상위 보고를 처리합니다. call_agent로 보고할 필요 없습니다.)"""

                    # 히스토리 앞에 컨텍스트 주입 (rules 다음에)
                    # rules_history 다음 위치에 삽입
                    context_msg = {"role": "user", "content": context_reminder}

                    # rules_history 개수 파악 (보통 2개: system_prompt + role)
                    rules_count = 0
                    for msg in history:
                        if msg.get('content', '').startswith('[시스템 규칙]') or msg.get('content', '').startswith('[당신의 역할]'):
                            rules_count += 1
                        else:
                            break

                    # rules 다음에 context 삽입
                    history.insert(rules_count, context_msg)
                    self.log(f"[컨텍스트 복원] 히스토리에 위임 컨텍스트 주입 완료")
                
                # AI 처리 (AI가 call_agent를 호출하면 그쪽에서 DB 저장됨)
                self.log(f"[AI 호출] 시작...")
                clear_called_agent()  # call_agent 호출 플래그 초기화
                response = self.ai.process_message_with_history(
                    content,
                    f'{from_agent}@internal',
                    history,
                    f'{from_agent}@internal',
                    task_id=extracted_task_id  # ✅ 워커 스레드에 task_id 전달
                )
                self.log(f"[AI 응답] {len(response)}자")
                self.log(f"[AI 응답 내용] {response}")

                # ✅ 시스템 자동화: 워커 응답 완료 시 자동 결과 전달
                # AI가 call_agent를 호출하지 않았으면 시스템이 대신 전달
                current_task_id = extracted_task_id  # 워커 스레드에서 처리됐으므로 직접 사용
                called_another_agent = getattr(self.ai, '_last_called_agent', False)  # 워커에서 캡처한 값

                # 보고 메시지인지 확인 (하위 에이전트로부터 받은 보고)
                is_report_message = bool(re.search(r'\[task:[^\]]+\]\s*완료', content))

                if current_task_id:
                    if called_another_agent:
                        # AI가 다른 에이전트를 호출함 - 자동 보고 스킵 (위임받은 에이전트가 보고할 것)
                        self.log(f"[자동 보고] call_agent 호출됨 - 자동 보고 스킵, 위임 결과 대기")
                    else:
                        # 일 완료: parent_task_id를 통해 상위 에이전트에게 자동 보고
                        self._auto_report_to_chain(current_task_id, response)
                    # 워커 스레드에서 이미 정리됨 (clear_current_task_id, clear_called_agent)

                # 참고: GUI 응답은 자동 보고(_auto_report_to_chain)에서 DB에 저장됨
                # _is_connected_to_user 로직은 중복 저장을 피하기 위해 제거됨
                
            except Exception as e:
                import traceback
                self.log(f"내부 메시지 처리 실패: {e}")
                self.log(traceback.format_exc())

            # 다음 메시지 가져오기 (스레드 안전)
            with AgentRunner._lock:
                messages = AgentRunner.internal_messages.get(my_id, [])
                if not messages:
                    break
                msg_dict = messages.pop(0)


    @classmethod
    def get_agent_by_name(cls, name: str):
        """이름으로 에이전트 찾기 (스레드 안전)"""
        with cls._lock:
            for agent_id, runner in cls.agent_registry.items():
                if runner.config['name'] == name:
                    return runner
        return None

    @classmethod
    def get_all_agent_names(cls):
        """모든 에이전트 이름 목록 (스레드 안전)"""
        with cls._lock:
            return [runner.config['name'] for runner in cls.agent_registry.values()]

    def _get_or_create_neighbor(self, from_addr: str, contact_type: str = 'email') -> int:
        """이웃 찾기 또는 생성 (캐싱 포함)"""
        if from_addr in self.neighbor_cache:
            return self.neighbor_cache[from_addr]
        
        # 이름 추출 (email에서 @ 앞 부분)
        name = from_addr.split('@')[0] if '@' in from_addr else from_addr
        
        neighbor_id = self.conversations.find_or_add_neighbor(
            name=name,
            neighbor_type='human',
            contact_type=contact_type,
            contact_value=from_addr
        )
        
        # 캐싱
        self.neighbor_cache[from_addr] = neighbor_id
        return neighbor_id
    
    def _build_history_with_rules(self, raw_history: list) -> list:
        """규칙 + DB 히스토리 조합 (rules.json에서 로드)"""
        from my_conversations import MyConversations

        project_path = self.config.get('_project_path')
        rules = MyConversations.load_rules_history(self.config['name'], project_path)

        # 규칙 + 대화 히스토리 합치기
        return rules + raw_history

    def _auto_report_to_chain(self, task_id: str, response: str):
        """
        시스템 자동화: 에이전트가 일을 마치면 위임 체인을 따라 자동 보고

        각 위임마다 새 태스크가 생성되므로:
        1. 현재 태스크의 parent_task_id가 있으면 → 부모 태스크의 delegated_to에게 보고
        2. parent_task_id가 없으면 → 최초 요청자(사용자)에게 최종 보고

        Args:
            task_id: 현재 작업 ID
            response: AI 응답 (보고 내용)
        """
        import re
        import json

        # 파일 경로 추출 (상대경로/절대경로 모두 지원)
        # 백틱 안의 경로, 파일:/경로: 뒤의 경로, 절대경로 순으로 매칭
        file_patterns = [
            r'`([^`]*[\w가-힣._-]+\.(?:html|pdf|png|jpg|json|txt|csv))`',  # 백틱 안의 경로
            r'파일[:\s]*`?([^\s`]+\.(?:html|pdf|png|jpg|json|txt|csv))`?',  # 파일: 뒤
            r'경로[:\s]*`?([^\s`]+\.(?:html|pdf|png|jpg|json|txt|csv))`?',  # 경로: 뒤
            r'(/[\w가-힣/._-]+\.(?:html|pdf|png|jpg|json|txt|csv))',  # 절대경로
        ]

        file_paths = []
        for pattern in file_patterns:
            matches = re.findall(pattern, response)
            file_paths.extend(matches)
        file_paths = list(set(file_paths))

        try:
            from conversation_db import ConversationDB
            db = ConversationDB()
            task = db.get_task(task_id)

            if not task:
                self.log(f"[자동 보고] task를 찾을 수 없음: {task_id}")
                return

            # 이미 완료된 task는 중복 보고 방지
            if task.get('status') == 'completed':
                self.log(f"[자동 보고] 이미 완료된 task - 스킵: {task_id}")
                return

            my_name = self.config.get('name', '')
            parent_task_id = task.get('parent_task_id')
            requester = task.get('requester', '')
            channel = task.get('requester_channel', 'gui')

            # 결과 요약 생성
            result_summary = response[:500] if len(response) > 500 else response
            if file_paths:
                result_summary = f"파일 생성됨: {', '.join(file_paths)}\n\n{result_summary}"

            # 현재 태스크 완료 처리
            db.complete_task(task_id, result_summary)

            # ✅ 1. parent_task_id가 있으면 → 부모 태스크에 응답 누적 + 조건부 보고
            if parent_task_id:
                parent_task = db.get_task(parent_task_id)
                if parent_task:
                    # 부모 태스크의 delegation_context에 응답 누적
                    delegation_context_str = parent_task.get('delegation_context')
                    pending_delegations = parent_task.get('pending_delegations', 0)
                    total_delegations = 0

                    if delegation_context_str:
                        try:
                            delegation_context = json.loads(delegation_context_str)

                            # 새 형식 (delegations 배열)
                            if 'delegations' in delegation_context:
                                total_delegations = len(delegation_context['delegations'])

                                # 응답 누적
                                if 'responses' not in delegation_context:
                                    delegation_context['responses'] = []

                                delegation_context['responses'].append({
                                    'child_task_id': task_id,
                                    'from_agent': my_name,
                                    'response': result_summary,
                                    'completed_at': datetime.now().isoformat()
                                })

                                # pending_delegations 감소 및 컨텍스트 업데이트
                                with db.get_connection() as conn:
                                    cursor = conn.cursor()
                                    cursor.execute('''
                                        UPDATE tasks
                                        SET delegation_context = ?,
                                            pending_delegations = MAX(0, COALESCE(pending_delegations, 0) - 1)
                                        WHERE task_id = ?
                                    ''', (json.dumps(delegation_context, ensure_ascii=False), parent_task_id))
                                    conn.commit()

                                    # 업데이트된 pending_delegations 조회
                                    cursor.execute('SELECT pending_delegations FROM tasks WHERE task_id = ?', (parent_task_id,))
                                    row = cursor.fetchone()
                                    remaining = row[0] if row else 0

                                self.log(f"[자동 보고] 응답 누적: {task_id} → {parent_task_id} (남은 위임: {remaining}/{total_delegations})")

                                # ✅ 병렬 위임 수집 모드: 2개 이상 위임이면 모든 응답 도착 시까지 대기
                                if total_delegations >= 2:
                                    if remaining > 0:
                                        self.log(f"[자동 보고] 수집 모드 - 대기 중: {remaining}개 응답 더 필요")
                                        return  # 아직 다 안 모임 → 보고 스킵
                                    else:
                                        self.log(f"[자동 보고] 수집 모드 - 모든 응답 도착! 통합 보고 전송")
                                        # 모든 응답을 통합해서 보고
                                        all_responses = delegation_context.get('responses', [])
                                        combined_report = "[병렬 위임 결과 통합 보고]\n\n"
                                        for resp in all_responses:
                                            combined_report += f"◆ {resp['from_agent']}:\n{resp['response']}\n\n"
                                        result_summary = combined_report
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
                        target = AgentRunner.get_agent_by_name(report_to)
                        if target:
                            # 부모 태스크 ID로 보고 (부모가 자신의 태스크 컨텍스트를 복원할 수 있게)
                            report_msg = f"[task:{parent_task_id}] 완료.\n{result_summary}"
                            msg_dict = {
                                'content': report_msg,
                                'from_agent': my_name,
                                'timestamp': datetime.now().isoformat()
                            }
                            with AgentRunner._lock:
                                AgentRunner.internal_messages[target.config['id']].append(msg_dict)
                            self.log(f"[자동 보고] 상위 에이전트 '{report_to}'에게 보고: {task_id} → {parent_task_id}")
                        else:
                            self.log(f"[자동 보고] 상위 에이전트를 찾을 수 없음: {report_to}")
                else:
                    self.log(f"[자동 보고] 부모 태스크를 찾을 수 없음: {parent_task_id}")

            # ✅ 2. parent_task_id가 없으면 → 최초 요청이므로 사용자에게 최종 보고
            if not parent_task_id:
                if channel == 'gui':
                    # DB에 메시지 저장 (프론트엔드가 폴링해서 가져감)
                    try:
                        # requester에서 사용자 이름 추출 (format: "username@gui")
                        if requester.endswith('@gui'):
                            user_name = requester[:-4]  # "@gui" 제거
                        else:
                            user_name = requester

                        # 사용자(requester) ID 조회
                        user_agent_id = self.conversations.find_agent_by_name(user_name)
                        my_agent_id = self.conversations.find_agent_by_name(my_name)

                        if user_agent_id and my_agent_id:
                            self.conversations.db.save_message(
                                from_agent_id=my_agent_id,
                                to_agent_id=user_agent_id,
                                content=f"[작업 완료] {result_summary}",
                                contact_type='gui'
                            )
                            self.log(f"[자동 보고] GUI 메시지 DB 저장 완료: {my_name} → {user_name}")
                        else:
                            self.log(f"[자동 보고] 에이전트 ID 조회 실패: user={user_agent_id}({user_name}), my={my_agent_id}")
                    except Exception as save_error:
                        self.log(f"[자동 보고] DB 저장 오류: {save_error}")

                    # WebSocket으로 GUI에 직접 전송
                    try:
                        import asyncio
                        from websocket_manager import manager

                        # 연결된 클라이언트 확인
                        connections = list(manager.active_connections.keys())
                        self.log(f"[자동 보고] 연결된 클라이언트: {connections}")

                        # 연결된 클라이언트에게 전송
                        for client_id in connections:
                            if str(self.config['id']) in client_id:
                                asyncio.run(manager.send_message(client_id, {
                                    "type": "auto_report",
                                    "content": f"[작업 완료] {result_summary}",
                                    "agent": my_name
                                }))
                                self.log(f"[자동 보고] WebSocket 전송 완료: {client_id}")
                                break
                    except Exception as ws_error:
                        self.log(f"[자동 보고] WebSocket 전송 실패: {ws_error}")

                    self.log(f"[자동 보고] 사용자(GUI)에게 최종 결과 전달: {task_id}")
                elif channel in ('email', 'nostr'):
                    self._send_to_external_channel(channel, requester, result_summary, task_id)
                    self.log(f"[자동 보고] 사용자({channel})에게 최종 결과 전달: {task_id}")

                self.log(f"[태스크 완료] 최초 태스크 {task_id}")

        except Exception as e:
            import traceback
            self.log(f"[자동 보고] 오류: {e}")
            self.log(traceback.format_exc())

    def _send_to_external_channel(self, channel_type: str, requester: str, result: str, task_id: str):
        """
        외부 채널(email, nostr)로 최종 결과 전송

        Args:
            channel_type: 'email' or 'nostr'
            requester: 요청자 정보 (예: "user@email.com@email" or "npub1...@nostr")
            result: 전송할 결과 메시지
            task_id: 작업 ID
        """
        try:
            # requester에서 주소 추출 (format: "address@channel_type")
            # 예: "user@email.com@email" → "user@email.com"
            if requester.endswith(f"@{channel_type}"):
                address = requester[:-len(f"@{channel_type}")]
            else:
                address = requester.split('@')[0] if '@' in requester else requester

            # 해당 채널 찾기
            target_channel = None
            for ch in self.channels:
                ch_type = ch.__class__.__name__
                if channel_type == 'email' and 'Gmail' in ch_type:
                    target_channel = ch
                    break
                elif channel_type == 'nostr' and 'Nostr' in ch_type:
                    target_channel = ch
                    break

            if not target_channel:
                self.log(f"[외부채널 응답] {channel_type} 채널을 찾을 수 없음")
                return

            # 메시지 전송
            if channel_type == 'email':
                target_channel.send_message(
                    to=address,
                    subject=f"[작업 완료] Task {task_id}",
                    body=result
                )
                self.log(f"[외부채널 응답] Email 전송 완료 → {address}")
            elif channel_type == 'nostr':
                target_channel.send_message(
                    to=address,
                    subject="(IndieBiz 작업 완료)",
                    body=result
                )
                self.log(f"[외부채널 응답] Nostr 전송 완료 → {address[:20]}...")

        except Exception as e:
            self.log(f"[외부채널 응답] 전송 실패: {e}")

    def _make_channel_callback(self, channel):
        """채널별 콜백 함수 생성 (클로저 문제 해결)"""
        def callback(msg):
            self._process_channel_message(channel, msg)
        return callback
    
    def _process_channel_message(self, channel, msg):
        """
        채널로부터 받은 메시지 처리 (DB 통합)
        
        1. 파라미터 추출
        2. 보낸 사람 찾기/생성
        3. DB에서 히스토리 로드
        4. 메시지 DB 저장
        5. AI 처리
        6. 응답 DB 저장
        7. OutputRouter로 라우팅
        """
        subject = msg.get('subject', '(제목 없음)')
        from_addr = msg.get('from', '')
        
        # 시스템 메시지 필터링
        system_senders = [
            'mailer-daemon@',
            'postmaster@',
            'noreply@',
            'no-reply@'
        ]
        
        if any(sender in from_addr.lower() for sender in system_senders):
            self.log(f"시스템 메시지 무시: {subject} (from: {from_addr})")
            return
        
        self.log(f"새 메시지: {subject}")
        self.log(f"내용: {msg.get('body', '')[:100]}...")  # 내용 출력
        
        try:
            # 1. 파라미터 추출
            channel_type = channel.__class__.__name__
            
            if 'Gmail' in channel_type:
                content = msg.get('body', '')
                reply_to = from_addr
                contact_type = 'email'
            elif 'Nostr' in channel_type:
                content = msg.get('body', '')  # Nostr도 'body' 사용
                
                # NIP-18 마커 제거 ([//]: # (nip18) 등)
                if content.startswith('[//]:'):
                    lines = content.split('\n')
                    # 첫 줄이 마커면 제거
                    if lines and lines[0].strip().startswith('[//]'):
                        content = '\n'.join(lines[1:]).strip()
                
                reply_to = msg.get('from', '')  # 'from' 필드에 public_key(hex) 있음
                contact_type = 'nostr'
            else:
                self.log(f"알 수 없는 채널 타입: {channel_type}")
                return
            
            # Nostr는 hex를 npub으로 변환하여 표시
            if contact_type == 'nostr':
                try:
                    from pynostr.key import PublicKey
                    pubkey_obj = PublicKey(bytes.fromhex(from_addr))
                    from_display = pubkey_obj.bech32()
                    self.log(f"메시지 파라미터: from={from_display[:20]}... (hex={from_addr[:16]}...), reply_to={reply_to[:16]}...")
                except:
                    self.log(f"메시지 파라미터: from={from_addr}, reply_to={reply_to}")
            else:
                self.log(f"메시지 파라미터: from={from_addr}, reply_to={reply_to}")
            
            # 2. 보낸 사람 찾기/생성
            neighbor_id = self._get_or_create_neighbor(from_addr, contact_type)
            
            # 3. DB에서 히스토리 로드 (기본값 사용 - conversation_db.py에서 관리)
            raw_history = self.conversations.get_history_for_ai(neighbor_id)
            
            # 4. 규칙 + 히스토리 조합
            history = self._build_history_with_rules(raw_history)
            
            # 5. 수신 메시지 DB 저장
            self.conversations.receive_message(
                from_agent_id=neighbor_id,
                content=content,
                contact_type=contact_type
            )

            # ✅ 시스템 자동화: 외부 채널 메시지도 task 생성
            import uuid
            task_id = f"task_{uuid.uuid4().hex[:8]}"
            requester_info = f"{from_addr}@{contact_type}"

            try:
                self.conversations.db.create_task(
                    task_id=task_id,
                    requester=requester_info,
                    requester_channel=contact_type,  # 'email' or 'nostr'
                    original_request=content,
                    delegated_to=self.config.get('name', '')
                )
                self.log(f"[외부채널] task 자동 생성: {task_id} (채널: {contact_type})")
            except Exception as task_err:
                self.log(f"[외부채널] task 생성 실패: {task_err}")

            # task_id 및 채널 정보 설정
            set_current_task_id(task_id)
            clear_called_agent()

            # 6. AI 처리
            response = self.ai.process_message_with_history(
                content, from_addr, history, reply_to,
                task_id=task_id  # ✅ 워커 스레드에 task_id 전달
            )

            # call_agent 호출 여부 확인
            called_another_agent = did_call_agent()

            # 7. 응답 DB 저장
            self.conversations.send_message(
                to_agent_id=neighbor_id,
                content=response,
                contact_type=contact_type
            )

            # 8. 채널로 직접 응답 전송 (call_agent를 호출하지 않은 경우에만)
            # call_agent 호출 시에는 위임 결과가 나중에 _auto_report_result를 통해 전달됨
            if not called_another_agent:
                try:
                    if 'Gmail' in channel_type:
                        channel.send_message(
                            to=reply_to,
                            subject="Re: " + subject,
                            body=response
                        )
                        self.log(f"Gmail 응답 전송 완료 → {reply_to}")
                        # Task 완료 처리
                        self.conversations.db.complete_task(task_id, response[:500])
                    elif 'Nostr' in channel_type:
                        channel.send_message(
                            to=reply_to,
                            subject="(IndieBiz)",
                            body=response
                        )
                        self.log(f"Nostr 응답 전송 완료 → {reply_to[:16]}...")
                        # Task 완료 처리
                        self.conversations.db.complete_task(task_id, response[:500])
                except Exception as send_error:
                    self.log(f"응답 전송 실패: {send_error}")
            else:
                self.log(f"[외부채널] call_agent 호출됨 - 직접 응답 스킵, 위임 결과 대기")

            # 정리
            clear_current_task_id()
            clear_called_agent()
            
        except Exception as e:
            import traceback
            self.log(f"처리 실패: {e}")
            self.log(traceback.format_exc())
