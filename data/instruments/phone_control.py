"""Selected Android phone controls. Executed by guestpc/python with explicit inputs.

No model calls, shell commands, player replacement or manufacturer-specific paths.
The undo receipt lives on the phone, and is consumed only after verified restoration.
"""
import json
import os


def integer(value, low, high):
    if isinstance(value, bool):
        raise ValueError("정수를 지정해 주세요.")
    number = int(value)
    if str(number) != str(value) or not low <= number <= high:
        raise ValueError(f"{low}~{high} 사이의 정수를 지정해 주세요.")
    return number


def read_receipt(path):
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except FileNotFoundError:
        return {}


def write_receipt(path, receipt):
    with open(path + ".tmp", "w", encoding="utf-8") as stream:
        json.dump(receipt, stream)
    os.replace(path + ".tmp", path)


def volume_control(audio, stream, path, op, value=None):
    """Call under the per-phone file lock. Re-read OS state after every mutation."""
    maximum = int(audio.getStreamMaxVolume(stream))
    before = int(audio.getStreamVolume(stream))
    fixed = bool(audio.isVolumeFixed())
    receipt = read_receipt(path)
    previous = receipt.get("previous")
    can_restore = (isinstance(previous, int) and not isinstance(previous, bool)
                   and 0 <= previous <= maximum and receipt.get("after") == before
                   and previous != before and not fixed)
    message = "현재 음량을 확인했습니다."
    target = before
    if op != "status":
        if fixed:
            raise ValueError("이 출력 장치는 음량을 변경할 수 없습니다.")
        if op == "restore":
            if not can_restore:
                raise ValueError("복원할 값이 없거나 다른 곳에서 음량이 변경됐습니다. 상태를 새로 확인해 주세요.")
            target = previous
        elif op == "set":
            target = integer(value, 0, maximum)
        elif op == "step":
            target = max(0, min(maximum, before + integer(value, -1, 1)))
        elif op == "half":
            target = before // 2
        elif op == "mute":
            target = 0
        else:
            raise ValueError("지원하지 않는 음량 명령입니다.")
        if target != before:
            # Preserve recovery before the side effect, including a lost reply.
            pending = {"previous": previous if op == "restore" else before, "after": target}
            write_receipt(path, pending)
            try:
                audio.setStreamVolume(stream, target, 0)
            except Exception:
                if int(audio.getStreamVolume(stream)) == before:
                    write_receipt(path, receipt)
                raise
            actual = int(audio.getStreamVolume(stream))
            if actual != target:
                if actual == before:
                    write_receipt(path, receipt)
                raise ValueError(f"요청한 {target}단계와 실제 {actual}단계가 다릅니다. 상태를 새로 확인해 주세요.")
            write_receipt(path, {} if op == "restore" else pending)
        message = "이전 음량으로 복원했습니다." if op == "restore" else "음량을 적용하고 확인했습니다."
    actual = int(audio.getStreamVolume(stream))
    saved = read_receipt(path)
    previous = saved.get("previous")
    can_restore = (isinstance(previous, int) and not isinstance(previous, bool)
                   and 0 <= previous <= maximum and saved.get("after") == actual
                   and previous != actual and not fixed)
    return {"success": True, "verified": actual == target, "target": target,
            "stream": "music", "before": before, "actual": actual,
            "max": maximum, "percent": round(actual * 100 / maximum) if maximum else 0,
            "fixed": fixed, "can_restore": can_restore,
            "previous": previous if can_restore else None, "message": message}


def run(args):
    import fcntl
    from java import jclass
    from indiebiz_android import context

    op = args.get("op", "status")
    if op not in {"status", "set", "step", "half", "mute", "restore", "vibrate"}:
        raise ValueError("지원하지 않는 명령입니다.")
    root = os.path.join(str(context.getFilesDir().getAbsolutePath()), "phone_control")
    os.makedirs(root, exist_ok=True)
    audio = context.getSystemService("audio")
    am = jclass("android.media.AudioManager")
    stream_name = args.get("stream", "music")
    streams = {"music": am.STREAM_MUSIC, "alarm": am.STREAM_ALARM,
               "ring": am.STREAM_RING, "notification": am.STREAM_NOTIFICATION}
    if stream_name not in streams:
        raise ValueError("음량 종류는 music/alarm/ring/notification입니다.")
    receipt_name = "volume.json" if stream_name == "music" else "volume_" + stream_name + ".json"
    with open(os.path.join(root, "volume.lock"), "a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        out = volume_control(audio, streams[stream_name], os.path.join(root, receipt_name),
                             "status" if op == "vibrate" else op, args.get("value"))
    out["stream"] = stream_name
    build = jclass("android.os.Build")
    version = jclass("android.os.Build$VERSION")
    battery = context.getSystemService("batterymanager")
    bm = jclass("android.os.BatteryManager")
    vibrator = context.getSystemService("vibrator")
    has_vibrator = bool(vibrator and vibrator.hasVibrator())
    if op == "vibrate":
        duration = integer(args.get("duration_ms", 200), 1, 1000)
        if not has_vibrator:
            raise ValueError("이 기기에는 진동 기능이 없습니다.")
        if version.SDK_INT >= 26:
            effect = jclass("android.os.VibrationEffect")
            vibrator.vibrate(effect.createOneShot(duration, effect.DEFAULT_AMPLITUDE))
        else:
            vibrator.vibrate(duration)
        out["message"] = "짧은 진동을 요청했습니다."
    out.update({"model": str(build.MODEL), "android": str(version.RELEASE),
                "battery": int(battery.getIntProperty(bm.BATTERY_PROPERTY_CAPACITY)),
                "has_vibrator": has_vibrator, "op": op})
    return out


if "inputs" in globals():
    try:
        result = run(inputs)
    except Exception as error:
        result = {"success": False, "error": str(error)}
