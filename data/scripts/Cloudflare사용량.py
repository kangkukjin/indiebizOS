"""Cloudflare 사용량 — 무료 한도 대비 (R2 저장·R2 작업·Workers 요청). 등록 스크립트.

2026-09-05 ep2833: "내 Cloudflare 상태 봐줄래" 에 시스템 AI 가 `[limbs:cloudflare_api]` 로는 GraphQL
분석을 못 불러 `.env` 를 직접 파싱하는 임시 파이썬 셋으로 답했다 — 해마에 남지 않아 다음 질문이
같은 6분을 다시 쓴다. IBL 헌법대로 그 배관을 `[self:script]` 로 얼린다(새 어휘 아님).

args (stdin JSON):
  days       기간(기본 30) — Workers 요청·R2 작업 추이
  account_id 계정(기본 CLOUDFLARE_ACCOUNT_ID 환경변수 → 없으면 /accounts 첫 계정)
  sections   "all"(기본) | "r2" | "workers"
출력: {"items": [...], "message": "...", "period": {...}} — items 통화(section 열로 구분)
  section=r2_storage  : 버킷별 최근 관측일 저장량 GB·객체 수 · free_limit_gb 10 · pct_of_free
  section=r2_ops      : 이달 Class A/B 작업 수 · free_limit(A 100만/B 1000만) · pct_of_free
  section=workers     : 스크립트별 기간 요청·오류·최대 일요청 · free_limit_per_day 100000 · pct_of_free_max_day
무료 한도 수치는 Cloudflare 가 공개한 Free 플랜 값(2026-09 기준, 반증 가능한 세계의 데이터) — 바뀌면 여기만 고친다.
토큰은 환경변수(CLOUDFLARE_API_TOKEN)로만 — 파일에서 직접 읽지 않는다.
"""
import datetime as _dt
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.cloudflare.com/client/v4"
FREE_R2_STORAGE_GB = 10.0
FREE_R2_CLASS_A = 1_000_000
FREE_R2_CLASS_B = 10_000_000
FREE_WORKERS_PER_DAY = 100_000
CLASS_A = {"ListBuckets", "PutBucket", "ListObjects", "PutObject", "CopyObject", "CompleteMultipartUpload",
           "CreateMultipartUpload", "ListMultipartUploads", "UploadPart", "UploadPartCopy", "ListParts",
           "PutBucketEncryption", "PutBucketCors", "PutBucketLifecycleConfiguration", "DeleteObject"}
CLASS_B = {"HeadBucket", "HeadObject", "GetObject", "UsageSummary", "GetBucketEncryption", "GetBucketLocation",
           "GetBucketCors", "GetBucketLifecycleConfiguration"}


def _fail(msg):
    print(json.dumps({"success": False, "error": msg}, ensure_ascii=False))
    sys.exit(1)


