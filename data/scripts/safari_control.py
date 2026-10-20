"""Safari 창·탭 드라이버 — 본체 앱 조작면 `app:com.apple.Safari` 의 고정 실행 부품.

CONTROL_DRIVER_DESIGN_2026_10_20 §13 걸음 3 의 시범. 46~48회차 긴 문장 훈련에서 화면 조작(좌표·ref)으로
더듬다 생긴 발견 — 탭 전환 불가(L46-1), 새 탭 뒤 활성 탭 조용히 전환(L48-1) — 은 "Safari 에게 현재 탭을
바꿔라" 하고 말하는 계약 통로에서는 애초에 생기지 않는다. 이 부품은 그 통로다.

stdin: {op: contract/status/open/switch/close, url, window_id, tab, expected, launch}
- 어느 탭을 열고 닫을지는 AI 가 정한다. 여기는 기계적 부분(AppleScript 사전 호출·재조회)만 얼린다.
- 동작마다 실행 조건(needs_front·shared_state·isolated_resources)을 CONTRACT 에 적고, 실행 직전 검사가
  OS·실행 중 여부·권한을 확인한다. 어떤 동작도 Safari 를 앞으로 가져오지(activate) 않는다.
- 결과는 그림이 아니라 상태값이다. `verified` 는 변경 뒤 AppleScript 재조회(`applescript_tab_readback`)를
  통과했다는 보고이며 화면에 실제로 그려졌는지는 범위 밖이다.
- 시간 초과·응답 유실은 실패가 아니라 불명확이다. 변경을 재전송하지 않고 **변경 없이** 재조회해 판별하고,
  판별이 안 되면 `unknown` 을 유지한다(실측: 숨은 Safari 의 첫 창 만들기는 효과가 즉시 나고 응답은 20초 넘게 늦었다).
stdlib 만 쓴다. 등록: data/scripts/registry.yaml `Safari제어`, 가이드 safari_control.md.
"""
import hashlib
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
DEADLINE = None
CONTRACT = {
    "version": 2,
    "surface": SURFACE,
    "supported_platforms": ["darwin"],
    "verification_scope": {
        READBACK: "변경 뒤 Safari 사전으로 창·탭 상태를 재조회해 요청과 대조했다. 화면 표시·페이지 로드 완료는 범위 밖.",
        "applescript_readback": "현재 창·탭 상태 조회. 변경 없음.",
    },
    "actions": {
        "status": {"params": [], "optional": ["window_id"], "needs_front": False, "shared_state": False,
                   "isolated_resources": [], "verification_scope": "applescript_readback",
                   "effect": "창·탭 목록과 현재 탭. 변경 없음"},
        "open": {"params": ["url"], "optional": ["window_id", "launch", "expected"], "needs_front": False, "shared_state": False,
                 "isolated_resources": [], "verification_scope": READBACK,
                 "effect": "지정 창(기본 첫 창)의 끝에 배경 탭을 만든다. 현재 탭은 바뀌지 않는다. 창이 없으면 새 창이 생기며(window_created) 그때는 사용자 화면에 창 하나가 추가된다. Safari 가 꺼져 있으면 launch:true 일 때만 배경으로 띄운다"},
        "switch": {"params": ["window_id", "tab", "expected"], "optional": [], "needs_front": False, "shared_state": True,
                   "isolated_resources": [], "verification_scope": READBACK,
                   "effect": "그 창의 현재 탭을 바꾼다 — 사용자가 보는 탭이 바뀌는 요청된 효과. Safari 를 앞으로 가져오지 않는다"},
        "close": {"params": ["window_id", "tab", "expected"], "optional": [], "needs_front": False, "shared_state": True,
                  "isolated_resources": [], "verification_scope": READBACK,
                  "effect": "그 창의 탭 하나를 닫는다. 마지막 탭이면 창이 닫힌다"},
    },
    "failure_codes": {
        "UNSUPPORTED_PLATFORM": "darwin 이 아닌 본체", "TARGET_MISSING": "Safari 미실행·창·탭 없음(-1719/-1728)",
        "PERMISSION_REQUIRED": "자동화(Apple Events) 권한 미허용(-1743)", "INVALID_ARGUMENT": "인수 검증 실패",
        "UNKNOWN": "응답 유실·시간 초과 뒤 재조회로도 실행 여부를 판별하지 못함",
        "STATE_CHANGED": "관측한 창 상태와 달라 변경 전에 중단. 새 상태로 대상을 다시 선택",
        "POSTCONDITION_FAILED": "변경을 요청했으나 보존 조건이나 요청 결과를 확인하지 못함. 자동 재전송 금지",
    },
    "target_contract": "switch/close는 status 또는 직전 결과 state.revision을 expected로 전달한다. "
                       "창 ID·현재 탭·URL 순서를 대조하며 제목은 판본에서 제외한다. "
                       "동일 URL 탭의 개체 신원과 관측 사이의 변경 후 원상 복귀는 판별하지 못한다.",
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
    if DEADLINE is not None:
        timeout = min(timeout, DEADLINE - time.monotonic())
        if timeout <= 0:
            raise subprocess.TimeoutExpired("Safari operation deadline", 50)
    proc = subprocess.run(["osascript", "-s", "s", "-e", script], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        err = proc.stderr.strip()
        code = re.search(r"\((-\d+)\)\s*$", err)
        number = int(code.group(1)) if code else None
        if number == -27001:
            raise Failure("STATE_CHANGED", "실행 직전 Safari 창 상태가 바뀌었습니다.", "status 로 다시 조회해 대상을 선택하세요.")
        if number == -1712:
            raise subprocess.TimeoutExpired("Safari Apple Event", timeout)
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


def osa(value):
    """AppleScript literals, including Unicode URLs (JSON Unicode escape is not AppleScript)."""
    if value is None:
        return "missing value"
    if isinstance(value, list):
        return "{" + ", ".join(osa(v) for v in value) + "}"
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return str(value)


def revision(window):
    payload = [window["window_id"], window["current_tab"], [t["url"] for t in window["tabs"]]]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()


def windows(window_id=None):
    """One script process for the requested window, or all windows; getters stay inside it."""
    selection = "every window" if window_id is None else f"{{window id {int(window_id)}}}"
    script = f'''-- safari_snapshot_v2
set rows to {{}}
tell application "{APP}"
    try
        set selectedWindows to {selection}
    on error number -1728
        return rows
    end try
    repeat with w in selectedWindows
        try
            set end of rows to {{id of w, name of w, index of current tab of w, {{index, URL, name}} of every tab of w}}
        on error number -1728
            -- A window disappeared while reading it. Never synthesize an empty window.
        end try
    end repeat
end tell
return rows'''
    raw = _parse_list(apple_event(script))
    if not isinstance(raw, list):
        raise Failure("APPLESCRIPT_ERROR", "Safari 창 목록 응답 형식이 올바르지 않습니다.")
    out = []
    for row in raw:
        if not isinstance(row, list) or len(row) != 4:
            raise Failure("APPLESCRIPT_ERROR", "Safari 창 응답 형식이 올바르지 않습니다.")
        wid, name, current, columns = row
        if not isinstance(columns, list) or len(columns) != 3:
            raise Failure("APPLESCRIPT_ERROR", "Safari 탭 응답 형식이 올바르지 않습니다.")
        idx, urls, titles = (col if isinstance(col, list) else [col] for col in columns)
        if len(idx) != len(urls) or len(idx) != len(titles):
            raise Failure("APPLESCRIPT_ERROR", "Safari 탭 관측이 불완전합니다.")
        tabs = [{"index": int(i), "url": u if isinstance(u, str) else None,
                 "name": n if isinstance(n, str) else None} for i, u, n in zip(idx, urls, titles)]
        if [t["index"] for t in tabs] != list(range(1, len(tabs) + 1)):
            raise Failure("APPLESCRIPT_ERROR", "Safari 탭 번호 관측이 일관되지 않습니다.")
        if tabs and (type(current) is not int or not 1 <= current <= len(tabs)):
            raise Failure("APPLESCRIPT_ERROR", "Safari 현재 탭 관측이 일관되지 않습니다.")
        item = {"window_id": int(wid), "name": name if isinstance(name, str) else None,
                "current_tab": int(current) if type(current) is int else None,
                "tab_count": len(tabs), "tabs": tabs}
        item["revision"] = revision(item)
        out.append(item)
    return out


# ---------------------------------------------------------------- 검증·실행 전 검사

def validate(args):
    if not isinstance(args, dict):
        raise Failure("INVALID_ARGUMENT", "인수는 객체여야 합니다.")
    op = args.get("op", "status")
    if op == "contract":
        if set(args) != {"op"}:
            raise Failure("INVALID_ARGUMENT", "contract 는 추가 인수를 받지 않습니다.")
        return {"op": op}
    if not isinstance(op, str):
        raise Failure("INVALID_ARGUMENT", "op 는 문자열이어야 합니다.")
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
    if "window_id" in args:
        if type(args["window_id"]) is not int or args["window_id"] <= 0:
            raise Failure("INVALID_ARGUMENT", "window_id 는 status 가 돌려준 양의 정수입니다.")
        out["window_id"] = args["window_id"]
    if "tab" in args:
        if type(args["tab"]) is not int or args["tab"] <= 0:
            raise Failure("INVALID_ARGUMENT", "tab 은 1부터 세는 탭 번호입니다(status 의 index).")
        out["tab"] = args["tab"]
    if "expected" in args:
        if not isinstance(args["expected"], str) or not re.fullmatch(r"[0-9a-f]{64}", args["expected"]):
            raise Failure("INVALID_ARGUMENT", "expected 는 관측 결과 state.revision 또는 windows[].revision 입니다.")
        if "window_id" not in out:
            raise Failure("INVALID_ARGUMENT", "expected 와 함께 window_id 가 필요합니다.")
        out["expected"] = args["expected"]
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
    if "window_id" in request:
        base["window_id"] = request["window_id"]
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
        if result.get("window_id"):
            result["recovery"]["observe"]["window_id"] = result["window_id"]
    return result


def _target(window, tab=None):
    if window is None:
        return None
    index = window["current_tab"] if tab is None else tab
    if not any(t["index"] == index for t in window["tabs"]):
        return None
    return {"window_id": window["window_id"], "tab": index, "expected": window["revision"]}


def _state_fields(before, after, tab=None):
    return {"before": {k: before[k] for k in ("window_id", "current_tab", "tab_count", "revision")} if before else None,
            "state": after, "target": _target(after, tab), "page_loaded": None}


def _selected(request):
    before = windows(request.get("window_id"))
    target = _find(before, request.get("window_id"))
    if request.get("expected") and (target is None or request["expected"] != target["revision"]):
        raise Failure("STATE_CHANGED", "관측 이후 창의 탭 순서·주소·현재 탭이 바뀌었습니다.",
                      "새 상태에서 대상을 다시 선택하세요.", state=target)
    return before, target


def _guard(window):
    # Repeat the comparison in the mutation's AppleScript, narrowing the read/write gap.
    # Safari exposes positional tabs, not durable identities or transactional locks.
    urls = osa([t["url"] for t in window["tabs"]])
    return f'''set w to window id {window["window_id"]}
considering case
    if (URL of every tab of w) is not equal to {urls} then error "SAFARI_STATE_CHANGED" number -27001
end considering
if (index of current tab of w) is not equal to {window["current_tab"]} then error "SAFARI_STATE_CHANGED" number -27001'''


def _mutate(script, timeout=10):
    try:
        return apple_event(script, timeout=timeout), False
    except subprocess.TimeoutExpired:
        return None, True
    except Failure as exc:
        if exc.code in {"STATE_CHANGED", "PERMISSION_REQUIRED"}:
            raise
        # An Apple Event error can follow an applied effect. Reconcile without retransmitting.
        return None, True


def _after(request, window_id=None):
    try:
        return windows(window_id), None
    except Exception as exc:
        return None, _unknown(request, "변경 후 재조회에 실패했습니다.",
                              observation_error={"code": getattr(exc, "code", type(exc).__name__), "message": str(exc)[:200]})


def _postcondition(request, message, **fields):
    return _result(request, success=False, status="unconfirmed", verified=False,
                   failure={"code": "POSTCONDITION_FAILED", "message": message,
                            "next": "반환된 상태를 확인하세요. 같은 변경을 자동 재전송하지 마세요."}, **fields)


def do_status(request, running):
    wins = windows(request.get("window_id")) if running else []
    state = _find(wins, request["window_id"]) if request.get("window_id") else None
    return _result(request, verified=True, running=running, windows=wins,
                   window_count=len(wins), scope="window" if request.get("window_id") else "all",
                   **_state_fields(None, state))


def do_open(request, running):
    before, target = _selected(request)
    url_osa = osa(request["url"])
    if target is None:
        script = f'''tell application "{APP}"
if (count of windows) is not equal to 0 then error "SAFARI_STATE_CHANGED" number -27001
make new document with properties {{URL:{url_osa}}}
return {{id of front window, index of current tab of front window}}
end tell'''
    else:
        script = f'''tell application "{APP}"
{_guard(target)}
set createdTab to make new tab at end of tabs of w with properties {{URL:{url_osa}}}
return {{id of w, index of createdTab}}
end tell'''
    response, lost = _mutate(script, timeout=15)
    after, error = _after(request, target["window_id"] if target else None)
    if error:
        return error
    receipt = None
    if response:
        try:
            value = _parse_list(response)
            if isinstance(value, list) and len(value) == 2 and all(type(v) is int for v in value):
                receipt = tuple(value)
        except Exception:
            pass  # The effect may have happened; only readback can now prove it.
    if target is None:
        new = [w for w in after if w["window_id"] not in {w0["window_id"] for w0 in before}]
        created = new[0] if len(new) == 1 else None
        added = created["tabs"] if created and created["tab_count"] == 1 else []
        preserved = created is not None and len(added) == 1
    else:
        created = next((w for w in after if w["window_id"] == target["window_id"]), None)
        added = created["tabs"][target["tab_count"]:] if created else []
        preserved = (created is not None and created["tab_count"] == target["tab_count"] + 1
                     and [t["url"] for t in created["tabs"][:target["tab_count"]]] == [t["url"] for t in target["tabs"]]
                     and created["current_tab"] == target["current_tab"])
    tab = added[0] if len(added) == 1 else None
    receipt_matches = bool(created and tab and receipt == (created["window_id"], tab["index"]))
    url_matches = bool(tab and tab["url"] == request["url"])
    # A returned creation reference permits redirects. Lost response needs exact URL evidence.
    identified = receipt_matches or (receipt is None and url_matches)
    fields = {**_state_fields(target, created, tab["index"] if tab else None),
              "response_lost": lost, "requested_url": request["url"],
              "observed_url": tab["url"] if tab else None,
              "checks": {"created_tab_identified": identified, "existing_state_preserved": preserved,
                         "requested_url_observed": url_matches, "creation_receipt": receipt_matches},
              "window_created": target is None,
              "current_tab_unchanged": created["current_tab"] == target["current_tab"] if target and created else None}
    if preserved and identified:
        return _result(request, verified=True, window_id=created["window_id"], tab=tab["index"],
                       current_tab=created["current_tab"], **fields)
    if lost:
        return _unknown(request, "열기 응답이 유실됐고 탭 생성·기존 상태 보존을 확인하지 못했습니다.", **fields)
    return _postcondition(request, "탭 생성 또는 기존 탭·현재 탭 보존을 확인하지 못했습니다.", **fields)


def do_switch(request, running):
    _, target = _selected(request)
    if request["tab"] > target["tab_count"]:
        raise Failure("TARGET_MISSING", f"창 {target['window_id']} 에 탭 {request['tab']} 이 없습니다.", "status 로 다시 선택하세요.")
    if target["current_tab"] == request["tab"]:
        return _result(request, verified=True, changed=False, window_id=target["window_id"],
                       current_tab=target["current_tab"], previous_tab=target["current_tab"], response_lost=False,
                       checks={"current_tab_matches": True, "tab_order_preserved": True},
                       **_state_fields(target, target, request["tab"]))
    _, lost = _mutate(f'''tell application "{APP}"
{_guard(target)}
set current tab of w to tab {request["tab"]} of w
end tell''')
    wins, error = _after(request, target["window_id"])
    if error:
        return error
    after = next(iter(wins), None)
    same_tabs = bool(after and [t["url"] for t in after["tabs"]] == [t["url"] for t in target["tabs"]])
    matches = bool(after and after["current_tab"] == request["tab"])
    fields = {**_state_fields(target, after, request["tab"]), "window_id": target["window_id"],
              "previous_tab": target["current_tab"], "current_tab": after["current_tab"] if after else None,
              "response_lost": lost, "checks": {"current_tab_matches": matches, "tab_order_preserved": same_tabs}}
    if matches and same_tabs:
        return _result(request, verified=True, changed=True, **fields)
    if lost:
        return _unknown(request, "전환 응답이 유실됐고 재조회한 창·탭 상태가 요청과 다릅니다.", **fields)
    return _postcondition(request, "전환 뒤 요청 탭과 기존 탭 순서 보존을 확인하지 못했습니다.", **fields)


def do_close(request, running):
    _, target = _selected(request)
    victim = next((t for t in target["tabs"] if t["index"] == request["tab"]), None)
    if victim is None:
        raise Failure("TARGET_MISSING", f"창 {target['window_id']} 에 탭 {request['tab']} 이 없습니다.", "status 로 다시 선택하세요.")
    _, lost = _mutate(f'''tell application "{APP}"
{_guard(target)}
close tab {request["tab"]} of w
end tell''')
    wins, error = _after(request, target["window_id"])
    if error:
        return error
    after = next(iter(wins), None)
    expected = [t["url"] for t in target["tabs"] if t["index"] != victim["index"]]
    window_closed = after is None
    gone = ((window_closed and target["tab_count"] == 1) or
            (after is not None and after["tab_count"] == target["tab_count"] - 1
             and [t["url"] for t in after["tabs"]] == expected))
    fields = {**_state_fields(target, after), "window_id": target["window_id"], "closed_tab": victim,
              "window_closed": window_closed, "tab_count": after["tab_count"] if after else 0,
              "response_lost": lost, "checks": {"requested_removal_only": gone}}
    if gone:
        return _result(request, verified=True, **fields)
    if lost:
        return _unknown(request, "닫기 응답이 유실됐고 요청한 탭만 제거됐는지 확인하지 못했습니다.", **fields)
    return _postcondition(request, "닫기 뒤 남은 창·탭 상태가 요청과 다릅니다.", **fields)


def _unknown(request, message, **fields):
    return _result(request, success=False, verified=False, status="unknown",
                   failure={"code": "UNKNOWN", "message": message,
                            "next": "변경을 재전송하지 말고 status 로 현재 상태를 조회해 판별하세요. 판별이 안 되면 unknown 으로 보고합니다."}, **fields)


def run(args):
    global DEADLINE
    request = validate(args)
    if request["op"] == "contract":
        return {"success": True, **CONTRACT, "host_platform": sys.platform}
    DEADLINE = time.monotonic() + 50  # Leave time to emit UNKNOWN before the registered 60s timeout.
    try:
        running = precheck(request)
        return {"status": do_status, "open": do_open, "switch": do_switch, "close": do_close}[request["op"]](request, running)
    finally:
        DEADLINE = None


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
        wire = isinstance(payload, dict) and payload.get("protocol") == "ibl-script/2"
        result = run(payload.get("args", {}) if wire else payload)
    except Failure as exc:
        # 문장 오류와 구조화 실패·복구 증거를 함께 전달한다.
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
