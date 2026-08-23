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
from datetime import datetime
from typing import Optional, List, Dict, Any
from common.platform_utils import (
    find_binary, install_hint, spawn_detached, open_url,
    kill_processes_by_marker, is_process_running_by_marker,
)

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



# 다운로드·자막·요약은 tool_transcript.py 로 분리(2026-08-06, 1500줄 규칙).
# ★재생 상태 기계(전역 프로세스·큐·락)는 이 파일에 남는다 — 그 전역이 곧 상태다.
# 이 모듈은 handler 가 load_singleton 으로 한 번만 로드하므로 재노출 이름도 안정적이다.
from common.pkg_utils import load_sibling

_tx = load_sibling(__file__, "tool_transcript")
markdown_to_html = _tx.markdown_to_html
download_youtube_music = _tx.download_youtube_music
format_timestamp = _tx.format_timestamp
merge_transcript_segments = _tx.merge_transcript_segments
get_youtube_info = _tx.get_youtube_info
extract_video_id = _tx.extract_video_id
list_available_transcripts = _tx.list_available_transcripts
get_youtube_transcript = _tx.get_youtube_transcript
load_system_ai_config = _tx.load_system_ai_config
get_summary_ai_client = _tx.get_summary_ai_client
summarize_youtube = _tx.summarize_youtube


# ============================================================
# YouTube 검색 & 재생 (ffplay + yt-dlp 기반, 플레이리스트 큐 지원)
# ============================================================

import threading
import time

# ffplay 기반 오디오 플레이어
# 라디오와 동일한 고아 청소 전략: ffplay 명령줄(-window_title)에 이 표식을 박아,
# 정지 때 전역 _player_process 뿐 아니라 표식 단 프로세스를 모두 psutil 로 종료한다.
# → 이전 백엔드가 띄운 고아(전역 추적 밖) ffplay 도 확실히 멈춘다("stop 이 거짓 성공" 방지).
YOUTUBE_MARKER = "indiebiz-youtube-player"
_player_process = None   # ffplay subprocess.Popen
_player_video_id = None  # 현재 재생 중인 video_id
_player_title = None     # 현재 재생 중인 제목
_player_queue = []       # 재생 대기열: [{'video_id', 'title', 'channel', 'duration'}, ...]
_player_mode = "audio"   # 현재 재생 모드
# ── 중간 점프(seek) 지원 상태 ──
# ffplay 는 실행 중 조종 채널이 없어 위치 이동이 불가하다. 그래서 seek = "현 ffplay 를
# 죽이고 -ss <초> 로 그 지점부터 재시작"(skip/next 가 쓰는 kill+relaunch 기계 재사용).
# 위치 표시는 정확한 재생 헤드 대신 벽시계로 추정: elapsed = seek_offset + (now - started_at).
_player_audio_url = None    # 현재 곡의 오디오 스트림 URL (seek 재시작에 재사용, 재-resolve 회피)
_player_duration = 0        # 현재 곡 길이(초)
_player_started_at = None   # 현재 ffplay 를 띄운 벽시계 시각(위치 추정용)
_player_seek_offset = 0.0   # 현재 ffplay 를 -ss 로 시작한 오프셋(초)
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


def _start_ffplay(audio_url, seek=0):
    """ffplay로 오디오 스트림 재생 (백그라운드 분리 프로세스, 전 OS).

    seek>0 이면 -ss 로 그 지점부터 시작 = 중간 점프(현 프로세스를 죽이고 이 지점부터 재시작).
    -ss 를 입력 URL 앞에 두면 HTTP range 요청으로 빠르게 탐색한다(googlevideo 는 range 지원).
    위치 추정용으로 시작 벽시계·오프셋을 함께 기록한다.
    """
    global _player_process, _player_audio_url, _player_started_at, _player_seek_offset
    ffplay_path = find_binary("ffplay")
    if not ffplay_path:
        raise FileNotFoundError(install_hint("ffplay"))
    cmd = [ffplay_path, '-nodisp', '-autoexit', '-loglevel', 'quiet',
           '-window_title', YOUTUBE_MARKER]  # 고아 청소용 표식(-nodisp 라 창 없음)
    if seek and seek > 0:
        cmd += ['-ss', str(int(seek))]  # 입력 앞 -ss = range 빠른 탐색
    cmd += ['-reconnect', '1',
            '-reconnect_streamed', '1',
            '-reconnect_delay_max', '5',
            audio_url]
    _player_process = spawn_detached(cmd)
    _player_audio_url = audio_url
    _player_seek_offset = float(seek or 0)
    _player_started_at = time.time()


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
    global _player_process, _player_video_id, _player_title, _player_duration
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
            _player_duration = 0
            return False
        _player_duration = int(next_item.get('duration') or 0)  # 큐 항목은 raw 초 저장
        _start_ffplay(audio_url)
        return True
    except Exception:
        _player_process = None
        _player_video_id = None
        _player_title = None
        _player_duration = 0
        return False


