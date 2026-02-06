"""
SMS/MMS 관리 모듈
메시지 조회, 검색, 전송, 삭제
"""

import sys
import re
from pathlib import Path
from datetime import datetime
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

_current_dir = Path(__file__).parent
if str(_current_dir) not in sys.path:
    sys.path.insert(0, str(_current_dir))

from adb_core import run_adb


def get_sms_list(device_id: Optional[str] = None, box: str = "inbox", limit: int = 50, offset: int = 0) -> dict:
    """SMS 목록 조회

    Args:
        box: inbox(수신함), sent(발신함), all(전체)
        limit: 조회 개수
        offset: 건너뛸 개수 (페이지네이션용)
    """
    uri = f"content://sms/{box}" if box != "all" else "content://sms"

    result = run_adb([
        "shell", "content", "query",
        "--uri", uri,
        "--projection", "_id:address:body:date:read:type"
    ], device_id, timeout=30)

    if not result["success"]:
        return result

    messages = []
    # Row: 로 분리하여 각 행 처리
    for line in result["stdout"].split("Row:"):
        if not line.strip():
            continue

        msg = {}

        # _id 추출
        id_match = re.search(r'_id=(\d+)', line)
        if id_match:
            msg['_id'] = id_match.group(1)

        # address 추출 (body= 전까지)
        addr_match = re.search(r'address=([^,]+?)(?:,\s*body=|$)', line)
        if addr_match:
            msg['address'] = addr_match.group(1).strip()

        # date 추출
        date_match = re.search(r'date=(\d+)', line)
        if date_match:
            msg['date'] = date_match.group(1)

        # read 추출
        read_match = re.search(r'read=(\d+)', line)
        if read_match:
            msg['read'] = read_match.group(1)

        # type 추출
        type_match = re.search(r'type=(\d+)', line)
        if type_match:
            msg['type'] = type_match.group(1)

        # body 추출 (address와 date 사이의 모든 것)
        body_match = re.search(r'body=(.*?)(?:,\s*date=|,\s*read=|,\s*type=|,\s*thread_id=|$)', line, re.DOTALL)
        if body_match:
            msg['body'] = body_match.group(1).strip()

        if msg.get("_id"):
            # 날짜 변환 (밀리초 타임스탬프)
            if msg.get("date"):
                try:
                    timestamp = int(msg["date"]) / 1000
                    msg["date_formatted"] = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
                except:
                    msg["date_formatted"] = msg["date"]

            # type: 1=수신, 2=발신
            msg["direction"] = "received" if msg.get("type") == "1" else "sent"
            messages.append(msg)

    # 최신순 정렬
    messages = sorted(messages, key=lambda x: x.get("date", "0"), reverse=True)

    # 전체 개수 저장
    total_count = len(messages)

    # offset과 limit 적용
    messages = messages[offset:offset + limit]

    # content provider로 못 가져오면 알림에서 시도
    if total_count == 0:
        notif_result = get_sms_from_notifications(device_id)
        if notif_result.get("success") and notif_result.get("messages"):
            return notif_result

    return {
        "success": True,
        "messages": messages,
        "count": len(messages),
        "total": total_count,
        "offset": offset,
        "has_more": offset + len(messages) < total_count,
        "message": f"전체 {total_count}개 중 {offset + 1}~{offset + len(messages)}번째" if messages else "SMS 접근 권한이 없습니다. 폰에서 '설정 > 앱 > 특별한 앱 액세스 > 알림 액세스'에서 권한을 확인하세요."
    }


