"""
CCTV 및 실시간 웹캠 통합 도구 패키지

소스 (우선순위):
  1. 카카오맵 — 전국 6,892대, API 키 불필요, 모두 HLS 스트리밍
  2. TOPIS — 서울 502대 (카카오맵에 없는 서울 CCTV 보완)
  3. UTIC — 전국 시내 도로 16,000대 (카카오맵에 없는 CCTV 보완)
  4. ITS — 고속도로/국도 (카카오맵 mltm과 동일 소스)
  5. Windy Webcams — 전세계 웹캠 (해외 폴백)
"""

import json
import os
import sys
import importlib.util
from pathlib import Path

current_dir = Path(__file__).parent

# 모듈 로딩 캐시
_loaded_modules = {}


def load_module(module_name):
    """같은 디렉토리의 모듈을 동적으로 로드"""
    if module_name in _loaded_modules:
        return _loaded_modules[module_name]

    module_path = current_dir / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)

    # common 모듈을 sys.modules에 등록 (다른 모듈이 import할 수 있도록)
    if module_name == "common":
        sys.modules["common"] = module

    spec.loader.exec_module(module)
    _loaded_modules[module_name] = module
    return module


# common 모듈 먼저 로드 (다른 모듈의 의존성)
load_module("common")

# 주요 지명 → 좌표 매핑 (Windy 웹캠 폴백용)
def _is_hls_playable(url: str) -> bool:
    """URL이 hls.js로 재생 가능한 HLS 스트림인지 판단"""
    if not url:
        return False
    u = url.lower()
    # HLS 직접 스트림
    if '.m3u8' in u:
        return True
    # 카카오맵 경유 HLS (ktict.co.kr)
    if 'ktict.co.kr' in u:
        return True
    # TOPIS 서울 HLS
    if 'eseoul.go.kr' in u:
        return True
    # RTMP/HLS 스트리밍 서버
    if ':1935/' in u:
        return True
    if 'streamlock.net' in u:
        return True
    # UTIC JSP 페이지 → 재생 불가
    if 'utic.go.kr' in u and '.jsp' in u:
        return False
    return False


def _is_korea(lat: float, lng: float) -> bool:
    """좌표가 대한민국 범위인지 판단"""
    return 33.0 <= lat <= 39.0 and 124.0 <= lng <= 132.0


# 좌표 → 지역명 매핑 (바운딩박스 기반)
_KOREA_REGIONS = [
    ("서울", 37.42, 37.72, 126.76, 127.19),
    ("인천", 37.35, 37.60, 126.35, 126.80),
    ("경기", 36.90, 38.30, 126.35, 127.90),
    ("부산", 34.87, 35.40, 128.75, 129.35),
    ("대구", 35.70, 36.05, 128.35, 128.85),
    ("대전", 36.20, 36.50, 127.25, 127.55),
    ("광주", 35.05, 35.25, 126.70, 127.00),
    ("울산", 35.35, 35.75, 129.00, 129.50),
    ("세종", 36.42, 36.70, 126.85, 127.10),
    ("제주", 33.10, 33.60, 126.10, 127.00),
    ("전주", 35.70, 35.90, 127.05, 127.25),
    ("청주", 36.55, 36.75, 127.35, 127.55),
    ("천안", 36.70, 36.90, 127.05, 127.25),
    ("수원", 37.20, 37.35, 126.90, 127.10),
    ("창원", 35.15, 35.35, 128.55, 128.80),
    ("전남", 34.10, 35.10, 126.00, 127.90),
    ("전북", 35.30, 36.10, 126.30, 127.90),
    ("경남", 34.70, 35.90, 127.50, 129.40),
    ("경북", 35.60, 37.10, 128.30, 130.00),
    ("충남", 36.00, 37.00, 126.00, 127.40),
    ("충북", 36.40, 37.20, 127.30, 128.60),
    ("강원", 37.00, 38.60, 127.00, 129.40),
]


