"""
face_provision.py — 창고 신원(공개 얼굴) 자동 발급.

배경(2026-07-20): 새 몸(새 PC)에서 git pull 만으로는 공유창고가 생기지 않는다 —
창고의 정체(공개 주소)를 이루는 재료(tunnel_config.json·public_face.json·터널
자격증명·DNS)가 전부 git 밖 머신-전속 상태이기 때문. 이 모듈이 그 "발급기":
새 몸 = 새 신원 = 새 주소를 버튼 하나로 만든다. (첫 실행 마법사의 '공개 얼굴' 단계)

두 갈래 — 「공개 HTTPS 주소 → localhost:8765」 계약의 두 구현(api_tunnel 참조):
  ① tailscale : Funnel — 머신마다 고유 `https://<기기>.<테일넷>.ts.net` 주소가
     자동으로 생긴다(도메인·DNS·Worker 전부 불필요). 전제 = Tailscale 앱 로그인뿐.
     api_tunnel.start_funnel 이 이미 public_face 배선까지 하므로 여기선 그 위에
     tunnel_config(provider·auto_start)와 apply_public_base(표면 4곳 전파)를 얹는다.
  ② cloudflare : CF API 토큰으로 원격관리 터널을 통째로 발급 —
     터널 생성(cfd_tunnel, config_src=cloudflare = cert.pem·대화형 login 불필요)
     → 실행 토큰 → ingress 원격 설정(hostname→localhost:8765) → DNS CNAME
     (<sub>.<도메인> → <터널id>.cfargotunnel.com) → `cloudflared tunnel run --token`
     → public_face 직접 서빙(direct_hosts)에 합류
     → ★CDN(Worker+R2)까지 발급(cdn_provision) — CF 경로의 존재 이유가 캐시이므로
     (2026-07-21 결정: R2 없는 CF 는 "도메인 비용만 내는 tailscale"이 된다). 성공 시
     public_base = workers.dev 주소(엣지 캐시 + 원본 은닉). 실패해도 발급은 성공 —
     직접 서빙 폴백으로 공개면이 서고, 스텝 로그의 힌트로 /cdn 재시도가 가능하다.
     (맥의 기존 얼굴은 수공예 Worker(`public-files`) 경유 그대로 — 이름이 달라 충돌 없음.)

안전: 전부 소유자 전용(/tunnel/* = is_public_remote_path 미등록 → 터널서 401).
cloudflare 발급은 dry_run=true 로 변이 없이 계획만 미리 볼 수 있다.
"""

import json
import os
import platform
import re
import secrets as _secrets
import time
from pathlib import Path
from typing import Optional

from common.platform_utils import IS_WINDOWS  # OS 이음매 — 날 os.name 분기 금지(OS-가드)

import requests
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import api_tunnel
import public_face

router = APIRouter(prefix="/tunnel/provision", tags=["tunnel-provision"])

_ROOT = Path(__file__).resolve().parent.parent
_CF_API = "https://api.cloudflare.com/client/v4"


# ── 자격증명 — os.environ(부팅 시 dotenv) + .env 직접 읽기(재시작 없이 갓 저장한 키) ──

def _env_value(name: str) -> str:
    v = (os.environ.get(name) or "").strip()
    if v:
        return v
    try:
        for line in (_ROOT / ".env").read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def _cf_creds() -> dict:
    return {"token": _env_value("CLOUDFLARE_API_TOKEN"),
            "account_id": _env_value("CLOUDFLARE_ACCOUNT_ID")}


def _cf_call(method: str, path: str, token: str, body: Optional[dict] = None,
             params: Optional[dict] = None) -> dict:
    """CF API 호출 — {ok, result, errors}. 예외도 errors 로 흡수(스텝 로그에 그대로 실림)."""
    try:
        r = requests.request(
            method, f"{_CF_API}{path}",
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
            json=body, params=params, timeout=30)
        data = r.json()
        return {"ok": bool(data.get("success")), "result": data.get("result"),
                "errors": data.get("errors") or ([] if data.get("success") else
                                                 [{"message": f"HTTP {r.status_code}"}])}
    except Exception as e:
        return {"ok": False, "result": None, "errors": [{"message": str(e)}]}


def _err_text(res: dict) -> str:
    return "; ".join(str(e.get("message", e)) for e in (res.get("errors") or [])) or "알 수 없는 오류"


