"""
Cloudflare R2 버킷/파일 목록 조회
"""

import requests


def run(tool_input: dict, creds: dict) -> dict:
    """
    Cloudflare R2 버킷 또는 파일 목록 조회

    Args:
        tool_input: {bucket (선택), prefix (선택)}
        creds: {api_token, account_id}

    Returns:
        버킷 목록 또는 파일 목록
    """
    bucket = tool_input.get("bucket")
    prefix = tool_input.get("prefix", "")
    account_id = creds["account_id"]
    api_token = creds["api_token"]

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }

    try:
        if not bucket:
            # 버킷 목록 조회
            url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/r2/buckets"
            response = requests.get(url, headers=headers, timeout=30)
            data = response.json()

            if data.get("success"):
                buckets = data.get("result", {}).get("buckets", [])
                return {
                    "success": True,
                    "count": len(buckets),
                    "buckets": [
                        {
                            "name": b.get("name"),
                            "creation_date": b.get("creation_date"),
                            "location": b.get("location")
                        }
                        for b in buckets
                    ]
                }
            else:
                return {
                    "success": False,
                    "error": "버킷 목록 조회 실패",
                    "details": data.get("errors", [])
                }
        else:
            # 버킷 내 파일 목록 조회 (S3 호환 API 사용 필요)
            # wrangler CLI 사용
            import subprocess
            import os

            env = os.environ.copy()
            env["CLOUDFLARE_API_TOKEN"] = api_token
            env["CLOUDFLARE_ACCOUNT_ID"] = account_id

            cmd = ["npx", "wrangler", "r2", "object", "list", bucket]
            if prefix:
                cmd.extend(["--prefix", prefix])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=60
            )

            if result.returncode == 0:
                # 출력 파싱
                lines = result.stdout.strip().split("\n")
                files = []
                for line in lines:
                    if line and not line.startswith("Listing"):
                        parts = line.split()
                        if len(parts) >= 2:
                            files.append({
                                "key": parts[-1],
                                "size": parts[0] if len(parts) > 1 else "unknown"
                            })

                return {
                    "success": True,
                    "bucket": bucket,
                    "prefix": prefix or "(root)",
                    "count": len(files),
                    "files": files[:100]  # 최대 100개
                }
            else:
                return {
                    "success": False,
                    "error": f"파일 목록 조회 실패",
                    "stderr": result.stderr
                }

    except Exception as e:
        return {"success": False, "error": str(e)}
