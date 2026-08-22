"""
runtime_utils.py - 번들된 런타임 경로 유틸리티
IndieBiz OS Core

Electron 앱으로 배포될 때 번들된 Python/Node.js 런타임을 사용하고,
개발 환경에서는 시스템에 설치된 런타임을 사용합니다.
"""

import os
import sys
import platform
from pathlib import Path


def get_base_path() -> Path:
    """
    IndieBiz OS 기본 경로 반환
    프로덕션에서는 INDIEBIZ_BASE_PATH 환경변수 (userData),
    개발 모드에서는 backend의 상위 폴더 (indiebizOS root)
    """
    env_path = os.environ.get("INDIEBIZ_BASE_PATH")
    if env_path:
        return Path(env_path)
    return Path(__file__).parent.parent.parent


def get_data_path() -> Path:
    """데이터 경로 반환 (base_path/data)"""
    p = get_base_path() / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def in_test_process() -> bool:
    """이 프로세스가 자기시험인가 — **시험이 만든 흔적은 몸의 삶이 아니다**.

    시험은 상한·순환·오류 경로를 *일부러* 밟고, 실행기억·건강·주행기록에 그 의도된
    자국을 남긴다. 그게 실사용과 같은 칸에 쌓이면 몸은 자기 삶을 잘못 읽는다
    (B18-1 실측: 재귀 깊이 픽스처의 의도된 실패가 "만성 실패: self:workflow" 경보를
    사용자 알림함까지 올렸다).

    픽스처 이름 규약(`_t_` 접두 등)으로 거르지 않는 이유: 규약은 시험마다 다르고 새 시험이
    다시 감염시킨다. **프로세스 정체**로 판정하면 시험 전체가 한 번에 격리된다.

    ★단일 소스(2026-08-22): 원래 pulse_db 안에만 있었는데 같은 판정이 주행기록에도
    필요해졌다(episode_log). 판정을 복제하면 두 원장의 '시험'이 서로 다른 뜻이 된다 —
    base 층에 한 벌만 두고 datastore·base 가 함께 부른다.
    """
    try:
        if "pytest" in sys.modules:
            return True
        argv0 = os.path.basename(sys.argv[0] or "")
        return argv0.startswith("test_") and argv0.endswith(".py")
    except Exception:
        return False


# ============================================================
# Playwright 브라우저 주소 — 단일 소스
# ============================================================
# 이 저장소는 브라우저 바이너리를 기본 캐시(~/Library/Caches/ms-playwright 등)가
# 아니라 base_path/ms-playwright 에 둔다. 이유=설치본 이식성: 프로덕션에서
# get_base_path() 는 userData(항상 쓰기가능)라, 읽기전용일 수 있는 앱 번들과
# 무관하게 런타임 자동설치(install_python_dependency)와 실행이 같은 곳을 본다.
#
# ★단일 소스인 이유(2026-08-15 실측): 주소가 두 군데서 계산되면 반드시 갈라진다.
#   ① 받는 곳: `playwright install` 을 PLAYWRIGHT_BROWSERS_PATH 없이 돌리면 기본 캐시로 간다.
#   ② 보는 곳: 아래 setup 이 base_path/ms-playwright 를 본다.
#   playwright 를 올리면 빌드 번호가 바뀌므로(1228→1234) 그 순간 어긋나고,
#   증상은 조용하다 — 슬라이드·영상·글자얹기·browser-action 이 *쓸 때* 처음 터진다.
#   그래서 주소 계산은 여기 한 곳, 설치는 조리법(scripts/bootstrap.py)의 일부,
#   어긋남은 12시간 자가점검이 신고한다(scripts/check_playwright_browsers.py).

# `playwright install chromium` 이 실제로 내려놓는 것들(브라우저+녹화용 ffmpeg).
_PLAYWRIGHT_REQUIRED_BROWSERS = ("chromium", "chromium-headless-shell", "ffmpeg")


def get_playwright_browsers_path() -> Path:
    """브라우저 바이너리가 사는 곳 — 받는 쪽·보는 쪽 공통 주소.

    이미 환경변수가 있으면 그것이 진실(사용자·상위 런처가 정한 것을 뒤집지 않는다).
    """
    env = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if env:
        return Path(env)
    return get_base_path() / "ms-playwright"


