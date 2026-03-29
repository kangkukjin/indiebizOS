"""
agent_runner.py - 에이전트 실행 엔진
IndieBiz OS Core

에이전트를 백그라운드에서 실행하고 AI 대화를 처리합니다.
비동기 메시지 큐를 통한 에이전트 간 통신 및 위임 체인을 지원합니다.
"""

import json
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from ai_agent import AIAgent
from conversation_db import ConversationDB, HISTORY_LIMIT_AGENT
from thread_context import (
    set_current_agent_id, set_current_agent_name, set_current_project_id,
    get_current_agent_id, get_current_agent_name, get_current_registry_key,
    set_current_task_id, get_current_task_id, clear_current_task_id,
    set_called_agent, did_call_agent, clear_called_agent,
    set_allowed_nodes
)


class AgentRunner:
    """에이전트 실행기 - 비동기 메시지 큐 및 위임 체인 지원"""

    # 클래스 변수 (모든 인스턴스가 공유)
    internal_messages: Dict[str, List[dict]] = {}  # agent_id -> [메시지 dict]
    agent_registry: Dict[str, 'AgentRunner'] = {}  # agent_id -> AgentRunner 인스턴스
    # RLock 사용: 같은 스레드에서 중첩 호출 시 데드락 방지
    # (예: 메시지 처리 중 call_agent 호출 시 다시 Lock 획득 필요한 경우)
    _lock = threading.RLock()

    def __init__(self, agent_config: dict, common_config: dict = None, delegated_from_system_ai: bool = False):
        self.config = agent_config
        self.common_config = common_config or {}
        self.delegated_from_system_ai = delegated_from_system_ai

        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.cancel_event = threading.Event()

        # AI 에이전트
        self.ai: Optional[AIAgent] = None

        # 채널 관리 (외부 에이전트용)
        self.channels: List = []
        self.processed_ids: set = set()

        # 프로젝트 정보
        self.project_path = Path(agent_config.get("_project_path", "."))
        self.project_id = agent_config.get("_project_id", "")

        # 대화 DB
        db_path = self.project_path / "conversations.db"
        self.db = ConversationDB(str(db_path))

        # 레지스트리에 등록 (스레드 안전)
        # 키 형식: {project_id}:{agent_id} - 프로젝트 간 충돌 방지
        agent_id = agent_config.get("id")
        if agent_id:
            registry_key = f"{self.project_id}:{agent_id}" if self.project_id else agent_id
            self.registry_key = registry_key  # stop()에서 사용
            with AgentRunner._lock:
                AgentRunner.agent_registry[registry_key] = self
                if registry_key not in AgentRunner.internal_messages:
                    AgentRunner.internal_messages[registry_key] = []
            print(f"[AgentRunner] {agent_config.get('name')} 레지스트리 등록됨 (key: {registry_key})")

    def start(self):
        """에이전트 시작"""
        if self.running:
            return

        self.running = True
        self.cancel_event.clear()

        # AI 에이전트 초기화
        self._init_ai()

        # 백그라운드 스레드 시작 (내부 메시지 폴링)
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

        print(f"[AgentRunner] {self.config.get('name')} 시작됨")

        # 에이전트 노드 캐시 무효화 (Phase 11)
        try:
            from node_registry import invalidate_agent_cache
            invalidate_agent_cache()
        except ImportError:
            pass

    def stop(self):
        """에이전트 중지"""
        self.running = False
        self.cancel_event.set()

        if self.thread:
            self.thread.join(timeout=5)

        # 레지스트리에서 제거
        registry_key = getattr(self, 'registry_key', None)
        if registry_key:
            with AgentRunner._lock:
                if registry_key in AgentRunner.agent_registry:
                    del AgentRunner.agent_registry[registry_key]
                if registry_key in AgentRunner.internal_messages:
                    del AgentRunner.internal_messages[registry_key]

        # 프로바이더 캐시 정리 (Gemini 컨텍스트 캐시 등)
        provider = getattr(self.ai, '_provider', None) if self.ai else None
        if provider and hasattr(provider, 'cleanup'):
            try:
                provider.cleanup()
            except Exception:
                pass

        # 에이전트 노드 캐시 무효화 (Phase 11)
        try:
            from node_registry import invalidate_agent_cache
            invalidate_agent_cache()
        except ImportError:
            pass

        print(f"[AgentRunner] {self.config.get('name')} 중지됨")

    def cancel(self):
        """현재 작업 취소"""
        self.cancel_event.set()

    def _init_ai(self):
        """AI 에이전트 초기화

        Phase 19: IBL-only 모드 — execute_ibl + 시스템 도구만 제공
        개별 도구 패키지(336개)를 로딩하지 않고, execute_ibl 하나로 모든 노드에 접근
        """
        ai_config = self.config.get("ai", {})
        agent_name = self.config.get("name", "에이전트")
        agent_id = self.config.get("id")

        # 역할 로드
        role_file = self.project_path / f"agent_{agent_name}_role.txt"
        role = ""
        if role_file.exists():
            role = role_file.read_text(encoding='utf-8')

        # 시스템 프롬프트 생성
        system_prompt = self._build_system_prompt(role)

        # IBL-only 도구 목록 구성
        tools = self._build_ibl_tools()

        # AIAgent 생성 (tools 명시 → 336개 로딩 방지)
        self.ai = AIAgent(
            ai_config=ai_config,
            system_prompt=system_prompt,
            agent_name=agent_name,
            agent_id=agent_id,
            project_path=str(self.project_path),
            tools=tools
        )

    def _build_system_prompt(self, role: str, consciousness_output: dict = None) -> str:
        """시스템 프롬프트 구성 (동적 조합)

        구조: base_prompt_v4.md + (조건부 위임 프롬프트) + IBL 환경
              + 의식 에이전트 출력 + 개별역할 + 영구메모
        Phase 16: 모든 에이전트가 ibl_only 모드로 통일
        """
        from prompt_builder import build_agent_prompt

        agent_name = self.config.get("name", "에이전트")

        # 1. 프로젝트 내 에이전트 수 파악
        agent_count = self._get_agent_count()

        # 2. Git 활성화 여부 (system 노드는 ALWAYS_ALLOWED이므로 .git 존재만 확인)
        git_enabled = (self.project_path / ".git").exists()

        # 3. 에이전트별 영구메모
        agent_notes = ""
        note_file = self.project_path / f"agent_{agent_name}_note.txt"
        if note_file.exists():
            agent_notes = note_file.read_text(encoding='utf-8').strip()

        # 시스템 AI 위임 여부 확인
        is_delegated_from_system_ai = self.delegated_from_system_ai
        if not is_delegated_from_system_ai:
            try:
                pending = self.db.get_pending_tasks(delegated_to=agent_name)
                is_delegated_from_system_ai = any(
                    t.get('requester_channel') == 'system_ai' for t in pending
                )
            except Exception:
                pass

        # 4. allowed_nodes (IBL 노드 접근 제어)
        allowed_nodes_config = self.config.get("allowed_nodes")

        # 동적 프롬프트 빌드 (Phase 16: ibl_only 단일 경로)
        return build_agent_prompt(
            agent_name=agent_name,
            role=role,
            agent_count=agent_count,
            agent_notes=agent_notes,
            git_enabled=git_enabled,
            delegated_from_system_ai=is_delegated_from_system_ai,
            ibl_only=True,
            allowed_nodes=allowed_nodes_config,
            project_path=str(self.project_path),
            agent_id=self.config.get("id"),
            consciousness_output=consciousness_output
        )

    def _run_consciousness(self, user_message: str, history: list) -> dict:
        """의식 에이전트 실행 — 메타 판단

        사용자 메시지와 히스토리를 분석하여 프롬프트 최적화 지침을 반환합니다.
        실패 시 None을 반환하고, 기존 방식으로 폴백합니다.

        Returns:
            의식 에이전트 출력 dict 또는 None
        """
        try:
            from consciousness_agent import (
                get_consciousness_agent,
                get_ibl_node_summary,
                get_guide_list,
                get_world_pulse_text,
            )

            agent = get_consciousness_agent()
            if not agent.is_ready:
                return None

            allowed_nodes = self.config.get("allowed_nodes")
            agent_name = self.config.get("name", "")

            # 역할 전문 로드 (잘리지 않고 전체 전달 — self_awareness 판단용)
            role_file = self.project_path / f"agent_{agent_name}_role.txt"
            agent_role = ""
            if role_file.exists():
                agent_role = role_file.read_text(encoding='utf-8').strip()

            # 영구메모 로드
            agent_notes = self.config.get("notes", "")

            result = agent.process(
                user_message=user_message,
                history=history,
                ibl_node_summary=get_ibl_node_summary(allowed_nodes, user_message=user_message),
                guide_list=get_guide_list(user_message),
                world_pulse=get_world_pulse_text(),
                agent_name=agent_name,
                agent_role=agent_role,
                agent_notes=agent_notes,
            )

            if result:
                self._log(f"[의식] 태스크: {result.get('task_framing', '')[:60]}")
            return result

        except Exception as e:
            self._log(f"[의식] 실행 실패 (폴백): {e}")
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

    def _get_agent_count(self) -> int:
        """프로젝트 내 활성 에이전트 수 반환"""
        try:
            import yaml
            agents_file = self.project_path / "agents.yaml"
            if agents_file.exists():
                with open(agents_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    agents = data.get("agents", [])
                    return sum(1 for a in agents if a.get("active", True))
        except Exception:
            pass
        return 1

    def _build_execute_ibl_tool(self) -> Optional[dict]:
        """ibl_nodes.yaml에서 execute_ibl 도구 정의를 동적 생성.
        tool_loader.build_execute_ibl_tool() 공유 함수 사용.
        에이전트의 allowed_nodes 설정을 반영하여 허용된 노드만 포함.
        """
        from tool_loader import build_execute_ibl_tool
        allowed_nodes = self.config.get("allowed_nodes")
        return build_execute_ibl_tool(allowed_nodes=allowed_nodes)

    def _build_ibl_tools(self) -> list:
        """에이전트 도구 구성: IBL + 범용 언어(Python, Node.js, Shell)

        에이전트는 두 종류의 도구를 가진다:
        1. execute_ibl - 인디비즈 고유 기능 (전문 용어/지름길)
        2. execute_python, execute_node, run_command - 범용 프로그래밍 언어

        IBL은 인디비즈 도메인 특화 언어이고,
        Python/Node.js/Shell은 복잡한 로직, 데이터 처리, 워크플로우 구성에 사용.
        """
        import json as _json

        tools = []
        pkg_base = Path(__file__).parent.parent / "data" / "packages" / "installed" / "tools"

        # 1) IBL 도구 — ibl_nodes.yaml에서 description 동적 생성
        ibl_tool = self._build_execute_ibl_tool()
        if ibl_tool:
            tools.append(ibl_tool)

        # 2) 범용 언어 도구 (일상 언어)
        lang_tools = [
            ("python-exec", "execute_python"),
            ("nodejs", "execute_node"),
            ("system_essentials", "run_command"),
            # 에이전트 인지 도구 — IBL 경유 불가 (파라미터 구조 불일치)
            ("system_essentials", "todo_write"),
            ("system_essentials", "ask_user_question"),
            ("system_essentials", "enter_plan_mode"),
            ("system_essentials", "exit_plan_mode"),
        ]
        for pkg_id, tool_name in lang_tools:
            tool_json = pkg_base / pkg_id / "tool.json"
            if tool_json.exists():
                try:
                    with open(tool_json, 'r', encoding='utf-8') as f:
                        pkg_data = _json.load(f)
                    for tool_def in pkg_data.get("tools", []):
                        if tool_def.get("name") == tool_name:
                            tools.append(tool_def)
                            break
                except Exception as e:
                    print(f"[AgentRunner] {pkg_id}/tool.json 로드 실패: {e}")

        # 3) 가이드 검색 도구 (복잡한 작업 전에 매뉴얼 찾기)
        tools.append({
            "name": "read_guide",
            "description": "가이드 파일을 읽는 도구. 검색, 투자 분석, 동영상 제작, 웹사이트 빌드 등 복잡한 작업의 단계별 가이드가 저장되어 있다. 작업 전에 이 도구로 가이드를 읽어라. 예: query='검색'이면 검색 가이드를 읽음.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "검색 키워드 (예: 동영상, 투자분석, 홈페이지, 음악)"
                    },
                    "read": {
                        "type": "boolean",
                        "description": "true(기본): 가이드 내용까지 반환, false: 목록만 반환"
                    }
                },
                "required": ["query"]
            }
        })

        print(f"[AgentRunner] {self.config.get('name')}: IBL + 범용언어 모드 (도구 {len(tools)}개)")
        return tools

    def _get_available_tools(self) -> list:
        """에이전트가 사용할 수 있는 도구 이름 목록 반환

        IBL(도메인 특화) + 범용 프로그래밍 언어 + 가이드 검색
        """
        return ["execute_ibl", "execute_python", "execute_node", "run_command", "read_guide",
                "todo_write", "ask_user_question", "enter_plan_mode", "exit_plan_mode"]

    def augment_with_ibl_references(self, user_message: str) -> str:
        """사용자 메시지에 IBL 참조 용례를 주입 (RAG)

        유사한 과거 IBL 용례를 검색하여 AI가 참고할 수 있도록 메시지 앞에 추가.
        실패 시 원본 메시지 그대로 반환 (graceful degradation).
        """
        try:
            from ibl_usage_rag import IBLUsageRAG
            rag = IBLUsageRAG()
            allowed_nodes = self.config.get("allowed_nodes")
            if allowed_nodes:
                from ibl_access import resolve_allowed_nodes
                allowed_set = resolve_allowed_nodes(allowed_nodes)
            else:
                allowed_set = None
            return rag.inject_references(user_message, allowed_set)
        except Exception:
            return user_message

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

                # 무의식 에이전트 — 실행형/판���형 분류 (반사 신경)
                request_type = self._classify_request(content)
                self._log(f"[무의식] 분류: {request_type}")

                # 판단형만 의식 에이전트 실행
                consciousness_output = None
                if request_type == "THINK":
                    consciousness_output = self._run_consciousness(content, history)
                if consciousness_output:
                    # 시스템 프롬프트 재구성 (의식 에이전트 출력 반영)
                    role_file = self.project_path / f"agent_{agent_name}_role.txt"
                    role = role_file.read_text(encoding='utf-8') if role_file.exists() else ""
                    new_prompt = self._build_system_prompt(role, consciousness_output)
                    self.ai.system_prompt = new_prompt
                    if self.ai._provider:
                        self.ai._provider.system_prompt = new_prompt

                    # 히스토리 편집 (의식 에이전트 판단에 따라)
                    history = self._apply_consciousness_to_history(history, consciousness_output)

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
                                max_rounds=_goal_cfg.get("max_rounds", 3)
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
                    # IBL 용례 참조 주입 (RAG)
                    ai_message = self.augment_with_ibl_references(content)
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

                                # ✅ 병렬 위임 수집 모드: 동시에 2개 이상 위임이 진행 중일 때만
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

    # ============ 클래스 메서드: 에이전트 검색 ============

    @classmethod
    def get_agent_by_name(cls, name: str, project_id: str = None) -> Optional['AgentRunner']:
        """이름으로 에이전트 찾기 (스레드 안전)

        Args:
            name: 에이전트 이름
            project_id: 프로젝트 ID (지정하면 해당 프로젝트 내에서만 검색)
        """
        with cls._lock:
            for registry_key, runner in cls.agent_registry.items():
                if runner.config.get('name') == name:
                    # 프로젝트 ID가 지정되면 같은 프로젝트만 반환
                    if project_id and runner.project_id != project_id:
                        continue
                    return runner
        return None

    @classmethod
    def get_agent_by_id(cls, agent_id: str, project_id: str = None) -> Optional['AgentRunner']:
        """ID로 에이전트 찾기 (스레드 안전)

        Args:
            agent_id: 에이전트 ID
            project_id: 프로젝트 ID (지정하면 해당 프로젝트의 레지스트리 키로 검색)
        """
        with cls._lock:
            # 프로젝트 ID가 있으면 복합 키로 검색
            if project_id:
                registry_key = f"{project_id}:{agent_id}"
                return cls.agent_registry.get(registry_key)
            # 없으면 agent_id만으로 검색 (하위 호환)
            return cls.agent_registry.get(agent_id)

    @classmethod
    def get_all_agent_names(cls) -> List[str]:
        """모든 에이전트 이름 목록 (스레드 안전)"""
        with cls._lock:
            return [runner.config.get('name', '') for runner in cls.agent_registry.values()]

    @classmethod
    def get_all_agents(cls) -> List[dict]:
        """모든 에이전트 정보 목록 (스레드 안전)"""
        with cls._lock:
            result = []
            for agent_id, runner in cls.agent_registry.items():
                result.append({
                    "id": agent_id,
                    "name": runner.config.get("name", ""),
                    "type": runner.config.get("type", "internal"),
                    "running": runner.running
                })
            return result

    @classmethod
    def send_message(cls, to_agent_id: str, message: str, from_agent: str = "system",
                     task_id: str = None) -> bool:
        """
        에이전트에게 메시지 전송 (비동기)

        Args:
            to_agent_id: 대상 에이전트 ID
            message: 전달할 메시지
            from_agent: 발신 에이전트 이름
            task_id: 연관된 태스크 ID

        Returns:
            성공 여부
        """
        with cls._lock:
            if to_agent_id not in cls.agent_registry:
                return False

            msg_dict = {
                'content': message,
                'from_agent': from_agent,
                'task_id': task_id,
                'timestamp': datetime.now().isoformat()
            }

            if to_agent_id not in cls.internal_messages:
                cls.internal_messages[to_agent_id] = []

            cls.internal_messages[to_agent_id].append(msg_dict)
            print(f"[AgentRunner] 메시지 큐 추가: {from_agent} → {to_agent_id}")
            return True

    @classmethod
    def send_message_by_name(cls, to_agent_name: str, message: str, from_agent: str = "system",
                             task_id: str = None, project_id: str = None) -> bool:
        """
        에이전트 이름으로 메시지 전송 (비동기)

        Args:
            to_agent_name: 대상 에이전트 이름
            message: 전달할 메시지
            from_agent: 발신 에이전트 이름
            task_id: 연관된 태스크 ID
            project_id: 프로젝트 ID (지정하면 해당 프로젝트 내에서만 검색)

        Returns:
            성공 여부
        """
        target = cls.get_agent_by_name(to_agent_name, project_id=project_id)
        if not target:
            return False

        registry_key = getattr(target, 'registry_key', None)
        if not registry_key:
            return False

        return cls.send_message(registry_key, message, from_agent, task_id)

    # ============ Goal 실행 (Phase 26) ============

    def _get_goals_db(self):
        """Goal 관리용 ConversationDB 인스턴스"""
        from conversation_db import ConversationDB
        db_path = os.path.join(self.project_path, "conversations.db")
        return ConversationDB(db_path)

    def execute_goal(self, goal_data: dict) -> dict:
        """
        Goal Block 실행 (파서 출력을 받아 Goal 생성 → 활성화 → 판단 루프)

        Args:
            goal_data: 파싱된 goal dict (_goal=True, name, success_condition, ...)

        Returns:
            {"goal_id": "...", "status": "...", "message": "..."}
        """
        import uuid
        from goal_evaluator import (
            estimate_goal_cost, format_cost_confirmation, check_termination
        )

        db = self._get_goals_db()
        goal_id = f"goal_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        # 1. Goal 생성
        db.create_goal(goal_id, goal_data)

        # 2. 비용 산출
        model_name = self.config.get("model", "default")
        estimated_cost = estimate_goal_cost(goal_data, model_name)

        # 3. 사용자 확인 (every/schedule이 있는 장기 Goal만)
        needs_confirmation = (
            goal_data.get("every") or goal_data.get("schedule") or
            estimated_cost > 1.0 or
            goal_data.get("max_rounds", 0) > 10
        )

        if needs_confirmation:
            msg = format_cost_confirmation(
                goal_data.get("name", ""),
                estimated_cost,
                goal_data.get("max_rounds", 100),
                goal_data.get("every")
            )
            self._log(f"[Goal] 사용자 확인 필요: {msg}")
            # 확인을 기다리지 않고 pending 상태로 반환
            # (실제 확인은 GUI/API에서 approve_goal 호출)
            return {
                "goal_id": goal_id,
                "status": "pending_approval",
                "estimated_cost": estimated_cost,
                "message": msg
            }

        # 4. 즉시 실행 (단순 Goal)
        return self._activate_and_run_goal(goal_id)

    def approve_goal(self, goal_id: str) -> dict:
        """
        사용자 승인 후 Goal 활성화

        pending_approval 상태의 Goal을 승인하여 실행/스케줄링한다.
        GUI/API에서 호출된다.
        """
        db = self._get_goals_db()
        goal = db.get_goal(goal_id)
        if not goal:
            return {"error": f"Goal not found: {goal_id}"}

        if goal['status'] != 'pending':
            return {"error": f"Goal is not pending: {goal['status']}"}

        return self._activate_and_run_goal(goal_id)

    def _activate_and_run_goal(self, goal_id: str) -> dict:
        """Goal을 active로 전환하고 판단 루프 실행 (또는 스케줄 등록)"""
        from goal_evaluator import check_termination

        db = self._get_goals_db()
        goal = db.get_goal(goal_id)
        if not goal:
            return {"error": f"Goal not found: {goal_id}"}

        # active로 전환
        db.update_goal_status(goal_id, "active")
        self._log(f"[Goal] 활성화: {goal['name']} ({goal_id})")

        # every/schedule이 있는 Goal은 calendar_manager에 등록
        every = goal.get('every_frequency')
        schedule_at = goal.get('schedule_at')

        if every or schedule_at:
            schedule_result = self._register_goal_schedule(goal_id, goal)
            if schedule_result.get("error"):
                self._log(f"[Goal] 스케줄 등록 실패: {schedule_result['error']}")
            else:
                self._log(f"[Goal] 스케줄 등록: {schedule_result.get('event_id', '')}")

        # 즉시 첫 라운드 실행 (schedule-only Goal 제외)
        if schedule_at and not every:
            # 일회성 예약: 즉시 실행하지 않고 스케줄 대기
            return {
                "goal_id": goal_id,
                "status": "active",
                "message": f"Goal 예약됨: {schedule_at}에 실행 예정"
            }

        # 판단 루프 실행
        result = self._judgment_loop(goal_id)
        return result

    def _register_goal_schedule(self, goal_id: str, goal: dict) -> dict:
        """
        Goal의 every/schedule을 calendar_manager에 등록

        Args:
            goal_id: 목표 ID
            goal: goal dict

        Returns:
            {"event_id": "...", "message": "..."} 또는 {"error": "..."}
        """
        try:
            from calendar_manager import get_calendar_manager

            cm = get_calendar_manager(log_callback=lambda msg: self._log(f"[Goal Schedule] {msg}"))

            every = goal.get('every_frequency', '')
            schedule_at = goal.get('schedule_at', '')
            goal_name = goal.get('name', 'unnamed')

            # every 파싱: "매일 08:00", "매주 월요일 09:00", "daily 08:00" 등
            repeat_type, event_time, weekdays = self._parse_every_frequency(every)

            if schedule_at and not every:
                # 일회성 예약
                result = cm.add_event(
                    title=f"[Goal] {goal_name}",
                    event_date=schedule_at.split(" ")[0] if " " in schedule_at else schedule_at,
                    event_type="goal",
                    repeat="none",
                    event_time=schedule_at.split(" ")[1] if " " in schedule_at else "09:00",
                    action="run_goal",
                    action_params={"goal_id": goal_id},
                    description=f"Goal 예약 실행: {goal_name}"
                )
            else:
                # 반복 실행
                result = cm.add_event(
                    title=f"[Goal] {goal_name}",
                    event_type="goal",
                    repeat=repeat_type,
                    event_time=event_time,
                    weekdays=weekdays,
                    action="run_goal",
                    action_params={"goal_id": goal_id},
                    description=f"Goal 반복 실행: {goal_name} ({every})"
                )

            return result if isinstance(result, dict) else {"event_id": str(result)}
        except Exception as e:
            self._log(f"[Goal] 스케줄 등록 오류: {e}")
            return {"error": str(e)}

    def _parse_every_frequency(self, every: str) -> tuple:
        """
        every 문자열을 calendar_manager 파라미터로 변환

        Args:
            every: "매일 08:00", "매주 월요일 09:00", "daily 08:00", "매시간" 등

        Returns:
            (repeat_type, event_time, weekdays)
        """
        import re

        if not every:
            return "daily", "09:00", None

        every_lower = every.lower().strip()

        # 시간 추출
        time_match = re.search(r'(\d{1,2}:\d{2})', every)
        event_time = time_match.group(1) if time_match else "09:00"

        # 요일 매핑
        day_map = {
            '월': 0, '화': 1, '수': 2, '목': 3, '금': 4, '토': 5, '일': 6,
            'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6,
            '월요일': 0, '화요일': 1, '수요일': 2, '목요일': 3,
            '금요일': 4, '토요일': 5, '일요일': 6,
        }

        weekdays = None

        if '매시간' in every or 'hourly' in every_lower:
            return "hourly", event_time, None
        elif '매일' in every or 'daily' in every_lower or '매일' in every:
            return "daily", event_time, None
        elif '매주' in every or 'weekly' in every_lower:
            # 요일 추출
            for day_name, day_num in day_map.items():
                if day_name in every:
                    weekdays = [day_num]
                    break
            return "weekly", event_time, weekdays or [0]  # 기본 월요일
        elif '매월' in every or 'monthly' in every_lower:
            return "monthly", event_time, None

        return "daily", event_time, None

    def _judgment_loop(self, goal_id: str) -> dict:
        """
        판단 루프 실행

        1. 종료 조건 체크 (until > deadline > max_rounds/max_cost)
        2. success_condition 평가 (AI 판단)
        3. strategy 내 조건 평가 (sense 노드 실행)
        4. IBL 생성 → 실행 → 결과 기록
        5. 반복
        """
        from goal_evaluator import check_termination
        from ibl_engine import execute_ibl

        db = self._get_goals_db()
        accumulated_results = []  # 라운드별 결과 누적 (AI 판단용 컨텍스트)

        while self.running:
            goal = db.get_goal(goal_id)
            if not goal or goal['status'] != 'active':
                break

            # 종료 조건 체크
            termination = check_termination(goal)
            if termination:
                if termination == "expired":
                    db.update_goal_status(goal_id, "expired")
                else:
                    db.update_goal_status(goal_id, "limit_reached")
                self._log(f"[Goal] 종료: {goal['name']} - {termination}")
                return self._report_goal_result(goal_id, termination)

            # 다음 라운드 실행
            round_num = goal['current_round'] + 1
            self._log(f"[Goal] 라운드 {round_num}/{goal['max_rounds']}: {goal['name']}")

            # success_condition 평가 (라운드 2 이상부터, 누적 결과가 있을 때)
            if round_num > 1 and accumulated_results and goal.get('success_condition'):
                achieved, judgment = self._evaluate_success_condition(goal, accumulated_results)
                self._log(f"[Goal] success_condition 평가: achieved={achieved}")
                if achieved:
                    db.update_goal_status(goal_id, "achieved")
                    self._log(f"[Goal] 달성: {goal['name']}")
                    return self._report_goal_result(goal_id, "achieved")

            # strategy가 있으면 조건에 따라 분기
            strategy = goal.get('strategy')
            if strategy and isinstance(strategy, dict):
                action = self._resolve_strategy(strategy, goal)
            else:
                action = None

            # IBL 실행
            round_cost = 0.0
            round_result = ""

            if action and isinstance(action, dict) and action.get("_node"):
                # 직접 실행 가능한 IBL step
                try:
                    result = execute_ibl(action, self.project_path, self.config.get("id", ""))
                    round_result = str(result)[:500] if result else "실행 완료"
                    round_cost = self._estimate_action_cost(action)
                except Exception as e:
                    round_result = f"실행 오류: {str(e)}"
                    round_cost = 0.005
            elif action and isinstance(action, dict) and action.get("_goal"):
                # 중첩 Goal (strategy 분기에서 Goal이 나온 경우)
                round_result = f"하위 Goal 생성: {action.get('name', 'unnamed')}"
                round_cost = 0.001
            else:
                # AI에게 판단 위임: success_condition 달성을 위한 IBL 생성 + 실행
                ai_result, ai_cost = self._ai_generate_and_execute(goal, accumulated_results)
                round_result = ai_result
                round_cost = ai_cost

            accumulated_results.append({
                "round": round_num,
                "result": round_result[:300]
            })
            # 최근 10개만 유지 (컨텍스트 크기 제한)
            if len(accumulated_results) > 10:
                accumulated_results = accumulated_results[-10:]

            # 비용 산출
            judgment_cost = self._estimate_judgment_cost()
            total_round_cost = round_cost + judgment_cost

            # 라운드 결과 기록
            db.add_goal_round(goal_id, round_num, total_round_cost, round_result)

            # 빈도 실행 Goal이면 이 라운드 후 대기 (다음 every 주기)
            if goal.get('every_frequency'):
                self._log(f"[Goal] 라운드 완료, 다음 주기 대기: {goal['every_frequency']}")
                return {
                    "goal_id": goal_id,
                    "status": "active",
                    "round": round_num,
                    "result": round_result,
                    "message": f"라운드 {round_num} 완료. 다음 실행: {goal['every_frequency']}"
                }

        # 루프 종료 (running=False 등)
        goal = db.get_goal(goal_id)
        return {
            "goal_id": goal_id,
            "status": goal.get("status", "unknown") if goal else "unknown",
            "message": "판단 루프 종료"
        }

    def _resolve_strategy(self, strategy: dict, goal: dict = None) -> Optional[dict]:
        """
        strategy 내 조건/case 평가하여 실행할 action 반환

        실제 sense 노드를 실행하여 조건을 평가한다.

        Args:
            strategy: _condition 또는 _case dict
            goal: 현재 goal dict (컨텍스트용)

        Returns:
            실행할 action dict 또는 None
        """
        from goal_evaluator import select_case_branch
        from ibl_engine import execute_ibl
        import re

        if strategy.get("_condition"):
            # if/else 조건문 — sense 실행 후 조건 평가
            for branch in strategy.get("branches", []):
                condition = branch.get("condition")
                if condition is None:
                    # else 분기
                    return branch.get("action")

                # 조건 파싱: "sense:field < 100" 형태
                sense_value = self._execute_condition_sense(condition)
                if sense_value is not None:
                    # 비교 연산자 추출 및 평가
                    if self._evaluate_condition_expr(condition, sense_value):
                        return branch.get("action")
                else:
                    # sense 실행 실패 시 다음 분기로
                    self._log(f"[Goal] 조건 평가 실패, 건너뜀: {condition}")
                    continue

            return None

        elif strategy.get("_case"):
            # case문 — sense 노드 실행 후 분기 선택
            source = strategy.get("source", "")
            branches = strategy.get("branches", [])
            default = strategy.get("default")

            # source에서 sense 값 가져오기
            sense_value = self._execute_sense_source(source)

            if sense_value is not None:
                result = select_case_branch(sense_value, branches, default)
                if result:
                    return result

            # sense 실패 시 default
            return default

        return None

    def _execute_condition_sense(self, condition: str) -> Any:
        """
        조건문에서 sense 부분을 실행하여 값 가져오기

        Args:
            condition: "sense:kospi < 2400", "sense:weather == '비'" 등

        Returns:
            sense 실행 결과 값 또는 None
        """
        import re
        from ibl_engine import execute_ibl

        # "sense:field" 부분 추출
        match = re.match(r'(sense:\w+)', condition)
        if not match:
            return None

        sense_ref = match.group(1)
        parts = sense_ref.split(":")
        if len(parts) != 2:
            return None

        node, action = parts[0], parts[1]

        try:
            step = {"_node": node, "action": action, "params": {}}
            result = execute_ibl(step, self.project_path, self.config.get("id", ""))

            # 결과에서 핵심 값 추출
            if isinstance(result, dict):
                return result.get("value", result.get("result", str(result)))
            return result
        except Exception as e:
            self._log(f"[Goal] sense 실행 오류: {sense_ref} - {e}")
            return None

    def _evaluate_condition_expr(self, condition: str, sense_value: Any) -> bool:
        """
        조건 표현식 평가

        Args:
            condition: "sense:kospi < 2400"
            sense_value: sense 실행 결과

        Returns:
            조건 충족 여부
        """
        import re

        # 연산자와 비교값 추출: "sense:xxx OP VALUE"
        match = re.search(r'(==|!=|>=|<=|>|<)\s*(.+)$', condition)
        if not match:
            # 연산자 없으면 truthy 판단
            return bool(sense_value)

        op = match.group(1)
        compare_raw = match.group(2).strip().strip("'\"")

        try:
            # 숫자 비교 시도
            sense_num = float(sense_value)
            compare_num = float(compare_raw)

            if op == "==": return sense_num == compare_num
            if op == "!=": return sense_num != compare_num
            if op == ">":  return sense_num > compare_num
            if op == ">=": return sense_num >= compare_num
            if op == "<":  return sense_num < compare_num
            if op == "<=": return sense_num <= compare_num
        except (ValueError, TypeError):
            # 문자열 비교
            sense_str = str(sense_value)
            if op == "==": return sense_str == compare_raw
            if op == "!=": return sense_str != compare_raw

        return False

    def _execute_sense_source(self, source: str) -> Any:
        """
        case문의 source (예: "sense:market_status")에서 값 가져오기

        Args:
            source: "sense:field" 형태

        Returns:
            sense 결과 값 또는 None
        """
        from ibl_engine import execute_ibl

        parts = source.split(":")
        if len(parts) != 2:
            return None

        node, action = parts[0], parts[1]

        try:
            step = {"_node": node, "action": action, "params": {}}
            result = execute_ibl(step, self.project_path, self.config.get("id", ""))

            if isinstance(result, dict):
                return result.get("value", result.get("result", str(result)))
            return result
        except Exception as e:
            self._log(f"[Goal] sense source 실행 오류: {source} - {e}")
            return None

    def _evaluate_success_condition(self, goal: dict, accumulated_results: list) -> tuple:
        """
        AI를 사용하여 success_condition 달성 여부 판단

        Args:
            goal: 현재 goal dict
            accumulated_results: 지금까지 라운드 결과 목록

        Returns:
            (achieved: bool, judgment: str)
        """
        if not self.ai:
            return False, "AI 미초기화"

        success_condition = goal.get('success_condition', '')
        goal_name = goal.get('name', '')

        # 최근 결과를 요약
        results_summary = "\n".join([
            f"라운드 {r['round']}: {r['result']}"
            for r in accumulated_results[-5:]  # 최근 5개
        ])

        prompt = (
            f"당신은 목표 달성 여부를 판단하는 평가자입니다.\n\n"
            f"목표: {goal_name}\n"
            f"달성 조건: {success_condition}\n\n"
            f"지금까지의 실행 결과:\n{results_summary}\n\n"
            f"위 결과를 바탕으로 달성 조건이 충족되었는지 판단하세요.\n"
            f"반드시 첫 줄에 ACHIEVED 또는 NOT_ACHIEVED 중 하나만 적고,\n"
            f"둘째 줄부터 간단한 판단 근거를 적으세요."
        )

        try:
            response = self.ai.process_message_with_history(
                message_content=prompt,
                history=[],
                task_id=f"goal_eval_{goal.get('goal_id', '')}"
            )

            first_line = response.strip().split('\n')[0].strip().upper()
            achieved = "ACHIEVED" in first_line and "NOT" not in first_line
            return achieved, response
        except Exception as e:
            self._log(f"[Goal] success_condition 평가 오류: {e}")
            return False, str(e)

    def _ai_generate_and_execute(self, goal: dict, accumulated_results: list) -> tuple:
        """
        AI에게 목표 달성을 위한 IBL을 생성하게 하고 실행

        Args:
            goal: 현재 goal dict
            accumulated_results: 지금까지 라운드 결과 목록

        Returns:
            (result_text: str, cost: float)
        """
        from ibl_parser import parse
        from ibl_engine import execute_ibl

        if not self.ai:
            return "AI 미초기화", 0.0

        goal_name = goal.get('name', '')
        success_condition = goal.get('success_condition', '')
        current_round = goal.get('current_round', 0)
        max_rounds = goal.get('max_rounds', 100)

        # 이전 결과 요약
        prev_summary = ""
        if accumulated_results:
            prev_summary = "\n".join([
                f"라운드 {r['round']}: {r['result']}"
                for r in accumulated_results[-3:]
            ])
            prev_summary = f"\n이전 실행 결과:\n{prev_summary}\n"

        prompt = (
            f"당신은 목표를 달성하기 위해 IBL 액션을 선택하는 에이전트입니다.\n\n"
            f"목표: {goal_name}\n"
            f"달성 조건: {success_condition}\n"
            f"현재 라운드: {current_round + 1}/{max_rounds}\n"
            f"{prev_summary}\n"
            f"목표 달성을 위해 지금 실행해야 할 IBL 액션을 하나 작성하세요.\n"
            f"IBL 형식: [node:action]{{param: \"value\"}}\n"
            f"반드시 실행 가능한 IBL 코드 한 줄만 작성하세요. 설명은 불필요합니다."
        )

        try:
            response = self.ai.process_message_with_history(
                message_content=prompt,
                history=[],
                task_id=f"goal_act_{goal.get('goal_id', '')}"
            )

            # AI 응답에서 IBL 추출 (정규식으로 [node:action]{...} 패턴 찾기)
            import re
            ibl_match = re.search(r'\[[\w]+:[\w]+\]\{[^}]*\}', response)
            if not ibl_match:
                # 간단한 형태도 시도: [node:action]
                ibl_match = re.search(r'\[[\w]+:[\w]+\]', response)

            if ibl_match:
                ibl_code = ibl_match.group(0)
                self._log(f"[Goal] AI 생성 IBL: {ibl_code}")

                # 파싱 + 실행
                parsed = parse(ibl_code)
                if parsed:
                    step = parsed[0]
                    result = execute_ibl(step, self.project_path, self.config.get("id", ""))
                    result_text = str(result)[:500] if result else "실행 완료"
                    cost = self._estimate_action_cost(step)
                    return f"IBL: {ibl_code} → {result_text}", cost + 0.02
                else:
                    return f"IBL 파싱 실패: {ibl_code}", 0.02
            else:
                # IBL 코드 없이 텍스트 응답만 온 경우
                return f"AI 응답 (IBL 미포함): {response[:300]}", 0.02

        except Exception as e:
            self._log(f"[Goal] AI 생성/실행 오류: {e}")
            return f"AI 생성 오류: {str(e)}", 0.02

    def _estimate_action_cost(self, step: dict) -> float:
        """
        IBL 액션 실행 비용 추정 (토큰 기반)

        Args:
            step: 파싱된 IBL step dict

        Returns:
            추정 비용 (USD)
        """
        from goal_evaluator import MODEL_COSTS, TOKENS_PER_ACTION

        model_name = self.config.get("model", "default") if hasattr(self, 'config') else "default"
        costs = MODEL_COSTS.get(model_name, MODEL_COSTS.get("default", {"input_per_1k": 0.003, "output_per_1k": 0.015}))

        cost = (
            (TOKENS_PER_ACTION["input"] * costs["input_per_1k"] / 1000) +
            (TOKENS_PER_ACTION["output"] * costs["output_per_1k"] / 1000)
        )
        return round(cost, 6)

    def _estimate_judgment_cost(self) -> float:
        """
        판단 루프 자체 비용 추정 (success_condition 평가)

        Returns:
            추정 비용 (USD)
        """
        from goal_evaluator import MODEL_COSTS, TOKENS_PER_JUDGMENT

        model_name = self.config.get("model", "default") if hasattr(self, 'config') else "default"
        costs = MODEL_COSTS.get(model_name, MODEL_COSTS.get("default", {"input_per_1k": 0.003, "output_per_1k": 0.015}))

        cost = (
            (TOKENS_PER_JUDGMENT["input"] * costs["input_per_1k"] / 1000) +
            (TOKENS_PER_JUDGMENT["output"] * costs["output_per_1k"] / 1000)
        )
        return round(cost, 6)

    def _report_goal_result(self, goal_id: str, reason: str) -> dict:
        """Goal 결과 보고"""
        db = self._get_goals_db()
        goal = db.get_goal(goal_id)
        if not goal:
            return {"error": f"Goal not found: {goal_id}"}

        rounds_data = goal.get("rounds_data", [])
        last_rounds = rounds_data[-3:] if isinstance(rounds_data, list) else []

        return {
            "goal_id": goal_id,
            "name": goal.get("name"),
            "status": goal.get("status"),
            "reason": reason,
            "total_rounds": goal.get("current_round", 0),
            "total_cost": f"${goal.get('cumulative_cost', 0):.2f}",
            "last_rounds": last_rounds,
            "message": f"목표 '{goal.get('name')}' {reason}으로 종료됨. "
                       f"{goal.get('current_round', 0)}라운드 실행, "
                       f"비용 ${goal.get('cumulative_cost', 0):.2f}"
        }

    def recover_active_goals(self):
        """
        시스템 재시작 시 활성 Goal 복구

        - every가 있는 Goal: 다음 주기를 기다림 (현재 라운드 포기)
        - every가 없는 일회성 Goal: 재개
        """
        try:
            db = self._get_goals_db()
            active_goals = db.list_goals(status="active")

            for goal in active_goals:
                if goal.get("every_frequency"):
                    self._log(f"[Goal 복구] '{goal['name']}' 다음 스케줄 대기")
                else:
                    self._log(f"[Goal 복구] '{goal['name']}' 재개 예정")
                    # 일회성 Goal은 다음 루프에서 재개
        except Exception as e:
            self._log(f"[Goal 복구] 오류: {e}")

    # ============================================================
    # 무의식 에이전트 — 실행형/판단형 분류 (반사 신경)
    # ============================================================

    def _classify_request(self, user_message: str) -> str:
        """사용자 요청을 실행형(EXECUTE) 또는 판단형(THINK)으로 분류한다.

        무의식 에이전트 — 의식 에이전트를 호출하기 전의 반사 신경.
        실행형은 의식/평가 루프를 타지 않고 바로 실행된다.
        """
        try:
            from consciousness_agent import lightweight_ai_call, get_unconscious_prompt

            system_prompt = get_unconscious_prompt()
            response = lightweight_ai_call(user_message, system_prompt=system_prompt)

            if response is None:
                return "THINK"  # AI 미준비 시 안전하게 판단형으로

            result = response.strip().upper()
            if "EXECUTE" in result:
                return "EXECUTE"
            return "THINK"

        except Exception as e:
            self._log(f"[무의식] 분류 실패: {e}")
            return "THINK"  # 실패 시 안전하게 판단형으로

    # ============================================================
    # Goal 평가 루프 — 의식 에이전트의 달성 기준 기반 자동 평가
    # ============================================================

    def _extract_achievement_criteria(self, consciousness_output: dict) -> Optional[str]:
        """의식 에이전트 출력에서 달성 기준을 추출한다.

        1차: achievement_criteria 필드 (별도 필드)
        2차: task_framing에서 "달성 기준:" 이후 텍스트 (하위 호환)
        """
        if not consciousness_output:
            return None

        # 1차: 별도 필드 (문자열 또는 리스트)
        criteria = consciousness_output.get("achievement_criteria", "")
        if isinstance(criteria, list):
            criteria = ", ".join(str(c) for c in criteria if c)
        if criteria and isinstance(criteria, str) and criteria.strip():
            return criteria.strip()

        # 2차: task_framing에서 추출 (하위 호환)
        task_framing = consciousness_output.get("task_framing", "")
        if "달성 기준:" in task_framing:
            return task_framing.split("달성 기준:")[-1].strip().rstrip(".")
        if "달성기준:" in task_framing:
            return task_framing.split("달성기준:")[-1].strip().rstrip(".")

        return None

    def _collect_created_files(self, response: str) -> str:
        """에이전트 응답에서 생성된 파일 경로를 찾아 내용을 읽는다."""
        import os

        # 절대 경로 패턴 매칭
        path_pattern = re.compile(r'(/[^\s"\'<>]+\.\w{1,10})')
        paths = path_pattern.findall(response)

        files_content = []
        for path in paths:
            if os.path.isfile(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    if len(content) > 10000:
                        content = content[:10000] + "\n\n... (10000자 초과, 생략됨)"
                    files_content.append(f"### {os.path.basename(path)}\n```\n{content}\n```")
                except Exception:
                    pass

        return "\n\n".join(files_content) if files_content else ""

    _evaluator_prompt_cache: str = ""

    @classmethod
    def _load_evaluator_prompt(cls) -> str:
        """평가 에이전트 프롬프트 파일을 로드한다 (캐시)."""
        if not cls._evaluator_prompt_cache:
            prompt_path = Path(__file__).parent.parent / "data" / "common_prompts" / "evaluator_prompt.md"
            try:
                cls._evaluator_prompt_cache = prompt_path.read_text(encoding='utf-8')
            except FileNotFoundError:
                cls._evaluator_prompt_cache = "달성 기준의 모든 항목을 엄격히 평가하라."
        return cls._evaluator_prompt_cache

    def _evaluate_achievement(self, user_message: str, criteria: str,
                               response: str, created_files: str,
                               consciousness_output: dict = None,
                               tool_results_str: str = "") -> tuple:
        """평가 AI로 달성 기준 충족 여부를 판단한다.

        의식 에이전트의 출력(self_awareness, capability_focus, world_state)을 활용하여
        결과물뿐 아니라 도구 활용의 적절성까지 평가한다.

        Returns:
            (achieved: bool, feedback: str)
        """
        evaluator_system_prompt = self._load_evaluator_prompt()

        # 메시지에는 평가 대상 데이터만
        prompt = (
            f"## 사용자 요청\n{user_message}\n\n"
            f"## 달성 기준\n{criteria}\n\n"
        )

        # 의식 에이전트의 자기 인식과 도구 정보를 평가 맥락으로 제공
        if consciousness_output:
            self_awareness = consciousness_output.get("self_awareness", "")
            if self_awareness:
                prompt += f"## 에이전트 자기 인식 (의식 에이전트 판단)\n{self_awareness}\n\n"

            cap_focus = consciousness_output.get("capability_focus", {})
            if isinstance(cap_focus, dict):
                hint = cap_focus.get("hint", "")
                actions = cap_focus.get("highlight_actions", [])
                if hint or actions:
                    prompt += "## 도구 활용 맥락\n"
                    if actions:
                        prompt += f"- 추천된 도구: {', '.join(actions)}\n"
                    if hint:
                        prompt += f"- 접근 방향: {hint}\n"
                    prompt += "\n"

            world_state = consciousness_output.get("world_state", "")
            if world_state:
                prompt += f"## 세계 상태\n{world_state}\n\n"

        if tool_results_str:
            prompt += f"## 도구 실행 결과\n{tool_results_str}\n\n"

        prompt += f"## 에이전트 응답\n{response[:8000]}\n\n"

        if created_files:
            prompt += f"## 생성된 파일 내용\n{created_files}\n\n"

        prompt += "위 정보를 바탕으로 평가하세요. 도구 실행 결과가 있으면 실제로 작업이 수행되었는지 확인하세요."

        try:
            from consciousness_agent import lightweight_ai_call

            eval_response = lightweight_ai_call(prompt, system_prompt=evaluator_system_prompt)
            if eval_response is None or not eval_response.strip():
                self._log("[GoalEval] AI 응답 없음 (API 오류 등), 통과 처리")
                return True, "평가 스킵 (AI 응답 없음)"

            self._log(f"[GoalEval] 평가 응답: {eval_response[:200]}")

            first_line = eval_response.strip().split('\n')[0].strip().upper()
            achieved = "ACHIEVED" in first_line and "NOT" not in first_line
            return achieved, eval_response

        except Exception as e:
            self._log(f"[GoalEval] 평가 오류: {e}")
            return True, f"평가 오류 (통과 처리): {e}"

    def _run_goal_evaluation_loop(self, user_message: str, criteria: str,
                                   initial_response: str, history: list,
                                   consciousness_output: dict = None,
                                   max_rounds: int = 2,
                                   tool_results: list = None) -> str:
        """달성 기준 기반 평가 루프.

        Args:
            user_message: 사용자 원래 요청
            criteria: 달성 기준
            initial_response: 에이전트 첫 응답
            history: 대화 히스토리
            consciousness_output: 의식 에이전트 출력 (self_awareness, capability_focus 등)
            max_rounds: 최대 평가 횟수 (기본 2)
            tool_results: 도구 실행 이력 리스트

        Returns:
            최종 응답 텍스트
        """
        import time as _time
        response = initial_response

        # 도구 실행 이력을 문자열로 변환
        tool_results_str = ""
        if tool_results:
            tool_entries = []
            for tr in tool_results:
                if isinstance(tr, str) and tr.strip():
                    # 너무 긴 결과는 truncate
                    entry = tr[:2000] if len(tr) > 2000 else tr
                    tool_entries.append(entry)
            if tool_entries:
                tool_results_str = "\n---\n".join(tool_entries[-5:])  # 최근 5개

        for round_num in range(1, max_rounds + 1):
            self._log(f"[GoalEval] 라운드 {round_num}/{max_rounds} 평가 시작")
            eval_start = _time.time()

            # 생성된 파일 수집
            created_files = self._collect_created_files(response)

            # 달성 여부 평가 (의식 에이전트의 자기 인식 + 도구 실행 이력 포함)
            achieved, feedback = self._evaluate_achievement(
                user_message, criteria, response, created_files,
                consciousness_output=consciousness_output,
                tool_results_str=tool_results_str
            )

            eval_time = _time.time() - eval_start
            self._log(
                f"[GoalEval] 라운드 {round_num}: "
                f"{'ACHIEVED' if achieved else 'NOT_ACHIEVED'} "
                f"({eval_time:.1f}초)"
            )

            if achieved:
                return response

            # 마지막 라운드면 그냥 반환
            if round_num >= max_rounds:
                self._log(f"[GoalEval] 라운드 소진, 현재 응답 반환")
                return response

            # 피드백을 주입하여 재실행
            self._log(f"[GoalEval] 재실행 시작 (피드백 주입)")
            feedback_message = (
                f"[평가 피드백] 이전 응답이 달성 기준을 충족하지 못했습니다.\n\n"
                f"달성 기준: {criteria}\n\n"
                f"부족한 점:\n{feedback}\n\n"
                f"위 피드백을 반영하여 다시 작업하세요. "
                f"이전 작업 결과를 최대한 활용하고, 부족한 부분만 보완하세요."
            )

            # 피드백을 히스토리에 추가하여 재실행
            retry_history = history + [
                {"role": "assistant", "content": response[:2000]},
                {"role": "user", "content": feedback_message}
            ]

            try:
                retry_response = self.ai.process_message_with_history(
                    message_content=feedback_message,
                    history=retry_history,
                    task_id=f"goal_retry_{round_num}"
                )
                # 재실행 결과가 비어있으면 (503 등) 이전 응답 유지
                if retry_response and retry_response.strip():
                    response = retry_response
                    self._log(f"[GoalEval] 재실행 완료: {len(response)}자")
                else:
                    self._log(f"[GoalEval] 재실행 결과 비어있음, 이전 응답 유지 ({len(response)}자)")
            except Exception as e:
                self._log(f"[GoalEval] 재실행 실패: {e}")
                return initial_response

        return response
