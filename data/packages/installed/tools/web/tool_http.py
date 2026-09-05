"""[sense:http] — HTTP 탐침(HEAD/GET, 읽기 전용) (2026-09-05, 사용자 판정 "어휘는 만들자").

왜: 모델이 스트림 엔드포인트의 Range 응답·상태 코드·헤더를 보려고 curl 로 나갔다(새 요청 2주 41회, ep2835).
crawl 은 본문을 문단으로 뭉개므로 "상태·헤더·바이트·지연" 을 보는 눈이 없었다. 이 낱말은 그 *접근*만 캡슐화한다.

계약(읽기 전용):
  · op=head(기본): url(·headers·range·timeout) → items 1행 {url, final_url, status, ok, elapsed_ms, content_type, content_length,
    accept_ranges, content_range, headers(소문자 키 dict), redirected}
  · op=body: 같은 행 + bytes(받은 본문 길이)·body_preview(앞 max_preview 자, 텍스트일 때만). 본문은 max_bytes 까지만 읽는다(기본 64KB).
  · range: "bytes=0-99999" 같은 Range 헤더 값 — 206·Content-Range 를 확인하는 자리.
  · GET/HEAD 만 — POST 같은 부작용 요청은 이 낱말이 아니다(등록 스크립트·[self:script]).
  · 4xx/5xx 도 실패가 아니라 관측이다: success:true, ok:false, status 로 말한다. 연결 실패·타임아웃만 success:false.
"""
import json
import time
import urllib.error
import urllib.request

MAX_BYTES_DEFAULT = 65536
MAX_PREVIEW_DEFAULT = 600
TIMEOUT_DEFAULT = 15
_TEXT_TYPES = ("text/", "application/json", "application/xml", "application/javascript", "application/x-www-form-urlencoded")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """리다이렉트를 따라가되 횟수·최종 URL 을 기록한다."""

    def __init__(self):
        self.hops = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.hops += 1
        if self.hops > 5:
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _row(url, resp_url, status, headers, elapsed_ms, hops):
    h = {k.lower(): v for k, v in headers.items()} if headers else {}
    cl = h.get("content-length")
    try:
        cl = int(cl) if cl is not None else None
    except ValueError:
        pass
    return {"url": url, "final_url": resp_url or url, "status": status, "ok": 200 <= int(status) < 400,
            "elapsed_ms": elapsed_ms, "content_type": h.get("content-type"), "content_length": cl,
            "accept_ranges": h.get("accept-ranges"), "content_range": h.get("content-range"),
            "redirected": hops > 0, "headers": h}


def probe(tool_input: dict) -> dict:
    url = str(tool_input.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return {"success": False, "items": [], "error": "url 파라미터에 http/https 주소가 필요합니다."}
    op = str(tool_input.get("op") or "head").strip().lower()
    if op not in ("head", "body"):
        return {"success": False, "items": [], "error": f"알 수 없는 op: {op} (가능: head/body) — 부작용 요청(POST 등)은 이 낱말이 아닙니다. 본문까지 보려면 op: \"body\"."}
    try:
        timeout = float(tool_input.get("timeout") or TIMEOUT_DEFAULT)
    except (TypeError, ValueError):
        timeout = TIMEOUT_DEFAULT
    timeout = max(1.0, min(timeout, 120.0))  # clamp-ok: 탐침은 짧게 — 긴 다운로드는 이 낱말의 일이 아니다
    try:
        max_bytes = int(tool_input.get("max_bytes") or MAX_BYTES_DEFAULT)
    except (TypeError, ValueError):
        max_bytes = MAX_BYTES_DEFAULT
    try:
        max_preview = int(tool_input.get("max_preview") or MAX_PREVIEW_DEFAULT)
    except (TypeError, ValueError):
        max_preview = MAX_PREVIEW_DEFAULT
    headers = {"User-Agent": "indiebizOS-probe/1.0"}
    extra = tool_input.get("headers")
    if isinstance(extra, dict):
        headers.update({str(k): str(v) for k, v in extra.items()})
    rng = tool_input.get("range")
    if isinstance(rng, str) and rng.strip():
        headers["Range"] = rng.strip() if rng.strip().lower().startswith("bytes=") else f"bytes={rng.strip()}"
    req = urllib.request.Request(url, headers=headers, method="HEAD" if op == "head" else "GET")   # body = HTTP GET(이름은 정본 규칙 — get 금지)
    redirector = _NoRedirect()
    opener = urllib.request.build_opener(redirector)
    t0 = time.time()
    body = b""
    try:
        with opener.open(req, timeout=timeout) as resp:
            status = resp.status
            resp_headers = dict(resp.headers.items())
            resp_url = resp.geturl()
            if op == "body":
                body = resp.read(max_bytes + 1)
    except urllib.error.HTTPError as e:                     # 4xx/5xx — 관측이지 실패가 아니다
        status = e.code
        resp_headers = dict(e.headers.items()) if e.headers else {}
        resp_url = e.geturl() if hasattr(e, "geturl") else url
        if op == "body":
            try:
                body = e.read(max_bytes + 1)
            except Exception:
                body = b""
    except urllib.error.URLError as e:
        return {"success": False, "items": [], "url": url, "error": f"연결 실패: {getattr(e, 'reason', e)}",
                "elapsed_ms": int((time.time() - t0) * 1000)}
    except (TimeoutError, OSError) as e:
        return {"success": False, "items": [], "url": url, "error": f"요청 실패: {type(e).__name__}: {e}",
                "elapsed_ms": int((time.time() - t0) * 1000)}
    elapsed_ms = int((time.time() - t0) * 1000)
    row = _row(url, resp_url, status, resp_headers, elapsed_ms, redirector.hops)
    if op == "body":
        truncated = len(body) > max_bytes
        body = body[:max_bytes]
        row["bytes"] = len(body)
        row["body_truncated"] = truncated
        ctype = (row.get("content_type") or "").lower()
        if any(ctype.startswith(t) for t in _TEXT_TYPES):
            try:
                text = body.decode("utf-8", errors="replace")
            except Exception:
                text = ""
            row["body_preview"] = text[:max_preview]
    out = {"success": True, "op": op, "url": url, "status": status, "ok": row["ok"], "count": 1, "items": [row]}
    if not row["ok"]:
        out["note"] = f"HTTP {status} — 요청은 닿았고 서버가 이렇게 답했습니다(연결 실패가 아님)."
    return out


if __name__ == "__main__":                                  # 손 점검용
    import sys
    print(json.dumps(probe({"url": sys.argv[1] if len(sys.argv) > 1 else "https://example.com", "op": "head"}),
                     ensure_ascii=False, indent=1))
