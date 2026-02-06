"""
Cloudflare Tunnel 관리 도구

cloudflared CLI를 통해 터널을 생성하고 관리합니다.
NAS/원격 Finder 등 로컬 서비스를 외부에 안전하게 노출할 때 사용합니다.
"""

import json
import os
import subprocess
import shutil
from pathlib import Path


def run_command(cmd: list, timeout: int = 30) -> dict:
    """명령어 실행"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "명령어 타임아웃"}
    except FileNotFoundError:
        return {"success": False, "error": "cloudflared가 설치되어 있지 않습니다"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def check_cloudflared() -> dict:
    """cloudflared 설치 및 로그인 상태 확인"""
    # 설치 확인
    cloudflared_path = shutil.which("cloudflared")
    if not cloudflared_path:
        return {
            "installed": False,
            "logged_in": False,
            "error": "cloudflared가 설치되어 있지 않습니다",
            "install_guide": {
                "macOS": "brew install cloudflared",
                "Linux": "curl -L -o cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb && sudo dpkg -i cloudflared.deb",
                "Windows": "winget install Cloudflare.cloudflared"
            }
        }

    # 버전 확인
    version_result = run_command(["cloudflared", "version"])
    version = version_result.get("stdout", "unknown") if version_result["success"] else "unknown"

    # 로그인 상태 확인 (인증서 파일 존재 여부)
    cert_path = Path.home() / ".cloudflared" / "cert.pem"
    logged_in = cert_path.exists()

    # 기존 터널 목록 확인
    tunnels = []
    if logged_in:
        tunnel_result = run_command(["cloudflared", "tunnel", "list", "-o", "json"])
        if tunnel_result["success"]:
            try:
                tunnels = json.loads(tunnel_result["stdout"])
            except:
                pass

    return {
        "installed": True,
        "path": cloudflared_path,
        "version": version,
        "logged_in": logged_in,
        "cert_path": str(cert_path) if logged_in else None,
        "existing_tunnels": len(tunnels),
        "tunnels": tunnels[:5] if tunnels else [],  # 최대 5개만
        "login_command": "cloudflared tunnel login" if not logged_in else None
    }


def create_tunnel(name: str) -> dict:
    """새 터널 생성"""
    # 상태 확인
    status = check_cloudflared()
    if not status["installed"]:
        return {"success": False, **status}

    if not status["logged_in"]:
        return {
            "success": False,
            "error": "Cloudflare에 로그인되어 있지 않습니다",
            "action_required": "먼저 터미널에서 'cloudflared tunnel login' 을 실행하세요",
            "note": "브라우저가 열리면 Cloudflare 계정으로 로그인하고 도메인을 선택합니다"
        }

    # 터널 생성
    result = run_command(["cloudflared", "tunnel", "create", name])

    if result["success"]:
        # 터널 ID 추출
        stdout = result["stdout"]
        tunnel_id = None

        # "Created tunnel {name} with id {uuid}" 형식에서 ID 추출
        if "with id" in stdout:
            parts = stdout.split("with id")
            if len(parts) > 1:
                tunnel_id = parts[1].strip().split()[0]

        # credentials 파일 경로
        creds_path = Path.home() / ".cloudflared" / f"{tunnel_id}.json" if tunnel_id else None

        return {
            "success": True,
            "message": f"터널 '{name}' 생성 완료",
            "tunnel_name": name,
            "tunnel_id": tunnel_id,
            "credentials_file": str(creds_path) if creds_path and creds_path.exists() else None,
            "next_steps": [
                f"DNS 라우팅: cloudflared tunnel route dns {name} subdomain.yourdomain.com",
                "config.yml 생성 (cf_tunnel_config 사용)",
                f"터널 실행: cloudflared tunnel run {name}"
            ]
        }
    else:
        # 이미 존재하는 경우
        if "already exists" in result.get("stderr", ""):
            return {
                "success": False,
                "error": f"터널 '{name}'이(가) 이미 존재합니다",
                "suggestion": "다른 이름을 사용하거나, cf_tunnel_list()로 기존 터널을 확인하세요"
            }

        return {
            "success": False,
            "error": result.get("stderr") or result.get("error", "터널 생성 실패")
        }


def list_tunnels() -> dict:
    """터널 목록 조회"""
    status = check_cloudflared()
    if not status["installed"]:
        return {"success": False, **status}

    if not status["logged_in"]:
        return {
            "success": False,
            "error": "로그인 필요",
            "action_required": "cloudflared tunnel login"
        }

    result = run_command(["cloudflared", "tunnel", "list", "-o", "json"])

    if result["success"]:
        try:
            tunnels = json.loads(result["stdout"])
            return {
                "success": True,
                "count": len(tunnels),
                "tunnels": [
                    {
                        "id": t.get("id"),
                        "name": t.get("name"),
                        "created_at": t.get("created_at"),
                        "connections": len(t.get("connections", []))
                    }
                    for t in tunnels
                ]
            }
        except json.JSONDecodeError:
            return {
                "success": True,
                "raw": result["stdout"]
            }
    else:
        return {
            "success": False,
            "error": result.get("stderr") or "터널 목록 조회 실패"
        }


def route_dns(tunnel_name: str, hostname: str) -> dict:
    """터널에 DNS 라우팅 추가"""
    status = check_cloudflared()
    if not status["installed"] or not status["logged_in"]:
        return {"success": False, "error": "cloudflared 설치 및 로그인 필요"}

    result = run_command(["cloudflared", "tunnel", "route", "dns", tunnel_name, hostname])

    if result["success"] or "already exists" in result.get("stderr", "").lower():
        return {
            "success": True,
            "message": f"DNS 라우팅 설정 완료: {hostname} → 터널 '{tunnel_name}'",
            "hostname": hostname,
            "tunnel": tunnel_name,
            "note": "DNS 전파에 몇 분 걸릴 수 있습니다"
        }
    else:
        return {
            "success": False,
            "error": result.get("stderr") or "DNS 라우팅 실패",
            "suggestion": "도메인이 Cloudflare에 등록되어 있는지 확인하세요"
        }


def generate_config(tunnel_name: str, hostname: str, local_port: int = 8765, tunnel_id: str = None) -> dict:
    """터널 설정 파일(config.yml) 생성"""
    config_dir = Path.home() / ".cloudflared"
    config_path = config_dir / "config.yml"

    # 터널 ID 조회 (미제공 시)
    if not tunnel_id:
        list_result = list_tunnels()
        if list_result.get("success"):
            for t in list_result.get("tunnels", []):
                if t.get("name") == tunnel_name:
                    tunnel_id = t.get("id")
                    break

    if not tunnel_id:
        return {
            "success": False,
            "error": f"터널 '{tunnel_name}'을(를) 찾을 수 없습니다",
            "suggestion": "먼저 cf_tunnel_create로 터널을 생성하세요"
        }

    # credentials 파일 경로
    creds_file = config_dir / f"{tunnel_id}.json"

    # config.yml 내용
    config_content = f"""# Cloudflare Tunnel Configuration