def setup_playwright_browsers_path() -> str:
    """PLAYWRIGHT_BROWSERS_PATH 를 이 프로세스와 자식 프로세스에 고정하고 그 값을 반환.

    ★부팅 경로와 무관하게 항상 같은 값이어야 한다 — 이 호출이
    setup_bundled_runtime_paths() 의 '번들 파이썬 아니면 조기 return' 안쪽에 있던 탓에
    Electron 기동(INDIEBIZ_PYTHON_PATH 있음)은 저장소 안을, start.sh 기동은 기본 캐시를
    보고 있었다. 같은 설치가 기동 방법에 따라 다른 곳을 보는 것이 드리프트의 뿌리다.
    """
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(get_base_path() / "ms-playwright"))
    return os.environ["PLAYWRIGHT_BROWSERS_PATH"]


def check_playwright_browsers() -> dict:
    """설치된 playwright 가 기대하는 브라우저 빌드가 그 주소에 실재하는가.

    파일 읽기만 한다(playwright 를 import 하지 않음 — greenlet ABI 파손 같은
    import 사고를 이 점검이 대신 겪지 않도록). 기대 빌드 번호는 playwright 패키지가
    동봉한 driver/package/browsers.json 이 진실 소스.

    반환: {status, ok, browsers_path, playwright_version, expected[], missing[], stale[], note}
      status: ok | missing | playwright_missing | error
      stale: 같은 브라우저의 다른(옛) 빌드 폴더 — 정리 후보(삭제는 사용자 결정)
    """
    import json as _json

    out = {"status": "error", "ok": False, "browsers_path": None,
           "playwright_version": None, "expected": [], "missing": [], "stale": [], "note": ""}
    try:
        browsers_path = get_playwright_browsers_path()
        out["browsers_path"] = str(browsers_path)

        try:
            import importlib.util
            spec = importlib.util.find_spec("playwright")
        except Exception:
            spec = None
        if spec is None or not spec.origin:
            out.update(status="playwright_missing", ok=True,
                       note="playwright 미설치 — 브라우저 점검 대상 아님(의존성 감사 소관)")
            return out

        try:
            import importlib.metadata as _md
            out["playwright_version"] = _md.version("playwright")
        except Exception:
            pass

        manifest = Path(spec.origin).parent / "driver" / "package" / "browsers.json"
        if not manifest.exists():
            out["note"] = f"browsers.json 없음: {manifest}"
            return out
        entries = _json.loads(manifest.read_text(encoding="utf-8")).get("browsers") or []

        wanted = {}
        for e in entries:
            name = e.get("name")
            if name in _PLAYWRIGHT_REQUIRED_BROWSERS and e.get("revision"):
                wanted[name] = str(e["revision"])
        if not wanted:
            out["note"] = f"browsers.json 에서 기대 빌드를 못 찾음: {manifest}"
            return out

        for name, rev in sorted(wanted.items()):
            # playwright 폴더 관례: 이름의 '-' 는 '_' (chromium-headless-shell → chromium_headless_shell)
            d = browsers_path / f"{name.replace('-', '_')}-{rev}"
            # INSTALLATION_COMPLETE = playwright 가 다운로드 완주 때만 남기는 표식
            # (폴더만 있고 반쯤 받아진 상태를 '있음' 으로 오독하지 않기 위해)
            present = d.is_dir() and (d / "INSTALLATION_COMPLETE").exists()
            out["expected"].append({"name": name, "revision": rev, "dir": str(d), "present": present})
            if not present:
                out["missing"].append(f"{name}-{rev}")

        if browsers_path.is_dir():
            for name, rev in sorted(wanted.items()):
                prefix = f"{name.replace('-', '_')}-"
                for d in sorted(browsers_path.glob(prefix + "*")):
                    # 'chromium-' 글롭이 'chromium_headless_shell-' 까지 먹지 않게 정확 분해
                    if not d.is_dir() or d.name[len(prefix):].strip("0123456789") != "":
                        continue
                    if d.name != f"{prefix}{rev}":
                        out["stale"].append(str(d))

        out["ok"] = not out["missing"]
        out["status"] = "ok" if out["ok"] else "missing"
        if out["missing"]:
            out["note"] = (f"playwright {out['playwright_version'] or '?'} 가 기대하는 빌드가 "
                           f"{browsers_path} 에 없음: {', '.join(out['missing'])} — "
                           f"`python scripts/check_playwright_browsers.py --install` 로 받으세요")
        return out
    except Exception as e:
        out["note"] = f"점검 실패: {e}"
        return out


