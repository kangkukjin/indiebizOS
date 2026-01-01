import asyncio
import os
import sys
import importlib.util
from pathlib import Path

# tool_browser.py 모듈을 동적으로 로드합니다.
current_dir = Path(__file__).parent
tool_browser_path = current_dir / "tool_browser.py"

def execute(tool_name, args, project_path=None):
    """
    자연어 지시사항을 받아 브라우저 자동화를 실행합니다.
    """
    if tool_name != "browser_action":
        return {"error": f"Unknown tool: {tool_name}"}

    instruction = args.get("instruction", "")
    spec = importlib.util.spec_from_file_location("tool_browser", tool_browser_path)
    tool_browser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool_browser)

    # AI 설정 가져오기
    ai_config = tool_browser.get_ai_config()
    if not ai_config or not ai_config.get('api_key'):
        return "에러: AI API 키가 설정되지 않았습니다. config.yaml 또는 tool_settings.json을 확인하세요."

    # 실행 스크립트 생성
    script_content = tool_browser.generate_script(instruction, ai_config)
    
    # 임시 파일로 스크립트 실행 (asyncio 루프 충돌 방지)
    temp_script = current_dir / "_temp_run.py"
    with open(temp_script, "w", encoding="utf-8") as f:
        f.write(script_content)

    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, str(temp_script)],
            capture_output=True,
            text=True,
            encoding="utf-8"
        )
        
        output = result.stdout
        if "---RESULT_START---" in output:
            final_result = output.split("---RESULT_START---")[1].split("---RESULT_END---")[0].strip()
            return final_result
        else:
            return f"브라우저 작업 중 오류가 발생했습니다: {result.stderr}"
    except Exception as e:
        return f"실행 실패: {str(e)}"
    finally:
        if temp_script.exists():
            temp_script.unlink()