def _ensure_origin_secret() -> dict:
    """SHOWCASE_ORIGIN_SECRET 보장 — 없으면 랜덤 생성해 .env 에 기록.

    공개 서빙 경로는 터널 익명 게이트를 통과하므로, 이 시크릿이 '공식 정문
    (Worker 또는 직접 서빙 게이트웨이)만 노크할 수 있다'는 악수다. 비어 있으면
    _check_secret 이 무조건 403 → 발급 직후 공개면이 'failed to fetch'로 죽는다
    (2026-07-20 윈도우 첫 발급에서 실측). 양쪽 검사기가 매 호출 .env 를 다시
    읽으므로 재시작 없이 즉시 반영된다."""
    existing = _env_value("SHOWCASE_ORIGIN_SECRET")
    if existing:
        return {"created": False}
    value = _secrets.token_urlsafe(32)
    envp = _ROOT / ".env"
    try:
        prev = envp.read_text(encoding="utf-8") if envp.exists() else ""
        sep = "" if (not prev or prev.endswith("\n")) else "\n"
        with open(envp, "a", encoding="utf-8") as f:
            f.write(f"{sep}SHOWCASE_ORIGIN_SECRET={value}\n")
        os.environ["SHOWCASE_ORIGIN_SECRET"] = value
        return {"created": True}
    except Exception as e:
        return {"created": False, "error": str(e)}


def _ingress_config(hostname: str) -> dict:
    """원격관리 터널의 ingress 선언 — 발급·부팅 재선언의 단일 소스.
    httpHostHeader: cloudflared 의 Host 재작성(localhost:8765) 방지 — 없으면
    is_direct_host 미스로 공개면 404 (2026-07-20 윈도우 실측)."""
    return {"config": {"ingress": [
        {"hostname": hostname, "service": "http://localhost:8765",
         "originRequest": {"httpHostHeader": hostname}},
        {"service": "http_status:404"}]}}


def _probe_public_face(base: str, timeout: int = 12) -> dict:
    """공개면 자가검증 — 내 공개 주소를 한 번 찔러 본다.

    구별해야 할 두 404:
    - cloudflared catch-all(빈 본문 404) = 실행 중 프로세스의 활성 ingress 에 내
      hostname 규칙이 없다 = 낡은 설정을 물고 있다 → 재기동으로만 고쳐진다.
    - 백엔드가 낸 404(본문 있음) = 배관은 정상, 경로 문제.
    ★반드시 이벤트 루프 밖(스레드)에서 — 이 요청은 CF 를 돌아 내 서버로 되돌아온다."""
    try:
        r = requests.get(base + "/manifest", timeout=timeout,
                         allow_redirects=False)
        body_len = len(r.content or b"")
        catch_all = (r.status_code == 404 and body_len == 0)
        return {"reached": True, "status": r.status_code, "bytes": body_len,
                "catch_all": catch_all}
    except Exception as e:
        return {"reached": False, "error": str(e)}


def verify_public_face(delay: float = 8.0) -> dict:
    """부팅 자가검증·자가치유 — 공개면이 catch-all 404 면 cloudflared 를 재기동한다.

    왜 재PUT 이 아니라 재기동인가(2026-07-20 윈도우 실측): 원격관리 터널의 ingress 는
    *접속 시점에* 받아간다. 같은 내용을 다시 PUT 하면 CF 가 버전을 올리지 않아
    푸시 자체가 없고, 실행 중 프로세스는 낡은 설정을 계속 물고 있다. 그래서
    '설정을 다시 쓰기'가 아니라 '연결을 다시 맺기'가 유일한 수렴 수단이다.
    (발급 때 공개면이 살아난 것도 재PUT 이 아니라 *실제 변경*이 푸시된 덕이었다.)

    발급된 몸에서만 — 맥(로컬관리 config.yml)·미발급은 조용히 스킵. 오프라인 무해."""
    tcfg = api_tunnel.load_config()
    host = tcfg.get("hostname", "")
    if not (host and tcfg.get("tunnel_token")):
        return {"skipped": "발급된 원격관리 터널 없음"}
    if host not in set(public_face.load_config().get("direct_hosts") or []):
        return {"skipped": "이 얼굴은 닫혀 있음"}   # 사용자가 닫아둔 주소는 깨우지 않는다
    base = f"https://{host}"
    time.sleep(delay)                                # cloudflared 접속 완료 대기
    p = _probe_public_face(base)
    if not p.get("reached"):
        print(f"[Tunnel] 공개면 검증 건너뜀(도달 실패: {p.get('error')})")
        return {"ok": False, "probe": p}
    if not p.get("catch_all"):
        print(f"[Tunnel] 공개면 정상 ({base} → {p['status']})")
        return {"ok": True, "probe": p}

    # catch-all = 낡은 ingress. 재기동으로 설정을 다시 받아오게 한다.
    print(f"[Tunnel] 공개면 catch-all 404 — cloudflared 재기동으로 ingress 갱신 시도")
    r = api_tunnel.start_tunnel(tcfg.get("tunnel_name", ""),
                                tunnel_token=tcfg.get("tunnel_token"), force=True)
    if not r.get("success"):
        print(f"[Tunnel] 재기동 실패: {r.get('error')}")
        return {"ok": False, "restarted": False, "error": r.get("error"), "probe": p}
    time.sleep(delay)
    p2 = _probe_public_face(base)
    if p2.get("reached") and not p2.get("catch_all"):
        print(f"[Tunnel] 재기동 후 공개면 정상 ({base} → {p2['status']})")
        return {"ok": True, "restarted": True, "probe": p2}

    # 여전히 catch-all — QUIC(UDP 7844) 차단 의심(연결 수가 모자라면 설정 수신도 불안정).
    # http2 폴백으로 한 번 더. (윈도우 방화벽·공유기에서 흔한 실패 모드)
    print("[Tunnel] 여전히 catch-all — http2 프로토콜 폴백으로 재기동")
    r = api_tunnel.start_tunnel(tcfg.get("tunnel_name", ""),
                                tunnel_token=tcfg.get("tunnel_token"),
                                force=True, protocol="http2")
    if not r.get("success"):
        return {"ok": False, "restarted": True, "error": r.get("error"), "probe": p2}
    time.sleep(delay)
    p3 = _probe_public_face(base)
    ok = bool(p3.get("reached") and not p3.get("catch_all"))
    print(f"[Tunnel] http2 폴백 결과: {'정상' if ok else '여전히 실패'} ({base})")
    if ok:
        tcfg["protocol"] = "http2"      # 다음 부팅부터 이 프로토콜로 기동
        api_tunnel.save_config(tcfg)
    return {"ok": ok, "restarted": True, "protocol": "http2", "probe": p3}