def get_sms_from_notifications(device_id: Optional[str] = None) -> dict:
    """알림에서 SMS 메시지 추출 (권한 우회용)"""
    result = run_adb(["shell", "dumpsys", "notification", "--noredact"], device_id, timeout=15)

    if not result["success"]:
        return result

    messages = []
    current_pkg = None
    current_title = None
    current_text = None

    # 메시지 앱 패키지들
    sms_packages = [
        "com.samsung.android.messaging",
        "com.google.android.apps.messaging",
        "com.android.mms",
        "com.skt.prod.dialer",
        "com.lge.message",
    ]

    lines = result["stdout"].split("\n")
    for i, line in enumerate(lines):
        line = line.strip()

        # 패키지명 찾기
        if "pkg=" in line:
            pkg_match = re.search(r"pkg=(\S+)", line)
            if pkg_match:
                current_pkg = pkg_match.group(1)

        # SMS 앱의 알림인 경우 내용 추출
        if current_pkg and any(p in current_pkg for p in sms_packages):
            if "android.title=" in line:
                title_match = re.search(r"android\.title=(.+?)(?:\s+android\.|$)", line)
                if title_match:
                    current_title = title_match.group(1).strip()

            if "android.text=" in line:
                text_match = re.search(r"android\.text=(.+?)(?:\s+android\.|$)", line)
                if text_match:
                    current_text = text_match.group(1).strip()

            # 제목과 텍스트 둘 다 있으면 메시지로 추가
            if current_title and current_text:
                messages.append({
                    "_id": f"notif_{len(messages)}",
                    "address": current_title,
                    "body": current_text,
                    "date_formatted": "알림에서 가져옴",
                    "direction": "received",
                    "source": "notification"
                })
                current_title = None
                current_text = None

    # 중복 제거
    seen = set()
    unique_messages = []
    for msg in messages:
        key = f"{msg['address']}:{msg['body']}"
        if key not in seen:
            seen.add(key)
            unique_messages.append(msg)

    return {
        "success": True,
        "messages": unique_messages[:50],
        "count": len(unique_messages),
        "message": f"알림에서 {len(unique_messages)}개의 메시지를 찾았습니다.",
        "source": "notifications"
    }


def _fetch_mms_address(args: tuple) -> tuple:
    """MMS 주소 조회 (병렬 처리용 헬퍼)"""
    mms_id, device_id = args
    addr_result = run_adb([
        "shell", "content", "query",
        "--uri", f"content://mms/{mms_id}/addr",
        "--projection", "address:type"
    ], device_id, timeout=5)

    if addr_result["success"]:
        for addr_line in addr_result["stdout"].split("Row:"):
            addr_match = re.search(r'address=([^,]+)', addr_line)
            if addr_match:
                addr = addr_match.group(1).strip()
                if addr and not addr.startswith("insert-address"):
                    return (mms_id, addr)
    return (mms_id, None)


def get_mms_list(device_id: Optional[str] = None, box: str = "inbox", limit: int = 50, offset: int = 0) -> dict:
    """MMS 목록 조회 - 최적화 버전 (ADB 2회 호출)

    Args:
        box: inbox(수신함), sent(발신함), all(전체)
        limit: 조회 개수
        offset: 건너뛸 개수 (페이지네이션용)
    """
    # MMS content provider에서 메타데이터 조회
    uri = "content://mms"
    if box == "inbox":
        uri = "content://mms/inbox"
    elif box == "sent":
        uri = "content://mms/sent"

    result = run_adb([
        "shell", "content", "query",
        "--uri", uri,
        "--projection", "_id:date:msg_box:thread_id"
    ], device_id, timeout=30)

    if not result["success"]:
        return result

    all_mms = []
    for line in result["stdout"].split("Row:"):
        if not line.strip():
            continue

        id_match = re.search(r'_id=(\d+)', line)
        if not id_match:
            continue

        mms = {"_id": id_match.group(1)}

        date_match = re.search(r'date=(\d+)', line)
        if date_match:
            mms['date'] = str(int(date_match.group(1)) * 1000)

        msgbox_match = re.search(r'msg_box=(\d+)', line)
        if msgbox_match:
            mms['msg_box'] = msgbox_match.group(1)
            mms['direction'] = "received" if mms['msg_box'] == "1" else "sent"

        thread_match = re.search(r'thread_id=(\d+)', line)
        if thread_match:
            mms['thread_id'] = thread_match.group(1)

        all_mms.append(mms)

    # 최신순 정렬
    all_mms = sorted(all_mms, key=lambda x: x.get("date", "0"), reverse=True)
    total_count = len(all_mms)

    # offset과 limit 적용
    target_mms = all_mms[offset:offset + limit]

    if not target_mms:
        return {
            "success": True,
            "messages": [],
            "count": 0,
            "total": total_count,
            "offset": offset,
            "has_more": False,
            "message": "MMS가 없거나 접근 권한이 없습니다."
        }

    target_ids = set(mms['_id'] for mms in target_mms)

    # 본문 조회 (1번의 ADB 호출) - 주소 조회 생략
    part_result = run_adb([
        "shell", "content", "query",
        "--uri", "content://mms/part",
        "--projection", "mid:ct:text"
    ], device_id, timeout=30)

    mid_body_map = {}
    if part_result["success"]:
        for part_line in part_result["stdout"].split("Row:"):
            mid_match = re.search(r'mid=(\d+)', part_line)
            if not mid_match or mid_match.group(1) not in target_ids:
                continue

            mid = mid_match.group(1)
            ct_match = re.search(r'ct=([^,]+)', part_line)
            text_match = re.search(r'text=(.+?)(?:,\s*mid=|,\s*ct=|$)', part_line, re.DOTALL)

            if text_match:
                text = text_match.group(1).strip()
                if text and text != "NULL":
                    ct = ct_match.group(1) if ct_match else ""
                    if "text/plain" in ct or mid not in mid_body_map:
                        mid_body_map[mid] = text

    # 결과 구성
    for mms in target_mms:
        mms_id = mms['_id']
        mms['body'] = mid_body_map.get(mms_id, "")
        mms['address'] = ""  # 주소 조회 생략 (속도 최적화)
        mms['message_type'] = 'mms'

        if mms.get("date"):
            try:
                mms["date_formatted"] = datetime.fromtimestamp(int(mms["date"]) / 1000).strftime("%Y-%m-%d %H:%M")
            except:
                mms["date_formatted"] = mms["date"]

    return {
        "success": True,
        "messages": target_mms,
        "count": len(target_mms),
        "total": total_count,
        "offset": offset,
        "has_more": offset + len(target_mms) < total_count,
        "message": f"MMS 전체 {total_count}개 중 {offset + 1}~{offset + len(target_mms)}번째" if target_mms else "MMS가 없거나 접근 권한이 없습니다."
    }


