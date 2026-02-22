"""
안드로이드 관리 도구 (IndieBiz Quality Standard 적용 버전)
Android Management Tool for IndieBiz

ADB(Android Debug Bridge)를 통해 안드로이드 스마트폰을 관리합니다.
자가 진단 및 상세 에러 보고 기능이 강화되었습니다.

모듈화된 구조:
- adb_core.py: ADB 핵심 유틸리티 (find_adb, run_adb)
- device_info.py: 기기 정보 및 시스템 상태
- app_manager.py: 앱 관리
- sms_manager.py: SMS/MMS 관리
- call_manager.py: 통화 관리
- contacts_manager.py: 연락처 관리
- file_utils.py: 파일 및 화면 유틸리티
"""

import sys
import json
from pathlib import Path

# 현재 디렉토리를 sys.path에 추가하여 모듈을 import할 수 있도록 함
_current_dir = Path(__file__).parent
if str(_current_dir) not in sys.path:
    sys.path.insert(0, str(_current_dir))

# 모듈 임포트
from adb_core import find_adb, run_adb
from device_info import (
    list_devices,
    get_device_info,
    get_battery_status,
    get_storage_info,
    get_system_status,
    grant_adb_permissions,
    check_adb_permissions,
)
from app_manager import (
    list_packages,
    get_app_sizes,
    get_app_usage_stats,
    get_app_info,
    uninstall_app,
    get_apps_with_details,
)
from sms_manager import (
    get_sms_list,
    get_sms_from_notifications,
    get_mms_list,
    get_all_messages,
    send_sms,
    delete_sms,
    delete_sms_by_ids,
    delete_mms_by_content,
    delete_messages_by_ids,
    search_sms,
)
from call_manager import (
    make_call,
    end_call,
    get_call_log,
    delete_call_log,
)
from contacts_manager import (
    get_contacts,
    search_contacts,
    delete_contact,
)
from file_utils import (
    capture_screen,
    send_to_clipboard,
    push_file,
    pull_file,
    get_notifications,
    open_android_manager_window,
)
from ui_control import (
    tap,
    swipe,
    long_press,
    press_key,
    type_text,
    get_screen_info,
    get_ui_hierarchy,
    capture_screen_base64,
    open_app,
    find_element,
    find_and_tap,
)


