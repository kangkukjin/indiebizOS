"""
해양수산부 연안 CCTV

coast.mof.go.kr의 연안침식 모니터링 CCTV 및 주요 해수욕장 CCTV를 검색합니다.
공식 API가 없으므로 알려진 CCTV 목록 + 웹 스크래핑을 사용합니다.
"""

import json
import os
import re
import time
import requests
from typing import List, Dict, Optional

from common import success_response, error_response, HEADERS

# 캐시 설정
_coastal_cache = {"data": None, "timestamp": 0}
_CACHE_TTL = 3600  # 1시간

# 알려진 해양수산부 연안 CCTV 목록 (fallback + 기본 데이터)
KNOWN_COASTAL_CCTVS = [
    {"name": "해운대 해수욕장", "region": "부산", "lat": 35.1587, "lng": 129.1604,
     "page_url": "https://coast.mof.go.kr/coastScene/coastMediaService.do"},
    {"name": "광안리 해수욕장", "region": "부산", "lat": 35.1533, "lng": 129.1186,
     "page_url": "https://coast.mof.go.kr/coastScene/coastMediaService.do"},
    {"name": "송정 해수욕장", "region": "부산", "lat": 35.1789, "lng": 129.2001,
     "page_url": "https://coast.mof.go.kr/coastScene/coastMediaService.do"},
    {"name": "경포 해수욕장", "region": "강원", "lat": 37.8056, "lng": 128.9094,
     "page_url": "https://coast.mof.go.kr/coastScene/coastMediaService.do"},
    {"name": "속초 해수욕장", "region": "강원", "lat": 38.1906, "lng": 128.6011,
     "page_url": "https://coast.mof.go.kr/coastScene/coastMediaService.do"},
    {"name": "낙산 해수욕장", "region": "강원", "lat": 38.1172, "lng": 128.6319,
     "page_url": "https://coast.mof.go.kr/coastScene/coastMediaService.do"},
    {"name": "강문 해수욕장", "region": "강원", "lat": 37.7956, "lng": 128.9164,
     "page_url": "https://coast.mof.go.kr/coastScene/coastMediaService.do"},
    {"name": "망상 해수욕장", "region": "강원", "lat": 37.5789, "lng": 129.1139,
     "page_url": "https://coast.mof.go.kr/coastScene/coastMediaService.do"},
    {"name": "대천 해수욕장", "region": "충남", "lat": 36.3167, "lng": 126.5139,
     "page_url": "https://coast.mof.go.kr/coastScene/coastMediaService.do"},
    {"name": "만리포 해수욕장", "region": "충남", "lat": 36.7872, "lng": 126.1419,
     "page_url": "https://coast.mof.go.kr/coastScene/coastMediaService.do"},
    {"name": "을왕리 해수욕장", "region": "인천", "lat": 37.4459, "lng": 126.3722,
     "page_url": "https://coast.mof.go.kr/coastScene/coastMediaService.do"},
    {"name": "중문 해수욕장", "region": "제주", "lat": 33.2439, "lng": 126.4106,
     "page_url": "https://coast.mof.go.kr/coastScene/coastMediaService.do"},
    {"name": "협재 해수욕장", "region": "제주", "lat": 33.3942, "lng": 126.2397,
     "page_url": "https://coast.mof.go.kr/coastScene/coastMediaService.do"},
    {"name": "함덕 해수욕장", "region": "제주", "lat": 33.5433, "lng": 126.6694,
     "page_url": "https://coast.mof.go.kr/coastScene/coastMediaService.do"},
    {"name": "이호테우 해수욕장", "region": "제주", "lat": 33.4992, "lng": 126.4528,
     "page_url": "https://coast.mof.go.kr/coastScene/coastMediaService.do"},
    {"name": "고래불 해수욕장", "region": "경북", "lat": 36.4917, "lng": 129.4181,
     "page_url": "https://coast.mof.go.kr/coastScene/coastMediaService.do"},
    {"name": "정동진 해변", "region": "강원", "lat": 37.6886, "lng": 129.0336,
     "page_url": "https://coast.mof.go.kr/coastScene/coastMediaService.do"},
    {"name": "선유도 해수욕장", "region": "전북", "lat": 35.8253, "lng": 126.4181,
     "page_url": "https://coast.mof.go.kr/coastScene/coastMediaService.do"},
    {"name": "무창포 해수욕장", "region": "충남", "lat": 36.2756, "lng": 126.5397,
     "page_url": "https://coast.mof.go.kr/coastScene/coastMediaService.do"},
    {"name": "상주 해수욕장", "region": "경남", "lat": 34.7289, "lng": 128.0586,
     "page_url": "https://coast.mof.go.kr/coastScene/coastMediaService.do"},
]


