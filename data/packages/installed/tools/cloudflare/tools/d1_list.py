"""
Cloudflare D1 데이터베이스 목록 조회
"""

import requests


def run(tool_input: dict, creds: dict) -> dict:
    """
    Cloudflare D1 데이터베이스 목록 조회

    Args:
        tool_input: {database (선택)}
        creds: {api_token, account_id}

    Returns:
        데이터베이스 목록 또는 특정 DB 정보
    """
    database = tool_input.get("database")
    account_id = creds["account_id"]
    api_token = creds["api_token"]

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }

    try:
        if database:
            # 특정 데이터베이스 조회 - 먼저 목록에서 ID 찾기
            url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database"
            response = requests.get(url, headers=headers, timeout=30)
            data = response.json()

            if data.get("success"):
                databases = data.get("result", [])
                target_db = None
                for db in databases:
                    if db.get("name") == database or db.get("uuid") == database:
                        target_db = db
                        break

                if target_db:
                    return {
                        "success": True,
                        "database": {
                            "name": target_db.get("name"),
                            "uuid": target_db.get("uuid"),
                            "version": target_db.get("version"),
                            "created_at": target_db.get("created_at"),
                            "num_tables": target_db.get("num_tables", "unknown"),
                            "file_size": target_db.get("file_size", "unknown")
                        }
                    }
                else:
                    return {
                        "success": False,
                        "error": f"데이터베이스를 찾을 수 없습니다: {database}"
                    }
            else:
                return {
                    "success": False,
                    "error": "데이터베이스 조회 실패",
                    "details": data.get("errors", [])
                }
        else:
            # 전체 데이터베이스 목록
            url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database"
            response = requests.get(url, headers=headers, timeout=30)
            data = response.json()

            if data.get("success"):
                databases = data.get("result", [])
                return {
                    "success": True,
                    "count": len(databases),
                    "databases": [
                        {
                            "name": db.get("name"),
                            "uuid": db.get("uuid"),
                            "created_at": db.get("created_at")
                        }
                        for db in databases
                    ]
                }
            else:
                return {
                    "success": False,
                    "error": "데이터베이스 목록 조회 실패",
                    "details": data.get("errors", [])
                }

    except Exception as e:
        return {"success": False, "error": str(e)}
