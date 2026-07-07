"""
common.platform_utils — OS 이식성 헬퍼 (맥/윈도우/리눅스 공통)

개발·실행이 맥에서만 돌던 탓에 mpv·ffmpeg 탐색, 백그라운드 프로세스 기동/종료,
파일·URL 열기가 맥 전용 명령(pgrep/pkill/open/os.setsid)에 묶여 윈도우 설치에서 깨졌다.
이 모듈이 그 지점들을 한곳에서 크로스플랫폼으로 흡수한다.

원칙
  - 바이너리 탐색:   PATH(shutil.which) 우선 + OS별 표준 설치 경로 폴백(윈도우 .exe 포함).
  - 프로세스 관리:   psutil 로 통일(pgrep/pkill/tasklist 불필요, 전 OS 동일).
  - 백그라운드 기동: 유닉스=start_new_session, 윈도우=DETACHED_PROCESS(콘솔창 없이 분리).
  - 열기:            윈도우=os.startfile, 맥=open, 리눅스=xdg-open / URL=webbrowser.
"""
from __future__ import annotations

import os
import sys
import shutil
import subprocess
import webbrowser

IS_WINDOWS = os.name == "nt"
IS_MAC = sys.platform == "darwin"

try:
    import psutil  # 전 OS 프로세스 관리 (sense:host 등에서 이미 의존)
except Exception:  # pragma: no cover
    psutil = None


# ─────────────────────────────────────────────────────────────
# 바이너리 탐색
# ─────────────────────────────────────────────────────────────

# OS별 표준 설치 경로 폴백 — PATH 에 없을 때(GUI 실행이라 PATH 얇을 때) 훑는다.
_BINARY_FALLBACKS = {
    "mpv": {
        "darwin": ["/opt/homebrew/bin/mpv", "/usr/local/bin/mpv", "/usr/bin/mpv"],
        "win32": [
            r"C:\Program Files\mpv\mpv.exe",
            r"C:\ProgramData\chocolatey\bin\mpv.exe",
        ],
        "linux": ["/usr/bin/mpv", "/usr/local/bin/mpv"],
    },
    "ffmpeg": {
        "darwin": ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"],
        "win32": [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
        ],
        "linux": ["/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg"],
    },
    "ffprobe": {
        "darwin": ["/opt/homebrew/bin/ffprobe", "/usr/local/bin/ffprobe", "/usr/bin/ffprobe"],
        "win32": [
            r"C:\ffmpeg\bin\ffprobe.exe",
            r"C:\Program Files\ffmpeg\bin\ffprobe.exe",
            r"C:\ProgramData\chocolatey\bin\ffprobe.exe",
        ],
        "linux": ["/usr/bin/ffprobe", "/usr/local/bin/ffprobe"],
    },
    "ffplay": {
        "darwin": ["/opt/homebrew/bin/ffplay", "/usr/local/bin/ffplay", "/usr/bin/ffplay"],
        "win32": [
            r"C:\ffmpeg\bin\ffplay.exe",
            r"C:\Program Files\ffmpeg\bin\ffplay.exe",
            r"C:\ProgramData\chocolatey\bin\ffplay.exe",
        ],
        "linux": ["/usr/bin/ffplay", "/usr/local/bin/ffplay"],
    },
}


def find_binary(name: str, extra_paths: list[str] | None = None) -> str | None:
    """실행 파일 경로를 크로스플랫폼으로 찾는다. 못 찾으면 None.

    1) shutil.which (PATH, 윈도우는 .exe 자동 처리)
    2) 호출자가 준 extra_paths
    3) OS별 표준 설치 경로 폴백(_BINARY_FALLBACKS)
    """
    found = shutil.which(name)
    if found:
        return found

    candidates = list(extra_paths or [])
    # 자동 공급된 bin 디렉토리(ffmpeg_provision) — PATH 반영 전에도 찾도록 직접 확인
    bin_dir = os.environ.get("INDIEBIZ_BIN_DIR")
    if bin_dir:
        exe = name + (".exe" if IS_WINDOWS else "")
        candidates.append(os.path.join(bin_dir, exe))
    plat = "win32" if IS_WINDOWS else ("darwin" if IS_MAC else "linux")
    candidates += _BINARY_FALLBACKS.get(name, {}).get(plat, [])

    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def install_hint(binary: str) -> str:
    """바이너리가 없을 때 보여줄 OS별 설치 안내 문구."""
    hints = {
        "mpv": {
            "win32": "mpv가 없습니다. PowerShell에서 'winget install mpv' 또는 'choco install mpv', "
                     "혹은 https://mpv.io/installation/ 에서 설치 후 다시 시도하세요.",
            "darwin": "mpv가 없습니다. 'brew install mpv'로 설치 후 다시 시도하세요.",
            "linux": "mpv가 없습니다. 'sudo apt install mpv'(또는 배포판 패키지 매니저)로 설치하세요.",
        },
        "ffmpeg": {
            "win32": "FFmpeg가 없습니다. PowerShell에서 'winget install Gyan.FFmpeg' 또는 'choco install ffmpeg', "
                     "혹은 https://ffmpeg.org/download.html 에서 설치 후 PATH에 추가하세요.",
            "darwin": "FFmpeg가 없습니다. 'brew install ffmpeg'로 설치 후 다시 시도하세요.",
            "linux": "FFmpeg가 없습니다. 'sudo apt install ffmpeg'(또는 배포판 패키지 매니저)로 설치하세요.",
        },
    }
    # ffplay/ffprobe 는 ffmpeg 패키지에 포함 → 동일 안내
    key = "ffmpeg" if binary in ("ffplay", "ffprobe") else binary
    plat = "win32" if IS_WINDOWS else ("darwin" if IS_MAC else "linux")
    return hints.get(key, {}).get(plat, f"{binary}를 찾을 수 없습니다. 설치 후 다시 시도하세요.")


