"""
연락처 관리 모듈
연락처 조회, 검색, 삭제
"""

import sys
import re
from pathlib import Path
from typing import Optional

_current_dir = Path(__file__).parent
if str(_current_dir) not in sys.path:
    sys.path.insert(0, str(_current_dir))

from adb_core import run_adb


def get_contacts(device_id: Optional[str] = None, limit: int = 100, offset: int = 0) -> dict:
    """연락처 목록 조회

    Args:
        limit: 조회 개수
        offset: 건너뛸 개수 (페이지네이션용)
    """
    # Android 최신 버전은 com.android.contacts/data URI 사용
    result = run_adb([
        "shell", "content", "query",
        "--uri", "content://com.android.contacts/data",
        "--projection", "display_name:data1:mimetype"
    ], device_id, timeout=30)

    if not result["success"]:
        return result

    contacts = []
    seen_contacts = set()  # 중복 제거용

    for line in result["stdout"].split("Row:"):
        if not line.strip():
            continue

        # phone_v2 mimetype만 처리 (전화번호가 있는 항목)
        if "phone_v2" not in line:
            continue

        contact = {}

        # display_name 추출
        name_match = re.search(r'display_name=([^,]*?)(?:,\s*data1=|$)', line)
        if name_match:
            name_val = name_match.group(1).strip()
            if name_val and name_val.lower() != 'null':
                contact['display_name'] = name_val

        # data1 = 전화번호
        phone_match = re.search(r'data1=([^,]+?)(?:,\s*mimetype=|$)', line)
        if phone_match:
            contact['number'] = phone_match.group(1).strip()

        if contact.get("display_name") and contact.get("number"):
            # 중복 체크 (이름+번호 조합)
            key = f"{contact['display_name']}:{contact['number']}"
            if key not in seen_contacts:
                seen_contacts.add(key)
                contacts.append({
                    "id": str(len(contacts)),
                    "name": contact.get("display_name", "이름 없음"),
                    "phone": contact.get("number", "")
                })

    # 전체 개수 저장
    total_count = len(contacts)

    # offset과 limit 적용
    contacts = contacts[offset:offset + limit]

    return {
        "success": True,
        "contacts": contacts,
        "count": len(contacts),
        "total": total_count,
        "offset": offset,
        "has_more": offset + len(contacts) < total_count,
        "message": f"전체 {total_count}개 중 {offset + 1}~{offset + len(contacts)}번째" if contacts else f"{total_count}개의 연락처"
    }


def search_contacts(query: str, device_id: Optional[str] = None) -> dict:
    """연락처 검색"""
    all_contacts = get_contacts(device_id, limit=500)

    if not all_contacts["success"]:
        return all_contacts

    query_lower = query.lower()
    matched = []

    for contact in all_contacts["contacts"]:
        name = contact.get("name", "").lower()
        phone = contact.get("phone", "").lower()

        if query_lower in name or query_lower in phone:
            matched.append(contact)

    return {
        "success": True,
        "contacts": matched,
        "count": len(matched),
        "query": query,
        "message": f"'{query}' 검색 결과: {len(matched)}개"
    }


def delete_contact(contact_id: str = None, phone_number: str = None, device_id: Optional[str] = None) -> dict:
    """연락처 삭제

    Args:
        contact_id: 삭제할 연락처 ID (raw_contact_id)
        phone_number: 전화번호로 삭제 (contact_id가 없을 때 사용)
    """
    if not contact_id and not phone_number:
        return {"success": False, "message": "삭제할 연락처 ID 또는 전화번호를 지정하세요."}

    # 전화번호로 삭제하는 경우, 먼저 연락처를 찾아서 ID 확보
    if phone_number and not contact_id:
        # 전화번호로 raw_contact_id 찾기
        result = run_adb([
            "shell", "content", "query",
            "--uri", "content://com.android.contacts/data",
            "--projection", "raw_contact_id:data1",
            "--where", f"data1 LIKE '%{phone_number}%'"
        ], device_id, timeout=15)

        if not result["success"]:
            return result

        # raw_contact_id 추출
        match = re.search(r'raw_contact_id=(\d+)', result.get("stdout", ""))
        if not match:
            return {"success": False, "message": f"전화번호 '{phone_number}'에 해당하는 연락처를 찾을 수 없습니다."}

        contact_id = match.group(1)

    # raw_contacts에서 삭제 (연관된 모든 데이터도 함께 삭제됨)
    result = run_adb([
        "shell", "content", "delete",
        "--uri", f"content://com.android.contacts/raw_contacts/{contact_id}"
    ], device_id, timeout=15)

    if not result["success"]:
        return result

    return {
        "success": True,
        "deleted_id": contact_id,
        "phone_number": phone_number,
        "message": f"연락처(ID: {contact_id})가 삭제되었습니다."
    }
