"""Android OS driver: explicit target, correlated receipts, readback, no replay.

The same verifier runs beside the existing phone primitives and on the caller.
Only stdlib is loaded here; Android imports stay in the selected primitive.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import uuid
from datetime import datetime, timezone

PROTOCOL = "android-control/1"
AUDIO = {"volume_status": "status", "volume": "set", "volume_step": "step",
         "volume_half": "half", "volume_mute": "mute", "volume_restore": "restore",
         "vibrate": "vibrate"}
REQUIRED = {
    "status": [], "volume_status": [], "volume": ["value"], "volume_step": ["value"],
    "volume_half": [], "volume_mute": [], "volume_restore": [], "vibrate": [],
    "brightness": ["value"], "brightness_auto": ["enabled"], "rotation": ["enabled"],
    "timeout": ["seconds"], "torch": ["enabled"], "sensor": ["sensor"],
    "screen_on": [], "screen_off": [], "settings_permission": [],
}
OPTIONAL = {a: ["stream"] for a in AUDIO}
OPTIONAL.update(vibrate=["stream", "duration_ms"], torch=["camera_id"])
READS = {"status", "volume_status", "sensor"}
REQUEST_ONLY = {"vibrate", "settings_permission"}
SENSORS = {"light", "proximity", "accelerometer", "gyroscope", "magnetic_field", "pressure"}


def condition(action):
    scope = ("request_only" if action in REQUEST_ONLY else
             "sensor_sample" if action == "sensor" else
             "os_state_readback" if action in READS else
             "torch_callback_readback" if action == "torch" else
             "screen_interactive_readback" if action.startswith("screen_") else
             "os_setting_readback")
    return {"needs_front": False, "shared_state": action not in READS,
            "isolated_resources": [], "verification_scope": scope}


def validate(request):
    if not isinstance(request, dict):
        raise ValueError("요청은 객체여야 합니다.")
    action = request.get("action", "status")
    if not isinstance(action, str) or action not in REQUIRED:
        raise ValueError("지원하지 않는 Android OS 동작입니다.")
    if set(request) - {"action", *REQUIRED[action], *OPTIONAL.get(action, [])}:
        raise ValueError("이 동작이 받지 않는 인수가 있습니다.")
    if any(k not in request for k in REQUIRED[action]):
        raise ValueError("필수 인수가 없습니다: " + ", ".join(REQUIRED[action]))
    out = {**request, "action": action}
    ranges = {"volume": ("value", 0, 1000), "volume_step": ("value", -1, 1),
              "brightness": ("value", 1, 255), "timeout": ("seconds", 15, 600),
              "vibrate": ("duration_ms", 1, 1000)}
    if action == "vibrate":
        out.setdefault("duration_ms", 200)
    if action in ranges:
        key, low, high = ranges[action]
        if type(out[key]) is not int or not low <= out[key] <= high:
            raise ValueError(f"{key}는 {low}~{high} 정수입니다.")
    if action == "volume_step" and out["value"] == 0:
        raise ValueError("음량 단계 변경은 -1 또는 1입니다.")
    if "enabled" in out and type(out["enabled"]) is not bool:
        raise ValueError("enabled는 true 또는 false입니다.")
    if action in AUDIO:
        out.setdefault("stream", "music")
        if out["stream"] not in ("music", "alarm", "ring", "notification"):
            raise ValueError("음량 종류는 music/alarm/ring/notification입니다.")
    if action == "sensor" and out["sensor"] not in SENSORS:
        raise ValueError("지원하지 않는 센서입니다.")
    if "camera_id" in out and (not isinstance(out["camera_id"], str)
                               or not out["camera_id"] or len(out["camera_id"]) > 128):
        raise ValueError("조회한 camera_id 문자열을 지정하세요.")
    return out


def select_target(args):
    request = validate(args.get("request"))
    target = args.get("target")
    if not isinstance(target, str) or not target.strip() or target == "__local__":
        raise ValueError("등록된 Android 폰의 device_id를 명시하세요.")
    rows = [r for r in args.get("limbs", []) if isinstance(r, dict) and r.get("device_id") == target]
    if len(rows) != 1:
        raise ValueError("등록된 Android 폰 ID를 확인하세요.")
    row = rows[0]
    reg = row.get("registration") or {}
    caps = reg.get("capabilities") or {}
    python = (caps.get("runtimes") or {}).get("python") or {}
    if ((caps.get("os") or (row.get("env") or {}).get("os")) != "android"
            or row.get("revoked") or row.get("expired") or row.get("invitation")
            or row.get("connected") is not True or reg.get("state") != "active"
            or reg.get("paused") or caps.get("execution_contract") != 1
            or python.get("ready") is not True):
        raise ValueError("폰의 Android·등록·연결·Python 실행 준비 상태를 확인하세요.")
    wait = args.get("wait")
    wait = 60 if wait is None else wait
    if type(wait) not in (int, float) or not math.isfinite(wait) or not 0 <= wait <= 240:
        raise ValueError("대기는 0~240초입니다.")
    filename = "phone_control.py" if request["action"] in AUDIO else "phone_device.py"
    return {"target": target, "platform": "android", "request": request,
            "source_path": "~workspace/data/instruments/" + filename, "wait": wait, "timeout": 20}


def helper_hash():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def prepare(args):
    request = validate(args.get("request"))
    source = args.get("source")
    if not isinstance(source, str) or not source.strip() or len(source.encode()) > 128000:
        raise ValueError("선택한 폰 실행 파일을 읽어 전달하세요.")
    request_id = uuid.uuid4().hex
    digest = hashlib.sha256(source.encode()).hexdigest()
    # Separate namespaces avoid triggering the primitive's legacy inputs entry point.
    driver = Path(__file__).read_text(encoding="utf-8")
    code = ("_driver = {'__name__': 'android_driver'}\n"
            f"exec(compile({driver!r}, '<android_driver>', 'exec'), _driver)\n"
            f"result = _driver['run_device']({request!r}, {source!r}, "
            f"{request_id!r}, {digest!r})\n")
    return {"request": request, "request_id": request_id, "platform": "android",
            "source_sha256": digest, "helper_sha256": helper_hash(), "code": code}


def readback(request, value):
    """Check observed values, not just a provider's success/verified bit."""
    action = request["action"]
    if value.get("success") is not True:
        return False
    if action in REQUEST_ONLY:
        return False
    if action in AUDIO:
        actual, maximum, before = (value.get(k) for k in ("actual", "max", "before"))
        if (value.get("stream") != request["stream"] or type(actual) is not int
                or type(maximum) is not int or not 0 <= actual <= maximum):
            return False
        if action == "volume_status":
            return True
        if type(before) is not int or not 0 <= before <= maximum:
            return False
        expected = {"volume": request.get("value"), "volume_mute": 0,
                    "volume_half": before // 2,
                    "volume_step": max(0, min(maximum, before + request.get("value", 0))),
                    "volume_restore": value.get("target")}
        return (value.get("verified") is True and type(expected[action]) is int
                and actual == expected[action])
    if action == "status":
        return (value.get("hardware_control") in (0, 1)
                and type(value.get("screen_on")) is bool and type(value.get("locked")) is bool
                and type(value.get("battery")) is int and isinstance(value.get("capabilities"), dict))
    if action == "sensor":
        sample = value.get("reading") or {}
        values = sample.get("values")
        return (value.get("sensor") == request["sensor"] and isinstance(values, list) and bool(values)
                and all(type(x) in (int, float) and math.isfinite(x) for x in values)
                and type(sample.get("timestamp_ns")) is int and sample["timestamp_ns"] > 0)
    if value.get("verified") is not True:
        return False
    if action == "torch":
        lights = value.get("torches") or []
        selected = request.get("camera_id") or (lights[0].get("id") if lights else None)
        rows = [r for r in lights if r.get("id") == selected]
        return len(rows) == 1 and rows[0].get("enabled") is request["enabled"]
    if action == "brightness":
        return value.get("brightness") == request["value"] and value.get("brightness_auto") is False
    if action in {"brightness_auto", "rotation"}:
        key = "auto_rotate" if action == "rotation" else action
        return value.get(key) is request["enabled"]
    if action == "timeout":
        return value.get("screen_timeout_ms") == request["seconds"] * 1000
    if action in {"screen_on", "screen_off"}:
        return value.get("screen_on") is (action == "screen_on")
    return False


