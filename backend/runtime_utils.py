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
