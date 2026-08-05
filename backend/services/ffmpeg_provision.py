"""ffmpeg_provision.py — 첫 실행 시 ffmpeg/ffplay/ffprobe 자동 공급.

라디오(ffplay 재생)·유튜브(ffplay 재생 + ffmpeg 다운로드/변환)는 시스템 바이너리 ffmpeg 가
있어야 동작한다. mpv/ffmpeg 는 pip 가 아닌 OS 실행 파일이라 자동 설치가 안 돼, fresh 윈도우
설치에서 "재생 불가"였다. 이 모듈이 첫 실행에 ffmpeg 정적 빌드(ffplay 포함)를 내려받아
userData/bin 에 심는다 → 사용자 무설치(OOTB).

설계는 hippocampus_provision 패턴을 그대로 본뜬다: 백그라운드·멱등·시끄럽게(로그), 이미
있으면 아무것도 안 함, 실패해도 부팅·본체엔 영향 없음(안내로 폴백).

- 윈도우: gyan.dev essentials zip(ffmpeg/ffplay/ffprobe.exe) → userData/bin 전개. 다운로드는
  stdlib(urllib/zipfile)만.
- 맥/리눅스: 신뢰할 만한 ffplay 정적 빌드가 없어 자동 공급 대상이 아니다 → 시스템 패키지
  매니저(brew/apt)로 설치(라디오/유튜브가 install_hint 안내). 개발/사용 맥은 대개 homebrew 보유.

공급된 bin 디렉토리는 PATH + INDIEBIZ_BIN_DIR 로 노출 → common.platform_utils.find_binary 가 인식.
"""
import os
import threading
import tempfile
import zipfile
from pathlib import Path
from urllib.request import urlopen, Request

# 윈도우 정적 빌드 고정 URL. ★반드시 ffplay 포함 빌드여야 함(라디오 재생용).
# BtbN win64-gpl = ffmpeg/ffplay/ffprobe.exe 모두 포함, "latest" 고정 URL.
# (gyan 'essentials' 는 ffplay 미포함이라 부적합 — 'full' 이나 BtbN 를 쓸 것.)
# 다른 곳에 두려면 INDIEBIZ_FFMPEG_URL 로 덮어씀.
DEFAULT_WIN_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"

_WANT = ("ffmpeg", "ffplay", "ffprobe")

_provisioning = threading.Event()  # 다운로드 진행 중 표식(핸들러가 "준비 중" 안내에 사용)


def _base() -> Path:
    from runtime_utils import get_base_path
    return get_base_path()


def _bin_dir() -> Path:
    d = _base() / "bin"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _exe(name: str) -> str:
    return name + (".exe" if os.name == "nt" else "")


def register_bin_path():
    """공급된 bin 디렉토리를 PATH · INDIEBIZ_BIN_DIR 에 노출한다(멱등).

    이미 공급돼 있던(재시작 후) ffmpeg 도 find_binary 가 찾도록, 부팅 시 항상 호출.
    """
    d = str(_base() / "bin")
    os.environ["INDIEBIZ_BIN_DIR"] = d  # find_binary 가 직접 확인
    if os.path.isdir(d):
        sep = os.pathsep
        parts = os.environ.get("PATH", "").split(sep)
        if d not in parts:
            os.environ["PATH"] = d + sep + os.environ.get("PATH", "")


def ffmpeg_present() -> bool:
    """ffmpeg·ffplay 둘 다 찾을 수 있으면 True(시스템 설치 or 이미 공급됨)."""
    from common.platform_utils import find_binary
    return bool(find_binary("ffmpeg") and find_binary("ffplay"))


def is_provisioning() -> bool:
    return _provisioning.is_set()


def _download_windows(url: str = None) -> bool:
    """윈도우 ffmpeg essentials zip → userData/bin 에 ffmpeg/ffplay/ffprobe.exe 전개."""
    url = url or os.environ.get("INDIEBIZ_FFMPEG_URL") or DEFAULT_WIN_URL
    bin_dir = _bin_dir()
    tmp = Path(tempfile.gettempdir()) / "ffmpeg_dl.zip"
    print(f"[ffmpeg공급] 다운로드 시작: {url}")
    try:
        req = Request(url, headers={"User-Agent": "indiebizOS"})
        total = 0
        with urlopen(req, timeout=120) as resp, open(tmp, "wb") as f:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                total += len(chunk)
        print(f"[ffmpeg공급] 다운로드 완료 {total / 1024 / 1024:.0f}MB → 전개 중")
        # zip 안 어딘가의 bin/ffmpeg.exe 등만 골라 평탄하게 추출
        wanted = {_exe(n) for n in _WANT}
        extracted = 0
        with zipfile.ZipFile(tmp) as z:
            for member in z.namelist():
                base = os.path.basename(member)
                if base in wanted:
                    with z.open(member) as src, open(bin_dir / base, "wb") as dst:
                        dst.write(src.read())
                    extracted += 1
        tmp.unlink(missing_ok=True)
        register_bin_path()
        ok = extracted >= 1 and (bin_dir / _exe("ffplay")).exists()
        print(f"[ffmpeg공급] 전개 {'완료' if ok else '실패(zip 레이아웃 확인)'} — {extracted}개")
        return ok
    except Exception as e:
        print(f"[ffmpeg공급] 다운로드 실패(무시, 안내로 폴백): {e}")
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return False


def ensure_ffmpeg() -> bool:
    """ffmpeg/ffplay 확보(동기). 이미 있으면 즉시 True. 윈도우면 다운로드, 그 외는 False(시스템 설치 안내)."""
    register_bin_path()
    if ffmpeg_present():
        return True
    if os.name != "nt":
        return False  # 맥/리눅스는 시스템 패키지 매니저(brew/apt)로 — install_hint 안내
    if _provisioning.is_set():
        return False  # 이미 다른 스레드가 받는 중
    _provisioning.set()
    try:
        return _download_windows()
    finally:
        _provisioning.clear()


def provision_async(enabled: bool = True):
    """첫 실행 ffmpeg 공급을 백그라운드로. 이미 있으면 즉시 종료(조용). 데스크탑 진입점(api.py)에서 호출."""
    register_bin_path()  # 재시작 후 이미 공급된 것 즉시 노출
    if not enabled:
        return
    if ffmpeg_present():
        return  # 시스템 설치 or 이미 공급 — 조용히 통과(개발기 맥 homebrew 포함)
    if os.name != "nt":
        return  # 맥/리눅스 자동 공급 대상 아님

    def _run():
        try:
            if ensure_ffmpeg():
                print("[ffmpeg공급] ✅ ffmpeg 완비 — 라디오·유튜브 재생 준비 완료")
            else:
                print("[ffmpeg공급] ⚠️ 확보 실패 — 네트워크 확인 후 재시작 시 재시도")
        except Exception as e:
            print(f"[ffmpeg공급] 공급 중 오류(무시): {e}")

    threading.Thread(target=_run, daemon=True, name="ffmpeg-provision").start()
