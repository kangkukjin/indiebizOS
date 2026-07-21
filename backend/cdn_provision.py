"""
cdn_provision.py — CF 경로의 가속기(Worker + R2)를 발급기로 제품화.

배경(2026-07-21): CF 창고 경로의 존재 이유는 R2 엣지 캐시(파일 트래픽을 엣지가
받아 맥 업링크·상시성을 지켜줌)인데, 발급기는 터널·DNS·직접 서빙까지만 해주고
Worker 는 맥에만 손으로(wrangler deploy + ORIGIN_BASE 수기) 있었다 — 즉 사용자가
CF 를 골라도 도메인 비용만 내고 캐시는 못 받았다. 이 모듈이 그 간극을 메운다:
CF API 만으로(wrangler 불필요) R2 버킷 생성 → worker.js 업로드(바인딩 포함) →
workers.dev 서브도메인 활성 → SPA index.html R2 업로드 → 도달 검증.

wrangler.toml 은 이 경로에서 아예 안 쓴다 — 바인딩(BUCKET·ORIGIN_BASE·
SHOWCASE_SECRET)을 업로드 메타데이터로 직접 심는다. 몸-전속 값이 파일로 남지
않으므로 신원 유출 부류(wrangler.toml 추적 사고)의 뿌리도 함께 사라진다.

이름은 몸마다 유일(`public-files-<슬러그>`) — 같은 CF 계정의 두 몸이 서로의
Worker 를 덮어쓰는 사고(2026-07-21 메모리 body-identity-leak ②) 방지.
맥의 수공예 Worker(`public-files`)와도 이름이 달라 충돌하지 않는다.

실패는 발급 실패가 아니다 — 호출자(face_provision)는 CDN 이 안 되면 직접 서빙
폴백으로 공개면을 세운다. 전형적 실패 = 토큰 권한 부족(Workers Scripts:Edit ·
R2:Edit), R2 미활성 계정. 스텝 로그에 힌트를 실어 사용자가 고칠 수 있게 한다.
"""

import json
import re
from pathlib import Path
from typing import Optional

import requests

_ROOT = Path(__file__).resolve().parent.parent
_CF_API = "https://api.cloudflare.com/client/v4"
_SITE = _ROOT / "data" / "packages" / "installed" / "tools" / "public-files" / "site"

# worker.js 의 compatibility_date 와 짝 (wrangler.toml.example 과 동일 값 유지)
_COMPAT_DATE = "2026-01-01"


def _err_text(data: dict, status: int) -> str:
    errs = data.get("errors") or []
    msg = "; ".join(str(e.get("message", e)) for e in errs)
    return msg or f"HTTP {status}"


def _call(method: str, path: str, token: str, *, body: Optional[dict] = None,
          params: Optional[dict] = None, files=None, data=None,
          headers: Optional[dict] = None, timeout: int = 60) -> dict:
    """CF API 호출 — JSON 본문(body) 또는 멀티파트(files)/raw(data)를 모두 지원.
    face_provision._cf_call 은 JSON 전용이라 Worker 업로드(멀티파트)·R2 오브젝트
    업로드(raw)를 못 실어 별도 헬퍼를 둔다."""
    try:
        hdrs = {"Authorization": f"Bearer {token}"}
        if headers:
            hdrs.update(headers)
        if body is not None:
            hdrs.setdefault("Content-Type", "application/json")
        r = requests.request(method, f"{_CF_API}{path}", headers=hdrs,
                             json=body, params=params, files=files, data=data,
                             timeout=timeout)
        try:
            payload = r.json()
        except Exception:
            payload = {"success": r.ok, "errors": [{"message": r.text[:200]}]}
        return {"ok": bool(payload.get("success")), "result": payload.get("result"),
                "error": "" if payload.get("success") else _err_text(payload, r.status_code),
                "status": r.status_code}
    except Exception as e:
        return {"ok": False, "result": None, "error": str(e), "status": 0}


def worker_name_for(slug: str) -> str:
    """몸-유일 Worker 이름. Workers 스크립트 이름 규칙([a-z0-9-], 63자)에 맞춘다."""
    name = re.sub(r"[^a-z0-9-]+", "-", f"public-files-{slug}".lower()).strip("-")
    return name[:63]


