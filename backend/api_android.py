"""
api_android.py - Android Device Manager API
안드로이드 기기의 SMS, 통화, 연락처 관리 API
"""

import sys
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

# Android 도구 경로
BACKEND_PATH = Path(__file__).parent
from runtime_utils import get_base_path as _get_base_path
DATA_PATH = _get_base_path() / "data"
ANDROID_TOOL_PATH = DATA_PATH / "packages" / "installed" / "tools" / "android"

# Lazy loading: API 호출 시점에 로드 (시작 시 에러 방지)
_tool_android = None
_import_error = None
_import_attempted = False


def _ensure_tool_loaded():
    """API 호출 시점에 도구 로드 (lazy loading)"""
    global _tool_android, _import_error, _import_attempted

    if _import_attempted:
        return

    _import_attempted = True

    # sys.path에 도구 경로 추가
    tool_path_str = str(ANDROID_TOOL_PATH)
    if tool_path_str not in sys.path:
        sys.path.insert(0, tool_path_str)

    try:
        import tool_android as _ta
        _tool_android = _ta
    except ImportError as e:
        _import_error = str(e)

router = APIRouter(prefix="/android", tags=["android"])

# 창 열기 요청 큐
_pending_windows: list[dict] = []


# ============ 요청 모델 ============

class SendSmsRequest(BaseModel):
    phone_number: str
    message: str
    device_id: Optional[str] = None


class MakeCallRequest(BaseModel):
    phone_number: str
    device_id: Optional[str] = None


class DeleteRequest(BaseModel):
    id: str
    device_id: Optional[str] = None


class SearchRequest(BaseModel):
    query: str
    limit: Optional[int] = 100
    offset: Optional[int] = 0
    device_id: Optional[str] = None


class AiCommandRequest(BaseModel):
    command: str
    device_id: Optional[str] = None


# ============ 헬퍼 함수 ============

def check_tool_available():
    """Android 도구 사용 가능 여부 확인 (lazy loading)"""
    _ensure_tool_loaded()
    if _tool_android is None:
        raise HTTPException(
            status_code=503,
            detail=f"Android 도구가 설치되어 있지 않습니다. 경로: {ANDROID_TOOL_PATH}, 에러: {_import_error}"
        )
    return _tool_android


# ============ 기기 관리 ============

@router.get("/devices")
async def list_devices():
    """연결된 안드로이드 기기 목록"""
    tool = check_tool_available()
    return tool.list_devices()


@router.get("/devices/{device_id}/info")
async def get_device_info(device_id: str):
    """기기 상세 정보"""
    check_tool_available()
    return _tool_android.get_device_info(device_id if device_id != "default" else None)


@router.get("/devices/{device_id}/status")
async def get_system_status(device_id: str):
    """기기 시스템 상태 (배터리, 저장공간 등)"""
    check_tool_available()
    return _tool_android.get_system_status(device_id if device_id != "default" else None)


# ============ SMS 관리 ============

@router.get("/sms")
async def get_sms_list(
    box: str = "inbox",
    limit: int = 50,
    offset: int = 0,
    device_id: Optional[str] = None
):
    """SMS 목록 조회"""
    check_tool_available()
    return _tool_android.get_sms_list(
        device_id=device_id,
        box=box,
        limit=limit,
        offset=offset
    )


@router.post("/sms/send")
async def send_sms(request: SendSmsRequest):
    """SMS 보내기"""
    check_tool_available()
    return _tool_android.send_sms(
        phone_number=request.phone_number,
        message=request.message,
        device_id=request.device_id
    )


@router.delete("/sms/{sms_id}")
async def delete_sms(sms_id: str, device_id: Optional[str] = None):
    """SMS 삭제 (단일)"""
    check_tool_available()
    return _tool_android.delete_sms(sms_id=sms_id, device_id=device_id)


class BulkDeleteSmsRequest(BaseModel):
    address: Optional[str] = None
    body_contains: Optional[str] = None
    before_date: Optional[str] = None
    dry_run: Optional[bool] = False
    device_id: Optional[str] = None


