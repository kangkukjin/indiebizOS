"""AI시대 뉴스: 완료된 AI 동향 보고서의 공개 출처만 전달한다."""
import contextlib
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from urllib.request import Request, urlopen

BASE = Path(__file__).resolve().parents[2]
REPORTS = BASE / "outputs/ai_trend_reports"
STATE = BASE / "outputs/ai_era_news/state.json"
START = "2026-09-15"
ENDPOINT = "https://ai-era-b18.pages.dev/api/news"
FIELDS = {"key", "url", "title_ko", "publisher", "report_date", "published_date"}
HOSTS = {
    "pymnts.com": "PYMNTS", "n.news.naver.com": "뉴시스",
    "tokenpost.kr": "토큰포스트", "ifm.ai": "IFM",
    "pandaily.com": "Pandaily", "withspecific.com": "Specific Labs",
    "news-medical.net": "News-Medical", "arxiv.org": "arXiv",
    "blog.naver.com": "네이버 블로그", "github.com": "GitHub",
    "fortune.com": "Fortune", "fedscoop.com": "FedScoop",
    "ubergizmo.com": "Ubergizmo",
}

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def safe_url(value):
    u = urlsplit(value)
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not host or u.username or u.password or u.port not in (None, 443):
        raise ValueError("공개 HTTPS 출처만 허용")
    if "." not in host or host.endswith((".local", ".internal", ".localhost")):
        raise ValueError("비공개 호스트")
    try:
        if not ipaddress.ip_address(host).is_global:
            raise ValueError("비공개 주소")
    except ValueError as exc:
        if str(exc) == "비공개 주소":
            raise
    pairs = parse_qsl(u.query, keep_blank_values=True)
    if any(re.search(r"token|secret|password|api.?key|signature|auth", k, re.I) for k, _ in pairs):
        raise ValueError("인증정보 포함 URL")
    pairs = [(k, v) for k, v in pairs if not k.startswith("utm_") and k not in ("fbclid", "gclid")]
    return urlunsplit(("https", u.netloc.lower(), u.path, urlencode(pairs), ""))

def load_state():
    if not STATE.exists():
        return {"version": 1, "candidates": {}, "done": {}, "metadata": {}}
    s = json.loads(STATE.read_text())
    if s.get("version") != 1:
        raise ValueError("뉴스 상태 형식 오류")
    return s

def save_state(s):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".state-", dir=STATE.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(s, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, STATE)
    finally:
        if os.path.exists(name):
            os.unlink(name)