def _ensure_bucket(token: str, acc: str, name: str) -> dict:
    """R2 버킷 보장 (이름 기준 멱등 — 이미 있으면 재사용)."""
    res = _call("POST", f"/accounts/{acc}/r2/buckets", token, body={"name": name})
    if res["ok"]:
        return {"ok": True, "detail": f"버킷 생성 ({name})"}
    # 10004 = already exists → 멱등 재사용
    if "already exists" in res["error"].lower() or "10004" in res["error"]:
        return {"ok": True, "detail": f"기존 버킷 재사용 ({name})"}
    hint = ""
    low = res["error"].lower()
    if "not entitled" in low or "payment" in low or "10042" in res["error"]:
        hint = " — CF 대시보드 → R2 에서 최초 활성화(무료 티어 있음)가 필요합니다"
    elif "authentication" in low or "permission" in low or res["status"] in (401, 403):
        hint = " — API 토큰에 'Workers R2 Storage:Edit' 권한을 추가하세요"
    return {"ok": False, "detail": f"R2 버킷 실패: {res['error']}{hint}"}


def _workers_subdomain(token: str, acc: str) -> dict:
    """계정의 workers.dev 서브도메인 — Worker 공개 주소의 재료."""
    res = _call("GET", f"/accounts/{acc}/workers/subdomain", token, timeout=30)
    sub = (res.get("result") or {}).get("subdomain") if res["ok"] else None
    if sub:
        return {"ok": True, "subdomain": sub}
    if res["status"] in (401, 403):
        return {"ok": False, "detail": "workers.dev 서브도메인 조회 권한 없음 — API 토큰에 "
                                       "'Workers Scripts:Edit' 권한을 추가하세요"}
    return {"ok": False, "detail": "이 계정에 workers.dev 서브도메인이 없습니다 — CF 대시보드 "
                                   "→ Workers 에서 서브도메인을 먼저 만드세요 (1회)"}


def _upload_worker(token: str, acc: str, name: str, origin_base: str,
                   bucket: str, secret: str) -> dict:
    """worker.js 업로드 — 바인딩(BUCKET·ORIGIN_BASE·SHOWCASE_SECRET)을 메타데이터로 심는다."""
    try:
        js = (_SITE / "worker.js").read_text(encoding="utf-8")
    except Exception as e:
        return {"ok": False, "detail": f"worker.js 읽기 실패: {e}"}
    metadata = {
        "main_module": "worker.js",
        "compatibility_date": _COMPAT_DATE,
        "bindings": [
            {"type": "r2_bucket", "name": "BUCKET", "bucket_name": bucket},
            {"type": "plain_text", "name": "ORIGIN_BASE", "text": origin_base},
            {"type": "secret_text", "name": "SHOWCASE_SECRET", "text": secret},
        ],
    }
    res = _call("PUT", f"/accounts/{acc}/workers/scripts/{name}", token, files={
        "metadata": (None, json.dumps(metadata), "application/json"),
        "worker.js": ("worker.js", js, "application/javascript+module"),
    })
    if res["ok"]:
        return {"ok": True, "detail": f"Worker 배포 ({name})"}
    hint = ""
    if res["status"] in (401, 403):
        hint = " — API 토큰에 'Workers Scripts:Edit' 권한을 추가하세요"
    return {"ok": False, "detail": f"Worker 배포 실패: {res['error']}{hint}"}


def _enable_subdomain_route(token: str, acc: str, name: str) -> dict:
    """<name>.<계정>.workers.dev 라우트 활성화."""
    res = _call("POST", f"/accounts/{acc}/workers/scripts/{name}/subdomain", token,
                body={"enabled": True, "previews_enabled": False}, timeout=30)
    if res["ok"]:
        return {"ok": True, "detail": "workers.dev 라우트 활성"}
    return {"ok": False, "detail": f"workers.dev 라우트 실패: {res['error']}"}


def _upload_index(token: str, acc: str, bucket: str) -> dict:
    """창고 SPA(index.html)를 R2 에 업로드 — Worker 의 serveIndex 폴백이 읽는다."""
    try:
        html = (_SITE / "index.html").read_bytes()
    except Exception as e:
        return {"ok": False, "detail": f"index.html 읽기 실패: {e}"}
    res = _call("PUT", f"/accounts/{acc}/r2/buckets/{bucket}/objects/index.html", token,
                data=html, headers={"Content-Type": "text/html"})
    if res["ok"]:
        return {"ok": True, "detail": f"index.html 업로드 ({len(html):,}B)"}
    return {"ok": False, "detail": f"index.html 업로드 실패: {res['error']}"}


