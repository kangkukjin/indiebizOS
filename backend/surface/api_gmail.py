"""
api_gmail.py - Gmail 채널 API
IndieBiz OS Core
"""

import sys
from pathlib import Path
from typing import Dict, Any, Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Gmail 확장 경로 추가
from runtime_utils import get_base_path as _get_base_path
GMAIL_PATH = _get_base_path() / "data" / "packages" / "installed" / "extensions" / "gmail"
sys.path.insert(0, str(GMAIL_PATH))

router = APIRouter()

# Gmail 클라이언트 인스턴스 캐시
_gmail_clients: Dict[str, Any] = {}


class GmailConfig(BaseModel):
    client_id: str
    client_secret: str
    email: Optional[str] = None
    project_id: Optional[str] = None
    token_file: Optional[str] = "tokens/token.json"


class SendEmailRequest(BaseModel):
    to: str
    subject: str
    body: str
    attachment_path: Optional[str] = None


def get_gmail_client(config: dict, client_key: str = "default"):
    """Gmail 클라이언트 가져오기 (캐시 사용)"""
    global _gmail_clients

    if client_key not in _gmail_clients:
        try:
            from gmail import GmailClient
            client = GmailClient(config)
            client.authenticate()
            _gmail_clients[client_key] = client
        except ImportError as e:
            raise HTTPException(status_code=500, detail=f"Gmail 모듈 로드 실패: {e}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Gmail 인증 실패: {e}")

    return _gmail_clients[client_key]


def get_gmail_client_for_email(email: str):
    """
    특정 이메일 주소용 Gmail 클라이언트 반환.
    공통 OAuth 설정(config.yaml)을 사용하고, 이메일별 토큰 파일 사용.
    에이전트, 시스템 AI 등 어디서든 사용 가능.
    """
    global _gmail_clients

    if email in _gmail_clients:
        return _gmail_clients[email]

    import yaml

    # 공통 OAuth 설정 로드
    config_path = GMAIL_PATH / "config.yaml"
    if not config_path.exists():
        raise Exception("Gmail config.yaml 없음. 먼저 Gmail 채널 설정을 완료하세요.")

    with open(config_path) as f:
        config = yaml.safe_load(f)

    gmail_config = config.get('gmail', {})
    if not gmail_config.get('client_id') or not gmail_config.get('client_secret'):
        raise Exception("Gmail OAuth 설정 없음. 먼저 Gmail 채널 설정을 완료하세요.")

    # 이메일 지정 (토큰 파일명으로 사용됨)
    gmail_config['email'] = email

    from gmail import GmailClient
    client = GmailClient(gmail_config)
    client.authenticate()
    _gmail_clients[email] = client

    return client


@router.get("/gmail/status")
async def get_gmail_status():
    """Gmail 확장 상태 확인"""
    gmail_py = GMAIL_PATH / "gmail.py"
    return {
        "installed": gmail_py.exists(),
        "path": str(GMAIL_PATH),
        "clients_cached": len(_gmail_clients)
    }


@router.post("/gmail/auth")
async def authenticate_gmail(config: GmailConfig):
    """Gmail 인증 (OAuth 플로우 시작)"""
    try:
        client = get_gmail_client(config.model_dump(), config.email or "default")
        profile = client.get_profile()
        return {
            "status": "authenticated",
            "email": profile.get("emailAddress"),
            "messages_total": profile.get("messagesTotal")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gmail/profile")
async def get_gmail_profile(client_key: str = "default"):
    """Gmail 프로필 조회"""
    if client_key not in _gmail_clients:
        raise HTTPException(status_code=400, detail="먼저 인증이 필요합니다")

    try:
        client = _gmail_clients[client_key]
        profile = client.get_profile()
        return {
            "email": profile.get("emailAddress"),
            "messages_total": profile.get("messagesTotal"),
            "threads_total": profile.get("threadsTotal")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gmail/messages")
async def get_gmail_messages(
    client_key: str = "default",
    query: Optional[str] = None,
    max_results: int = 10
):
    """Gmail 메시지 목록 조회"""
    if client_key not in _gmail_clients:
        raise HTTPException(status_code=400, detail="먼저 인증이 필요합니다")

    try:
        client = _gmail_clients[client_key]
        messages = client.get_messages(query=query, max_results=max_results)
        return {"messages": messages, "count": len(messages)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gmail/messages/unread")
async def get_unread_messages(client_key: str = "default", max_results: int = 10):
    """읽지 않은 메시지 조회"""
    if client_key not in _gmail_clients:
        raise HTTPException(status_code=400, detail="먼저 인증이 필요합니다")

    try:
        client = _gmail_clients[client_key]
        messages = client.get_unread_messages(max_results=max_results)
        return {"messages": messages, "count": len(messages)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gmail/messages/{message_id}")
async def get_gmail_message(message_id: str, client_key: str = "default"):
    """특정 메시지 조회"""
    if client_key not in _gmail_clients:
        raise HTTPException(status_code=400, detail="먼저 인증이 필요합니다")

    try:
        client = _gmail_clients[client_key]
        message = client.get_message(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다")
        return message
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/gmail/messages/{message_id}/read")
async def mark_message_as_read(message_id: str, client_key: str = "default"):
    """메시지 읽음 처리"""
    if client_key not in _gmail_clients:
        raise HTTPException(status_code=400, detail="먼저 인증이 필요합니다")

    try:
        client = _gmail_clients[client_key]
        client.mark_as_read(message_id)
        return {"status": "marked_as_read", "message_id": message_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/gmail/send")
async def send_gmail(request: SendEmailRequest, client_key: str = "default"):
    """이메일 전송"""
    if client_key not in _gmail_clients:
        raise HTTPException(status_code=400, detail="먼저 인증이 필요합니다")

    try:
        client = _gmail_clients[client_key]
        result = client.send_message(
            to=request.to,
            subject=request.subject,
            body=request.body,
            attachment_path=request.attachment_path
        )
        return {
            "status": "sent",
            "message_id": result.get("id"),
            "thread_id": result.get("threadId")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/gmail/auth/{client_key}")
async def logout_gmail(client_key: str):
    """Gmail 로그아웃 (클라이언트 캐시 제거)"""
    global _gmail_clients

    if client_key in _gmail_clients:
        del _gmail_clients[client_key]
        return {"status": "logged_out", "client_key": client_key}

    raise HTTPException(status_code=404, detail="클라이언트를 찾을 수 없습니다")
