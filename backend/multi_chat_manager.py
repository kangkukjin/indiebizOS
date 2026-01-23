"""
multi_chat_manager.py - 다중채팅방 관리자
IndieBiz OS

기능:
- 채팅방 생성/삭제
- 에이전트 소환 (기존 프로젝트에서 불러오기)
- 대화 진행 (사용자 주도 + 랜덤 응답 + @지목)
"""

import random
import re
import yaml
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from multi_chat_db import MultiChatDB
from ai_agent import AIAgent


class MultiChatManager:
    """다중채팅방 관리자"""

    def __init__(self, base_path: Path = None, ai_config: dict = None):
        if base_path is None:
            base_path = Path(__file__).parent.parent  # indiebizOS root

        self.base_path = Path(base_path)
        self.projects_path = self.base_path / "projects"
        self.data_path = self.base_path / "data"

        # DB 초기화
        db_path = self.data_path / "multi_chat.db"
        self.db = MultiChatDB(str(db_path))

        # AI 설정
        self.ai_config = ai_config or {}

    # ============ Room 관리 ============

    def create_room(self, name: str, description: str = "") -> Dict:
        """채팅방 생성"""
        room_id = self.db.create_room(name, description)
        return self.db.get_room(room_id)

    def get_room(self, room_id: str) -> Optional[Dict]:
        """채팅방 정보"""
        return self.db.get_room(room_id)

    def list_rooms(self) -> List[Dict]:
        """모든 채팅방 목록"""
        import json
        rooms = self.db.list_rooms()
        # 각 방의 참여자 수 추가 및 icon_position 파싱
        for room in rooms:
            participants = self.db.get_participants(room['id'])
            room['participant_count'] = len(participants)
            # icon_position JSON 파싱
            if room.get('icon_position'):
                try:
                    room['icon_position'] = json.loads(room['icon_position'])
                except:
                    room['icon_position'] = [100, 100]
            else:
                room['icon_position'] = [100, 100]
        return rooms

    def delete_room(self, room_id: str) -> bool:
        """채팅방 영구 삭제"""
        return self.db.delete_room(room_id)

    def move_to_trash(self, room_id: str) -> dict:
        """채팅방을 휴지통으로 이동"""
        return self.db.move_to_trash(room_id)

    def restore_from_trash(self, room_id: str) -> dict:
        """채팅방을 휴지통에서 복원"""
        return self.db.restore_from_trash(room_id)

    def list_trashed_rooms(self) -> List[Dict]:
        """휴지통에 있는 채팅방 목록"""
        return self.db.list_trashed_rooms()

    def empty_trash(self) -> int:
        """휴지통 비우기"""
        return self.db.empty_trash()

    def update_room_position(self, room_id: str, x: int, y: int) -> bool:
        """채팅방 아이콘 위치 업데이트"""
        return self.db.update_room_position(room_id, x, y)

    # ============ 에이전트 소환 ============

    def list_available_agents(self) -> List[Dict]:
        """
        모든 프로젝트에서 소환 가능한 에이전트 목록

        Returns:
            [{"project_id": "...", "project_name": "...", "agent_id": "...",
              "agent_name": "...", "role": "..."}, ...]
        """
        available = []

        # projects.json 로드
        projects_json = self.projects_path / "projects.json"
        if not projects_json.exists():
            return available

        import json
        with open(projects_json, encoding='utf-8') as f:
            projects = json.load(f)

        for project in projects:
            if project.get("type") != "project":
                continue

            project_id = project.get("id", "")
            project_name = project.get("name", "")
            project_path = self.projects_path / project_id

            # agents.yaml 로드
            agents_yaml = project_path / "agents.yaml"
            if not agents_yaml.exists():
                continue

            try:
                with open(agents_yaml, encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}

                for agent in data.get("agents", []):
                    if not agent.get("active", True):
                        continue

                    # role_description 또는 role 또는 system_prompt에서 역할 가져오기
                    role = (
                        agent.get("role_description") or
                        agent.get("role") or
                        agent.get("system_prompt", "")[:100]  # 시스템 프롬프트 앞부분
                    )

                    available.append({
                        "project_id": project_id,
                        "project_name": project_name,
                        "agent_id": agent.get("id", ""),
                        "agent_name": agent.get("name", ""),
                        "role": role,
                        "source": f"{project_name}/{agent.get('name', '')}"
                    })
            except Exception as e:
                print(f"[MultiChatManager] 에이전트 로드 실패 ({project_id}): {e}")

        return available

    def add_agent_to_room(self, room_id: str, project_id: str, agent_id: str) -> bool:
        """
        채팅방에 에이전트 추가

        Args:
            room_id: 채팅방 ID
            project_id: 프로젝트 ID
            agent_id: 에이전트 ID
        """
        # 에이전트 정보 로드
        project_path = self.projects_path / project_id
        agents_yaml = project_path / "agents.yaml"

        if not agents_yaml.exists():
            return False

        try:
            with open(agents_yaml, encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}

            agent_info = None
            for agent in data.get("agents", []):
                if agent.get("id") == agent_id:
                    agent_info = agent
                    break

            if not agent_info:
                return False

            # 시스템 프롬프트 구성 (다중채팅용)
            agent_name = agent_info.get("name", "")
            role = agent_info.get("role", "")

            system_prompt = f"""너는 '{agent_name}'이다.

[역할]
{role}

[다중채팅 규칙]
- 이것은 여러 에이전트와 사용자가 함께하는 다중채팅방이다.
- 대화만 가능하다. 도구 사용, 파일 접근, 검색 등은 할 수 없다.
- 다른 참여자의 의견에 동의하거나 반박할 수 있다.
- 자신의 역할과 관점에서 의견을 제시하라.
- 대화 히스토리에서 [이름] 형식으로 누가 말했는지 확인할 수 있다.
- 짧고 간결하게 대화하라."""

            agent_source = f"{project_id}/{agent_name}"

            # AI 설정 추출
            ai_config = agent_info.get("ai", {})
            ai_provider = ai_config.get("provider", "")
            ai_model = ai_config.get("model", "")
            ai_api_key = ai_config.get("api_key", "")

            print(f"[MultiChatManager] 에이전트 추가: {agent_name}")
            print(f"  - provider: {ai_provider}")
            print(f"  - model: {ai_model}")
            print(f"  - api_key: {ai_api_key[:20]}..." if ai_api_key else "  - api_key: (없음)")

            return self.db.add_participant(
                room_id=room_id,
                agent_name=agent_name,
                agent_source=agent_source,
                system_prompt=system_prompt,
                ai_provider=ai_provider,
                ai_model=ai_model,
                ai_api_key=ai_api_key
            )

        except Exception as e:
            print(f"[MultiChatManager] 에이전트 추가 실패: {e}")
            return False

    def remove_agent_from_room(self, room_id: str, agent_name: str) -> bool:
        """채팅방에서 에이전트 제거"""
        return self.db.remove_participant(room_id, agent_name)

    def get_room_participants(self, room_id: str) -> List[Dict]:
        """채팅방 참여자 목록"""
        return self.db.get_participants(room_id)

    # ============ 대화 진행 ============

    def send_message(self, room_id: str, message: str,
                     response_count: int = 2,
                     images: List[Dict] = None) -> List[Dict]:
        """
        사용자 메시지 전송 및 에이전트 응답 받기

        Args:
            room_id: 채팅방 ID
            message: 사용자 메시지
            response_count: 응답할 에이전트 수 (기본 2명)
            images: 첨부 이미지 [{"base64": "...", "media_type": "..."}]

        Returns:
            [{"speaker": "...", "content": "..."}, ...]
        """
        # 사용자 메시지 저장
        self.db.add_message(room_id, "사용자", message)

        # 참여자 목록
        participants = self.db.get_participants(room_id)
        if not participants:
            return []

        # @지목 파싱
        mentioned = self._parse_mentions(message, participants)

        # 응답할 에이전트 선택
        if mentioned:
            # 지목된 에이전트만
            responders = mentioned
        else:
            # 랜덤 선택
            count = min(response_count, len(participants))
            responders = random.sample(participants, count)

        # 각 에이전트 응답 생성
        responses = []
        for participant in responders:
            response = self._get_agent_response(room_id, participant, images)
            if response:
                responses.append({
                    "speaker": participant['agent_name'],
                    "content": response
                })
                # 응답 저장
                self.db.add_message(room_id, participant['agent_name'], response)

        return responses

    def _parse_mentions(self, message: str, participants: List[Dict]) -> List[Dict]:
        """@지목 파싱"""
        mentioned = []
        participant_names = {p['agent_name']: p for p in participants}

        # @이름 패턴 찾기
        pattern = r'@(\S+)'
        matches = re.findall(pattern, message)

        for match in matches:
            if match in participant_names:
                mentioned.append(participant_names[match])

        return mentioned

    def _get_agent_response(self, room_id: str, participant: Dict, images: List[Dict] = None) -> str:
        """개별 에이전트 응답 생성"""
        try:
            # 히스토리 로드
            history = self.db.get_history_for_ai(room_id)

            # 참여자의 AI 설정 사용 (없으면 기본 설정 사용)
            ai_provider = participant.get('ai_provider', '')
            ai_model = participant.get('ai_model', '')
            ai_api_key = participant.get('ai_api_key', '')

            # 에이전트별 AI 설정 구성
            agent_ai_config = dict(self.ai_config) if self.ai_config else {}
            if ai_provider:
                agent_ai_config['provider'] = ai_provider
            if ai_model:
                agent_ai_config['model'] = ai_model
            if ai_api_key:
                agent_ai_config['api_key'] = ai_api_key

            # AI 에이전트 생성 (도구 없음)
            agent = AIAgent(
                ai_config=agent_ai_config,
                system_prompt=participant.get('system_prompt', ''),
                agent_name=participant.get('agent_name', ''),
                tools=[]  # 도구 없음!
            )

            # 응답 생성
            # 마지막 사용자 메시지 추출
            last_user_msg = ""
            for msg in reversed(history):
                if msg.get('role') == 'user':
                    last_user_msg = msg.get('content', '')
                    break

            response = agent.process_message_with_history(
                message_content=last_user_msg,
                history=history[:-1] if history else [],  # 마지막 메시지 제외
                images=images  # 이미지 전달
            )

            return response

        except Exception as e:
            print(f"[MultiChatManager] 응답 생성 실패 ({participant.get('agent_name')}): {e}")
            import traceback
            traceback.print_exc()
            return ""

    # ============ 메시지 조회 ============

    def get_messages(self, room_id: str, limit: int = 50) -> List[Dict]:
        """채팅방 메시지 조회"""
        return self.db.get_messages(room_id, limit)

    def clear_messages(self, room_id: str) -> int:
        """채팅방 메시지 삭제"""
        return self.db.clear_messages(room_id)

    # ============ 에이전트 활성화/비활성화 ============

    def activate_all_agents(self, room_id: str, tools: List[str] = None) -> List[str]:
        """
        채팅방의 모든 에이전트 활성화

        Args:
            room_id: 채팅방 ID
            tools: 에이전트에게 부여할 도구 목록

        Returns:
            활성화된 에이전트 이름 목록
        """
        participants = self.db.get_participants(room_id)
        activated = []

        for participant in participants:
            agent_name = participant.get('agent_name', '')
            # 도구가 제공된 경우 시스템 프롬프트 업데이트
            if tools:
                current_prompt = participant.get('system_prompt', '')
                # 도구 사용 가능 안내 추가
                tools_str = ', '.join(tools)
                updated_prompt = current_prompt.replace(
                    "대화만 가능하다. 도구 사용, 파일 접근, 검색 등은 할 수 없다.",
                    f"다음 도구들을 사용할 수 있다: {tools_str}"
                )
                self.db.update_participant_prompt(room_id, agent_name, updated_prompt)

            activated.append(agent_name)
            print(f"[MultiChatManager] 에이전트 활성화됨: {agent_name}")

        return activated

    def deactivate_all_agents(self, room_id: str) -> List[str]:
        """
        채팅방의 모든 에이전트 비활성화

        Returns:
            비활성화된 에이전트 이름 목록
        """
        participants = self.db.get_participants(room_id)
        deactivated = []

        for participant in participants:
            agent_name = participant.get('agent_name', '')
            # 시스템 프롬프트에서 도구 제거
            current_prompt = participant.get('system_prompt', '')
            if '다음 도구들을 사용할 수 있다:' in current_prompt:
                # 원래 문구로 복원
                import re
                updated_prompt = re.sub(
                    r'다음 도구들을 사용할 수 있다: [^\n]+',
                    '대화만 가능하다. 도구 사용, 파일 접근, 검색 등은 할 수 없다.',
                    current_prompt
                )
                self.db.update_participant_prompt(room_id, agent_name, updated_prompt)

            deactivated.append(agent_name)
            print(f"[MultiChatManager] 에이전트 비활성화됨: {agent_name}")

        return deactivated
