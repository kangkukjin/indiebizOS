"""
channel_engine.py - IBL 채널 노드 실행 엔진

IBL Phase 2의 핵심.
[channel:send](gmail) { to, subject, body }
[channel:read](nostr) { limit, since }
[channel:search](gmail) { query, max_results }

기존 Gmail, Nostr(IndieNet) 인프라에 위임합니다.
"""

import os
import sys
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional


# === 지원 채널 ===
SUPPORTED_CHANNELS = ["gmail", "nostr"]


# === IBL 노드 액션 핸들러 (ibl_engine에서 호출) ===

def execute_channel_action(action: str, target: str, params: dict,
                           project_path: str) -> Any:
    """
    ibl_engine에서 호출되는 채널 노드 액션 핸들러

    Args:
        action: send, read, search
        target: 채널 타입 (gmail, nostr)
        params: 액션별 파라미터
        project_path: 프로젝트 경로
    """
    if not target:
        return {
            "error": "채널 타입(target)이 필요합니다.",
            "supported_channels": SUPPORTED_CHANNELS,
            "usage": {
                "send": '[channel:send](gmail) { "to": "user@mail.com", "subject": "제목", "body": "내용" }',
                "read": '[channel:read](gmail) { "max_results": 10 }',
                "search": '[channel:search](gmail) { "query": "from:someone" }',
            }
        }

    channel_type = target.lower().strip()
    if channel_type not in SUPPORTED_CHANNELS:
        return {
            "error": f"지원하지 않는 채널: {channel_type}",
            "supported_channels": SUPPORTED_CHANNELS
        }

    if action == "send":
        return _channel_send(channel_type, params)
    elif action == "read":
        return _channel_read(channel_type, params)
    elif action == "search":
        return _channel_search(channel_type, params)
    else:
        return {
            "error": f"알 수 없는 채널 액션: {action}",
            "available_actions": ["send", "read", "search"]
        }


# === Gmail 클라이언트 ===

def _get_gmail_client():
    """Gmail 클라이언트 가져오기 (api_gmail 재사용)"""
    # Gmail 확장 경로 추가
    env_path = os.environ.get("INDIEBIZ_BASE_PATH")
    if env_path:
        base = Path(env_path)
    else:
        base = Path(__file__).parent.parent

    gmail_ext_path = base / "data" / "packages" / "installed" / "extensions" / "gmail"
    config_path = gmail_ext_path / "config.yaml"

    if not config_path.exists():
        raise Exception("Gmail config.yaml이 없습니다. Gmail 채널 설정을 먼저 완료하세요.")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    gmail_config = config.get("gmail", {})
    email = gmail_config.get("email", "")
    if not email:
        raise Exception("Gmail 이메일 주소가 설정되지 않았습니다.")

    from api_gmail import get_gmail_client_for_email
    return get_gmail_client_for_email(email)


# === IndieNet ===

def _get_indienet():
    """IndieNet 싱글톤 가져오기"""
    from indienet import get_indienet
    indienet = get_indienet()
    if not indienet.is_initialized():
        raise Exception("IndieNet이 초기화되지 않았습니다. Nostr 설정을 먼저 완료하세요.")
    return indienet


# === 내부 구현 ===

def _channel_send(channel_type: str, params: dict) -> dict:
    """메시지 발송"""
    if channel_type == "gmail":
        to = params.get("to")
        subject = params.get("subject", "(제목 없음)")
        body = params.get("body", "")
        attachment_path = params.get("attachment_path")

        if not to:
            return {"error": "수신자(to) 이메일이 필요합니다."}

        try:
            client = _get_gmail_client()
            result = client.send_message(
                to=to, subject=subject, body=body,
                attachment_path=attachment_path
            )
            return {
                "success": True,
                "channel": "gmail",
                "message_id": result.get("id"),
                "thread_id": result.get("threadId"),
                "to": to,
                "subject": subject
            }
        except Exception as e:
            return {"success": False, "channel": "gmail", "error": str(e)}

    elif channel_type == "nostr":
        to = params.get("to") or params.get("to_pubkey")
        content = params.get("content") or params.get("body", "")

        if not to:
            return {"error": "수신자 공개키(to)가 필요합니다. (npub 또는 hex 형식)"}
        if not content:
            return {"error": "메시지 내용(content)이 필요합니다."}

        try:
            indienet = _get_indienet()
            event_id = indienet.send_dm(to_pubkey=to, content=content)
            if event_id:
                return {
                    "success": True,
                    "channel": "nostr",
                    "event_id": event_id,
                    "to": to[:20] + "..."
                }
            return {"success": False, "channel": "nostr", "error": "DM 전송 실패"}
        except Exception as e:
            return {"success": False, "channel": "nostr", "error": str(e)}

    return {"error": f"send 미지원 채널: {channel_type}"}


