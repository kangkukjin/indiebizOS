"""
channel_engine.py - IBL 채널 노드 실행 엔진

[others:channel_send]{channel_type: "gmail", to: "user@mail.com", subject: "제목", body: "내용"}
[others:channel_read]{channel_type: "gmail", max_results: 10}
[others:channel_search]{channel_type: "gmail", query: "from:someone"}

에이전트 identity 기반 발송:
- 외부 에이전트: 에이전트에 설정된 주소(email/nostr)를 사용
- 내부 에이전트: 외부 채널 사용 불가 (실패 반환)
- account 파라미터로 명시적 주소 지정 가능 (예: 사용자 이메일 확인)
"""

import os
import sys
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional


# === 지원 채널 ===
SUPPORTED_CHANNELS = ["gmail", "nostr"]


# === 에이전트 identity 조회 ===

def _resolve_agent_identity(channel_type: str, params: dict,
                            project_path: str, agent_id: str = None) -> dict:
    """
    채널 사용 시 에이전트의 identity를 결정한다.

    우선순위:
    1. params에 account가 명시되면 그 주소를 사용
    2. agent_id가 있으면 agents.yaml에서 해당 에이전트의 주소를 조회
    3. 둘 다 없으면 에러

    Returns:
        {"email": "..."} 또는 {"npub": "..."} 또는 {"error": "..."}
    """
    # 1) 명시적 account 지정
    account = params.get("account")
    if account:
        if channel_type == "gmail":
            return {"email": account}
        elif channel_type == "nostr":
            return {"npub": account}

    # 2) 에이전트 설정에서 조회
    if not agent_id:
        return {"error": "에이전트 정보가 없습니다. 채널 사용에는 에이전트 identity가 필요합니다."}

    agents_file = Path(project_path) / "agents.yaml"
    if not agents_file.exists():
        return {"error": f"agents.yaml을 찾을 수 없습니다: {agents_file}"}

    try:
        with open(agents_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        return {"error": f"agents.yaml 읽기 실패: {e}"}

    # 에이전트 찾기
    agent_config = None
    for agent in data.get("agents", []):
        if agent.get("id") == agent_id:
            agent_config = agent
            break

    if not agent_config:
        return {"error": f"에이전트 '{agent_id}'를 찾을 수 없습니다."}

    # 내부 에이전트 체크
    if agent_config.get("type") == "internal":
        return {"error": f"내부 에이전트 '{agent_id}'는 외부 채널을 사용할 수 없습니다."}

    # 채널별 주소 조회
    if channel_type == "gmail":
        email = agent_config.get("email")
        if not email:
            return {"error": f"에이전트 '{agent_id}'에 email이 설정되어 있지 않습니다."}
        return {"email": email}

    elif channel_type == "nostr":
        npub = agent_config.get("npub") or agent_config.get("nostr")
        if not npub:
            # nostr는 시스템 공용 identity를 fallback으로 사용
            return {"npub": None, "use_system": True}
        return {"npub": npub}

    return {"error": f"identity 조회 미지원 채널: {channel_type}"}


# === IBL 노드 액션 핸들러 (ibl_engine에서 호출) ===

def execute_channel_action(action: str, params: dict,
                           project_path: str, agent_id: str = None) -> Any:
    """
    ibl_engine에서 호출되는 채널 노드 액션 핸들러

    Args:
        action: send, read, search
        params: 액션별 파라미터 (channel_type 포함)
        project_path: 프로젝트 경로
        agent_id: 에이전트 ID (identity 결정에 사용)
    """
    channel_type_raw = params.get("channel_type", "")
    if not channel_type_raw:
        return {
            "error": "channel_type이 필요합니다.",
            "supported_channels": SUPPORTED_CHANNELS,
            "usage": {
                "send": '[others:channel_send]{channel_type: "gmail", to: "user@mail.com", subject: "제목", body: "내용"}',
                "read": '[others:channel_read]{channel_type: "gmail", max_results: 10}',
                "search": '[others:channel_search]{channel_type: "gmail", query: "from:someone"}',
            }
        }

    channel_type = channel_type_raw.lower().strip()
    if channel_type not in SUPPORTED_CHANNELS:
        return {
            "error": f"지원하지 않는 채널: {channel_type}",
            "supported_channels": SUPPORTED_CHANNELS
        }

    # 에이전트 identity 결정
    identity = _resolve_agent_identity(channel_type, params, project_path, agent_id)
    if "error" in identity:
        return {"success": False, "channel": channel_type, "error": identity["error"]}

    if action == "send":
        return _channel_send(channel_type, params, identity)
    elif action == "read":
        return _channel_read(channel_type, params, identity)
    elif action == "search":
        return _channel_search(channel_type, params, identity)
    else:
        return {
            "error": f"알 수 없는 채널 액션: {action}",
            "available_actions": ["send", "read", "search"]
        }


# === Gmail 클라이언트 ===

def _get_gmail_client(email: str = None):
    """Gmail 클라이언트 가져오기

    Args:
        email: 사용할 Gmail 주소. None이면 extension config에서 읽음.
    """
    from api_gmail import get_gmail_client_for_email

    if email:
        return get_gmail_client_for_email(email)

    # fallback: extension config
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
    default_email = gmail_config.get("email", "")
    if not default_email:
        raise Exception("Gmail 이메일 주소가 설정되지 않았습니다.")

    return get_gmail_client_for_email(default_email)


# === IndieNet ===

def _get_indienet():
    """IndieNet 싱글톤 가져오기"""
    from indienet import get_indienet
    indienet = get_indienet()
    if not indienet.is_initialized():
        raise Exception("IndieNet이 초기화되지 않았습니다. Nostr 설정을 먼저 완료하세요.")
    return indienet


# === 내부 구현 ===

def _channel_send(channel_type: str, params: dict, identity: dict) -> dict:
    """메시지 발송"""
    if channel_type == "gmail":
        to = params.get("to")
        subject = params.get("subject", "(제목 없음)")
        body = params.get("body", "")
        attachment_path = params.get("attachment_path")

        if not to:
            return {"error": "수신자(to) 이메일이 필요합니다."}

        try:
            client = _get_gmail_client(email=identity.get("email"))
            result = client.send_message(
                to=to, subject=subject, body=body,
                attachment_path=attachment_path
            )
            return {
                "success": True,
                "channel": "gmail",
                "from": identity.get("email"),
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


def _channel_read(channel_type: str, params: dict, identity: dict) -> dict:
    """메시지 읽기"""
    if channel_type == "gmail":
        query = params.get("query")
        max_results = params.get("max_results", 10)

        try:
            client = _get_gmail_client(email=identity.get("email"))
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
                "account": identity.get("email"),
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


def _channel_search(channel_type: str, params: dict, identity: dict) -> dict:
    """메시지 검색"""
    if channel_type == "gmail":
        query = params.get("query", "")
        max_results = params.get("max_results", 10)

        if not query:
            return {"error": "검색어(query)가 필요합니다."}

        try:
            client = _get_gmail_client(email=identity.get("email"))
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
                "account": identity.get("email"),
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