def _http(url, token, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                                 method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        _fail(f"HTTP {e.code} {url}: {e.read().decode()[:300]}")
    except Exception as e:  # noqa: BLE001
        _fail(f"{type(e).__name__}: {e}")


def _graphql(token, query, variables):
    d = _http(f"{API}/graphql", token, {"query": query, "variables": variables})
    if d.get("errors"):
        _fail("GraphQL: " + "; ".join(str(e.get("message", e)) for e in d["errors"])[:400])
    accs = (((d.get("data") or {}).get("viewer") or {}).get("accounts") or [])
    return accs[0] if accs else {}


# ── 순수 집계(시험 가능) ──
def aggregate_r2_storage(groups):
    """r2StorageAdaptiveGroups 행들 → 버킷별 최근 관측일 저장량 + 합계 행."""
    latest = {}
    for g in groups or []:
        dim = g.get("dimensions") or {}
        b, d = dim.get("bucketName") or "", dim.get("date") or ""
        if not b:
            continue
        mx = g.get("max") or {}
        size = (mx.get("payloadSize") or 0) + (mx.get("metadataSize") or 0)
        if b not in latest or d > latest[b]["date"]:
            latest[b] = {"date": d, "bytes": size, "objects": mx.get("objectCount") or 0}
    rows, total_b, total_o = [], 0, 0
    for b in sorted(latest):
        v = latest[b]
        gb = v["bytes"] / 1e9
        total_b += v["bytes"]
        total_o += v["objects"]
        rows.append({"section": "r2_storage", "bucket": b, "date": v["date"], "gb": round(gb, 3),
                     "objects": v["objects"], "free_limit_gb": FREE_R2_STORAGE_GB,
                     "pct_of_free": round(gb / FREE_R2_STORAGE_GB * 100, 1)})
    if rows:
        gb = total_b / 1e9
        rows.append({"section": "r2_storage", "bucket": "(전체)", "date": max(v["date"] for v in latest.values()),
                     "gb": round(gb, 3), "objects": total_o, "free_limit_gb": FREE_R2_STORAGE_GB,
                     "pct_of_free": round(gb / FREE_R2_STORAGE_GB * 100, 1)})
    return rows


def aggregate_r2_ops(groups):
    """r2OperationsAdaptiveGroups 행들(이달) → Class A/B 합계 행."""
    a = b = other = 0
    for g in groups or []:
        t = (g.get("dimensions") or {}).get("actionType") or ""
        n = (g.get("sum") or {}).get("requests") or 0
        if t in CLASS_A:
            a += n
        elif t in CLASS_B:
            b += n
        else:
            other += n
    rows = [{"section": "r2_ops", "class": "A", "month_requests": a, "free_limit": FREE_R2_CLASS_A,
             "pct_of_free": round(a / FREE_R2_CLASS_A * 100, 2)},
            {"section": "r2_ops", "class": "B", "month_requests": b, "free_limit": FREE_R2_CLASS_B,
             "pct_of_free": round(b / FREE_R2_CLASS_B * 100, 2)}]
    if other:
        rows.append({"section": "r2_ops", "class": "(미분류)", "month_requests": other, "free_limit": None,
                     "pct_of_free": None})
    return rows


def aggregate_workers(groups):
    """workersInvocationsAdaptive 행들(스크립트·일) → 스크립트별 기간 합계·최대 일요청 행 + 전체 행."""
    per = {}
    day_total = {}
    for g in groups or []:
        dim = g.get("dimensions") or {}
        s, d = dim.get("scriptName") or "", dim.get("date") or ""
        sm = g.get("sum") or {}
        req, err = sm.get("requests") or 0, sm.get("errors") or 0
        p = per.setdefault(s, {"requests": 0, "errors": 0, "max_day": "", "max_day_requests": -1})
        p["requests"] += req
        p["errors"] += err
        if req > p["max_day_requests"]:
            p["max_day"], p["max_day_requests"] = d, req
        day_total[d] = day_total.get(d, 0) + req
    rows = []
    for s in sorted(per, key=lambda k: -per[k]["requests"]):
        p = per[s]
        rows.append({"section": "workers", "script": s, "days_requests": p["requests"], "errors": p["errors"],
                     "max_day": p["max_day"], "max_day_requests": max(p["max_day_requests"], 0),
                     "free_limit_per_day": FREE_WORKERS_PER_DAY,
                     "pct_of_free_max_day": round(max(p["max_day_requests"], 0) / FREE_WORKERS_PER_DAY * 100, 2)})
    if day_total:
        md = max(day_total, key=day_total.get)
        rows.append({"section": "workers", "script": "(전체)", "days_requests": sum(day_total.values()),
                     "errors": sum(p["errors"] for p in per.values()), "max_day": md,
                     "max_day_requests": day_total[md], "free_limit_per_day": FREE_WORKERS_PER_DAY,
                     "pct_of_free_max_day": round(day_total[md] / FREE_WORKERS_PER_DAY * 100, 2)})
    return rows


def summarize(rows):
    parts = []
    st = [r for r in rows if r["section"] == "r2_storage" and r["bucket"] == "(전체)"]
    if st:
        parts.append(f"R2 저장 {st[0]['gb']}GB/{FREE_R2_STORAGE_GB:g}GB({st[0]['pct_of_free']}%)")
    for r in rows:
        if r["section"] == "r2_ops" and r["class"] in ("A", "B"):
            parts.append(f"R2 Class {r['class']} {r['month_requests']:,}/{r['free_limit']:,}({r['pct_of_free']}%)")
    wk = [r for r in rows if r["section"] == "workers" and r["script"] == "(전체)"]
    if wk:
        parts.append(f"Workers 최대 일요청 {wk[0]['max_day_requests']:,}/{FREE_WORKERS_PER_DAY:,}"
                     f"({wk[0]['pct_of_free_max_day']}%, {wk[0]['max_day']})")
    return " · ".join(parts) or "관측 없음"


def main():
    try:
        args = json.loads(sys.stdin.read() or "{}") or {}
    except json.JSONDecodeError:
        _fail("args 는 JSON 객체여야 합니다.")
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if not token:
        _fail("CLOUDFLARE_API_TOKEN 환경변수가 없습니다 — 백엔드 .env 에 두면 스크립트가 물려받는다.")
    days = int(args.get("days") or 30)
    sections = str(args.get("sections") or "all").lower()
    acct = str(args.get("account_id") or os.environ.get("CLOUDFLARE_ACCOUNT_ID") or "").strip()
    if not acct:
        d = _http(f"{API}/accounts", token)
        res = d.get("result") or []
        if not res:
            _fail("계정을 찾을 수 없습니다(/accounts 빈 결과).")
        acct = res[0]["id"]
    now = _dt.datetime.now(_dt.timezone.utc)
    start = now - _dt.timedelta(days=days)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    iso = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
    rows = []
    if sections in ("all", "r2"):
        q = """query($a:String!,$s:Time!,$e:Time!,$ms:Time!){ viewer { accounts(filter:{accountTag:$a}) {
          r2StorageAdaptiveGroups(limit:10000, filter:{datetime_geq:$s, datetime_leq:$e}) {
            dimensions { date bucketName } max { objectCount payloadSize metadataSize } }
          r2OperationsAdaptiveGroups(limit:10000, filter:{datetime_geq:$ms, datetime_leq:$e}) {
            dimensions { actionType } sum { requests } } } } }"""
        acc = _graphql(token, q, {"a": acct, "s": iso(start), "e": iso(now), "ms": iso(month_start)})
        rows += aggregate_r2_storage(acc.get("r2StorageAdaptiveGroups"))
        rows += aggregate_r2_ops(acc.get("r2OperationsAdaptiveGroups"))
    if sections in ("all", "workers"):
        q = """query($a:String!,$s:Time!,$e:Time!){ viewer { accounts(filter:{accountTag:$a}) {
          workersInvocationsAdaptive(limit:10000, filter:{datetime_geq:$s, datetime_leq:$e}) {
            dimensions { scriptName date } sum { requests errors } } } } }"""
        acc = _graphql(token, q, {"a": acct, "s": iso(start), "e": iso(now)})
        rows += aggregate_workers(acc.get("workersInvocationsAdaptive"))
    print(json.dumps({"items": rows, "count": len(rows), "message": summarize(rows),
                      "period": {"days": days, "start": iso(start), "end": iso(now), "month_start": iso(month_start)},
                      "free_plan": {"r2_storage_gb": FREE_R2_STORAGE_GB, "r2_class_a": FREE_R2_CLASS_A,
                                    "r2_class_b": FREE_R2_CLASS_B, "workers_per_day": FREE_WORKERS_PER_DAY}},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
