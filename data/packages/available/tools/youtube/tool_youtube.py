"""
YouTube 다운로드 도구
- 음악 다운로드 (MP3)
- 동영상 정보 조회
- 자막/트랜스크립트 가져오기
- 동영상 요약 (AI 사용)
"""

import os
import shutil
import re
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from tool_utils import markdown_to_html, OUTPUTS_DIR

# AI 설정 경로
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
SETTINGS_PATH = os.path.join(DATA_DIR, "tool_settings.json")


def download_youtube_music(url: str, filename: str = "output.mp3") -> dict:
    """YouTube에서 음악을 MP3로 다운로드"""
    try:
        import yt_dlp
    except ImportError:
        return {
            'success': False,
            'message': 'yt_dlp 패키지가 설치되지 않았습니다. pip install yt-dlp 실행 필요'
        }
    
    try:
        desktop_path = "/Users/kangkukjin/Desktop"
        if not os.path.isabs(filename):
            filename = os.path.join(desktop_path, filename)
        
        if not filename.endswith('.mp3'):
            filename += '.mp3'
        
        ffmpeg_path = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
        if not ffmpeg_path:
            return {
                'success': False,
                'message': 'FFmpeg를 찾을 수 없습니다.'
            }
        
        print(f"[YouTube] 다운로드 시작: {url}")
        print(f"[YouTube] 저장 위치: {filename}")
        
        # 진행 상황 표시
        def progress_hook(d):
            if d['status'] == 'downloading':
                print(f"[YouTube] 다운로드 중... {d.get('_percent_str', '?')}%")
            elif d['status'] == 'finished':
                print(f"[YouTube] 다운로드 완료, MP3 변환 중...")
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }],
            'outtmpl': filename.rsplit('.mp3', 1)[0],
            'ffmpeg_location': ffmpeg_path,
            'quiet': False,  # 진행 상황 표시
            'no_warnings': False,
            'noprogress': False,
            'progress_hooks': [progress_hook],
            'noplaylist': True,  # 플레이리스트 무시, 단일 비디오만 다운로드
            'extract_flat': False,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"[YouTube] 비디오 정보 가져오는 중...")
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'Unknown')
            duration = info.get('duration', 0)
            
            print(f"[YouTube] 제목: {title}")
            print(f"[YouTube] 길이: {duration}초")
            print(f"[YouTube] 다운로드 시작...")
            
            ydl.download([url])
            
            print(f"[YouTube] 완료! 파일: {filename}")
            
            return {
                'success': True,
                'file_path': filename,
                'title': title,
                'duration': duration,
                'message': f'다운로드 완료: {title} ({duration}초)'
            }
    except Exception as e:
        print(f"[YouTube] 오류: {str(e)}")
        return {
            'success': False,
            'message': f'다운로드 실패: {str(e)}'
        }


def format_timestamp(seconds: float) -> str:
    """초를 HH:MM:SS 또는 MM:SS 형식으로 변환합니다."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def merge_transcript_segments(segments: List[dict], max_duration: float = 60.0) -> List[dict]:
    """자막 세그먼트를 병합하여 더 읽기 쉬운 형태로 만듭니다.

    Args:
        segments: 자막 세그먼트 리스트 (각 세그먼트는 start, duration, text 포함)
        max_duration: 병합할 최대 시간 간격 (초, 기본 60초)

    Returns:
        병합된 자막 세그먼트 리스트
    """
    if not segments:
        return []

    merged = []
    current_segment = {
        'start': segments[0]['start'],
        'text': segments[0]['text'],
        'duration': segments[0].get('duration', 0)
    }

    for segment in segments[1:]:
        if segment['start'] - current_segment['start'] < max_duration:
            current_segment['text'] += ' ' + segment['text']
            current_segment['duration'] = segment['start'] + segment.get('duration', 0) - current_segment['start']
        else:
            merged.append(current_segment)
            current_segment = {
                'start': segment['start'],
                'text': segment['text'],
                'duration': segment.get('duration', 0)
            }

    merged.append(current_segment)
    return merged


def get_youtube_info(url: str) -> dict:
    """YouTube 동영상 정보 조회"""
    try:
        import yt_dlp
    except ImportError:
        return {'success': False, 'message': 'yt_dlp 패키지 없음'}

    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                'success': True,
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown'),
                'view_count': info.get('view_count', 0),
            }
    except Exception as e:
        return {'success': False, 'message': f'실패: {str(e)}'}


def extract_video_id(url: str) -> str:
    """YouTube URL에서 video_id 추출"""
    # 이미 ID 형식인 경우
    if re.match(r'^[a-zA-Z0-9_-]{11}$', url):
        return url

    patterns = [
        r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:embed/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def list_available_transcripts(url: str) -> dict:
    """YouTube 동영상에서 사용 가능한 자막 언어 목록을 조회합니다.

    Args:
        url: YouTube URL 또는 video_id

    Returns:
        dict: {
            'success': bool,
            'video_id': str,
            'manual_transcripts': list,  # 수동 생성 자막 목록
            'auto_transcripts': list,    # 자동 생성 자막 목록
            'message': str
        }
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return {
            'success': False,
            'message': 'youtube-transcript-api 패키지가 필요합니다. pip install youtube-transcript-api'
        }

    video_id = extract_video_id(url)
    if not video_id:
        return {
            'success': False,
            'message': f'올바른 YouTube URL이 아닙니다: {url}'
        }

    try:
        ytt_api = YouTubeTranscriptApi()
        transcript_list = ytt_api.list(video_id)

        manual_transcripts = []
        auto_transcripts = []

        for t in transcript_list:
            info = {
                'language': t.language,
                'language_code': t.language_code,
                'is_translatable': t.is_translatable
            }
            if t.is_generated:
                auto_transcripts.append(info)
            else:
                manual_transcripts.append(info)

        return {
            'success': True,
            'video_id': video_id,
            'manual_transcripts': manual_transcripts,
            'auto_transcripts': auto_transcripts,
            'message': f'자막 언어 목록 조회 완료. 수동: {len(manual_transcripts)}개, 자동: {len(auto_transcripts)}개'
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'자막 목록 조회 실패: {str(e)}'
        }