def get_all_messages(device_id: Optional[str] = None, box: str = "inbox", limit: int = 50, offset: int = 0) -> dict:
    """SMS와 MMS를 통합하여 조회 (최신순 정렬)

    최적화: 필요한 만큼만 조회하여 성능 향상

    Args:
        box: inbox(수신함), sent(발신함), all(전체)
        limit: 조회 개수
        offset: 건너뛸 개수 (페이지네이션용)
    """
    # 충분한 양 조회 (offset + limit의 2배 정도, 최소 200개)
    fetch_limit = max(200, (offset + limit) * 2)

    # SMS 조회
    sms_result = get_sms_list(device_id, box, limit=fetch_limit, offset=0)
    sms_messages = sms_result.get("messages", []) if sms_result.get("success") else []
    sms_total = sms_result.get("total", 0)

    # MMS 조회
    mms_result = get_mms_list(device_id, box, limit=fetch_limit, offset=0)
    mms_messages = mms_result.get("messages", []) if mms_result.get("success") else []
    mms_total = mms_result.get("total", 0)

    # SMS에 message_type 추가
    for msg in sms_messages:
        msg['message_type'] = 'sms'

    # 모든 메시지 합치기
    all_messages = sms_messages + mms_messages

    # 최신순 정렬
    all_messages = sorted(all_messages, key=lambda x: int(x.get("date", "0")), reverse=True)

    # 전체 개수 (실제 총 개수)
    total_count = sms_total + mms_total

    # offset과 limit 적용
    result_messages = all_messages[offset:offset + limit]

    return {
        "success": True,
        "messages": result_messages,
        "count": len(result_messages),
        "total": total_count,
        "offset": offset,
        "has_more": offset + len(result_messages) < total_count,
        "sms_total": sms_total,
        "mms_total": mms_total,
        "message": f"전체 {total_count}개 (SMS {sms_total}개 + MMS {mms_total}개) 중 {offset + 1}~{offset + len(result_messages)}번째"
    }


