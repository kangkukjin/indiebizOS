"""
Radio Tool - 인터넷 라디오 검색 및 재생
Radio Browser API + 한국 방송사 직접 API + mpv 재생
"""

import os
import sys
import json
import time
import signal
import subprocess
from pathlib import Path
from threading import Lock

# common 유틸리티 사용
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.api_client import api_call_raw

# ─── 상수 ───

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
FAVORITES_PATH = os.path.join(DATA_DIR, "favorites.json")
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
    # SBS
    "sbs_powerfm": {
        "name": "SBS Power FM",
        "broadcaster": "SBS",
        "api": "sbs",
        "channel_code": "powerfm",
        "description": "대중음악/토크"
    },
    "sbs_lovefm": {
        "name": "SBS Love FM",
        "broadcaster": "SBS",
        "api": "sbs",
        "channel_code": "lovefm",
        "description": "뉴스/시사/교양"
    },
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
    "cbs_musicfm": {
        "name": "CBS Music FM",
        "broadcaster": "CBS",
        "api": "cbs",
        "channel_code": "mfm",
        "description": "음악 전문"
    },
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

# CBS 고정 URL
CBS_URLS = {
    "sfm": "https://aac.cbs.co.kr/cbs939/cbs939.stream/playlist.m3u8",
    "mfm": "https://aac.cbs.co.kr/mfm961/mfm961.stream/playlist.m3u8",
}

# EBS 고정 URL
EBS_URLS = {
    "fm": "https://ebsonair.ebs.co.kr/fmradiofamily/bandibudistream/playlist.m3u8",
}

# ─── 재생 상태 관리 ───

_player_lock = Lock()
_player_process = None
_current_station = None
_play_start_time = None


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
        "stations": results,
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


def _get_sbs_stream_url(channel_code):
    """SBS API에서 실시간 스트림 URL 가져오기 (텍스트 URL 반환)"""
    url = f"https://apis.sbs.co.kr/play-api/1.0/livestream/media/{channel_code}?protocol=hls&ssl=Y"
    text = _http_get(url).strip()
    # SBS는 URL을 텍스트로 직접 반환
    if text.startswith("http"):
        return text
    # JSON 형태인 경우 대비
    try:
        data = json.loads(text)
        return data.get("onair", {}).get("source", {}).get("mediasource", {}).get("mediaurl", "")
    except (json.JSONDecodeError, KeyError, AttributeError):
        pass
    return ""


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
        elif api == "sbs":
            url = _get_sbs_stream_url(code)
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
        "stations": stations,
        "tip": "play_radio의 station_id 파라미터에 station_id를 넣으면 바로 재생됩니다.",
    }, ensure_ascii=False)


# ─── 재생 제어 (mpv) ───

def _find_mpv():
    """mpv 실행 경로 찾기"""
    for path in ["/opt/homebrew/bin/mpv", "/usr/local/bin/mpv", "/usr/bin/mpv"]:
        if os.path.isfile(path):
            return path
    # PATH에서 찾기
    try:
        result = subprocess.run(["which", "mpv"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def play_radio(station_id=None, stream_url=None, volume=70):
    """라디오 재생"""
    global _player_process, _current_station, _play_start_time

    mpv_path = _find_mpv()
    if not mpv_path:
        return json.dumps({
            "success": False,
            "error": "mpv가 설치되어 있지 않습니다. 'brew install mpv'로 설치해주세요.",
        }, ensure_ascii=False)

    # 스트림 URL 결정
    station_name = None
    if station_id:
        url, err = _get_korean_stream_url(station_id)
        if err:
            return json.dumps({"success": False, "error": err}, ensure_ascii=False)
        stream_url = url
        station_name = KOREAN_STATIONS[station_id]["name"]
    elif stream_url:
        station_name = "외부 방송"
    else:
        return json.dumps({
            "success": False,
            "error": "station_id 또는 stream_url 중 하나를 지정해주세요.",
        }, ensure_ascii=False)

    volume = max(0, min(100, volume or 70))

    # 기존 재생 중지
    with _player_lock:
        if _player_process and _player_process.poll() is None:
            try:
                _player_process.terminate()
                _player_process.wait(timeout=3)
            except Exception:
                try:
                    _player_process.kill()
                except Exception:
                    pass

        # mpv 실행
        cmd = [
            mpv_path,
            "--no-video",
            "--really-quiet",
            f"--volume={volume}",
            "--cache=yes",
            "--cache-secs=10",
            "--demuxer-max-bytes=500KiB",
            stream_url,
        ]

        try:
            _player_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid,
            )
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
                "error": f"mpv 실행 실패: {str(e)}",
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

    with _player_lock:
        if not _player_process or _player_process.poll() is not None:
            _player_process = None
            _current_station = None
            _play_start_time = None
            return json.dumps({
                "success": True,
                "message": "재생 중인 라디오가 없습니다.",
            }, ensure_ascii=False)

        station_name = _current_station.get("name", "알 수 없음") if _current_station else "알 수 없음"

        try:
            os.killpg(os.getpgid(_player_process.pid), signal.SIGTERM)
            _player_process.wait(timeout=3)
        except Exception:
            try:
                _player_process.kill()
            except Exception:
                pass

        _player_process = None
        _current_station = None
        _play_start_time = None

    return json.dumps({
        "success": True,
        "message": f"{station_name} 재생을 중지했습니다.",
    }, ensure_ascii=False)


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
        "favorites": favs,
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


def remove_radio_favorite(name):
    """즐겨찾기 제거"""
    favs = _load_favorites()
    new_favs = [f for f in favs if f.get("name") != name]

    if len(new_favs) == len(favs):
        return json.dumps({
            "success": False,
            "error": f"'{name}'을(를) 즐겨찾기에서 찾을 수 없습니다.",
        }, ensure_ascii=False)

    _save_favorites(new_favs)
    return json.dumps({
        "success": True,
        "message": f"'{name}'을(를) 즐겨찾기에서 제거했습니다.",
    }, ensure_ascii=False)
