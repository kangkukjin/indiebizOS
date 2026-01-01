"""
file-ops 도구 핸들러 (read_file, write_file, list_directory)
"""
import json
import os
from pathlib import Path


def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    """
    파일 조작 도구

    Args:
        tool_name: 도구 이름
        tool_input: 도구 입력 파라미터
        project_path: 프로젝트 경로

    Returns:
        JSON 형식의 결과 문자열
    """
    if tool_name == "read_file":
        file_path = tool_input.get("file_path", "")
        full_path = Path(project_path) / file_path if not os.path.isabs(file_path) else Path(file_path)
        if full_path.exists():
            content = full_path.read_text(encoding='utf-8')
            return json.dumps({"success": True, "content": content}, ensure_ascii=False)
        else:
            return json.dumps({"success": False, "error": "파일을 찾을 수 없습니다."}, ensure_ascii=False)

    elif tool_name == "write_file":
        file_path = tool_input.get("file_path", "")
        content = tool_input.get("content", "")
        full_path = Path(project_path) / file_path if not os.path.isabs(file_path) else Path(file_path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding='utf-8')
        return json.dumps({"success": True, "message": f"파일 저장됨: {full_path}"}, ensure_ascii=False)

    elif tool_name == "list_directory":
        dir_path = tool_input.get("dir_path", ".")
        full_path = Path(project_path) / dir_path if not os.path.isabs(dir_path) else Path(dir_path)
        if full_path.exists() and full_path.is_dir():
            items = []
            for item in full_path.iterdir():
                items.append({
                    "name": item.name,
                    "type": "directory" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else None
                })
            return json.dumps({"success": True, "items": items}, ensure_ascii=False)
        else:
            return json.dumps({"success": False, "error": "디렉토리를 찾을 수 없습니다."}, ensure_ascii=False)

    return json.dumps({"success": False, "error": f"알 수 없는 도구: {tool_name}"}, ensure_ascii=False)
