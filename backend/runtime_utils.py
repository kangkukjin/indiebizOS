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

    Returns:
        {"python": "python3 경로", "node": "node 경로"}
    """
    # 기본값 (시스템 설치된 런타임)
    python_cmd = "python3"
    node_cmd = "node"

    # backend 폴더 기준
    backend_path = Path(__file__).parent

    # 번들된 런타임 경로 확인 (Electron 앱 환경)
    if getattr(sys, 'frozen', False):
        # PyInstaller로 빌드된 경우
        base_path = Path(sys.executable).parent
    else:
        # 개발 환경 - backend 상위의 runtime 폴더 확인
        base_path = backend_path.parent

    runtime_path = base_path / "runtime"

    # macOS/Linux용 Electron 앱 경로도 확인
    if not runtime_path.exists():
        # Electron extraResources 경로
        resources_path = base_path.parent / "Resources" / "runtime"
        if resources_path.exists():
            runtime_path = resources_path

    is_windows = platform.system() == "Windows"

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
