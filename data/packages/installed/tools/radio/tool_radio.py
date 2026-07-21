"""
Radio Tool - 인터넷 라디오 검색 및 재생
Radio Browser API + 한국 방송사 직접 API + mpv 재생
"""

import os
import sys
import json
import time
from pathlib import Path
from threading import Lock

# common 유틸리티 사용
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.api_client import api_call_raw
from common.platform_utils import (
    find_binary, install_hint, spawn_detached,
    kill_processes_by_marker, is_process_running_by_marker,
)

# ─── 상수 ───

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
FAVORITES_PATH = os.path.join(DATA_DIR, "favorites.json")
# 재생기(ffplay)는 spawn_detached(유닉스 setsid / 윈도우 DETACHED_PROCESS)로 백엔드에서 분리 실행 →
# 백엔드(Electron 자식)가 죽어도 계속 재생된다.
# 그래서 모듈 전역(_player_process)만으로는 새 백엔드가 옛 재생기를 못 찾아 정지 불가·중복 재생.
# 해법: 라디오 ffplay 명령줄(-window_title)에 이 표식을 박아, 정지/재생 때 표식 단 프로세스를 모두 죽인다(psutil, 전 OS).
# (어느 백엔드가 띄웠든 무관 — "정지=음악 프로세스 종료"의 단순·확실한 구현.)
RADIO_MARKER = "indiebiz-radio-player"
RADIO_BROWSER_API = "https://de1.api.radio-browser.info"
USER_AGENT = "IndieBizOS/1.0"

# ─── 한국 방송사 채널 정의 ───

KOREAN_STATIONS = {
    # KBS (채널 코드: 21=1Radio, 22=CoolFM, 23=3Radio, 24=ClassicFM, 25=HappyFM)
    "kbs_1radio": {
        "name": "KBS 1Radio",
        "broadcaster": "KBS",
        "api": "kbs",
        "channel_code": "21",
        "description": "뉴스/시사/교양"
    },
    "kbs_coolfm": {
        "name": "KBS Cool FM",
        "broadcaster": "KBS",
        "api": "kbs",
        "channel_code": "22",
        "description": "대중음악/토크"
    },
    "kbs_classicfm": {
        "name": "KBS Classic FM",
        "broadcaster": "KBS",
        "api": "kbs",
        "channel_code": "24",
        "description": "클래식 음악"
    },
    "kbs_happyfm": {
        "name": "KBS Happy FM",
        "broadcaster": "KBS",
        "api": "kbs",
        "channel_code": "25",
        "description": "생활/정보"
    },
    "kbs_3radio": {
        "name": "KBS 3Radio",
        "broadcaster": "KBS",
        "api": "kbs",
        "channel_code": "23",
        "description": "교통/생활정보"
    },
    # MBC
    "mbc_sfm": {
        "name": "MBC Standard FM",
        "broadcaster": "MBC",
        "api": "mbc",
        "channel_code": "sfm",
        "description": "뉴스/시사/교양"
    },
    "mbc_fm4u": {
        "name": "MBC FM4U",
        "broadcaster": "MBC",
        "api": "mbc",
        "channel_code": "mfm",
        "description": "음악 전문"
    },
    "mbc_mini": {
        "name": "MBC mini (All That Music)",
        "broadcaster": "MBC",
        "api": "mbc",
        "channel_code": "chm",
        "description": "음악/예능"
    },
    # SBS 제외: 공식 스트림이 토큰 보호라 외부 클라이언트(mpv 포함) 403 — 재생 불가 (2026-06-11)
    # TBS
    "tbs_fm": {
        "name": "TBS FM",
        "broadcaster": "TBS",
        "api": "tbs",
        "channel_code": "fm",
        "description": "서울 교통방송"
    },
    "tbs_efm": {
        "name": "TBS eFM",
        "broadcaster": "TBS",
        "api": "tbs",
        "channel_code": "efm",
        "description": "영어 방송"
    },
    # CBS
    "cbs_sfm": {
        "name": "CBS Standard FM",
        "broadcaster": "CBS",
        "api": "cbs",
        "channel_code": "sfm",
        "description": "뉴스/시사"
    },
    # CBS Music FM 제외: 공식 호스트(aac/m-aac) 음악FM 경로 소멸 — 재생 불가 (2026-06-11)
    # EBS
    "ebs_fm": {
        "name": "EBS FM",
        "broadcaster": "EBS",
        "api": "ebs",
        "channel_code": "fm",
        "description": "교육/교양"
    },
}