@router.post("/verify")
def api_verify_public_face():
    """공개면 즉시 자가검증(수동 트리거) — 설정 UI 의 '지금 점검' 용."""
    return verify_public_face(delay=0.0)


def _machine_slug() -> str:
    """이 머신의 기본 이름 — 서브도메인·터널명 제안용 (소문자 영숫자-하이픈)."""
    raw = (platform.node() or "indiebiz").split(".")[0].lower()
    slug = re.sub(r"[^a-z0-9-]+", "-", raw).strip("-")
    return slug or "indiebiz"


# ── 상태 — 두 갈래의 준비도 + 현재 신원 ─────────────────────────────────────────

def _effective_public_base(face: dict) -> str:
    """실효 창고 주소 — public_face 가 비면 showcase 상태로 폴백.
    (맥처럼 Worker 가 얼굴인 몸은 주소가 showcase_state.json 에만 있다.)"""
    base = (face.get("public_base") or "").rstrip("/")
    if base:
        return base
    try:
        st = json.loads((_ROOT / "data" / "showcase_state.json").read_text(encoding="utf-8"))
        return ((st.get("settings") or {}).get("public_base") or "").rstrip("/")
    except Exception:
        return ""


@router.get("/status")
async def provision_status():
    """양 갈래 준비 상태 + 현재 창고 신원(public_base). 설정 UI 의 첫 화면."""
    face = public_face.load_config()
    tcfg = api_tunnel.load_config()
    ts = api_tunnel.tailscale_info()
    creds = _cf_creds()
    return {
        "success": True,
        "identity": {
            "public_base": _effective_public_base(face),
            "provider": face.get("provider", ""),
            "direct_hosts": face.get("direct_hosts", []),
            "moved_to": face.get("moved_to", ""),
            "origin_secret_present": bool(_env_value("SHOWCASE_ORIGIN_SECRET")),
        },
        "tunnel": {
            "provider": tcfg.get("provider", ""),
            "tunnel_name": tcfg.get("tunnel_name", ""),
            "hostname": tcfg.get("hostname", ""),
            "running": (api_tunnel.is_funnel_running()
                        if tcfg.get("provider") == "tailscale"
                        else api_tunnel.is_tunnel_running()),
        },
        "tailscale": {
            "installed": ts["installed"], "logged_in": ts["logged_in"],
            "dns_name": ts["dns_name"], "error": ts["error"],
            "install_hint": ("winget install tailscale.tailscale" if IS_WINDOWS
                             else "https://tailscale.com/download (앱 설치 후 로그인)"),
        },
        "cloudflare": {
            "cloudflared_installed": api_tunnel.is_cloudflared_installed(),
            "api_token_present": bool(creds["token"]),
            "account_id_present": bool(creds["account_id"]),
            "install_hint": ("winget install Cloudflare.cloudflared" if IS_WINDOWS
                             else "brew install cloudflared"),
            # 직접서빙 발급 여부 — UI 얼굴 스위치의 재료 (맥의 Worker 얼굴은 여기 안 잡힘)
            "hostname": tcfg.get("hostname", ""),
            "provisioned": bool(tcfg.get("tunnel_token") and tcfg.get("hostname")),
            # 발급기가 배포한 CDN(Worker+R2) — 있으면 public_base 가 이 주소다
            "cdn_worker": tcfg.get("cdn_worker", ""),
            "cdn_url": tcfg.get("cdn_url", ""),
        },
        "machine_slug": _machine_slug(),
    }