def _scrape_coastal_list() -> List[Dict]:
    """해양수산부 연안 CCTV 목록 스크래핑"""
    global _coastal_cache

    now = time.time()
    if _coastal_cache["data"] and (now - _coastal_cache["timestamp"]) < _CACHE_TTL:
        return _coastal_cache["data"]

    cctvs = []
    try:
        # 연안침식 모니터링 페이지에서 CCTV 목록 시도
        url = "https://coast.mof.go.kr/coastScene/coastMediaService.do"
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        html = response.text

        # m3u8 스트리밍 URL 패턴 탐색
        m3u8_urls = re.findall(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
        # 비디오 소스 URL 탐색
        video_urls = re.findall(r'<source[^>]+src=["\']([^"\']+)["\']', html)
        # iframe 소스 탐색
        iframe_urls = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html)

        # CCTV 이름 + URL 매핑 시도
        # 목록 항목 패턴 (li/a/option 태그에서 이름 추출)
        name_patterns = re.findall(
            r'(?:data-[a-z]+=["\']([^"\']+)["\']|value=["\']([^"\']+)["\'])[^>]*>([^<]+)<',
            html
        )

        all_stream_urls = m3u8_urls + video_urls

        if all_stream_urls:
            for i, stream_url in enumerate(all_stream_urls):
                name = f"연안 CCTV #{i + 1}"
                if i < len(name_patterns):
                    name = name_patterns[i][2].strip() or name
                cctvs.append({
                    "name": name,
                    "region": "",
                    "stream_url": stream_url,
                    "stream_type": "hls" if ".m3u8" in stream_url else "video",
                    "page_url": url,
                    "capturable": True,
                    "source": "coastal_mof"
                })

        print(f"[CCTV] 연안 CCTV 스크래핑 완료: {len(cctvs)}개 스트림 발견")

    except Exception as e:
        print(f"[CCTV] 연안 CCTV 스크래핑 오류: {e}")

    # 스크래핑 결과가 부족하면 알려진 목록으로 보충
    if len(cctvs) < 5:
        known_names = {c["name"] for c in cctvs}
        for known in KNOWN_COASTAL_CCTVS:
            if known["name"] not in known_names:
                cctvs.append({
                    "name": known["name"],
                    "region": known["region"],
                    "lat": known["lat"],
                    "lng": known["lng"],
                    "stream_url": "",
                    "stream_type": "",
                    "page_url": known["page_url"],
                    "capturable": False,
                    "source": "coastal_mof"
                })

    _coastal_cache["data"] = cctvs
    _coastal_cache["timestamp"] = now
    return cctvs


def search_coastal_cctv(region: str = None, keyword: str = None) -> str:
    """해양수산부 연안 CCTV 검색"""
    try:
        cctvs = _scrape_coastal_list()

        # 필터링
        results = cctvs
        if region:
            region_lower = region.lower()
            results = [c for c in results if region_lower in c.get("region", "").lower()
                       or region_lower in c.get("name", "").lower()]

        if keyword:
            keyword_lower = keyword.lower()
            results = [c for c in results if keyword_lower in c.get("name", "").lower()
                       or keyword_lower in c.get("region", "").lower()]

        return success_response(
            source="coastal_mof",
            count=len(results),
            cctvs=results,
            note="해양수산부 연안침식 모니터링 CCTV. 스크래핑 기반으로 일부 URL이 변경될 수 있습니다."
        )
    except Exception as e:
        return error_response(str(e))


if __name__ == "__main__":
    print("해양수산부 연안 CCTV 모듈")
    print(f"알려진 CCTV: {len(KNOWN_COASTAL_CCTVS)}개")
    print("\n[테스트] 전체 목록 조회...")
    result = search_coastal_cctv()
    data = json.loads(result)
    print(f"총 {data.get('count', 0)}개 CCTV")
    if data.get("cctvs"):
        for c in data["cctvs"][:3]:
            print(f"  - {c['name']} ({c.get('region', '')})")
