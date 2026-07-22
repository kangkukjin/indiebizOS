"""desktop_av.py — 데스크탑 몸의 카메라·마이크 프로브 ([sense:see]/[sense:listen] 지표어)

see/listen 은 here 와 같은 지표어 — 각 몸이 **자기 하드웨어**로 감각한다.
폰=Camera2/SpeechRecognizer(handler.py 폰 경로), 데스크탑=ffmpeg 웹캠·마이크
(macOS=avfoundation, 윈도우=dshow, 리눅스=v4l2/alsa). 하드웨어가 없으면
정직한 작동불능(no_hardware) — 흉내내지 않는다(맥미니=카메라 0 이 정상 사례,
카메라·마이크 달린 PC 는 흔하므로 어휘를 폰에 묶지 않는다).

ffmpeg 는 라디오·유튜브가 쓰는 공급 체계(common.platform_utils.find_binary +
ffmpeg_provision)를 재사용. 데스크탑 STT 는 Gemini 오디오 이해(GEMINI_API_KEY,
맥·폰 공통 프로비저닝) — 없으면 녹음 파일만 정직 반환.
"""
import base64
import os
import platform
import re
import subprocess
import time


def _ffmpeg():
    try:
        from common.platform_utils import find_binary
        return find_binary("ffmpeg")
    except Exception:
        import shutil
        return shutil.which("ffmpeg")


def _outputs_dir() -> str:
    base = os.environ.get("INDIEBIZ_BASE_PATH") or os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "..")
    d = os.path.abspath(os.path.join(base, "outputs"))
    os.makedirs(d, exist_ok=True)
    return d


def _mac_devices(ff):
    """avfoundation 장치 열거 → (video[(idx,name)], audio[(idx,name)])."""
    p = subprocess.run([ff, "-hide_banner", "-f", "avfoundation",
                        "-list_devices", "true", "-i", ""],
                       capture_output=True, text=True, timeout=15)
    video, audio, section = [], [], None
    for line in (p.stderr or "").splitlines():
        if "video devices" in line:
            section = "v"
            continue
        if "audio devices" in line:
            section = "a"
            continue
        m = re.search(r"\]\s+\[(\d+)\]\s+(.+)$", line)
        if m and "AVFoundation" in line and section:
            entry = (int(m.group(1)), m.group(2).strip())
            (video if section == "v" else audio).append(entry)
    return video, audio


def _win_devices(ff):
    """dshow 장치 열거 → (video[names], audio[names])."""
    p = subprocess.run([ff, "-hide_banner", "-list_devices", "true",
                        "-f", "dshow", "-i", "dummy"],
                       capture_output=True, text=True, timeout=15)
    video, audio = [], []
    for line in (p.stderr or "").splitlines():
        m = re.search(r'"(.+?)"\s+\((video|audio)\)', line)
        if m:
            (video if m.group(2) == "video" else audio).append(m.group(1))
    return video, audio


def _no_hw(sense: str, ask_hint: str) -> dict:
    return {"success": False, "no_hardware": True,
            "error": (f"이 몸에 {sense} 하드웨어가 없습니다 — 지표어는 각 몸의 하드웨어를 "
                      f"쓰므로 이 데스크탑에선 작동불능입니다. 필요하면 폰 몸에 부탁: {ask_hint}")}


def _no_ffmpeg() -> dict:
    return {"success": False,
            "error": "데스크탑 캡처 도구(ffmpeg)가 없습니다 — 라디오/유튜브 첫 사용 시 자동 "
                     "공급되거나, macOS 는 `brew install ffmpeg` 로 설치하세요."}


