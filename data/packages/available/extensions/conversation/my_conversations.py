"""
주체별 대화 관리 래퍼 클래스 (새 스키마)

각 주체(사용자, AI 에이전트)가 마치 자신만의 독립 DB를 가진 것처럼 사용할 수 있게 해줍니다.
실제로는 통합 DB를 사용하지만, 인터페이스는 완전히 독립적입니다.
"""

import uuid
from typing import List, Dict, Optional
from conversation_db import ConversationDB


class MyConversations:
    """
    특정 주체의 대화 관리 클래스 (새 스키마)
    
    agents 테이블 기반, from/to 단방향 메시지
    """
    
    def __init__(self, agent_name: str, agent_type: str = 'ai_agent', db_path: str = None):
        """
        Args:
            agent_name: 에이전트 이름 (예: 'kukjin', '집사', '코더')
            agent_type: 'human' 또는 'ai_agent'
            db_path: DB 경로 (None이면 기본 경로 사용)
        """
        self.agent_name = agent_name
        self.agent_type = agent_type
        self.db = ConversationDB(db_path)
        
        # agents 테이블에서 자신의 ID 가져오기
        self.my_agent_id = self._get_my_agent_id()
        
        # 현재 세션 ID
        self.current_session_id = str(uuid.uuid4())
    
    def _get_my_agent_id(self) -> int:
        """agents 테이블에서 자신의 ID 조회 (없으면 자동 생성)"""
        agent = self.db.get_agent_by_name(self.agent_name)
        
        if not agent:
            # 에이전트가 없으면 자동 등록
            agent_id = self.db.add_agent(self.agent_name, self.agent_type)
            print(f"✓ 에이전트 '{self.agent_name}' 자동 등록됨 (ID: {agent_id})")
            return agent_id
        
        return agent['id']
    
    # ==================== 상대방 agent 찾기 ====================
    
    def find_agent_by_name(self, name: str) -> Optional[int]:
        """다른 agent를 이름으로 찾기"""
        agent = self.db.get_agent_by_name(name)
        return agent['id'] if agent else None
    
    def get_agent_info(self, agent_id: int) -> Optional[Dict]:
        """agent 정보 조회"""
        return self.db.get_agent(agent_id)
    
    # ==================== 메시지 송수신 ====================
    
    def send_message(self, to_agent_id: int, content: str,
                    contact_type: str = 'gui',
                    tool_calls: Optional[List] = None,
                    session_id: Optional[str] = None) -> int:
        """
        다른 agent에게 메시지 보내기
        
        Args:
            to_agent_id: 받는 사람 (agent ID)
            content: 메시지 내용
            contact_type: 연락 채널
            tool_calls: 도구 호출 정보
            session_id: 세션 ID (없으면 현재 세션)
        
        Returns:
            message_id
        """
        return self.db.save_message(
            from_agent_id=self.my_agent_id,
            to_agent_id=to_agent_id,
            content=content,
            contact_type=contact_type,
            tool_calls=tool_calls,
            session_id=session_id or self.current_session_id
        )
    
    def receive_message(self, from_agent_id: int, content: str,
                       contact_type: str = 'gui') -> int:
        """
        다른 agent로부터 메시지 받기
        
        실제로는 send_message와 동일하지만 의미론적으로 명확히 하기 위함
        
        Args:
            from_agent_id: 보낸 사람 (agent ID)
            content: 메시지 내용
            contact_type: 연락 채널
        
        Returns:
            message_id
        """
        return self.db.save_message(
            from_agent_id=from_agent_id,
            to_agent_id=self.my_agent_id,
            content=content,
            contact_type=contact_type,
            session_id=self.current_session_id
        )
    
    # ==================== 대화 히스토리 조회 ====================
    
    def get_history_with(self, other_agent_id: int, limit: int = 30,
                         session_id: Optional[str] = None) -> List[Dict]:
        """
        다른 agent와의 대화 히스토리 조회
        
        Args:
            other_agent_id: 대화 상대 (agent ID)
            limit: 최대 메시지 수
            session_id: 특정 세션만 (선택)
        
        Returns:
            메시지 목록 (시간순 정렬)
        """
        return self.db.get_conversation_history(
            agent1_id=self.my_agent_id,
            agent2_id=other_agent_id,
            limit=limit,
            session_id=session_id
        )
    
    def get_history_for_ai(self, other_agent_id: int, limit: int = 30) -> List[Dict]:
        """
        AI 프롬프트에 넣을 형식으로 히스토리 조회
        
        Args:
            other_agent_id: 대화 상대 (agent ID)
            limit: 최대 메시지 수
        
        Returns:
            [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
        """
        return self.db.format_history_for_ai(
            my_agent_id=self.my_agent_id,
            other_agent_id=other_agent_id,
            limit=limit
        )
    
    def get_current_session_history(self, other_agent_id: int) -> List[Dict]:
        """현재 세션의 대화만 조회"""
        return self.get_history_with(
            other_agent_id=other_agent_id,
            session_id=self.current_session_id
        )
    
    def get_my_conversations(self) -> List[Dict]:
        """내가 대화한 모든 상대 목록"""
        return self.db.get_conversations_with_message_count(self.my_agent_id)
    
    # ==================== 세션 관리 ====================
    
    def start_new_session(self):
        """새로운 대화 세션 시작"""
        self.current_session_id = str(uuid.uuid4())
        return self.current_session_id
    
    def get_current_session_id(self) -> str:
        """현재 세션 ID 반환"""
        return self.current_session_id
    
    # ==================== 편의 메서드 ====================
    
    def chat_with(self, agent_name: str, my_message: str,
                  contact_type: str = 'gui') -> Dict:
        """
        다른 agent와 대화 (간편 버전)
        
        Args:
            agent_name: 상대 agent 이름
            my_message: 내가 보낼 메시지
            contact_type: 연락 채널
        
        Returns:
            {"agent_id": int, "message_id": int, "history": List[Dict]}
        """
        # agent 찾기
        other_agent_id = self.find_agent_by_name(agent_name)
        
        if not other_agent_id:
            raise ValueError(f"Agent '{agent_name}'을 찾을 수 없습니다")
        
        # 메시지 보내기
        msg_id = self.send_message(
            to_agent_id=other_agent_id,
            content=my_message,
            contact_type=contact_type
        )
        
        # 히스토리 조회
        history = self.get_history_with(other_agent_id, limit=10)
        
        return {
            "agent_id": other_agent_id,
            "message_id": msg_id,
            "history": history
        }
    
    def print_history_with(self, other_agent_id: int, limit: int = 30):
        """대화 히스토리를 보기 좋게 출력"""
        other_agent = self.get_agent_info(other_agent_id)
        other_name = other_agent['name'] if other_agent else f"ID:{other_agent_id}"
        
        print(f"\n=== {self.agent_name} ↔ {other_name} 대화 ===")
        
        history = self.get_history_with(other_agent_id, limit)
        
        for msg in history:
            # from_agent_id로 누가 보냈는지 판단
            if msg['from_agent_id'] == self.my_agent_id:
                role = "나"
            else:
                role = other_name
            
            time_str = str(msg['message_time'])[:19]  # YYYY-MM-DD HH:MM:SS
            
            tool_info = ""
            if msg.get('tool_calls'):
                tool_info = f" [도구: {msg['tool_calls']}]"
            
            print(f"[{time_str}] {role}: {msg['content']}{tool_info}")
    
    def print_my_conversations(self):
        """내 모든 대화 상대 출력"""
        convs = self.get_my_conversations()
        
        print(f"\n=== {self.agent_name}의 대화 상대 ===")
        for conv in convs:
            print(f"- {conv['other_agent_name']}: {conv['message_count']}개 메시지 "
                  f"(마지막: {str(conv['last_message_time'])[:19]})")
    
    # ==================== 규칙 히스토리 관리 ====================
    
    @staticmethod
    def save_rules_history(agent_name: str, system_prompt: str = '',
                          role: str = '', persistent_note: str = '',
                          project_path: str = None):
        """
        규칙들을 히스토리 형식으로 변환하여 JSON 파일에 저장

        Args:
            agent_name: 에이전트 이름 (파일명에 사용)
            system_prompt: 공통 시스템 프롬프트
            role: 개별 역할
            persistent_note: 영구 메모
            project_path: 프로젝트 경로 (없으면 os.getcwd() 사용)
        """
        import json
        import os

        # JSON 파일 전체 구조
        data = {
            "rules_history": [],
            "persistent_note": persistent_note  # 영구메모는 별도 필드로 저장
        }

        # 1. 시스템 규칙
        if system_prompt:
            data["rules_history"].append({
                "role": "user",
                "content": f"[시스템 규칙]\n{system_prompt}"
            })

        # 2. 개별 역할
        if role:
            data["rules_history"].append({
                "role": "user",
                "content": f"[당신의 역할]\n{role}"
            })

        # 3. 영구 메모 (히스토리에도 추가)
        if persistent_note:
            data["rules_history"].append({
                "role": "user",
                "content": f"[영구 정보]\n{persistent_note}"
            })

        # 파일명 생성
        filename = f"agent_{agent_name}_rules.json"
        base_path = project_path if project_path else os.getcwd()
        filepath = os.path.join(base_path, filename)

        # JSON 파일로 저장
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return filepath
    
    @staticmethod
    def load_rules_history(agent_name: str, project_path: str = None) -> List[Dict]:
        """
        JSON 파일에서 규칙 히스토리 로드

        Args:
            agent_name: 에이전트 이름
            project_path: 프로젝트 경로 (없으면 os.getcwd() 사용)

        Returns:
            규칙 히스토리 리스트 (없으면 빈 리스트)
        """
        import json
        import os

        filename = f"agent_{agent_name}_rules.json"
        base_path = project_path if project_path else os.getcwd()
        filepath = os.path.join(base_path, filename)

        if not os.path.exists(filepath):
            return []
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # 새 형식 (dict with rules_history)
                if isinstance(data, dict) and 'rules_history' in data:
                    return data['rules_history']
                
                # 구 형식 (list) - 하위호환
                elif isinstance(data, list):
                    return data
                
                else:
                    return []
        except Exception as e:
            print(f"규칙 히스토리 로드 실패 ({agent_name}): {e}")
            return []
    
    @staticmethod
    def load_persistent_note(agent_name: str) -> str:
        """
        JSON 파일에서 영구메모만 로드
        
        Args:
            agent_name: 에이전트 이름
        
        Returns:
            영구메모 문자열 (없으면 빈 문자열)
        """
        import json
        import os
        
        filename = f"agent_{agent_name}_rules.json"
        filepath = os.path.join(os.getcwd(), filename)
        
        if not os.path.exists(filepath):
            return ''
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # 새 형식에서 persistent_note 필드 추출
                if isinstance(data, dict):
                    return data.get('persistent_note', '')
                
                return ''
        except Exception as e:
            print(f"영구메모 로드 실패 ({agent_name}): {e}")
            return ''
    
    # ==================== 원본 파일 관리 (편집용) ====================
    
    @staticmethod
    def load_common_settings() -> str:
        """공통설정 원본 파일 읽기"""
        import os
        filepath = os.path.join(os.getcwd(), 'common_settings.txt')
        if not os.path.exists(filepath):
            return ''
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"공통설정 로드 실패: {e}")
            return ''
    
    @staticmethod
    def save_common_settings(content: str):
        """공통설정 원본 파일 저장"""
        import os
        filepath = os.path.join(os.getcwd(), 'common_settings.txt')
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return filepath
        except Exception as e:
            print(f"공통설정 저장 실패: {e}")
            return None
    
    @staticmethod
    def load_agent_role(agent_name: str) -> str:
        """개별역할 원본 파일 읽기"""
        import os
        filepath = os.path.join(os.getcwd(), f'agent_{agent_name}_role.txt')
        if not os.path.exists(filepath):
            return ''
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"역할 로드 실패 ({agent_name}): {e}")
            return ''
    
    @staticmethod
    def save_agent_role(agent_name: str, content: str):
        """개별역할 원본 파일 저장"""
        import os
        filepath = os.path.join(os.getcwd(), f'agent_{agent_name}_role.txt')
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return filepath
        except Exception as e:
            print(f"역할 저장 실패 ({agent_name}): {e}")
            return None
    
    @staticmethod
    def load_agent_note(agent_name: str) -> str:
        """영구노트 원본 파일 읽기"""
        import os
        filepath = os.path.join(os.getcwd(), f'agent_{agent_name}_note.txt')
        if not os.path.exists(filepath):
            return ''
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"노트 로드 실패 ({agent_name}): {e}")
            return ''
    
    @staticmethod
    def save_agent_note(agent_name: str, content: str):
        """영구노트 원본 파일 저장"""
        import os
        filepath = os.path.join(os.getcwd(), f'agent_{agent_name}_note.txt')
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return filepath
        except Exception as e:
            print(f"노트 저장 실패 ({agent_name}): {e}")
            return None

    @staticmethod
    def rename_agent(old_name: str, new_name: str, base_path: str = None) -> dict:
        """
        에이전트 이름 변경 시 관련 파일들을 리네이밍합니다.

        변경 대상:
        - agent_{old}_role.txt → agent_{new}_role.txt
        - agent_{old}_note.txt → agent_{new}_note.txt
        - agent_{old}_rules.json → agent_{new}_rules.json
        - 대화 DB의 agent_name 필드

        Args:
            old_name: 기존 에이전트 이름
            new_name: 새 에이전트 이름
            base_path: 기본 경로 (None이면 현재 작업 디렉토리)

        Returns:
            dict: {
                'success': bool,
                'renamed_files': list,  # 리네이밍된 파일 목록
                'errors': list,         # 오류 목록
                'db_updated': bool      # DB 업데이트 여부
            }
        """
        import os

        if base_path is None:
            base_path = os.getcwd()

        result = {
            'success': True,
            'renamed_files': [],
            'errors': [],
            'db_updated': False
        }

        # 리네이밍할 파일 패턴들
        file_patterns = [
            ('role.txt', f'agent_{old_name}_role.txt', f'agent_{new_name}_role.txt'),
            ('note.txt', f'agent_{old_name}_note.txt', f'agent_{new_name}_note.txt'),
            ('rules.json', f'agent_{old_name}_rules.json', f'agent_{new_name}_rules.json'),
        ]

        for desc, old_file, new_file in file_patterns:
            old_path = os.path.join(base_path, old_file)
            new_path = os.path.join(base_path, new_file)

            if os.path.exists(old_path):
                try:
                    # 새 파일이 이미 있으면 백업
                    if os.path.exists(new_path):
                        backup_path = new_path + '.backup'
                        os.rename(new_path, backup_path)
                        result['renamed_files'].append(f"{new_file} → {new_file}.backup (백업)")

                    os.rename(old_path, new_path)
                    result['renamed_files'].append(f"{old_file} → {new_file}")
                    print(f"✓ 파일 리네이밍: {old_file} → {new_file}")
                except Exception as e:
                    error_msg = f"파일 리네이밍 실패 ({old_file}): {e}"
                    result['errors'].append(error_msg)
                    print(f"✗ {error_msg}")

        # 대화 DB 업데이트
        try:
            from conversation_db import ConversationDB
            db = ConversationDB()
            updated = db.rename_agent(old_name, new_name)
            if updated:
                result['db_updated'] = True
                print(f"✓ 대화 DB 업데이트: {old_name} → {new_name}")
            else:
                print(f"ℹ 대화 DB: 변경할 데이터 없음")
        except Exception as e:
            error_msg = f"대화 DB 업데이트 실패: {e}"
            result['errors'].append(error_msg)
            print(f"✗ {error_msg}")

        if result['errors']:
            result['success'] = False

        return result

    # ==================== 외부인 neighbor 관리 (확장용) ====================
    
    def find_or_add_neighbor(self, name: str, neighbor_type: str = 'external',
                            contact_type: Optional[str] = None,
                            contact_value: Optional[str] = None) -> int:
        """
        외부인 이웃 찾기 또는 추가
        
        agents가 아닌 외부인(이메일, Nostr 등)을 neighbors에 추가
        나중에 필요할 때 사용
        """
        return self.db.get_or_create_neighbor(
            my_agent_id=self.my_agent_id,
            neighbor_name=name,
            neighbor_type=neighbor_type,
            contact_type=contact_type,
            contact_value=contact_value
        )