def _probe(url: str, retries: int = 3, wait: float = 3.0) -> dict:
    """배포 직후 도달 검증 — workers.dev 첫 배포는 전파에 수 초 걸릴 수 있어 재시도."""
    import time
    last = ""
    for i in range(retries):
        try:
            r = requests.get(f"{url}/manifest", timeout=12)
            if r.status_code < 500:
                return {"ok": True, "detail": f"도달 확인 (/manifest {r.status_code})"}
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = str(e)
        if i < retries - 1:
            time.sleep(wait)
    return {"ok": False, "detail": f"도달 미확인({last}) — 전파 지연일 수 있음, 잠시 후 접속해 보세요"}


def provision_cdn(token: str, acc: str, origin_hostname: str, secret: str,
                  slug: str, worker: str = "") -> dict:
    """Worker+R2 를 통째로 발급. 반환 {ok, worker, url, steps[]} — 스텝은 발급기 로그 형식.

    멱등: 버킷·Worker 모두 이름 기준 재사용/덮어쓰기라 재실행 = 갱신 배포.
    (worker.js 가 저장소에서 바뀐 뒤 다시 부르면 새 코드로 갈아끼워진다.)

    worker= 이름 지정 — 기존 Worker 를 발급기 관리로 *흡수*할 때 쓴다(맥의 수공예
    `public-files` 이주, 2026-07-21 1단계): 같은 이름으로 재배포하면 주소·버킷이
    그대로인 채 관리 주체만 바뀐다. 생략하면 몸-유일 이름(public-files-<슬러그>).
    """
    steps = []
    name = re.sub(r"[^a-z0-9-]+", "-", worker.lower()).strip("-")[:63] if worker \
        else worker_name_for(slug)
    bucket = name  # 버킷 이름 = Worker 이름 (몸-유일 쌍)

    def step(key, r):
        steps.append({"step": f"cdn:{key}", "ok": r["ok"], "detail": r["detail"]})
        return r["ok"]

    if not step("r2", _ensure_bucket(token, acc, bucket)):
        return {"ok": False, "steps": steps}

    sub = _workers_subdomain(token, acc)
    if not sub.get("ok"):
        step("subdomain", sub)
        return {"ok": False, "steps": steps}
    steps.append({"step": "cdn:subdomain", "ok": True,
                  "detail": f"{sub['subdomain']}.workers.dev"})

    origin_base = f"https://{origin_hostname}"
    if not step("worker", _upload_worker(token, acc, name, origin_base, bucket, secret)):
        return {"ok": False, "steps": steps}
    if not step("route", _enable_subdomain_route(token, acc, name)):
        return {"ok": False, "steps": steps}
    step("index", _upload_index(token, acc, bucket))   # 실패해도 치명 아님(공개면은 성립)

    url = f"https://{name}.{sub['subdomain']}.workers.dev"
    step("probe", _probe(url))                          # 전파 지연은 경고로만
    return {"ok": True, "worker": name, "url": url, "steps": steps}


def remove_cdn(token: str, acc: str, worker: str) -> dict:
    """CDN 철거(검증·청소용) — Worker 스크립트 + 버킷(오브젝트 포함) 삭제.
    버킷은 비어야 지워지므로 오브젝트를 전부 열거·삭제한 뒤 버킷을 지운다
    (지연 캐시가 쓰는 cache/* 키들이 실사용 몇 분 만에 쌓인다 — 실측)."""
    steps = []
    r = _call("DELETE", f"/accounts/{acc}/workers/scripts/{worker}", token, timeout=30)
    steps.append({"step": "del:worker", "ok": r["ok"], "detail": r["error"] or "삭제"})
    from urllib.parse import quote
    deleted = 0
    for _ in range(20):                     # 페이지 상한 — 폭주 방어
        r = _call("GET", f"/accounts/{acc}/r2/buckets/{worker}/objects", token, timeout=30)
        keys = [o.get("key") for o in (r.get("result") or []) if o.get("key")]
        if not keys:
            break
        for k in keys:
            _call("DELETE", f"/accounts/{acc}/r2/buckets/{worker}/objects/{quote(k, safe='')}",
                  token, timeout=30)
            deleted += 1
    r = _call("DELETE", f"/accounts/{acc}/r2/buckets/{worker}", token, timeout=30)
    steps.append({"step": "del:bucket", "ok": r["ok"],
                  "detail": r["error"] or f"삭제 (오브젝트 {deleted}개 소거)"})
    return {"ok": all(s["ok"] for s in steps), "steps": steps}
