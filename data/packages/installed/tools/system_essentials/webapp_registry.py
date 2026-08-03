"""webapp_registry.py — 내 웹앱 등기부 ([self:webapp]{op: list/status/register/remove}).

원칙 = **파생 우선**: 수동 원장을 하나 더 만들면 반드시 드리프트한다. 몸 공개면
(런처·NAS·포털·게시판·가족신문·공개파일·정기보고)과 web-builder 사이트는 각자의
진실 소스(state 파일)가 이미 있으므로 매 호출 때 거기서 **파생**한다. 수동 등록
(data/webapps.json)은 파생 밖의 예외(야생 Worker·수제 배포)만 담는다.

status = 전 함대 HTTP 생존 실측(병렬, 기본 5초) — "웹앱이 몇 개고 돌아가는지 모른다"의 해소.
World Pulse Self-Check 합류는 보류(2026-08-01 사용자 결정) — 필요해지면 op_status 재사용.

저장 = limb_keys 식 무-flock 원자쓰기(윈도우 안전). 가이드 = data/guides/webapp.md.
"""
import json
import os
import threading
import time
from pathlib import Path

import sys
_ROOT = Path(__file__).resolve().parents[5]  # indiebizOS/
_BACKEND = str(_ROOT / "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
from common.currency import items  # IBL 단일 통화 생성자

_DATA = _ROOT / "data"
_MANUAL_PATH = _DATA / "webapps.json"
_lock = threading.RLock()


def _read_json(p) -> dict:
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _public_base() -> str:
    """공개면 공통 베이스 — portal_state 의 public_base 가 단일 소스."""
    return (_read_json(_DATA / "portal_state.json").get("public_base") or "").rstrip("/")


def _origin_base() -> str:
    """런처·NAS(8765 직결 면)의 베이스 — ★public_base(Worker CDN)와 다른 축.

    Worker 는 /s/·/n/·/h/·/b/·/r/ 만 라우팅하고 /launcher/*·/nas/* 분기가 없어
    미매칭은 공개파일 index 로 떨어진다 — 고정 5면에 public_base 를 붙이면
    존재하지 않는 주소가 된다(2026-08-03 실사용 신고). 진실 소스는
    api_tunnel.origin_host()(오리진 호스트, docstring 에 이 구분이 명시돼 있다)."""
    try:
        import api_tunnel
        host = (api_tunnel.origin_host() or "").strip()
        if host:
            return f"https://{host}"
    except Exception:
        pass
    # 폴백: direct_hosts 중 터널(비 ts.net) 호스트 — origin_host 와 같은 선호 순서
    hosts = [h for h in (_read_json(_DATA / "public_face.json").get("direct_hosts") or []) if h]
    for h in hosts:
        if not h.endswith(".ts.net"):
            return f"https://{h}"
    return f"https://{hosts[0]}" if hosts else ""


def _wrangler_name(toml_path) -> str:
    """wrangler.toml 의 name = "..." 한 줄만 — toml 파서 의존성 없이."""
    try:
        for line in open(toml_path, "r", encoding="utf-8"):
            s = line.strip()
            if s.startswith("name") and "=" in s:
                return s.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def _derived() -> list:
    """진실 소스 7곳에서 웹앱 목록 파생 — 원장 아님, 매 호출 재계산(드리프트 원리적 불가)."""
    base = _public_base()
    out = []

    def add(title, url, kind, source, memo=""):
        out.append({"title": title, "url": url, "kind": kind, "source": source,
                    "memo": memo, "meta": f"{kind} · {source}", "summary": url or memo})

    # 1) 고정 5면 — 몸의 얼굴 (본판 PWA 2 + 구형 기기 라이트 3)
    #    ★베이스는 오리진 호스트(터널 직결)다 — Worker(public_base)는 이 경로들을 라우팅하지 않는다
    origin = _origin_base()
    if origin:
        add("원격런처 (PWA)", f"{origin}/launcher/app", "몸 공개면", "고정")
        add("원격NAS · IBFind (PWA)", f"{origin}/nas/app", "몸 공개면", "고정")
        add("원격런처 · 라이트 (구형 기기)", f"{origin}/launcher/lite", "몸 공개면", "고정",
            "순수 ES5 경량판 — iOS 10.3~5.1.1 구형 Safari 용")
        add("원격NAS · 라이트 (구형 기기)", f"{origin}/nas/lite", "몸 공개면", "고정",
            "경량 Finder — iOS 10.3 급 낡은 WebKit 용")
        add("원격NAS · 라이트2 (초구형 기기)", f"{origin}/nas/lite2", "몸 공개면", "고정",
            "순수 ES5 — iOS 5.1.1 아이패드 1세대 급. TLS 한계 시 LAN http://<맥IP>:8765/nas/lite2")
    # 2) 포털
    for p in _read_json(_DATA / "portal_state.json").get("portals") or []:
        slug = p.get("slug")
        if slug:
            add(f"포털 · {p.get('title') or slug}", f"{base}/h/{slug}/", "몸 공개면", "portal")
    # 3) 게시판
    for b in _read_json(_DATA / "bulletin" / "state.json").get("boards") or []:
        slug = b.get("slug")
        if slug:
            add(f"게시판 · {b.get('title') or slug}", f"{base}/b/{slug}/", "몸 공개면", "bulletin")
    # 4) 가족신문
    fn = _read_json(_DATA / "family_news" / "state.json")
    if fn.get("slug"):
        add(f"가족신문 · {fn.get('title') or ''}".strip(" ·"), f"{base}/n/{fn['slug']}/",
            "몸 공개면", "family_news")
    # 5) 공개파일 바스켓
    for bk in _read_json(_DATA / "showcase_state.json").get("baskets") or []:
        slug = bk.get("slug")
        if slug:
            add(f"공개파일 · {bk.get('title') or slug}", f"{base}/s/{slug}/", "몸 공개면", "showcase")
    # 6) 정기보고 발행 면
    for r in _read_json(_DATA / "report_publish.json").get("reports") or []:
        if r.get("slug") and r.get("enabled", True):
            add(f"보고서 · {r.get('title') or r['slug']}", f"{base}/r/{r['slug']}/",
                "몸 공개면", "report")
    # 7) web-builder 사이트 (외부 Vercel — 홈페이지)
    sj = _read_json(_DATA / "packages" / "installed" / "tools" / "web-builder" / "sites.json")
    sites = sj if isinstance(sj, list) else sj.get("sites", [])
    for s in sites or []:
        url = (s.get("deploy_url") or "").strip()
        add(s.get("name") or s.get("id") or "(이름 없음)", url, "외부(Vercel)", "web-builder",
            (s.get("description") or "")[:80] or ("주소 미등록" if not url else ""))
    # 8) 야생 Worker (outputs/web-projects/*/wrangler.toml) — kospi-board 부류
    wp = _ROOT / "outputs" / "web-projects"
    if wp.is_dir():
        for d in sorted(wp.iterdir()):
            tm = d / "wrangler.toml"
            if tm.exists():
                nm = _wrangler_name(tm) or d.name
                add(f"Worker · {nm}", "", "외부(Worker)", "web-projects",
                    f"{d.name}/ — 배포 주소 미상: register 로 보충")
    return out


# ── 수동 원장 (파생 밖 예외만) ───────────────────────────────────────────────

def _load_manual() -> list:
    with _lock:
        d = _read_json(_MANUAL_PATH)
        return d.get("webapps") or []


def _save_manual(entries: list) -> None:
    with _lock:
        tmp = _MANUAL_PATH.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"webapps": entries}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _MANUAL_PATH)