@router.get("/zones")
async def provision_zones():
    """CF 계정의 도메인(zone) 목록 — 발급 UI 의 도메인 셀렉터용."""
    creds = _cf_creds()
    if not creds["token"]:
        return JSONResponse({"success": False, "error": "CLOUDFLARE_API_TOKEN 이 없습니다 "
                             "(설정 → API 키 탭에서 등록)"}, status_code=400)
    res = _cf_call("GET", "/zones", creds["token"], params={"per_page": 50, "status": "active"})
    if not res["ok"]:
        return JSONResponse({"success": False, "error": f"zone 조회 실패: {_err_text(res)}"},
                            status_code=502)
    zones = [{"id": z["id"], "name": z["name"]} for z in (res["result"] or [])]
    return {"success": True, "zones": zones}


# ── ① tailscale 발급 — funnel 켜기 + 신원 전파 ─────────────────────────────────

class TailscaleReq(BaseModel):
    port: Optional[int] = None


@router.post("/tailscale")
def provision_tailscale(req: TailscaleReq = TailscaleReq()):
    """원클릭: funnel 켜기(→ public_face 배선 포함) + tunnel_config 갱신 + 표면 4곳 전파."""
    port = int(req.port or api_tunnel.load_config().get("funnel_port") or 8765)
    result = api_tunnel.start_funnel(port)
    if not result.get("success"):
        return JSONResponse({"success": False, "error": result.get("error", "funnel 시작 실패"),
                             "tailscale": {k: result.get(k) for k in
                                           ("installed", "logged_in", "dns_name")}},
                            status_code=400)
    base = result.get("public_base", "")
    tcfg = api_tunnel.load_config()
    tcfg.update({"provider": "tailscale", "enabled": True, "auto_start": True,
                 "funnel_port": port})
    api_tunnel.save_config(tcfg)
    secret = _ensure_origin_secret()   # 직접 서빙 악수 — 없으면 공개면이 403으로 죽는다
    applied = public_face.apply_public_base(base) if base else {}
    return {"success": True, "public_base": base, "dns_name": result.get("dns_name", ""),
            "applied": applied, "origin_secret": secret,
            "message": f"창고 주소가 발급되었습니다: {base or '(주소 확인 실패)'}"}


# ── 공식 주소 스위치 — 발급(얼굴 만들기)과 분리된 명시적 전환 ─────────────────────

class UseReq(BaseModel):
    provider: str = ""    # "cloudflare" | "tailscale"


@router.post("/use")
def provision_use(req: UseReq):
    """이미 발급된 두 얼굴 사이에서 공식 주소(public_base)를 옮긴다 — UI 의 스위치.

    발급="주소 만들기", 스위치="어느 주소를 공식으로 쓸까"의 분리(2026-07-20 사용자
    피드백: 재발급=전환은 아는 사람만 아는 의미론). 반대쪽 얼굴은 계속 서빙
    (direct_hosts 불변 — moved_to 전파 기간 양쪽 공존). 그쪽 터널이 죽어 있으면 켠다."""
    provider = (req.provider or "").strip().lower()
    if provider not in ("cloudflare", "tailscale"):
        return JSONResponse({"success": False, "error": "provider 는 cloudflare|tailscale"},
                            status_code=400)
    tcfg = api_tunnel.load_config()

    if provider == "tailscale":
        info = api_tunnel.tailscale_info()
        if not info["logged_in"] or not info["dns_name"]:
            return JSONResponse({"success": False, "error":
                                 "Tailscale 주소가 아직 없습니다 — 먼저 발급하세요. "
                                 + (info["error"] or "")}, status_code=400)
        # funnel 은 선언형·멱등 — 죽어 있어도 이 호출이 되살리고 public_face 합류까지 한다
        r = api_tunnel.start_funnel(int(tcfg.get("funnel_port") or 8765))
        if not r.get("success"):
            return JSONResponse({"success": False, "error": r.get("error", "funnel 시작 실패")},
                                status_code=400)
        host = info["dns_name"]
    else:
        host = tcfg.get("hostname", "")
        if not (host and tcfg.get("tunnel_token")):
            return JSONResponse({"success": False, "error":
                                 "Cloudflare 주소가 아직 없습니다 — 먼저 발급하세요."},
                                status_code=400)
        if not api_tunnel.is_tunnel_running():
            r = api_tunnel.start_tunnel(tcfg.get("tunnel_name", ""),
                                        tunnel_token=tcfg.get("tunnel_token"))
            if not r.get("success"):
                return JSONResponse({"success": False,
                                     "error": r.get("error", "터널 시작 실패")}, status_code=502)

    base = f"https://{host}"
    fcfg = public_face.load_config()
    hosts = set(fcfg.get("direct_hosts") or [])
    hosts.add(host)
    fcfg.update({"provider": provider, "direct_hosts": sorted(hosts), "public_base": base})
    public_face.save_config(fcfg)
    try:
        from api_launcher_web import reload_external_hostnames
        reload_external_hostnames()
    except Exception:
        pass
    tcfg.update({"provider": provider, "enabled": True})
    api_tunnel.save_config(tcfg)
    applied = public_face.apply_public_base(base)
    return {"success": True, "provider": provider, "public_base": base, "applied": applied,
            "message": f"공식 주소를 옮겼습니다: {base}"}