@contextlib.contextmanager
def state_lock():
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with (STATE.parent / ".lock").open("a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield

def rows_of(value):
    if value is None or value == "":
        return []
    if isinstance(value, str):
        value = json.loads(value)
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and isinstance(value.get("items"), list):
        return value["items"]
    raise ValueError("items 목록 필요")

def report_fingerprint(report, rows):
    return digest(report.read_text() + "\n" + rows.read_text())

def prepare():
    ledger = json.loads((REPORTS / "_coverage_ledger.json").read_text())
    complete = {x.get("file") or "ai_trend_report_" + x["date"] + ".md" for x in ledger}
    issues, eligible = [], {}
    with state_lock():
        s = load_state()
        for filename in sorted(complete):
            m = re.fullmatch(r"ai_trend_report_(\d{4}-\d{2}-\d{2})(?:_evening)?\.md", filename)
            if not m or m[1] < START:
                continue
            report = REPORTS / filename
            verified = REPORTS / ("_verified_rows_" + m[1] + ".json")
            if not report.exists() or not verified.exists():
                issues.append({"report_date": m[1], "reason": "완료 보고서 또는 검증 출처 목록 누락"})
                continue
            if time.time() - max(report.stat().st_mtime, verified.stat().st_mtime) < 120:
                continue
            text = report.read_text()
            if not re.search(r"^## 출처\s*$", text, re.M):
                issues.append({"report_date": m[1], "reason": "출처 절 누락"})
                continue
            version = report_fingerprint(report, verified)
            for row in rows_of(json.loads(verified.read_text())):
                if row.get("verified") is not True or row.get("label") not in ("NEW", "CHANGED", "ONGOING"):
                    continue
                # 재유입·기각 판정 및 URL 없는 장부 행은 뉴스가 아니다.
                if row.get("label") == "ONGOING" and re.search(r"기각|제외|강등|미열람", str(row.get("summary", ""))):
                    continue
                try:
                    url = safe_url(row.get("url", ""))
                    if urlsplit(url).path in ("", "/"):
                        continue
                except (ValueError, TypeError):
                    continue
                key = digest(filename + "\n" + url)
                candidate = {"key": key, "url": url, "report_date": m[1],
                             "version": version, "report": filename,
                             "verified": verified.name}
                eligible[key] = candidate
                s["candidates"][key] = candidate
        # 현재 원장에 있는 보고서의 삭제/수정된 후보는 과거 pending에서 배제한다.
        for key, c in list(s["candidates"].items()):
            if c["report"] in complete and key not in eligible:
                del s["candidates"][key]
        pending = [c for key, c in s["candidates"].items()
                   if s["done"].get(key) != c["version"]]
        pending.sort(key=lambda c: (c["report_date"], c["key"]))
        s["last_prepare"] = {"time": time.time(), "pending": len(pending), "issues": issues}
        save_state(s)
    # 내부 경로·요약·장부 문자열은 모델/공개 배관에 싣지 않는다.
    return {"items": [{k: c[k] for k in ("key", "url", "report_date")}
                      for c in pending[:40]], "pending": len(pending),
            "remaining": max(0, len(pending)-40), "issues": issues}

def normalize(data):
    groups = {}
    for row in rows_of(data):
        if row.get("key"):
            groups.setdefault(row["key"], []).append(row)
    result, errors = [], []
    with state_lock():
        s = load_state()
        for key, meta in groups.items():
            c = s["candidates"].get(key)
            if not c:
                raise ValueError("알 수 없는 후보")
            titles = [r for r in meta if r.get("field") == "title" and r.get("value")]
            titles = [r for r in titles if not re.search(r"access denied|just a moment|captcha|403 forbidden|404 not found", str(r["value"]), re.I)]
            titles.sort(key=lambda r: (0 if "headline" in r.get("source", "") else
                                      1 if "og:title" in r.get("source", "") else
                                      2 if "twitter:title" in r.get("source", "") else 3))
            if not titles:
                errors.append({"key": key, "reason": "원문 제목 확인 실패"})
                continue
            # 한국어 제목 중간의 말줄임표는 흔한 구두점이다. 끝이 잘린
            # 메타 제목만 제외하고, 같은 페이지의 완전한 다른 제목을 찾는다.
            complete = [r for r in titles
                        if 3 <= len(str(r["value"]).strip()) <= 500
                        and not str(r["value"]).strip().endswith(("…", "..."))]
            if not complete:
                errors.append({"key": key, "reason": "제목 잘림"})
                continue
            selected = complete[0]
            title = str(selected["value"]).strip()
            try:
                url = safe_url(selected.get("source_url") or selected["url"])
                if urlsplit(url).hostname == "news.google.com":
                    raise ValueError("원문 주소 미해소")
            except ValueError as exc:
                errors.append({"key": key, "reason": str(exc)})
                continue
            dates = sorted({str(r.get("normalized") or r.get("value"))[:10]
                            for r in meta if r.get("field") == "published_at"
                            and re.match(r"\d{4}-\d{2}-\d{2}", str(r.get("normalized") or r.get("value")))})
            published = dates[0] if len(dates) == 1 else None
            host = urlsplit(url).hostname.removeprefix("www.")
            publisher = HOSTS.get(host, host)
            record = {"key": key, "url": url, "original_title": title,
                      "publisher": publisher, "report_date": c["report_date"],
                      "published_date": published}
            s["metadata"][key] = {**record, "version": c["version"]}
            result.append(record)
        s["last_normalize"] = {"errors": errors, "count": len(result)}
        save_state(s)
    return {"items": result, "errors": errors, "error_count": len(errors)}

def validate_public(rows, s):
    clean = []
    seen = set()
    for r in rows:
        key = r.get("key")
        if key in seen:
            raise ValueError("중복 입력")
        seen.add(key)
        m = s["metadata"].get(key)
        c = s["candidates"].get(key)
        if not m or not c or m["version"] != c["version"]:
            raise ValueError("원문 메타데이터 누락 또는 수정됨")
        if report_fingerprint(REPORTS / c["report"], REPORTS / c["verified"]) != c["version"]:
            raise ValueError("보고서가 처리 중 변경됨: 다음 실행에서 재시도")
        for field in ("url", "publisher", "report_date", "published_date"):
            if r.get(field) != m[field]:
                raise ValueError("번역에서 원문 식별정보 변경")
        title = r.get("title_ko")
        if not isinstance(title, str) or not 2 <= len(title) <= 500 or not re.search("[가-힣]", title):
            raise ValueError("한국어 제목 누락")
        if re.search(r"[<>\n\r]|https?://|/Users/|api.?key|Bearer ", title, re.I):
            raise ValueError("제목에 허용되지 않은 내용")
        clean.append({k: r.get(k) for k in FIELDS})
    return clean

def publish(data):
    rows = rows_of(data)
    if not rows:
        return {"items": [], "sent": 0}
    with state_lock():
        s = load_state()
        clean = validate_public(rows, s)
        token = subprocess.check_output(
            ["security", "find-generic-password", "-s", "ai-era-community-admin", "-w"],
            stderr=subprocess.DEVNULL, text=True).strip()
        request = Request(ENDPOINT, data=json.dumps({"items": clean}).encode(),
                          headers={"Authorization": "Bearer " + token,
                                   "Content-Type": "application/json",
                                   "User-Agent": "Mozilla/5.0 (compatible; AiEraNews/1.0)"}, method="POST")
        with urlopen(request, timeout=45) as response:
            receipt = json.load(response)
        if not receipt.get("ok") or set(receipt.get("accepted", [])) != {r["key"] for r in clean}:
            raise ValueError("뉴스 전송 영수증 불일치")
        for r in clean:
            s["done"][r["key"]] = s["candidates"][r["key"]]["version"]
        s["last_publish"] = {"time": time.time(), "sent": len(clean),
                             "inserted": receipt["inserted"], "updated": receipt["updated"]}
        save_state(s)
    return {"items": [], "sent": len(clean), "inserted": receipt["inserted"],
            "updated": receipt["updated"], "unchanged": receipt["unchanged"]}

def main(args):
    op = args.get("op", "prepare")
    if op == "prepare":
        return prepare()
    if op == "normalize":
        return normalize(args["data"])
    if op == "publish":
        return publish(args["data"])
    if op == "retry":
        with state_lock():
            s = load_state()
            for key in args["keys"]:
                if key not in s["candidates"]:
                    raise ValueError("알 수 없는 재시도 키")
                s["done"].pop(key, None)
            save_state(s)
        return {"items": [], "retry": len(args["keys"])}
    if op == "status":
        s = load_state()
        pending = {k for k, c in s["candidates"].items()
                   if s["done"].get(k) != c["version"]}
        errors = [e for e in s.get("last_normalize", {}).get("errors", [])
                  if e["key"] in pending]
        issues = s.get("last_prepare", {}).get("issues", [])
        return {"items": [], "success": not errors and not issues,
                "candidates": len(s["candidates"]), "done": len(s["done"]),
                "pending_count": len(pending), "errors": errors, "issues": issues,
                "prepare": s.get("last_prepare"), "normalize": s.get("last_normalize"),
                "publish": s.get("last_publish")}
    raise ValueError("지원하지 않는 작업")

if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False))
    except Exception as exc:
        # HTTP 본문·토큰·내부 경로는 로그에 출력하지 않는다.
        print(json.dumps({"success": False, "error": type(exc).__name__ + (" HTTP " + str(exc.code) if hasattr(exc, "code") else "") + ": " +
                          ("동기화 실패; 기존 뉴스 유지, 다음 실행에서 재시도"
                           if not isinstance(exc, ValueError) else str(exc))}, ensure_ascii=False))
        sys.exit(1)
