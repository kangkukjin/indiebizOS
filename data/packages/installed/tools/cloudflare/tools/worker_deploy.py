"""
Cloudflare Workers 배포 도구
"""

import subprocess
import json
import os
import tempfile
from pathlib import Path


def run(tool_input: dict, creds: dict) -> dict:
    """
    Cloudflare Worker 생성/배포

    Args:
        tool_input: {worker_name, code, file_path}
        creds: {api_token, account_id}

    Returns:
        배포 결과
    """
    worker_name = tool_input.get("worker_name")
    code = tool_input.get("code")
    file_path = tool_input.get("file_path")

    if not worker_name:
        return {"success": False, "error": "worker_name이 필요합니다."}

    if not code and not file_path:
        return {"success": False, "error": "code 또는 file_path 중 하나가 필요합니다."}

    try:
        # 임시 디렉토리 생성
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Worker 코드 파일 준비
            if file_path:
                src_path = Path(file_path)
                if not src_path.exists():
                    return {"success": False, "error": f"파일이 존재하지 않습니다: {file_path}"}
                worker_code = src_path.read_text(encoding="utf-8")
            else:
                worker_code = code

            # index.js 생성
            worker_file = tmp_path / "index.js"
            worker_file.write_text(worker_code, encoding="utf-8")

            # wrangler.toml 생성
            wrangler_config = f"""
name = "{worker_name}"
main = "index.js"
compatibility_date = "2024-01-01"

[vars]
# 환경 변수는 여기에 추가
"""
            wrangler_file = tmp_path / "wrangler.toml"
            wrangler_file.write_text(wrangler_config, encoding="utf-8")

            # 환경변수 설정
            env = os.environ.copy()
            env["CLOUDFLARE_API_TOKEN"] = creds["api_token"]
            env["CLOUDFLARE_ACCOUNT_ID"] = creds["account_id"]

            # wrangler deploy 명령 실행
            result = subprocess.run(
                ["npx", "wrangler", "deploy"],
                capture_output=True,
                text=True,
                env=env,
                timeout=120,
                cwd=str(tmp_path)
            )

            if result.returncode == 0:
                # URL 추출
                output = result.stdout
                url = f"https://{worker_name}.{creds['account_id'][:8]}.workers.dev"

                for line in output.split("\n"):
                    if "https://" in line and "workers.dev" in line:
                        url = line.strip()
                        break

                return {
                    "success": True,
                    "message": "Worker 배포 성공!",
                    "worker_name": worker_name,
                    "url": url,
                    "output": output[-500:] if len(output) > 500 else output
                }
            else:
                return {
                    "success": False,
                    "error": "Worker 배포 실패",
                    "stderr": result.stderr,
                    "stdout": result.stdout
                }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "배포 타임아웃 (2분 초과)"}
    except FileNotFoundError:
        return {
            "success": False,
            "error": "wrangler CLI가 설치되어 있지 않습니다. 'npm install -g wrangler'를 실행하세요."
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
