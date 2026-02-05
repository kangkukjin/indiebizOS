"""
Cloudflare 통합 도구 패키지 핸들러
Pages, Workers, R2, D1 등 Cloudflare 서비스 관리

필요 환경변수:
  - CLOUDFLARE_API_TOKEN: Cloudflare API 토큰
  - CLOUDFLARE_ACCOUNT_ID: Cloudflare Account ID

환경변수 설정 방법:
  1. backend/.env 파일에 추가
  2. 또는 시스템 환경변수로 설정
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


def load_tool_module(tool_name: str):
    """도구 모듈 동적 로드"""
    # cf_ 접두어 제거하고 모듈 찾기
    module_name = tool_name.replace("cf_", "")
    module_path = TOOLS_DIR / f"{module_name}.py"

    if not module_path.exists():
        return None

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def execute(tool_name: str, tool_input: dict, project_path: str = None) -> str:
    """
    도구 실행 진입점

    Args:
        tool_name: 실행할 도구 이름
        tool_input: 도구 입력 파라미터
        project_path: 프로젝트 경로 (컨텍스트)

    Returns:
        JSON 형식의 결과 문자열
    """
    try:
        # === cf_config: 설정 확인 (핸들러에서 직접 처리) ===
        if tool_name == "cf_config":
            return _handle_config(tool_input)

        # === 다른 도구: 모듈 로드 후 실행 ===
        module = load_tool_module(tool_name)

        if module is None:
            return json.dumps({
                "success": False,
                "error": f"도구를 찾을 수 없습니다: {tool_name}",
                "available_tools": TOOLS
            }, ensure_ascii=False)

        # 인증 정보 확인
        creds = get_credentials()
        if not creds["api_token"] or not creds["account_id"]:
            return json.dumps({
                "success": False,
                "error": "Cloudflare 환경변수가 설정되지 않았습니다.\n\n"
                         "backend/.env 파일에 다음을 추가하세요:\n"
                         "CLOUDFLARE_API_TOKEN=your_api_token\n"
                         "CLOUDFLARE_ACCOUNT_ID=your_account_id\n\n"
                         "cf_config(action='get')으로 현재 상태를 확인할 수 있습니다."
            }, ensure_ascii=False)

        # 도구 실행 (인증 정보 전달)
        result = module.run(tool_input, creds)

        # 결과 반환
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


def _handle_config(tool_input: dict) -> str:
    """cf_config 도구 처리 (환경변수 기반)"""
    action = tool_input.get("action", "get")

    if action == "get":
        api_token = CLOUDFLARE_API_TOKEN
        account_id = CLOUDFLARE_ACCOUNT_ID

        return json.dumps({
            "success": True,
            "account_id": account_id if account_id else "(미설정)",
            "api_token": (api_token[:10] + "..." + api_token[-4:]) if api_token and len(api_token) > 14 else "(미설정)",
            "configured": bool(api_token and account_id),
            "note": "환경변수에서 로드됨 (CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID)"
        }, ensure_ascii=False)

    elif action == "test":
        creds = get_credentials()
        if not creds["api_token"] or not creds["account_id"]:
            return json.dumps({
                "success": False,
                "error": "환경변수가 설정되지 않았습니다.\n\n"
                         "backend/.env 파일에 다음을 추가하세요:\n"
                         "CLOUDFLARE_API_TOKEN=your_api_token\n"
                         "CLOUDFLARE_ACCOUNT_ID=your_account_id"
            }, ensure_ascii=False)

        # API 테스트
        try:
            import requests
            response = requests.get(
                "https://api.cloudflare.com/client/v4/user/tokens/verify",
                headers={"Authorization": f"Bearer {creds['api_token']}"},
                timeout=10
            )
            data = response.json()

            if data.get("success"):
                return json.dumps({
                    "success": True,
                    "message": "API 연결 성공!",
                    "token_status": data.get("result", {}).get("status", "unknown")
                }, ensure_ascii=False)
            else:
                return json.dumps({
                    "success": False,
                    "error": "API 토큰이 유효하지 않습니다.",
                    "details": data.get("errors", [])
                }, ensure_ascii=False)

        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"API 테스트 실패: {str(e)}"
            }, ensure_ascii=False)

    else:
        return json.dumps({
            "success": False,
            "error": f"알 수 없는 action: {action}. 지원: get, test"
        }, ensure_ascii=False)


# 도구 목록
TOOLS = [
    "cf_config",
    "cf_pages_deploy",
    "cf_pages_list",
    "cf_worker_deploy",
    "cf_worker_list",
    "cf_r2_upload",
    "cf_r2_list",
    "cf_d1_query",
    "cf_d1_list",
]


if __name__ == "__main__":
    print("Cloudflare 도구 패키지")
    print(f"도구 목록: {TOOLS}")
    print(f"총 {len(TOOLS)}개 도구")
    print()
    print("필요 환경변수:")
    print("  - CLOUDFLARE_API_TOKEN")
    print("  - CLOUDFLARE_ACCOUNT_ID")