def use_tool(tool_name: str, tool_input: dict) -> dict:
    """도구 실행 브릿지"""
    device_id = tool_input.get("device_id")

    # 도구 이름에 따른 함수 매핑
    dispatch = {
        # 기기 관리
        "android_list_devices": lambda: list_devices(),
        "android_device_info": lambda: get_device_info(device_id),
        "android_system_status": lambda: get_system_status(device_id),
        # 권한 관리
        "android_grant_permissions": lambda: grant_adb_permissions(device_id),
        "android_check_permissions": lambda: check_adb_permissions(device_id),
        # 앱 관리
        "android_list_apps": lambda: list_packages(device_id, tool_input.get("third_party_only", True)),
        "android_app_sizes": lambda: get_app_sizes(device_id, tool_input.get("limit", 20)),
        "android_app_usage": lambda: get_app_usage_stats(device_id),
        "android_app_info": lambda: get_app_info(tool_input.get("package_name", ""), device_id),
        "android_uninstall_app": lambda: uninstall_app(tool_input.get("package_name", ""), device_id),
        "android_apps_with_details": lambda: get_apps_with_details(device_id, tool_input.get("limit", 50)),
        # 파일/화면
        "android_capture_screen": lambda: capture_screen(device_id),
        "android_send_text": lambda: send_to_clipboard(tool_input.get("text", ""), device_id),
        "android_push_file": lambda: push_file(tool_input.get("local_path", ""), tool_input.get("remote_path", "/sdcard/Download/"), device_id),
        "android_pull_file": lambda: pull_file(tool_input.get("remote_path", ""), tool_input.get("local_path"), device_id),
        "android_notifications": lambda: get_notifications(device_id),
        # SMS
        "android_get_sms": lambda: get_sms_list(device_id, tool_input.get("box", "inbox"), tool_input.get("limit", 50), tool_input.get("offset", 0)),
        "android_send_sms": lambda: send_sms(tool_input.get("phone_number", ""), tool_input.get("message", ""), device_id),
        "android_delete_sms": lambda: delete_sms(
            sms_id=tool_input.get("sms_id"),
            address=tool_input.get("address"),
            body_contains=tool_input.get("body_contains"),
            before_date=tool_input.get("before_date"),
            dry_run=tool_input.get("dry_run", False),
            device_id=device_id
        ),
        "android_search_sms": lambda: search_sms(tool_input.get("query", ""), device_id, tool_input.get("limit", 100)),
        # SMS+MMS 통합 삭제
        "android_delete_messages": lambda: delete_sms_by_ids(
            sms_ids=tool_input.get("sms_ids"),
            mms_ids=tool_input.get("mms_ids"),
            device_id=device_id
        ),
        # MMS 조건부 삭제 (빠름)
        "android_delete_mms_by_content": lambda: delete_mms_by_content(
            body_contains=tool_input.get("body_contains", ""),
            dry_run=tool_input.get("dry_run", True),
            device_id=device_id
        ),
        # MMS (삼성 채팅+, RCS 메시지)
        "android_get_mms": lambda: get_mms_list(device_id, tool_input.get("box", "inbox"), tool_input.get("limit", 50), tool_input.get("offset", 0)),
        "android_get_all_messages": lambda: get_all_messages(device_id, tool_input.get("box", "inbox"), tool_input.get("limit", 50), tool_input.get("offset", 0)),
        # 전화
        "android_make_call": lambda: make_call(tool_input.get("phone_number", ""), device_id),
        "android_end_call": lambda: end_call(device_id),
        "android_get_call_log": lambda: get_call_log(device_id, tool_input.get("limit", 50), tool_input.get("call_type", "all")),
        "android_delete_call_log": lambda: delete_call_log(tool_input.get("call_id"), device_id),
        # 연락처
        "android_get_contacts": lambda: get_contacts(device_id, tool_input.get("limit", 100)),
        "android_search_contacts": lambda: search_contacts(tool_input.get("query", ""), device_id),
        "android_delete_contact": lambda: delete_contact(tool_input.get("contact_id"), tool_input.get("phone_number"), device_id),
        # UI 창 열기 (백엔드 API 통해 요청)
        "open_android_manager": lambda: open_android_manager_window(device_id, tool_input.get("project_id")),
        # UI 제어 (Computer-Use)
        "android_ui_tap": lambda: tap(tool_input.get("x", 0), tool_input.get("y", 0), device_id),
        "android_ui_swipe": lambda: swipe(
            tool_input.get("x1", 0), tool_input.get("y1", 0),
            tool_input.get("x2", 0), tool_input.get("y2", 0),
            tool_input.get("duration_ms", 300), device_id
        ),
        "android_ui_long_press": lambda: long_press(
            tool_input.get("x", 0), tool_input.get("y", 0),
            tool_input.get("duration_ms", 1000), device_id
        ),
        "android_ui_press_key": lambda: press_key(tool_input.get("keycode", ""), device_id),
        "android_ui_type_text": lambda: type_text(tool_input.get("text", ""), device_id),
        "android_ui_screen_info": lambda: get_screen_info(device_id),
        "android_ui_hierarchy": lambda: get_ui_hierarchy(device_id),
        "android_ui_screenshot": lambda: capture_screen_base64(device_id),
        "android_ui_open_app": lambda: open_app(tool_input.get("package_name", ""), device_id),
        # UI 요소 검색 및 터치
        "android_ui_find_element": lambda: find_element(tool_input.get("query", ""), device_id),
        "android_ui_find_and_tap": lambda: find_and_tap(
            tool_input.get("query", ""),
            tool_input.get("index", 0),
            device_id
        ),
    }

    if tool_name in dispatch:
        try:
            return dispatch[tool_name]()
        except Exception as e:
            return {
                "success": False,
                "error_type": "INTERNAL_EXCEPTION",
                "message": f"도구 실행 중 예상치 못한 오류 발생: {str(e)}"
            }
    else:
        return {"success": False, "message": f"알 수 없는 도구: {tool_name}"}


if __name__ == "__main__":
    # 자가 진단 테스트
    print("--- Android Tool Self-Diagnosis ---")
    adb = find_adb()
    print(f"ADB Found: {adb if adb else 'Not Found'}")
    print(json.dumps(list_devices(), indent=2, ensure_ascii=False))
