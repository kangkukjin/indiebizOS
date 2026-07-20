"""
api_tunnel.py - 터널(공개 도달성) 관리 API — 프로바이더 교체형

「공개 HTTPS 주소 → localhost:8765」 계약의 두 구현(2026-07-19, public_face 참조):
  - cloudflare: 이름 있는 터널(cloudflared, 도메인 필요) + Worker 가속기(R2 캐시·은닉)
  - tailscale : Funnel(무도메인 `*.ts.net`) → public_face 직접 서빙 게이트웨이가 받음
AI 모델 프로바이더처럼 config["provider"] 로 갈아끼운다. tailscale 선택 시 이 모듈이
Funnel 을 켜고, ts.net 주소를 public_face(direct_hosts·public_base)에 배선한다.
"""

import json
import subprocess
import signal
import os
import re
import time
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
        "provider": "cloudflare",   # cloudflare | tailscale — 공개 도달성 프로바이더
        "enabled": False,
        "auto_start": False,
        "tunnel_name": "",
        "hostname": "",
        "finder_hostname": "",
        "launcher_hostname": "",
        "config_path": str(Path.home() / ".cloudflared" / "config.yml"),
        "funnel_port": 8765,        # tailscale funnel 이 노출할 로컬 포트
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
    """cloudflared 실행 경로 찾기 (전 OS — PATH + OS별 표준 설치 경로)"""
    from common.platform_utils import find_binary
    hit = find_binary("cloudflared")  # PATH(윈도우 .exe 자동) 우선
    if hit:
        return hit
    # 폴백 — 실행해 --version 으로 검증하는 후보들(윈도우 경로 포함)
    if os.name == "nt":
        possible_paths = [
            r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
            r"C:\Program Files\cloudflared\cloudflared.exe",
            r"C:\ProgramData\chocolatey\bin\cloudflared.exe",
            "cloudflared",
        ]
    else:
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

    # 외부에서 실행 중인 cloudflared 확인 (psutil, 전 OS — 구 pgrep 대체)
    try:
        from common.platform_utils import is_process_running_by_marker
        return any(is_process_running_by_marker(p) for p in _tunnel_markers())
    except Exception:
        return False


def _tunnel_markers():
    """이 앱이 관리하는 indiebiz 터널 프로세스만 집는 마커 패턴들(조각 전부 포함 매칭).

    ★두 함정의 균형(2026-07-20 실측):
    - 옛 단일 부분문자열 "cloudflared tunnel run" 은 `--config x.yml` 이 사이에 끼는
      순간 못 잡는다 → stop 이 못 죽이고 is_running 이 못 봐서 유령 5마리 축적.
    - 그렇다고 ["cloudflared", "tunnel run"] 으로 넓히면 같은 기계의 **다른**
      cloudflared(원격관리 터널 remote-desktop.yml, 별도 상주)까지 죽인다.
    → 이 앱이 띄우는 두 형태만 정확히: 토큰 모드("tunnel run --token") +
      이름 모드("tunnel run <이름>"). 플래그가 어디 끼든 조각 매칭이라 안전."""
    patterns = [["cloudflared", "tunnel run --token"]]
    try:
        name = (load_config().get("tunnel_name") or "").strip()
    except Exception:
        name = ""
    if name:
        patterns.append(["cloudflared", f"tunnel run {name}"])
    return patterns