# TBS 고정 URL
TBS_URLS = {
    "fm": "https://cdnfm.tbs.seoul.kr/tbs/_definst_/tbs_fm_web_360.smil/playlist.m3u8",
    "efm": "https://cdnefm.tbs.seoul.kr/tbs/_definst_/tbs_efm_web_360.smil/playlist.m3u8",
}

# CBS 고정 URL (2026-06-11: 호스트 aac → m-aac 로 이전, 표준FM 복구 검증. 음악FM은 경로 소멸로 제외)
CBS_URLS = {
    "sfm": "https://m-aac.cbs.co.kr/cbs939/cbs939.stream/playlist.m3u8",
}

# EBS 고정 URL (2026-06-11: 경로 fmradiofamily/bandibudistream → fmradiofamilypc/familypc1m)
EBS_URLS = {
    "fm": "https://ebsonair.ebs.co.kr/fmradiofamilypc/familypc1m/playlist.m3u8",
}

# ─── 재생 상태 관리 ───

_player_lock = Lock()
_player_process = None
_current_station = None
_play_start_time = None


def _kill_radio_mpv():
    """표식 단 라디오 mpv 를 모두 종료. 어느 백엔드가 띄웠든(창 닫기·재시작 후 고아 포함)
    상관없이 정지·중복재생을 한 방에 해결. 다른 용도 mpv 는 표식이 없어 영향 없음.
    psutil 기반이라 맥·윈도우·리눅스 동일 동작(구 pgrep/pkill 대체)."""
    return kill_processes_by_marker(RADIO_MARKER)


def _radio_mpv_running():
    """표식 단 라디오 mpv 가 살아있는지(전 OS)."""
    return is_process_running_by_marker(RADIO_MARKER)


# ─── HTTP 헬퍼 (common.api_client 사용) ───

def _http_get(url, timeout=10):
    """간단한 HTTP GET 요청 - api_call_raw 사용"""
    result = api_call_raw(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
        raw_response=True,
    )
    # api_call_raw는 에러 시 {"error": "..."} dict 반환
    if isinstance(result, dict) and "error" in result:
        raise Exception(result["error"])
    return result


def _http_get_json(url, timeout=10):
    """HTTP GET → JSON - api_call_raw 사용"""
    result = api_call_raw(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
    )
    # api_call_raw는 에러 시 {"error": "..."}, 성공 시 파싱된 JSON 반환
    if isinstance(result, dict) and "error" in result:
        raise Exception(result["error"])
    return result


# ─── Radio Browser API ───

