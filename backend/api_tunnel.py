"""
api_tunnel.py - Cloudflare Tunnel 관리 API
터널 프로세스 시작/종료 및 설정 관리
"""

import json
import subprocess
import signal
import os
import re
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from runtime_utils import get_base_path

router = APIRouter(prefix="/tunnel", tags=["tunnel"])

# 설정 파일 경로
DATA_PATH = get_base_path() / "data"
CONFIG_FILE = DATA_PATH / "tunnel_config.json"

# 터널 프로세스 추적
_tunnel_process: Optional[subprocess.Popen] = None


def get_default_config():
    """기본 설정"""
    return {
        "enabled": False,
        "auto_start": False,
        "tunnel_name": "",
        "hostname": "",
        "finder_hostname": "",
        "launcher_hostname": "",
        "config_path": str(Path.home() / ".cloudflared" / "config.yml")
    }


def load_config() -> dict:
    """설정 로드"""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                # 기본값 병합
                default = get_default_config()
                default.update(config)
                return default
        except:
            pass
    return get_default_config()


def save_config(config: dict):
    """설정 저장"""
    DATA_PATH.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_cloudflared_path() -> str:
    """cloudflared 실행 경로 찾기"""
    # 가능한 경로들
    possible_paths = [
        "/opt/homebrew/bin/cloudflared",  # macOS Apple Silicon (Homebrew)
        "/usr/local/bin/cloudflared",      # macOS Intel / Linux
        "/usr/bin/cloudflared",            # Linux 시스템
        "cloudflared",                      # PATH에 있는 경우
    ]

    for path in possible_paths:
        try:
            result = subprocess.run(
                [path, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return path
        except:
            continue

    return ""


def is_cloudflared_installed() -> bool:
    """cloudflared 설치 여부 확인"""
    return bool(get_cloudflared_path())


def is_tunnel_running() -> bool:
    """터널 프로세스 실행 중인지 확인"""
    global _tunnel_process

    # 내부 프로세스 확인
    if _tunnel_process is not None:
        poll = _tunnel_process.poll()
        if poll is None:
            return True
        else:
            _tunnel_process = None

    # 외부에서 실행 중인 cloudflared 확인
    try:
        result = subprocess.run(
            ["pgrep", "-f", "cloudflared tunnel run"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except:
        return False


def start_tunnel(tunnel_name: str, config_path: str = None) -> dict:
    """터널 시작"""
    global _tunnel_process

    if is_tunnel_running():
        return {"success": True, "message": "터널이 이미 실행 중입니다."}

    if not is_cloudflared_installed():
        return {
            "success": False,
            "error": "cloudflared가 설치되지 않았습니다.",
            "hint": "brew install cloudflared (macOS) 또는 apt install cloudflared (Linux)"
        }

    try:
        # cloudflared 경로 찾기
        cloudflared_bin = get_cloudflared_path()
        if not cloudflared_bin:
            return {"success": False, "error": "cloudflared를 찾을 수 없습니다."}

        # config.yml이 있으면 사용 (--config은 글로벌 플래그이므로 tunnel 앞에 위치)
        cmd = [cloudflared_bin]

        if config_path and Path(config_path).exists():
            cmd.extend(["--config", config_path])

        cmd.extend(["tunnel", "run", tunnel_name])

        # 백그라운드 프로세스로 실행
        # start_new_session 사용하지 않음 → 부모(FastAPI)와 같은 프로세스 그룹
        # → Ctrl+C(SIGINT) 시 cloudflared도 함께 시그널 수신하여 종료됨
        _tunnel_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # 잠시 대기 후 상태 확인
        import time
        time.sleep(2)

        if _tunnel_process.poll() is not None:
            # 프로세스가 즉시 종료됨 - stdout/stderr 모두 읽기
            returncode = _tunnel_process.returncode
            stdout_data = ""
            stderr_data = ""
            try:
                stdout_data = _tunnel_process.stdout.read().decode(errors="replace") if _tunnel_process.stdout else ""
                stderr_data = _tunnel_process.stderr.read().decode(errors="replace") if _tunnel_process.stderr else ""
            except Exception:
                pass
            _tunnel_process = None
            # stderr 우선, 없으면 stdout 사용
            output = (stderr_data.strip() or stdout_data.strip())
            details = f"(exit code: {returncode}) {output[:500]}" if output else f"프로세스 종료 코드: {returncode}"
            print(f"[Tunnel] 시작 실패 - cmd: {' '.join(cmd)}")
            print(f"[Tunnel] stdout: {stdout_data[:300]}")
            print(f"[Tunnel] stderr: {stderr_data[:300]}")
            return {
                "success": False,
                "error": "터널 시작 실패",
                "details": details
            }

        return {
            "success": True,
            "message": f"터널 '{tunnel_name}' 시작됨",
            "pid": _tunnel_process.pid
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def stop_tunnel() -> dict:
    """터널 종료"""
    global _tunnel_process

    stopped = False

    # 내부 프로세스 종료
    if _tunnel_process is not None:
        try:
            _tunnel_process.terminate()
            _tunnel_process.wait(timeout=5)
            stopped = True
        except:
            try:
                _tunnel_process.kill()
                stopped = True
            except:
                pass
        _tunnel_process = None

    # 외부 프로세스도 종료
    try:
        result = subprocess.run(
            ["pkill", "-f", "cloudflared tunnel run"],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            stopped = True
    except:
        pass

    if stopped or not is_tunnel_running():
        return {"success": True, "message": "터널이 종료되었습니다."}
    else:
        return {"success": False, "error": "터널 종료 실패"}


def parse_ingress_hostnames(config_path: str = None) -> dict:
    """config.yml의 ingress 규칙에서 서비스별 외부 호스트명 추출"""
    result = {"finder_hostname": "", "launcher_hostname": ""}

    if not config_path:
        config_path = str(Path.home() / ".cloudflared" / "config.yml")

    config_file = Path(config_path)
    if not config_file.exists():
        return result

    try:
        content = config_file.read_text(encoding="utf-8")

        # 간단한 YAML 파싱: hostname과 service 쌍 추출
        # ingress 블록에서 각 항목의 hostname → service 매핑
        entries = []
        current_hostname = None
        for line in content.split("\n"):
            stripped = line.strip()
            # hostname 라인
            hostname_match = re.match(r"^-?\s*hostname:\s*(.+)", stripped)
            if hostname_match:
                current_hostname = hostname_match.group(1).strip()
                continue
            # service 라인
            service_match = re.match(r"service:\s*(.+)", stripped)
            if service_match and current_hostname:
                service = service_match.group(1).strip()
                entries.append({"hostname": current_hostname, "service": service})
                current_hostname = None

        # 서비스 포트/경로로 finder vs launcher 판별
        for entry in entries:
            hostname = entry["hostname"]
            service = entry["service"]
            # NAS/Finder 서비스 (포트 8080 또는 경로에 nas/finder 포함)
            if "8080" in service or "nas" in service.lower() or "finder" in service.lower() or "finder" in hostname.lower():
                result["finder_hostname"] = hostname
            # Launcher 서비스 (포트 3001 또는 경로에 launcher 포함)
            elif "3001" in service.lower() or "launcher" in service.lower() or "launcher" in hostname.lower():
                result["launcher_hostname"] = hostname
            # 메인 서비스 (포트 8765) - 단일 호스트명으로 모두 서빙하는 경우
            elif "8765" in service:
                if not result["finder_hostname"]:
                    result["finder_hostname"] = hostname
                if not result["launcher_hostname"]:
                    result["launcher_hostname"] = hostname
    except Exception as e:
        print(f"[Tunnel] config.yml 파싱 실패: {e}")

    return result


# === API 엔드포인트 ===

class TunnelConfig(BaseModel):
    enabled: Optional[bool] = None
    auto_start: Optional[bool] = None
    tunnel_name: Optional[str] = None
    hostname: Optional[str] = None
    finder_hostname: Optional[str] = None
    launcher_hostname: Optional[str] = None
    config_path: Optional[str] = None


@router.get("/config")
async def get_tunnel_config():
    """터널 설정 조회"""
    config = load_config()

    # 설정 파일에 호스트명이 없으면 config.yml에서 자동 추출 (폴백)
    finder_host = config.get("finder_hostname", "")
    launcher_host = config.get("launcher_hostname", "")
    if not finder_host or not launcher_host:
        ingress = parse_ingress_hostnames(config.get("config_path"))
        if not finder_host:
            finder_host = ingress["finder_hostname"]
        if not launcher_host:
            launcher_host = ingress["launcher_hostname"]

    return {
        "success": True,
        **config,
        "cloudflared_installed": is_cloudflared_installed(),
        "running": is_tunnel_running(),
        "finder_hostname": finder_host,
        "launcher_hostname": launcher_host,
    }


@router.post("/config")
async def update_tunnel_config(update: TunnelConfig):
    """터널 설정 저장"""
    config = load_config()

    # None이 아닌 값만 업데이트
    update_dict = update.dict(exclude_none=True)
    config.update(update_dict)

    save_config(config)

    return {"success": True, "config": config}


@router.post("/start")
def api_start_tunnel():
    """터널 시작 (동기 함수 - subprocess/sleep 사용으로 인해 def 사용)"""
    config = load_config()

    if not config.get("tunnel_name"):
        raise HTTPException(status_code=400, detail="터널 이름이 설정되지 않았습니다.")

    result = start_tunnel(
        tunnel_name=config["tunnel_name"],
        config_path=config.get("config_path")
    )

    if result["success"]:
        config["enabled"] = True
        save_config(config)

    return result


@router.post("/stop")
def api_stop_tunnel():
    """터널 종료 (동기 함수 - subprocess 사용으로 인해 def 사용)"""
    result = stop_tunnel()

    if result["success"]:
        config = load_config()
        config["enabled"] = False
        save_config(config)

    return result


@router.get("/status")
async def get_tunnel_status():
    """터널 상태 조회"""
    running = is_tunnel_running()
    config = load_config()

    return {
        "success": True,
        "running": running,
        "tunnel_name": config.get("tunnel_name", ""),
        "hostname": config.get("hostname", ""),
        "cloudflared_installed": is_cloudflared_installed()
    }


# 앱 시작 시 자동 시작 체크
def auto_start_if_enabled():
    """설정에 따라 자동 시작"""
    config = load_config()
    if config.get("auto_start") and config.get("tunnel_name"):
        result = start_tunnel(
            tunnel_name=config["tunnel_name"],
            config_path=config.get("config_path")
        )
        if result["success"]:
            print(f"[Tunnel] 자동 시작됨: {config['tunnel_name']}")
        else:
            print(f"[Tunnel] 자동 시작 실패: {result.get('error', 'unknown')}")
