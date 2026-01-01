import subprocess
import json
import os
import sys
import platform
from pathlib import Path


def get_node_cmd():
    """번들된 Node.js 또는 시스템 Node.js 경로 반환"""
    node_cmd = "node"

    # backend 폴더 찾기
    current = Path(__file__).parent
    while current.parent != current:
        if (current / "backend").exists():
            base_path = current
            break
        current = current.parent
    else:
        return node_cmd

    runtime_path = base_path / "runtime"

    # Electron extraResources 경로도 확인
    if not runtime_path.exists():
        resources_path = base_path.parent / "Resources" / "runtime"
        if resources_path.exists():
            runtime_path = resources_path

    is_windows = platform.system() == "Windows"

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
    try:
        # 임시 JavaScript 파일 생성
        with open('temp.js', 'w') as f:
            f.write(code)

        # Node.js를 사용하여 JavaScript 코드 실행 (제한 시간 30초)
        node_cmd = get_node_cmd()
        result = subprocess.run([node_cmd, 'temp.js'], capture_output=True, text=True, timeout=30, check=True, cwd=os.getcwd())

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
        try:
            os.remove('temp.js')
        except FileNotFoundError:
            pass