@router.post("/close")
def provision_close(req: UseReq):
    """얼굴 닫기 — 그 주소의 서빙을 내린다(가역: /open 또는 /use 로 재개).

    창고를 2개 열든 1개만 열든 다 닫든 사용자 자유(2026-07-20 피드백 — 공식 주소
    가드 없음). 닫기=direct_hosts 제거+터널 내림 — 발급물(터널·DNS·주소)은
    남으므로 삭제가 아니라 휴면이다. 공식 주소를 닫으면 그 주소가 잠시 오프라인일
    뿐 정체(public_base)는 유지된다."""
    provider = (req.provider or "").strip().lower()
    if provider not in ("cloudflare", "tailscale"):
        return JSONResponse({"success": False, "error": "provider 는 cloudflare|tailscale"},
                            status_code=400)

    if provider == "tailscale":
        r = api_tunnel.stop_funnel()   # funnel reset + direct_hosts 에서 .ts.net 제거
        if not r.get("success"):
            return JSONResponse({"success": False, "error": r.get("error", "funnel 종료 실패")},
                                status_code=502)
        return {"success": True, "message": "Tailscale 주소를 닫았습니다 — 창고·원격 런처·"
                                           "원격 Finder 가 함께 닫힙니다 (열기로 재개)"}

    tcfg = api_tunnel.load_config()
    host = tcfg.get("hostname", "")
    if not (host and tcfg.get("tunnel_token")):
        return JSONResponse({"success": False, "error": "발급된 Cloudflare 주소가 없습니다"},
                            status_code=400)
    api_tunnel.stop_tunnel()
    cfg = public_face.load_config()
    cfg["direct_hosts"] = [h for h in (cfg.get("direct_hosts") or []) if h != host]
    public_face.save_config(cfg)
    try:
        from api_launcher_web import reload_external_hostnames
        reload_external_hostnames()
    except Exception:
        pass
    return {"success": True, "message": "Cloudflare 주소를 닫았습니다 — 창고·원격 런처·"
                                       "원격 Finder 가 함께 닫힙니다 (열기로 재개)"}


