"""
통화 관리 모듈
전화 걸기/끊기, 통화 기록 조회/삭제
"""

import sys
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

_current_dir = Path(__file__).parent
if str(_current_dir) not in sys.path:
    sys.path.insert(0, str(_current_dir))

from adb_core import run_adb


def make_call(phone_number: str, device_id: Optional[str] = None) -> dict:
    """전화 걸기"""
    phone_number = re.sub(r'[^\d+]', '', phone_number)

    result = run_adb([
        "shell", "am", "start", "-a", "android.intent.action.CALL",
        "-d", f"tel:{phone_number}"
    ], device_id)

    if not result["success"]:
        return result

    return {
        "success": True,
        "phone_number": phone_number,
        "message": f"{phone_number}에 전화를 겁니다."
    }


def end_call(device_id: Optional[str] = None) -> dict:
    """통화 종료"""
    result = run_adb(["shell", "input", "keyevent", "KEYCODE_ENDCALL"], device_id)

    if not result["success"]:
        return result

    return {
        "success": True,
        "message": "통화를 종료했습니다."
    }


def get_call_log(device_id: Optional[str] = None, limit: int = 50, call_type: str = "all", offset: int = 0) -> dict:
    """통화 기록 조회

    Args:
        call_type: all(전체), incoming(수신), outgoing(발신), missed(부재중)
        offset: 건너뛸 개수 (페이지네이션용)
    """
    result = run_adb([
        "shell", "content", "query",
        "--uri", "content://call_log/calls",
        "--projection", "_id:number:name:date:duration:type"
    ], device_id, timeout=30)

    if not result["success"]:
        return result

    calls = []
    type_map = {"1": "incoming", "2": "outgoing", "3": "missed", "4": "voicemail", "5": "rejected"}

    for line in result["stdout"].split("Row:"):
        if not line.strip():
            continue

        call = {}

        # 정규식으로 각 필드 추출
        id_match = re.search(r'_id=(\d+)', line)
        if id_match:
            call['_id'] = id_match.group(1)

        number_match = re.search(r'number=([^,]+?)(?:,\s*name=|,\s*date=|$)', line)
        if number_match:
            call['number'] = number_match.group(1).strip()

        name_match = re.search(r'name=([^,]*?)(?:,\s*date=|,\s*duration=|$)', line)
        if name_match:
            name_val = name_match.group(1).strip()
            if name_val and name_val.lower() != 'null':
                call['name'] = name_val

        date_match = re.search(r'date=(\d+)', line)
        if date_match:
            call['date'] = date_match.group(1)

        duration_match = re.search(r'duration=(\d+)', line)
        if duration_match:
            call['duration'] = duration_match.group(1)

        type_match = re.search(r'type=(\d+)', line)
        if type_match:
            call['type'] = type_match.group(1)

        if call.get("_id"):
            # 날짜 변환
            if call.get("date"):
                try:
                    timestamp = int(call["date"]) / 1000
                    call["date_formatted"] = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
                except:
                    call["date_formatted"] = call["date"]

            # 통화 유형 변환
            call["call_type"] = type_map.get(call.get("type", ""), "unknown")

            # 통화 시간 (초)
            if call.get("duration"):
                try:
                    duration = int(call["duration"])
                    call["duration_formatted"] = f"{duration // 60}분 {duration % 60}초"
                except:
                    pass

            # 필터링
            if call_type == "all" or call["call_type"] == call_type:
                calls.append(call)

    # 최신순 정렬
    calls = sorted(calls, key=lambda x: x.get("date", "0"), reverse=True)

    # 전체 개수 저장
    total_count = len(calls)

    # offset과 limit 적용
    calls = calls[offset:offset + limit]

    return {
        "success": True,
        "calls": calls,
        "count": len(calls),
        "total": total_count,
        "offset": offset,
        "has_more": offset + len(calls) < total_count,
        "message": f"전체 {total_count}개 중 {offset + 1}~{offset + len(calls)}번째" if calls else "통화 기록에 접근할 수 없습니다. Android 보안 정책으로 ADB를 통한 통화 기록 접근이 제한될 수 있습니다."
    }


def delete_call_log(call_id: str = None, device_id: Optional[str] = None) -> dict:
    """통화 기록 삭제"""
    if call_id:
        result = run_adb([
            "shell", "content", "delete",
            "--uri", "content://call_log/calls",
            "--where", f"_id={call_id}"
        ], device_id)
    else:
        return {"success": False, "message": "삭제할 통화 기록 ID를 지정하세요."}

    if not result["success"]:
        return result

    return {
        "success": True,
        "deleted_id": call_id,
        "message": f"통화 기록(ID: {call_id})이 삭제되었습니다."
    }