def get_youtube_transcript(
    url: str,
    languages: list = None,
    include_timestamps: bool = False,
    merge_segments: bool = False,
    max_length: Optional[int] = None
) -> dict:
    """
    YouTube 동영상의 자막/트랜스크립트를 가져옵니다.

    Args:
        url: YouTube URL 또는 video_id
        languages: 선호 언어 목록 (예: ['ko', 'en']). None이면 자동 선택
        include_timestamps: True면 타임스탬프 포함 형식으로 반환
        merge_segments: True면 짧은 세그먼트를 60초 단위로 병합
        max_length: 반환할 자막의 최대 문자 수 (None이면 제한 없음)

    Returns:
        dict: {
            'success': bool,
            'transcript': str,  # 전체 자막 텍스트
            'formatted_transcript': str,  # 포맷팅된 자막 (타임스탬프 포함 시)
            'segments': list,   # 타임스탬프 포함 세그먼트
            'language': str,    # 사용된 언어
            'title': str,       # 영상 제목
            'duration': int,    # 영상 길이 (초)
            'message': str
        }
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return {
            'success': False,
            'message': 'youtube-transcript-api 패키지가 필요합니다. pip install youtube-transcript-api'
        }

    # video_id 추출
    video_id = extract_video_id(url)
    if not video_id:
        return {
            'success': False,
            'message': f'올바른 YouTube URL이 아닙니다: {url}'
        }

    # 영상 정보 가져오기 (선택적)
    video_info = get_youtube_info(url)
    title = video_info.get('title', 'Unknown') if video_info.get('success') else 'Unknown'
    duration = video_info.get('duration', 0) if video_info.get('success') else 0

    try:
        # 언어 우선순위 설정
        if languages is None:
            languages = ['ko', 'en', 'ja', 'zh-Hans', 'zh-Hant']

        # youtube-transcript-api 1.2.x 새로운 API 사용
        ytt_api = YouTubeTranscriptApi()

        transcript_data = None
        used_language = None

        # 선호 언어 순서대로 시도
        for lang in languages:
            try:
                transcript_data = ytt_api.fetch(video_id, languages=[lang])
                used_language = lang
                break
            except Exception:
                continue

        # 선호 언어로 못 찾으면 아무 자막이나
        if transcript_data is None:
            try:
                transcript_data = ytt_api.fetch(video_id)
                used_language = 'auto'
            except Exception as e:
                return {
                    'success': False,
                    'message': f'자막을 찾을 수 없습니다: {str(e)}'
                }

        if not transcript_data:
            return {
                'success': False,
                'message': '사용 가능한 자막이 없습니다.'
            }

        # 타임스탬프 포함 세그먼트
        segments = [
            {
                'start': segment.start,
                'duration': segment.duration,
                'text': segment.text
            }
            for segment in transcript_data
        ]

        # 세그먼트 병합 옵션 적용
        if merge_segments:
            segments = merge_transcript_segments(segments)

        # 전체 텍스트로 합치기
        full_text = ' '.join([s['text'] for s in segments])
        full_text = re.sub(r'\s+', ' ', full_text).strip()

        # 최대 길이 제한 적용
        if max_length and len(full_text) > max_length:
            full_text = full_text[:max_length] + "... (자막이 잘렸습니다)"

        # 타임스탬프 포함 포맷팅
        formatted_transcript = None
        if include_timestamps:
            formatted_lines = []
            for segment in segments:
                timestamp = format_timestamp(segment['start'])
                text = segment['text'].strip()
                formatted_lines.append(f"[{timestamp}] {text}")
            formatted_transcript = '\n'.join(formatted_lines)

        return {
            'success': True,
            'transcript': full_text,
            'formatted_transcript': formatted_transcript,
            'segments': segments,
            'language': used_language,
            'title': title,
            'duration': duration,
            'video_id': video_id,
            'message': f'자막을 성공적으로 가져왔습니다. (언어: {used_language}, 세그먼트: {len(segments)}개)'
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'자막 가져오기 실패: {str(e)}'
        }


def load_tool_settings() -> dict:
    """도구 설정 로드"""
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {
        "youtube": {
            "summary_ai": {
                "provider": "gemini",
                "model": "gemini-2.0-flash-exp",
                "api_key": ""
            }
        }
    }


def get_summary_ai_client():
    """요약용 AI 클라이언트 반환"""
    settings = load_tool_settings()

    # youtube 설정이 없으면 blog_insight 설정 사용 (폴백)
    ai_config = settings.get("youtube", {}).get("summary_ai", {})
    if not ai_config.get("api_key"):
        ai_config = settings.get("blog_insight", {}).get("report_ai", {})

    provider = ai_config.get("provider", "gemini")
    model = ai_config.get("model", "gemini-2.0-flash-exp")
    api_key = ai_config.get("api_key", "")

    if provider == "gemini":
        from google import genai
        client = genai.Client(api_key=api_key)
        return client, "gemini", model
    elif provider == "openai":
        import openai
        client = openai.OpenAI(api_key=api_key)
        return client, "openai", model
    elif provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        return client, "anthropic", model
    else:
        raise ValueError(f"Unknown provider: {provider}")


def summarize_youtube(
    url: str,
    summary_length: int = 3000,
    languages: list = None
) -> Dict[str, Any]:
    """
    YouTube 동영상을 AI로 요약하여 HTML 파일로 저장합니다.

    Args:
        url: YouTube URL 또는 video_id
        summary_length: 요약 길이 (기본 3000자)
        languages: 선호 언어 목록 (예: ['ko', 'en']). None이면 자동 선택

    Returns:
        dict: {
            'success': bool,
            'file_path': str,  # 생성된 HTML 파일 경로
            'title': str,      # 영상 제목
            'duration': int,   # 영상 길이 (초)
            'message': str
        }
    """
    print(f"\n📺 YouTube 영상 요약 시작: {url}")

    # 1. 자막 가져오기
    print("[1/3] 자막 가져오는 중...")
    transcript_result = get_youtube_transcript(url, languages=languages)

    if not transcript_result.get('success'):
        return {
            'success': False,
            'message': f"자막 가져오기 실패: {transcript_result.get('message')}"
        }

    transcript = transcript_result.get('transcript', '')
    title = transcript_result.get('title', 'Unknown')
    duration = transcript_result.get('duration', 0)
    video_id = transcript_result.get('video_id', '')
    language = transcript_result.get('language', 'auto')

    print(f"      ✓ 자막 가져오기 완료 (언어: {language}, {len(transcript)}자)")

    # 2. AI로 요약 생성
    print("[2/3] AI 요약 생성 중...")

    summary_prompt = f"""다음은 YouTube 동영상의 자막입니다. 이 내용을 {summary_length}자 내외로 상세하게 요약해주세요.