def see_desktop(tool_input: dict) -> dict:
    """데스크탑 카메라 프로브 — 웹캠 정지 1장(화면캡처 장치는 카메라가 아니므로 제외)."""
    ff = _ffmpeg()
    if not ff:
        return _no_ffmpeg()
    sysname = platform.system()
    out = os.path.join(_outputs_dir(), f"see_{time.strftime('%Y%m%d_%H%M%S')}.jpg")

    if sysname == "Darwin":
        video, _ = _mac_devices(ff)
        cams = [(i, n) for i, n in video if "capture screen" not in n.lower()]
        if not cams:
            return _no_hw("카메라", '[others:ask]{message: "사진 한 장 찍어줘"}')
        idx, name = cams[0]
        cmd = [ff, "-hide_banner", "-f", "avfoundation", "-framerate", "30",
               "-i", str(idx), "-frames:v", "1", "-y", out]
        perm_hint = " (권한이면: 시스템 설정 > 개인정보 보호 > 카메라에서 백엔드 프로세스 허용)"
    elif sysname == "Windows":
        video, _ = _win_devices(ff)
        if not video:
            return _no_hw("카메라", '[others:ask]{message: "사진 한 장 찍어줘"}')
        name = video[0]
        cmd = [ff, "-hide_banner", "-f", "dshow", "-i", f"video={name}",
               "-frames:v", "1", "-y", out]
        perm_hint = ""
    else:
        if not os.path.exists("/dev/video0"):
            return _no_hw("카메라", '[others:ask]{message: "사진 한 장 찍어줘"}')
        name = "/dev/video0"
        cmd = [ff, "-hide_banner", "-f", "v4l2", "-i", name, "-frames:v", "1", "-y", out]
        perm_hint = ""

    p = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return {"success": True, "path": out, "source": "webcam", "device": str(name),
                "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    tail = (p.stderr or "").strip().splitlines()[-1:] or ["원인 미상"]
    return {"success": False, "error": f"웹캠 캡처 실패: {tail[0][:150]}{perm_hint}",
            "device": str(name)}


def _record(ff, sysname: str, duration: int) -> dict:
    """마이크 녹음 공통 — m4a 파일 경로 반환."""
    out = os.path.join(_outputs_dir(), f"listen_{time.strftime('%Y%m%d_%H%M%S')}.m4a")
    if sysname == "Darwin":
        _, audio = _mac_devices(ff)
        if not audio:
            return _no_hw("마이크", '[others:ask]{message: "지금 소리 받아써줘"}')
        idx, name = audio[0]
        cmd = [ff, "-hide_banner", "-f", "avfoundation", "-i", f":{idx}",
               "-t", str(duration), "-y", out]
    elif sysname == "Windows":
        _, audio = _win_devices(ff)
        if not audio:
            return _no_hw("마이크", '[others:ask]{message: "지금 소리 받아써줘"}')
        name = audio[0]
        cmd = [ff, "-hide_banner", "-f", "dshow", "-i", f"audio={name}",
               "-t", str(duration), "-y", out]
    else:
        name = "default(alsa)"
        cmd = [ff, "-hide_banner", "-f", "alsa", "-i", "default",
               "-t", str(duration), "-y", out]

    p = subprocess.run(cmd, capture_output=True, text=True, timeout=duration + 20)
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return {"success": True, "path": out, "source": "mic", "device": str(name),
                "duration_sec": duration,
                "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    tail = (p.stderr or "").strip().splitlines()[-1:] or ["원인 미상"]
    return {"success": False, "error": f"마이크 녹음 실패: {tail[0][:150]} "
            "(macOS 권한이면: 시스템 설정 > 개인정보 보호 > 마이크)", "device": str(name)}


def _gemini_stt(path: str) -> dict:
    """녹음 파일 → Gemini 오디오 이해로 받아쓰기. 키 없으면 정직히 불능."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {"ok": False, "error": "이 몸에 STT 수단이 없습니다(GEMINI_API_KEY 부재) — 녹음 파일만 반환."}
    try:
        import httpx
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        # ★2.5-flash 명시(gemini-flash-latest+thinkingBudget:0 은 400 — body_ask 선례)
        model = os.environ.get("BODY_ASK_COMPILE_MODEL", "gemini-2.5-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = {
            "contents": [{"parts": [
                {"inline_data": {"mime_type": "audio/mp4", "data": b64}},
                {"text": "이 오디오의 발화를 정확히 받아써라(한국어 우선). 발화가 없으면 정확히 (무음) 이라고만. 받아쓴 텍스트만 출력."},
            ]}],
            "generationConfig": {"maxOutputTokens": 800,
                                 "thinkingConfig": {"thinkingBudget": 0}},
        }
        with httpx.Client(timeout=60.0) as client:
            r = client.post(url, params={"key": api_key}, json=payload,
                            headers={"Content-Type": "application/json"})
            r.raise_for_status()
            data = r.json()
        parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts).strip()
        return {"ok": True, "text": text}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"STT 실패: {e}"}


def listen_desktop(op: str, tool_input: dict) -> dict:
    """데스크탑 마이크 프로브 — record=녹음 / transcribe=녹음+Gemini 받아쓰기."""
    ff = _ffmpeg()
    if not ff:
        return _no_ffmpeg()
    sysname = platform.system()

    if op == "record":
        duration = int(tool_input.get("duration_sec") or 10)
        return _record(ff, sysname, duration)

    # transcribe: timeout_sec 만큼 듣고 받아쓴다
    duration = int(tool_input.get("timeout_sec") or 8)
    rec = _record(ff, sysname, duration)
    if not rec.get("success"):
        return rec
    stt = _gemini_stt(rec["path"])
    if not stt.get("ok"):
        rec["note"] = stt.get("error")
        return rec  # 녹음은 성공 — STT 불능만 정직 병기
    return {"success": True, "text": stt["text"], "source": "mic+gemini",
            "path": rec["path"], "device": rec.get("device"),
            "duration_sec": duration, "measured_at": rec.get("measured_at")}
