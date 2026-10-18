"""macOS native PC controls. stdlib only; Core Audio binds explicit output UIDs."""
import ctypes as C
import json
import os
import platform
import subprocess
import sys
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
        return {**base, "verified": False, "message": "화면 잠금을 요청했습니다. 잠금 상태는 확인하지 않았습니다."}
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