# Generated by IndieBiz OS

tunnel: {tunnel_id}
credentials-file: {creds_file}

ingress:
  - hostname: {hostname}
    service: http://localhost:{local_port}
  - service: http_status:404
"""

    # 기존 파일 백업
    if config_path.exists():
        backup_path = config_dir / "config.yml.backup"
        config_path.rename(backup_path)

    # 새 파일 작성
    config_path.write_text(config_content)

    return {
        "success": True,
        "message": "config.yml 생성 완료",
        "config_path": str(config_path),
        "tunnel_id": tunnel_id,
        "hostname": hostname,
        "local_service": f"http://localhost:{local_port}",
        "config_content": config_content,
        "run_command": f"cloudflared tunnel run {tunnel_name}",
        "access_url": f"https://{hostname}/nas/app"
    }


def delete_tunnel(tunnel_name: str) -> dict:
    """터널 삭제"""
    status = check_cloudflared()
    if not status["installed"] or not status["logged_in"]:
        return {"success": False, "error": "cloudflared 설치 및 로그인 필요"}

    # 연결 정리
    run_command(["cloudflared", "tunnel", "cleanup", tunnel_name])

    # 터널 삭제
    result = run_command(["cloudflared", "tunnel", "delete", tunnel_name])

    if result["success"]:
        return {
            "success": True,
            "message": f"터널 '{tunnel_name}' 삭제 완료"
        }
    else:
        return {
            "success": False,
            "error": result.get("stderr") or "터널 삭제 실패",
            "note": "활성 연결이 있으면 먼저 터널을 중지하세요"
        }


def get_run_instructions(tunnel_name: str) -> dict:
    """터널 실행 방법 안내"""
    config_path = Path.home() / ".cloudflared" / "config.yml"

    instructions = {
        "success": True,
        "tunnel_name": tunnel_name,
        "manual_run": {
            "command": f"cloudflared tunnel run {tunnel_name}",
            "description": "터미널에서 직접 실행 (터미널을 닫으면 종료)"
        },
        "background_run": {
            "command": f"nohup cloudflared tunnel run {tunnel_name} > /dev/null 2>&1 &",
            "description": "백그라운드 실행 (터미널 닫아도 유지)"
        },
        "service_install": {
            "macOS": "sudo cloudflared service install",
            "Linux": "sudo cloudflared service install && sudo systemctl enable cloudflared && sudo systemctl start cloudflared",
            "Windows": "cloudflared service install",
            "description": "시스템 서비스로 등록 (부팅 시 자동 시작)"
        },
        "config_exists": config_path.exists(),
        "config_path": str(config_path)
    }

    return instructions


def run(tool_input: dict, creds: dict = None) -> dict:
    """
    Tunnel 도구 실행 진입점

    action에 따라 다른 기능 실행:
    - status: 상태 확인
    - create: 터널 생성
    - list: 터널 목록
    - route: DNS 라우팅
    - config: config.yml 생성
    - delete: 터널 삭제
    - run_info: 실행 방법 안내
    - setup_remote_access: 원격 접근(Finder & 런처) 원스텝 설정
    """
    action = tool_input.get("action", "status")

    if action == "status":
        return check_cloudflared()

    elif action == "create":
        name = tool_input.get("name")
        if not name:
            return {"success": False, "error": "터널 이름(name)이 필요합니다"}
        return create_tunnel(name)

    elif action == "list":
        return list_tunnels()

    elif action == "route":
        tunnel_name = tool_input.get("tunnel_name")
        hostname = tool_input.get("hostname")
        if not tunnel_name or not hostname:
            return {"success": False, "error": "tunnel_name과 hostname이 필요합니다"}
        return route_dns(tunnel_name, hostname)

    elif action == "config":
        tunnel_name = tool_input.get("tunnel_name")
        hostname = tool_input.get("hostname")
        local_port = tool_input.get("local_port", 8765)
        if not tunnel_name or not hostname:
            return {"success": False, "error": "tunnel_name과 hostname이 필요합니다"}
        return generate_config(tunnel_name, hostname, local_port)

    elif action == "delete":
        name = tool_input.get("name")
        if not name:
            return {"success": False, "error": "터널 이름(name)이 필요합니다"}
        return delete_tunnel(name)

    elif action == "run_info":
        tunnel_name = tool_input.get("tunnel_name", "nas")
        return get_run_instructions(tunnel_name)

    elif action == "setup_remote_access":
        # 원격 접근(Finder & 런처) 원스텝 설정
        tunnel_name = tool_input.get("tunnel_name", "indiebiz")
        hostname = tool_input.get("hostname")
        local_port = tool_input.get("local_port", 8765)

        if not hostname:
            return {"success": False, "error": "hostname이 필요합니다 (예: home.yourdomain.com)"}

        results = {"steps": []}

        # 1. 상태 확인
        status = check_cloudflared()
        results["steps"].append({"step": "status", "result": status})

        if not status["installed"]:
            return {
                "success": False,
                "error": "cloudflared가 설치되어 있지 않습니다",
                "install_guide": status.get("install_guide"),
                "action_required": "먼저 cloudflared를 설치하세요",
                "steps": results["steps"]
            }

        if not status["logged_in"]:
            return {
                "success": False,
                "error": "Cloudflare 로그인이 필요합니다 (최초 1회)",
                "action_required": "터미널에서 다음 명령을 실행하세요:\n\n  cloudflared tunnel login\n\n브라우저가 열리면 Cloudflare 계정으로 로그인하고 터널에 사용할 도메인을 선택합니다.\n인증 완료 후 다시 이 명령을 실행하세요.",
                "login_command": "cloudflared tunnel login",
                "steps": results["steps"]
            }

        # 2. 터널 생성 (이미 있으면 스킵)
        existing = [t for t in status.get("tunnels", []) if t.get("name") == tunnel_name]
        if existing:
            results["steps"].append({
                "step": "create",
                "result": {"success": True, "message": "기존 터널 사용", "tunnel_id": existing[0].get("id")}
            })
            tunnel_id = existing[0].get("id")
        else:
            create_result = create_tunnel(tunnel_name)
            results["steps"].append({"step": "create", "result": create_result})
            if not create_result.get("success"):
                return {"success": False, "steps": results["steps"], "error": "터널 생성 실패"}
            tunnel_id = create_result.get("tunnel_id")

        # 3. DNS 라우팅
        route_result = route_dns(tunnel_name, hostname)
        results["steps"].append({"step": "route", "result": route_result})

        # 4. config.yml 생성
        config_result = generate_config(tunnel_name, hostname, local_port, tunnel_id)
        results["steps"].append({"step": "config", "result": config_result})

        return {
            "success": True,
            "message": "원격 접근 터널 설정 완료!",
            "tunnel_name": tunnel_name,
            "hostname": hostname,
            "access_urls": {
                "원격 Finder": f"https://{hostname}/nas/app",
                "원격 런처": f"https://{hostname}/launcher/app"
            },
            "run_command": f"cloudflared tunnel run {tunnel_name}",
            "steps": results["steps"],
            "next_steps": [
                "1. 런처 설정에서 원격 Finder/런처 활성화 및 비밀번호 설정",
                f"2. 터널 실행: cloudflared tunnel run {tunnel_name}",
                f"3. 브라우저에서 https://{hostname}/nas/app 또는 /launcher/app 접속"
            ]
        }

    # 하위 호환성: setup_nas도 setup_remote_access로 처리
    elif action == "setup_nas":
        tool_input["action"] = "setup_remote_access"
        return run(tool_input, creds)

    else:
        return {
            "success": False,
            "error": f"알 수 없는 action: {action}",
            "available_actions": ["status", "create", "list", "route", "config", "delete", "run_info", "setup_remote_access"]
        }