def run_device(request, source, request_id, digest):
    action = request["action"]
    metadata = {"protocol": PROTOCOL, "platform": "android", "action": action,
                "request_id": request_id, "source_sha256": digest,
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "condition": condition(action), "verification_scope": condition(action)["verification_scope"]}
    try:
        validate(request)
        namespace = {"__name__": "phone_primitive"}
        exec(compile(source, "<phone_primitive>", "exec"), namespace)
        inputs = {k: v for k, v in request.items() if k != "action"}
        inputs["op"] = AUDIO.get(action, action)
        value = namespace["run"](inputs)
        metadata["observed_at"] = datetime.now(timezone.utc).isoformat()
        if not isinstance(value, dict):
            raise ValueError("폰 실행 응답이 객체가 아닙니다.")
        verified = readback(request, value)
        success = value.get("success") is True and (verified or action in REQUEST_ONLY)
        return {**value, **metadata, "success": success, "verified": verified,
                "driver_status": "completed" if success else "failed",
                **({} if success else {"error": value.get("error") or "POSTCONDITION_FAILED: 관측값이 요청과 다릅니다."})}
    except Exception as exc:
        # A setter may have succeeded before a later metadata read raised.
        return {**metadata, "success": False, "verified": False,
                "driver_status": "failed" if action in READS else "unknown", "error": str(exc)}


