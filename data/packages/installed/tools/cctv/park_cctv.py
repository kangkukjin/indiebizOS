"""
국립공원 실시간 CCTV

국립공원공단(knps.or.kr) 및 제주특별자치도(한라산) CCTV를 검색합니다.
공식 API가 없으므로 알려진 CCTV 정보 + 웹 스크래핑을 사용합니다.
"""

import json
import os
import re
import time
import requests
from typing import List, Dict, Optional

from common import success_response, error_response, HEADERS

# 캐시 설정
_park_cache = {}  # park_id -> {"data": [...], "timestamp": 0}
_CACHE_TTL = 3600  # 1시간

# 국립공원 CCTV 정보 (알려진 목록)
PARK_LIST = [
    {
        "id": "jirisan",
        "name": "지리산",
        "cctvs": [
            {"name": "장터목대피소", "page_url": "https://www.knps.or.kr/common/cctv/cctv1.html"},
            {"name": "천왕봉", "page_url": "https://www.knps.or.kr/common/cctv/cctv1.html"},
        ]
    },
    {
        "id": "gyeryongsan",
        "name": "계룡산",
        "cctvs": [
            {"name": "관음봉", "page_url": "https://www.knps.or.kr/common/cctv/cctv2.html"},
        ]
    },
    {
        "id": "seoraksan",
        "name": "설악산",
        "cctvs": [
            {"name": "울산바위", "page_url": "https://www.knps.or.kr/common/cctv/cctv3.html"},
            {"name": "대청봉", "page_url": "https://www.knps.or.kr/common/cctv/cctv3.html"},
        ]
    },
    {
        "id": "songnisan",
        "name": "속리산",
        "cctvs": [
            {"name": "천왕봉", "page_url": "https://www.knps.or.kr/common/cctv/cctv4.html"},
        ]
    },
    {
        "id": "naejangsan",
        "name": "내장산",
        "cctvs": [
            {"name": "내장산전경", "page_url": "https://www.knps.or.kr/common/cctv/cctv5.html"},
        ]
    },
    {
        "id": "gayasan",
        "name": "가야산",
        "cctvs": [
            {"name": "상왕봉", "page_url": "https://www.knps.or.kr/common/cctv/cctv6.html"},
        ]
    },
    {
        "id": "deogyusan",
        "name": "덕유산",
        "cctvs": [
            {"name": "향적봉", "page_url": "https://www.knps.or.kr/common/cctv/cctv7.html"},
            {"name": "설천봉", "page_url": "https://www.knps.or.kr/common/cctv/cctv7.html"},
        ]
    },
    {
        "id": "odaesan",
        "name": "오대산",
        "cctvs": [
            {"name": "비로봉", "page_url": "https://www.knps.or.kr/common/cctv/cctv8.html"},
        ]
    },
    {
        "id": "juwangsan",
        "name": "주왕산",
        "cctvs": [
            {"name": "주왕산전경", "page_url": "https://www.knps.or.kr/common/cctv/cctv9.html"},
        ]
    },
    {
        "id": "chiaksan",
        "name": "치악산",
        "cctvs": [
            {"name": "비로봉", "page_url": "https://www.knps.or.kr/common/cctv/cctv10.html"},
        ]
    },
    {
        "id": "wolaksan",
        "name": "월악산",
        "cctvs": [
            {"name": "영봉", "page_url": "https://www.knps.or.kr/common/cctv/cctv11.html"},
        ]
    },
    {
        "id": "bukhansan",
        "name": "북한산",
        "cctvs": [
            {"name": "백운대", "page_url": "https://www.knps.or.kr/common/cctv/cctv12.html"},
        ]
    },
    {
        "id": "sobaeksan",
        "name": "소백산",
        "cctvs": [
            {"name": "비로봉", "page_url": "https://www.knps.or.kr/common/cctv/cctv13.html"},
        ]
    },
    {
        "id": "wolchulsan",
        "name": "월출산",
        "cctvs": [
            {"name": "천황봉", "page_url": "https://www.knps.or.kr/common/cctv/cctv14.html"},
        ]
    },
    {
        "id": "mudeungsan",
        "name": "무등산",
        "cctvs": [
            {"name": "무등산전경", "page_url": "https://www.knps.or.kr/common/cctv/cctv15.html"},
        ]
    },
    {
        "id": "taebaeksan",
        "name": "태백산",
        "cctvs": [
            {"name": "천제단", "page_url": "https://www.knps.or.kr/common/cctv/cctv16.html"},
        ]
    },
    {
        "id": "hallasan",
        "name": "한라산",
        "cctvs": [
            {"name": "백록담", "page_url": "https://www.jeju.go.kr/tool/halla/cctv_01.html"},
            {"name": "왕관릉", "page_url": "https://www.jeju.go.kr/tool/halla/cctv_01.html"},
            {"name": "윗세오름", "page_url": "https://www.jeju.go.kr/tool/halla/cctv_01.html"},
            {"name": "어승생악", "page_url": "https://www.jeju.go.kr/tool/halla/cctv_01.html"},
            {"name": "1100도로", "page_url": "https://www.jeju.go.kr/tool/halla/cctv_01.html"},
        ]
    },
]


