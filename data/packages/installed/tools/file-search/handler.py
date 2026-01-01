"""
file-search 도구 핸들러
"""
import json
from pathlib import Path


def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    """
    파일 검색 도구

    Args:
        tool_name: 도구 이름 (이 패키지에서는 "search_files")
        tool_input: 도구 입력 파라미터
        project_path: 프로젝트 경로

    Returns:
        JSON 형식의 결과 문자열
    """
    if tool_name == "search_files":
        query = tool_input.get("query", "")
        search_content = tool_input.get("search_content", False)

        try:
            results = []
            project_dir = Path(project_path)

            for file_path in project_dir.rglob("*"):
                if file_path.is_file():
                    # 파일명 검색
                    if query.lower() in file_path.name.lower():
                        results.append({
                            "path": str(file_path.relative_to(project_dir)),
                            "match_type": "filename"
                        })
                    # 내용 검색
                    elif search_content:
                        try:
                            content = file_path.read_text(encoding='utf-8', errors='ignore')
                            if query.lower() in content.lower():
                                results.append({
                                    "path": str(file_path.relative_to(project_dir)),
                                    "match_type": "content"
                                })
                        except:
                            pass

                    if len(results) >= 50:  # 최대 50개
                        break

            return json.dumps({"success": True, "results": results, "count": len(results)}, ensure_ascii=False)

        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    return json.dumps({"success": False, "error": f"알 수 없는 도구: {tool_name}"}, ensure_ascii=False)