def _close_player():
    """재생 중지 + 큐 초기화"""
    global _player_process, _player_video_id, _player_title, _player_queue
    global _player_audio_url, _player_duration, _player_started_at, _player_seek_offset
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
        # 표식 단 ffplay 를 모두 종료 — 이전 백엔드가 띄운 고아(전역 추적 밖)까지 확실히 정지.
        # (이게 없으면 _player_process=None 인 고아가 살아있어 "stop 이 거짓 성공"을 반환한다.)
        kill_processes_by_marker(YOUTUBE_MARKER)
        _player_process = None
        _player_video_id = None
        _player_title = None
        _player_queue = []
        _player_audio_url = None
        _player_duration = 0
        _player_started_at = None
        _player_seek_offset = 0.0


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


# 검색 결과 상한 — yt-dlp ytsearchN 자체엔 제한이 없다. 가이드·앱 계기가 12를 쓰므로
# 옛 상한 10 은 침묵 클램프였다(2026-08-18 수리). 넘으면 clamped 로 신고한다.
SEARCH_COUNT_MAX = 25


def search_youtube(query: str, count: int = 5) -> dict:
    """유튜브 검색 (재생하지 않고 결과만 반환)

    Args:
        query: 검색어
        count: 검색 결과 수 (1-25, 기본 5). 상한 초과 시 clamped/requested 로 신고

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

    requested = int(count or 5)
    count = max(1, min(SEARCH_COUNT_MAX, requested))

    try:
        search_query = f"ytsearch{count}:{query}"
        with yt_dlp.YoutubeDL({
            'quiet': True, 'no_warnings': True,
            'extract_flat': True,
        }) as ydl:
            result = ydl.extract_info(search_query, download=False)
            entries = result.get('entries', [])

        if not entries:
            return {'success': False, 'error': f'"{query}" 검색 결과가 없습니다.'}

        # 채널/플레이리스트 ID 필터링 (video ID만 남김)
        entries = [e for e in entries if e.get('id') and not e['id'].startswith('UC') and len(e['id']) <= 16]
        if not entries:
            return {'success': False, 'error': f'"{query}" 검색 결과에서 영상을 찾지 못했습니다.'}

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
                'thumb': f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",   # 앱 카드용
            })

        out = {
            'success': True,
            'query': query,
            'count': len(results),
            'results': results,
        }
        # 침묵 클램프 금지 — 요청보다 적게 받았으면 그 사실을 결과에 실어 보낸다.
        if requested != count:
            out['clamped'] = True
            out['requested'] = requested
            out['message'] = (
                f'요청 {requested}건 → 상한 {SEARCH_COUNT_MAX}건으로 조정되어 검색했습니다.'
            )
        return out

    except Exception as e:
        return {'success': False, 'error': f'검색 실패: {str(e)}'}


def relay_youtube(query: str, media: str = "audio", count: int = 6) -> dict:
    """유튜브 검색 → 맥 경유 릴레이 스트림 목록 (원격·폰 표면 '전송' 재생용).

    브라우저가 유튜브에 직접 접속하지 않는다 — 각 항목의 stream(/yt/relay/…)을
    표면의 <audio>/<video> 가 물면, 그때 백엔드(api_ytrelay)가 yt-dlp resolve →
    ffmpeg -c copy 리먹스 생방송 + 캐시 tee 로 중계한다. 여기서는 검색만 하므로
    즉시 반환(대기 0) — 해소·전송은 재생 버튼을 누른 항목만 일어난다.

    mode:client(googlevideo URL 직접)와 다른 점: client 는 맥과 같은 공인 IP 에서만
    재생되지만(IP 잠금) 릴레이는 어디서든 된다. 캐시 후엔 재다운로드도 없다.

    Args:
        query: 검색어 또는 유튜브 URL
        media: audio(기본) | video — 소리만 / 영상+소리
        count: 검색 결과 수 (1-10, URL 이면 무시)

    Returns:
        dict: {success, items: [{title, channel, duration, video_id, stream, thumb, is_video}]}
    """
    media = "video" if media == "video" else "audio"
    # URL 냄새가 날 때만 ID 추출 — extract_video_id 는 맨 11자 영숫자도 ID 로 보므로
    # 짧은 영어 검색어가 영상 ID 로 오인되지 않게 게이트를 건다.
    q = (query or "").strip()
    vid = extract_video_id(q) if ("youtu" in q or "://" in q) else None
    if vid:
        info = get_youtube_info(f"https://www.youtube.com/watch?v={vid}")
        entries = [{"video_id": vid,
                    "title": info.get("title", vid),
                    "channel": info.get("uploader", ""),
                    "duration": _format_duration(info.get("duration", 0))}]
    else:
        found = search_youtube(query, count=count)
        if not found.get("success"):
            return found
        entries = found.get("results", [])
    items = []
    for e in entries:
        v = e.get("video_id", "")
        items.append({
            "video_id": v,
            "title": e.get("title", ""),
            "channel": e.get("channel", ""),
            "duration": e.get("duration", ""),
            "stream": f"/yt/relay/{v}?kind={media}",
            # 저대역 판 — 느린 회선 표면이 자동 선택(영상만, 오디오는 이미 가볍다)
            "stream_low": (f"/yt/relay/{v}?kind=video&q=low" if media == "video" else ""),
            "thumb": f"https://i.ytimg.com/vi/{v}/mqdefault.jpg",
            "is_video": media == "video",
        })
    label = "영상" if media == "video" else "음악"
    return {
        "success": True,
        "media": media,
        "items": items,
        "message": f"{label} {len(items)}건 — 재생을 누르면 맥이 받으면서 바로 중계합니다 (유튜브 직접 접속 없음).",
    }


def play_youtube(query: str, mode: str = "audio", count: int = 5) -> dict:
    """유튜브 검색 후 재생

    Args:
        query: 검색어 또는 YouTube URL
        mode: 재생 모드 - "audio" (소리만, 기본), "video" (브라우저)
        count: 검색 결과 수 (1-25, 기본 5). URL 직접 지정 시 무시됨.
            상한 초과 시 clamped/requested 로 신고

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
    requested = int(count or 5)
    count = max(1, min(SEARCH_COUNT_MAX, requested))
    # 침묵 클램프 금지 — 검색 경로(search_youtube)와 같은 자로 신고한다.
    clamp_info = {}
    if requested != count:
        clamp_info = {
            'clamped': True,
            'requested': requested,
            'clamp_message': f'요청 {requested}건 → 상한 {SEARCH_COUNT_MAX}건으로 조정되어 검색했습니다.',
        }

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
            return {'success': False, 'error': f'영상 정보 조회 실패: {str(e)}'}
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
                return {'success': False, 'error': f'"{query}" 검색 결과가 없습니다.'}

            # 채널/플레이리스트 ID 필터링 (video ID만 남김: 11자, UC로 시작하지 않음)
            entries = [e for e in entries if e.get('id') and not e['id'].startswith('UC') and len(e['id']) <= 16]
            if not entries:
                return {'success': False, 'error': f'"{query}" 검색 결과에서 재생 가능한 영상을 찾지 못했습니다.'}

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
            return {'success': False, 'error': f'검색 실패: {str(e)}'}

    global _player_video_id, _player_mode, _player_title, _player_process, _player_duration

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
                result.update(clamp_info)
            return result

    # client 모드: 서버측 재생(ffplay) 대신 오디오 URL 을 resolve 해 클라이언트(폰/원격
    # WebView)가 직접 재생한다 — 라디오의 play_in_client 패턴과 동일(제네릭 런처 표면).
    # 분산 IBL: 폰서 [limbs:music]{op:play, mode:client} → 맥에 위임 → 맥 yt-dlp resolve →
    # play_in_client+stream_url 반환 → 폰 WebView <audio> 재생. 맥·폰이 같은 공인 IP(집 WiFi)면
    # googlevideo URL 직접 도달(실측 확인). 외출 시 모바일데이터는 후속(오디오 프록시 필요).
    # 서버측 플레이어를 건드리지 않으므로 _close_player() 전에 분기(맥 자신의 재생과 독립).
    if mode == "client":
        try:
            audio_url = _get_audio_url(video_id)
        except Exception as e:
            return {'success': False, 'error': f'오디오 URL resolve 실패: {str(e)}'}
        if not audio_url:
            return {'success': False, 'error': '오디오 스트림 URL을 가져올 수 없습니다.'}
        result = {
            'success': True,
            'play_in_client': True,
            'stream_url': audio_url,
            'video_id': video_id,
            'title': title,
            'channel': channel,
            'duration': _format_duration(duration),
            'mode': 'client',
            'message': f'재생: {title} - {channel} ({_format_duration(duration)})',
        }
        if not is_url:
            try:
                result['search_results'] = search_results
            except NameError:
                pass
            result.update(clamp_info)
        return result

    # 이전 재생 종료
    _close_player()
    _player_mode = mode

    if mode == "video":
        # video 모드: 기본 브라우저로 열기 (큰 화면)
        watch_url = f"https://www.youtube.com/watch?v={video_id}"
        if not open_url(watch_url):  # 전 OS 기본 브라우저 (맥 전용 'open' 대체)
            return {'success': False, 'error': '브라우저 열기 실패'}
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
                return {'success': False, 'error': '오디오 스트림 URL을 가져올 수 없습니다.'}
            _player_duration = int(duration or 0)  # seek 진행바용 곡 길이(초)
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
        result.update(clamp_info)

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
    # 전역이 비어 있어도(이전 백엔드가 띄운 고아) 표식 단 ffplay 가 살아있으면 정리한다.
    # → 옛 코드처럼 "재생 중인 항목이 없습니다"라는 거짓 성공을 내지 않는다.
    orphan = is_process_running_by_marker(YOUTUBE_MARKER)
    if vid or _player_process or orphan:
        _close_player()  # _player_process + 표식 고아 모두 종료
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
        return {'success': False, 'error': 'yt-dlp 패키지가 없습니다.'}

    # ★침묵 클램프 청산(2026-08-24 #repair B6): 조용히 깎는 대신 정직하게 거절한다.
    _requested = int(count or 3)
    if _requested > 5:
        return {'success': False, 'requested': _requested,
                'error': f'큐 담기는 한 번에 5곡까지입니다(요청 {_requested}). count 를 5 이하로 주세요.'}
    count = max(1, _requested)
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
            return {'success': False, 'error': f'영상 정보 조회 실패: {str(e)}'}
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
                return {'success': False, 'error': f'"{query}" 검색 결과가 없습니다.'}
            # 채널/플레이리스트 ID 필터링
            entries = [e for e in entries if e.get('id') and not e['id'].startswith('UC') and len(e['id']) <= 16]
            if not entries:
                return {'success': False, 'error': f'"{query}" 검색 결과에서 재생 가능한 영상을 찾지 못했습니다.'}
            selected = entries[0]
            video_id = selected.get('id', '')
            title = selected.get('title', '')
            channel = selected.get('channel', selected.get('uploader', ''))
            duration = selected.get('duration', 0)
        except Exception as e:
            return {'success': False, 'error': f'검색 실패: {str(e)}'}

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