def verify_task(args, context):
    task = args.get("task")
    task = task if isinstance(task, dict) else {}
    out = {k: task.get(k) for k in ("target", "task_ref", "verification", "evidence_ref")}
    out.update(status="unknown", verified=False, result=None, failure=None)

    def fail(message, result=None, status="unknown"):
        return {**out, "status": status, "result": result, "failure": {
            "stage": "verification", "message": message,
            "next": "같은 작업을 Android제어확인으로 조회하세요. 근거가 없으면 상태만 새로 읽으세요. 변경을 재전송하지 마세요."}}

    try:
        receipts = context.get("receipts", {})
        prepared, accepted = receipts.get("plan_ref", {}), receipts.get("job_ref", {})
        if not prepared.get("available") or not accepted.get("available"):
            return fail("원래 준비·접수 영수증을 읽을 수 없습니다.")
        plan, job = prepared["value"], accepted["value"]
        if (prepared.get("producer") != "Android제어부품" or accepted.get("action") != "limbs:guestpc"
                or plan.get("helper_sha256") != helper_hash()):
            return fail("원래 검증기 또는 접수 근거가 다릅니다.")
        verification = {k: plan[k] for k in ("request", "request_id", "platform", "source_sha256")}
        if (task.get("verification") != verification or not job.get("task_ref")
                or task.get("task_ref") != job.get("task_ref") or task.get("target") != job.get("limb")
                or job.get("request_id") != plan["request_id"]):
            return fail("원래 요청·대상·작업 참조와 다릅니다.")
        observation = args.get("observation")
        if observation is None:
            return {**out, "status": "pending"}
        if (observation.get("task_ref") != job["task_ref"]
                or observation.get("limb", job["limb"]) != job["limb"]
                or observation.get("request_id", plan["request_id"]) != plan["request_id"]):
            return fail("다른 작업의 관측 결과입니다.")
        state = observation.get("state")
        if state in {"queued", "running", "waiting", "accepted"}:
            return {**out, "status": "pending"}
        result = observation.get("result") or observation.get("execution_result")
        if not isinstance(result, dict) or result.get("success") is not True:
            return fail("원격 실행 결과가 불확실합니다: " + str(state), result)
        value = result.get("value")
        if not isinstance(value, dict) or any(value.get(k) != v for k, v in {
                "protocol": PROTOCOL, "platform": "android", "action": plan["request"]["action"],
                "request_id": plan["request_id"], "source_sha256": plan["source_sha256"]}.items()):
            return fail("요청과 다른 Android 결과입니다.", result)
        if value.get("driver_status") in {"unknown", "failed"}:
            return fail(value.get("error") or "폰 제어 실패", value, value["driver_status"])
        if state != "succeeded":
            return fail("원격 작업 종료를 확인하지 못했습니다.", value)
        action = plan["request"]["action"]
        verified = readback(plan["request"], value)
        if value.get("success") is not True or (not verified and action not in REQUEST_ONLY):
            return fail("POSTCONDITION_FAILED: 결과 재검증에 실패했습니다.", value, "failed")
        return {**out, "status": "completed", "verified": verified, "result": {
            **value, "verified": verified, "condition": condition(action),
            "verification_scope": condition(action)["verification_scope"]}}
    except (KeyError, TypeError, AttributeError, ValueError):
        return fail("준비·접수·관측 근거의 형식이 불완전합니다.")


def run(args, context=None):
    op = args.get("op")
    if op == "contract":
        return {"version": 1, "platforms": ["android"], "actions": REQUIRED, "optional": OPTIONAL,
                "conditions": {a: condition(a) for a in REQUIRED},
                "units": {"volume": "OS integer steps, max from volume_status",
                          "brightness": "1..255", "timeout": "seconds"},
                "recovery": "Query the original task; never replay a mutation automatically."}
    if op == "select":
        return select_target(args)
    if op == "prepare":
        return prepare(args)
    if op == "verify":
        return verify_task(args, context or {})
    raise ValueError("지원하지 않는 드라이버 op입니다.")


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        value = run(payload["args"], payload.get("context", {}))
        result = {"protocol": "ibl-script/2", "ok": True, "value": value}
    except Exception as exc:
        result = {"protocol": "ibl-script/2", "ok": False, "error": str(exc)}
    text = json.dumps(result, ensure_ascii=False, allow_nan=False)
    destination = os.environ.get("INDIEBIZ_SCRIPT_RESULT")
    if destination:
        path = Path(destination)
        temp = path.with_suffix(".tmp")
        temp.write_text(text, encoding="utf-8")
        temp.replace(path)
    else:
        print(text)
