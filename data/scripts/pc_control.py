"""Shared PC command preparation/result validation for manual apps and AI.

Run through self:script path; native source is read at execution time, never bundled
in a frontend build. Transport remains guestpc/shell with stdin, or local subprocess.
"""
import base64
import hashlib
import json
import math
import os
import platform
import re
import subprocess
import sys
import uuid
import unicodedata
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

PROTOCOL = "pc-control/1"
MARKER = "INDIEBIZ_PC_RESULT:"
CONTRACT = {
    "version": 1,
    "platforms": ["darwin", "windows"],
    "audio_capabilities": {
        "scope": "os_api_support",
        "meaning": "can_set_volume·can_mute는 OS가 제공하는 제어 API의 지원 여부다. "
                   "Windows는 EndpointVolume 인터페이스 활성화·조회 성공을 근거로 true를 반환한다. "
                   "하드웨어 직접 지원이나 실제 변경 시험의 결과가 아니며, 그 시험의 부재로 API 지원을 unknown으로 바꾸지 않는다.",
        "basis": {"darwin": "coreaudio_property_settable", "windows": "wasapi_endpoint_volume_interface"},
        "setter_tested_by_status": False,
        "hardware_support_observed": False,
        "physical_sound_verified": False,
    },
    "actions": {
        "status": [], "volume": ["device_id", "value"],
        "mute": ["device_id", "enabled"], "open_url": ["url"], "lock": [],
        "youtube_status": [], "youtube_stop": [],
        "youtube_replace": ["url", "title", "duration_seconds", "fullscreen"],
    },
}


class ControlFailure(ValueError):
    """A correlated native failure retains its observation for AI recovery."""

    def __init__(self, message, state):
        super().__init__(message)
        self.state = state


def validate(args):
    if not isinstance(args, dict):
        raise ValueError("PC 제어 인수는 객체여야 합니다.")
    action = args.get("action", "status")
    if action not in CONTRACT["actions"]:
        raise ValueError("지원하지 않는 PC 동작입니다.")
    allowed = {"action", *CONTRACT["actions"][action]}
    if set(args) - allowed:
        raise ValueError("이 동작이 받지 않는 인수가 있습니다.")
    for key in CONTRACT["actions"][action]:
        if key not in args:
            raise ValueError(f"{key}가 필요합니다.")
    result = {"action": action}
    if action == "youtube_replace":
        parsed = urlsplit(str(args["url"]))
        host = (parsed.hostname or "").lower().rstrip(".")
        video = (parsed.path.strip("/") if host == "youtu.be" else
                 parse_qs(parsed.query).get("v", [""])[0] if
                 host in {"www.youtube.com", "youtube.com", "m.youtube.com", "music.youtube.com"}
                 and parsed.path == "/watch" else "")
        if parsed.scheme != "https" or parsed.username or parsed.password or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video):
            raise ValueError("검색 결과의 유튜브 단일 영상 https 주소가 필요합니다.")
        title, duration = args["title"], args["duration_seconds"]
        if not isinstance(title, str) or not title.strip() or len(title) > 1000:
            raise ValueError("확인할 영상의 전체 제목이 필요합니다.")
        if type(duration) is not int or not 1 <= duration <= 86400:
            raise ValueError("영상 전체 길이를 초 단위로 입력하세요. 생방송은 아직 지원하지 않습니다.")
        if type(args["fullscreen"]) is not bool:
            raise ValueError("fullscreen은 true 또는 false입니다.")
        result.update(url=f"https://www.youtube.com/watch?v={video}", title=title.strip(),
                      duration_seconds=duration, fullscreen=args["fullscreen"])
    if action in {"volume", "mute"}:
        device = args["device_id"]
        if not isinstance(device, str) or not device.strip() or len(device) > 1024:
            raise ValueError("조회한 출력 장치를 지정해 주세요.")
        result["device_id"] = device
    if action == "volume":
        value = args["value"]
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value != int(value) or not 0 <= value <= 100):
            raise ValueError("음량은 0~100 사이 정수여야 합니다.")
        result["value"] = int(value)
    if action == "mute":
        if type(args["enabled"]) is not bool:
            raise ValueError("음소거는 true 또는 false로 지정해 주세요.")
        result["enabled"] = args["enabled"]
    if action == "open_url":
        url = args["url"]
        if not isinstance(url, str) or len(url) > 4096 or any(ord(c) < 32 for c in url):
            raise ValueError("올바른 웹 주소를 입력해 주세요.")
        parsed = urlsplit(url)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("인증정보가 없는 http 또는 https 주소만 열 수 있습니다.")
        host = parsed.hostname.lower().rstrip(".")
        youtube = host == "youtube.com" or host.endswith(".youtube.com")
        embedded = host == "youtube-nocookie.com" or host.endswith(".youtube-nocookie.com")
        # open_url owns no playback session. A successful launch cannot replace an
        # existing video, so do not silently accumulate players through this path.
        route = unquote(parsed.path).strip("/").split("/", 1)[0].lower()
        if (host == "youtu.be" or host.endswith(".youtu.be") or
                ((youtube or embedded) and route in {"watch", "playlist", "shorts", "live", "embed", "v"})):
            raise ValueError(
                "유튜브 영상은 일반 주소 열기로 재생하지 않습니다. 기존 영상과 겹칠 수 있습니다. "
                "기존 재생 탭을 확인하고 그 탭에서 영상을 교체하세요. "
                "Windows에서는 youtube_replace에 영상 URL·제목·전체 길이를 전달하세요."
            )
        result["url"] = url
    return result