def search_radio(name=None, tag=None, country=None, state=None, language=None, order=None, bitrateMin=None, limit=10):
    """Radio Browser API로 방송 검색"""
    limit = min(max(1, limit or 10), 50)

    # 정렬 기준 (기본: votes, random일 때는 reverse 안 함)
    order = order or "votes"
    valid_orders = ["votes", "clickcount", "random", "name", "bitrate"]
    if order not in valid_orders:
        order = "votes"

    params = {
        "limit": str(limit),
        "order": order,
        "hidebroken": "true",
    }
    if order != "random":
        params["reverse"] = "true"
    if name:
        params["name"] = name
    if tag:
        params["tag"] = tag
    if country:
        params["countrycode"] = country.upper()
    if state:
        params["state"] = state
    if language:
        params["language"] = language.lower()
    if bitrateMin and bitrateMin > 0:
        params["bitrateMin"] = str(bitrateMin)

    url = f"{RADIO_BROWSER_API}/json/stations/search"
    data = api_call_raw(
        url,
        headers={"User-Agent": USER_AGENT},
        params=params,
    )
    if isinstance(data, dict) and "error" in data:
        return json.dumps({"success": False, "error": data["error"]}, ensure_ascii=False)
    if isinstance(data, str):
        data = json.loads(data)

    results = []
    for s in data:
        results.append({
            "name": s.get("name", "").strip(),
            "country": s.get("country", ""),
            "countrycode": s.get("countrycode", ""),
            "language": s.get("language", ""),
            "tags": s.get("tags", ""),
            "codec": s.get("codec", ""),
            "bitrate": s.get("bitrate", 0),
            "votes": s.get("votes", 0),
            "stream_url": s.get("url_resolved", s.get("url", "")),
            "homepage": s.get("homepage", ""),
            "favicon": s.get("favicon", ""),
        })

    return json.dumps({
        "success": True,
        "count": len(results),
        # 단일 통화 — native 방송국 dict(name/country/tags/bitrate/stream_url/favicon 등 풍부)를 items로.
        # (옛 records 5칸 변환은 bitrate/stream_url 등을 버려 손실적이라 은퇴.)
        "items": results,
    }, ensure_ascii=False)


# ─── 한국 방송 ───

def _get_kbs_stream_url(channel_code):
    """KBS API에서 실시간 스트림 URL 가져오기"""
    url = f"https://cfpwwwapi.kbs.co.kr/api/v1/landing/live/channel_code/{channel_code}"
    data = _http_get_json(url)
    try:
        items = data.get("channel_item", [])
        if items:
            return items[0].get("service_url", "")
    except (KeyError, IndexError):
        pass
    return ""


def _get_mbc_stream_url(channel_code):
    """MBC API에서 실시간 스트림 URL 가져오기"""
    url = f"https://sminiplay.imbc.com/aacplay.ashx?agent=webapp&channel={channel_code}"
    return _http_get(url).strip()


def _get_korean_stream_url(station_id):
    """한국 방송 station_id로 스트림 URL 획득"""
    station = KOREAN_STATIONS.get(station_id)
    if not station:
        return None, f"알 수 없는 방송: {station_id}"

    api = station["api"]
    code = station["channel_code"]

    try:
        if api == "kbs":
            url = _get_kbs_stream_url(code)
        elif api == "mbc":
            url = _get_mbc_stream_url(code)
        elif api == "tbs":
            url = TBS_URLS.get(code, "")
        elif api == "cbs":
            url = CBS_URLS.get(code, "")
        elif api == "ebs":
            url = EBS_URLS.get(code, "")
        else:
            return None, f"미지원 API: {api}"

        if not url:
            return None, f"{station['name']} 스트림 URL을 가져올 수 없습니다"
        return url, None
    except Exception as e:
        return None, f"{station['name']} URL 조회 실패: {str(e)}"


def get_korean_radio(broadcaster=None):
    """한국 방송 목록 반환"""
    stations = []
    for sid, info in KOREAN_STATIONS.items():
        if broadcaster and info["broadcaster"].upper() != broadcaster.upper():
            continue
        stations.append({
            "station_id": sid,
            "name": info["name"],
            "broadcaster": info["broadcaster"],
            "description": info["description"],
        })

    return json.dumps({
        "success": True,
        "count": len(stations),
        "items": stations,  # 단일 통화 — native 방송국 dict 직접
        "tip": "play_radio의 station_id 파라미터에 station_id를 넣으면 바로 재생됩니다.",
    }, ensure_ascii=False)


# ─── 재생 제어 (ffplay) ───
# 재생기는 ffplay(ffmpeg 동반). mpv 별도 설치가 필요 없고, ffmpeg 하나로 라디오 재생 +
# 유튜브 재생·다운로드까지 커버된다. 윈도우에 없으면 ffmpeg_provision 이 자동 공급한다.

def _find_ffplay():
    """ffplay 실행 경로 찾기 (전 OS — PATH + 자동 공급 bin + OS별 표준 경로 폴백)."""
    return find_binary("ffplay")


