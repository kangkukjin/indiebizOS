import os
import json
import importlib.util
from pathlib import Path

# 같은 디렉토리의 모듈을 동적으로 로드
current_dir = Path(__file__).parent

def load_tool_youtube():
    module_path = current_dir / "tool_youtube.py"
    spec = importlib.util.spec_from_file_location("tool_youtube", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
SETTINGS_PATH = os.path.join(BASE_DIR, "tool_settings.json")

def execute(tool_name: str, arguments: dict, project_path: str = None):
    tool_youtube = load_tool_youtube()

    if tool_name == 'download_youtube_music':
        return tool_youtube.download_youtube_music(url=arguments['url'], filename=arguments.get('output_path', 'output.mp3'))
    elif tool_name == 'get_youtube_info':
        return tool_youtube.get_youtube_info(url=arguments['url'])
    elif tool_name == 'get_youtube_transcript':
        # language를 languages 리스트로 변환
        lang = arguments.get('language') or arguments.get('languages')
        if isinstance(lang, str):
            languages = [lang]
        elif isinstance(lang, list):
            languages = lang
        else:
            languages = ['ko', 'en']
        return tool_youtube.get_youtube_transcript(url=arguments['url'], languages=languages)
    elif tool_name == 'list_available_transcripts':
        return tool_youtube.list_available_transcripts(url=arguments['url'])
    elif tool_name == 'summarize_youtube':
        # summary_length와 languages 파라미터 전달
        summary_length = arguments.get('summary_length', 3000)
        lang = arguments.get('language') or arguments.get('languages')
        if isinstance(lang, str):
            languages = [lang]
        elif isinstance(lang, list):
            languages = lang
        else:
            languages = None  # 자동 선택
        return tool_youtube.summarize_youtube(
            url=arguments['url'],
            summary_length=summary_length,
            languages=languages
        )
    else:
        raise ValueError(f'Unknown tool: {tool_name}')