def get_runtime_paths() -> dict:
    """
    번들된 런타임 경로 또는 시스템 런타임 반환

    우선순위:
    1. INDIEBIZ_PYTHON_PATH / INDIEBIZ_NODE_PATH 환경변수
    2. INDIEBIZ_RUNTIME_PATH 환경변수의 runtime 경로
    3. 폴더 탐색으로 runtime 찾기
    4. 시스템 런타임 (폴백)

    Returns:
        {"python": "python3 경로", "node": "node 경로"}
    """
    is_windows = platform.system() == "Windows"

    # 기본값 (시스템 설치된 런타임)
    python_cmd = "python" if is_windows else "python3"
    node_cmd = "node"

    # 1. 환경변수에서 직접 경로 확인 (가장 확실한 방법)
    env_python = os.environ.get("INDIEBIZ_PYTHON_PATH")
    if env_python and Path(env_python).exists():
        python_cmd = env_python

    env_node = os.environ.get("INDIEBIZ_NODE_PATH")
    if env_node and Path(env_node).exists():
        node_cmd = env_node

    # 이미 환경변수로 설정되었으면 바로 반환
    if env_python or env_node:
        # 나머지 하나도 runtime_path에서 찾아보기
        env_runtime = os.environ.get("INDIEBIZ_RUNTIME_PATH")
        if env_runtime:
            runtime_path = Path(env_runtime)
            if runtime_path.exists():
                if not env_python:
                    if is_windows:
                        bundled_python = runtime_path / "python" / "python.exe"
                    else:
                        bundled_python = runtime_path / "python" / "bin" / "python3"
                    if bundled_python.exists():
                        python_cmd = str(bundled_python)

                if not env_node:
                    if is_windows:
                        bundled_node = runtime_path / "node" / "node.exe"
                    else:
                        bundled_node = runtime_path / "node" / "bin" / "node"
                    if bundled_node.exists():
                        node_cmd = str(bundled_node)

        return {"python": python_cmd, "node": node_cmd}

    # 2. INDIEBIZ_RUNTIME_PATH 환경변수에서 runtime 경로 확인
    env_runtime = os.environ.get("INDIEBIZ_RUNTIME_PATH")
    if env_runtime:
        runtime_path = Path(env_runtime)
        if runtime_path.exists():
            if is_windows:
                bundled_python = runtime_path / "python" / "python.exe"
                bundled_node = runtime_path / "node" / "node.exe"
            else:
                bundled_python = runtime_path / "python" / "bin" / "python3"
                bundled_node = runtime_path / "node" / "bin" / "node"

            if bundled_python.exists():
                python_cmd = str(bundled_python)
            if bundled_node.exists():
                node_cmd = str(bundled_node)

            return {"python": python_cmd, "node": node_cmd}

    # 3. 폴더 탐색 (개발 환경 또는 환경변수 미설정 시)
    backend_path = Path(__file__).parent.parent

    if getattr(sys, 'frozen', False):
        base_path = Path(sys.executable).parent
    else:
        base_path = backend_path.parent

    runtime_path = base_path / "runtime"

    # macOS/Linux용 Electron 앱 경로도 확인
    if not runtime_path.exists():
        resources_path = base_path.parent / "Resources" / "runtime"
        if resources_path.exists():
            runtime_path = resources_path

    # Python 런타임
    if runtime_path.exists():
        if is_windows:
            bundled_python = runtime_path / "python" / "python.exe"
        else:
            bundled_python = runtime_path / "python" / "bin" / "python3"

        if bundled_python.exists():
            python_cmd = str(bundled_python)

    # Node.js 런타임
    if runtime_path.exists():
        if is_windows:
            bundled_node = runtime_path / "node" / "node.exe"
        else:
            bundled_node = runtime_path / "node" / "bin" / "node"

        if bundled_node.exists():
            node_cmd = str(bundled_node)

    return {"python": python_cmd, "node": node_cmd}


