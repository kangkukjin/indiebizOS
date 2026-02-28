import subprocess
import json
import os
import sys
import platform
from pathlib import Path


def get_node_cmd():
    """번들된 Node.js 또는 시스템 Node.js 경로 반환

    우선순위:
    1. INDIEBIZ_NODE_PATH 환경변수 (Electron에서 설정)
    2. INDIEBIZ_RUNTIME_PATH/node 경로
    3. 폴더 탐색으로 runtime 찾기
    4. 시스템 Node.js (폴백)
    """
    # 1. 환경변수에서 직접 Node.js 경로 확인 (가장 확실한 방법)
    env_node = os.environ.get("INDIEBIZ_NODE_PATH")
    if env_node and Path(env_node).exists():
        return env_node

    # 기본값 (시스템 Node.js)
    node_cmd = "node"
    is_windows = platform.system() == "Windows"

    # 2. INDIEBIZ_RUNTIME_PATH 환경변수에서 runtime 경로 확인
    env_runtime = os.environ.get("INDIEBIZ_RUNTIME_PATH")
    if env_runtime:
        runtime_path = Path(env_runtime)
        if runtime_path.exists():
            if is_windows:
                bundled_node = runtime_path / "node" / "node.exe"
            else:
                bundled_node = runtime_path / "node" / "bin" / "node"

            if bundled_node.exists():
                return str(bundled_node)

    # 3. 폴더 탐색 (개발 환경 또는 환경변수 미설정 시)
    current = Path(__file__).parent
    while current.parent != current:
        if (current / "backend").exists():
            runtime_path = current / "runtime"
            break
        current = current.parent
    else:
        return node_cmd

    # Electron extraResources 경로도 확인
    if not runtime_path.exists():
        resources_path = current.parent / "Resources" / "runtime"
        if resources_path.exists():
            runtime_path = resources_path

    if runtime_path.exists():
        if is_windows:
            bundled_node = runtime_path / "node" / "node.exe"
        else:
            bundled_node = runtime_path / "node" / "bin" / "node"

        if bundled_node.exists():
            node_cmd = str(bundled_node)

    return node_cmd


def execute(tool_name, args, project_path=None):
    if tool_name != "execute_node":
        return {"error": f"Unknown tool: {tool_name}"}

    code = args.get("code", "")
    work_dir = project_path or os.getcwd()
    temp_path = None
    try:
        # 임시 JavaScript 파일 생성 (project_path 내에 생성)
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, dir=work_dir) as f:
            temp_path = f.name
            f.write(code)

        # Node.js를 사용하여 JavaScript 코드 실행 (제한 시간 30초)
        node_cmd = get_node_cmd()
        result = subprocess.run([node_cmd, temp_path], capture_output=True, text=True, timeout=30, check=True, cwd=work_dir)

        # 결과 반환
        return {"result": result.stdout.strip()}

    except subprocess.TimeoutExpired:
        return {"error": "Timeout: JavaScript code execution exceeded 30 seconds."}
    except subprocess.CalledProcessError as e:
        return {"error": f"Error: JavaScript code execution failed with error: {e.stderr.strip()}"}
    except Exception as e:
        return {"error": f"An unexpected error occurred: {str(e)}"}
    finally:
        # 임시 파일 삭제
        if temp_path:
            try:
                os.remove(temp_path)
            except FileNotFoundError:
                pass