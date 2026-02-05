"""
Cloudflare Workers 목록 조회
"""

import requests


def run(tool_input: dict, creds: dict) -> dict:
    """
    Cloudflare Workers 목록 조회

    Args:
        tool_input: {worker_name (선택)}
        creds: {api_token, account_id}

    Returns:
        Worker 목록 또는 특정 Worker 정보
    """
    worker_name = tool_input.get("worker_name")
    account_id = creds["account_id"]
    api_token = creds["api_token"]

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }

    try:
        if worker_name:
            # 특정 Worker 조회
            url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/workers/scripts/{worker_name}"
            response = requests.get(url, headers=headers, timeout=30)

            if response.status_code == 200:
                # Worker 설정 정보 조회
                settings_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/workers/scripts/{worker_name}/settings"
                settings_response = requests.get(settings_url, headers=headers, timeout=30)
                settings_data = settings_response.json()

                return {
                    "success": True,
                    "worker": {
                        "name": worker_name,
                        "url": f"https://{worker_name}.{account_id[:8]}.workers.dev",
                        "settings": settings_data.get("result", {}) if settings_data.get("success") else {}
                    }
                }
            else:
                return {
                    "success": False,
                    "error": f"Worker를 찾을 수 없습니다: {worker_name}"
                }
        else:
            # 전체 Worker 목록
            url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/workers/scripts"
            response = requests.get(url, headers=headers, timeout=30)
            data = response.json()

            if data.get("success"):
                workers = data.get("result", [])
                return {
                    "success": True,
                    "count": len(workers),
                    "workers": [
                        {
                            "name": w.get("id"),
                            "created_on": w.get("created_on"),
                            "modified_on": w.get("modified_on"),
                            "url": f"https://{w.get('id')}.{account_id[:8]}.workers.dev"
                        }
                        for w in workers
                    ]
                }
            else:
                return {
                    "success": False,
                    "error": "Worker 목록 조회 실패",
                    "details": data.get("errors", [])
                }

    except Exception as e:
        return {"success": False, "error": str(e)}