def play_radio(station_id=None, stream_url=None, volume=70, name=None, mode=None):
    """라디오 재생. name: stream_url 재생 시 채널명(검색 결과 등) — 미지정 시 '외부 방송'.

    mode: 출력지 — "client"(보고 있는 기기에서) / "host"(이 기계 스피커에서).
      미지정이면 *요청 표면*이 정한다(브라우저=client, 그 기계 자신=host).
      2026-07-21: 옛 판정은 `INDIEBIZ_PROFILE=="phone"`(어느 몸이 실행하는가)이었는데,
      원격런처는 맥이 실행하고 폰이 보고 있어 폰에서 눌러도 맥 스피커로 나갔다.
      유튜브뮤직([limbs:music]{op:play, mode:"client"})이 이미 쓰는 축을 여기 맞춘다.
    """
    global _player_process, _current_station, _play_start_time

    # 스트림 URL 결정 (mpv 유무와 무관 — 폰은 클라이언트가 재생)
    station_name = None
    if station_id:
        url, err = _get_korean_stream_url(station_id)
        if err:
            return json.dumps({"success": False, "error": err}, ensure_ascii=False)
        stream_url = url
        station_name = KOREAN_STATIONS[station_id]["name"]
    elif stream_url:
        station_name = (name or "").strip() or "외부 방송"
    else:
        return json.dumps({
            "success": False,
            "error": "station_id 또는 stream_url 중 하나를 지정해주세요.",
        }, ensure_ascii=False)

    try:
        volume = int(volume)
    except (TypeError, ValueError):
        volume = 70
    volume = max(0, min(100, volume))

    # 출력지 결정: 명시 mode 가 최우선, 없으면 표면이 정한다.
    #  - 브라우저 표면(원격런처·포털·폰 WebView) → client: stream_url 을 돌려주면
    #    그쪽 <audio>/hls.js 가 직접 문다(소리는 보고 있는 기기에서).
    #  - 표면 힌트 없음(데스크탑 일렉트론 = 맥 자신) → host: ffplay 로 이 기계에서.
    #  - 폰 네이티브 백엔드는 ffplay 자체가 없으므로 최후 폴백으로 몸 프로파일도 본다.
    mode = (mode or "").strip().lower() or None
    if mode not in ("client", "host", None):
        mode = None
    if mode is None:
        try:
            from thread_context import is_web_surface
            web_surface = is_web_surface()
        except Exception:
            web_surface = False
        mode = "client" if (web_surface or os.environ.get("INDIEBIZ_PROFILE") == "phone") else "host"

    if mode == "client":
        return json.dumps({
            "success": True,
            "play_in_client": True,
            "stream_url": stream_url,
            "station": station_name,
            "volume": volume,
            "message": f"{station_name} 재생",
        }, ensure_ascii=False)

    # PC: ffplay 로 재생 (없으면 윈도우는 자동 공급 시도)
    ffplay_path = _find_ffplay()
    if not ffplay_path:
        try:
            from ffmpeg_provision import provision_async, is_provisioning
            provision_async()  # 백그라운드 다운로드 시작(윈도우) — 없으면 no-op
            if os.name == "nt":
                return json.dumps({
                    "success": False,
                    "provisioning": True,
                    "error": "재생기(ffmpeg)를 자동 설치하는 중입니다 (최초 1회, 수십 초). "
                             "잠시 후 다시 재생을 눌러주세요." if is_provisioning() or True else "",
                }, ensure_ascii=False)
        except Exception:
            pass
        return json.dumps({
            "success": False,
            "error": install_hint("ffplay"),
        }, ensure_ascii=False)

    # 기존 라디오 재생기 전부 종료(이 백엔드 것·옛 백엔드 고아 모두) → 중복 재생 방지
    with _player_lock:
        _kill_radio_mpv()

        # ffplay 실행 — -window_title 에 표식을 박아 정지 때 명령줄(psutil)로 찾는다(-nodisp 라 창 없음).
        cmd = [
            ffplay_path,
            "-nodisp",
            "-autoexit",
            "-loglevel", "quiet",
            "-window_title", RADIO_MARKER,
            "-volume", str(volume),
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            stream_url,
        ]

        try:
            # 백그라운드 분리 실행 — 유닉스 setsid / 윈도우 DETACHED_PROCESS 를 흡수
            _player_process = spawn_detached(cmd)
            _current_station = {
                "station_id": station_id,
                "name": station_name,
                "stream_url": stream_url,
                "volume": volume,
            }
            _play_start_time = time.time()

            # 잠시 대기 후 프로세스 살아있는지 확인
            time.sleep(1)
            if _player_process.poll() is not None:
                _player_process = None
                _current_station = None
                _play_start_time = None
                return json.dumps({
                    "success": False,
                    "error": "스트림 재생 실패. URL이 유효하지 않거나 접속할 수 없습니다.",
                }, ensure_ascii=False)

        except Exception as e:
            _player_process = None
            _current_station = None
            return json.dumps({
                "success": False,
                "error": f"재생기(ffplay) 실행 실패: {str(e)}",
            }, ensure_ascii=False)

    return json.dumps({
        "success": True,
        "message": f"{station_name} 재생을 시작합니다.",
        "station": station_name,
        "volume": volume,
    }, ensure_ascii=False)