# ─────────────────────────────────────────────────────────────
# 백그라운드 프로세스 기동 (콘솔창 없이 분리 실행)
# ─────────────────────────────────────────────────────────────

def spawn_detached(cmd: list[str], **kwargs) -> subprocess.Popen:
    """백엔드와 분리된 백그라운드 프로세스로 실행(라디오/유튜브 오디오 등).

    유닉스: start_new_session=True (setsid — 세션 리더로 분리).
    윈도우: DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP (콘솔창 없이 분리).
    맥 전용 preexec_fn=os.setsid 를 대체한다.
    """
    kwargs.setdefault("stdout", subprocess.DEVNULL)
    kwargs.setdefault("stderr", subprocess.DEVNULL)
    if IS_WINDOWS:
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | flags
    else:
        kwargs.setdefault("start_new_session", True)
    return subprocess.Popen(cmd, **kwargs)


# ─────────────────────────────────────────────────────────────
# 프로세스 탐색/종료 (표식 = 명령줄 부분 문자열)
# ─────────────────────────────────────────────────────────────

def _iter_procs_by_marker(marker: str):
    """명령줄에 marker 를 포함한 프로세스를 순회. (psutil 필요)"""
    if not psutil:
        return
    me = os.getpid()
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            if proc.info["pid"] == me:
                continue
            cmdline = proc.info.get("cmdline") or []
            if marker in " ".join(cmdline):
                yield proc
        except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
            continue


def kill_processes_by_marker(marker: str) -> bool:
    """명령줄에 marker 가 박힌 프로세스를 모두 종료(전 OS). 하나라도 종료했으면 True.

    라디오 mpv 의 --force-media-title 표식처럼, 어느 백엔드가 띄웠든(고아 포함)
    표식만으로 찾아 정지·중복재생을 해결한다. psutil 이 없으면 유닉스 pgrep/pkill 폴백.
    """
    found = False
    if psutil:
        for proc in _iter_procs_by_marker(marker):
            try:
                proc.terminate()
                found = True
            except Exception:
                pass
        return found
    # psutil 없는 극단적 폴백 (유닉스 전용)
    if not IS_WINDOWS:
        try:
            subprocess.run(["pkill", "-f", marker], timeout=5)
            found = True
        except Exception:
            pass
    return found


def is_process_running_by_marker(marker: str) -> bool:
    """명령줄에 marker 가 박힌 프로세스가 살아있는지(전 OS)."""
    if psutil:
        for _ in _iter_procs_by_marker(marker):
            return True
        return False
    if not IS_WINDOWS:
        try:
            out = subprocess.run(["pgrep", "-f", marker], capture_output=True, text=True, timeout=5)
            return bool(out.stdout.strip())
        except Exception:
            return False
    return False


# ─────────────────────────────────────────────────────────────
# 파일·URL 열기
# ─────────────────────────────────────────────────────────────

def open_url(url: str) -> bool:
    """기본 브라우저로 URL 열기(전 OS). 맥 전용 'open' 대체."""
    try:
        return webbrowser.open(url)
    except Exception:
        return False


def open_path(path: str) -> bool:
    """OS 기본 앱으로 파일/폴더 열기. 윈도우=startfile, 맥=open, 리눅스=xdg-open."""
    try:
        if IS_WINDOWS:
            os.startfile(path)  # type: ignore[attr-defined]
        elif IS_MAC:
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False


def reveal_path(path: str) -> bool:
    """파일 탐색기에서 해당 항목을 선택한 채로 연다(윈도우 explorer /select, 맥 open -R)."""
    try:
        if IS_WINDOWS:
            subprocess.run(["explorer", "/select,", os.path.normpath(path)])
        elif IS_MAC:
            subprocess.run(["open", "-R", path])
        else:
            # 리눅스는 표준 'reveal'이 없어 상위 폴더를 연다
            subprocess.Popen(["xdg-open", os.path.dirname(path) or "."])
        return True
    except Exception:
        return False