def prepare(args):
    system = args.get("platform")
    if system not in CONTRACT["platforms"]:
        raise ValueError("지원 OS는 darwin과 windows입니다.")
    source = args.get("source")
    if not isinstance(source, str) or not source.strip() or len(source.encode()) > 128000:
        raise ValueError("PC 실행 파일을 읽어 전달해 주세요.")
    request = validate(args.get("request", {}))
    if request["action"].startswith("youtube_") and system != "windows":
        raise ValueError("검증된 유튜브 탭 교체는 현재 Windows Chrome·Edge·Brave를 지원합니다.")
    request["request_id"] = uuid.uuid4().hex
    encoded = base64.b64encode(json.dumps(request, ensure_ascii=False).encode()).decode()
    if system == "darwin":
        prefix = f"import base64, json\nPC_REQUEST = json.loads(base64.b64decode('{encoded}'))\n"
        command = "python3 -"
    else:
        prefix = f"$PcRequest = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded}')) | ConvertFrom-Json\n"
        command = ('powershell.exe -STA -NoProfile -NonInteractive -Command '
                   '"[Console]::InputEncoding=[Text.Encoding]::UTF8; $s=[Console]::In.ReadToEnd(); & ([ScriptBlock]::Create($s))"')
    return {"success": True, "platform": system, "request": request,
            "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "command": command, "stdin": prefix + source + "\n", "helper_sha256": helper_hash()}


def decode(output, plan):
    if not isinstance(output, str) or not isinstance(plan, dict):
        raise ValueError("PC 실행 결과가 불완전합니다. 상태를 다시 조회하세요.")
    lines = [line[len(MARKER):] for line in output.splitlines() if line.startswith(MARKER)]
    if len(lines) != 1:
        raise ValueError("PC 결과를 확인하지 못했습니다. Python/PowerShell과 연결을 확인하세요. 변경을 자동 재전송하지 마세요.")
    state = json.loads(lines[0])
    request = plan.get("request", {})
    if (not isinstance(state, dict) or state.get("protocol") != PROTOCOL
            or state.get("request_id") != request.get("request_id")
            or state.get("platform") != plan.get("platform")
            or state.get("action") != request.get("action")):
        raise ValueError("요청과 다른 PC 결과입니다.")
    if state.get("success") is not True:
        state["source_sha256"] = plan.get("source_sha256")
        raise ControlFailure(str(state.get("error") or "PC 제어에 실패했습니다."), state)
    if request["action"] in {"youtube_replace", "youtube_stop"}:
        if state.get("verified") is not True or state.get("previous_stopped") is not True:
            raise ValueError("기존 유튜브 재생 정지를 확인하지 못했습니다.")
        if (type(state.get("tab_count_before")) is not int or state["tab_count_before"] < 1
                or type(state.get("tab_count_after")) is not int
                or state["tab_count_before"] != state["tab_count_after"]):
            raise ValueError("유튜브 교체 중 탭 개수가 바뀌었습니다.")
        if request["action"] == "youtube_replace":
            if request["fullscreen"] and state.get("fullscreen_verified") is not True:
                raise ValueError("요청한 전체화면을 확인하지 못했습니다.")
            playback = state.get("playback") or {}
            expected_video = parse_qs(urlsplit(request["url"]).query)["v"][0]
            actual_url = urlsplit(str(playback.get("url", "")))
            actual_video = parse_qs(actual_url.query).get("v", [""])[0]
            normalize = lambda text: " ".join(unicodedata.normalize("NFKC", str(text)).split())
            samples = [playback.get("position"), playback.get("previous_position"), playback.get("duration")]
            if (state.get("playback_verified") is not True or playback.get("ad") is not False
                    or playback.get("playing") is not True or playback.get("video_id") != expected_video
                    or actual_url.scheme != "https" or actual_url.path != "/watch"
                    or actual_url.hostname not in {"youtube.com", "www.youtube.com"} or actual_video != expected_video
                    or normalize(playback.get("title")) != normalize(request["title"])
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in samples)
                    or abs(playback["duration"] - request["duration_seconds"]) > 2
                    or not 0.25 < playback["position"] - playback["previous_position"] < 10):
                raise ValueError("요청한 본영상의 재생을 확인하지 못했습니다.")
    if request["action"] in {"volume", "mute"}:
        device = state.get("device", {})
        if device.get("id") != request["device_id"] or state.get("verified") is not True:
            raise ValueError("지정한 출력 장치의 변경을 확인하지 못했습니다.")
        if request["action"] == "volume" and (
                type(device.get("volume")) not in (int, float)
                or not math.isfinite(device["volume"])
                or abs(device["volume"] - request["value"]) > 1):
            raise ValueError("실제 음량이 요청과 다릅니다.")
        if request["action"] == "mute" and device.get("muted") is not request["enabled"]:
            raise ValueError("실제 음소거 상태가 요청과 다릅니다.")
    state["source_sha256"] = plan.get("source_sha256")
    if request["action"] in {"status", "volume", "mute"}:
        state["audio_capabilities"] = CONTRACT["audio_capabilities"]
        state["verification_scope"] = ("os_state_readback" if request["action"] == "status"
                                       else "os_setting_readback")
    return state