# 런타임 경로 캐시
_runtime_paths = None


def get_python_cmd() -> str:
    """Python 실행 경로 반환"""
    global _runtime_paths
    if _runtime_paths is None:
        _runtime_paths = get_runtime_paths()
    return _runtime_paths["python"]


def get_node_cmd() -> str:
    """Node.js 실행 경로 반환"""
    global _runtime_paths
    if _runtime_paths is None:
        _runtime_paths = get_runtime_paths()
    return _runtime_paths["node"]


def install_python_dependency(package: str, timeout: int = 300) -> dict:
    """런타임에 파이썬 라이브러리를 쓰기가능한 userData(pylibs)에 설치한다.

    도구 의존성 누락([sense:search]의 ddgs 등)을 사용자 승낙 후 그 자리에서 채우기 위함.
    - 번들 site-packages 는 읽기전용일 수 있어 --target userData/pylibs 로 설치(항상 쓰기가능).
      pylibs 는 setup_bundled_runtime_paths 가 sys.path 에 올려 두므로 설치 즉시 import 가능.
    - package 가 'playwright' 계열이면 chromium 브라우저 바이너리(playwright install chromium)도
      userData/ms-playwright 에 함께 받는다(browser-action 이 그 경로에서 찾음).

    반환: {success: bool, message: str, log: str}
    """
    import subprocess
    package = (package or "").strip()
    if not package:
        return {"success": False, "message": "설치할 라이브러리명(package)이 비었습니다."}
    # 안전: 공백·셸메타 차단(단일 패키지 스펙만 허용)
    if any(c in package for c in " ;&|`$\n"):
        return {"success": False, "message": f"허용되지 않는 패키지명: {package!r} (한 번에 하나씩, 셸 메타문자 불가)"}

    py = get_python_cmd()
    target = get_base_path() / "pylibs"
    target.mkdir(parents=True, exist_ok=True)
    target_str = str(target)
    log = []
    try:
        r = subprocess.run(
            [py, "-m", "pip", "install", "--upgrade", "--target", target_str, package],
            capture_output=True, text=True, timeout=timeout,
        )
        if r.stdout:
            log.append(r.stdout[-1500:])
        if r.returncode != 0:
            return {"success": False, "message": f"pip 설치 실패: {package}",
                    "log": (r.stderr or r.stdout or "")[-1500:]}
        if target_str not in sys.path:
            sys.path.insert(0, target_str)  # 설치 즉시 import 가능하게

        if package.lower().split("==")[0].split(">")[0].strip() in ("playwright",):
            # 주소는 단일 소스에서 (bootstrap·자가점검·실행이 보는 그 곳)
            browsers = str(get_playwright_browsers_path())
            env = dict(os.environ)
            env["PLAYWRIGHT_BROWSERS_PATH"] = browsers
            env["PYTHONPATH"] = target_str + os.pathsep + env.get("PYTHONPATH", "")
            r2 = subprocess.run(
                [py, "-m", "playwright", "install", "chromium"],
                capture_output=True, text=True, timeout=max(timeout, 600), env=env,
            )
            if r2.returncode != 0:
                return {"success": False, "message": "playwright 는 설치됐으나 chromium 브라우저 다운로드 실패",
                        "log": (r2.stderr or r2.stdout or "")[-1500:]}
            log.append("chromium 브라우저 설치 완료")

        return {"success": True, "message": f"'{package}' 설치 완료", "log": "\n".join(log)[-1500:]}
    except subprocess.TimeoutExpired:
        return {"success": False, "message": f"설치 시간 초과({timeout}초): {package}"}
    except Exception as e:
        return {"success": False, "message": f"설치 중 오류: {e}"}


