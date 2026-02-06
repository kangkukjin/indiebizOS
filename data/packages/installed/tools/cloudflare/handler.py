"""
Cloudflare 통합 도구 패키지 핸들러 v2.0

단일 도구(cf_api)로 모든 Cloudflare API 호출을 처리합니다.
상세 사용법은 cloudflare_guide.md 가이드 파일에서 제공됩니다.

필요 환경변수:
  - CLOUDFLARE_API_TOKEN: Cloudflare API 토큰
  - CLOUDFLARE_ACCOUNT_ID: Cloudflare Account ID
"""

import json
import os
import importlib.util
from pathlib import Path

# 패키지 디렉토리
PACKAGE_DIR = Path(__file__).parent
TOOLS_DIR = PACKAGE_DIR / "tools"

# 환경변수에서 인증 정보 로드
CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "")
CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")


def get_credentials() -> dict:
    """API 인증 정보 반환 (환경변수에서)"""
    return {
        "api_token": CLOUDFLARE_API_TOKEN,
        "account_id": CLOUDFLARE_ACCOUNT_ID,
    }


def execute(tool_name: str, tool_input: dict, project_path: str = None) -> str:
    """
    도구 실행 진입점

    Args:
        tool_name: 실행할 도구 이름 (cf_api만 지원)
        tool_input: 도구 입력 파라미터
        project_path: 프로젝트 경로 (컨텍스트)

    Returns:
        JSON 형식의 결과 문자열
    """
    try:
        if tool_name != "cf_api":
            return json.dumps({
                "success": False,
                "error": f"지원하지 않는 도구: {tool_name}",
                "hint": "cf_api 도구를 사용하세요. 가이드 파일에서 사용법을 확인하세요."
            }, ensure_ascii=False)

        # 인증 정보 확인
        creds = get_credentials()
        if not creds["api_token"] or not creds["account_id"]:
            return json.dumps({
                "success": False,
                "error": "Cloudflare 환경변수가 설정되지 않았습니다.",
                "setup": {
                    "1": "backend/.env 파일에 다음을 추가하세요:",
                    "2": "CLOUDFLARE_API_TOKEN=your_api_token",
                    "3": "CLOUDFLARE_ACCOUNT_ID=your_account_id",
                    "4": "IndieBiz OS를 재시작하세요."
                }
            }, ensure_ascii=False)

        # api.py 모듈 로드
        module_path = TOOLS_DIR / "api.py"
        if not module_path.exists():
            return json.dumps({
                "success": False,
                "error": "api.py 모듈을 찾을 수 없습니다."
            }, ensure_ascii=False)

        spec = importlib.util.spec_from_file_location("api", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # 도구 실행
        result = module.run(tool_input, creds)

        if isinstance(result, dict):
            return json.dumps(result, ensure_ascii=False)
        elif isinstance(result, str):
            return result
        else:
            return json.dumps({"success": True, "result": str(result)}, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
            "tool": tool_name
        }, ensure_ascii=False)


if __name__ == "__main__":
    print("Cloudflare 도구 패키지 v2.0")
    print("도구: cf_api (단일 도구)")
    print("가이드: cloudflare_guide.md")
    print()
    print("필요 환경변수:")
    print("  - CLOUDFLARE_API_TOKEN")
    print("  - CLOUDFLARE_ACCOUNT_ID")
