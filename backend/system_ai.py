"""
system_ai.py - 시스템 AI 도구 로딩 유틸리티
IndieBiz OS Core

시스템 AI가 사용하는 도구를 패키지에서 동적으로 로딩합니다.
"""

import json
import traceback
from pathlib import Path
from typing import List, Dict

from ai_agent import execute_tool as execute_package_tool

# 경로 설정
BACKEND_PATH = Path(__file__).parent
from runtime_utils import get_base_path as _get_base_path
DATA_PATH = _get_base_path() / "data"
INSTALLED_TOOLS_PATH = DATA_PATH / "packages" / "installed" / "tools"

# 시스템 AI 기본 패키지 목록
SYSTEM_AI_DEFAULT_PACKAGES = ["system_essentials", "python-exec", "nodejs", "cloudflare"]


# ============ 메시징 도구 정의 ============

MESSAGING_TOOLS = [
    {
        "name": "send_nostr_message",
        "description": """Nostr DM(다이렉트 메시지)을 전송합니다.

## 사용 시점
- 사용자가 특정 Nostr 주소로 메시지를 보내라고 요청할 때
- npub 주소 또는 hex 공개키로 메시지 전송

## 이웃 연동
- 수신자 주소로 이웃 DB를 검색하여 기존 이웃이면 해당 이웃에게 보낸 것으로 기록
- 이웃이 없으면 새 이웃을 자동 생성하여 기록""",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "수신자 Nostr 공개키 (npub... 또는 hex 형식)"
                },
                "message": {
                    "type": "string",
                    "description": "전송할 메시지 내용"
                }
            },
            "required": ["to", "message"]
        }
    },
    {
        "name": "send_gmail_message",
        "description": """Gmail로 이메일을 전송합니다.

## 사용 시점
- 사용자가 특정 이메일 주소로 메일을 보내라고 요청할 때
- 파일을 첨부하여 보낼 때는 attachment_path에 절대 경로를 지정

## 이웃 연동
- 수신자 이메일로 이웃 DB를 검색하여 기존 이웃이면 해당 이웃에게 보낸 것으로 기록
- 이웃이 없으면 새 이웃을 자동 생성하여 기록""",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "수신자 이메일 주소"
                },
                "subject": {
                    "type": "string",
                    "description": "이메일 제목"
                },
                "message": {
                    "type": "string",
                    "description": "이메일 본문 내용"
                },
                "attachment_path": {
                    "type": "string",
                    "description": "첨부할 파일의 절대 경로 (선택)"
                }
            },
            "required": ["to", "subject", "message"]
        }
    }
]


def get_messaging_tools() -> List[Dict]:
    """메시징 도구 정의 반환"""
    return MESSAGING_TOOLS


# ============ 메시징 도구 실행 ============

def _get_or_create_neighbor(contact_type: str, contact_value: str) -> int:
    """이웃을 찾거나 새로 생성하여 neighbor_id 반환"""
    from business_manager import BusinessManager
    bm = BusinessManager()

    neighbor = bm.find_neighbor_by_contact(contact_type, contact_value)
    if neighbor:
        return neighbor['id'], neighbor.get('name', ''), False

    # 새 이웃 생성
    if contact_type == 'gmail':
        # 이메일에서 이름 추출 (@ 앞 부분)
        name = contact_value.split('@')[0]
    else:
        # Nostr: 공개키 앞 8자리로 이름
        name = f"nostr_{contact_value[:8]}"

    new_neighbor = bm.create_neighbor(name=name, info_level=0)
    neighbor_id = new_neighbor['id']

    # 연락처 추가
    bm.add_contact(neighbor_id, contact_type, contact_value)

    return neighbor_id, name, True


def _record_sent_message(contact_type: str, contact_value: str, subject: str,
                         content: str, neighbor_id: int):
    """business.db에 발신 메시지 기록"""
    from business_manager import BusinessManager
    bm = BusinessManager()

    bm.create_message(
        content=content,
        contact_type=contact_type,
        contact_value=contact_value,
        subject=subject,
        neighbor_id=neighbor_id,
        is_from_user=1,  # 발신 메시지
        status='sent'
    )