def start_tunnel(tunnel_name: str, config_path: str = None, tunnel_token: str = None,
                 force: bool = False, protocol: str = "") -> dict:
    """터널 시작 — 두 모드:
    - 토큰 모드(tunnel_token): `tunnel run --token` — 원격관리 터널(face_provision 발급).
      cert.pem·config.yml 불필요, ingress 는 CF 쪽 원격 설정이 담당.
    - 이름 모드(tunnel_name+config.yml): 기존 로컬관리 터널(맥의 indiebiz-os).

    force=True 면 이미 떠 있어도 내리고 다시 띄운다 — 원격관리 터널은 *접속 시점에*
    ingress 를 받아오므로, 낡은 설정을 물고 있는 프로세스는 재기동만이 갱신 수단이다
    (같은 내용 재PUT 은 CF 가 버전을 안 올려 푸시 자체가 없다 — 2026-07-20 윈도우 실측).
    protocol="http2" 는 QUIC(UDP 7844)이 막힌 망의 폴백."""
    global _tunnel_process

    if is_tunnel_running():
        if not force:
            return {"success": True, "message": "터널이 이미 실행 중입니다."}
        stop_tunnel()
        time.sleep(1.5)

    if not is_cloudflared_installed():
        return {
            "success": False,
            "error": "cloudflared가 설치되지 않았습니다.",
            "hint": ("winget install Cloudflare.cloudflared (Windows) 또는 "
                     "brew install cloudflared (macOS)")
        }

    try:
        # cloudflared 경로 찾기
        cloudflared_bin = get_cloudflared_path()
        if not cloudflared_bin:
            return {"success": False, "error": "cloudflared를 찾을 수 없습니다."}

        cmd = [cloudflared_bin]

        if protocol:
            cmd.extend(["--protocol", protocol])   # QUIC 막힌 망 폴백(http2)
        if tunnel_token:
            cmd.extend(["tunnel", "run", "--token", tunnel_token])
        else:
            # config.yml이 있으면 사용 (--config은 글로벌 플래그이므로 tunnel 앞에 위치)
            if config_path and Path(config_path).exists():
                cmd.extend(["--config", config_path])
            cmd.extend(["tunnel", "run", tunnel_name])

        # 백그라운드 프로세스로 실행
        # start_new_session 사용하지 않음 → 부모(FastAPI)와 같은 프로세스 그룹
        # → Ctrl+C(SIGINT) 시 cloudflared도 함께 시그널 수신하여 종료됨
        #
        # ★stdout/stderr 를 PIPE 로 잡아놓고 안 읽으면 안 된다 — 정상 기동 경로에선
        # 아무도 파이프를 안 읽어, 윈도우 익명 파이프 버퍼(~4KB)가 기동 로그로 차는
        # 순간 cloudflared(Go)가 로그 쓰기에서 통째로 블록된다(2026-07-20 윈도우 실측:
        # conns=1 degraded·ingress 미수신 빈 404·재시작 코인토스가 전부 이것. 어는
        # 시점이 레이스라 증상이 제멋대로였다). 맥은 버퍼가 64KB 라 늦게 터질 뿐 같은
        # 폭탄. 로그 파일 리다이렉트는 막히지 않고, 즉사 진단·평시 터널 디버깅도
        # 이 파일로 한다. 이게 있어야 자가치유 재기동(95e57d1)도 코인토스가 아니게 된다.
        log_path = DATA_PATH / "cloudflared.log"
        try:
            if log_path.exists() and log_path.stat().st_size > 5 * 1024 * 1024:
                log_path.replace(log_path.with_suffix(".log.1"))   # 단순 1세대 로테이션
        except Exception:
            pass
        log_f = open(log_path, "ab")
        try:
            _tunnel_process = subprocess.Popen(cmd, stdout=log_f, stderr=log_f)
        finally:
            log_f.close()   # 자식은 물려받은 핸들로 쓴다 — 부모 쪽 핸들은 닫아 누수 방지

        # 잠시 대기 후 상태 확인
        time.sleep(2)

        if _tunnel_process.poll() is not None:
            # 프로세스가 즉시 종료됨 — 로그 파일 꼬리에서 원인 읽기
            returncode = _tunnel_process.returncode
            _tunnel_process = None
            output = ""
            try:
                output = log_path.read_bytes()[-2000:].decode(errors="replace").strip()
            except Exception:
                pass
            details = f"(exit code: {returncode}) {output[-500:]}" if output else f"프로세스 종료 코드: {returncode}"
            # 토큰은 시크릿 — 로그에 남기지 않는다
            safe_cmd = ["***" if (i > 0 and cmd[i - 1] == "--token") else c
                        for i, c in enumerate(cmd)]
            print(f"[Tunnel] 시작 실패 - cmd: {' '.join(safe_cmd)}")
            print(f"[Tunnel] log tail: {output[-300:]}")
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

    # 외부 프로세스도 종료 (psutil, 전 OS — 구 pkill 대체)
    # ★이 앱의 터널 패턴만(_tunnel_markers) — 다른 cloudflared(원격관리 터널)는 남긴다
    try:
        from common.platform_utils import kill_processes_by_marker
        for p in _tunnel_markers():
            if kill_processes_by_marker(p):
                stopped = True
    except Exception:
        pass

    if stopped or not is_tunnel_running():
        return {"success": True, "message": "터널이 종료되었습니다."}
    else:
        return {"success": False, "error": "터널 종료 실패"}


