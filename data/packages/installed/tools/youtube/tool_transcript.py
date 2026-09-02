"""tool_transcript.py — 유튜브 다운로드·자막·요약 (tool_youtube.py 에서 분리, 2026-08-06 1500줄 규칙).

MP3 다운로드 / 영상 정보 / 자막(트랜스크립트) 추출 / AI 요약. **상태 없는** 영역이라
싱글턴일 필요가 없다 — 재생 상태 기계(ffplay 프로세스·큐·락)는 tool_youtube.py 에
그대로 남았다(그 전역이 곧 상태라 옮기면 안 된다). 의존은 한 방향:
tool_youtube → tool_transcript (relay_youtube 가 extract_video_id·get_youtube_info 사용).
"""
import os
import sys
import shutil
import re
import json
from runtime_utils import expand_body_path  # 경로 펼침 단일 해소점 (~workspace/·~)
from datetime import datetime
from typing import Optional, List, Dict, Any
from common.platform_utils import find_binary, install_hint, open_url

_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
INDIEBIZ_DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "..", ".."))
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


def download_youtube_music(url: str, filename: str = "output.mp3", mode: str = "server") -> dict:
    """YouTube에서 음악을 MP3로 다운로드.

    mode="server"(기본): 맥 Desktop 에 저장(데스크탑 사용).
    mode="client": 임시 폴더에 받아 base64 로 반환(빌린 연산→로컬 산출물). 분산 IBL 에서
      폰이 [limbs:music]{op:download, mode:client} 를 맥에 위임 → 맥이 추출 → b64 로 돌려주면
      폰 Python(phone_api)이 받아 네이티브 MediaStore 로 폰 Music 폴더에 저장한다.
      (큰 b64 를 WebView JS 브리지로 안 보내고 Python↔Kotlin 으로만 다룸.)
    """
    try:
        import yt_dlp
    except ImportError:
        return {
            'success': False,
            'message': 'yt_dlp 패키지가 설치되지 않았습니다. pip install yt-dlp 실행 필요'
        }

    client = (mode == "client")
    _tmpdir = None
    try:
        if client:
            import tempfile
            _tmpdir = tempfile.mkdtemp(prefix="ibz_dl_")
            filename = os.path.join(_tmpdir, "track.mp3")
        else:
            # 동적으로 Desktop 경로 설정 (크로스 플랫폼 지원)
            desktop_path = os.path.join(expand_body_path("~"), "Desktop")
            if not os.path.isabs(filename):
                filename = os.path.join(desktop_path, filename)
            if not filename.endswith('.mp3'):
                filename += '.mp3'
        
        # FFmpeg 경로 찾기 (전 OS — PATH + OS별 표준 설치 경로 폴백)
        ffmpeg_path = find_binary("ffmpeg")
        if not ffmpeg_path or not os.path.isfile(ffmpeg_path):
            return {
                'success': False,
                'message': install_hint("ffmpeg"),
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

        if client:
            # 임시 mp3 → base64. 폰(phone_api)이 받아 MediaStore 로 Music 폴더에 저장.
            import base64
            with open(filename, 'rb') as _f:
                _data = _f.read()
            _b64 = base64.b64encode(_data).decode('ascii')
            _safe = re.sub(r'[\\/:*?"<>|\n\r\t]+', '_', title).strip()[:90] or 'track'
            return {
                'success': True,
                'download_in_client': True,
                'filename': _safe + '.mp3',
                'b64': _b64,
                'title': title,
                'bytes': len(_data),
                'message': f'다운로드: {title}',
            }
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
    finally:
        if _tmpdir:
            shutil.rmtree(_tmpdir, ignore_errors=True)


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
        return {'success': False, 'error': 'yt_dlp 패키지 없음'}

    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                'success': True,
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown'),
                'view_count': info.get('view_count', 0),
                'upload_date': info.get('upload_date'),  # YYYYMMDD — 최신성 필터(AI 팁 보고서 6개월 규칙 등)에 필요
            }
    except Exception as e:
        return {'success': False, 'error': f'실패: {str(e)}'}


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
            out = {
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
                # 통째로 도로 읽으면 파일로 뺀 의미가 사라진다 — 부분 읽기 '방법'까지 알려준다.
                # ★[self:grep] 은 path 가 아니라 root_path + file_pattern 을 받는다.
                'message': (
                    f'자막이 길어서 파일로 저장했습니다 ({len(full_text):,}자, {len(segments)}개 세그먼트): {filepath}\n'
                    f'★통째로 읽지 마세요. 앵커를 먼저 잡고 그 구간만 읽습니다:\n'
                    f'  1) [self:grep]{{pattern: "키워드1|키워드2", root_path: "{outputs_dir}", file_pattern: "{filename}"}} → 줄 번호 확보\n'
                    f'  2) [self:read]{{path: "{filepath}", start_line: 640, end_line: 1045}} → 그 구간만 발췌 (1-기반 양끝 포함)\n'
                    f'  전체 흐름만 필요하면 preview 필드(앞 2,000자)로 충분한 경우가 많습니다.'
                )
            }
            # 파이프 통화(2026-08-29): 봉투는 파일 참조로 작게 유지하되, 세그먼트 통화를
            # 스필 참조로 싣는다 — `transcript >> [table:brief]` 류 파이프의 소비자
            # (_get_items·each·$items 바인딩)가 resolve_ref 로 투명하게 전체 세그먼트를
            # 받는다(어제·오늘 이틀 연속 마찰: "입력 통화가 없습니다"). 미가용 시 종전 모양.
            try:
                from common.spill import spill_write
                _env = spill_write(json.dumps({"items": segments}, ensure_ascii=False),
                                   tag=f"transcript_{video_id}")
                out.update({"items": [], "ref": _env["ref"], "_spilled": True})
            except Exception:
                pass
            return out

        return {
            'success': True,
            'transcript': full_text,
            'formatted_transcript': formatted_transcript,
            'segments': segments,
            # 단일 통화(2026-08-29): 세그먼트를 items 로도 싣는다 — `>> [table:brief]` 등
            # 파이프 변환자가 통화를 받는 자리. segments 키는 기존 독자용으로 유지.
            'items': segments,
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


def get_summary_ai_client():
    """요약용 AI provider 반환 — 모델 기어 'content_text' 역할(실행 축).

    정책: 콘텐츠를 만드는 AI 는 실행 AI 와 같은 모델을 쓴다 — 사용자가 기어로 조정한다
    (lecture_workspace/slide_ai.py 가 2026-08-04 에 옮겨간 것과 같은 관용).

    ★왜 옮겼나(2026-08-30): 옛 판은 고급 티어 파일을 직접 읽고 provider 이름을 손으로
    분기해 두 군데서 동시에 깨졌다 — ①분기가 google/openai/anthropic 세 이름만 알아서
    기어가 claude_code·deepseek 로 바뀌자 'Unknown provider' 로 죽었고(세 티어 어느
    것도 통과 못 함), ②키를 티어 json 의 apiKey 에서만 찾아 .env 로 옮겨간 정본 키를
    못 봤다. 둘 다 기어 우회라는 한 뿌리에서 나온 증상이라 통로 자체를 바꾼다.
    """
    from model_resolver import resolve, provider_needs_api_key

    d = resolve("content_text")
    provider_name = (d.get("provider") or "").strip()
    model_name = (d.get("model") or "").strip()
    api_key = (d.get("api_key") or "").strip()

    if not provider_name or not model_name:
        raise RuntimeError(
            "요약 모델을 해소하지 못했습니다 — 모델 기어(실행 축) 설정을 확인하세요.")
    # claude_code·ollama 는 자체 인증이라 키가 없는 것이 정상이다.
    if not api_key and provider_needs_api_key(provider_name):
        raise RuntimeError(
            f"{provider_name} 키가 없습니다 — .env 의 프로바이더 키를 확인하세요.")

    from providers import get_provider
    provider = get_provider(
        provider_name,
        api_key=api_key,
        model=model_name,
        system_prompt="당신은 영상 자막을 읽고 핵심을 정리하는 요약 전문가다.",
        tools=[],
    )
    provider.init_client()
    print(f"      · 요약 모델: {provider_name}/{model_name} ({d.get('source', '')})")
    return provider


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
        # 프로바이더별 SDK 분기는 provider 계층이 이미 흡수한다 — 여기서 다시 갈래를
        # 치면 새 프로바이더가 생길 때마다 이 파일이 뒤처진다(그게 옛 결함이었다).
        ai = get_summary_ai_client()
        summary_content = ai.process_message(summary_prompt, history=[])

        if not (summary_content or "").strip():
            raise RuntimeError("요약 모델이 빈 응답을 냈습니다")

        print(f"      ✓ AI 요약 완료 ({len(summary_content)}자)")

    except Exception as ai_err:
        return {
            'success': False,
            'message': f"AI 요약 실패: {str(ai_err)}"
        }

    # 3. HTML 파일로 저장
    print("[3/3] HTML 파일 생성 중...")

    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")  # ASCII 포맷이라 로케일 무관
    # ★ 로케일 비의존 조립: strftime 포맷 속 한글 리터럴(년/월/일)은 윈도우 임베디드
    #   Python(로케일 Korean_Korea + 코드페이지 1252 불일치)에서 UnicodeEncodeError로
    #   터진다. 맥(UTF-8)에선 재현 안 됨. 숫자 필드로 직접 조립(출력 동일).
    today_str = f"{now.year}년 {now.month:02d}월 {now.day:02d}일"

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
- **생성 시각**: {now.year}년 {now.month:02d}월 {now.day:02d}일 {now.hour:02d}시 {now.minute:02d}분
"""

    # HTML 변환 및 저장
    os.makedirs(OUTPUTS_DIR, exist_ok=True)

    html_content = markdown_to_html(markdown_content, f"YouTube 요약: {title}", today_str, doc_type="report")
    html_filename = f"youtube_summary_{safe_title}_{timestamp}.html"
    html_filepath = os.path.join(OUTPUTS_DIR, html_filename)

    with open(html_filepath, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"💾 HTML 저장: {html_filename}")

    # 4. 브라우저로 열기
    import webbrowser
    abs_path = os.path.abspath(html_filepath)
    webbrowser.open(f"file://{abs_path}")
    print(f"🌐 브라우저에서 열기: {abs_path}")
    print(f"✅ YouTube 요약 완료!\n")

    return {
        'success': True,
        'file_path': abs_path,
        'title': title,
        'duration': duration,
        'summary_length': len(summary_content),
        'message': f'YouTube 영상 요약이 완료되었습니다. 브라우저에서 열었습니다. 파일: {abs_path}'
    }