@router.post("/sms/bulk-delete")
async def bulk_delete_sms(request: BulkDeleteSmsRequest):
    """SMS 일괄 삭제 (조건부)"""
    check_tool_available()
    return _tool_android.delete_sms(
        address=request.address,
        body_contains=request.body_contains,
        before_date=request.before_date,
        dry_run=request.dry_run or False,
        device_id=request.device_id
    )


class BulkDeleteByIdsRequest(BaseModel):
    ids: List[str]
    device_id: Optional[str] = None


class BulkDeleteMessagesRequest(BaseModel):
    sms_ids: Optional[List[str]] = None
    mms_ids: Optional[List[str]] = None
    device_id: Optional[str] = None


@router.post("/sms/bulk-delete-by-ids")
async def bulk_delete_sms_by_ids(request: BulkDeleteByIdsRequest):
    """SMS ID 목록으로 일괄 삭제 (하위 호환)"""
    check_tool_available()
    return _tool_android.delete_sms_by_ids(
        sms_ids=request.ids,
        device_id=request.device_id
    )


@router.post("/messages/bulk-delete")
async def bulk_delete_messages(request: BulkDeleteMessagesRequest):
    """SMS + MMS 통합 일괄 삭제"""
    check_tool_available()
    return _tool_android.delete_sms_by_ids(
        sms_ids=request.sms_ids,
        mms_ids=request.mms_ids,
        device_id=request.device_id
    )


@router.post("/sms/search")
async def search_sms(request: SearchRequest):
    """SMS 검색"""
    check_tool_available()
    return _tool_android.search_sms(
        query=request.query,
        device_id=request.device_id,
        limit=request.limit or 100,
        offset=request.offset or 0
    )


# ============ 통합 메시지 (SMS + MMS) ============

@router.get("/messages")
async def get_all_messages(
    box: str = "inbox",
    limit: int = 50,
    offset: int = 0,
    device_id: Optional[str] = None
):
    """SMS + MMS 통합 메시지 목록 조회 (삼성 채팅+ 포함)"""
    check_tool_available()
    return _tool_android.get_all_messages(
        device_id=device_id,
        box=box,
        limit=limit,
        offset=offset
    )


@router.get("/mms")
async def get_mms_list(
    box: str = "inbox",
    limit: int = 50,
    offset: int = 0,
    device_id: Optional[str] = None
):
    """MMS 목록 조회 (삼성 채팅+, RCS 등)"""
    check_tool_available()
    return _tool_android.get_mms_list(
        device_id=device_id,
        box=box,
        limit=limit,
        offset=offset
    )


# ============ 통화 관리 ============

@router.get("/calls")
async def get_call_log(
    call_type: str = "all",
    limit: int = 50,
    offset: int = 0,
    device_id: Optional[str] = None
):
    """통화 기록 조회"""
    check_tool_available()
    return _tool_android.get_call_log(
        device_id=device_id,
        limit=limit,
        call_type=call_type,
        offset=offset
    )


@router.post("/calls/make")
async def make_call(request: MakeCallRequest):
    """전화 걸기"""
    check_tool_available()
    return _tool_android.make_call(
        phone_number=request.phone_number,
        device_id=request.device_id
    )


@router.post("/calls/end")
async def end_call(device_id: Optional[str] = None):
    """통화 종료"""
    check_tool_available()
    return _tool_android.end_call(device_id)


@router.delete("/calls/{call_id}")
async def delete_call_log(call_id: str, device_id: Optional[str] = None):
    """통화 기록 삭제"""
    check_tool_available()
    return _tool_android.delete_call_log(call_id, device_id)


# ============ 연락처 관리 ============

@router.get("/contacts")
async def get_contacts(
    limit: int = 100,
    offset: int = 0,
    device_id: Optional[str] = None
):
    """연락처 목록 조회"""
    check_tool_available()
    return _tool_android.get_contacts(device_id, limit, offset)