def _all_entries() -> list:
    """파생 + 수동 합집합. url 이 겹치면 파생이 정본(수동은 보충일 뿐)."""
    derived = _derived()
    seen = {e["url"] for e in derived if e.get("url")}
    for m in _load_manual():
        url = (m.get("url") or "").strip()
        if url and url in seen:
            continue
        e = dict(m)
        e.setdefault("kind", "수동")
        e["source"] = "수동등록"
        e["meta"] = f"{e.get('kind')} · 수동등록"
        e["summary"] = url or e.get("memo", "")
        e.setdefault("title", url or "(이름 없음)")
        e.setdefault("url", "")
        derived.append(e)
    return derived


# ── op 구현 ──────────────────────────────────────────────────────────────────

def op_list(tool_input: dict):
    ents = _all_entries()
    return items(ents, success=True,
                 message=f"웹앱 {len(ents)}개 (파생 {len([e for e in ents if e['source'] != '수동등록'])} + 수동 {len([e for e in ents if e['source'] == '수동등록'])})")


def op_status(tool_input: dict):
    """전 함대 생존 실측 — 병렬 HTTP GET(리다이렉트 추종, 본문은 안 읽음)."""
    import requests
    timeout = float(tool_input.get("timeout") or 5)
    ents = _all_entries()
    results = [None] * len(ents)

    def probe(i, e):
        url = e.get("url")
        if not url:
            results[i] = {**e, "alive": None, "status_line": "주소 미상 — register 로 보충"}
            return
        t0 = time.time()
        try:
            r = requests.get(url, timeout=timeout, stream=True,
                             headers={"User-Agent": "indiebizOS-webapp-status"})
            ms = int((time.time() - t0) * 1000)
            r.close()
            ok = r.status_code < 500
            results[i] = {**e, "alive": ok, "http": r.status_code, "ms": ms,
                          "status_line": f"{'🟢' if ok else '🔴'} HTTP {r.status_code} · {ms}ms"}
        except Exception as ex:
            results[i] = {**e, "alive": False, "http": 0,
                          "status_line": f"🔴 접속 실패 ({type(ex).__name__})"}

    threads = [threading.Thread(target=probe, args=(i, e), daemon=True)
               for i, e in enumerate(ents)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout + 2)
    done = [r for r in results if r]
    dead = [r for r in done if r.get("alive") is False]
    return items(done, success=True,
                 message=f"웹앱 {len(done)}개 중 응답 불능 {len(dead)}개"
                         + (f" — {', '.join(d['title'] for d in dead[:5])}" if dead else ""))


def op_register(tool_input: dict):
    name = (tool_input.get("name") or "").strip()
    url = (tool_input.get("url") or "").strip()
    if not name or not url:
        return items([], success=False, message="name 과 url 이 필요합니다 (몸 공개면·web-builder 사이트는 자동 파생이라 등록 불필요)")
    if any(e.get("url") == url for e in _derived()):
        return items([], success=False, message="이미 자동 파생되는 주소입니다 — 등록 불필요")
    manual = [m for m in _load_manual() if (m.get("url") or "") != url]
    manual.append({"title": name, "url": url, "kind": (tool_input.get("kind") or "수동").strip(),
                   "memo": (tool_input.get("memo") or "").strip(), "created_at": time.time()})
    _save_manual(manual)
    return op_list(tool_input)


def op_remove(tool_input: dict):
    url = (tool_input.get("url") or "").strip()
    if not url:
        return items([], success=False, message="지울 url 이 필요합니다")
    manual = _load_manual()
    kept = [m for m in manual if (m.get("url") or "") != url]
    if len(kept) == len(manual):
        return items([], success=False, message="수동 등록에 없는 주소입니다 (파생 항목은 각자의 진실 소스에서 지워야 합니다 — 포털/게시판/사이트 등)")
    _save_manual(kept)
    return op_list(tool_input)