def setup_bundled_runtime_paths():
    """
    백엔드 시작 시 호출 — 번들 Python의 Scripts/bin과 site-packages를
    os.environ['PATH']와 sys.path에 등록.

    이렇게 하면:
    - subprocess.run(['yt-dlp', ...]) 등이 번들 Python에 pip 설치된 CLI를 찾음
    - import yt_dlp 등이 번들 Python의 site-packages에서 모듈을 찾음

    개발 환경(시스템 Python)에서는 해당 경로가 존재하지 않으므로 안전하게 무시됨.
    """
    # --- 0. playwright 브라우저 주소 (번들 여부와 무관 — 아래 조기 return 보다 위) ---
    # 이 줄이 조기 return 아래 있던 탓에 같은 설치가 기동 방법에 따라 다른 곳을 봤다:
    # Electron 기동(INDIEBIZ_PYTHON_PATH 있음)=저장소 안 / start.sh 기동=기본 캐시.
    try:
        setup_playwright_browsers_path()
    except Exception as e:
        print(f"[Runtime] playwright 브라우저 경로 설정 실패(무시): {e}")

    is_windows = platform.system() == "Windows"
    python_cmd = get_python_cmd()
    python_path = Path(python_cmd)

    # 시스템 Python이면 설정 불필요 (절대경로가 아닌 명령어 이름만 있는 경우)
    if not python_path.is_absolute():
        return

    if not python_path.exists():
        return

    python_dir = python_path.parent  # python.exe가 있는 폴더

    # --- 1. Scripts/bin 디렉토리를 PATH에 추가 (subprocess용) ---
    if is_windows:
        scripts_dir = python_dir / "Scripts"
    else:
        scripts_dir = python_dir  # Unix에서는 bin/ 자체가 python이 있는 폴더

    if scripts_dir.exists():
        scripts_str = str(scripts_dir)
        current_path = os.environ.get("PATH", "")
        if scripts_str not in current_path:
            os.environ["PATH"] = scripts_str + os.pathsep + current_path
            print(f"[Runtime] PATH에 추가: {scripts_str}")

    # Windows에서는 python.exe가 있는 폴더 자체도 PATH에 추가
    if is_windows:
        python_dir_str = str(python_dir)
        current_path = os.environ.get("PATH", "")
        if python_dir_str not in current_path:
            os.environ["PATH"] = python_dir_str + os.pathsep + current_path

    # --- 2. site-packages를 sys.path에 추가 (import용) ---
    if is_windows:
        site_packages = python_dir / "Lib" / "site-packages"
    else:
        # Unix: python_dir = .../bin/, site-packages = .../lib/pythonX.Y/site-packages
        py_ver = f"python{sys.version_info.major}.{sys.version_info.minor}"
        site_packages = python_dir.parent / "lib" / py_ver / "site-packages"

    if site_packages.exists():
        sp_str = str(site_packages)
        if sp_str not in sys.path:
            sys.path.insert(0, sp_str)
            print(f"[Runtime] sys.path에 추가: {sp_str}")

    # --- 2.5. userData 쓰기가능 라이브러리 폴더 (런타임 자동설치 [self:install_lib]가 여기 설치) ---
    # 번들 site-packages(resources)는 프로덕션에서 읽기전용일 수 있어(맥 /Applications 등),
    # 런타임 설치는 항상 쓰기가능한 userData(get_base_path)로 target 한다. 그 폴더를 sys.path 최상단에.
    try:
        user_libs = get_base_path() / "pylibs"
        user_libs.mkdir(parents=True, exist_ok=True)
        ul_str = str(user_libs)
        if ul_str not in sys.path:
            sys.path.insert(0, ul_str)
            print(f"[Runtime] sys.path에 추가(userData libs): {ul_str}")
        # (playwright 브라우저 주소는 이 함수 맨 위 0단계에서 이미 고정됐다)
    except Exception as e:
        print(f"[Runtime] userData libs 설정 실패(무시): {e}")

    # --- 3. Node.js도 PATH에 추가 ---
    node_cmd = get_node_cmd()
    node_path = Path(node_cmd)
    if node_path.is_absolute() and node_path.exists():
        node_dir = str(node_path.parent)
        current_path = os.environ.get("PATH", "")
        if node_dir not in current_path:
            os.environ["PATH"] = node_dir + os.pathsep + current_path
            print(f"[Runtime] PATH에 Node.js 추가: {node_dir}")