@router.post("/contacts/search")
async def search_contacts(request: SearchRequest):
    """연락처 검색"""
    check_tool_available()
    return _tool_android.search_contacts(
        query=request.query,
        device_id=request.device_id
    )


@router.delete("/contacts/{contact_id}")
async def delete_contact(contact_id: str, device_id: Optional[str] = None):
    """연락처 삭제"""
    check_tool_available()
    return _tool_android.delete_contact(contact_id=contact_id, device_id=device_id)


# ============ 앱 관리 ============

@router.get("/apps")
async def get_apps_list(
    limit: int = 50,
    offset: int = 0,
    device_id: Optional[str] = None
):
    """앱 목록과 상세 정보 조회"""
    check_tool_available()
    return _tool_android.get_apps_with_details(device_id, limit, offset)


@router.get("/apps/usage")
async def get_apps_usage(device_id: Optional[str] = None):
    """앱 사용량 통계"""
    check_tool_available()
    return _tool_android.get_app_usage_stats(device_id)


@router.get("/apps/{package_name}/info")
async def get_app_info(package_name: str, device_id: Optional[str] = None):
    """특정 앱 상세 정보"""
    check_tool_available()
    return _tool_android.get_app_info(package_name, device_id)


@router.delete("/apps/{package_name}")
async def uninstall_app(package_name: str, device_id: Optional[str] = None):
    """앱 삭제"""
    check_tool_available()
    return _tool_android.uninstall_app(package_name, device_id)


# ============ 디버그 ============

@router.get("/debug/raw-sms")
async def debug_raw_sms(device_id: Optional[str] = None):
    """디버그: ADB content query의 raw 결과 확인"""
    check_tool_available()

    # run_adb 직접 호출해서 raw 결과 반환
    result = _tool_android.run_adb([
        "shell", "content", "query",
        "--uri", "content://sms/inbox",
        "--projection", "_id:address:body"
    ], device_id, timeout=30)

    return {
        "success": result.get("success"),
        "stdout": result.get("stdout", "")[:2000],  # 처음 2000자만
        "stderr": result.get("stderr", ""),
        "error": result.get("error", ""),
        "message": result.get("message", "")
    }


# ============ 기타 기능 ============

@router.post("/screen/capture")
async def capture_screen(device_id: Optional[str] = None):
    """화면 캡처"""
    check_tool_available()
    return _tool_android.capture_screen(device_id)


@router.get("/notifications")
async def get_notifications(device_id: Optional[str] = None):
    """알림 목록"""
    check_tool_available()
    return _tool_android.get_notifications(device_id)


# ============ 창 열기 요청 ============

@router.get("/pending-windows")
async def get_pending_windows():
    """대기 중인 Android Manager 창 열기 요청 반환 후 큐 비우기"""
    global _pending_windows
    requests = _pending_windows.copy()
    _pending_windows.clear()
    return {"requests": requests}


@router.post("/open-window")
async def request_open_window(device_id: Optional[str] = None, project_id: Optional[str] = None):
    """Android Manager 창 열기 요청 등록"""
    _pending_windows.append({"device_id": device_id, "project_id": project_id})
    return {"success": True, "message": "Android Manager 창 열기 요청이 등록되었습니다."}


# ============ 안드로이드 전용 에이전트 ============

# 안드로이드 에이전트 인스턴스 (창 하나당 하나)
_android_agent = None
_android_agent_id = None


@router.post("/agent/start")
async def start_android_agent():
    """안드로이드 전용 에이전트 시작"""
    global _android_agent, _android_agent_id
    import uuid

    # 이미 실행 중이면 기존 ID 반환
    if _android_agent is not None:
        return {"success": True, "agent_id": _android_agent_id, "message": "기존 에이전트 사용"}

    # 새 에이전트 ID 생성
    _android_agent_id = f"android_{uuid.uuid4().hex[:8]}"

    # 에이전트 생성 (지연 import)
    try:
        from android_agent import AndroidAgent
        _android_agent = AndroidAgent(_android_agent_id)
        await _android_agent.start()
        return {"success": True, "agent_id": _android_agent_id, "message": "에이전트 시작됨"}
    except Exception as e:
        _android_agent = None
        _android_agent_id = None
        return {"success": False, "error": str(e)}


