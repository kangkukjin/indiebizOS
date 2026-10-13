#!/usr/bin/env python3
"""미디어 세션(통화·확장 장치 카메라/마이크/스피커·재생 전달)을 IBL 에서 새 낱말 없이 부린다.

[self:script]{op:"run", id:"미디어세션", args:{...}} — 허브 백엔드의 /media API(docs/MEDIA_SESSION_CONTRACT.md §2)를 호출.
args:
  {"op": "capabilities", "target": "삼성1"}                      장치 능력(생략=허브 자신)
  {"op": "create", "kind": "extension", "purpose": "camera", "target": "삼성1", "want_mic": true}
  {"op": "create", "kind": "extension", "purpose": "playback", "target": "거실PC", "content": {"path": "~/Music/a.mp3", "position_s": 0}}
  {"op": "create", "kind": "call", "purpose": "voice_call", "target": "친구이름 또는 npub"}
  {"op": "status"|"end"|"accept"|"reject", "session_id": "..."}   (end: reason / reject: reason, block)
  {"op": "update", "session_id": "...", "expected_revision": 3, "changes": {"mute": true}}
  {"op": "list"} / {"op": "history", "limit": 20} / {"op": "health"}
출력: items 통화 — 세션은 items 한 행. 실패는 success:false + error(code·message). 토큰·SDP 는 다루지 않는다.
브라우저 화면(통화 창)은 조종실/연락처 버튼이 연다 — 이 스크립트는 제어만 한다.
"""
import json
import os
import sys
import urllib.error
import urllib.request

_PORT = os.environ.get("INDIEBIZ_API_PORT") or os.environ.get("INDIEBIZ_BACKEND_PORT") or "8765"
_BASE = f"http://127.0.0.1:{_PORT}"


def _http(method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(_BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return _norm(json.loads(resp.read().decode("utf-8") or "{}"), resp.status)
    except urllib.error.HTTPError as exc:
        try:
            return _norm(json.loads(exc.read().decode("utf-8") or "{}"), exc.code)
        except ValueError:
            return {"success": False, "error": {"code": f"http_{exc.code}", "message": str(exc)}}
    except (urllib.error.URLError, OSError) as exc:
        return {"success": False, "error": {"code": "backend_unreachable", "message": f"허브 백엔드에 닿지 못함: {exc}"}}


def _norm(body, status):
    """/media 봉투가 아닌 응답(404 Not Found 등)도 정직한 error 로 — 옛 허브(미디어 미탑재)를 구분한다."""
    if isinstance(body, dict) and "success" in body:
        return body
    detail = body.get("detail") if isinstance(body, dict) else body
    msg = "허브에 /media API 가 없습니다(백엔드 판 확인)" if status == 404 else str(detail)
    return {"success": False, "error": {"code": f"http_{status}", "message": msg}}


def _safe_result(value):
    """AI receives intent/status, never SDP, TURN credentials or session bearer tokens."""
    if isinstance(value, list):
        return [_safe_result(item) for item in value]
    if isinstance(value, dict):
        private = {"pending_offer", "ice_servers", "sdp", "secret", "token", "credential", "grant", "mac"}
        return {key: _safe_result(item) for key, item in value.items() if key not in private}
    if isinstance(value, str) and value.startswith(("http://", "https://", "ws://", "wss://")):
        from urllib.parse import urlsplit, urlunsplit
        url = urlsplit(value)
        return urlunsplit((url.scheme, url.netloc.rsplit("@", 1)[-1], url.path, "", ""))
    return value


def main():
    try:
        args = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        args = {}
    if not isinstance(args, dict):
        args = {}
    op = str(args.get("op") or "status")
    sid = str(args.get("session_id") or "")
    if op == "capabilities":
        q = "?target=" + urllib.request.quote(str(args["target"])) if args.get("target") else ""
        out = _http("GET", "/media/capabilities" + q)
        res = {"success": out.get("success", False), "items": [out.get("capabilities")] if out.get("success") else [],
               "error": out.get("error")}
    elif op == "health":
        out = _http("GET", "/media/health")
        res = {"success": out.get("success", False), "items": [out.get("health")] if out.get("success") else [], "error": out.get("error")}
    elif op == "list":
        out = _http("GET", "/media/sessions?active=" + ("1" if args.get("active", True) else "0"))
        res = {"success": out.get("success", False), "items": out.get("items") or [], "error": out.get("error")}
    elif op == "history":
        out = _http("GET", f"/media/history?limit={int(args.get('limit') or 50)}")
        res = {"success": out.get("success", False), "items": out.get("items") or [], "error": out.get("error")}
    elif op == "create":
        body = {k: args[k] for k in ("kind", "purpose", "target", "tracks", "delivery", "request_id", "content", "want_mic") if k in args}
        if args.get("camera"):
            body["camera"] = args["camera"]
        if body.get("purpose") == "playback":
            body.setdefault("delivery", "content")
        out = _http("POST", "/media/sessions", body)
        res = {"success": out.get("success", False), "items": [out["session"]] if out.get("success") else [], "error": out.get("error")}
    elif op in ("status", "accept", "reject", "end", "update"):
        if not sid:
            res = {"success": False, "items": [], "error": {"code": "session_id_required", "message": "session_id 가 필요합니다"}}
        elif op == "status":
            out = _http("GET", f"/media/sessions/{sid}")
            res = {"success": out.get("success", False), "items": [out["session"]] if out.get("success") else [], "error": out.get("error")}
        else:
            body = {"reason": args.get("reason"), "block": args.get("block"),
                    "expected_revision": args.get("expected_revision"), "changes": args.get("changes")}
            body = {k: v for k, v in body.items() if v is not None}
            out = _http("POST", f"/media/sessions/{sid}/{op}", body)
            res = {"success": out.get("success", False), "items": [out["session"]] if out.get("success") else [], "error": out.get("error")}
    else:
        res = {"success": False, "items": [], "error": {"code": "unknown_op", "message": f"모르는 op: {op}"}}
    if res.get("error") is None:
        res.pop("error", None)
    elif isinstance(res["error"], dict):
        res["error"] = f"{res['error'].get('code')}: {res['error'].get('message') or ''}".strip(": ")
    print(json.dumps(_safe_result(res), ensure_ascii=False))


if __name__ == "__main__":
    main()
