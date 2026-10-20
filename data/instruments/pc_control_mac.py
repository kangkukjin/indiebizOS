"""macOS native PC controls. stdlib only; Core Audio binds explicit output UIDs."""
import ctypes as C
import json
import os
import platform
import re
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone


def fourcc(text):
    return int.from_bytes(text.encode("ascii"), "big")


class Address(C.Structure):
    _fields_ = [("selector", C.c_uint32), ("scope", C.c_uint32), ("element", C.c_uint32)]


class Audio:
    def __init__(self):
        self.lib = C.CDLL("/System/Library/Frameworks/CoreAudio.framework/CoreAudio")
        self.cf = C.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        self.lib.AudioObjectGetPropertyData.argtypes = [C.c_uint32, C.POINTER(Address), C.c_uint32, C.c_void_p, C.POINTER(C.c_uint32), C.c_void_p]
        self.lib.AudioObjectGetPropertyDataSize.argtypes = [C.c_uint32, C.POINTER(Address), C.c_uint32, C.c_void_p, C.POINTER(C.c_uint32)]
        self.lib.AudioObjectSetPropertyData.argtypes = [C.c_uint32, C.POINTER(Address), C.c_uint32, C.c_void_p, C.c_uint32, C.c_void_p]
        self.lib.AudioObjectIsPropertySettable.argtypes = [C.c_uint32, C.POINTER(Address), C.POINTER(C.c_ubyte)]
        self.cf.CFStringGetCString.argtypes = [C.c_void_p, C.c_char_p, C.c_long, C.c_uint32]
        self.cf.CFStringGetCString.restype = C.c_ubyte
        self.cf.CFRelease.argtypes = [C.c_void_p]

    def address(self, selector, scope="glob", element=0):
        return Address(fourcc(selector), fourcc(scope), element)

    def read(self, device, selector, value, scope="glob", element=0):
        address = self.address(selector, scope, element)
        size = C.c_uint32(C.sizeof(value))
        status = self.lib.AudioObjectGetPropertyData(device, C.byref(address), 0, None, C.byref(size), C.byref(value))
        if status:
            raise RuntimeError(f"Core Audio 조회 실패 ({selector}, {status})")
        return value

    def size(self, device, selector, scope="glob"):
        address = self.address(selector, scope)
        size = C.c_uint32()
        status = self.lib.AudioObjectGetPropertyDataSize(device, C.byref(address), 0, None, C.byref(size))
        return size.value if not status else 0

    def text(self, device, selector):
        value = self.read(device, selector, C.c_void_p())
        if not value.value:
            return ""
        try:
            buffer = C.create_string_buffer(4096)
            if not self.cf.CFStringGetCString(value, buffer, len(buffer), 0x08000100):
                raise RuntimeError("오디오 장치 이름을 읽지 못했습니다.")
            return buffer.value.decode("utf-8")
        finally:
            self.cf.CFRelease(value)

    def slots(self, device, selector, ctype):
        for elements in ([0], [1, 2]):
            found = []
            for element in elements:
                try:
                    value = self.read(device, selector, ctype(), "outp", element).value
                    address = self.address(selector, "outp", element)
                    writable = C.c_ubyte()
                    status = self.lib.AudioObjectIsPropertySettable(device, C.byref(address), C.byref(writable))
                    found.append((element, value, not status and bool(writable.value)))
                except RuntimeError:
                    pass
            if found:
                return found
        return []

    def describe(self, device, default):
        volume = self.slots(device, "volm", C.c_float)
        mute = self.slots(device, "mute", C.c_uint32)
        return {"id": self.text(device, "uid "), "name": self.text(device, "lnam"),
                "default": device == default,
                "volume": round(sum(v[1] for v in volume) / len(volume) * 100) if volume else None,
                "muted": all(bool(m[1]) for m in mute) if mute else None,
                "can_set_volume": bool(volume) and all(v[2] for v in volume),
                "can_mute": bool(mute) and all(m[2] for m in mute),
                "capability_basis": "coreaudio_property_settable",
                "volume_channels": len(volume)}

    def devices(self):
        default = self.read(1, "dOut", C.c_uint32()).value
        size = self.size(1, "dev#")
        values = self.read(1, "dev#", (C.c_uint32 * (size // 4))())
        rows = []
        for device in values:
            if self.size(device, "stm#", "outp"):
                rows.append((device, self.describe(device, default)))
        return rows

    def change(self, request):
        pairs = self.devices()
        selected = next(((native, row) for native, row in pairs if row["id"] == request["device_id"]), None)
        if selected is None:
            raise RuntimeError("출력 장치가 사라졌습니다. 상태를 다시 조회하세요.")
        device, before = selected
        selector, ctype = ("volm", C.c_float) if request["action"] == "volume" else ("mute", C.c_uint32)
        values = self.slots(device, selector, ctype)
        if not values or not all(v[2] for v in values):
            raise RuntimeError("이 출력 장치는 해당 값을 변경할 수 없습니다.")
        value = request["value"] / 100 if selector == "volm" else int(request["enabled"])
        for element, _, _ in values:
            if self.text(device, "uid ") != before["id"]:
                raise RuntimeError("출력 장치의 신원이 바뀌었습니다.")
            address = self.address(selector, "outp", element)
            data = ctype(value)
            status = self.lib.AudioObjectSetPropertyData(device, C.byref(address), 0, None, C.sizeof(data), C.byref(data))
            if status:
                raise RuntimeError(f"오디오 설정 실패 ({status}); 일부 채널에 적용됐을 수 있습니다.")
        rows = [row for _, row in self.devices()]
        actual = next((row for row in rows if row["id"] == before["id"]), None)
        if actual is None:
            raise RuntimeError("변경 뒤 장치가 사라졌습니다.")
        verified = (abs(actual["volume"] - request["value"]) <= 1 if selector == "volm"
                    else actual["muted"] is request["enabled"])
        if not verified:
            raise RuntimeError("장치가 반환한 값이 요청한 값과 다릅니다.")
        return {"devices": rows, "device": actual, "verified": True,
                "message": "출력 장치의 실제 설정값을 확인했습니다."}


# ---------------------------------------------------------------- 본체 OS 조작면 (2026-10-20 1층)
# 설계: docs/CONTROL_DRIVER_DESIGN_2026_10_20.md §17. 전부 배경 실행(needs_front 없음).
# 읽기는 OS 조회값을 그대로, 쓰기는 변경 뒤 같은 조회로 재확인한 것만 verified.

CF_UTF8 = 0x08000100
KEEP_AWAKE_FILE = os.path.join(tempfile.gettempdir(), "indiebiz_pc_control_keep_awake.json")


def sh(argv, timeout=10, input_text=None, ok_codes=(0,)):
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                          input=input_text, encoding="utf-8", errors="replace")
    if proc.returncode not in ok_codes:
        detail = (proc.stderr or proc.stdout).strip()[-400:]
        raise RuntimeError(f"{os.path.basename(argv[0])} 실패({proc.returncode}): {detail}")
    return proc.stdout


class Display:
    """CoreGraphics 공개 API 로 화면·세션을 읽는다. 밝기는 비공개 프레임워크라 없으면 null."""

    def __init__(self):
        self.cg = C.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        self.cf = C.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        self.cg.CGMainDisplayID.restype = C.c_uint32
        self.cg.CGGetOnlineDisplayList.argtypes = [C.c_uint32, C.POINTER(C.c_uint32), C.POINTER(C.c_uint32)]
        for name in ("CGDisplayIsAsleep", "CGDisplayIsActive", "CGDisplayIsBuiltin", "CGDisplayIsMain"):
            getattr(self.cg, name).argtypes = [C.c_uint32]
            getattr(self.cg, name).restype = C.c_bool
        for name in ("CGDisplayPixelsWide", "CGDisplayPixelsHigh"):
            getattr(self.cg, name).argtypes = [C.c_uint32]
            getattr(self.cg, name).restype = C.c_size_t
        self.cg.CGSessionCopyCurrentDictionary.restype = C.c_void_p
        cf = self.cf
        cf.CFStringCreateWithCString.restype = C.c_void_p
        cf.CFStringCreateWithCString.argtypes = [C.c_void_p, C.c_char_p, C.c_uint32]
        cf.CFDictionaryGetValue.restype = C.c_void_p
        cf.CFDictionaryGetValue.argtypes = [C.c_void_p, C.c_void_p]
        cf.CFBooleanGetValue.restype = C.c_bool
        cf.CFBooleanGetValue.argtypes = [C.c_void_p]
        cf.CFGetTypeID.restype = C.c_ulong
        cf.CFGetTypeID.argtypes = [C.c_void_p]
        cf.CFBooleanGetTypeID.restype = C.c_ulong
        cf.CFNumberGetTypeID.restype = C.c_ulong
        cf.CFNumberGetValue.restype = C.c_bool
        cf.CFNumberGetValue.argtypes = [C.c_void_p, C.c_int, C.c_void_p]
        cf.CFRelease.argtypes = [C.c_void_p]
        self.ds = None
        try:
            ds = C.CDLL("/System/Library/PrivateFrameworks/DisplayServices.framework/DisplayServices")
            ds.DisplayServicesGetBrightness.argtypes = [C.c_uint32, C.POINTER(C.c_float)]
            ds.DisplayServicesGetBrightness.restype = C.c_int
            ds.DisplayServicesSetBrightness.argtypes = [C.c_uint32, C.c_float]
            ds.DisplayServicesSetBrightness.restype = C.c_int
            ds.DisplayServicesCanChangeBrightness.argtypes = [C.c_uint32]
            ds.DisplayServicesCanChangeBrightness.restype = C.c_bool
            self.ds = ds
        except (OSError, AttributeError):
            self.ds = None

    def ids(self):
        buf = (C.c_uint32 * 32)()
        count = C.c_uint32()
        if self.cg.CGGetOnlineDisplayList(32, buf, C.byref(count)):
            raise RuntimeError("화면 목록을 읽지 못했습니다.")
        return [int(buf[i]) for i in range(count.value)]

    def brightness(self, display_id):
        if self.ds is None:
            return None, False
        can = bool(self.ds.DisplayServicesCanChangeBrightness(display_id))
        value = C.c_float()
        status = self.ds.DisplayServicesGetBrightness(display_id, C.byref(value))
        return (round(value.value * 100) if status == 0 else None), can

    def describe(self, display_id):
        cg = self.cg
        level, can = self.brightness(display_id)
        return {"id": display_id, "main": bool(cg.CGDisplayIsMain(display_id)),
                "builtin": bool(cg.CGDisplayIsBuiltin(display_id)), "active": bool(cg.CGDisplayIsActive(display_id)),
                "asleep": bool(cg.CGDisplayIsAsleep(display_id)),
                "width": int(cg.CGDisplayPixelsWide(display_id)), "height": int(cg.CGDisplayPixelsHigh(display_id)),
                "brightness": level, "can_set_brightness": can,
                "brightness_basis": "displayservices_private_framework" if self.ds is not None else "unavailable"}

    def displays(self):
        return [self.describe(d) for d in self.ids()]

    def session(self):
        """로그인 세션 사전. 잠금 키는 잠겼을 때만 존재한다(없음 = 잠기지 않음)."""
        cf = self.cf
        ref = self.cg.CGSessionCopyCurrentDictionary()
        if not ref:
            return {"screen_locked": None, "on_console": None, "session_basis": "cg_session_dictionary_unavailable"}
        out = {"screen_locked": False, "on_console": None, "session_basis": "cg_session_dictionary"}
        try:
            for key, field in (("CGSSessionScreenIsLocked", "screen_locked"), ("kCGSSessionOnConsoleKey", "on_console")):
                k = cf.CFStringCreateWithCString(None, key.encode(), CF_UTF8)
                try:
                    v = cf.CFDictionaryGetValue(ref, k)
                    if v:
                        t = cf.CFGetTypeID(v)
                        if t == cf.CFBooleanGetTypeID():
                            out[field] = bool(cf.CFBooleanGetValue(v))
                        elif t == cf.CFNumberGetTypeID():
                            num = C.c_longlong()
                            cf.CFNumberGetValue(v, 4, C.byref(num))
                            out[field] = bool(num.value)
                finally:
                    cf.CFRelease(k)
        finally:
            cf.CFRelease(ref)
        return out

    def set_brightness(self, request):
        target = request.get("display_id")
        ids = self.ids()
        display_id = int(target) if target is not None else self.cg.CGMainDisplayID()
        if display_id not in ids:
            raise RuntimeError("지정한 화면이 없습니다. display 로 목록을 조회하세요.")
        if self.ds is None:
            raise RuntimeError("이 macOS 에서 밝기 제어 프레임워크를 열지 못했습니다.")
        if not self.ds.DisplayServicesCanChangeBrightness(display_id):
            raise RuntimeError("이 화면은 밝기 변경을 지원하지 않습니다(외부 모니터 등). display 의 can_set_brightness 를 보세요.")
        status = self.ds.DisplayServicesSetBrightness(display_id, request["value"] / 100)
        if status:
            raise RuntimeError(f"밝기 설정 실패({status})")
        after = self.describe(display_id)
        if after["brightness"] is None or abs(after["brightness"] - request["value"]) > 2:
            raise RuntimeError("변경 뒤 읽은 밝기가 요청과 다릅니다.")
        return {"display": after, "verified": True, "message": "화면 밝기를 바꾸고 재조회로 확인했습니다."}


def parse_idle_seconds(text):
    m = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', text)
    return round(int(m.group(1)) / 1e9, 1) if m else None


def idle_seconds():
    return parse_idle_seconds(sh(["/usr/sbin/ioreg", "-c", "IOHIDSystem", "-d", "4", "-r", "-k", "HIDIdleTime"]))


def parse_clamshell(text):
    m = re.search(r'"AppleClamshellState"\s*=\s*(Yes|No)', text)
    return None if not m else m.group(1) == "Yes"


def lid_closed():
    return parse_clamshell(sh(["/usr/sbin/ioreg", "-r", "-k", "AppleClamshellState", "-d", "4"]))


def parse_battery(text):
    """pmset -g batt → 전원 출처와 배터리(없으면 null)."""
    source = re.search(r"Now drawing from '([^']+)'", text)
    battery = None
    m = re.search(r"(\d+)%;\s*([^;]+);\s*([^\n]+)", text)
    if m:
        battery = {"percent": int(m.group(1)), "state": m.group(2).strip(), "remaining": m.group(3).strip()}
    return {"power_source": source.group(1) if source else None, "battery": battery}


def parse_assertions(text):
    """pmset -g assertions → 시스템 전체 플래그와 잠 못 들게 하는 프로세스."""
    flags = {}
    for key in ("UserIsActive", "PreventUserIdleDisplaySleep", "PreventUserIdleSystemSleep", "PreventSystemSleep"):
        m = re.search(r"^\s*" + key + r"\s+(\d+)\s*$", text, re.M)
        flags[key] = int(m.group(1)) if m else None
    holders = []
    for m in re.finditer(r"^\s*pid (\d+)\(([^)]*)\):\s*\[[^\]]+\]\s*\S+\s+(PreventUserIdle(?:Display|System)Sleep|PreventSystemSleep|NoIdleSleepAssertion|NoDisplaySleepAssertion)\s+named:\s*\"([^\"]*)\"", text, re.M):
        holders.append({"pid": int(m.group(1)), "process": m.group(2), "kind": m.group(3), "name": m.group(4)})
    return {"flags": flags, "sleep_holders": holders}


def keep_awake_record():
    try:
        with open(KEEP_AWAKE_FILE, encoding="utf-8") as fh:
            rec = json.load(fh)
    except (OSError, ValueError):
        return None
    pid = rec.get("pid")
    try:
        os.kill(int(pid), 0)
        alive = True
    except (OSError, TypeError, ValueError):
        alive = False
    return {**rec, "alive": alive}


def power_status():
    out = parse_battery(sh(["/usr/bin/pmset", "-g", "batt"]))
    out.update(parse_assertions(sh(["/usr/bin/pmset", "-g", "assertions"])))
    out["lid_closed"] = lid_closed()
    out["keep_awake"] = keep_awake_record()
    return out


def keep_awake(request):
    current = keep_awake_record()
    if current and current["alive"]:
        raise RuntimeError(f"이미 잠들지 않기가 켜져 있습니다(pid {current['pid']}, until {current.get('until')}). 먼저 allow_sleep 하세요.")
    argv = ["/usr/bin/caffeinate", "-i"] + (["-d"] if request.get("display") else []) + ["-t", str(request["seconds"])]
    proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    until = datetime.now(timezone.utc).timestamp() + request["seconds"]
    rec = {"pid": proc.pid, "seconds": request["seconds"], "display": bool(request.get("display")),
           "started_at": datetime.now(timezone.utc).isoformat(), "until": datetime.fromtimestamp(until, timezone.utc).isoformat()}
    with open(KEEP_AWAKE_FILE, "w", encoding="utf-8") as fh:
        json.dump(rec, fh)
    verified = False
    for _ in range(10):
        text = sh(["/usr/bin/pmset", "-g", "assertions"])
        if any(h["pid"] == proc.pid for h in parse_assertions(text)["sleep_holders"]):
            verified = True
            break
        time.sleep(0.3)
    if not verified:
        raise RuntimeError("전원 관리에 잠들지 않기 요청이 등록되지 않았습니다.")
    return {"keep_awake": {**rec, "alive": True}, "verified": True,
            "message": "잠들지 않기를 켜고 전원 관리 목록에서 확인했습니다."}


def allow_sleep():
    current = keep_awake_record()
    if not current:
        return {"keep_awake": None, "verified": True, "message": "켜 둔 잠들지 않기가 없습니다."}
    pid = int(current["pid"])
    if current["alive"]:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError as error:
            raise RuntimeError(f"잠들지 않기 종료 실패: {error}")
        for _ in range(20):
            try:
                os.kill(pid, 0)
                time.sleep(0.1)
            except OSError:
                break
        else:
            raise RuntimeError("잠들지 않기 프로세스가 종료되지 않았습니다.")
    try:
        os.remove(KEEP_AWAKE_FILE)
    except OSError:
        pass
    return {"keep_awake": None, "verified": True, "message": "잠들지 않기를 끄고 프로세스 종료를 확인했습니다."}


APP_ENTRY = re.compile(r'^\s*\d+\)\s+"(.+?)"\s+(ASN:\S+):\s*$')


def parse_app_list(text):
    """앱 목록 명령 출력 → [{name, bundle_id, pid, type}]."""
    apps, current = [], None
    for line in text.splitlines():
        m = APP_ENTRY.match(line)
        if m:
            current = {"name": m.group(1), "asn": m.group(2), "bundle_id": None, "pid": None, "type": None, "path": None}
            apps.append(current)
            continue
        if current is None:
            continue
        b = re.search(r'bundleID="([^"]*)"', line)
        if b:
            current["bundle_id"] = b.group(1)
        bp = re.search(r'bundle path="([^"]*)"', line)
        if bp:
            current["path"] = bp.group(1)
        p = re.search(r"\bpid = (\d+)", line)
        if p:
            current["pid"] = int(p.group(1))
            t = re.search(r'type="([^"]*)"', line)
            current["type"] = t.group(1) if t else None
    return apps


def parse_app_info(text):
    out = {}
    for m in re.finditer(r'^"([^"]+)"=(?:"([^"]*)"|(\S+))\s*$', text, re.M):
        out[m.group(1)] = m.group(2) if m.group(2) is not None else m.group(3)
    pid = out.get("pid")
    return {"pid": int(pid) if pid and pid.isdigit() else None,
            "bundle_id": out.get("CFBundleIdentifier"), "name": out.get("LSDisplayName")}


def app_list():
    return parse_app_list(sh(["/usr/bin/lsappinfo", "list"]))


def front_app():
    asn = sh(["/usr/bin/lsappinfo", "front"]).strip()
    if not asn.startswith("ASN:"):
        return None
    return parse_app_info(sh(["/usr/bin/lsappinfo", "info", "-only", "pid,bundleid,name", asn]))


def apps_status():
    rows = app_list()
    visible = [{k: r[k] for k in ("name", "bundle_id", "pid", "type")} for r in rows if r.get("type") == "Foreground"]
    return {"front": front_app(), "apps": visible,
            "background_count": sum(1 for r in rows if r.get("type") != "Foreground"),
            "message": "앞 앱과 화면에 보이는 앱 목록(배경 전용 프로세스는 개수만)."}


def app_names(row):
    """현지화 표시 이름과 번들 파일 이름(TextEdit.app → textedit) 둘 다 이름 대조에 쓴다."""
    names = {(row.get("name") or "").lower()}
    path = row.get("path") or ""
    if path:
        base = os.path.basename(path.rstrip("/"))
        names.add(base.lower())
        if base.lower().endswith(".app"):
            names.add(base[:-4].lower())
    names.discard("")
    return names


def match_app(rows, request):
    key = request["app"].lower()
    if request["app_kind"] == "bundle":
        return [r for r in rows if (r.get("bundle_id") or "").lower() == key]
    return [r for r in rows if key in app_names(r)]


def launch_app(request):
    before = match_app(app_list(), request)
    flag = "-b" if request["app_kind"] == "bundle" else "-a"
    proc = subprocess.run(["/usr/bin/open", "-g", flag, request["app"]], capture_output=True, text=True, timeout=15)
    if proc.returncode != 0:
        raise RuntimeError("앱을 찾지 못했거나 실행이 거절됐습니다: " + proc.stderr.strip()[-300:])
    found = []
    for _ in range(20):
        found = match_app(app_list(), request)
        if found:
            break
        time.sleep(0.25)
    if not found:
        raise RuntimeError("실행 요청 뒤 5초 안에 앱 목록에 나타나지 않았습니다.")
    row = {k: found[0][k] for k in ("name", "bundle_id", "pid", "type")}
    return {"app": {**row, "running": True, "already_running": bool(before)}, "verified": True,
            "message": "앱이 실행 중임을 목록 재조회로 확인했습니다(앞으로 가져오지 않음)." if not before else
                       "앱이 이미 실행 중이었습니다(앞으로 가져오지 않음)."}


def quit_app(request):
    rows = match_app(app_list(), request)
    if not rows:
        return {"app": {"name": request["app"], "running": False, "already_stopped": True}, "verified": True,
                "message": "앱이 실행 중이 아니었습니다."}
    ref = (f'application id "{request["app"]}"' if request["app_kind"] == "bundle"
           else f'application "{request["app"]}"')
    proc = subprocess.run(["/usr/bin/osascript", "-e", f"tell {ref} to quit"], capture_output=True, text=True, timeout=20)
    if proc.returncode != 0:
        err = proc.stderr.strip()[-300:]
        if "-1743" in err:
            raise RuntimeError("이 앱에 Apple Events 자동화 권한이 없습니다(-1743). 시스템 설정 > 개인정보 보호 > 자동화에서 허용하세요: " + err)
        raise RuntimeError("종료 요청 실패: " + err)
    for _ in range(32):
        if not match_app(app_list(), request):
            return {"app": {"name": rows[0].get("name"), "bundle_id": rows[0].get("bundle_id"), "running": False},
                    "verified": True, "message": "앱 종료를 목록 재조회로 확인했습니다."}
        time.sleep(0.25)
    raise RuntimeError("종료 요청을 보냈지만 8초 안에 앱이 사라지지 않았습니다(저장 확인 창이 떠 있을 수 있음).")


def clipboard_read():
    text = sh(["/usr/bin/pbpaste"], ok_codes=(0, 1))
    limit = 100_000
    return {"text": text[:limit], "length": len(text), "truncated": len(text) > limit,
            "verified": True, "message": "클립보드 글을 읽었습니다(글 아닌 내용은 비어 보일 수 있음)."}


def clipboard_write(request):
    sh(["/usr/bin/pbcopy"], input_text=request["text"])
    after = sh(["/usr/bin/pbpaste"], ok_codes=(0, 1))
    if after != request["text"]:
        raise RuntimeError("클립보드에 쓴 뒤 읽은 내용이 다릅니다.")
    return {"length": len(request["text"]), "verified": True, "message": "클립보드에 쓰고 재조회로 확인했습니다."}


def parse_wifi_port(text):
    block = re.search(r"Hardware Port: Wi-Fi\s*\nDevice: (\S+)", text)
    return block.group(1) if block else None


def wifi_port():
    return parse_wifi_port(sh(["/usr/sbin/networksetup", "-listallhardwareports"]))


def parse_wifi_power(text):
    m = re.search(r":\s*(On|Off)\s*$", text.strip())
    return (m.group(1) == "On") if m else None


def parse_ssid(text):
    m = re.search(r"^\s*SSID\s*:\s*(.+?)\s*$", text, re.M)
    if not m or m.group(1) == "<redacted>":
        return None
    return m.group(1)


def wifi_status(port=None):
    port = port or wifi_port()
    if not port:
        return {"port": None, "enabled": None, "ssid": None, "message": "Wi-Fi 장치가 없습니다."}
    enabled = parse_wifi_power(sh(["/usr/sbin/networksetup", "-getairportpower", port]))
    ssid = None
    if enabled:
        try:
            ssid = parse_ssid(sh(["/usr/sbin/ipconfig", "getsummary", port]))
        except RuntimeError:
            ssid = None
    return {"port": port, "enabled": enabled, "ssid": ssid,
            "ssid_basis": "ipconfig_summary (위치 권한 없으면 null)"}


def bluetooth_status():
    try:
        raw = sh(["/usr/sbin/system_profiler", "SPBluetoothDataType", "-json"], timeout=20)
        data = json.loads(raw)["SPBluetoothDataType"][0]
    except (RuntimeError, ValueError, KeyError, IndexError, subprocess.TimeoutExpired) as error:
        return {"enabled": None, "connected": [], "error": str(error)[:200]}
    state = (data.get("controller_properties") or {}).get("controller_state")
    connected = []
    for entry in data.get("device_connected") or []:
        for name, props in (entry or {}).items():
            props = props or {}
            connected.append({"name": name, "address": props.get("device_address"),
                              "type": props.get("device_minorType"), "battery": props.get("device_batteryLevelMain")})
    return {"enabled": None if state is None else state == "attrib_on", "connected": connected}


def network_status():
    return {"wifi": wifi_status(), "bluetooth": bluetooth_status(), "verified": True,
            "message": "Wi-Fi 전원·연결 이름과 블루투스 연결 기기를 읽었습니다. 블루투스 연결·해제는 지원하지 않습니다."}


def wifi_set(request):
    port = wifi_port()
    if not port:
        raise RuntimeError("Wi-Fi 장치가 없습니다.")
    sh(["/usr/sbin/networksetup", "-setairportpower", port, "on" if request["enabled"] else "off"])
    after = None
    for _ in range(10):
        after = wifi_status(port)
        if after["enabled"] is request["enabled"]:
            return {"wifi": after, "verified": True, "message": "Wi-Fi 전원을 바꾸고 재조회로 확인했습니다."}
        time.sleep(0.3)
    raise RuntimeError("변경 뒤 읽은 Wi-Fi 전원 상태가 요청과 다릅니다.")


def shortcuts_list():
    names = [line.strip() for line in sh(["/usr/bin/shortcuts", "list"], timeout=20).splitlines() if line.strip()]
    return {"shortcuts": names, "count": len(names), "verified": True, "message": "사용자가 만든 단축어 이름 목록."}


def shortcut_run(request):
    names = shortcuts_list()["shortcuts"]
    if request["name"] not in names:
        raise RuntimeError("그 이름의 단축어가 없습니다. shortcuts 로 목록을 조회하세요.")
    proc = subprocess.run(["/usr/bin/shortcuts", "run", request["name"]], capture_output=True, text=True, timeout=90)
    if proc.returncode != 0:
        raise RuntimeError(f"단축어가 오류로 끝났습니다({proc.returncode}): " + (proc.stderr or proc.stdout).strip()[-400:])
    return {"name": request["name"], "output": proc.stdout[:4000], "exit": 0, "verified": False,
            "message": "단축어가 정상 종료했습니다. 단축어 안의 효과는 확인 범위 밖입니다."}


def presence():
    display = Display()
    disp = display.displays()
    return {"idle_seconds": idle_seconds(), "front": front_app(), **display.session(),
            "display_asleep": any(d["asleep"] for d in disp if d["main"]) if disp else None,
            "verified": True,
            "message": "마지막 입력 뒤 경과 초·앞 앱·화면 잠금·주 화면 잠듦. 사용자가 보고 있는지의 판단 재료이지 판정이 아닙니다."}


def run_host(request):
    """본체 OS 조작면 동작. 처리했으면 결과 dict, 아니면 None."""
    action = request["action"]
    if action == "display":
        display = Display()
        return {"displays": display.displays(), **display.session(), "verified": True, "message": "화면 목록과 세션 상태를 읽었습니다."}
    if action == "brightness":
        return Display().set_brightness(request)
    if action == "power":
        return {**power_status(), "verified": True, "message": "전원·배터리·잠 방지 상태를 읽었습니다."}
    if action == "presence":
        return presence()
    if action == "apps":
        return {**apps_status(), "verified": True}
    if action == "launch":
        return launch_app(request)
    if action == "quit":
        return quit_app(request)
    if action == "clipboard":
        return clipboard_read()
    if action == "clipboard_write":
        return clipboard_write(request)
    if action == "network":
        return network_status()
    if action == "wifi":
        return wifi_set(request)
    if action == "shortcuts":
        return shortcuts_list()
    if action == "shortcut":
        return shortcut_run(request)
    if action == "keep_awake":
        return keep_awake(request)
    if action == "allow_sleep":
        return allow_sleep()
    if action == "sleep":
        sh(["/usr/bin/pmset", "sleepnow"])
        return {"verified": False, "message": "잠자기를 요청했습니다. 실제로 잠들었는지는 확인 범위 밖입니다."}
    return None


def run(request, audio_factory=Audio):
    if sys.platform != "darwin":
        raise RuntimeError("맥 전용 실행 파일입니다.")
    action = request["action"]
    lock_binary = "/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession"
    base = {"hostname": platform.node(), "os_version": platform.mac_ver()[0],
            "can_lock": os.path.isfile(lock_binary),
            "observed_at": datetime.now(timezone.utc).isoformat()}
    if action == "status":
        try:
            base["devices"] = [row for _, row in audio_factory().devices()]
        except Exception as error:
            base.update(devices=[], audio_error=str(error))
        return {**base, "verified": True, "message": "맥 상태를 조회했습니다."}
    if action in {"volume", "mute"}:
        return {**base, **audio_factory().change(request)}
    if action == "open_url":
        subprocess.run(["/usr/bin/open", request["url"]], check=True, capture_output=True, timeout=10)
        return {**base, "verified": False, "message": "기본 브라우저에 주소 열기를 요청했습니다. 로딩·재생은 확인하지 않았습니다."}
    if action == "lock":
        # Login-window lock; no sleep, reboot, process kill or key injection.
        if not os.path.isfile(lock_binary):
            raise RuntimeError("이 macOS에는 지원하는 잠금 명령이 없습니다. 직접 화면을 잠가 주세요.")
        subprocess.Popen([lock_binary, "-suspend"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        locked = None
        for _ in range(12):
            time.sleep(0.25)
            try:
                locked = Display().session().get("screen_locked")
            except Exception:
                locked = None
            if locked:
                break
        return {**base, "screen_locked": locked, "verified": locked is True,
                "message": ("화면 잠금을 세션 상태 재조회로 확인했습니다." if locked is True else
                            "화면 잠금을 요청했지만 3초 안에 잠금 상태를 읽지 못했습니다.")}
    host = run_host(request)
    if host is not None:
        return {**base, **host}
    raise ValueError("지원하지 않는 동작입니다.")


if __name__ == "__main__":
    request = globals().get("PC_REQUEST") or json.load(sys.stdin)
    result = {"protocol": "pc-control/1", "platform": "darwin", "action": request.get("action"),
              "request_id": request.get("request_id")}
    try:
        result.update(run(request), success=True)
    except Exception as error:
        result.update(success=False, verified=False, error=str(error))
    print("INDIEBIZ_PC_RESULT:" + json.dumps(result, ensure_ascii=False))