def send_sms(phone_number: str, message: str, device_id: Optional[str] = None) -> dict:
    """SMS 보내기"""
    import time

    # 전화번호 정리
    phone_number = re.sub(r'[^\d+]', '', phone_number)

    # SMS 앱 열기 + 메시지 입력
    result = run_adb([
        "shell", "am", "start", "-a", "android.intent.action.SENDTO",
        "-d", f"sms:{phone_number}",
        "--es", "sms_body", message
    ], device_id)

    if not result["success"]:
        return result

    # 잠시 대기 후 전송 버튼 클릭 (자동 전송)
    time.sleep(1)

    # 전송 버튼 클릭 시도 (기기마다 다를 수 있음)
    send_result = run_adb(["shell", "input", "keyevent", "KEYCODE_ENTER"], device_id)

    return {
        "success": True,
        "phone_number": phone_number,
        "message": message,
        "note": "SMS 앱이 열렸습니다. 자동 전송을 시도했지만, 기기에 따라 수동 전송이 필요할 수 있습니다."
    }


def delete_sms(
    sms_id: str = None,
    address: str = None,
    body_contains: str = None,
    before_date: str = None,
    dry_run: bool = False,
    device_id: Optional[str] = None
) -> dict:
    """SMS 삭제 (단일 또는 조건부 일괄 삭제)

    Args:
        sms_id: 특정 메시지 ID 삭제
        address: 특정 발신자의 모든 메시지 삭제
        body_contains: 본문에 특정 문자열이 포함된 메시지 삭제
        before_date: 특정 날짜 이전 메시지 삭제 (YYYY-MM-DD 형식)
        dry_run: True면 삭제하지 않고 대상만 조회 (미리보기)

    Examples:
        - sms_id="8389" → 해당 ID 메시지 1개 삭제
        - address="#CMAS#Severe" → 긴급재난문자 전체 삭제
        - body_contains="광고" → 본문에 "광고" 포함된 메시지 삭제
        - address="1588", body_contains="배송" → 1588번호 중 배송 관련만 삭제
    """
    # 조건이 하나도 없으면 에러
    if not any([sms_id, address, body_contains, before_date]):
        return {"success": False, "message": "삭제 조건을 지정하세요. (sms_id, address, body_contains, before_date 중 하나 이상)"}

    # 단일 ID 삭제
    if sms_id and not any([address, body_contains, before_date]):
        result = run_adb([
            "shell", "content", "delete",
            "--uri", f"content://sms/{sms_id}"
        ], device_id)

        if not result["success"]:
            return result

        return {
            "success": True,
            "deleted_count": 1,
            "deleted_id": sms_id,
            "message": f"문자 메시지(ID: {sms_id})가 삭제되었습니다."
        }

    # 조건부 삭제: WHERE 절 구성
    conditions = []

    if address:
        # 정확히 일치 또는 LIKE 패턴
        if '%' in address or '_' in address:
            conditions.append(f"address LIKE '{address}'")
        else:
            conditions.append(f"address='{address}'")

    if body_contains:
        conditions.append(f"body LIKE '%{body_contains}%'")

    if before_date:
        # YYYY-MM-DD를 밀리초 타임스탬프로 변환
        try:
            dt = datetime.strptime(before_date, "%Y-%m-%d")
            timestamp_ms = int(dt.timestamp() * 1000)
            conditions.append(f"date<{timestamp_ms}")
        except ValueError:
            return {"success": False, "message": f"날짜 형식 오류: {before_date} (YYYY-MM-DD 형식 사용)"}

    where_clause = " AND ".join(conditions)

    # 삭제 대상 미리 조회 (shell 내에서 전체 명령 실행)
    count_cmd = f'content query --uri content://sms --projection _id --where "{where_clause}"'
    count_result = run_adb(["shell", count_cmd], device_id, timeout=30)

    if not count_result["success"]:
        return count_result

    # 삭제 대상 개수 계산
    target_count = count_result.get("stdout", "").count("_id=")

    if target_count == 0:
        return {
            "success": True,
            "deleted_count": 0,
            "conditions": {"address": address, "body_contains": body_contains, "before_date": before_date},
            "message": "삭제 조건에 해당하는 메시지가 없습니다."
        }

    # dry_run이면 삭제 없이 대상만 반환
    if dry_run:
        # 샘플 몇 개 가져오기
        sample_cmd = f'content query --uri content://sms --projection _id:address:body:date --where "{where_clause}"'
        sample_result = run_adb(["shell", sample_cmd], device_id, timeout=30)

        samples = []
        if sample_result.get("success"):
            for line in sample_result.get("stdout", "").split("Row:")[:5]:
                if "_id=" in line:
                    samples.append(line.strip()[:100] + "...")

        return {
            "success": True,
            "dry_run": True,
            "target_count": target_count,
            "conditions": {"address": address, "body_contains": body_contains, "before_date": before_date},
            "samples": samples,
            "message": f"삭제 대상: {target_count}개. 실제 삭제하려면 dry_run=False로 호출하세요."
        }

    # 실제 삭제 실행
    delete_cmd = f'content delete --uri content://sms --where "{where_clause}"'
    result = run_adb(["shell", delete_cmd], device_id, timeout=60)

    if not result["success"]:
        return result

    return {
        "success": True,
        "deleted_count": target_count,
        "conditions": {"address": address, "body_contains": body_contains, "before_date": before_date},
        "message": f"{target_count}개의 문자 메시지가 삭제되었습니다."
    }


