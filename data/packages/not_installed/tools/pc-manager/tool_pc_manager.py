import subprocess
import os
import json

def run_pc_manager(mode: str, path: str = None) -> dict:
    """
    scripts/pc_manager.py를 실행하는 범용 함수
    """
    # 환경변수 또는 현재 디렉토리 기준으로 경로 설정
    base_dir = os.environ.get("INDIEBIZ_BASE_DIR", os.path.expanduser("~"))
    script_path = os.path.join(base_dir, "scripts", "pc_manager.py")

    if not os.path.exists(script_path):
        return {
            "success": False,
            "message": f"관리 스크립트를 찾을 수 없습니다: {script_path}. INDIEBIZ_BASE_DIR 환경변수를 설정하세요."
        }

    try:
        # 기본 경로 설정
        if not path:
            path = base_dir
            
        args = ["python3", script_path, mode, path]
        result = subprocess.run(args, capture_output=True, text=True, check=True)
        return {
            "success": True,
            "stdout": result.stdout,
            "message": f"{mode} 작업이 완료되었습니다."
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"{mode} 작업 중 오류 발생: {str(e)}"
        }

def analyze_storage(path: str = None) -> dict:
    return run_pc_manager("analyze", path)

def find_duplicates(path: str = None) -> dict:
    return run_pc_manager("duplicates", path)

def find_junk(path: str = None) -> dict:
    return run_pc_manager("junk", path)

# 도구 정의
PC_MANAGER_TOOLS = [
    {
        "name": "analyze_storage",
        "description": "PC의 특정 경로(폴더)를 분석하여 용량 정보를 제공합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "분석할 디렉토리 경로 (예: '~/Desktop')"
                }
            }
        }
    },
    {
        "name": "find_duplicates",
        "description": "지정된 경로에서 중복된 파일을 찾아 목록을 보여줍니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "검색할 디렉토리 경로"
                }
            }
        }
    },
    {
        "name": "find_junk",
        "description": "임시 파일, 캐시, 로그 등 삭제 가능한 찌꺼기 파일을 찾아 예상 절약 공간을 계산합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "검색할 디렉토리 경로"
                }
            }
        }
    }
]