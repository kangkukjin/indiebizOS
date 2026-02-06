"""
Cloudflare R2 파일 업로드 도구
"""

import subprocess
import os
from pathlib import Path


def run(tool_input: dict, creds: dict) -> dict:
    """
    Cloudflare R2에 파일 업로드

    Args:
        tool_input: {bucket, file_path, directory, key, prefix}
        creds: {api_token, account_id}

    Returns:
        업로드 결과
    """
    bucket = tool_input.get("bucket")
    file_path = tool_input.get("file_path")
    directory = tool_input.get("directory")
    key = tool_input.get("key")
    prefix = tool_input.get("prefix", "")

    if not bucket:
        return {"success": False, "error": "bucket이 필요합니다."}

    if not file_path and not directory:
        return {"success": False, "error": "file_path 또는 directory가 필요합니다."}

    try:
        env = os.environ.copy()
        env["CLOUDFLARE_API_TOKEN"] = creds["api_token"]
        env["CLOUDFLARE_ACCOUNT_ID"] = creds["account_id"]

        uploaded_files = []

        if file_path:
            # 단일 파일 업로드
            src = Path(file_path)
            if not src.exists():
                return {"success": False, "error": f"파일이 존재하지 않습니다: {file_path}"}

            dest_key = key or src.name

            result = subprocess.run(
                ["npx", "wrangler", "r2", "object", "put",
                 f"{bucket}/{dest_key}",
                 "--file", str(src)],
                capture_output=True,
                text=True,
                env=env,
                timeout=300
            )

            if result.returncode == 0:
                uploaded_files.append({"file": src.name, "key": dest_key})
            else:
                return {
                    "success": False,
                    "error": f"파일 업로드 실패: {src.name}",
                    "stderr": result.stderr
                }

        elif directory:
            # 디렉토리 업로드
            dir_path = Path(directory)
            if not dir_path.exists() or not dir_path.is_dir():
                return {"success": False, "error": f"디렉토리가 존재하지 않습니다: {directory}"}

            for file in dir_path.rglob("*"):
                if file.is_file():
                    relative_path = file.relative_to(dir_path)
                    dest_key = f"{prefix}{relative_path}" if prefix else str(relative_path)

                    result = subprocess.run(
                        ["npx", "wrangler", "r2", "object", "put",
                         f"{bucket}/{dest_key}",
                         "--file", str(file)],
                        capture_output=True,
                        text=True,
                        env=env,
                        timeout=60
                    )

                    if result.returncode == 0:
                        uploaded_files.append({"file": str(relative_path), "key": dest_key})
                    else:
                        return {
                            "success": False,
                            "error": f"파일 업로드 실패: {relative_path}",
                            "stderr": result.stderr,
                            "uploaded_so_far": uploaded_files
                        }

        return {
            "success": True,
            "message": f"{len(uploaded_files)}개 파일 업로드 완료",
            "bucket": bucket,
            "uploaded_files": uploaded_files
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "업로드 타임아웃"}
    except FileNotFoundError:
        return {
            "success": False,
            "error": "wrangler CLI가 설치되어 있지 않습니다. 'npm install -g wrangler'를 실행하세요."
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