# 좌표→지역 매핑에서 사용할 검색어 (카카오 캐시의 region 필드는 "서울특별시" 형태)
_REGION_SEARCH_TERMS = {
    "서울": "서울",
    "인천": "인천",
    "경기": "경기",
    "부산": "부산",
    "대구": "대구",
    "대전": "대전",
    "광주": "광주",
    "울산": "울산",
    "세종": "세종",
    "제주": "제주",
    "전주": "전라북",      # 전라북도, 전북특별자치도 모두 매칭
    "청주": "충청북",      # 충청북도
    "천안": "충청남",      # 충청남도
    "수원": "경기",
    "창원": "경상남",      # 경상남도
    "전남": "전라남",
    "전북": "전라북",
    "경남": "경상남",
    "경북": "경상북",
    "충남": "충청남",
    "충북": "충청북",
    "강원": "강원",
}


def _coords_to_region(lat: float, lng: float) -> str:
    """좌표에서 가장 가까운 한국 지역명을 추정하고, 카카오 검색용 키워드를 반환한다."""
    region_name = None
    for name, lat_min, lat_max, lng_min, lng_max in _KOREA_REGIONS:
        if lat_min <= lat <= lat_max and lng_min <= lng <= lng_max:
            region_name = name
            break

    if not region_name:
        # 바운딩박스에 정확히 안 맞으면 중심점 거리로 가장 가까운 지역 반환
        best, best_dist = "서울", 999
        for name, lat_min, lat_max, lng_min, lng_max in _KOREA_REGIONS:
            clat = (lat_min + lat_max) / 2
            clng = (lng_min + lng_max) / 2
            d = ((lat - clat) ** 2 + (lng - clng) ** 2) ** 0.5
            if d < best_dist:
                best, best_dist = name, d
        region_name = best

    return _REGION_SEARCH_TERMS.get(region_name, region_name)


_LANDMARKS = {
    "한라산": (33.36, 126.53, "mountain"),
    "백록담": (33.36, 126.53, "mountain"),
    "설악산": (38.12, 128.47, "mountain"),
    "지리산": (35.34, 127.73, "mountain"),
    "북한산": (37.66, 126.98, "mountain"),
    "해운대": (35.16, 129.16, "beach"),
    "광안리": (35.15, 129.12, "beach"),
    "서울": (37.57, 126.98, "city"),
    "부산": (35.18, 129.08, "city"),
    "인천": (37.46, 126.71, "city"),
    "제주": (33.50, 126.53, "city"),
    "대전": (36.35, 127.38, "city"),
    "대구": (35.87, 128.60, "city"),
    "광주": (35.16, 126.85, "city"),
    "뉴욕": (40.71, -74.01, "city"),
    "도쿄": (35.68, 139.69, "city"),
    "파리": (48.86, 2.35, "city"),
    "런던": (51.51, -0.13, "city"),
}