def seek_youtube(position) -> dict:
    """현재 재생 중인 곡의 특정 지점(초)으로 점프.

    ffplay 는 실행 중 위치 이동이 불가하므로, 현 프로세스를 죽이고 같은 오디오 URL 을
    -ss <position> 으로 재시작한다(skip/next 와 동일한 kill+relaunch 기계 재사용).
    """
    global _player_process, _player_started_at
    try:
        pos = float(position)
    except (TypeError, ValueError):
        return {'success': False, 'error': 'position(초)이 올바르지 않습니다.'}
    if pos < 0:
        pos = 0.0

    with _player_lock:
        if not _player_video_id or not _player_audio_url:
            return {'success': False, 'error': '재생 중인 곡이 없습니다.'}
        # 오디오 모드(서버측 ffplay)만 seek 가능 — video/client 모드는 대상 아님
        if _player_mode != 'audio':
            return {'success': False, 'error': '이 재생 모드에서는 위치 이동을 지원하지 않습니다.'}

        dur = _player_duration or 0
        if dur and pos > dur - 1:
            pos = max(0.0, dur - 1)  # 끝 직전으로 클램프(-autoexit 즉시 종료 방지)

        audio_url = _player_audio_url
        # 현 ffplay 종료. _player_process 를 먼저 None 으로 바꿔, 락 대기 중이던 옛
        # 모니터 스레드가 깨어나도 `_player_process is not proc` 로 빠지게 한다(큐 오진행 방지).
        old = _player_process
        _player_process = None
        if old:
            try:
                old.terminate()
                old.wait(timeout=3)
            except Exception:
                try:
                    old.kill()
                except Exception:
                    pass

        # 같은 URL 을 -ss 로 재시작
        try:
            _start_ffplay(audio_url, seek=pos)
        except Exception as e:
            _player_started_at = None
            return {'success': False, 'error': f'위치 이동 실패: {str(e)}'}

        # 새 모니터 스레드(곡 끝나면 큐 진행)
        t = threading.Thread(target=_queue_monitor, daemon=True)
        t.start()

    return {
        'success': True,
        'message': f'{int(pos)}초 지점으로 이동했습니다.',
        'position': int(pos),
        'duration': int(_player_duration or 0),
    }


def get_queue() -> dict:
    """현재 재생 대기열 조회"""
    with _player_lock:
        now_playing = None
        if _player_video_id:
            # 위치(elapsed) 추정: seek 오프셋 + 재생 경과(벽시계). ffplay 는 정확한 재생
            # 헤드를 노출하지 않으므로 근사값 — 진행바/시간표시엔 충분하다.
            elapsed = 0
            if _player_started_at is not None:
                elapsed = _player_seek_offset + (time.time() - _player_started_at)
                if _player_duration and elapsed > _player_duration:
                    elapsed = float(_player_duration)
            now_playing = {
                'video_id': _player_video_id,
                'title': _player_title or '',
                'duration': int(_player_duration or 0),
                'elapsed': int(elapsed),
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
