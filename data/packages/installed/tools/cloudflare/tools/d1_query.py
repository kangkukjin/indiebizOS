"""
Cloudflare D1 데이터베이스 쿼리 실행
"""

import subprocess
import os
import json


def run(tool_input: dict, creds: dict) -> dict:
    """
    Cloudflare D1 데이터베이스에 SQL 쿼리 실행

    Args:
        tool_input: {database, query, params}
        creds: {api_token, account_id}

    Returns:
        쿼리 결과
    """
    database = tool_input.get("database")
    query = tool_input.get("query")
    params = tool_input.get("params", [])

    if not database or not query:
        return {"success": False, "error": "database와 query가 필요합니다."}

    try:
        env = os.environ.copy()
        env["CLOUDFLARE_API_TOKEN"] = creds["api_token"]
        env["CLOUDFLARE_ACCOUNT_ID"] = creds["account_id"]

        # 파라미터 바인딩이 있는 경우 처리
        # wrangler d1 execute는 --command 옵션 사용
        final_query = query

        # 간단한 파라미터 대체 (실제로는 prepared statement 사용 권장)
        if params:
            for i, param in enumerate(params):
                # ?를 순서대로 값으로 대체 (문자열은 따옴표 추가)
                if isinstance(param, str):
                    replacement = f"'{param}'"
                else:
                    replacement = str(param)
                final_query = final_query.replace("?", replacement, 1)

        # wrangler d1 execute 명령 실행
        result = subprocess.run(
            ["npx", "wrangler", "d1", "execute", database,
             "--command", final_query,
             "--json"],
            capture_output=True,
            text=True,
            env=env,
            timeout=60
        )

        if result.returncode == 0:
            try:
                output = json.loads(result.stdout)
                return {
                    "success": True,
                    "database": database,
                    "query": query,
                    "results": output
                }
            except json.JSONDecodeError:
                return {
                    "success": True,
                    "database": database,
                    "query": query,
                    "raw_output": result.stdout
                }
        else:
            return {
                "success": False,
                "error": "쿼리 실행 실패",
                "stderr": result.stderr,
                "stdout": result.stdout
            }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "쿼리 타임아웃 (1분 초과)"}
    except FileNotFoundError:
        return {
            "success": False,
            "error": "wrangler CLI가 설치되어 있지 않습니다. 'npm install -g wrangler'를 실행하세요."
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