def cctv_search(query: str, lat: float = None, lon: float = None,
                category: str = None, limit: int = 10, **kwargs) -> str:
    """통합 CCTV/웹캠 검색"""
    common = load_module("common")
    all_results = []

    # 1. 카카오맵 (전국 6,892대 — 최우선, API 키 불필요, 모두 HLS)
    try:
        kakao = load_module("kakao_traffic")
        kakao_res = json.loads(kakao.get_cctv_by_name(query, limit=limit))
        if kakao_res.get("success") and kakao_res.get("cctvs"):
            all_results.extend(kakao_res["cctvs"])
        # 결과 없으면 쿼리를 단어별로 분리해서 재시도 (예: "전주 풍남문" → "전주")
        if not all_results and " " in query:
            for word in query.split():
                if len(word) >= 2:
                    retry = json.loads(kakao.get_cctv_by_name(word, limit=limit))
                    if retry.get("success") and retry.get("cctvs"):
                        all_results.extend(retry["cctvs"])
                        break
    except Exception as e:
        print(f"[CCTV] 카카오맵 검색 실패: {e}")

    # 2. TOPIS (서울 보완 — 카카오맵에 없는 서울 CCTV)
    if len(all_results) < limit:
        try:
            topis = load_module("topis_traffic")
            topis_res = json.loads(topis.get_cctv_by_name(query, limit=limit))
            if topis_res.get("success") and topis_res.get("cctvs"):
                # 카카오 결과와 중복 제거 (이름 기반)
                existing_names = {r.get("name", "") for r in all_results}
                for c in topis_res["cctvs"]:
                    if c.get("name", "") not in existing_names:
                        all_results.append(c)
        except Exception as e:
            print(f"[CCTV] TOPIS 검색 실패: {e}")

    # 3. UTIC (전국 보완 — HLS 재생 가능한 CCTV만)
    if len(all_results) < limit:
        try:
            utic = load_module("utic_traffic")
            utic_res = json.loads(utic.get_cctv_by_name(query, limit=limit))
            if utic_res.get("success") and utic_res.get("cctvs"):
                existing_names = {r.get("name", "") for r in all_results}
                for c in utic_res["cctvs"]:
                    if c.get("name", "") not in existing_names and _is_hls_playable(c.get("url", "")):
                        all_results.append(c)
        except Exception as e:
            print(f"[CCTV] UTIC 검색 실패: {e}")

    # 4. ITS (고속도로/국도 — HLS 재생 가능한 CCTV만)
    if len(all_results) < limit:
        try:
            its = load_module("its_traffic")
            its_res = json.loads(its.get_cctv_by_name(query, limit=limit))
            if its_res.get("success") and its_res.get("cctvs"):
                existing_names = {r.get("name", "") for r in all_results}
                for c in its_res["cctvs"]:
                    if c.get("name", "") not in existing_names and _is_hls_playable(c.get("url", "")):
                        all_results.append(c)
        except Exception as e:
            print(f"[CCTV] ITS 검색 실패: {e}")

    # 5. Windy (전세계 웹캠 — 폴백)
    if not all_results:
        windy = load_module("windy_webcam")
        resolved_lat, resolved_lon = lat, lon
        if resolved_lat is None or resolved_lon is None:
            for name, (plat, plon, pcat) in _LANDMARKS.items():
                if name in query:
                    resolved_lat, resolved_lon = plat, plon
                    break

        if resolved_lat is not None:
            windy_res = json.loads(windy.get_nearby_webcams(resolved_lat, resolved_lon, limit=limit))
            if windy_res.get("success") and windy_res.get("webcams"):
                all_results.extend(windy_res["webcams"])

    if not all_results:
        return common.success_response(count=0, message=f"'{query}'에 대한 CCTV를 찾을 수 없습니다.", cctvs=[])

    results = all_results[:limit]

    # 스트림 태그 생성 — HLS 재생 가능한 URL만 포함
    stream_tags = []
    for cctv in results:
        url = cctv.get("url", "")
        if url and _is_hls_playable(url):
            tag_data = {"url": url, "name": cctv.get("name", "")}
            if cctv.get("source"):
                tag_data["source"] = cctv["source"]
            if cctv.get("lat") and cctv.get("lng"):
                tag_data["lat"] = cctv["lat"]
                tag_data["lng"] = cctv["lng"]
            stream_tags.append(f"[STREAM:{json.dumps(tag_data, ensure_ascii=False)}]")

    return common.success_response(
        count=len(results),
        cctvs=results,
        stream_tags=stream_tags,
        hint="검색 결과의 stream_tags를 응답에 그대로 포함하면 실시간 스트리밍이 표시됩니다. 캡처할 필요 없이 stream_tags만 출력하세요."
    )