# === Tailscale Funnel 프로바이더 ==============================================
# Funnel = 도메인 없이 `https://<기기>.<테일넷>.ts.net` 안정 공개 주소. cloudflared 와
# 달리 상주 프로세스를 우리가 띄우지 않는다 — tailscaled(앱/데몬)가 이미 돌고 있고,
# `tailscale funnel --bg <port>` 는 그 데몬에 서빙 설정을 심는 선언이라 명령은 즉시
# 끝난다(재부팅에도 설정 유지). 전제: Tailscale 앱 설치 + 로그인 + 테일넷에서 HTTPS
# 인증서·Funnel 노드 속성 허용(미충족이면 CLI 가 안내 문구를 stderr 로 내줌 → 그대로 노출).

def get_tailscale_path() -> str:
    """tailscale CLI 경로 (PATH + macOS 앱 번들 + 표준 설치 경로)"""
    try:
        from common.platform_utils import find_binary
        hit = find_binary("tailscale")
        if hit:
            return hit
    except Exception:
        pass
    # PATH 폴백 — 앱을 띄운 프로세스가 설치 이전 PATH 를 물고 있으면(윈도우 시작메뉴
    # 실행 등) find_binary 가 놓친다 → OS 표준 설치 경로를 직접 짚는다(cloudflared 동형).
    if os.name == "nt":
        candidates = [
            r"C:\Program Files\Tailscale\tailscale.exe",
            r"C:\Program Files (x86)\Tailscale\tailscale.exe",
        ]
    else:
        candidates = [
            "/Applications/Tailscale.app/Contents/MacOS/Tailscale",  # macOS 앱(App Store/직배포)
            "/opt/homebrew/bin/tailscale",
            "/usr/local/bin/tailscale",
            "/usr/bin/tailscale",
        ]
    for c in candidates:
        if Path(c).exists():
            return c
    return ""


def is_tailscale_installed() -> bool:
    return bool(get_tailscale_path())


def _ts_run(args: list, timeout: int = 20) -> dict:
    """tailscale CLI 실행 — {rc, out, err}"""
    binp = get_tailscale_path()
    if not binp:
        return {"rc": -1, "out": "", "err": "tailscale 미설치"}
    try:
        p = subprocess.run([binp] + args, capture_output=True, text=True, timeout=timeout)
        return {"rc": p.returncode, "out": p.stdout or "", "err": p.stderr or ""}
    except subprocess.TimeoutExpired:
        return {"rc": -1, "out": "", "err": f"tailscale {' '.join(args)} 시간 초과"}
    except Exception as e:
        return {"rc": -1, "out": "", "err": str(e)}


def tailscale_info() -> dict:
    """tailscale 상태 — 설치·로그인·ts.net 주소(DNSName)"""
    info = {"installed": is_tailscale_installed(), "logged_in": False,
            "backend_state": "", "dns_name": "", "error": ""}
    if not info["installed"]:
        info["error"] = ("Tailscale이 설치되지 않았습니다. "
                         "https://tailscale.com/download (macOS는 앱 설치 후 로그인)")
        return info
    r = _ts_run(["status", "--json"])
    if r["rc"] != 0:
        info["error"] = (r["err"] or r["out"]).strip()[:300]
        return info
    try:
        st = json.loads(r["out"])
        info["backend_state"] = st.get("BackendState", "")
        info["logged_in"] = info["backend_state"] == "Running"
        dns = ((st.get("Self") or {}).get("DNSName") or "").rstrip(".")
        info["dns_name"] = dns
        if not info["logged_in"]:
            info["error"] = f"Tailscale 로그인 필요 (상태: {info['backend_state'] or '알 수 없음'})"
    except Exception as e:
        info["error"] = f"상태 파싱 실패: {e}"
    return info