# ============================================================
# 자기수용감각 (Proprioception) — 자기 몸 감지
# ============================================================
# 같은 코드베이스가 폰/맥(PC)에서 모두 돈다. 실행 위치를 프롬프트에
# 정적으로 박으면 다른 몸에서 돌 때 거짓말이 되므로, 런타임에 감지한다.
# 부팅 때 1회 감지 후 캐시 (한 프로세스 안에서 몸은 안 바뀜).

_BODY_CACHE = None


def _sysctl(key: str) -> str:
    """macOS sysctl 단일 키 조회 (실패 시 빈 문자열)."""
    try:
        import subprocess
        out = subprocess.run(
            ["sysctl", "-n", key], capture_output=True, text=True, timeout=3
        )
        return out.stdout.strip()
    except Exception:
        return ""


def _detect_android_body() -> dict:
    """폰 프로세스 — Chaquopy로 android.os.Build 읽기 (검증된 jclass 경로)."""
    info = {"kind": "phone", "device": "안드로이드 폰", "os": "Android", "arch": ""}
    try:
        from java import jclass
        Build = jclass("android.os.Build")
        manufacturer = str(getattr(Build, "MANUFACTURER", "") or "").strip()
        model = str(getattr(Build, "MODEL", "") or "").strip()
        device_name = " ".join(p for p in [manufacturer, model] if p)
        if device_name:
            info["device"] = device_name
        try:
            Version = jclass("android.os.Build$VERSION")
            release = str(getattr(Version, "RELEASE", "") or "").strip()
            if release:
                info["os"] = f"Android {release}"
        except Exception:
            pass
        try:
            abis = Build.SUPPORTED_ABIS
            if abis:
                info["arch"] = str(abis[0])
        except Exception:
            pass
    except Exception:
        pass
    info["label"] = f"안드로이드 폰 · {info['device']} · {info['os']}".strip(" ·")
    return info


def _detect_desktop_body() -> dict:
    """맥/PC 프로세스 — platform + macOS sysctl로 칩/OS 정체성 읽기."""
    system = platform.system()        # Darwin / Windows / Linux
    arch = platform.machine()         # arm64 / x86_64
    info = {"arch": arch}
    if system == "Darwin":
        info["kind"] = "mac"
        chip = _sysctl("machdep.cpu.brand_string") or (
            "Apple Silicon" if arch == "arm64" else "Intel Mac"
        )
        hw_model = _sysctl("hw.model")
        ver = platform.mac_ver()[0] or ""
        info["device"] = chip + (f" ({hw_model})" if hw_model else "")
        info["os"] = f"macOS {ver}".strip()
        info["label"] = f"맥 · {chip} · macOS {ver}".strip(" ·")
    elif system == "Windows":
        info["kind"] = "pc"
        info["device"] = platform.processor() or "Windows PC"
        info["os"] = f"Windows {platform.release()}"
        info["label"] = f"PC · {info['device']} · {info['os']}".strip(" ·")
    else:
        info["kind"] = "pc"
        info["device"] = platform.processor() or f"{system} machine"
        info["os"] = f"{system} {platform.release()}"
        info["label"] = f"{system} · {info['device']}".strip(" ·")
    return info