def _delete_single_message(args: tuple) -> tuple:
    """단일 메시지 삭제 (병렬 처리용 헬퍼)"""
    msg_id, msg_type, device_id = args
    uri = f"content://{msg_type}/{msg_id}"
    result = run_adb([
        "shell", "content", "delete",
        "--uri", uri
    ], device_id, timeout=10)
    return (msg_id, msg_type, result.get("success", False))


def delete_sms_by_ids(sms_ids: list = None, mms_ids: list = None, device_id: Optional[str] = None) -> dict:
    """SMS/MMS ID 목록으로 일괄 삭제 (병렬 처리)

    Args:
        sms_ids: 삭제할 SMS ID 목록
        mms_ids: 삭제할 MMS ID 목록

    Returns:
        삭제 결과
    """
    sms_ids = sms_ids or []
    mms_ids = mms_ids or []

    if not sms_ids and not mms_ids:
        return {"success": False, "message": "삭제할 ID 목록이 비어있습니다."}

    deleted_sms = 0
    deleted_mms = 0
    failed_ids = []

    # 삭제 작업 목록 생성
    tasks = []
    for sms_id in sms_ids:
        tasks.append((sms_id, "sms", device_id))
    for mms_id in mms_ids:
        tasks.append((mms_id, "mms", device_id))

    # 병렬 삭제 (최대 50개 동시)
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(_delete_single_message, task) for task in tasks]
        for future in as_completed(futures):
            try:
                msg_id, msg_type, success = future.result()
                if success:
                    if msg_type == "sms":
                        deleted_sms += 1
                    else:
                        deleted_mms += 1
                else:
                    failed_ids.append(msg_id)
            except Exception:
                pass

    total_deleted = deleted_sms + deleted_mms

    return {
        "success": True,
        "deleted_count": total_deleted,
        "deleted_sms": deleted_sms,
        "deleted_mms": deleted_mms,
        "sms_ids": sms_ids,
        "mms_ids": mms_ids,
        "failed_ids": failed_ids,
        "message": f"{total_deleted}개 메시지 삭제 (SMS {deleted_sms}개, MMS {deleted_mms}개)"
    }


