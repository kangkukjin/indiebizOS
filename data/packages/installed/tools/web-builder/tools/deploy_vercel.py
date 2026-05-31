"""
deploy_vercel.py
Vercel에 사이트를 배포합니다.
"""

import subprocess
import json
import os

TOOL_NAME = "deploy_vercel"
TOOL_DESCRIPTION = "Vercel에 사이트를 배포합니다"
TOOL_PARAMETERS = {
    "project_path": {
        "type": "string",
        "description": "프로젝트 경로",
        "required": True
    },
    "production": {
        "type": "boolean",
        "description": "프로덕션 배포 여부 (False면 프리뷰 배포)",
        "default": False
    },
    "project_name": {
        "type": "string",
        "description": "Vercel 프로젝트 이름 (선택사항)",
        "required": False
    }
}


def check_vercel_cli() -> bool:
    """Vercel CLI 설치 확인"""
    try:
        result = subprocess.run(
            ["vercel", "--version"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def check_vercel_auth(token: str = None) -> bool:
    """Vercel 인증 상태 확인 (토큰 우선)"""
    cmd = ["vercel", "whoami"]
    if token:
        cmd.extend(["--token", token])
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except:
        return False


def run_command(cmd: list, cwd: str = None, timeout: int = 180) -> dict:
    """명령어 실행"""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "배포 시간 초과"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _mask_token_in_text(text: str, token: str) -> str:
    """로그/에러 메시지에서 토큰 노출 방지"""
    if not text or not token:
        return text
    return text.replace(token, "***")


def run(project_path: str, production: bool = False, project_name: str = None) -> dict:
    """
    Vercel에 배포

    Args:
        project_path: 프로젝트 경로
        production: 프로덕션 배포 여부
        project_name: Vercel 프로젝트 이름

    Returns:
        배포 결과
    """
    if not os.path.exists(project_path):
        return {"success": False, "error": f"프로젝트를 찾을 수 없습니다: {project_path}"}

    # Vercel CLI 확인
    if not check_vercel_cli():
        return {
            "success": False,
            "error": "Vercel CLI가 설치되어 있지 않습니다",
            "solution": "npm install -g vercel 명령어로 설치하세요"
        }

    # 인증 확인: VERCEL_TOKEN 환경변수 우선, 없으면 로컬 vercel login 폴백
    token = os.environ.get("VERCEL_TOKEN", "").strip() or None
    if not check_vercel_auth(token):
        if token:
            return {
                "success": False,
                "error": "VERCEL_TOKEN이 유효하지 않거나 만료되었습니다",
                "solution": "https://vercel.com/account/tokens 에서 토큰을 재발급 후 .env의 VERCEL_TOKEN을 갱신하고 백엔드를 재시작하세요"
            }
        return {
            "success": False,
            "error": "Vercel에 로그인되어 있지 않습니다",
            "solution": "환경변수 VERCEL_TOKEN을 .env에 설정하거나 vercel login 명령어로 로그인하세요"
        }

    results = []

    # 배포 명령어 구성
    deploy_cmd = ["vercel"]

    if production:
        deploy_cmd.append("--prod")
        results.append("🚀 프로덕션 배포 시작...")
    else:
        results.append("🔍 프리뷰 배포 시작...")

    # 프로젝트 이름 지정
    if project_name:
        deploy_cmd.extend(["--name", project_name])

    # 토큰 기반 인증 (환경변수가 있을 때만 명시 전달)
    if token:
        deploy_cmd.extend(["--token", token])

    # 확인 없이 배포
    deploy_cmd.append("--yes")

    # 배포 실행
    results.append("배포 진행 중... (최대 3분 소요)")
    deploy_result = run_command(deploy_cmd, cwd=project_path, timeout=180)

    if not deploy_result["success"]:
        error_msg = deploy_result.get("stderr", deploy_result.get("error", ""))
        if token:
            error_msg = _mask_token_in_text(error_msg, token)
        return {
            "success": False,
            "error": f"배포 실패: {error_msg[:500]}",
            "logs": results
        }

    # 배포 URL 추출
    stdout = deploy_result.get("stdout", "")
    stderr = deploy_result.get("stderr", "")
    output = stdout + stderr

    # URL 찾기
    deploy_url = None
    for line in output.split("\n"):
        line = line.strip()
        if line.startswith("https://") and "vercel.app" in line:
            deploy_url = line
            break

    if not deploy_url:
        # 다른 패턴 시도
        import re
        url_match = re.search(r'https://[a-zA-Z0-9-]+\.vercel\.app', output)
        if url_match:
            deploy_url = url_match.group()

    results.append("✓ 배포 완료!")

    if deploy_url:
        results.append(f"🌐 URL: {deploy_url}")

    return {
        "success": True,
        "project_path": project_path,
        "production": production,
        "url": deploy_url,
        "logs": results,
        "note": "프로덕션 배포는 커스텀 도메인이 연결된 경우 해당 도메인으로도 접근 가능합니다"
    }


def get_deployments(project_path: str) -> dict:
    """배포 목록 조회"""
    cmd = ["vercel", "ls"]
    token = os.environ.get("VERCEL_TOKEN", "").strip() or None
    if token:
        cmd.extend(["--token", token])
    result = run_command(cmd, cwd=project_path, timeout=30)

    if not result["success"]:
        return {"success": False, "error": "배포 목록 조회 실패"}

    return {
        "success": True,
        "deployments": result["stdout"]
    }


if __name__ == "__main__":
    result = run(
        project_path="/Users/kangkukjin/Desktop/AI/outputs/web-projects/test-project",
        production=False
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