@router.post("/open")
def provision_open(req: UseReq):
    """얼굴 열기 — 공식 주소는 건드리지 않고 그 주소의 서빙만 재개 (/close 의 반대).
    공식 주소까지 옮기려면 /use."""
    provider = (req.provider or "").strip().lower()
    if provider not in ("cloudflare", "tailscale"):
        return JSONResponse({"success": False, "error": "provider 는 cloudflare|tailscale"},
                            status_code=400)

    if provider == "tailscale":
        # start_funnel 은 정체(public_base·provider)까지 ts 로 배선하므로 — 열기 전
        # 값을 보존했다가 되돌린다(열기=서빙 재개일 뿐 정체 이동은 /use 의 일).
        before = public_face.load_config()
        keep_base = before.get("public_base", "")
        keep_provider = before.get("provider", "")
        tcfg = api_tunnel.load_config()
        r = api_tunnel.start_funnel(int(tcfg.get("funnel_port") or 8765))
        if not r.get("success"):
            return JSONResponse({"success": False, "error": r.get("error", "funnel 시작 실패")},
                                status_code=400)
        cfg = public_face.load_config()
        if keep_base:
            cfg["public_base"] = keep_base
        if keep_provider:
            cfg["provider"] = keep_provider
        public_face.save_config(cfg)
        try:
            from api_launcher_web import reload_external_hostnames
            reload_external_hostnames()
        except Exception:
            pass
        return {"success": True, "message": "Tailscale 창고 주소를 열었습니다"}

    tcfg = api_tunnel.load_config()
    host = tcfg.get("hostname", "")
    if not (host and tcfg.get("tunnel_token")):
        return JSONResponse({"success": False, "error": "발급된 Cloudflare 주소가 없습니다"},
                            status_code=400)
    if not api_tunnel.is_tunnel_running():
        r = api_tunnel.start_tunnel(tcfg.get("tunnel_name", ""),
                                    tunnel_token=tcfg.get("tunnel_token"))
        if not r.get("success"):
            return JSONResponse({"success": False, "error": r.get("error", "터널 시작 실패")},
                                status_code=502)
    cfg = public_face.load_config()
    hosts = set(cfg.get("direct_hosts") or [])
    hosts.add(host)
    cfg["direct_hosts"] = sorted(hosts)
    public_face.save_config(cfg)
    try:
        from api_launcher_web import reload_external_hostnames
        reload_external_hostnames()
    except Exception:
        pass
    return {"success": True, "message": "Cloudflare 창고 주소를 열었습니다"}


# ── ② cloudflare 발급 — CF API 원격관리 터널 + DNS + 직접 서빙 ────────────────────

class CloudflareReq(BaseModel):
    domain: str = ""          # zone 이름 (예: kukjinkang.uk)
    subdomain: str = ""       # 머신별 서브도메인 (예: win) → win.kukjinkang.uk
    dry_run: bool = False     # true = 변이 없이 계획만
    skip_cdn: bool = False    # true = Worker+R2 없이 직접 서빙만 (옛 동작)