def delete_mms_by_content(
    body_contains: str,
    dry_run: bool = True,
    device_id: Optional[str] = None
) -> dict:
    """SMS/MMS/RCS 본문 내용으로 조건부 삭제 - 빠른 버전

    Args:
        body_contains: 본문에 포함된 문자열 (필수)
        dry_run: True면 삭제 대상만 조회 (기본: True, 안전)
        device_id: 기기 ID

    Examples:
        - body_contains="Web발신", dry_run=True → 대상 개수 확인
        - body_contains="Web발신", dry_run=False → 실제 삭제
    """
    if not body_contains:
        return {"success": False, "message": "body_contains를 지정하세요."}

    query_lower = body_contains.lower()

    # ===== 1) SMS 검색 =====
    sms_matched = set()
    sms_result = run_adb([
        "shell", "content", "query",
        "--uri", "content://sms",
        "--projection", "_id:body"
    ], device_id, timeout=60)

    if sms_result.get("success"):
        for line in sms_result.get("stdout", "").split("Row:"):
            id_match = re.search(r'_id=(\d+)', line)
            body_match = re.search(r'body=(.+?)(?:,\s*_id=|$)', line, re.DOTALL)
            if id_match and body_match:
                body = body_match.group(1).strip()
                if body and query_lower in body.lower():
                    sms_matched.add(("sms", id_match.group(1)))

    # ===== 2) MMS 검색 =====
    mms_matched = set()
    part_result = run_adb([
        "shell", "content", "query",
        "--uri", "content://mms/part",
        "--projection", "mid:ct:text"
    ], device_id, timeout=60)

    if part_result.get("success"):
        for line in part_result.get("stdout", "").split("Row:"):
            mid_match = re.search(r'mid=(\d+)', line)
            text_match = re.search(r'text=(.+?)(?:,\s*mid=|,\s*ct=|$)', line, re.DOTALL)
            if mid_match and text_match:
                text = text_match.group(1).strip()
                if text and text != "NULL" and query_lower in text.lower():
                    mms_matched.add(("mms", mid_match.group(1)))

    # ===== 3) RCS/채팅+ 검색 (삼성폰) =====
    rcs_matched = set()
    rcs_result = run_adb([
        "shell", "content", "query",
        "--uri", "content://im/chat",
        "--projection", "_id:body"
    ], device_id, timeout=60)

    if rcs_result.get("success") and "Error" not in rcs_result.get("stdout", ""):
        for line in rcs_result.get("stdout", "").split("Row:"):
            id_match = re.search(r'_id=(\d+)', line)
            body_match = re.search(r'body=(.+?)(?:, display_notification_status=|, date_sent=|$)', line, re.DOTALL)
            if id_match and body_match:
                body = body_match.group(1).strip()
                if body and query_lower in body.lower():
                    rcs_matched.add(("rcs", id_match.group(1)))

    # 전체 매칭 결과
    all_matched = sms_matched | mms_matched | rcs_matched
    target_count = len(all_matched)

    if target_count == 0:
        return {
            "success": True,
            "deleted_count": 0,
            "body_contains": body_contains,
            "message": f"'{body_contains}' 포함된 메시지가 없습니다."
        }

    # dry_run이면 삭제 없이 대상만 반환
    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "target_count": target_count,
            "sms_count": len(sms_matched),
            "mms_count": len(mms_matched),
            "rcs_count": len(rcs_matched),
            "body_contains": body_contains,
            "message": f"삭제 대상: {target_count}개 (SMS {len(sms_matched)}개 + MMS {len(mms_matched)}개 + RCS {len(rcs_matched)}개). 실제 삭제하려면 dry_run=False로 호출하세요."
        }

    # ===== 실제 삭제 =====
    deleted_sms = 0
    deleted_mms = 0
    deleted_rcs = 0
    failed_ids = []

    def delete_one(item):
        msg_type, msg_id = item
        if msg_type == "rcs":
            # RCS는 content://im/chat/{id}
            result = run_adb([
                "shell", "content", "delete",
                "--uri", f"content://im/chat/{msg_id}"
            ], device_id, timeout=10)
        else:
            result = run_adb([
                "shell", "content", "delete",
                "--uri", f"content://{msg_type}/{msg_id}"
            ], device_id, timeout=10)
        return (msg_type, msg_id, result.get("success", False))

    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = {executor.submit(delete_one, item): item for item in all_matched}
        for future in as_completed(futures):
            try:
                msg_type, msg_id, success = future.result()
                if success:
                    if msg_type == "sms":
                        deleted_sms += 1
                    elif msg_type == "mms":
                        deleted_mms += 1
                    else:
                        deleted_rcs += 1
                else:
                    failed_ids.append(f"{msg_type}:{msg_id}")
            except:
                failed_ids.append(str(futures[future]))

    total_deleted = deleted_sms + deleted_mms + deleted_rcs

    return {
        "success": True,
        "deleted_count": total_deleted,
        "deleted_sms": deleted_sms,
        "deleted_mms": deleted_mms,
        "deleted_rcs": deleted_rcs,
        "failed_count": len(failed_ids),
        "body_contains": body_contains,
        "message": f"{total_deleted}개 삭제 완료 (SMS {deleted_sms}개 + MMS {deleted_mms}개 + RCS {deleted_rcs}개)" + (f" (실패: {len(failed_ids)}개)" if failed_ids else "")
    }