def detect_body() -> dict:
    """지금 이 프로세스가 어느 '몸'에서 도는지 감지 (부팅 1회·캐시).

    INDIEBIZ_PROFILE 로 폰/맥을 가르고, 각 몸의 네이티브 경로
    (Android Build / macOS sysctl)로 상세 정체성을 읽는다. 전 구간
    방어 — 감지 실패해도 부팅을 막지 않는다.

    Returns:
        {profile, kind, device, os, arch, label}
        label = 프롬프트용 한 줄 (예: "맥 · Apple M4 Pro · macOS 15.3")
    """
    global _BODY_CACHE
    if _BODY_CACHE is not None:
        return _BODY_CACHE

    profile = os.environ.get("INDIEBIZ_PROFILE", "")
    if not profile:
        # env 미설정 시 OS 자기-감지로 profile 유도(몸은 이미 자기가 뭔지 안다 —
        # _detect_desktop_body 가 Windows/Linux 도 정확히 읽음). env override 는 자기-감지가
        # *거짓말하는* 몸에만 필요: 안드로이드 파이썬은 platform.system()=='Linux' 로 위장하므로
        # phone_api 가 INDIEBIZ_PROFILE='phone' 을 명시 주입한다. 맥은 'mac' 그대로(무변경).
        profile = {"Darwin": "mac", "Windows": "windows", "Linux": "linux"}.get(
            platform.system(), "mac")
    body = {"profile": profile}
    if profile == "phone":
        body.update(_detect_android_body())
    else:
        body.update(_detect_desktop_body())

    _BODY_CACHE = body
    return body


# ── 능력 자기-모델 (capability self-portrait) ──
# 최소: "나는 누구다" + "내 마이크로 명령어 집합" + "빌릴 수 있는 상대"만. 큐레이션 액션 목록은 IBL
# 어휘가 따로 가르치고, 실시간 연결 상태는 월드펄스 생성 주기와 어긋나 stale 거짓말이 되므로 넣지 않는다
# (피어 닿는지는 실행 시점에 엔진이 phone_unreachable 로 명확히 알려준다). 단 마이크로 집합은
# *부팅 시점 정적 능력*(같은 프로세스에서 안 바뀜)이라 stale 위험 없음 → 자화상에 포함.


def detect_local_micros() -> dict:
    """이 몸의 Layer0 마이크로 명령어(실행/렌더 원시) 집합 + *만능 탈출구*.

    capability 기반(INDIEBIZ_PROFILE 무관 — 무포크). 각 몸은 고정 IBL 어휘를 벗어나는 *하나의*
    만능 탈출구를 가진다(나머지는 그걸 통하거나 부재):
    - 맥/PC: 탈출구=**shell**. 셸이 python·node 등을 띄운다(셸 ⊇ python). standalone python3 존재.
    - 폰: 탈출구=**python**(인-프로세스). standalone python3 가 없어 셸이 python 을 못 띄우니 역전 —
      python 이 만능(약한 toybox sh 는 subprocess 로 *포섭*, jclass 로 안드로이드 SDK 전체 도달).
      그래서 셸은 '빌림'이 아니라 python 에 포섭됨 → borrowed 에 넣지 않는다.
    Returns: {"escape": "shell"|"python", "local": [...], "borrowed": [...]}.
    """
    import shutil
    # 데스크탑 판별 프록시 = standalone python3 바이너리 유무(핸들러 _has_standalone_python 과 동일 신호,
    # 안드로이드 toybox sh 오판 회피). 있으면 맥/PC(셸이 만능), 없으면 폰(python 이 만능).
    py_cmd = os.environ.get("INDIEBIZ_PYTHON_PATH") or ("python" if os.name == "nt" else "python3")
    has_standalone_py = Path(py_cmd).exists() if os.path.isabs(py_cmd) else (shutil.which(py_cmd) is not None)
    node = os.environ.get("INDIEBIZ_NODE_PATH") or "node"
    node_ok = Path(node).exists() if os.path.isabs(node) else (shutil.which(node) is not None)

    if has_standalone_py:
        # 맥/PC — 셸이 만능 탈출구(python 은 셸을 통해 띄움).
        local = ["shell", "python", "html"] + (["node"] if node_ok else [])
        borrowed = [] if node_ok else ["node"]
        return {"escape": "shell", "local": local, "borrowed": borrowed}
    # 폰 — python 이 만능 탈출구(약한 sh 포섭 + jclass SDK). 셸은 별도 원시로 세지 않음.
    return {"escape": "python", "local": ["python", "html"], "borrowed": ["node"]}


