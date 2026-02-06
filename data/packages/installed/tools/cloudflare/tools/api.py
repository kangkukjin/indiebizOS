"""
cf_api - Cloudflare 범용 API 호출 도구

인증된 상태로 Cloudflare API를 호출합니다.
토큰은 환경변수에서 안전하게 주입됩니다.
"""

import requests
from typing import Optional


CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4"


def run(tool_input: dict, creds: dict) -> dict:
    """
    Cloudflare API 호출

    Args:
        tool_input:
            - method: HTTP 메서드 (GET, POST, PUT, DELETE, PATCH)
            - endpoint: API 엔드포인트 (예: "/zones", "/accounts/{account_id}/tunnels")
            - body: 요청 본문 (선택, dict)
            - params: 쿼리 파라미터 (선택, dict)
        creds:
            - api_token: Cloudflare API 토큰
            - account_id: Cloudflare Account ID

    Returns:
        Cloudflare API 응답
    """
    api_token = creds.get("api_token")
    account_id = creds.get("account_id")

    method = tool_input.get("method", "GET").upper()
    endpoint = tool_input.get("endpoint", "")
    body = tool_input.get("body")
    params = tool_input.get("params")

    if not endpoint:
        return {
            "success": False,
            "error": "endpoint가 필요합니다.",
            "hint": "예: /zones, /accounts/{account_id}/tunnels"
        }

    # {account_id} 플레이스홀더 치환
    endpoint = endpoint.replace("{account_id}", account_id)

    # 전체 URL 구성
    if endpoint.startswith("http"):
        url = endpoint
    else:
        url = f"{CLOUDFLARE_API_BASE}{endpoint}"

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=body if body else None,
            params=params if params else None,
            timeout=30
        )

        # JSON 응답 파싱 시도
        try:
            data = response.json()
        except:
            data = {"raw_response": response.text}

        # Cloudflare API 성공/실패 판단
        if isinstance(data, dict):
            cf_success = data.get("success", response.ok)
            return {
                "success": cf_success,
                "status_code": response.status_code,
                "result": data.get("result") if cf_success else None,
                "errors": data.get("errors") if not cf_success else None,
                "messages": data.get("messages"),
                "result_info": data.get("result_info")
            }
        else:
            return {
                "success": response.ok,
                "status_code": response.status_code,
                "data": data
            }

    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": "API 요청 타임아웃 (30초)"
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": f"API 요청 실패: {str(e)}"
        }
