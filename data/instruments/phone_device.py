"""Shared hardware primitives for the app and AI; execute with guestpc/python inputs."""
import json

OPS = {"status", "brightness", "brightness_auto", "rotation", "timeout",
       "sensor", "torch", "screen_on", "screen_off", "settings_permission"}


def legacy_status(context, jclass):
    """Old APKs remain observable, but never pretend to support new mutations."""
    battery = context.getSystemService("batterymanager")
    power = context.getSystemService("power")
    settings = jclass("android.provider.Settings$System")
    return {"success": True, "hardware_control": 0,
            "battery": int(battery.getIntProperty(4)),
            "charging": bool(battery.isCharging()),
            "screen_on": bool(power.isInteractive()),
            "locked": bool(context.getSystemService("keyguard").isKeyguardLocked()),
            "brightness": int(settings.getInt(context.getContentResolver(), "screen_brightness", -1)),
            "capabilities": {}, "sensors": [], "torches": [],
            "message": "기본 상태를 조회했습니다. 화면·손전등·센서 제어는 폰 앱 업데이트가 필요합니다."}


def run(args, bridge=None, fallback=None):
    if not isinstance(args, dict) or args.get("op", "status") not in OPS:
        raise ValueError("지원하지 않는 하드웨어 명령입니다.")
    if bridge is None:
        from indiebiz_android import call
        bridge = call
    try:
        value = bridge("hardware", json.dumps(args, ensure_ascii=False))
    except Exception as error:
        if "unsupported_device_call" not in str(error):
            raise
        if args.get("op", "status") != "status":
            raise RuntimeError("폰 앱 업데이트가 필요합니다. 명령은 실행하지 않았습니다.") from error
        if fallback is not None:
            return fallback()
        from java import jclass
        from indiebiz_android import context
        return legacy_status(context, jclass)
    if not isinstance(value, dict) or value.get("success") is not True:
        raise RuntimeError(str(value.get("error", "하드웨어 응답이 불완전합니다.")) if isinstance(value, dict)
                           else "하드웨어 응답이 불완전합니다.")
    return value


if "inputs" in globals():
    try:
        result = run(inputs)
    except Exception as error:
        result = {"success": False, "error": str(error)}