def stop_radio():
    """재생 중지"""
    global _player_process, _current_station, _play_start_time

    # 폰: 클라이언트(WebView)가 재생 중 → 클라이언트에 중지 지시
    if os.environ.get("INDIEBIZ_PROFILE") == "phone":
        return json.dumps({"success": True, "stop_in_client": True, "message": "재생 중지"}, ensure_ascii=False)

    with _player_lock:
        station_name = _current_station.get("name") if _current_station else None
        # 표식 단 라디오 mpv 를 모두 종료 — 이 백엔드 것이든, 창 닫기/재시작으로 생긴 고아든 무관
        killed = _kill_radio_mpv()
        _player_process = None
        _current_station = None
        _play_start_time = None

    # 브라우저 표면에서 누른 '정지'는 그쪽 재생도 함께 멈춘다 — 표면이 client 로 틀었으면
    # 소리는 거기서 나고 있고, 맥에 옛 ffplay 가 남아 있을 수도 있으므로 둘 다 끈다.
    # (미니플레이어의 ■정지는 IBL 왕복 없이 stopRadioStream 을 직접 부른다 — 그쪽은 무관.)
    payload = {
        "success": True,
        "message": (f"{station_name or '라디오'} 재생을 중지했습니다." if killed
                    else "재생 중인 라디오가 없습니다."),
    }
    try:
        from thread_context import is_web_surface
        if is_web_surface():
            payload["stop_in_client"] = True
            if not killed:
                payload["message"] = "재생을 중지했습니다."
    except Exception:
        pass
    return json.dumps(payload, ensure_ascii=False)


def radio_status():
    """재생 상태 확인"""
    global _player_process, _current_station, _play_start_time

    with _player_lock:
        if not _player_process or _player_process.poll() is not None:
            # 프로세스가 죽었으면 상태 정리
            if _player_process and _player_process.poll() is not None:
                _player_process = None
                _current_station = None
                _play_start_time = None
            # 모듈이 추적 못 하는 옛 mpv(이전 백엔드/창 닫기 고아)가 살아있으면 재생 중으로 보고
            if _radio_mpv_running():
                return json.dumps({
                    "success": True,
                    "playing": True,
                    "message": "라디오가 재생 중입니다.",
                }, ensure_ascii=False)
            return json.dumps({
                "success": True,
                "playing": False,
                "message": "재생 중인 라디오가 없습니다.",
            }, ensure_ascii=False)

        elapsed = int(time.time() - _play_start_time) if _play_start_time else 0
        minutes, seconds = divmod(elapsed, 60)
        hours, minutes = divmod(minutes, 60)

        if hours > 0:
            duration_str = f"{hours}시간 {minutes}분 {seconds}초"
        elif minutes > 0:
            duration_str = f"{minutes}분 {seconds}초"
        else:
            duration_str = f"{seconds}초"

        return json.dumps({
            "success": True,
            "playing": True,
            "station": _current_station.get("name", "알 수 없음"),
            "station_id": _current_station.get("station_id"),
            "volume": _current_station.get("volume", 70),
            "duration": duration_str,
            "elapsed_seconds": elapsed,
        }, ensure_ascii=False)