def _self_identity(body: dict) -> str:
    """정체성 한 줄 — *나를 올바른 class로* 부르는 환원 불가능한 씨앗만.

    선언적 자기인지의 힘은 올바른 class 명명에 있다. 그 핵심 사실 하나만 박고,
    따라 나오는 것(샌드박스·scoped storage·권한·Doze·아웃바운드 …)은 AI 가 이미
    아니까 *연역에 맡긴다*. 열거 = 연역 불신 = 토큰 낭비. 부팅 시점 정적이라 stale 없음.
    """
    kind = body.get("kind", "mac")
    if kind == "phone":
        # 핵심: Chaquopy류(내가 만든 앱에 Python 내장) + manifest 권한 범위 안 SDK 전체 in-process 호출.
        # 이 한 사실에서 샌드박스·권한·Doze·아웃바운드가 다 따라 나온다 → 열거 안 함.
        return (
            "나는 Chaquopy류 — 내가 만든 안드로이드 앱에 내장된 **in-process Python**이고, "
            "manifest 에 선언한 권한 범위 안에서 `from java import jclass` 로 **안드로이드 "
            "SDK 전체를 인-프로세스 호출**한다. 앱이 곧 내 권한 봉투다(루트·시스템 아님)."
        )
    # 플랫폼 class 만(버전 제외) — 버전은 윗줄 body 라벨에 있고, 여기 넣으면 OS 업데이트 때
    # stale. "macOS 26.5.1" → "macOS", "Windows 11" → "Windows".
    osname = ((body.get("os") or "").split() or [""])[0] or ("macOS" if kind == "mac" else "데스크톱 OS")
    # 핵심: 사용자 권한 전체(샌드박스 아님) + 상시 켜짐·인바운드 도달. 둘 다 하드웨어 사실일 뿐
    # 위계 아님(맥=중심/폰=부속 식으로 쓰지 말 것 — 관계는 대칭인 peer 줄이 따로 담는다). 나머지 연역.
    return (
        f"나는 {osname} 위에서 **로그인 사용자 권한으로 도는 indiebizOS 백엔드 프로세스**다"
        "(앱 샌드박스 아님 — 사용자가 할 수 있는 건 다 한다). 상시 켜져 있고 포트/터널로 "
        "인바운드 도달이 된다."
    )


def build_capability_portrait() -> dict:
    """능력 자기-모델 — 정체성(class+권한봉투) + 마이크로 명령어 집합 + 빌림 상대(피어 설정 시)."""
    body = detect_body()
    kind = body.get("kind", "mac")
    p = {"body": body.get("label", ""), "kind": kind}
    p["identity"] = _self_identity(body)  # 나를 올바른 class로 부르는 정체성 한 줄
    p["micros"] = detect_local_micros()   # 내가 직접 할 수 있는 / 빌려야 하는 실행 원시
    if kind == "phone":
        peer_url = os.environ.get("INDIEBIZ_MAC_URL")
        p["peer_name"] = "맥미니(집 PC)"
    else:
        peer_url = os.environ.get("INDIEBIZ_PHONE_URL")
        p["peer_name"] = "안드로이드 폰"
    p["has_peer"] = bool(peer_url)
    return p


def parse_first_json(text: str):
    """LLM 응답에서 첫 JSON 값(객체/배열)만 안전 추출. 실패 시 None.

    경량 모델(증류·포식·심층메모리)이 JSON 뒤에 잡담·중복 JSON·Auto-Continue 이어붙임
    잔재를 붙이면 json.loads 가 'Extra data' 로 통째 실패해 학습이 유실된다(에피소드 855
    실측) — 코드펜스를 벗기고 첫 '{'/'[' 에서 raw_decode 로 *첫 값만* 살린다.
    """
    import json as _json
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
        t = t.strip()
    dec = _json.JSONDecoder()
    for i, ch in enumerate(t):
        if ch in "[{":
            try:
                val, _end = dec.raw_decode(t, i)
                return val
            except _json.JSONDecodeError:
                continue  # 다음 시작 후보에서 재시도 (앞머리 잡담 관통)
    return None


# 분산 IBL — 맥(연합 두뇌) 위임 세션 캐시(원격 런처 인증). 폰 프로세스 내 모듈 전역.
# ibl_engine 에서 이동(2026-08-05 ⑦) — 렌트해마(ibl_usage_db)가 엔진을 import 하지 않게.
mac_session_cache = {"session": None}
