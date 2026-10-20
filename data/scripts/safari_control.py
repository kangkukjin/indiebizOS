"""Safari 창·탭 드라이버 — 본체 앱 조작면 `app:com.apple.Safari` 의 고정 실행 부품.

CONTROL_DRIVER_DESIGN_2026_10_20 §13 걸음 3 의 시범. 46~48회차 긴 문장 훈련에서 화면 조작(좌표·ref)으로
더듬다 생긴 발견 — 탭 전환 불가(L46-1), 새 탭 뒤 활성 탭 조용히 전환(L48-1) — 은 "Safari 에게 현재 탭을
바꿔라" 하고 말하는 계약 통로에서는 애초에 생기지 않는다. 이 부품은 그 통로다.

stdin: {op: contract/status/open/switch/close, url, window_id, tab, launch}
- 어느 탭을 열고 닫을지는 AI 가 정한다. 여기는 기계적 부분(AppleScript 사전 호출·재조회)만 얼린다.
- 동작마다 실행 조건(needs_front·shared_state·isolated_resources)을 CONTRACT 에 적고, 실행 직전 검사가
  OS·실행 중 여부·권한을 확인한다. 어떤 동작도 Safari 를 앞으로 가져오지(activate) 않는다.
- 결과는 그림이 아니라 상태값이다. `verified` 는 변경 뒤 AppleScript 재조회(`applescript_tab_readback`)를
  통과했다는 보고이며 화면에 실제로 그려졌는지는 범위 밖이다.
- 시간 초과·응답 유실은 실패가 아니라 불명확이다. 변경을 재전송하지 않고 **변경 없이** 재조회해 판별하고,
  판별이 안 되면 `unknown` 을 유지한다(실측: 숨은 Safari 의 첫 창 만들기는 효과가 즉시 나고 응답은 20초 넘게 늦었다).
stdlib 만 쓴다. 등록: data/scripts/registry.yaml `Safari제어`, 가이드 safari_control.md.
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

SURFACE = "app:com.apple.Safari"
APP = "Safari"
READBACK = "applescript_tab_readback"
OSA_TIMEOUT = 10
CONTRACT = {
    "version": 1,
    "surface": SURFACE,
    "supported_platforms": ["darwin"],
    "verification_scope": {
        READBACK: "변경 뒤 Safari 사전으로 창·탭 상태를 재조회해 요청과 대조했다. 화면 표시·페이지 로드 완료는 범위 밖.",
        "applescript_readback": "현재 창·탭 상태 조회. 변경 없음.",
    },
    "actions": {
        "status": {"params": [], "optional": [], "needs_front": False, "shared_state": False,
                   "isolated_resources": [], "verification_scope": "applescript_readback",
                   "effect": "창·탭 목록과 현재 탭. 변경 없음"},
        "open": {"params": ["url"], "optional": ["window_id", "launch"], "needs_front": False, "shared_state": False,
                 "isolated_resources": [], "verification_scope": READBACK,
                 "effect": "지정 창(기본 첫 창)의 끝에 배경 탭을 만든다. 현재 탭은 바뀌지 않는다. 창이 없으면 새 창이 생기며(window_created) 그때는 사용자 화면에 창 하나가 추가된다. Safari 가 꺼져 있으면 launch:true 일 때만 배경으로 띄운다"},
        "switch": {"params": ["window_id", "tab"], "optional": [], "needs_front": False, "shared_state": True,
                   "isolated_resources": [], "verification_scope": READBACK,
                   "effect": "그 창의 현재 탭을 바꾼다 — 사용자가 보는 탭이 바뀌는 요청된 효과. Safari 를 앞으로 가져오지 않는다"},
        "close": {"params": ["window_id", "tab"], "optional": [], "needs_front": False, "shared_state": True,
                  "isolated_resources": [], "verification_scope": READBACK,
                  "effect": "그 창의 탭 하나를 닫는다. 마지막 탭이면 창이 닫힌다"},
    },
    "failure_codes": {
        "UNSUPPORTED_PLATFORM": "darwin 이 아닌 본체", "TARGET_MISSING": "Safari 미실행·창·탭 없음(-1719/-1728)",
        "PERMISSION_REQUIRED": "자동화(Apple Events) 권한 미허용(-1743)", "INVALID_ARGUMENT": "인수 검증 실패",
        "UNKNOWN": "응답 유실·시간 초과 뒤 재조회로도 실행 여부를 판별하지 못함",
    },
}


class Failure(Exception):
    def __init__(self, code, message, next_step=None, **extra):
        super().__init__(message)
        self.code, self.next_step, self.extra = code, next_step, extra


def now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------- AppleScript

def apple_event(script, timeout=OSA_TIMEOUT):
    """한 번 호출, 재시도 없음. 시간 초과는 TimeoutExpired 그대로 — 호출자가 '불명확'으로 다룬다."""
    proc = subprocess.run(["osascript", "-s", "s", "-e", script], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        err = proc.stderr.strip()
        code = re.search(r"\((-\d+)\)\s*$", err)
        number = int(code.group(1)) if code else None
        if number == -1743:
            raise Failure("PERMISSION_REQUIRED", "Safari 자동화 권한이 없습니다. 시스템 설정 > 개인정보 보호 및 보안 > 자동화에서 "
                          "IndieBiz(Python)의 Safari 제어를 허용하세요.", "권한을 켠 뒤 같은 요청을 한 번 다시 보내세요.", os_error=number)
        if number in (-1719, -1728, -1700):
            raise Failure("TARGET_MISSING", "대상 창 또는 탭이 없습니다: " + err[-160:], "status 로 창·탭을 다시 조회해 고르세요.", os_error=number)
        raise Failure("APPLESCRIPT_ERROR", err[-300:] or "AppleScript 실패", "status 로 현재 상태를 조회하세요.", os_error=number)
    return proc.stdout.strip()


def _parse_list(text):
    """`-s s` 출력의 AppleScript 리스트/문자열/정수 → Python. 사전 호출 결과만 받으므로 모양이 제한적이다."""
    text = text.strip()
    if not text:
        return None
    out, i = [], 0

    def value(pos):
        if text[pos] == "{":
            items, pos = [], pos + 1
            while True:
                while text[pos] == " ":
                    pos += 1
                if text[pos] == "}":
                    return items, pos + 1
                item, pos = value(pos)
                items.append(item)
                while text[pos] == " ":
                    pos += 1
                if text[pos] == ",":
                    pos += 1
        if text[pos] == '"':
            end, buf = pos + 1, []
            while text[end] != '"':
                if text[end] == "\\":
                    end += 1
                buf.append(text[end])
                end += 1
            return "".join(buf), end + 1
        m = re.match(r"-?\d+(\.\d+)?|missing value|true|false", text[pos:])
        if not m:
            raise Failure("APPLESCRIPT_ERROR", "응답을 해석하지 못했습니다: " + text[:120], "status 로 다시 조회하세요.")
        tok = m.group(0)
        val = None if tok == "missing value" else tok == "true" if tok in ("true", "false") else (float(tok) if "." in tok else int(tok))
        return val, pos + len(tok)

    result, _ = value(0)
    return result


def is_running():
    return _parse_list(apple_event(f'application "{APP}" is running', timeout=5)) is True


def windows():
    """[{window_id, name, current_tab, tab_count, tabs:[{index,url,name}]}] — 창 순서는 Safari 의 앞→뒤."""
    # `count of tabs of every window` 는 창별 목록이 아니라 합계 하나를 돌려준다(실측) — 탭 수는 탭 목록에서 센다.
    raw = _parse_list(apple_event(f'tell application "{APP}" to get {{id, name, index of current tab}} of every window'))
    if not raw or raw == [[], [], []]:
        return []
    ids, names, currents = (col if isinstance(col, list) else [col] for col in raw)
    out = []
    for wid, name, current in zip(ids, names, currents):
        try:
            t = _parse_list(apple_event(f'tell application "{APP}" to tell window id {int(wid)} to get {{index, URL, name}} of every tab'))
        except Failure as exc:
            if exc.code == "TARGET_MISSING":
                continue   # 창 목록과 탭 조회 사이에 창이 사라졌다(마지막 탭 닫기 직후 실측 -1728) — 없는 창으로 본다
            raise
        idx, urls, titles = (col if isinstance(col, list) else [col] for col in (t or [[], [], []]))
        tabs = [{"index": int(i), "url": u if isinstance(u, str) else None, "name": n if isinstance(n, str) else None}
                for i, u, n in zip(idx, urls, titles)]
        out.append({"window_id": int(wid), "name": name if isinstance(name, str) else None,
                    "current_tab": int(current) if isinstance(current, int) else None, "tab_count": len(tabs), "tabs": tabs})
    return out


# ---------------------------------------------------------------- 검증·실행 전 검사

def validate(args):
    if not isinstance(args, dict):
        raise Failure("INVALID_ARGUMENT", "인수는 객체여야 합니다.")
    op = args.get("op", "status")
    if op == "contract":
        return {"op": op}
    spec = CONTRACT["actions"].get(op)
    if spec is None:
        raise Failure("INVALID_ARGUMENT", f"지원하지 않는 동작입니다: {op}. 사용 가능: {sorted(CONTRACT['actions'])}")
    allowed = {"op", *spec["params"], *spec["optional"]}
    if set(args) - allowed:
        raise Failure("INVALID_ARGUMENT", f"이 동작이 받지 않는 인수가 있습니다: {sorted(set(args) - allowed)}")
    for key in spec["params"]:
        if key not in args:
            raise Failure("INVALID_ARGUMENT", f"{key}가 필요합니다.")
    out = {"op": op}
    if "url" in args:
        url = args["url"]
        if not isinstance(url, str) or len(url) > 4096 or any(ord(c) < 32 for c in url):
            raise Failure("INVALID_ARGUMENT", "올바른 웹 주소를 입력해 주세요.")
        parsed = urlsplit(url)
        if url != "about:blank" and (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password):
            raise Failure("INVALID_ARGUMENT", "인증정보가 없는 http 또는 https 주소(또는 about:blank)만 열 수 있습니다.")
        out["url"] = url
    if "window_id" in args and args["window_id"] is not None:
        if type(args["window_id"]) is not int or args["window_id"] <= 0:
            raise Failure("INVALID_ARGUMENT", "window_id 는 status 가 돌려준 양의 정수입니다.")
        out["window_id"] = args["window_id"]
    if "tab" in args:
        if type(args["tab"]) is not int or args["tab"] <= 0:
            raise Failure("INVALID_ARGUMENT", "tab 은 1부터 세는 탭 번호입니다(status 의 index).")
        out["tab"] = args["tab"]
    if "launch" in args:
        if type(args["launch"]) is not bool:
            raise Failure("INVALID_ARGUMENT", "launch 는 true 또는 false 입니다.")
        out["launch"] = args["launch"]
    return out


def precheck(request):
    """실행 전 검사(§6) — OS·대상 실행 여부. 권한은 첫 사전 호출이 판정한다(-1743)."""
    if sys.platform != "darwin":
        raise Failure("UNSUPPORTED_PLATFORM", "Safari 제어는 macOS 본체에서만 동작합니다.", "원격 맥이면 해당 PC 의 드라이버를 쓰세요.")
    running = is_running()
    if running or request["op"] == "status":
        return running
    if request["op"] == "open" and request.get("launch"):
        subprocess.run(["open", "-gja", APP], capture_output=True, timeout=10)
        for _ in range(40):
            if is_running():
                return True
            time.sleep(0.25)
        raise Failure("TARGET_MISSING", "Safari 를 배경으로 띄웠지만 실행 확인이 되지 않았습니다.", "status 로 다시 확인하세요.")
    raise Failure("TARGET_MISSING", "Safari 가 실행 중이 아닙니다.", "사용자에게 확인하거나 open 에 launch:true 를 지정해 배경으로 띄우세요.")


# ---------------------------------------------------------------- 동작

def _find(wins, window_id):
    if window_id is None:
        if not wins:
            return None
        return wins[0]
    for w in wins:
        if w["window_id"] == window_id:
            return w
    raise Failure("TARGET_MISSING", f"창 {window_id} 이 없습니다.", "status 의 window_id 를 쓰세요.")


def _result(request, **fields):
    base = {"success": True, "op": request["op"], "surface": SURFACE, "verified": False,
            "verification_scope": CONTRACT["actions"][request["op"]]["verification_scope"],
            "condition": {k: CONTRACT["actions"][request["op"]][k] for k in ("needs_front", "shared_state", "isolated_resources")},
            "observed_at": now()}
    base.update(fields)
    return _failure_evidence(base)


def _failure_evidence(result):
    """문장과 구조화 복구 정보를 registered-json/1 → IBL 실패 경계까지 보존한다."""
    failure = result.get("failure")
    if result.get("success") is False and isinstance(failure, dict):
        code = failure["code"]
        result["error_code"] = code
        result["error"] = f"{code}: {failure['message']}" + (
            f" 다음: {failure['next']}" if failure.get("next") else "")
        if code == "UNKNOWN":
            result["error_type"] = "result_unknown"
        elif code == "PERMISSION_REQUIRED":
            result["error_type"] = "permission"
        result["recovery"] = {
            "status": result.get("status", "failed"),
            "next": failure.get("next"),
            "retry_change": False,
            "observe": {"op": "status"},
        }
    return result


def do_status(request, running):
    wins = windows() if running else []
    return _result(request, verified=True, running=running, windows=wins,
                   window_count=len(wins), frontmost_changed=False)


def do_open(request, running):
    before = windows()
    target = _find(before, request.get("window_id"))
    url_osa = json.dumps(request["url"])
    try:
        if target is None:
            apple_event(f'tell application "{APP}" to make new document with properties {{URL:{url_osa}}}', timeout=15)
        else:
            apple_event(f'tell application "{APP}" to tell window id {target["window_id"]} to make new tab at end of tabs with properties {{URL:{url_osa}}}', timeout=15)
        lost = False
    except subprocess.TimeoutExpired:
        lost = True
    after = windows()
    if target is None:
        new = [w for w in after if w["window_id"] not in {w0["window_id"] for w0 in before}]
        created = next((w for w in new if any((t["url"] or "") == request["url"] for t in w["tabs"])), None)
        if created is None:
            if lost:
                return _unknown(request, "새 창 만들기 응답이 유실됐고 재조회에서 요청 주소의 창을 찾지 못했습니다.", windows=after)
            return _result(request, success=False, verified=False, windows=after,
                           failure={"code": "APPLESCRIPT_ERROR", "message": "새 창을 만들었다는 응답 뒤 재조회에서 창을 찾지 못했습니다.", "next": "status 로 확인하세요."})
        tab = next(t for t in created["tabs"] if (t["url"] or "") == request["url"])
        return _result(request, verified=True, window_created=True, window_id=created["window_id"], tab=tab["index"],
                       current_tab=created["current_tab"], response_lost=lost, windows=after,
                       note="창이 없어 새 창을 만들었다. 사용자 화면에 창 하나가 추가됐다(앞으로 가져오지는 않음).")
    now_target = _find(after, target["window_id"])
    before_idx = {t["index"] for t in target["tabs"]}
    added = [t for t in now_target["tabs"] if t["index"] not in before_idx and (t["url"] or "") == request["url"]]
    if not added:
        if lost:
            return _unknown(request, "탭 만들기 응답이 유실됐고 재조회에서 새 탭을 찾지 못했습니다.", windows=after)
        return _result(request, success=False, verified=False, windows=after,
                       failure={"code": "APPLESCRIPT_ERROR", "message": "탭을 만들었다는 응답 뒤 재조회에서 탭을 찾지 못했습니다.", "next": "status 로 확인하세요."})
    return _result(request, verified=True, window_created=False, window_id=now_target["window_id"], tab=added[-1]["index"],
                   current_tab=now_target["current_tab"], current_tab_unchanged=now_target["current_tab"] == target["current_tab"],
                   response_lost=lost, windows=after)


def do_switch(request, running):
    before = windows()
    target = _find(before, request["window_id"])
    if request["tab"] > target["tab_count"]:
        raise Failure("TARGET_MISSING", f"창 {target['window_id']} 에 탭 {request['tab']} 이 없습니다(탭 {target['tab_count']}개).", "status 로 탭을 다시 고르세요.")
    try:
        apple_event(f'tell application "{APP}" to tell window id {target["window_id"]} to set current tab to tab {request["tab"]}')
        lost = False
    except subprocess.TimeoutExpired:
        lost = True
    after = _find(windows(), target["window_id"])
    if after["current_tab"] == request["tab"]:
        return _result(request, verified=True, window_id=after["window_id"], current_tab=after["current_tab"],
                       previous_tab=target["current_tab"], response_lost=lost)
    if lost:
        return _unknown(request, "탭 전환 응답이 유실됐고 재조회의 현재 탭이 요청과 다릅니다.", current_tab=after["current_tab"])
    return _result(request, success=False, verified=False, current_tab=after["current_tab"],
                   failure={"code": "NOT_APPLIED", "message": "전환 요청 뒤 현재 탭이 요청과 다릅니다.", "next": "사용자가 동시에 탭을 바꿨을 수 있습니다. status 로 확인하고 필요하면 다시 요청하세요."})


def do_close(request, running):
    before = windows()
    target = _find(before, request["window_id"])
    victim = next((t for t in target["tabs"] if t["index"] == request["tab"]), None)
    if victim is None:
        raise Failure("TARGET_MISSING", f"창 {target['window_id']} 에 탭 {request['tab']} 이 없습니다.", "status 로 탭을 다시 고르세요.")
    try:
        apple_event(f'tell application "{APP}" to tell window id {target["window_id"]} to close tab {request["tab"]}')
        lost = False
    except subprocess.TimeoutExpired:
        lost = True
    after_all = windows()
    after = next((w for w in after_all if w["window_id"] == target["window_id"]), None)
    window_closed = after is None
    # index 는 닫은 뒤 재번호된다. 남은 탭의 순서를 비교해야 동일 URL·제목의
    # 이웃 탭이 닫힌 탭의 번호를 물려받아도 정상 완료로 판정할 수 있다.
    expected = [(t["url"], t["name"]) for t in target["tabs"] if t["index"] != victim["index"]]
    gone = window_closed or (
        after["tab_count"] == target["tab_count"] - 1
        and [(t["url"], t["name"]) for t in after["tabs"]] == expected)
    if gone:
        return _result(request, verified=True, window_id=target["window_id"], closed_tab=victim, window_closed=window_closed,
                       tab_count=0 if window_closed else after["tab_count"], response_lost=lost)
    if lost:
        return _unknown(request, "탭 닫기 응답이 유실됐고 재조회한 남은 탭 상태가 요청과 다릅니다.", tab_count=after["tab_count"])
    return _result(request, success=False, verified=False, tab_count=after["tab_count"],
                   failure={"code": "NOT_APPLIED", "message": "닫기 요청 뒤 남은 탭 상태가 요청과 다릅니다.", "next": "status 로 확인하세요. 같은 닫기를 자동 반복하지 마세요."})


def _unknown(request, message, **fields):
    return _result(request, success=False, verified=False, status="unknown",
                   failure={"code": "UNKNOWN", "message": message,
                            "next": "변경을 재전송하지 말고 status 로 현재 상태를 조회해 판별하세요. 판별이 안 되면 unknown 으로 보고합니다."}, **fields)


def run(args):
    request = validate(args)
    if request["op"] == "contract":
        return {"success": True, **CONTRACT, "host_platform": sys.platform}
    running = precheck(request)
    return {"status": do_status, "open": do_open, "switch": do_switch, "close": do_close}[request["op"]](request, running)


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
        wire = isinstance(payload, dict) and payload.get("protocol") == "ibl-script/2"
        result = run(payload.get("args", {}) if wire else payload)
    except Failure as exc:
        # 실행기 어댑터는 success:false 의 error 문자열만 호출자에게 전한다(실측) — 코드와 다음 걸음을 문장에 싣는다.
        result = {"success": False, "verified": False, "surface": SURFACE,
                  "error": f"{exc.code}: {exc}" + (f" 다음: {exc.next_step}" if exc.next_step else ""),
                  "failure": {"code": exc.code, "message": str(exc), "next": exc.next_step, **exc.extra}}
    except subprocess.TimeoutExpired:
        result = {"success": False, "verified": False, "surface": SURFACE, "status": "unknown",
                  "error": "UNKNOWN: Safari 가 응답하지 않습니다. 실행 여부를 판별하지 못했습니다. 다음: 변경을 재전송하지 말고 status 로 조회하세요.",
                  "failure": {"code": "UNKNOWN", "message": "Safari 응답 시간 초과", "next": "변경을 재전송하지 말고 status 로 조회하세요."}}
    except Exception as exc:  # noqa: BLE001 — 스크립트 경계: 원인은 보존하고 전송 세부는 노출하지 않는다
        result = {"success": False, "verified": False, "surface": SURFACE, "error": f"{type(exc).__name__}: {exc}"[:300],
                  "failure": {"code": "SCRIPT_ERROR", "message": str(exc)[:300], "next": "status 로 현재 상태를 조회하세요."}}
    text = json.dumps(_failure_evidence(result), ensure_ascii=False, allow_nan=False)
    if dest := os.environ.get("INDIEBIZ_SCRIPT_RESULT"):
        Path(dest + ".tmp").write_text(text, encoding="utf-8")
        os.replace(dest + ".tmp", dest)
    else:
        print(text)