def set_radio_volume(volume):
    """볼륨 조절 - mpv 재시작 방식"""
    global _player_process, _current_station, _play_start_time

    try:
        volume = int(volume)
    except (TypeError, ValueError):
        volume = 70
    volume = max(0, min(100, volume))

    with _player_lock:
        if not _player_process or _player_process.poll() is not None:
            return json.dumps({
                "success": False,
                "error": "재생 중인 라디오가 없습니다.",
            }, ensure_ascii=False)

        if not _current_station:
            return json.dumps({
                "success": False,
                "error": "현재 방송 정보가 없습니다.",
            }, ensure_ascii=False)

    # 현재 방송 정보 저장 후 재시작
    sid = _current_station.get("station_id")
    surl = _current_station.get("stream_url")

    return play_radio(station_id=sid, stream_url=surl, volume=volume)


# ─── 즐겨찾기 ───

def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _load_favorites():
    _ensure_data_dir()
    if os.path.isfile(FAVORITES_PATH):
        try:
            with open(FAVORITES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_favorites(favs):
    _ensure_data_dir()
    with open(FAVORITES_PATH, "w", encoding="utf-8") as f:
        json.dump(favs, f, ensure_ascii=False, indent=2)


def get_radio_favorites():
    """즐겨찾기 목록"""
    favs = _load_favorites()
    return json.dumps({
        "success": True,
        "count": len(favs),
        "items": favs,  # 단일 통화 — native 즐겨찾기 dict 직접
    }, ensure_ascii=False)


def save_radio_favorite(station_id=None, name=None, stream_url=None):
    """즐겨찾기 저장"""
    # 현재 재생 중인 방송 자동 저장
    if not name and not station_id and _current_station:
        station_id = _current_station.get("station_id")
        name = _current_station.get("name")
        stream_url = _current_station.get("stream_url")

    if not name:
        if station_id and station_id in KOREAN_STATIONS:
            name = KOREAN_STATIONS[station_id]["name"]
        else:
            return json.dumps({
                "success": False,
                "error": "방송 이름(name)을 지정해주세요.",
            }, ensure_ascii=False)

    favs = _load_favorites()

    # 중복 체크
    for f in favs:
        if f.get("name") == name:
            return json.dumps({
                "success": True,
                "message": f"'{name}'은(는) 이미 즐겨찾기에 있습니다.",
            }, ensure_ascii=False)

    entry = {
        "name": name,
        "added_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if station_id:
        entry["station_id"] = station_id
    if stream_url:
        entry["stream_url"] = stream_url

    favs.append(entry)
    _save_favorites(favs)

    return json.dumps({
        "success": True,
        "message": f"'{name}'을(를) 즐겨찾기에 추가했습니다.",
    }, ensure_ascii=False)


def remove_radio_favorite(name=None, stream_url=None):
    """즐겨찾기 제거 (이름 또는 스트림 URL로)."""
    favs = _load_favorites()
    if not name and not stream_url:
        return json.dumps({
            "success": False,
            "error": "name 또는 stream_url 중 하나가 필요합니다.",
        }, ensure_ascii=False)

    def _match(f):
        return (name and f.get("name") == name) or (stream_url and f.get("stream_url") == stream_url)

    new_favs = [f for f in favs if not _match(f)]

    if len(new_favs) == len(favs):
        _key = name or stream_url
        return json.dumps({
            "success": False,
            "error": f"'{_key}'을(를) 즐겨찾기에서 찾을 수 없습니다.",
        }, ensure_ascii=False)

    _save_favorites(new_favs)
    return json.dumps({
        "success": True,
        "message": f"'{name or stream_url}'을(를) 즐겨찾기에서 제거했습니다.",
    }, ensure_ascii=False)