def execute_send_nostr_message(tool_input: dict) -> str:
    """send_nostr_message 실행 - IndieNet identity 키로 Nostr DM 전송"""
    to = tool_input.get("to", "").strip()
    message = tool_input.get("message", "")

    if not to or not message:
        return json.dumps({"success": False, "error": "to, message 필수"}, ensure_ascii=False)

    try:
        from indienet import get_indienet
        indienet = get_indienet()

        if not indienet._initialized:
            return json.dumps({
                "success": False,
                "error": "IndieNet이 초기화되어 있지 않습니다. IndieNet 설정을 확인하세요."
            }, ensure_ascii=False)

        # IndieNet identity 키로 Nostr DM 전송
        event_id = indienet.send_dm(to_pubkey=to, content=message)

        if not event_id:
            return json.dumps({
                "success": False,
                "error": "Nostr DM 전송에 실패했습니다."
            }, ensure_ascii=False)

        # 이웃 DB 연동
        neighbor_id, neighbor_name, is_new = _get_or_create_neighbor('nostr', to)
        _record_sent_message('nostr', to, '', message, neighbor_id)

        result = {
            "success": True,
            "message": "Nostr DM 전송 완료",
            "event_id": event_id,
            "to": to[:20] + "...",
            "neighbor": neighbor_name,
            "new_neighbor": is_new
        }
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        traceback.print_exc()
        return json.dumps({"success": False, "error": f"Nostr DM 전송 실패: {str(e)}"}, ensure_ascii=False)


def execute_send_gmail_message(tool_input: dict) -> str:
    """send_gmail_message 실행 - Gmail 확장의 인증된 클라이언트로 전송"""
    to = tool_input.get("to", "").strip()
    subject = tool_input.get("subject", "")
    message = tool_input.get("message", "")
    attachment_path = tool_input.get("attachment_path", "").strip() or None

    if not to or not message:
        return json.dumps({"success": False, "error": "to, message 필수"}, ensure_ascii=False)

    # 첨부 파일 존재 확인
    if attachment_path and not Path(attachment_path).exists():
        return json.dumps({
            "success": False,
            "error": f"첨부 파일을 찾을 수 없습니다: {attachment_path}"
        }, ensure_ascii=False)

    try:
        # channel_poller의 인증된 Gmail 클라이언트 사용
        from channel_poller import _poller_instance as poller

        if poller and poller._gmail_client:
            poller._gmail_client.send_message(to=to, subject=subject, body=message,
                                               attachment_path=attachment_path)
        else:
            # fallback: Gmail 확장에서 직접 클라이언트 초기화
            import yaml
            from gmail import GmailClient

            gmail_ext_path = DATA_PATH / "packages" / "installed" / "extensions" / "gmail"
            config_path = gmail_ext_path / "config.yaml"

            if not config_path.exists():
                return json.dumps({
                    "success": False,
                    "error": "Gmail 설정(config.yaml)이 없습니다."
                }, ensure_ascii=False)

            with open(config_path) as f:
                config = yaml.safe_load(f)

            gmail_config = config.get('gmail', {})
            client = GmailClient(gmail_config)
            client.authenticate()
            client.send_message(to=to, subject=subject, body=message,
                                attachment_path=attachment_path)

        # 이웃 DB 연동
        neighbor_id, neighbor_name, is_new = _get_or_create_neighbor('gmail', to)
        _record_sent_message('gmail', to, subject, message, neighbor_id)

        result = {
            "success": True,
            "message": "이메일 전송 완료" + (f" (첨부: {Path(attachment_path).name})" if attachment_path else ""),
            "to": to,
            "subject": subject,
            "neighbor": neighbor_name,
            "new_neighbor": is_new
        }
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        traceback.print_exc()
        return json.dumps({"success": False, "error": f"이메일 전송 실패: {str(e)}"}, ensure_ascii=False)


# ============ 패키지 도구 로딩 ============

def load_tools_from_packages(package_names: List[str] = None) -> List[Dict]:
    """
    설치된 패키지에서 도구 정의 로드

    Args:
        package_names: 로드할 패키지 이름 목록 (None이면 기본 패키지)

    Returns:
        도구 정의 목록
    """
    if package_names is None:
        package_names = SYSTEM_AI_DEFAULT_PACKAGES

    tools = []

    for pkg_name in package_names:
        pkg_path = INSTALLED_TOOLS_PATH / pkg_name / "tool.json"
        if pkg_path.exists():
            try:
                with open(pkg_path, 'r', encoding='utf-8') as f:
                    pkg_data = json.load(f)

                    # tools 배열이 있으면 여러 도구 패키지
                    if "tools" in pkg_data:
                        for tool in pkg_data["tools"]:
                            tools.append(tool)
                    # 단일 도구 패키지 (name 필드가 있으면)
                    elif "name" in pkg_data:
                        tools.append(pkg_data)
            except Exception as e:
                print(f"[시스템AI] 패키지 로드 실패 {pkg_name}: {e}")

    return tools


def execute_system_tool(tool_name: str, tool_input: dict, work_dir: str = ".") -> str:
    """
    시스템 AI 도구 실행 - 모든 도구를 패키지에서 동적 로딩
    """
    return execute_package_tool(tool_name, tool_input, work_dir)