def delete_messages_by_ids(ids: list, device_id: Optional[str] = None) -> dict:
    """메시지 ID 목록으로 통합 삭제 (message_type으로 자동 분류)

    Args:
        ids: 삭제할 메시지 목록 [{"_id": "123", "message_type": "sms"}, ...]

    Returns:
        삭제 결과
    """
    if not ids:
        return {"success": False, "message": "삭제할 ID 목록이 비어있습니다."}

    # message_type으로 분류
    sms_ids = []
    mms_ids = []

    for item in ids:
        if isinstance(item, dict):
            msg_id = str(item.get("_id", ""))
            msg_type = item.get("message_type", "sms")
        else:
            # 단순 ID만 전달된 경우 SMS로 간주
            msg_id = str(item)
            msg_type = "sms"

        if msg_id:
            if msg_type == "mms":
                mms_ids.append(msg_id)
            else:
                sms_ids.append(msg_id)

    return delete_sms_by_ids(sms_ids=sms_ids, mms_ids=mms_ids, device_id=device_id)


def search_sms(query: str, device_id: Optional[str] = None, limit: int = 100, offset: int = 0) -> dict:
    """SMS + MMS 통합 검색 (번호 또는 내용) - 최적화 버전

    Args:
        query: 검색어
        device_id: 기기 ID
        limit: 조회 개수 (기본 100)
        offset: 건너뛸 개수 (페이지네이션용)
    """
    if not query or not query.strip():
        return {"success": False, "message": "검색어를 입력하세요."}

    query = query.strip()
    query_lower = query.lower()

    # 전화번호인 경우 하이픈/공백 제거한 버전도 검색
    normalized_query = re.sub(r'[-\s]', '', query)
    normalized_lower = normalized_query.lower()

    # ===== SMS 검색 (1번의 ADB 호출) =====
    result = run_adb([
        "shell", "content", "query",
        "--uri", "content://sms",
        "--projection", "_id:address:body:date:type"
    ], device_id, timeout=60)

    sms_messages = []
    if result.get("success"):
        for line in result.get("stdout", "").split("Row:"):
            if "_id=" not in line:
                continue

            id_match = re.search(r'_id=(\d+)', line)
            if not id_match:
                continue

            addr_match = re.search(r'address=([^,\n]+)', line)
            body_match = re.search(r'body=([^,]*?)(?:, date=|, type=|$)', line)
            date_match = re.search(r'date=(\d+)', line)
            type_match = re.search(r'type=(\d+)', line)

            address = addr_match.group(1).strip() if addr_match else ""
            body = body_match.group(1).strip() if body_match else ""

            # 검색어 매칭
            if not (query_lower in address.lower() or
                    query_lower in body.lower() or
                    normalized_lower in re.sub(r'[-\s]', '', address).lower()):
                continue

            msg = {
                "message_type": "sms",
                "_id": id_match.group(1),
                "address": address,
                "body": body
            }

            if date_match:
                timestamp_ms = int(date_match.group(1))
                msg["date"] = timestamp_ms
                try:
                    msg["date_formatted"] = datetime.fromtimestamp(timestamp_ms / 1000).strftime("%Y-%m-%d %H:%M")
                except:
                    msg["date_formatted"] = ""

            if type_match:
                msg["direction"] = "received" if type_match.group(1) == "1" else "sent"

            sms_messages.append(msg)

    # ===== MMS 검색 (2번의 ADB 호출로 최적화) =====
    # 1) MMS part에서 본문과 mid 한 번에 조회
    part_result = run_adb([
        "shell", "content", "query",
        "--uri", "content://mms/part",
        "--projection", "mid:ct:text"
    ], device_id, timeout=60)

    matched_mms = {}  # mid -> body
    if part_result.get("success"):
        for line in part_result.get("stdout", "").split("Row:"):
            mid_match = re.search(r'mid=(\d+)', line)
            ct_match = re.search(r'ct=([^,]+)', line)
            text_match = re.search(r'text=(.+?)(?:,\s*mid=|,\s*ct=|$)', line, re.DOTALL)

            if mid_match and text_match:
                mid = mid_match.group(1)
                text = text_match.group(1).strip()
                ct = ct_match.group(1).strip() if ct_match else ""

                if text and text != "NULL" and query_lower in text.lower():
                    # text/plain 우선
                    if "text/plain" in ct or mid not in matched_mms:
                        matched_mms[mid] = text

    # 2) 매칭된 MMS의 메타데이터만 조회 (주소 조회 생략 - 속도 최적화)
    mms_messages = []
    if matched_mms:
        mms_result = run_adb([
            "shell", "content", "query",
            "--uri", "content://mms",
            "--projection", "_id:date:msg_box"
        ], device_id, timeout=30)

        if mms_result.get("success"):
            for line in mms_result.get("stdout", "").split("Row:"):
                id_match = re.search(r'_id=(\d+)', line)
                if id_match:
                    mms_id = id_match.group(1)
                    if mms_id in matched_mms:
                        date_match = re.search(r'date=(\d+)', line)
                        msgbox_match = re.search(r'msg_box=(\d+)', line)

                        timestamp = int(date_match.group(1)) * 1000 if date_match else 0
                        msg = {
                            "_id": mms_id,
                            "message_type": "mms",
                            "body": matched_mms[mms_id],
                            "address": "",  # 주소 조회 생략 (속도 최적화)
                            "date": timestamp,
                            "direction": "received" if msgbox_match and msgbox_match.group(1) == "1" else "sent"
                        }
                        if timestamp:
                            try:
                                msg["date_formatted"] = datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d %H:%M")
                            except:
                                msg["date_formatted"] = ""
                        mms_messages.append(msg)

    # ===== RCS/채팅+ 검색 (삼성폰 전용, 1번의 ADB 호출) =====
    rcs_messages = []
    rcs_result = run_adb([
        "shell", "content", "query",
        "--uri", "content://im/chat",
        "--projection", "_id:address:body:date:type"
    ], device_id, timeout=60)

    if rcs_result.get("success") and "Error" not in rcs_result.get("stdout", ""):
        for line in rcs_result.get("stdout", "").split("Row:"):
            if "_id=" not in line:
                continue

            id_match = re.search(r'_id=(\d+)', line)
            if not id_match:
                continue

            addr_match = re.search(r'address=([^,\n]+)', line)
            # RCS body는 JSON일 수 있음 - 전체 body 추출
            body_match = re.search(r'body=(.+?)(?:, display_notification_status=|, date_sent=|$)', line, re.DOTALL)
            date_match = re.search(r'date=(\d+)', line)
            type_match = re.search(r'type=(\d+)', line)

            address = addr_match.group(1).strip() if addr_match else ""
            body_raw = body_match.group(1).strip() if body_match else ""

            # RCS body에서 실제 텍스트 추출 (JSON인 경우)
            body = body_raw
            if body_raw.startswith("{"):
                # JSON에서 텍스트 추출 시도
                text_in_json = re.search(r'"text"\s*:\s*"([^"]+)"', body_raw)
                if text_in_json:
                    body = text_in_json.group(1)

            # 검색어 매칭
            if not (query_lower in address.lower() or
                    query_lower in body.lower() or
                    normalized_lower in re.sub(r'[-\s]', '', address).lower()):
                continue

            msg = {
                "message_type": "rcs",
                "_id": id_match.group(1),
                "address": address,
                "body": body[:500] if len(body) > 500 else body  # RCS는 길 수 있음
            }

            if date_match:
                timestamp_ms = int(date_match.group(1))
                msg["date"] = timestamp_ms
                try:
                    msg["date_formatted"] = datetime.fromtimestamp(timestamp_ms / 1000).strftime("%Y-%m-%d %H:%M")
                except:
                    msg["date_formatted"] = ""

            if type_match:
                msg["direction"] = "received" if type_match.group(1) == "1" else "sent"

            rcs_messages.append(msg)

    # SMS + MMS + RCS 통합 후 최신순 정렬
    all_messages = sms_messages + mms_messages + rcs_messages
    all_messages = sorted(all_messages, key=lambda x: x.get("date", 0), reverse=True)

    total_count = len(all_messages)

    # offset과 limit 적용
    result_messages = all_messages[offset:offset + limit]

    return {
        "success": True,
        "messages": result_messages,
        "count": len(result_messages),
        "total": total_count,
        "offset": offset,
        "has_more": offset + len(result_messages) < total_count,
        "query": query,
        "sms_count": len(sms_messages),
        "mms_count": len(mms_messages),
        "rcs_count": len(rcs_messages),
        "message": f"'{query}' 검색 결과: {total_count}개 (SMS {len(sms_messages)}개 + MMS {len(mms_messages)}개 + RCS {len(rcs_messages)}개)" if total_count > 0 else f"'{query}' 검색 결과 없음"
    }
