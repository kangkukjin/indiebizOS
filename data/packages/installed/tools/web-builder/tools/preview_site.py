"""
preview_site.py
로컬에서 사이트를 미리보기합니다.
"""

import subprocess
import json
import os
import time
import tempfile

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

# 실행 중인 프로세스 추적 (전 OS 임시 디렉토리 — 구 하드코딩 /tmp 대체)
PROCESS_FILE = os.path.join(tempfile.gettempdir(), "web-builder-preview.json")


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
    """프로세스 실행 여부 확인 (전 OS).

    판정은 common.platform_utils.pid_alive 단일 소스에 있다 — 이 함수는 그 얇은 경유다.
    ★윈도우에선 os.kill(pid, 0) 이 프로세스를 실제로 종료(TerminateProcess)시키므로 금지.
      이 파일은 그 사실을 알고 psutil 로 피하고 있었지만, 판정이 두 벌이면 한쪽만 고쳐지는
      드리프트가 생긴다(실제로 저장소의 다른 세 곳은 os.kill 관용구로 잠복해 있었다, 2026-08-22).
    함수 안 import: 이 모듈은 백엔드가 importlib 로 인프로세스 로드하지만 파일 단독 실행
      진입점(__main__)도 있어, 톱레벨 의존으로 만들면 그 경로가 import 시점에 깨진다."""
    from common.platform_utils import pid_alive
    return pid_alive(pid)


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

        # npm 은 윈도우에서 npm.cmd — shutil.which 로 해소(미발견 시 OS별 기본명)
        import shutil
        npm_cmd = shutil.which("npm") or ("npm.cmd" if os.name == "nt" else "npm")
        # 백그라운드 분리 — 유닉스 setsid / 윈도우 새 프로세스 그룹
        popen_kw = {}
        if os.name == "nt":
            popen_kw["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            popen_kw["start_new_session"] = True
        process = subprocess.Popen(
            [npm_cmd, "run", "dev", "--", "-p", str(port)],
            cwd=project_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            **popen_kw
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
        # 프로세스 트리 종료 (psutil, 전 OS — 구 os.killpg 대체).
        # 자식(npm→node dev 서버)까지 함께 정리.
        import psutil
        try:
            parent = psutil.Process(pid)
            procs = parent.children(recursive=True) + [parent]
        except psutil.NoSuchProcess:
            procs = []
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass
        _gone, alive = psutil.wait_procs(procs, timeout=3)
        for p in alive:  # 강제 종료 (필요시)
            try:
                p.kill()
            except Exception:
                pass

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
        project_path="outputs/web-projects/test-project",
        action="status"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