def nearby(lat: float, lng: float, radius: float = 0.1, count: int = 5) -> str:
    """주변 CCTV 검색 — 한국이면 카카오 최우선, 해외는 UTIC/ITS/Windy"""
    common = load_module("common")
    all_results = []

    if _is_korea(lat, lng):
        # ── 한국: 카카오맵 최우선 ──
        region = _coords_to_region(lat, lng)
        print(f"[CCTV nearby] 한국 좌표 → 지역: {region}")

        # 1. 카카오맵 — 지역명으로 검색
        try:
            kakao = load_module("kakao_traffic")
            kakao_res = json.loads(kakao.get_cctv_by_region(region, limit=count * 3))
            if kakao_res.get("success") and kakao_res.get("cctvs"):
                all_results.extend(kakao_res["cctvs"])
                print(f"[CCTV nearby] 카카오 {region}: {len(kakao_res['cctvs'])}대")
        except Exception as e:
            print(f"[CCTV nearby] 카카오 실패: {e}")

        # 2. TOPIS (서울 보완)
        if len(all_results) < count:
            try:
                topis = load_module("topis_traffic")
                topis_res = json.loads(topis.get_nearby_cctv(lat, lng, radius=radius, count=count))
                if topis_res.get("success") and topis_res.get("cctvs"):
                    existing = {r.get("name", "") for r in all_results}
                    for c in topis_res["cctvs"]:
                        if c.get("name", "") not in existing and _is_hls_playable(c.get("url", "")):
                            all_results.append(c)
            except Exception as e:
                print(f"[CCTV nearby] TOPIS 실패: {e}")

        # 3. UTIC/ITS — HLS 가능한 것만 보완
        if len(all_results) < count:
            for mod_name in ["utic_traffic", "its_traffic"]:
                try:
                    mod = load_module(mod_name)
                    res = json.loads(mod.get_nearby_cctv(lat, lng, radius=radius, count=count))
                    if res.get("success"):
                        existing = {r.get("name", "") for r in all_results}
                        for c in res["cctvs"]:
                            if c.get("name", "") not in existing and _is_hls_playable(c.get("url", "")):
                                all_results.append(c)
                except Exception as e:
                    print(f"[CCTV nearby] {mod_name} 실패: {e}")

    else:
        # ── 해외: UTIC/ITS/Windy ──
        for mod_name in ["utic_traffic", "its_traffic"]:
            try:
                mod = load_module(mod_name)
                res = json.loads(mod.get_nearby_cctv(lat, lng, radius=radius, count=count))
                if res.get("success"):
                    all_results.extend(res["cctvs"])
            except Exception:
                pass

        if not all_results:
            try:
                windy = load_module("windy_webcam")
                windy_res = json.loads(windy.get_nearby_webcams(lat, lng, limit=count))
                if windy_res.get("success"):
                    all_results.extend(windy_res.get("webcams", []))
            except Exception:
                pass

    all_results.sort(key=lambda x: x.get("distance_km", 999))
    results = all_results[:count]

    # 스트림 태그 생성 — HLS 재생 가능한 URL만 포함
    stream_tags = []
    for cctv in results:
        url = cctv.get("url", "")
        if url and _is_hls_playable(url):
            tag_data = {"url": url, "name": cctv.get("name", "")}
            if cctv.get("source"):
                tag_data["source"] = cctv["source"]
            if cctv.get("lat") and cctv.get("lng"):
                tag_data["lat"] = cctv["lat"]
                tag_data["lng"] = cctv["lng"]
            stream_tags.append(f"[STREAM:{json.dumps(tag_data, ensure_ascii=False)}]")

    return common.success_response(
        count=len(results),
        cctvs=results,
        stream_tags=stream_tags,
        hint="검색 결과의 stream_tags를 응답에 그대로 포함하면 실시간 스트리밍이 표시됩니다."
    )


def cctv_open(url: str = None, name: str = None, lat: float = None, lng: float = None) -> str:
    """CCTV 열기"""
    if url:
        import webbrowser
        webbrowser.open(url)
        return json.dumps({"success": True, "message": "CCTV 영상을 열었습니다.", "url": url})
    
    if name:
        res = json.loads(cctv_search(name, limit=1))
        if res.get("cctvs"):
            return cctv_open(url=res["cctvs"][0]["url"])
            
    return json.dumps({"success": False, "message": "CCTV를 찾을 수 없습니다."})