@router.post("/agent/stop")
async def stop_android_agent():
    """안드로이드 전용 에이전트 종료"""
    global _android_agent, _android_agent_id

    if _android_agent is not None:
        try:
            await _android_agent.stop()
        except:
            pass
        _android_agent = None
        _android_agent_id = None

    return {"success": True, "message": "에이전트 종료됨"}


def get_android_agent():
    """현재 안드로이드 에이전트 반환"""
    return _android_agent


# ============ AI 명령 처리 ============

@router.post("/ai-command")
async def process_ai_command(request: AiCommandRequest):
    """AI 자연어 명령 처리 (간단한 패턴 매칭)"""
    check_tool_available()

    command = request.command.lower()
    device_id = request.device_id

    # 간단한 명령어 패턴 매칭
    if "문자" in command and ("검색" in command or "찾" in command):
        # 검색어 추출 시도
        import re
        match = re.search(r'["\'](.+?)["\']|(\S+)(?:한테|에게|로부터|의)', command)
        if match:
            query = match.group(1) or match.group(2)
            result = _tool_android.search_sms(query, device_id)
            return {
                "success": True,
                "response": f"'{query}' 검색 결과: {result.get('count', 0)}개의 문자를 찾았습니다.",
                "data": result,
                "refresh": False
            }

    elif "통화" in command and ("기록" in command or "내역" in command):
        if "부재중" in command or "못받" in command:
            result = _tool_android.get_call_log(device_id, limit=20, call_type="missed")
            return {
                "success": True,
                "response": f"부재중 전화 {result.get('count', 0)}건입니다.",
                "data": result,
                "refresh": False
            }
        elif "발신" in command or "건" in command:
            result = _tool_android.get_call_log(device_id, limit=20, call_type="outgoing")
            return {
                "success": True,
                "response": f"발신 전화 {result.get('count', 0)}건입니다.",
                "data": result,
                "refresh": False
            }
        elif "수신" in command or "받" in command:
            result = _tool_android.get_call_log(device_id, limit=20, call_type="incoming")
            return {
                "success": True,
                "response": f"수신 전화 {result.get('count', 0)}건입니다.",
                "data": result,
                "refresh": False
            }

    elif "연락처" in command and ("검색" in command or "찾" in command):
        import re
        match = re.search(r'["\'](.+?)["\']|(\S+)(?:의|를|을)', command)
        if match:
            query = match.group(1) or match.group(2)
            result = _tool_android.search_contacts(query, device_id)
            return {
                "success": True,
                "response": f"'{query}' 검색 결과: {result.get('count', 0)}명을 찾았습니다.",
                "data": result,
                "refresh": False
            }

    elif "전화" in command and ("걸" in command or "연결" in command):
        import re
        # 전화번호 패턴 찾기
        match = re.search(r'(\d{2,4}[-\s]?\d{3,4}[-\s]?\d{4}|\d{10,11})', command)
        if match:
            phone = match.group(1).replace(" ", "").replace("-", "")
            result = _tool_android.make_call(phone, device_id)
            return {
                "success": True,
                "response": f"{phone}에 전화를 겁니다.",
                "data": result,
                "refresh": False
            }
        else:
            return {
                "success": False,
                "response": "전화번호를 인식할 수 없습니다. 전화번호를 포함해서 다시 말씀해주세요."
            }

    elif "새로고침" in command or "갱신" in command:
        return {
            "success": True,
            "response": "데이터를 새로고침합니다.",
            "refresh": True
        }

    # 기본 응답
    return {
        "success": True,
        "response": "명령을 이해하지 못했습니다. 다음과 같이 말해보세요:\n• '엄마한테 온 문자 검색해줘'\n• '부재중 통화 기록 보여줘'\n• '010-1234-5678에 전화 걸어줘'\n• '김철수 연락처 찾아줘'"
    }
