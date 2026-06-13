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
    return Path(__file__).parent.parent


def get_data_path() -> Path:
    """데이터 경로 반환 (base_path/data)"""
    p = get_base_path() / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


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
    backend_path = Path(__file__).parent

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


def setup_bundled_runtime_paths():
    """
    백엔드 시작 시 호출 — 번들 Python의 Scripts/bin과 site-packages를
    os.environ['PATH']와 sys.path에 등록.

    이렇게 하면:
    - subprocess.run(['yt-dlp', ...]) 등이 번들 Python에 pip 설치된 CLI를 찾음
    - import yt_dlp 등이 번들 Python의 site-packages에서 모듈을 찾음

    개발 환경(시스템 Python)에서는 해당 경로가 존재하지 않으므로 안전하게 무시됨.
    """
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
    body = {"profile": profile or "mac"}
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


def build_capability_portrait() -> dict:
    """능력 자기-모델 — 정체성 + 마이크로 명령어 집합 + 빌림 상대(피어 설정 시)."""
    body = detect_body()
    kind = body.get("kind", "mac")
    p = {"body": body.get("label", ""), "kind": kind}
    p["micros"] = detect_local_micros()   # 내가 직접 할 수 있는 / 빌려야 하는 실행 원시
    if kind == "phone":
        peer_url = os.environ.get("INDIEBIZ_MAC_URL")
        p["peer_name"] = "맥미니(집 PC)"
    else:
        peer_url = os.environ.get("INDIEBIZ_PHONE_URL")
        p["peer_name"] = "안드로이드 폰"
    p["has_peer"] = bool(peer_url)
    return p
