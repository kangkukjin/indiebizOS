"""
gmail.py - Gmail API 래퍼
이메일 읽기/보내기 기능
"""

import os
import json
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


class GmailClient:
    """Gmail API 클라이언트"""

    def __init__(self, config: dict):
        self.config = config

        # 이메일 기반으로 토큰 파일 경로 결정
        email = config.get('email', '')
        if email:
            # 이메일 주소가 토큰 파일명
            token_file = f"tokens/{email}.json"
        else:
            token_file = config.get('token_file', 'tokens/token.json')

        self.token_path = Path(__file__).parent / token_file

        # credentials.json은 공통 사용
        self.credentials_path = Path(__file__).parent / "credentials.json"
        
        self.scopes = config.get('scopes', [
            'https://www.googleapis.com/auth/gmail.readonly',
            'https://www.googleapis.com/auth/gmail.send',
            'https://www.googleapis.com/auth/gmail.modify'
        ])
        self.service = None
        self.creds = None
        
        # OAuth 클라이언트 설정 파일 생성
        self._create_credentials_file()
    
    def _create_credentials_file(self):
        """OAuth credentials.json 파일 생성"""
        credentials_data = {
            "installed": {
                "client_id": self.config['client_id'],
                "client_secret": self.config['client_secret'],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"]
            }
        }
        
        # project_id는 선택적
        if self.config.get('project_id'):
            credentials_data["installed"]["project_id"] = self.config['project_id']
        
        self.credentials_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.credentials_path, 'w') as f:
            json.dump(credentials_data, f)
    
    def authenticate(self):
        """Gmail 인증 수행"""
        
        # 설정에서 이메일 주소 가져오기
        expected_email = self.config.get('email', '설정되지 않음')
        
        # 저장된 토큰 로드 시도
        if self.token_path.exists():
            self.creds = Credentials.from_authorized_user_file(str(self.token_path), self.scopes)
        
        # 토큰이 없거나 유효하지 않으면 새로 인증
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                print(f"[Gmail] 토큰 갱신 중... (계정: {expected_email})")
                try:
                    self.creds.refresh(Request())
                except Exception as refresh_error:
                    print(f"[Gmail] 토큰 갱신 실패: {refresh_error}")
                    print("\n" + "="*60)
                    print(f"📧 Gmail 인증 필요")
                    print(f"계정: {expected_email}")
                    print(f"토큰 파일: {self.token_path}")
                    print("="*60)
                    print(f"\n⚠️  브라우저가 열립니다. {expected_email} 계정으로 로그인해주세요!\n")
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(self.credentials_path), self.scopes
                    )
                    # 동적 포트 (Google Cloud Console에 http://localhost 등록 필요)
                    self.creds = flow.run_local_server(
                        port=0,
                        access_type='offline',
                        prompt='consent'
                    )
            else:
                print("\n" + "="*60)
                print(f"📧 Gmail 인증 필요")
                print(f"계정: {expected_email}")
                print(f"토큰 파일: {self.token_path}")
                print("="*60)
                print(f"\n⚠️  브라우저가 열립니다. {expected_email} 계정으로 로그인해주세요!\n")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), self.scopes
                )
                # 동적 포트 (Google Cloud Console에 http://localhost 등록 필요)
                self.creds = flow.run_local_server(
                    port=0,
                    access_type='offline',
                    prompt='consent'
                )
            
            # 토큰 저장
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.token_path, 'w') as token:
                token.write(self.creds.to_json())
            print("[Gmail] 토큰 저장 완료")
        
        # Gmail 서비스 생성 (타임아웃 설정 포함)
        # socket 레벨에서 타임아웃 설정 (120초)
        import socket
        socket.setdefaulttimeout(120)
        
        # cache_discovery=False로 설정하여 연결 안정성 향상
        self.service = build('gmail', 'v1', credentials=self.creds, cache_discovery=False)
        
        # 실제 로그인된 계정 확인
        try:
            profile = self.service.users().getProfile(userId='me').execute()
            actual_email = profile['emailAddress']
            expected_email = self.config.get('email', 'unknown')
            
            print(f"[Gmail] 인증 성공: {actual_email}")
            
            # 계정 불일치 경고
            if expected_email != 'unknown' and actual_email != expected_email:
                print(f"[Gmail] ⚠️  경고: 예상 계정({expected_email})과 다름! 실제: {actual_email}")
                print(f"[Gmail] ⚠️  Token 파일을 삭제하고 다시 인증하세요: {self.token_path}")
            
            return True
        except Exception as e:
            print(f"[Gmail] 프로필 확인 실패: {e}")
            return False
    
    def is_authenticated(self) -> bool:
        """인증 상태 확인"""
        if not self.service:
            return False
        try:
            self.service.users().getProfile(userId='me').execute()
            return True
        except Exception:
            return False
    
    def get_profile(self) -> dict:
        """사용자 프로필 가져오기"""
        return self.service.users().getProfile(userId='me').execute()
    
    def _reconnect(self, silent=False):
        """연결 재시도"""
        if not silent:
            print("[Gmail] 연결 재시도 중...")
        import socket
        socket.setdefaulttimeout(120)
        # 새로운 서비스 객체 생성 (기존 연결 완전히 폐기)
        self.service = build('gmail', 'v1', credentials=self.creds, cache_discovery=False)
        if not silent:
            print("[Gmail] 재연결 성공")
    
    def get_messages(self, query: str = None, max_results: int = 10) -> list:
        """
        메시지 목록 가져오기
        
        Args:
            query: 검색 쿼리 (예: "is:unread", "from:example@gmail.com")
            max_results: 최대 결과 수
        
        Returns:
            메시지 목록
        """
        # 최대 3번 재시도
        for attempt in range(3):
            try:
                params = {
                    'userId': 'me',
                    'maxResults': max_results
                }
                if query:
                    params['q'] = query
                
                response = self.service.users().messages().list(**params).execute()
                messages = response.get('messages', [])
                break
            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                print(f"[Gmail] 연결 오류 (시도 {attempt + 1}/3): {e}")
                if attempt < 2:
                    self._reconnect()
                else:
                    print(f"[Gmail] 메시지 목록 가져오기 실패: {e}")
                    return []
            except Exception as e:
                print(f"[Gmail] 메시지 목록 가져오기 실패: {e}")
                return []
        
        try:
            
            # 각 메시지의 상세 정보 가져오기
            detailed_messages = []
            for msg in messages:
                detail = self.get_message(msg['id'])
                detailed_messages.append(detail)
            
            return detailed_messages
        
        except Exception as e:
            print(f"[Gmail] 메시지 목록 가져오기 실패: {e}")
            return []
    
    def get_message(self, message_id: str) -> dict:
        """
        메시지 상세 정보 가져오기
        
        Args:
            message_id: 메시지 ID
        
        Returns:
            파싱된 메시지 정보
        """
        # 최대 3번 재시도
        for attempt in range(3):
            try:
                message = self.service.users().messages().get(
                    userId='me', id=message_id, format='full'
                ).execute()
                
                return self._parse_message(message)
            
            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                if attempt < 2:
                    self._reconnect(silent=True)  # 조용히 재연결
                else:
                    print(f"[Gmail] 메시지 가져오기 최종 실패 ({message_id}): {e}")
                    return None
            except Exception as e:
                print(f"[Gmail] 메시지 가져오기 실패: {e}")
                return None
    
    def _parse_message(self, message: dict) -> dict:
        """메시지 파싱"""
        headers = message.get('payload', {}).get('headers', [])
        
        def get_header(name):
            for h in headers:
                if h['name'].lower() == name.lower():  # vj-ok: MIME 헤더 이름 — 프로토콜 식별자
                    return h['value']
            return ''
        
        # 본문 추출
        body = ''
        payload = message.get('payload', {})
        
        if 'body' in payload and payload['body'].get('data'):
            body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
        elif 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    if 'data' in part.get('body', {}):
                        body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                        break
                elif part['mimeType'] == 'text/html' and not body:
                    if 'data' in part.get('body', {}):
                        body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
        
        return {
            'id': message['id'],
            'thread_id': message['threadId'],
            'subject': get_header('Subject'),
            'from': get_header('From'),
            'to': get_header('To'),
            'date': get_header('Date'),
            'body': body,
            'snippet': message.get('snippet', ''),
            'label_ids': message.get('labelIds', [])
        }
    
    def send_message(self, to: str, subject: str, body: str, attachment_path: str = None) -> dict:
        """
        이메일 보내기
        
        Args:
            to: 수신자 이메일
            subject: 제목
            body: 본문
            attachment_path: 첨부파일 경로 (선택)
        
        Returns:
            전송된 메시지 정보
        """
        import time
        start_time = time.time()
        
        # 메시지 준비 (한 번만 수행)
        try:
            if attachment_path:
                # 파일 크기 확인
                file_size = Path(attachment_path).stat().st_size
                file_size_mb = file_size / (1024 * 1024)
                print(f"[Gmail] 첨부파일 크기: {file_size_mb:.2f}MB")
                
                message = MIMEMultipart()
                message.attach(MIMEText(body, 'html', 'utf-8'))
                
                # 첨부파일 추가
                import mimetypes
                filename = Path(attachment_path).name
                
                # MIME 타입 추측
                mime_type, _ = mimetypes.guess_type(attachment_path)
                if mime_type:
                    maintype, subtype = mime_type.split('/', 1)
                else:
                    maintype, subtype = 'application', 'octet-stream'
                
                print(f"[Gmail] 첨부파일 인코딩 중: {filename}")
                encode_start = time.time()
                
                with open(attachment_path, 'rb') as f:
                    part = MIMEBase(maintype, subtype)
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    
                    # RFC 2231 형식으로 한글 파일명 인코딩
                    from email.utils import encode_rfc2231
                    encoded_filename = encode_rfc2231(filename, 'utf-8')
                    part.add_header(
                        'Content-Disposition',
                        'attachment',
                        filename=('utf-8', '', filename)
                    )
                    message.attach(part)
                
                encode_time = time.time() - encode_start
                print(f"[Gmail] 첨부파일 인코딩 완료 ({encode_time:.1f}초)")
            else:
                message = MIMEText(body, 'html', 'utf-8')
            
            message['to'] = to
            message['subject'] = subject
            
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        
        except Exception as e:
            total_time = time.time() - start_time
            print(f"[Gmail] 메시지 준비 실패 ({total_time:.1f}초): {e}")
            raise
        
        # 전송 시도 (최대 3번 재시도)
        for attempt in range(3):
            try:
                print(f"[Gmail] 메시지 전송 중 (시도 {attempt+1}/3)...")
                send_start = time.time()
                
                result = self.service.users().messages().send(
                    userId='me',
                    body={'raw': raw}
                ).execute()
                
                send_time = time.time() - send_start
                total_time = time.time() - start_time
                
                print(f"[Gmail] 메시지 전송 성공: {result['id']} (전송 {send_time:.1f}초, 총 {total_time:.1f}초)")
                return result
            
            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                if attempt < 2:
                    print(f"[Gmail] 연결 오류 발생, 재시도 중... ({e})")
                    self._reconnect(silent=True)
                else:
                    total_time = time.time() - start_time
                    print(f"[Gmail] 메시지 전송 최종 실패 ({total_time:.1f}초): {e}")
                    raise
            
            except Exception as e:
                total_time = time.time() - start_time
                print(f"[Gmail] 메시지 전송 실패 ({total_time:.1f}초): {e}")
                raise
    
    def mark_as_read(self, message_id: str):
        """읽음으로 표시"""
        # 최대 3번 재시도
        for attempt in range(3):
            try:
                self.service.users().messages().modify(
                    userId='me',
                    id=message_id,
                    body={'removeLabelIds': ['UNREAD']}
                ).execute()
                return
            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                if attempt < 2:
                    self._reconnect(silent=True)
                else:
                    print(f"[Gmail] 읽음 표시 최종 실패 ({message_id}): {e}")
                    raise
            except Exception as e:
                print(f"[Gmail] 읽음 표시 실패: {e}")
                raise
    
    def get_unread_messages(self, max_results: int = 10) -> list:
        """읽지 않은 메시지 가져오기"""
        return self.get_messages(query='is:unread', max_results=max_results)


# 테스트용
if __name__ == "__main__":
    import yaml
    
    # 설정 로드
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    # Gmail 클라이언트 생성 및 인증
    gmail = GmailClient(config['gmail'])
    gmail.authenticate()
    
    # 프로필 출력
    profile = gmail.get_profile()
    print(f"\n로그인된 계정: {profile['emailAddress']}")
    
    # 최근 메시지 확인
    print("\n최근 메시지 5개:")
    messages = gmail.get_messages(max_results=5)
    for msg in messages:
        print(f"  - {msg['subject']} (from: {msg['from']})")
