"""
PC Manager 도구 핸들러
AI 에이전트가 PC Manager 창을 열고, 스토리지를 스캔/검색할 수 있게 한다

기능:
- open_file_explorer: PC Manager 파일 탐색기 창 열기
- scan_storage: 폴더/볼륨 스캔하여 메타데이터 수집
- annotate_folder: 폴더에 사용자 주석 추가
- query_storage: 파일 검색
- get_storage_summary: 볼륨 요약 정보
- list_volumes: 스캔된 볼륨 목록
- get_folder_annotations: 폴더 주석 조회
"""

import os
import sys
import json

# 현재 디렉토리를 path에 추가 (storage_db 임포트용)
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)


def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    """도구 실행"""
    try:
        # PC Manager 창 열기
        if tool_name == "open_file_explorer":
            return _open_file_explorer(tool_input)

        # 스토리지 스캔
        elif tool_name == "scan_storage":
            return _scan_storage(tool_input)

        # 폴더 주석 추가
        elif tool_name == "annotate_folder":
            return _annotate_folder(tool_input)

        # 파일 검색
        elif tool_name == "query_storage":
            return _query_storage(tool_input)

        # 볼륨 요약
        elif tool_name == "get_storage_summary":
            return _get_storage_summary(tool_input)

        # 볼륨 목록
        elif tool_name == "list_volumes":
            return _list_volumes(tool_input)

        # 폴더 주석 조회
        elif tool_name == "get_folder_annotations":
            return _get_folder_annotations(tool_input)

        return f"알 수 없는 도구: {tool_name}"

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


def _open_file_explorer(tool_input: dict) -> str:
    """PC Manager 창 열기"""
    path = tool_input.get("path", None)

    try:
        from api_pcmanager import _pending_window_requests
        request_id = os.urandom(8).hex()
        _pending_window_requests.append({
            "id": request_id,
            "path": path,
        })

        if path:
            return f"PC Manager 창 열기 요청을 전송했습니다. 경로: {path}"
        else:
            return "PC Manager 창 열기 요청을 전송했습니다. (홈 디렉토리)"

    except ImportError as e:
        return f"api_pcmanager 모듈을 불러올 수 없습니다: {e}"


def _scan_storage(tool_input: dict) -> str:
    """스토리지 스캔"""
    import storage_db

    path = tool_input.get("path")
    if not path:
        return json.dumps({"success": False, "error": "path가 필요합니다"}, ensure_ascii=False)

    volume_name = tool_input.get("volume_name")
    result = storage_db.scan_directory(path, volume_name)

    if result["success"]:
        return json.dumps({
            "success": True,
            "message": f"스캔 완료: {result['volume_name']}",
            "file_count": result['file_count'],
            "total_size_mb": result['total_size_mb'],
            "scan_time": result['scan_time']
        }, ensure_ascii=False)
    else:
        return json.dumps(result, ensure_ascii=False)


def _annotate_folder(tool_input: dict) -> str:
    """폴더 주석 추가"""
    import storage_db

    folder_path = tool_input.get("folder_path")
    note = tool_input.get("note")

    if not folder_path or not note:
        return json.dumps({"success": False, "error": "folder_path와 note가 필요합니다"}, ensure_ascii=False)

    result = storage_db.add_annotation(folder_path, note)

    if result["success"]:
        return json.dumps({
            "success": True,
            "message": f"주석 추가됨: {folder_path}",
            "note": note
        }, ensure_ascii=False)
    else:
        return json.dumps(result, ensure_ascii=False)


def _query_storage(tool_input: dict) -> str:
    """파일 검색"""
    import storage_db

    root_path = tool_input.get("volume_name") or tool_input.get("root_path")
    if not root_path:
        return json.dumps({"success": False, "error": "volume_name(또는 root_path)이 필요합니다"}, ensure_ascii=False)

    result = storage_db.query_files(
        root_path=root_path,
        search_term=tool_input.get("search_term"),
        extension=tool_input.get("extension"),
        min_size_mb=tool_input.get("min_size_mb"),
        limit=tool_input.get("limit", 100)
    )

    return json.dumps(result, ensure_ascii=False)


def _get_storage_summary(tool_input: dict) -> str:
    """볼륨 요약"""
    import storage_db

    root_path = tool_input.get("volume_name") or tool_input.get("root_path")
    if not root_path:
        return json.dumps({"success": False, "error": "volume_name(또는 root_path)이 필요합니다"}, ensure_ascii=False)

    result = storage_db.get_summary(root_path)

    return json.dumps(result, ensure_ascii=False)


def _list_volumes(tool_input: dict) -> str:
    """볼륨 목록"""
    import storage_db

    result = storage_db.list_volumes()
    return json.dumps(result, ensure_ascii=False)


def _get_folder_annotations(tool_input: dict) -> str:
    """폴더 주석 조회"""
    import storage_db

    root_path = tool_input.get("volume_name") or tool_input.get("root_path")
    if not root_path:
        return json.dumps({"success": False, "error": "volume_name(또는 root_path)이 필요합니다"}, ensure_ascii=False)

    result = storage_db.get_annotations(root_path)

    return json.dumps(result, ensure_ascii=False)