def is_funnel_running() -> bool:
    """Funnel 서빙 설정이 살아 있는지 — `funnel status` 출력에 proxy 대상이 보이면 on."""
    r = _ts_run(["funnel", "status"])
    if r["rc"] != 0:
        return False
    out = r["out"]
    return ("proxy" in out or "Funnel on" in out) and "No serve config" not in out


def start_funnel(port: int = 8765) -> dict:
    """Funnel 켜기 — https://<기기>.ts.net → localhost:<port>. --bg = 데몬에 영속 선언."""
    info = tailscale_info()
    if not info["installed"] or not info["logged_in"]:
        return {"success": False, "error": info["error"] or "tailscale 준비 안 됨", **info}
    r = _ts_run(["funnel", "--bg", str(port)], timeout=30)
    if r["rc"] != 0:
        # 인증서/노드속성 미허용 등 — CLI 안내문을 그대로 (설정 마법사의 다음 단계 안내)
        return {"success": False, "error": (r["err"] or r["out"]).strip()[:500], **info}
    base = f"https://{info['dns_name']}" if info["dns_name"] else ""
    # 직접 서빙 게이트웨이 배선 — ts.net 주소가 공개 얼굴이 된다
    wired = {}
    try:
        import public_face
        cfg = public_face.load_config()
        cfg["provider"] = "tailscale"
        # 합류(교체 아님) — cloudflare 직접서빙 호스트 등 다른 얼굴은 산 채로 둔다.
        # 두 얼굴 공존이 정상 상태(이사 공지 기간엔 양쪽이 함께 서빙해야 moved_to 전파).
        hosts = set(cfg.get("direct_hosts") or [])
        if info["dns_name"]:
            hosts.add(info["dns_name"])
        cfg["direct_hosts"] = sorted(hosts)
        if base:
            cfg["public_base"] = base
        public_face.save_config(cfg)
        wired = {"direct_hosts": cfg["direct_hosts"], "public_base": cfg.get("public_base", "")}
        from api_launcher_web import reload_external_hostnames
        reload_external_hostnames()
    except Exception as e:
        wired = {"error": f"public_face 배선 실패: {e}"}
    return {"success": True, "message": f"Funnel 시작됨: {base or '(주소 확인 실패)'}",
            "public_base": base, "dns_name": info["dns_name"], "wired": wired,
            "cli_output": (r["out"] or r["err"]).strip()[:300]}


