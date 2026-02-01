"""
channels/base.py - 통신 채널 기본 인터페이스
"""

from abc import ABC, abstractmethod


class Channel(ABC):
    """통신 채널 추상 클래스"""
    
    def __init__(self, config: dict):
        """
        채널 초기화
        Args:
            config: 채널 설정 딕셔너리
        """
        self.config = config
    
    @abstractmethod
    def authenticate(self) -> bool:
        """
        채널 인증 (초기화 시 한 번 실행)
        Returns:
            bool: 인증 성공 여부
        """
        pass
    
    @abstractmethod
    def poll_messages(self, max_count: int = 5) -> list:
        """
        새 메시지 가져오기
        Args:
            max_count: 가져올 최대 메시지 수
        Returns:
            list: 메시지 리스트
                [
                    {
                        'from': str,      # 발신자 (이메일, pubkey 등)
                        'subject': str,   # 제목 (없으면 '')
                        'body': str,      # 본문
                        'id': str,        # 메시지 ID
                        'raw': dict       # 원본 데이터 (선택)
                    },
                    ...
                ]
        """
        pass
    
    @abstractmethod
    def send_message(self, to: str, subject: str, body: str, attachment_path: str = None) -> bool:
        """
        메시지 전송
        Args:
            to: 수신자
            subject: 제목
            body: 본문
            attachment_path: 첨부할 파일의 절대 경로 (선택, 채널이 지원하는 경우)
        Returns:
            bool: 전송 성공 여부
        """
        pass
    
    @abstractmethod
    def mark_as_read(self, message_id: str):
        """
        메시지를 읽음으로 표시
        Args:
            message_id: 메시지 ID
        """
        pass
    
    def get_channel_info(self) -> dict:
        """
        채널 정보 반환 (선택적 구현)
        Returns:
            dict: 채널 정보 {'type': str, 'account': str, ...}
        """
        return {
            'type': self.__class__.__name__,
            'account': 'unknown'
        }

    def get_status(self) -> dict:
        """
        채널 상태 반환 (선택적 구현)
        Returns:
            dict: 채널 상태 {'type': str, 'authenticated': bool, ...}
        """
        info = self.get_channel_info()
        return {
            'type': info.get('type', 'unknown'),
            'authenticated': True,  # 기본값
            'account': info.get('account', 'unknown')
        }
    
    def is_realtime(self) -> bool:
        """
        실시간 이벤트 기반 채널인지 확인
        Returns:
            bool: True면 실시간 WebSocket/이벤트 기반, False면 폴링 기반
        """
        return False  # 기본값: 폴링
    
    def register_callback(self, callback):
        """
        실시간 메시지 수신 시 호출할 콜백 등록 (실시간 채널 전용)
        Args:
            callback: 메시지 수신 시 호출할 함수 (msg dict를 인자로 받음)
        """
        pass  # 폴링 채널은 구현 불필요
    
    def start_listening(self):
        """
        실시간 리스닝 시작 (실시간 채널 전용)
        """
        pass  # 폴링 채널은 구현 불필요
    
    def stop_listening(self):
        """
        실시간 리스닝 중지 (실시간 채널 전용)
        """
        pass  # 폴링 채널은 구현 불필요