def _scrape_park_streams(page_url: str) -> List[str]:
    """CCTV 페이지에서 스트리밍 URL 추출"""
    try:
        response = requests.get(page_url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        html = response.text

        stream_urls = []

        # m3u8 HLS 스트림 찾기
        m3u8 = re.findall(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
        stream_urls.extend(m3u8)

        # rtmp/rtsp 스트림 찾기
        rtmp = re.findall(r'(rtmp://[^\s"\'<>]+)', html)
        stream_urls.extend(rtmp)

        # video/source 태그에서 찾기
        video_src = re.findall(r'<(?:video|source)[^>]+src=["\']([^"\']+)["\']', html)
        stream_urls.extend(video_src)

        # iframe 내 video URL 찾기
        iframe_src = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html)
        for iframe_url in iframe_src:
            if "cctv" in iframe_url.lower() or "stream" in iframe_url.lower() or "live" in iframe_url.lower():
                try:
                    iframe_resp = requests.get(iframe_url, headers=HEADERS, timeout=10)
                    iframe_html = iframe_resp.text
                    inner_m3u8 = re.findall(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', iframe_html)
                    stream_urls.extend(inner_m3u8)
                    inner_video = re.findall(r'<(?:video|source)[^>]+src=["\']([^"\']+)["\']', iframe_html)
                    stream_urls.extend(inner_video)
                except Exception:
                    pass

        # JavaScript 변수에서 찾기
        js_urls = re.findall(r'(?:src|url|stream|source)\s*[:=]\s*["\']([^"\']+(?:\.m3u8|\.mp4|\.flv)[^\s"\']*)["\']', html)
        stream_urls.extend(js_urls)

        return list(set(stream_urls))
    except Exception as e:
        print(f"[CCTV] 국립공원 페이지 스크래핑 오류 ({page_url}): {e}")
        return []


def _get_park_cctvs(park_info: dict) -> List[Dict]:
    """특정 국립공원의 CCTV 정보 가져오기"""
    park_id = park_info["id"]
    now = time.time()

    # 캐시 확인
    if park_id in _park_cache and (now - _park_cache[park_id]["timestamp"]) < _CACHE_TTL:
        return _park_cache[park_id]["data"]

    results = []
    # 중복 페이지 URL 방지
    scraped_pages = set()

    for cctv_info in park_info["cctvs"]:
        page_url = cctv_info["page_url"]
        stream_urls = []

        if page_url not in scraped_pages:
            stream_urls = _scrape_park_streams(page_url)
            scraped_pages.add(page_url)

        cctv_entry = {
            "park_name": park_info["name"],
            "name": cctv_info["name"],
            "page_url": page_url,
            "stream_url": stream_urls[0] if stream_urls else "",
            "stream_type": "hls" if stream_urls and ".m3u8" in stream_urls[0] else "",
            "capturable": bool(stream_urls),
            "source": "national_parks"
        }
        results.append(cctv_entry)

    # 캐시 저장
    _park_cache[park_id] = {"data": results, "timestamp": now}
    return results


def search_park_cctv(park_name: str = None, keyword: str = None) -> str:
    """국립공원 CCTV 검색"""
    try:
        results = []

        # 특정 공원 또는 전체
        parks_to_search = PARK_LIST
        if park_name:
            park_name_lower = park_name.lower()
            parks_to_search = [p for p in PARK_LIST if park_name_lower in p["name"].lower()]
            if not parks_to_search:
                return success_response(
                    source="national_parks",
                    count=0,
                    message=f"'{park_name}' 국립공원을 찾을 수 없습니다.",
                    available_parks=[p["name"] for p in PARK_LIST],
                    cctvs=[]
                )

        for park in parks_to_search:
            cctvs = _get_park_cctvs(park)
            results.extend(cctvs)

        # 키워드 필터
        if keyword:
            keyword_lower = keyword.lower()
            results = [c for c in results
                       if keyword_lower in c.get("name", "").lower()
                       or keyword_lower in c.get("park_name", "").lower()]

        return success_response(
            source="national_parks",
            count=len(results),
            cctvs=results,
            note="국립공원공단 CCTV. 기상/통신 상황에 따라 영상이 중단될 수 있습니다."
        )
    except Exception as e:
        return error_response(str(e))


if __name__ == "__main__":
    print("국립공원 CCTV 모듈")
    print(f"등록된 국립공원: {len(PARK_LIST)}개")
    for park in PARK_LIST:
        print(f"  - {park['name']} ({len(park['cctvs'])}개 CCTV)")

    print("\n[테스트] 설악산 CCTV 검색...")
    result = search_park_cctv(park_name="설악산")
    data = json.loads(result)
    print(f"결과: {data.get('count', 0)}개")
    if data.get("cctvs"):
        for c in data["cctvs"]:
            print(f"  - {c['park_name']} {c['name']}: capturable={c.get('capturable', False)}")
