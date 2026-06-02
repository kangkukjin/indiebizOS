"""
preview_site.py
로컬에서 사이트를 미리보기합니다.
"""

import subprocess
import json
import os
import time
import signal

TOOL_NAME = "preview_site"
TOOL_DESCRIPTION = "로컬에서 사이트를 미리보기합니다"
TOOL_PARAMETERS = {
    "project_path": {
        "type": "string",
        "description": "프로젝트 경로",
        "required": True
    },
    "port": {
        "type": "number",
        "description": "포트 번호",
        "default": 3000
    },
    "action": {
        "type": "string",
        "description": "액션 (start, stop, status)",
        "enum": ["start", "stop", "status"],
        "default": "start"
    }
}

# 실행 중인 프로세스 추적
PROCESS_FILE = "/tmp/web-builder-preview.json"


def save_process_info(project_path: str, pid: int, port: int) -> None:
    """프로세스 정보 저장"""
    info = {}
    if os.path.exists(PROCESS_FILE):
        with open(PROCESS_FILE, "r") as f:
            info = json.load(f)

    info[project_path] = {"pid": pid, "port": port}

    with open(PROCESS_FILE, "w") as f:
        json.dump(info, f)


def get_process_info(project_path: str) -> dict:
    """프로세스 정보 조회"""
    if not os.path.exists(PROCESS_FILE):
        return None

    with open(PROCESS_FILE, "r") as f:
        info = json.load(f)

    return info.get(project_path)


def remove_process_info(project_path: str) -> None:
    """프로세스 정보 삭제"""
    if not os.path.exists(PROCESS_FILE):
        return

    with open(PROCESS_FILE, "r") as f:
        info = json.load(f)

    if project_path in info:
        del info[project_path]

    with open(PROCESS_FILE, "w") as f:
        json.dump(info, f)


def is_process_running(pid: int) -> bool:
    """프로세스 실행 여부 확인"""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def start_preview(project_path: str, port: int) -> dict:
    """개발 서버 시작"""
    # 이미 실행 중인지 확인
    existing = get_process_info(project_path)
    if existing and is_process_running(existing["pid"]):
        return {
            "success": True,
            "status": "already_running",
            "message": f"이미 실행 중입니다",
            "url": f"http://localhost:{existing['port']}",
            "pid": existing["pid"]
        }

    # package.json 확인
    package_json = os.path.join(project_path, "package.json")
    if not os.path.exists(package_json):
        return {
            "success": False,
            "error": "package.json을 찾을 수 없습니다"
        }

    try:
        # 백그라운드에서 개발 서버 실행
        env = os.environ.copy()
        env["PORT"] = str(port)

        process = subprocess.Popen(
            ["npm", "run", "dev", "--", "-p", str(port)],
            cwd=project_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            start_new_session=True
        )

        # 서버 시작 대기
        time.sleep(3)

        if process.poll() is not None:
            # 프로세스가 종료됨
            stderr = process.stderr.read().decode() if process.stderr else ""
            return {
                "success": False,
                "error": f"서버 시작 실패: {stderr[:500]}"
            }

        # 프로세스 정보 저장
        save_process_info(project_path, process.pid, port)

        return {
            "success": True,
            "status": "started",
            "message": "개발 서버가 시작되었습니다",
            "url": f"http://localhost:{port}",
            "pid": process.pid,
            "note": "브라우저에서 위 URL을 열어 확인하세요"
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"서버 시작 실패: {str(e)}"
        }


def stop_preview(project_path: str) -> dict:
    """개발 서버 중지"""
    process_info = get_process_info(project_path)

    if not process_info:
        return {
            "success": True,
            "status": "not_running",
            "message": "실행 중인 서버가 없습니다"
        }

    pid = process_info["pid"]

    if not is_process_running(pid):
        remove_process_info(project_path)
        return {
            "success": True,
            "status": "not_running",
            "message": "서버가 이미 종료되었습니다"
        }

    try:
        # 프로세스 그룹 종료
        os.killpg(os.getpgid(pid), signal.SIGTERM)
        time.sleep(1)

        # 강제 종료 (필요시)
        if is_process_running(pid):
            os.killpg(os.getpgid(pid), signal.SIGKILL)

        remove_process_info(project_path)

        return {
            "success": True,
            "status": "stopped",
            "message": "서버가 종료되었습니다"
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"서버 종료 실패: {str(e)}"
        }


def get_status(project_path: str) -> dict:
    """서버 상태 확인"""
    process_info = get_process_info(project_path)

    if not process_info:
        return {
            "success": True,
            "status": "not_running",
            "running": False
        }

    pid = process_info["pid"]
    port = process_info["port"]

    if is_process_running(pid):
        return {
            "success": True,
            "status": "running",
            "running": True,
            "url": f"http://localhost:{port}",
            "pid": pid,
            "port": port
        }
    else:
        remove_process_info(project_path)
        return {
            "success": True,
            "status": "not_running",
            "running": False
        }


def run(project_path: str, port: int = 3000, action: str = "start") -> dict:
    """
    로컬 미리보기 서버 관리

    Args:
        project_path: 프로젝트 경로
        port: 포트 번호
        action: 액션 (start, stop, status)

    Returns:
        결과
    """
    if not os.path.exists(project_path):
        return {"success": False, "error": f"프로젝트를 찾을 수 없습니다: {project_path}"}

    if action == "start":
        return start_preview(project_path, port)
    elif action == "stop":
        return stop_preview(project_path)
    elif action == "status":
        return get_status(project_path)
    else:
        return {"success": False, "error": f"알 수 없는 액션: {action}"}


if __name__ == "__main__":
    result = run(
        project_path="/Users/kangkukjin/Desktop/AI/outputs/web-projects/test-project",
        action="status"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
