"""
channels/gmail.py - Gmail 채널 플러그인
"""

from .base import Channel
from gmail import GmailClient


class GmailChannel(Channel):
    """Gmail 채널 구현"""
    
    def __init__(self, config: dict):
        """
        Args:
            config: Gmail 설정
                {
                    'client_id': str,
                    'client_secret': str,
                    'email': str (선택, 정보용)
                }
        """
        super().__init__(config)
        self.client = GmailClient(config)
        self.email = config.get('email', 'unknown')
    
    def authenticate(self) -> bool:
        """Gmail 인증"""
        try:
            return self.client.authenticate()
        except Exception as e:
            print(f"[GmailChannel] 인증 실패: {e}")
            return False
    
    def poll_messages(self, max_count: int = 5) -> list:
        """
        읽지 않은 메시지 가져오기
        Args:
            max_count: 최대 메시지 수
        Returns:
            통일된 형식의 메시지 리스트
        """
        try:
            raw_messages = self.client.get_unread_messages(max_results=max_count)
            
            # 통일된 형식으로 변환
            normalized = []
            for msg in raw_messages:
                normalized.append({
                    'from': msg.get('from', ''),
                    'subject': msg.get('subject', ''),
                    'body': msg.get('body', ''),
                    'id': msg.get('id', ''),
                    'raw': msg  # 원본 데이터 보존
                })
            
            return normalized
        
        except Exception as e:
            print(f"[GmailChannel] 메시지 폴링 실패: {e}")
            return []
    
    def send_message(self, to: str, subject: str, body: str, attachment_path: str = None) -> bool:
        """
        이메일 전송
        Args:
            to: 수신자 이메일
            subject: 제목
            body: 본문
            attachment_path: 첨부할 파일의 절대 경로 (선택)
        Returns:
            성공 여부
        """
        try:
            self.client.send_message(to=to, subject=subject, body=body,
                                     attachment_path=attachment_path)
            return True
        except Exception as e:
            print(f"[GmailChannel] 메시지 전송 실패: {e}")
            return False
    
    def mark_as_read(self, message_id: str):
        """메시지 읽음 표시"""
        try:
            self.client.mark_as_read(message_id)
        except Exception as e:
            print(f"[GmailChannel] 읽음 표시 실패: {e}")
    
    def get_channel_info(self) -> dict:
        """채널 정보 반환"""
        return {
            'type': 'gmail',
            'account': self.email
        }

    def get_status(self) -> dict:
        """채널 상태 반환"""
        return {
            'type': 'gmail',
            'authenticated': self.client is not None,
            'account': self.email
        }
