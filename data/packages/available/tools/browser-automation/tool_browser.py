"""
tool_browser.py - 브라우저 자동화 도구
browser-use + Playwright를 사용하여 지능형 웹 브라우저 조작
"""

import asyncio
import os
import json
import yaml
import sys
import subprocess
from pathlib import Path

# 설정 파일 경로
BACKEND_DIR = Path(__file__).parent
DATA_DIR = BACKEND_DIR / "data"
TOOL_SETTINGS_FILE = DATA_DIR / "tool_settings.json"
CONFIG_FILE = BACKEND_DIR / "config.yaml"


def get_ai_config():
    """AI 설정을 가져옵니다. tool_settings.json > config.yaml 순으로 확인"""

    # 1. tool_settings.json에서 browser 설정 확인
    if TOOL_SETTINGS_FILE.exists():
        try:
            with open(TOOL_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                settings = json.load(f)

            browser_config = settings.get('browser', {}).get('report_ai')
            if browser_config:
                return {
                    'provider': browser_config.get('provider', 'anthropic'),
                    'model': browser_config.get('model', 'claude-3-5-sonnet-20241022'),
                    'api_key': browser_config.get('api_key', '')
                }
        except Exception as e:
            print(f"[브라우저 도구] tool_settings.json 로드 실패: {e}")

    # 2. config.yaml에서 기본 설정 사용
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            return {
                'provider': 'anthropic',
                'model': 'claude-3-5-sonnet-20241022',
                'api_key': config.get('claude', {}).get('api_key', '')
            }
        except Exception as e:
            print(f"[브라우저 도구] config.yaml 로드 실패: {e}")

    return None


def generate_script(task: str, ai_config: dict) -> str:
    """AI 설정에 따른 실행 스크립트 생성"""

    provider = ai_config.get('provider', 'anthropic')
    model = ai_config.get('model', 'claude-3-5-sonnet-20241022')
    api_key = ai_config.get('api_key', '')

    if provider == 'anthropic':
        return f'''
import asyncio
import nest_asyncio
from browser_use import Agent
from langchain_anthropic import ChatAnthropic
import pydantic

nest_asyncio.apply()

async def run():
    llm = ChatAnthropic(model='{model}', api_key='{api_key}')

    # Pydantic v2 strict mode 우회
    class PatchedChatAnthropic(llm.__class__):
        model_config = pydantic.ConfigDict(extra='allow')
    llm.__class__ = PatchedChatAnthropic
    object.__setattr__(llm, 'provider', 'anthropic')

    agent = Agent(task={repr(task)}, llm=llm)
    result = await agent.run()
    print('---RESULT_START---')
    print(result)
    print('---RESULT_END---')

if __name__ == '__main__':
    asyncio.run(run())
'''

    elif provider == 'openai':
        return f'''
import asyncio
import nest_asyncio
from browser_use import Agent
from langchain_openai import ChatOpenAI
import pydantic

nest_asyncio.apply()

async def run():
    llm = ChatOpenAI(model='{model}', api_key='{api_key}')

    # Pydantic v2 strict mode 우회
    class PatchedChatOpenAI(llm.__class__):
        model_config = pydantic.ConfigDict(extra='allow')
    llm.__class__ = PatchedChatOpenAI

    agent = Agent(task={repr(task)}, llm=llm)
    result = await agent.run()
    print('---RESULT_START---')
    print(result)
    print('---RESULT_END---')

if __name__ == '__main__':
    asyncio.run(run())
'''

    elif provider == 'gemini':
        return f'''
import asyncio
import nest_asyncio
from browser_use import Agent
from langchain_google_genai import ChatGoogleGenerativeAI
import pydantic

nest_asyncio.apply()

async def run():
    llm = ChatGoogleGenerativeAI(model='{model}', google_api_key='{api_key}')

    # Pydantic v2 strict mode 우회
    class PatchedChatGoogle(llm.__class__):
        model_config = pydantic.ConfigDict(extra='allow')
    llm.__class__ = PatchedChatGoogle

    agent = Agent(task={repr(task)}, llm=llm)
    result = await agent.run()
    print('---RESULT_START---')
    print(result)
    print('---RESULT_END---')

if __name__ == '__main__':
    asyncio.run(run())
'''

    else:
        raise ValueError(f"지원하지 않는 AI 제공자: {provider}")


def use_tool(task: str, output_file: str = None) -> dict:
    """
    브라우저 자동화 도구 실행

    Args:
        task: 수행할 작업 설명 (자연어)
        output_file: 결과를 저장할 파일 경로 (선택)

    Returns:
        dict: {"success": bool, "data": str} 또는 {"success": bool, "error": str}
    """
    try:
        print(f"[브라우저 도구] 작업 시작: {task}")

        # AI 설정 로드
        ai_config = get_ai_config()
        if not ai_config or not ai_config.get('api_key'):
            return {
                "success": False,
                "error": "AI 설정을 찾을 수 없습니다. 프로젝트 설정에서 browser 도구의 AI를 설정해주세요."
            }

        print(f"[브라우저 도구] AI 제공자: {ai_config['provider']}, 모델: {ai_config['model']}")

        # 실행 스크립트 생성
        temp_script = generate_script(task, ai_config)
        temp_file = "/tmp/browser_task.py"

        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(temp_script)

        # subprocess로 실행
        process = subprocess.Popen(
            [sys.executable, temp_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            return {"success": False, "error": stderr}

        # 결과 파싱
        if '---RESULT_START---' in stdout:
            res_content = stdout.split('---RESULT_START---')[1].split('---RESULT_END---')[0].strip()
        else:
            res_content = stdout

        # 파일로 저장 (선택)
        if output_file:
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(res_content)

        return {"success": True, "data": res_content}

    except Exception as e:
        return {"success": False, "error": str(e)}
