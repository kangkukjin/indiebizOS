"""
web-request 도구 핸들러
"""
import json
import urllib.request
import urllib.error


def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    """
    HTTP 요청 도구

    Args:
        tool_name: 도구 이름 (이 패키지에서는 "web_request")
        tool_input: 도구 입력 파라미터
        project_path: 프로젝트 경로

    Returns:
        JSON 형식의 결과 문자열
    """
    if tool_name == "web_request":
        url = tool_input.get("url", "")
        method = tool_input.get("method", "GET").upper()
        headers_str = tool_input.get("headers", "{}")
        body = tool_input.get("body", "")

        try:
            headers = json.loads(headers_str) if headers_str else {}
            data = body.encode('utf-8') if body else None

            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=30) as response:
                content = response.read().decode('utf-8')
                return json.dumps({
                    "success": True,
                    "status": response.status,
                    "content": content[:10000]  # 최대 10KB
                }, ensure_ascii=False)
        except urllib.error.HTTPError as e:
            return json.dumps({"success": False, "error": f"HTTP {e.code}: {e.reason}"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    return json.dumps({"success": False, "error": f"알 수 없는 도구: {tool_name}"}, ensure_ascii=False)