@router.post("/cloudflare")
def provision_cloudflare(req: CloudflareReq):
    """CF API 로 새 몸의 터널·DNS·공개 얼굴을 통째로 발급. 단계별 steps 로그 반환.
    실패해도 이미 성공한 단계는 스텝 로그로 남아 재시도가 이어달리기가 된다
    (터널·DNS 생성은 이름 기준 멱등 — 있으면 재사용)."""
    steps = []

    def fail(msg, status=400):
        return JSONResponse({"success": False, "error": msg, "steps": steps}, status_code=status)

    creds = _cf_creds()
    if not creds["token"] or not creds["account_id"]:
        missing = [n for n, v in (("CLOUDFLARE_API_TOKEN", creds["token"]),
                                  ("CLOUDFLARE_ACCOUNT_ID", creds["account_id"])) if not v]
        return fail(f"{'·'.join(missing)} 이(가) 없습니다 (설정 → API 키 탭에서 등록)")

    domain = (req.domain or "").strip().lower().strip(".")
    sub = re.sub(r"[^a-z0-9-]+", "-", (req.subdomain or "").strip().lower()).strip("-")
    if not domain or not sub:
        return fail("domain(도메인)과 subdomain(서브도메인)이 필요합니다")
    hostname = f"{sub}.{domain}"
    tunnel_name = f"indiebiz-{sub}"
    token, acc = creds["token"], creds["account_id"]

    # 0) zone 확인 — 토큰 권한(Zone Read·DNS Edit) 검증을 겸한다
    res = _cf_call("GET", "/zones", token, params={"name": domain})
    if not res["ok"] or not res["result"]:
        return fail(f"도메인 '{domain}' 의 zone 을 찾지 못했습니다: {_err_text(res) if not res['ok'] else 'CF 계정에 해당 도메인 없음'}")
    zone_id = res["result"][0]["id"]
    steps.append({"step": "zone", "ok": True, "detail": f"{domain} (zone {zone_id[:8]}…)"})

    if req.dry_run:
        steps.append({"step": "plan", "ok": True, "detail":
                      f"터널 '{tunnel_name}' 생성/재사용 → ingress {hostname}→localhost:8765 "
                      f"→ CNAME {hostname} → cloudflared run --token → 직접 서빙 배선"})
        return {"success": True, "dry_run": True, "hostname": hostname,
                "tunnel_name": tunnel_name, "steps": steps}

    if not api_tunnel.is_cloudflared_installed():
        hint = "winget install Cloudflare.cloudflared" if IS_WINDOWS else "brew install cloudflared"
        return fail(f"cloudflared 가 설치되지 않았습니다. 먼저 설치하세요: {hint}")

    # 1) 터널 — 같은 이름이 있으면 재사용(멱등), 없으면 원격관리형으로 생성
    res = _cf_call("GET", f"/accounts/{acc}/cfd_tunnel", token,
                   params={"name": tunnel_name, "is_deleted": "false"})
    if not res["ok"]:
        return fail(f"터널 조회 실패: {_err_text(res)}", 502)
    existing = [t for t in (res["result"] or []) if t.get("name") == tunnel_name]
    if existing:
        tunnel_id = existing[0]["id"]
        steps.append({"step": "tunnel", "ok": True, "detail": f"기존 터널 재사용 ({tunnel_id[:8]}…)"})
    else:
        res = _cf_call("POST", f"/accounts/{acc}/cfd_tunnel", token,
                       body={"name": tunnel_name, "config_src": "cloudflare"})
        if not res["ok"]:
            return fail(f"터널 생성 실패: {_err_text(res)}", 502)
        tunnel_id = res["result"]["id"]
        steps.append({"step": "tunnel", "ok": True, "detail": f"터널 생성 ({tunnel_id[:8]}…)"})

    # 2) 실행 토큰
    res = _cf_call("GET", f"/accounts/{acc}/cfd_tunnel/{tunnel_id}/token", token)
    if not res["ok"] or not res["result"]:
        return fail(f"터널 토큰 발급 실패: {_err_text(res)}", 502)
    tunnel_token = res["result"] if isinstance(res["result"], str) else str(res["result"])
    steps.append({"step": "token", "ok": True, "detail": "실행 토큰 발급"})

    # 3) ingress 원격 설정 — hostname → 백엔드 (원격관리형이라 config.yml 불필요).
    #    선언 본문은 _ingress_config 단일 소스(부팅 재선언 reassert_ingress 와 공유).
    res = _cf_call("PUT", f"/accounts/{acc}/cfd_tunnel/{tunnel_id}/configurations", token,
                   body=_ingress_config(hostname))
    if not res["ok"]:
        return fail(f"ingress 설정 실패: {_err_text(res)}", 502)
    steps.append({"step": "ingress", "ok": True, "detail": f"{hostname} → localhost:8765"})

    # 4) DNS CNAME — 있으면 내용 갱신, 없으면 생성 (멱등)
    target = f"{tunnel_id}.cfargotunnel.com"
    res = _cf_call("GET", f"/zones/{zone_id}/dns_records", token, params={"name": hostname})
    if not res["ok"]:
        return fail(f"DNS 조회 실패: {_err_text(res)}", 502)
    rec = (res["result"] or [None])[0]
    if rec:
        res = _cf_call("PUT", f"/zones/{zone_id}/dns_records/{rec['id']}", token,
                       body={"type": "CNAME", "name": hostname, "content": target,
                             "proxied": True})
    else:
        res = _cf_call("POST", f"/zones/{zone_id}/dns_records", token,
                       body={"type": "CNAME", "name": hostname, "content": target,
                             "proxied": True})
    if not res["ok"]:
        return fail(f"DNS CNAME 설정 실패: {_err_text(res)}", 502)
    steps.append({"step": "dns", "ok": True, "detail": f"CNAME {hostname} → {target}"})

    # 5) tunnel_config 저장 + cloudflared 실행 (토큰 모드 — cert.pem·config.yml 불필요)
    tcfg = api_tunnel.load_config()
    tcfg.update({"provider": "cloudflare", "enabled": True, "auto_start": True,
                 "tunnel_name": tunnel_name, "tunnel_id": tunnel_id,
                 "tunnel_token": tunnel_token, "hostname": hostname})
    api_tunnel.save_config(tcfg)
    run = api_tunnel.start_tunnel(tunnel_name, tunnel_token=tunnel_token)
    steps.append({"step": "run", "ok": bool(run.get("success")),
                  "detail": run.get("message") or run.get("error", "")})
    if not run.get("success"):
        return fail(f"cloudflared 실행 실패: {run.get('error')} — 설정은 저장되어 "
                    "재시작 시 자동 시작을 다시 시도합니다", 502)

    # 6) 시크릿 — 공식 정문(Worker 또는 직접 서빙 게이트웨이)의 악수. CDN 보다 먼저
    #    (Worker 바인딩에 이 값이 실린다).
    sec = _ensure_origin_secret()
    steps.append({"step": "secret", "ok": "error" not in sec,
                  "detail": ("시크릿 생성(.env)" if sec.get("created")
                             else sec.get("error") or "기존 시크릿 사용")})

    # 7) CDN(Worker+R2) — CF 경로의 존재 이유. 실패해도 발급 실패가 아니다(직접 서빙 폴백).
    base = f"https://{hostname}"
    cdn_ok = False
    if not req.skip_cdn:
        import cdn_provision
        cdn = cdn_provision.provision_cdn(token, acc, hostname,
                                          _env_value("SHOWCASE_ORIGIN_SECRET"),
                                          _machine_slug())
        steps.extend(cdn["steps"])
        if cdn.get("ok"):
            cdn_ok = True
            base = cdn["url"]
            tcfg.update({"cdn_worker": cdn["worker"], "cdn_url": cdn["url"]})
            api_tunnel.save_config(tcfg)

    # 8) 공개 얼굴 배선 — direct_hosts 에는 CDN 여부와 무관하게 터널 호스트가 들어간다:
    #    직접 서빙일 땐 그 자체가 정문, CDN 일 땐 Worker 의 오리진(ORIGIN_BASE)이자
    #    런처·파인더의 주소(origin_host)다.
    fcfg = public_face.load_config()
    hosts = set(fcfg.get("direct_hosts") or [])
    hosts.add(hostname)
    fcfg.update({"provider": "cloudflare", "direct_hosts": sorted(hosts),
                 "public_base": base})
    public_face.save_config(fcfg)
    try:
        from api_launcher_web import reload_external_hostnames
        reload_external_hostnames()
    except Exception:
        pass
    applied = public_face.apply_public_base(base)
    steps.append({"step": "face", "ok": True, "detail":
                  (f"CDN 얼굴 배선 + 표면 전파: {base} (오리진 {hostname})" if cdn_ok
                   else f"직접 서빙 배선 + 표면 전파: {base}")})

    return {"success": True, "public_base": base, "hostname": hostname,
            "cdn": cdn_ok, "tunnel_name": tunnel_name, "tunnel_id": tunnel_id,
            "steps": steps,
            "message": (f"창고 주소가 발급되었습니다: {base} (R2 캐시 켜짐)" if cdn_ok else
                        f"창고 주소가 발급되었습니다: {base} — R2 캐시는 실패해 직접 서빙으로 "
                        "시작합니다 (스텝 로그 참조, '캐시 켜기'로 재시도 가능)")}