# ==================== 사용 예시 ====================

if __name__ == "__main__":
    # 1. kukjin의 대화 관리
    kukjin = MyConversations('kukjin', 'human')
    
    # 2. 집사와 대화
    print("=== kukjin이 집사에게 메시지 보내기 ===")
    butler_id = kukjin.find_agent_by_name('집사')
    kukjin.send_message(butler_id, "오늘 할 일 알려줘")
    
    # 3. 집사의 대화 관리 (독립적)
    butler = MyConversations('집사', 'ai_agent')
    
    # 집사가 kukjin의 메시지를 확인하고 응답
    kukjin_id = butler.find_agent_by_name('kukjin')
    butler.send_message(kukjin_id, "오늘 회의 3개 있습니다: 10시, 14시, 16시")
    
    # 4. 집사가 출판에게 작업 위임
    print("\n=== 집사가 출판에게 작업 위임 ===")
    publisher_id = butler.find_agent_by_name('출판')
    butler.send_message(publisher_id, "신문 발행해줘", contact_type='internal')
    
    # 5. 출판의 대화 관리
    publisher = MyConversations('출판', 'ai_agent')
    
    # 출판이 작업 완료 후 응답
    butler_id_for_pub = publisher.find_agent_by_name('집사')
    publisher.send_message(
        butler_id_for_pub, 
        "신문 발행 완료했습니다",
        contact_type='internal'
    )
    
    # 6. 각자의 대화 상대 확인
    kukjin.print_my_conversations()
    butler.print_my_conversations()
    publisher.print_my_conversations()
    
    # 7. 각자의 관점에서 대화 히스토리 확인
    kukjin.print_history_with(butler_id)
    butler.print_history_with(kukjin_id)
    butler.print_history_with(publisher_id)
    
    # 8. AI 프롬프트용 포맷
    print("\n=== 집사가 AI 응답 생성을 위해 히스토리 로드 ===")
    ai_history = butler.get_history_for_ai(kukjin_id, limit=30)
    print(f"로드된 메시지 수: {len(ai_history)}개")
    for msg in ai_history[:3]:  # 처음 3개만 출력
        print(f"  {msg['role']}: {msg['content']}")
    
    print("\n✅ 예시 완료!")