def _channel_read(channel_type: str, params: dict) -> dict:
    """메시지 읽기"""
    if channel_type == "gmail":
        query = params.get("query")
        max_results = params.get("max_results", 10)

        try:
            client = _get_gmail_client()
            messages = client.get_messages(query=query, max_results=max_results)

            simplified = []
            for msg in messages:
                if msg is None:
                    continue
                simplified.append({
                    "id": msg.get("id"),
                    "subject": msg.get("subject", ""),
                    "from": msg.get("from", ""),
                    "date": msg.get("date", ""),
                    "snippet": msg.get("snippet", ""),
                    "body": (msg.get("body") or "")[:500],
                })

            return {
                "success": True,
                "channel": "gmail",
                "count": len(simplified),
                "query": query,
                "messages": simplified
            }
        except Exception as e:
            return {"success": False, "channel": "gmail", "error": str(e)}

    elif channel_type == "nostr":
        limit = params.get("limit", 20)
        since = params.get("since")

        try:
            indienet = _get_indienet()
            dms = indienet.fetch_dms(limit=limit, since=since)
            return {
                "success": True,
                "channel": "nostr",
                "count": len(dms),
                "messages": dms
            }
        except Exception as e:
            return {"success": False, "channel": "nostr", "error": str(e)}

    return {"error": f"read 미지원 채널: {channel_type}"}


def _channel_search(channel_type: str, params: dict) -> dict:
    """메시지 검색"""
    if channel_type == "gmail":
        query = params.get("query", "")
        max_results = params.get("max_results", 10)

        if not query:
            return {"error": "검색어(query)가 필요합니다."}

        try:
            client = _get_gmail_client()
            messages = client.get_messages(query=query, max_results=max_results)

            simplified = []
            for msg in messages:
                if msg is None:
                    continue
                simplified.append({
                    "id": msg.get("id"),
                    "subject": msg.get("subject", ""),
                    "from": msg.get("from", ""),
                    "date": msg.get("date", ""),
                    "snippet": msg.get("snippet", "")
                })

            return {
                "success": True,
                "channel": "gmail",
                "query": query,
                "count": len(simplified),
                "messages": simplified
            }
        except Exception as e:
            return {"success": False, "channel": "gmail", "error": str(e)}

    elif channel_type == "nostr":
        query_text = params.get("query", "")
        limit = params.get("max_results", 20)

        if not query_text:
            return {"error": "검색어(query)가 필요합니다."}

        try:
            from business_manager import BusinessManager
            bm = BusinessManager()
            all_msgs = bm.get_messages(limit=limit * 3)

            matched = []
            for msg in all_msgs:
                if msg.get("contact_type") != "nostr":
                    continue
                content = (msg.get("content") or "") + " " + (msg.get("subject") or "")
                if query_text.lower() in content.lower():
                    matched.append({
                        "id": msg.get("id"),
                        "from": msg.get("contact_value", ""),
                        "content": (msg.get("content") or "")[:300],
                        "date": msg.get("message_time", "")
                    })
                    if len(matched) >= limit:
                        break

            return {
                "success": True,
                "channel": "nostr",
                "query": query_text,
                "count": len(matched),
                "messages": matched,
                "note": "Nostr 검색은 로컬 DB에서 수행됩니다."
            }
        except Exception as e:
            return {"success": False, "channel": "nostr", "error": str(e)}

    return {"error": f"search 미지원 채널: {channel_type}"}