def helper_hash():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def select_target(args):
    request = validate(args.get("request", {}))
    target = args.get("target")
    if not isinstance(target, str) or not target:
        raise ValueError("대상 PC ID가 필요합니다")
    if target == "__local__":
        system = "windows" if sys.platform == "win32" else sys.platform
    else:
        rows = [r for r in args.get("limbs", []) if r.get("device_id") == target]
        if len(rows) != 1:
            raise ValueError("등록된 PC ID를 지정하세요")
        row = rows[0]
        registration = row.get("registration") or {}
        caps = registration.get("capabilities") or {}
        if (row.get("revoked") or row.get("expired") or row.get("invitation")
                or registration.get("state") != "active" or registration.get("paused")
                or caps.get("shell") is not True or row.get("connected") is not True):
            raise ValueError("선택 PC가 연결·활성·shell 준비 상태가 아닙니다")
        raw = str(caps.get("os") or (row.get("env") or {}).get("os") or "").lower()
        system = {"macos": "darwin", "mac": "darwin", "osx": "darwin",
                  "win32": "windows", "win": "windows"}.get(raw, raw)
    if system not in CONTRACT["platforms"]:
        raise ValueError("지원 PC OS를 확인하지 못했습니다")
    youtube = request["action"].startswith("youtube_")
    if youtube and system != "windows":
        raise ValueError("유튜브 제어는 Windows에서 지원합니다")
    wait = args.get("wait")
    if wait is None:
        wait = 150 if youtube else 60
    if type(wait) not in (int, float) or not math.isfinite(wait) or not 0 <= wait <= 240:
        raise ValueError("대기는 0~240초입니다")
    filename = ("pc_youtube_windows.ps1" if youtube else
                "pc_control_mac.py" if system == "darwin" else "pc_control_windows.ps1")
    return {"success": True, "target": target, "platform": system, "request": request,
            "source_path": "~workspace/data/instruments/" + filename,
            "wait": wait, "timeout": 120 if youtube else 30}