def stop_funnel() -> dict:
    """Funnel 끄기 — serve/funnel 선언 전체 제거(reset)."""
    r = _ts_run(["funnel", "reset"], timeout=20)
    if r["rc"] != 0:
        # 구버전 CLI 폴백
        r = _ts_run(["serve", "reset"], timeout=20)
    if r["rc"] != 0:
        return {"success": False, "error": (r["err"] or r["out"]).strip()[:300]}
    try:
        import public_face
        cfg = public_face.load_config()
        # ts.net 얼굴만 내린다 — cloudflare 직접서빙 호스트는 funnel 과 무관하게 유지.
        cfg["direct_hosts"] = [h for h in (cfg.get("direct_hosts") or [])
                               if not h.endswith(".ts.net")]
        public_face.save_config(cfg)
        from api_launcher_web import reload_external_hostnames
        reload_external_hostnames()
    except Exception:
        pass
    return {"success": True, "message": "Funnel이 종료되었습니다."}


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
    provider: Optional[str] = None
    enabled: Optional[bool] = None
    auto_start: Optional[bool] = None
    tunnel_name: Optional[str] = None
    hostname: Optional[str] = None
    finder_hostname: Optional[str] = None
    launcher_hostname: Optional[str] = None
    config_path: Optional[str] = None
    funnel_port: Optional[int] = None


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

    provider = config.get("provider", "cloudflare")
    return {
        "success": True,
        **config,
        "cloudflared_installed": is_cloudflared_installed(),
        "tailscale_installed": is_tailscale_installed(),
        "running": is_funnel_running() if provider == "tailscale" else is_tunnel_running(),
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
    """터널 시작 — provider 분기 (동기 함수 - subprocess/sleep 사용으로 인해 def 사용)"""
    config = load_config()

    if config.get("provider") == "tailscale":
        result = start_funnel(int(config.get("funnel_port") or 8765))
    else:
        if not config.get("tunnel_name") and not config.get("tunnel_token"):
            raise HTTPException(status_code=400, detail="터널 이름이 설정되지 않았습니다.")
        result = start_tunnel(
            tunnel_name=config.get("tunnel_name", ""),
            config_path=config.get("config_path"),
            tunnel_token=config.get("tunnel_token") or None,
            protocol=config.get("protocol") or "",
        )

    if result["success"]:
        config["enabled"] = True
        save_config(config)

    return result


@router.post("/stop")
def api_stop_tunnel():
    """터널 종료 — provider 분기 (동기 함수 - subprocess 사용으로 인해 def 사용)"""
    config = load_config()
    if config.get("provider") == "tailscale":
        result = stop_funnel()
    else:
        result = stop_tunnel()

    if result["success"]:
        config["enabled"] = False
        save_config(config)

    return result


@router.get("/status")
async def get_tunnel_status():
    """터널 상태 조회 — provider 분기"""
    config = load_config()
    provider = config.get("provider", "cloudflare")

    if provider == "tailscale":
        info = tailscale_info()
        return {
            "success": True,
            "provider": provider,
            "running": is_funnel_running() if info["logged_in"] else False,
            "hostname": info["dns_name"],
            "tailscale_installed": info["installed"],
            "logged_in": info["logged_in"],
            "error": info["error"],
        }
    return {
        "success": True,
        "provider": provider,
        "running": is_tunnel_running(),
        "tunnel_name": config.get("tunnel_name", ""),
        "hostname": config.get("hostname", ""),
        "cloudflared_installed": is_cloudflared_installed()
    }


@router.post("/provider")
def set_tunnel_provider(update: TunnelConfig):
    """프로바이더 전환 — AI 모델 갈아끼우듯. 실행 중인 반대편은 끄지 않는다(이사 공지
    기간엔 양쪽이 함께 살아 있어야 moved_to 가 이웃에게 전파된다 — public_face 참조)."""
    provider = (update.provider or "").strip().lower()
    if provider not in ("cloudflare", "tailscale"):
        raise HTTPException(status_code=400, detail="provider 는 cloudflare|tailscale")
    config = load_config()
    config["provider"] = provider
    save_config(config)

    result = {"success": True, "provider": provider}
    if provider == "tailscale":
        result["tailscale"] = tailscale_info()
    else:
        result["cloudflared_installed"] = is_cloudflared_installed()
        # cloudflare 로 복귀 — provider 라벨만 바꾼다. direct_hosts(얼굴들)는 건드리지
        # 않는다: 얼굴의 생사는 발급(합류)·중지(stop_funnel 이 ts.net 만 제거)가 관리하고,
        # 전환 기간엔 양쪽 얼굴이 함께 살아 있어야 moved_to 가 이웃에게 전파된다.
        try:
            import public_face
            cfg = public_face.load_config()
            cfg["provider"] = "cloudflare"
            public_face.save_config(cfg)
            from api_launcher_web import reload_external_hostnames
            reload_external_hostnames()
        except Exception:
            pass
    return result


# 앱 시작 시 자동 시작 체크
def auto_start_if_enabled():
    """설정에 따라 자동 시작 — provider 분기"""
    config = load_config()
    if not config.get("auto_start"):
        return
    if config.get("provider") == "tailscale":
        # funnel 은 tailscaled 에 영속 선언이라 보통 이미 살아 있다 — 죽었을 때만 재선언
        if not is_funnel_running():
            result = start_funnel(int(config.get("funnel_port") or 8765))
            print(f"[Tunnel] funnel 자동 시작: {result.get('message') or result.get('error')}")
        return
    if config.get("tunnel_name") or config.get("tunnel_token"):
        result = start_tunnel(
            tunnel_name=config.get("tunnel_name", ""),
            config_path=config.get("config_path"),
            tunnel_token=config.get("tunnel_token") or None,
            protocol=config.get("protocol") or "",
        )
        if result["success"]:
            print(f"[Tunnel] 자동 시작됨: {config.get('tunnel_name') or '(토큰 모드)'}")
        else:
            print(f"[Tunnel] 자동 시작 실패: {result.get('error', 'unknown')}")