def cctv_capture(url: str, save_path: str = None, name: str = None, **kwargs) -> str:
    """CCTV 화면 캡처.

    URL이 UTIC JSP이면 m3u8 URL을 추출하여 ffmpeg으로 캡처한다.
    이름만 주어진 경우 검색 후 캡처한다.
    """
    # 이름으로 검색
    if not url and name:
        res = json.loads(cctv_search(name, limit=1))
        if res.get("cctvs"):
            url = res["cctvs"][0].get("url", "")
        if not url:
            return json.dumps({"success": False, "error": f"'{name}' CCTV를 찾을 수 없습니다."}, ensure_ascii=False)

    # UTIC JSP URL이면 → 이미 m3u8 URL로 변환되어 있을 수 있지만, 혹시 JSP URL이면 추출 시도
    if url and "utic.go.kr" in url and "openDataCctvStream.jsp" in url:
        import re
        import urllib.request as ureq
        try:
            req = ureq.Request(url, headers={
                "Referer": "http://www.utic.go.kr/guide/cctvOpenData.do",
                "User-Agent": "Mozilla/5.0",
            })
            with ureq.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            m3u8_urls = re.findall(r"(https?://[^'\"<>\s]+\.m3u8[^'\"<>\s]*)", html)
            m3u8_urls = [u for u in m3u8_urls if "211.236.72.94" not in u]
            if m3u8_urls:
                url = m3u8_urls[0]
                print(f"[CCTV 캡처] JSP → m3u8 변환: {url[:80]}")
        except Exception as e:
            print(f"[CCTV 캡처] JSP m3u8 추출 실패: {e}")

    capture = load_module("capture")
    return capture.capture_cctv(url)


def cctv_sources() -> str:
    """지원하는 CCTV 소스 목록 + 데이터 현황"""
    # 카카오맵 통계
    kakao_total = 0
    try:
        kakao = load_module("kakao_traffic")
        kakao_stats = json.loads(kakao.get_data_stats())
        kakao_total = kakao_stats.get("total_cctv", 0)
    except Exception:
        pass

    utic = load_module("utic_traffic")
    utic_stats = json.loads(utic.get_data_stats())

    return json.dumps({
        "success": True,
        "sources": [
            {
                "id": "kakao",
                "name": "카카오맵",
                "description": "전국 교통 CCTV (HLS 스트리밍, 최우선)",
                "total_cctv": kakao_total,
                "api_key_required": False,
            },
            {
                "id": "utic",
                "name": "도시교통정보센터",
                "description": "전국 시내 도로 CCTV (보완용)",
                "total_cctv": utic_stats.get("total_cctv", 0),
                "api_key_configured": utic_stats.get("api_key_configured", False),
            },
            {"id": "its", "name": "국가교통정보센터", "description": "전국 고속도로/국도 CCTV"},
            {"id": "windy", "name": "Windy Webcams", "description": "전세계 실시간 웹캠"}
        ]
    }, ensure_ascii=False)


def cctv_refresh() -> str:
    """UTIC 실시간 API에서 최신 CCTV 목록을 가져와 로컬 캐시 갱신"""
    utic = load_module("utic_traffic")
    return utic.refresh_cache()


def cctv_stats() -> str:
    """CCTV 데이터 소스 상태 및 통계"""
    utic = load_module("utic_traffic")
    return utic.get_data_stats()


# ── 도구 디스패처 ──────────────────────────────────────

# tool_name → 실제 함수 매핑
_TOOL_MAP = {
    "search_cctv": cctv_search,
    "cctv_search": cctv_search,
    "get_nearby_cctv": nearby,
    "open_cctv": cctv_open,
    "capture_cctv": cctv_capture,
    "list_cctv_sources": cctv_sources,
    "cctv_refresh": cctv_refresh,
    "cctv_stats": cctv_stats,
    "search_webcam": lambda **kw: load_module("windy_webcam").search_webcam(**kw),
    "get_nearby_webcam": lambda **kw: load_module("windy_webcam").get_nearby_webcam(**kw),
}


def execute(tool_name: str, args: dict, project_path: str = ".") -> str:
    """CCTV 도구 실행 통합 핸들러"""
    func = _TOOL_MAP.get(tool_name)
    if func is None:
        return json.dumps({"error": f"미구현 도구: {tool_name}"}, ensure_ascii=False)

    try:
        return func(**args)
    except TypeError as e:
        # 불필요한 파라미터 제거 후 재시도
        import inspect
        sig = inspect.signature(func)
        valid_args = {k: v for k, v in args.items() if k in sig.parameters}
        return func(**valid_args)
    except Exception as e:
        return json.dumps({"error": f"{tool_name} 실행 실패: {str(e)}"}, ensure_ascii=False)
