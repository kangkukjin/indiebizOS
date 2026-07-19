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
     → public_face 직접 서빙(direct_hosts)에 합류. ★Worker 는 선택적 가속기일 뿐
     (R2 캐시·원본 은닉) — 발급 단계에선 배포하지 않고 직접 서빙으로 공개면이 선다.
     (맥의 기존 얼굴은 Worker 경유 그대로 — 이 갈래는 새 몸의 기본 경로.)

안전: 전부 소유자 전용(/tunnel/* = is_public_remote_path 미등록 → 터널서 401).
cloudflare 발급은 dry_run=true 로 변이 없이 계획만 미리 볼 수 있다.
"""

import json
import os
import platform
import re
import secrets as _secrets
from pathlib import Path
from typing import Optional

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
            "install_hint": ("winget install tailscale.tailscale" if os.name == "nt"
                             else "https://tailscale.com/download (앱 설치 후 로그인)"),
        },
        "cloudflare": {
            "cloudflared_installed": api_tunnel.is_cloudflared_installed(),
            "api_token_present": bool(creds["token"]),
            "account_id_present": bool(creds["account_id"]),
            "install_hint": ("winget install Cloudflare.cloudflared" if os.name == "nt"
                             else "brew install cloudflared"),
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


# ── ② cloudflare 발급 — CF API 원격관리 터널 + DNS + 직접 서빙 ────────────────────

class CloudflareReq(BaseModel):
    domain: str = ""          # zone 이름 (예: kukjinkang.uk)
    subdomain: str = ""       # 머신별 서브도메인 (예: win) → win.kukjinkang.uk
    dry_run: bool = False     # true = 변이 없이 계획만


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
        hint = "winget install Cloudflare.cloudflared" if os.name == "nt" else "brew install cloudflared"
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

    # 3) ingress 원격 설정 — hostname → 백엔드 (원격관리형이라 config.yml 불필요)
    # ★httpHostHeader: cloudflared 가 원본으로 보내는 Host 를 공개호스트로 고정.
    #   없으면 서비스 기준(localhost:8765)으로 재작성돼 is_direct_host 미스 →
    #   게이트웨이 미작동 → 공개면 404 (2026-07-20 윈도우 실측).
    res = _cf_call("PUT", f"/accounts/{acc}/cfd_tunnel/{tunnel_id}/configurations", token,
                   body={"config": {"ingress": [
                       {"hostname": hostname, "service": "http://localhost:8765",
                        "originRequest": {"httpHostHeader": hostname}},
                       {"service": "http_status:404"}]}})
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

    # 6) 공개 얼굴 배선 — Worker 없이 직접 서빙(direct_hosts)으로 공개면 성립
    sec = _ensure_origin_secret()      # 직접 서빙 악수 — 없으면 공개면이 403으로 죽는다
    steps.append({"step": "secret", "ok": "error" not in sec,
                  "detail": ("시크릿 생성(.env)" if sec.get("created")
                             else sec.get("error") or "기존 시크릿 사용")})
    base = f"https://{hostname}"
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
    steps.append({"step": "face", "ok": True, "detail": f"직접 서빙 배선 + 표면 전파: {base}"})

    return {"success": True, "public_base": base, "hostname": hostname,
            "tunnel_name": tunnel_name, "tunnel_id": tunnel_id, "steps": steps,
            "message": f"창고 주소가 발급되었습니다: {base}"}
