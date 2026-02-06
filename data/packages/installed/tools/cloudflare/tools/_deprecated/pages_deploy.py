"""
Cloudflare Pages 배포 도구
"""

import subprocess
import json
import os
from pathlib import Path


def run(tool_input: dict, creds: dict) -> dict:
    """
    Cloudflare Pages에 정적 사이트 배포

    Args:
        tool_input: {project_name, directory, production}
        creds: {api_token, account_id}

    Returns:
        배포 결과
    """
    project_name = tool_input.get("project_name")
    directory = tool_input.get("directory")
    production = tool_input.get("production", True)

    if not project_name or not directory:
        return {"success": False, "error": "project_name과 directory가 필요합니다."}

    directory_path = Path(directory)
    if not directory_path.exists():
        return {"success": False, "error": f"디렉토리가 존재하지 않습니다: {directory}"}

    try:
        # 환경변수 설정
        env = os.environ.copy()
        env["CLOUDFLARE_API_TOKEN"] = creds["api_token"]
        env["CLOUDFLARE_ACCOUNT_ID"] = creds["account_id"]

        # wrangler pages deploy 명령 실행
        cmd = [
            "npx", "wrangler", "pages", "deploy",
            str(directory_path),
            "--project-name", project_name,
        ]

        if production:
            cmd.append("--branch=main")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=300,  # 5분 타임아웃
            cwd=str(directory_path.parent)
        )

        if result.returncode == 0:
            # 배포 URL 추출
            output = result.stdout
            url = None
            for line in output.split("\n"):
                if "https://" in line and ".pages.dev" in line:
                    url = line.strip()
                    break

            return {
                "success": True,
                "message": "배포 성공!",
                "project_name": project_name,
                "url": url or f"https://{project_name}.pages.dev",
                "production": production,
                "output": output[-500:] if len(output) > 500 else output  # 마지막 500자
            }
        else:
            return {
                "success": False,
                "error": "배포 실패",
                "stderr": result.stderr,
                "stdout": result.stdout
            }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "배포 타임아웃 (5분 초과)"}
    except FileNotFoundError:
        return {
            "success": False,
            "error": "wrangler CLI가 설치되어 있지 않습니다. 'npm install -g wrangler'를 실행하세요."
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