def verify_task(args, context):
    """원 준비·접수 영수증과 대조. 이 경로는 장치 명령을 전송하지 않는다."""
    task = args.get("task") or {}
    out = {"status": "unknown", "target": task.get("target"), "verified": False,
           "result": None, "task_ref": task.get("task_ref"),
           "verification": task.get("verification"), "evidence_ref": task.get("evidence_ref"),
           "failure": None}
    def fail(reason, status="unknown", result=None):
        return {**out, "status": status, "result": result,
                "failure": {"stage": "verification", "message": reason,
                            "next": "원 task_ref와 실행 영수증을 확인하세요. 변경을 재전송하지 마세요."}}
    receipts = context.get("receipts", {})
    prepared, accepted = receipts.get("plan_ref", {}), receipts.get("job_ref", {})
    if not prepared.get("available") or not accepted.get("available"):
        return fail("원래 준비·접수 영수증을 읽을 수 없습니다")
    plan, job = prepared.get("value", {}), accepted.get("value", {})
    if (prepared.get("producer") != "PC제어부품" or accepted.get("action") != "limbs:guestpc"
            or plan.get("helper_sha256") != helper_hash()):
        return fail("원래 검증기 또는 접수 근거가 다릅니다")
    verification = {k: plan.get(k) for k in ("request", "platform", "source_sha256")}
    if (task.get("verification") != verification or task.get("task_ref") != job.get("task_ref")
            or task.get("target") != job.get("limb")
            or job.get("request_id") != (plan.get("request") or {}).get("request_id")):
        return fail("원래 요청·대상·작업 참조와 다릅니다")
    observation = args.get("observation")
    if observation is None:
        return {**out, "status": "pending"}
    if (observation.get("task_ref") != job.get("task_ref")
            or observation.get("limb", job.get("limb")) != job.get("limb")):
        return fail("다른 작업의 관측 결과입니다")
    state = observation.get("state")
    if state in {"queued", "running", "waiting", "accepted"}:
        return {**out, "status": "pending"}
    result = observation.get("result") or observation.get("execution_result")
    if state in {"failed", "cancelled", "interrupted"}:
        return fail("원격 작업이 " + state + " 상태입니다", "failed", result)
    if state != "succeeded" or not isinstance(result, dict):
        return fail("원격 결과가 아직 확정되지 않았습니다", result=result)
    if result.get("exit") != 0 or result.get("timeout") or result.get("error"):
        return fail("원격 실행이 정상 종료하지 않았습니다", "failed", result)
    try:
        value = decode(result.get("output"), plan)
    except (ValueError, TypeError, KeyError) as exc:
        return fail(str(exc), "failed", getattr(exc, "state", result))
    return {**out, "status": "completed", "verified": value.get("verified") is True, "result": value}


def run(args, context=None):
    op = args.get("op", "prepare")
    if op == "select":
        return select_target(args)
    if op == "verify":
        return verify_task(args, context or {})
    if op == "contract":
        return {"success": True, **CONTRACT, "host_platform": platform.system()}
    if op == "decode":
        return decode(args.get("output"), args.get("plan"))
    plan = prepare(args)
    if op == "prepare":
        return plan
    if op != "local":
        raise ValueError("알 수 없는 실행 방법입니다.")
    expected = "windows" if sys.platform == "win32" else sys.platform
    if plan["platform"] != expected:
        raise ValueError("본체 OS와 선택한 앱이 다릅니다. 해당 OS의 원격 PC를 선택하세요.")
    argv = ([sys.executable, "-"] if expected == "darwin" else
            ["powershell.exe", "-STA", "-NoProfile", "-NonInteractive", "-Command",
             "[Console]::InputEncoding=[Text.Encoding]::UTF8; $s=[Console]::In.ReadToEnd(); & ([ScriptBlock]::Create($s))"])
    proc = subprocess.run(argv, input=plan["stdin"], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=115 if plan["request"]["action"].startswith("youtube_") else 25)
    if proc.returncode != 0:
        raise RuntimeError("PC 실행 실패: " + proc.stderr[-1200:])
    return decode(proc.stdout, plan)


if __name__ == "__main__":
    wire = False
    try:
        payload = json.load(sys.stdin)
        wire = payload.get("protocol") == "ibl-script/2"
        result = run(payload["args"] if wire else payload, payload.get("context", {}) if wire else {})
    except Exception as error:
        result = {"success": False, "error": str(error)}
        if isinstance(error, ControlFailure):
            result["observation"] = error.state
    if wire and result.get("observation", {}).get("protocol") == PROTOCOL:
        result = {**result["observation"], "verified": False}
    if wire:
        result = ({"protocol": "ibl-script/2", "ok": False, "error": result.get("error")}
                  if result.get("success") is False and result.get("protocol") != PROTOCOL else
                  {"protocol": "ibl-script/2", "ok": True, "value": result})
    text = json.dumps(result, ensure_ascii=False, allow_nan=False)
    destination = os.environ.get("INDIEBIZ_SCRIPT_RESULT")
    if destination:
        path = Path(destination)
        temp = path.with_suffix(".tmp")
        temp.write_text(text, encoding="utf-8")
        temp.replace(path)
    else:
        print(text)