## 요약 형식

### 영상 개요
- 영상의 핵심 주제와 목적

### 주요 내용
- 영상에서 다루는 핵심 포인트들을 구조적으로 정리
- 중요한 개념, 주장, 근거 포함
- 소제목을 사용해 구분

### 핵심 인사이트
- 이 영상에서 얻을 수 있는 가장 중요한 통찰 3가지

### 결론
- 영상의 결론 및 시사점

톤: 정보 전달에 충실하되 읽기 쉽게
분량: 약 {summary_length}자

=== 영상 정보 ===
제목: {title}
길이: {duration // 60}분 {duration % 60}초

=== 자막 내용 ===
{transcript[:50000]}
"""

    try:
        ai_result = get_summary_ai_client()

        if ai_result[1] == "gemini":
            client, _, model_name = ai_result
            response = client.models.generate_content(
                model=model_name,
                contents=summary_prompt
            )
            summary_content = response.text
        elif ai_result[1] == "openai":
            client, _, model_name = ai_result
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": summary_prompt}]
            )
            summary_content = response.choices[0].message.content
        elif ai_result[1] == "anthropic":
            client, _, model_name = ai_result
            response = client.messages.create(
                model=model_name,
                max_tokens=8192,
                messages=[{"role": "user", "content": summary_prompt}]
            )
            summary_content = response.content[0].text

        print(f"      ✓ AI 요약 완료 ({len(summary_content)}자)")

    except Exception as ai_err:
        return {
            'success': False,
            'message': f"AI 요약 실패: {str(ai_err)}"
        }

    # 3. HTML 파일로 저장
    print("[3/3] HTML 파일 생성 중...")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    today_str = datetime.now().strftime("%Y년 %m월 %d일")

    # 제목에서 파일명으로 쓸 수 없는 문자 제거
    safe_title = re.sub(r'[^\w가-힣\s-]', '', title)[:30].strip()

    markdown_content = f"""# {title}

**영상 링크**: [YouTube에서 보기](https://youtube.com/watch?v={video_id})
**영상 길이**: {duration // 60}분 {duration % 60}초
**요약 일시**: {today_str}
**요약 길이**: 약 {summary_length}자

---

{summary_content}

---

## 📊 요약 정보

- **원본 자막 길이**: {len(transcript)}자
- **요약 길이**: {len(summary_content)}자
- **요약 언어**: {language}
- **생성 시각**: {datetime.now().strftime('%Y년 %m월 %d일 %H시 %M분')}
"""

    # HTML 변환 및 저장
    os.makedirs(OUTPUTS_DIR, exist_ok=True)

    html_content = markdown_to_html(markdown_content, f"YouTube 요약: {title}", today_str, doc_type="report")
    html_filename = f"youtube_summary_{safe_title}_{timestamp}.html"
    html_filepath = os.path.join(OUTPUTS_DIR, html_filename)

    with open(html_filepath, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"💾 HTML 저장: {html_filename}")
    print(f"✅ YouTube 요약 완료!\n")

    return {
        'success': True,
        'file_path': html_filepath,
        'title': title,
        'duration': duration,
        'summary_length': len(summary_content),
        'message': f'YouTube 영상 요약이 완료되었습니다. 파일: {html_filepath}'
    }


# 도구 정의
YOUTUBE_TOOLS = [
    {
        "name": "download_youtube_music",
        "description": "YouTube에서 음악을 MP3로 다운로드합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "YouTube URL"},
                "filename": {"type": "string", "description": "파일명"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "get_youtube_info",
        "description": "YouTube 동영상 정보를 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "YouTube URL"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "get_youtube_transcript",
        "description": "YouTube 동영상의 자막/트랜스크립트를 가져옵니다. 영상 내용을 텍스트로 추출할 때 사용합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "YouTube URL 또는 video_id"},
                "languages": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "선호 언어 코드 목록 (예: ['ko', 'en']). 생략시 자동 선택"
                },
                "include_timestamps": {
                    "type": "boolean",
                    "description": "True면 [MM:SS] 형식의 타임스탬프 포함. 기본값: False"
                },
                "merge_segments": {
                    "type": "boolean",
                    "description": "True면 짧은 자막을 60초 단위로 병합하여 가독성 향상. 기본값: False"
                },
                "max_length": {
                    "type": "integer",
                    "description": "반환할 자막의 최대 문자 수. 요약용으로 사용 시 유용. 생략시 제한 없음"
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "list_available_transcripts",
        "description": "YouTube 동영상에서 사용 가능한 자막 언어 목록을 조회합니다. 어떤 언어 자막이 있는지 미리 확인할 때 유용합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "YouTube URL 또는 video_id"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "summarize_youtube",
        "description": "YouTube 동영상을 AI로 요약하여 HTML 파일로 저장합니다. 자막을 가져와서 AI가 지정된 길이로 요약하고, 결과를 HTML 파일로 저장한 뒤 파일 경로를 반환합니다.",
        "uses_ai": True,
        "ai_config_key": "youtube",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "YouTube URL 또는 video_id"},
                "summary_length": {
                    "type": "integer",
                    "description": "요약 길이 (기본 3000자). 예: 1000, 2000, 3000, 5000"
                },
                "languages": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "선호 언어 코드 목록 (예: ['ko', 'en']). 생략시 자동 선택"
                }
            },
            "required": ["url"]
        }
    }
]
