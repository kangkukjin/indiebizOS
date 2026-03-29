"""
YouTube 다운로드 도구
- 음악 다운로드 (MP3)
- 동영상 정보 조회
- 자막/트랜스크립트 가져오기
- 동영상 요약 (AI 사용)
- 유튜브 검색 및 재생
"""

import os
import sys
import shutil
import re
import json
import subprocess
from datetime import datetime
from typing import Optional, List, Dict, Any

# common 유틸리티 사용
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

# AI 설정 경로
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

# 시스템 AI 설정 경로 (indiebizOS/data/system_ai_config.json)
INDIEBIZ_DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "..", ".."))
SYSTEM_AI_CONFIG_PATH = os.path.join(INDIEBIZ_DATA_DIR, "system_ai_config.json")
OUTPUTS_DIR = os.path.join(INDIEBIZ_DATA_DIR, "outputs")


def markdown_to_html(content: str, title: str, date_str: str, doc_type: str = "report") -> str:
    """마크다운을 HTML로 변환 (간단 버전)"""
    try:
        import markdown
        html_body = markdown.markdown(content, extensions=['tables', 'fenced_code'])
    except ImportError:
        html_body = f"<pre>{content}</pre>"

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.6; }}
        h1, h2, h3 {{ color: #333; }}
        a {{ color: #0066cc; }}
        pre {{ background: #f5f5f5; padding: 10px; overflow-x: auto; }}
        code {{ background: #f0f0f0; padding: 2px 5px; border-radius: 3px; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <p><em>{date_str}</em></p>
    <hr>
    {html_body}
</body>
</html>"""


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
        # 동적으로 Desktop 경로 설정 (크로스 플랫폼 지원)
        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isabs(filename):
            filename = os.path.join(desktop_path, filename)
        
        if not filename.endswith('.mp3'):
            filename += '.mp3'
        
        # FFmpeg 경로 찾기 (크로스 플랫폼)
        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            # 일반적인 설치 경로들 확인
            common_paths = [
                "/opt/homebrew/bin/ffmpeg",  # macOS (Apple Silicon)
                "/usr/local/bin/ffmpeg",      # macOS (Intel) / Linux
                "/usr/bin/ffmpeg",            # Linux
            ]
            for path in common_paths:
                if os.path.isfile(path):
                    ffmpeg_path = path
                    break

        if not ffmpeg_path or not os.path.isfile(ffmpeg_path):
            return {
                'success': False,
                'message': 'FFmpeg를 찾을 수 없습니다. FFmpeg를 설치해주세요. (brew install ffmpeg)'
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

        # 긴 자막은 파일로 저장하고 경로만 반환
        LONG_THRESHOLD = 10000  # 10,000자 초과 시 파일 저장
        if len(full_text) > LONG_THRESHOLD:
            import os
            outputs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..', 'outputs')
            outputs_dir = os.path.normpath(outputs_dir)
            os.makedirs(outputs_dir, exist_ok=True)

            safe_title = re.sub(r'[^\w가-힣\s-]', '', title)[:50].strip()
            filename = f"transcript_{video_id}_{safe_title}.txt"
            filepath = os.path.join(outputs_dir, filename)

            # 타임스탬프 포함 버전 저장 (더 유용)
            save_lines = []
            for segment in segments:
                timestamp = format_timestamp(segment['start'])
                text = segment['text'].strip()
                save_lines.append(f"[{timestamp}] {text}")
            save_content = f"# {title}\n# Video ID: {video_id}\n# 언어: {used_language}\n# 세그먼트: {len(segments)}개\n\n" + '\n'.join(save_lines)

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(save_content)

            preview = full_text[:2000]
            return {
                'success': True,
                'saved_to_file': True,
                'file_path': filepath,
                'total_length': len(full_text),
                'segment_count': len(segments),
                'preview': preview,
                'language': used_language,
                'title': title,
                'duration': duration,
                'video_id': video_id,
                'message': f'자막이 길어서 파일로 저장했습니다 ({len(full_text):,}자, {len(segments)}개 세그먼트). 파일을 부분적으로 읽어서 요약해주세요: {filepath}'
            }

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


def load_system_ai_config() -> dict:
    """시스템 AI 설정 로드"""
    if os.path.exists(SYSTEM_AI_CONFIG_PATH):
        try:
            with open(SYSTEM_AI_CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {
        "provider": "google",
        "model": "gemini-2.0-flash",
        "apiKey": ""
    }


def get_summary_ai_client():
    """요약용 AI 클라이언트 반환 (시스템 AI 설정 사용)"""
    config = load_system_ai_config()

    provider = config.get("provider", "google")
    model = config.get("model", "gemini-2.0-flash")
    api_key = config.get("apiKey") or config.get("api_key", "")

    # provider 이름 정규화
    if provider in ["google", "gemini"]:
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


# ============================================================
# YouTube 검색 & 재생 (ffplay + yt-dlp 기반, 플레이리스트 큐 지원)
# ============================================================

import threading

# ffplay 기반 오디오 플레이어
_player_process = None   # ffplay subprocess.Popen
_player_video_id = None  # 현재 재생 중인 video_id
_player_title = None     # 현재 재생 중인 제목
_player_queue = []       # 재생 대기열: [{'video_id', 'title', 'channel', 'duration'}, ...]
_player_mode = "audio"   # 현재 재생 모드
_player_lock = threading.Lock()  # 큐/상태 동시접근 보호


def _get_audio_url(video_id):
    """yt-dlp로 video_id에서 오디오 스트림 URL 추출"""
    import yt_dlp
    url = f"https://www.youtube.com/watch?v={video_id}"
    with yt_dlp.YoutubeDL({
        'quiet': True, 'no_warnings': True,
        'format': 'bestaudio/best',
    }) as ydl:
        info = ydl.extract_info(url, download=False)
        return info.get('url', '')


def _start_ffplay(audio_url):
    """ffplay로 오디오 스트림 재생 (백그라운드 프로세스)"""
    global _player_process
    _player_process = subprocess.Popen(
        ['ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet',
         '-reconnect', '1',
         '-reconnect_streamed', '1',
         '-reconnect_delay_max', '5',
         audio_url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def _queue_monitor():
    """ffplay 프로세스 종료 감시 → 큐 자동 진행 (별도 스레드)"""
    global _player_process, _player_video_id, _player_title
    while True:
        proc = None
        with _player_lock:
            proc = _player_process
        if proc is None:
            break
        proc.wait()  # ffplay 종료 대기
        with _player_lock:
            # 프로세스가 바뀌었으면 (skip 등) 이 스레드는 종료
            if _player_process is not proc:
                break
            if not _player_queue:
                _player_process = None
                _player_video_id = None
                _player_title = None
                break
            # 다음 곡 재생
            _play_next_in_queue_locked()


def _play_next_in_queue_locked():
    """큐에서 다음 곡 재생 (_player_lock 잡힌 상태에서 호출)"""
    global _player_process, _player_video_id, _player_title
    if not _player_queue:
        return False
    next_item = _player_queue.pop(0)
    _player_video_id = next_item['video_id']
    _player_title = next_item.get('title', '')
    try:
        audio_url = _get_audio_url(next_item['video_id'])
        if not audio_url:
            _player_process = None
            _player_video_id = None
            _player_title = None
            return False
        _start_ffplay(audio_url)
        return True
    except Exception:
        _player_process = None
        _player_video_id = None
        _player_title = None
        return False


def _close_player():
    """재생 중지 + 큐 초기화"""
    global _player_process, _player_video_id, _player_title, _player_queue
    with _player_lock:
        if _player_process:
            try:
                _player_process.terminate()
                _player_process.wait(timeout=3)
            except Exception:
                try:
                    _player_process.kill()
                except Exception:
                    pass
        _player_process = None
        _player_video_id = None
        _player_title = None
        _player_queue = []


def _format_duration(seconds):
    """초를 M:SS 또는 H:MM:SS로 변환"""
    if not seconds:
        return "?"
    seconds = int(seconds)
    if seconds >= 3600:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h}:{m:02d}:{s:02d}"
    else:
        m = seconds // 60
        s = seconds % 60
        return f"{m}:{s:02d}"


def search_youtube(query: str, count: int = 5) -> dict:
    """유튜브 검색 (재생하지 않고 결과만 반환)

    Args:
        query: 검색어
        count: 검색 결과 수 (1-10, 기본 5)

    Returns:
        dict: {success, count, results: [{video_id, title, channel, duration, url}, ...]}
    """
    try:
        import yt_dlp
    except ImportError:
        return {
            'success': False,
            'message': 'yt-dlp 패키지가 설치되지 않았습니다. pip install yt-dlp'
        }

    count = max(1, min(10, int(count or 5)))

    try:
        search_query = f"ytsearch{count}:{query}"
        with yt_dlp.YoutubeDL({
            'quiet': True, 'no_warnings': True,
            'extract_flat': True,
        }) as ydl:
            result = ydl.extract_info(search_query, download=False)
            entries = result.get('entries', [])

        if not entries:
            return {'success': False, 'message': f'"{query}" 검색 결과가 없습니다.'}

        # 채널/플레이리스트 ID 필터링 (video ID만 남김)
        entries = [e for e in entries if e.get('id') and not e['id'].startswith('UC') and len(e['id']) <= 16]
        if not entries:
            return {'success': False, 'message': f'"{query}" 검색 결과에서 영상을 찾지 못했습니다.'}

        results = []
        for i, e in enumerate(entries):
            vid = e.get('id', '')
            results.append({
                'index': i + 1,
                'video_id': vid,
                'title': e.get('title', ''),
                'channel': e.get('channel', e.get('uploader', '')),
                'duration': _format_duration(e.get('duration')),
                'url': f"https://www.youtube.com/watch?v={vid}",
            })

        return {
            'success': True,
            'query': query,
            'count': len(results),
            'results': results,
        }

    except Exception as e:
        return {'success': False, 'message': f'검색 실패: {str(e)}'}


def play_youtube(query: str, mode: str = "audio", count: int = 5) -> dict:
    """유튜브 검색 후 재생

    Args:
        query: 검색어 또는 YouTube URL
        mode: 재생 모드 - "audio" (소리만, 기본), "video" (브라우저)
        count: 검색 결과 수 (1-10, 기본 5). URL 직접 지정 시 무시됨

    Returns:
        dict: {success, video_id, title, channel, duration, mode, message}
    """
    try:
        import yt_dlp
    except ImportError:
        return {
            'success': False,
            'message': 'yt-dlp 패키지가 설치되지 않았습니다. pip install yt-dlp'
        }

    mode = (mode or "audio").lower()
    count = max(1, min(10, int(count or 5)))

    # URL인지 검색어인지 판단
    is_url = bool(re.match(r'https?://', query)) or 'youtu' in query

    if is_url:
        video_url = query
        # URL에서 직접 정보 가져오기
        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
                info = ydl.extract_info(video_url, download=False)
                video_id = info.get('id', '')
                title = info.get('title', '')
                channel = info.get('channel', info.get('uploader', ''))
                duration = info.get('duration', 0)
        except Exception as e:
            return {'success': False, 'message': f'영상 정보 조회 실패: {str(e)}'}
    else:
        # 검색
        try:
            search_query = f"ytsearch{count}:{query}"
            with yt_dlp.YoutubeDL({
                'quiet': True, 'no_warnings': True,
                'extract_flat': True,
            }) as ydl:
                result = ydl.extract_info(search_query, download=False)
                entries = result.get('entries', [])

            if not entries:
                return {'success': False, 'message': f'"{query}" 검색 결과가 없습니다.'}

            # 채널/플레이리스트 ID 필터링 (video ID만 남김: 11자, UC로 시작하지 않음)
            entries = [e for e in entries if e.get('id') and not e['id'].startswith('UC') and len(e['id']) <= 16]
            if not entries:
                return {'success': False, 'message': f'"{query}" 검색 결과에서 재생 가능한 영상을 찾지 못했습니다.'}

            # 검색 결과 목록 생성
            search_results = []
            for i, e in enumerate(entries):
                search_results.append({
                    'index': i + 1,
                    'video_id': e.get('id', ''),
                    'title': e.get('title', ''),
                    'channel': e.get('channel', e.get('uploader', '')),
                    'duration': _format_duration(e.get('duration')),
                })

            # 첫 번째 결과 → 바로 재생
            selected = entries[0]
            video_id = selected.get('id', '')
            title = selected.get('title', '')
            channel = selected.get('channel', selected.get('uploader', ''))
            duration = selected.get('duration', 0)
            video_url = f"https://www.youtube.com/watch?v={video_id}"

            # ★ 나머지 결과 → 플레이어 시작 후 큐에 추가할 목록 준비
            pending_queue = []
            for e in entries[1:]:
                eid = e.get('id', '')
                if eid:
                    pending_queue.append({
                        'video_id': eid,
                        'title': e.get('title', ''),
                        'channel': e.get('channel', e.get('uploader', '')),
                        'duration': e.get('duration', 0),
                        'url': f"https://www.youtube.com/watch?v={eid}",
                    })

        except Exception as e:
            return {'success': False, 'message': f'검색 실패: {str(e)}'}

    global _player_video_id, _player_mode, _player_title, _player_process

    # ★ 이미 재생 중이면 자동으로 큐에 추가 (play_youtube 반복 호출 대응)
    with _player_lock:
        if _player_process and _player_video_id:
            queue_item = {
                'video_id': video_id,
                'title': title,
                'channel': channel,
                'duration': duration,
            }
            _player_queue.append(queue_item)
            result = {
                'success': True,
                'video_id': video_id,
                'title': title,
                'channel': channel,
                'duration': _format_duration(duration),
                'mode': _player_mode,
                'queued': True,
                'queue_position': len(_player_queue),
                'message': f'대기열에 추가: {title} - {channel} ({_format_duration(duration)}). 대기열 {len(_player_queue)}곡. 사용자에게 URL이나 링크를 보여주지 마세요.',
            }
            if not is_url:
                try:
                    result['search_results'] = search_results
                except NameError:
                    pass
            return result

    # 이전 재생 종료
    _close_player()
    _player_mode = mode

    if mode == "video":
        # video 모드: 기본 브라우저로 열기 (큰 화면)
        watch_url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            subprocess.Popen(['open', watch_url],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            return {'success': False, 'message': f'브라우저 열기 실패: {str(e)}'}
        _player_video_id = video_id
        _player_title = title
        result = {
            'success': True,
            'video_id': video_id,
            'title': title,
            'channel': channel,
            'duration': _format_duration(duration),
            'mode': 'video',
            'message': f'브라우저에서 영상을 재생합니다: {title} - {channel} ({_format_duration(duration)})',
        }
    else:
        # audio 모드: yt-dlp + ffplay로 오디오 스트림 재생
        try:
            audio_url = _get_audio_url(video_id)
            if not audio_url:
                return {'success': False, 'message': '오디오 스트림 URL을 가져올 수 없습니다.'}
            _start_ffplay(audio_url)
            _player_video_id = video_id
            _player_title = title
            # 큐 모니터링 스레드 시작 (곡 끝나면 자동 다음곡)
            t = threading.Thread(target=_queue_monitor, daemon=True)
            t.start()
        except Exception as e:
            return {
                'success': False,
                'message': f'오디오 재생 실패: {str(e)}',
            }

        result = {
            'success': True,
            'video_id': video_id,
            'title': title,
            'channel': channel,
            'duration': _format_duration(duration),
            'mode': 'audio',
            'message': f'음악을 재생합니다: {title} - {channel} ({_format_duration(duration)}). 사용자에게 URL이나 링크를 보여주지 마세요. 중지: stop_youtube, 건너뛰기: skip_youtube',
        }

    # 검색 결과가 있으면 포함
    if not is_url:
        try:
            result['search_results'] = search_results
        except NameError:
            pass

    # ★ 플레이어 시작 후 나머지 검색 결과를 큐에 추가
    if not is_url:
        try:
            if pending_queue:
                with _player_lock:
                    for item in pending_queue:
                        _player_queue.append(item)
                result['auto_queued'] = [{
                    'title': q['title'],
                    'channel': q['channel'],
                    'duration': _format_duration(q['duration']),
                } for q in pending_queue]
                result['queue_length'] = len(_player_queue)
                result['message'] += f' 대기열에 {len(pending_queue)}곡 추가됨 (총 {len(_player_queue)}곡 대기).'
        except NameError:
            pass

    return result


def stop_youtube() -> dict:
    """현재 재생 중인 유튜브 중지 (큐도 모두 초기화)"""
    with _player_lock:
        vid = _player_video_id
        remaining = len(_player_queue)
    if vid or _player_process:
        _close_player()
        msg = '재생을 중지했습니다.'
        if remaining > 0:
            msg += f' (대기열 {remaining}곡도 취소됨)'
        return {
            'success': True,
            'message': msg,
            'video_id': vid,
        }
    else:
        return {'success': True, 'message': '재생 중인 항목이 없습니다.'}


def add_to_queue(query: str, count: int = 3) -> dict:
    """재생 대기열에 곡 추가. 현재 재생 중일 때 사용.

    Args:
        query: 검색어 또는 YouTube URL
        count: 검색 결과 수 (1-5, 기본 3)

    Returns:
        dict: {success, video_id, title, queue_position, queue_length, message}
    """
    with _player_lock:
        if not _player_video_id and not _player_process:
            return {
                'success': False,
                'message': '현재 재생 중인 곡이 없습니다. play_youtube로 먼저 재생을 시작하세요.'
            }

    try:
        import yt_dlp
    except ImportError:
        return {'success': False, 'message': 'yt-dlp 패키지가 없습니다.'}

    count = max(1, min(5, int(count or 3)))
    is_url = bool(re.match(r'https?://', query)) or 'youtu' in query

    if is_url:
        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'extract_flat': True}) as ydl:
                info = ydl.extract_info(query, download=False)
                video_id = info.get('id', '')
                title = info.get('title', '')
                channel = info.get('channel', info.get('uploader', ''))
                duration = info.get('duration', 0)
        except Exception as e:
            return {'success': False, 'message': f'영상 정보 조회 실패: {str(e)}'}
    else:
        try:
            search_query = f"ytsearch{count}:{query}"
            with yt_dlp.YoutubeDL({
                'quiet': True, 'no_warnings': True,
                'extract_flat': True,
            }) as ydl:
                result = ydl.extract_info(search_query, download=False)
                entries = result.get('entries', [])
            if not entries:
                return {'success': False, 'message': f'"{query}" 검색 결과가 없습니다.'}
            # 채널/플레이리스트 ID 필터링
            entries = [e for e in entries if e.get('id') and not e['id'].startswith('UC') and len(e['id']) <= 16]
            if not entries:
                return {'success': False, 'message': f'"{query}" 검색 결과에서 재생 가능한 영상을 찾지 못했습니다.'}
            selected = entries[0]
            video_id = selected.get('id', '')
            title = selected.get('title', '')
            channel = selected.get('channel', selected.get('uploader', ''))
            duration = selected.get('duration', 0)
        except Exception as e:
            return {'success': False, 'message': f'검색 실패: {str(e)}'}

    # 큐에 추가
    with _player_lock:
        queue_item = {
            'video_id': video_id,
            'title': title,
            'channel': channel,
            'duration': duration,
        }
        _player_queue.append(queue_item)
        qlen = len(_player_queue)

    return {
        'success': True,
        'video_id': video_id,
        'title': title,
        'channel': channel,
        'duration': _format_duration(duration),
        'queue_position': qlen,
        'queue_length': qlen,
        'message': f'대기열에 추가: {title} - {channel} ({_format_duration(duration)}). 대기열 {qlen}곡.',
    }


def skip_youtube() -> dict:
    """현재 곡 건너뛰고 대기열의 다음 곡 재생"""
    global _player_process, _player_video_id, _player_title

    with _player_lock:
        if not _player_video_id and not _player_process:
            return {'success': True, 'message': '재생 중인 항목이 없습니다.'}
        skipped_id = _player_video_id

        # 현재 ffplay 프로세스 종료
        if _player_process:
            try:
                _player_process.terminate()
                _player_process.wait(timeout=3)
            except Exception:
                try:
                    _player_process.kill()
                except Exception:
                    pass
            _player_process = None

        if _player_queue:
            next_item = _player_queue[0]  # peek
            if _play_next_in_queue_locked():
                # 새 모니터 스레드 시작
                t = threading.Thread(target=_queue_monitor, daemon=True)
                t.start()
                return {
                    'success': True,
                    'message': f'건너뛰었습니다. 다음 곡 재생: {next_item["title"]}',
                    'skipped_video_id': skipped_id,
                    'now_playing': {
                        'video_id': next_item['video_id'],
                        'title': next_item['title'],
                        'channel': next_item['channel'],
                        'duration': _format_duration(next_item['duration']),
                    },
                    'queue_remaining': len(_player_queue),
                }
            else:
                _player_video_id = None
                _player_title = None
                _player_queue.clear()
                return {
                    'success': True,
                    'message': '건너뛰었으나 다음 곡 재생에 실패했습니다. 재생 종료.',
                    'skipped_video_id': skipped_id,
                }
        else:
            _player_video_id = None
            _player_title = None
            return {
                'success': True,
                'message': '건너뛰었습니다. 대기열이 비어 재생을 종료합니다.',
                'skipped_video_id': skipped_id,
            }


def get_queue() -> dict:
    """현재 재생 대기열 조회"""
    with _player_lock:
        now_playing = None
        if _player_video_id:
            now_playing = {
                'video_id': _player_video_id,
                'title': _player_title or '',
            }

        queue_list = []
        for i, item in enumerate(_player_queue):
            queue_list.append({
                'position': i + 1,
                'video_id': item['video_id'],
                'title': item['title'],
                'channel': item['channel'],
                'duration': _format_duration(item['duration']),
            })

        vid = _player_video_id

    return {
        'success': True,
        'now_playing': now_playing,
        'queue': queue_list,
        'queue_length': len(queue_list),
        'message': f'현재 재생 중: {vid or "없음"}, 대기열: {len(queue_list)}곡',
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