class CdnReq(BaseModel):
    worker: str = ""    # 이름 지정 — 기존 Worker 를 발급기 관리로 흡수(맥 이주). 생략=자동


@router.post("/cdn")
def provision_cdn_endpoint(req: CdnReq = CdnReq()):
    """CDN(Worker+R2)만 (재)발급 — CF 발급 때 실패했거나 worker.js 갱신을 반영할 때.
    멱등: 재실행 = 최신 worker.js·index.html 로 갈아끼우는 갱신 배포.

    오리진 = 발급된 터널 호스트, 없으면 수기 finder_hostname(맥의 수제 터널 몸) —
    맥의 수공예 Worker(`public-files`) 이주(1단계)가 이 폴백으로 가능해진다.
    이름 우선순위: 요청 worker > 저장된 cdn_worker(재배포) > 몸-유일 자동 이름."""
    creds = _cf_creds()
    if not creds["token"] or not creds["account_id"]:
        return JSONResponse({"success": False,
                             "error": "CLOUDFLARE_API_TOKEN·ACCOUNT_ID 가 없습니다"},
                            status_code=400)
    tcfg = api_tunnel.load_config()
    hostname = tcfg.get("hostname", "") if tcfg.get("tunnel_token") else ""
    hostname = hostname or tcfg.get("finder_hostname", "")
    if not hostname:
        return JSONResponse({"success": False, "error":
                             "오리진 호스트가 없습니다 — 먼저 Cloudflare 주소를 발급하세요"},
                            status_code=400)
    _ensure_origin_secret()
    worker_name = (req.worker or "").strip() or tcfg.get("cdn_worker", "")
    import cdn_provision
    cdn = cdn_provision.provision_cdn(creds["token"], creds["account_id"], hostname,
                                      _env_value("SHOWCASE_ORIGIN_SECRET"),
                                      _machine_slug(), worker=worker_name)
    if not cdn.get("ok"):
        return JSONResponse({"success": False, "steps": cdn["steps"],
                             "error": "CDN 발급 실패 — 스텝 로그 참조"}, status_code=502)
    tcfg.update({"cdn_worker": cdn["worker"], "cdn_url": cdn["url"]})
    api_tunnel.save_config(tcfg)
    fcfg = public_face.load_config()
    fcfg["public_base"] = cdn["url"]
    public_face.save_config(fcfg)
    applied = public_face.apply_public_base(cdn["url"])
    return {"success": True, "url": cdn["url"], "worker": cdn["worker"],
            "steps": cdn["steps"], "applied": applied,
            "message": f"R2 캐시가 켜졌습니다: {cdn['url']}"}
