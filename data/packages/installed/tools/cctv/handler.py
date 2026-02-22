"""
CCTV 및 실시간 웹캠 통합 도구 패키지

소스:
  - ITS 국가교통정보센터 (한국 교통 CCTV)
  - Windy Webcams (전세계 웹캠)

search_cctv는 통합 검색: ITS 이름검색 → 결과 없으면 Windy 웹캠 자동 폴백
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
_LANDMARKS = {
    # --- 한국 산 ---
    "한라산": (33.36, 126.53, "mountain"),
    "백록담": (33.36, 126.53, "mountain"),
    "설악산": (38.12, 128.47, "mountain"),
    "지리산": (35.34, 127.73, "mountain"),
    "북한산": (37.66, 126.98, "mountain"),
    "덕유산": (35.86, 127.75, "mountain"),
    "속리산": (36.54, 127.87, "mountain"),
    "내장산": (35.48, 126.89, "mountain"),
    "가야산": (35.80, 128.12, "mountain"),
    "오대산": (37.79, 128.57, "mountain"),
    "태백산": (37.09, 128.92, "mountain"),
    "월악산": (36.89, 128.10, "mountain"),
    "치악산": (37.37, 128.05, "mountain"),
    "계룡산": (36.34, 127.21, "mountain"),
    "무등산": (35.13, 126.99, "mountain"),
    # --- 한국 해변 ---
    "해운대": (35.16, 129.16, "beach"),
    "광안리": (35.15, 129.12, "beach"),
    "경포대": (37.80, 128.91, "beach"),
    "을왕리": (37.45, 126.37, "beach"),
    # --- 한국 도시 ---
    "서울": (37.57, 126.98, "city"),
    "부산": (35.18, 129.08, "city"),
    "인천": (37.46, 126.71, "city"),
    "제주": (33.50, 126.53, "city"),
    "대전": (36.35, 127.38, "city"),
    "대구": (35.87, 128.60, "city"),
    "광주": (35.16, 126.85, "city"),
    # --- 한국 공항 ---
    "인천공항": (37.46, 126.44, "airport"),
    "김포공항": (37.56, 126.80, "airport"),
    "제주공항": (33.51, 126.49, "airport"),
    # --- 해외 주요 도시 ---
    "manhattan": (40.78, -73.97, "city"),
    "맨하탄": (40.78, -73.97, "city"),
    "맨해튼": (40.78, -73.97, "city"),
    "new york": (40.71, -74.01, "city"),
    "뉴욕": (40.71, -74.01, "city"),
    "times square": (40.76, -73.99, "city"),
    "타임스퀘어": (40.76, -73.99, "city"),
    "tokyo": (35.68, 139.69, "city"),
    "도쿄": (35.68, 139.69, "city"),
    "paris": (48.86, 2.35, "city"),
    "파리": (48.86, 2.35, "city"),
    "london": (51.51, -0.13, "city"),
    "런던": (51.51, -0.13, "city"),
    "sydney": (-33.87, 151.21, "city"),
    "시드니": (-33.87, 151.21, "city"),
    "dubai": (25.20, 55.27, "city"),
    "두바이": (25.20, 55.27, "city"),
    "singapore": (1.35, 103.82, "city"),
    "싱가포르": (1.35, 103.82, "city"),
    "hong kong": (22.32, 114.17, "city"),
    "홍콩": (22.32, 114.17, "city"),
    "bangkok": (13.76, 100.50, "city"),
    "방콕": (13.76, 100.50, "city"),
    "beijing": (39.91, 116.40, "city"),
    "베이징": (39.91, 116.40, "city"),
    "shanghai": (31.23, 121.47, "city"),
    "상하이": (31.23, 121.47, "city"),
    "rome": (41.90, 12.50, "city"),
    "로마": (41.90, 12.50, "city"),
    "barcelona": (41.39, 2.17, "city"),
    "바르셀로나": (41.39, 2.17, "city"),
    "los angeles": (34.05, -118.24, "city"),
    "la": (34.05, -118.24, "city"),
    "san francisco": (37.77, -122.42, "city"),
    "chicago": (41.88, -87.63, "city"),
    "miami": (25.76, -80.19, "beach"),
    "마이애미": (25.76, -80.19, "beach"),
    "hawaii": (21.31, -157.86, "beach"),
    "하와이": (21.31, -157.86, "beach"),
    "waikiki": (21.28, -157.83, "beach"),
    "와이키키": (21.28, -157.83, "beach"),
    # --- 해외 명소 ---
    "후지산": (35.36, 138.73, "mountain"),
    "mount fuji": (35.36, 138.73, "mountain"),
    "에펠탑": (48.86, 2.29, "city"),
    "eiffel tower": (48.86, 2.29, "city"),
    "niagara": (43.08, -79.07, "landscape"),
    "나이아가라": (43.08, -79.07, "landscape"),
    "venice": (45.44, 12.32, "city"),
    "베니스": (45.44, 12.32, "city"),
    "santorini": (36.39, 25.46, "landscape"),
    "산토리니": (36.39, 25.46, "landscape"),
}


def _unified_search_cctv(query: str, lat: float = None, lon: float = None,
                         category: str = None, limit: int = 10, **kwargs) -> str:
    """
    통합 CCTV/웹캠 검색.

    1단계: ITS 교통 CCTV 이름 검색 (한국 고속도로/국도)
    2단계: 결과 없으면 Windy 웹캠 검색 (좌표 + 카테고리 기반)
    """
    common = load_module("common")
    all_results = []
    sources_tried = []

    print(f"[CCTV] 통합검색 시작: query='{query}', lat={lat}, lon={lon}, category={category}")

    # --- 1단계: ITS 교통 CCTV 이름 검색 ---
    its_key = bool(os.environ.get("ITS_API_KEY", ""))
    print(f"[CCTV] ITS_API_KEY 설정: {its_key}")
    if its_key:
        try:
            its = load_module("its_traffic")
            its_result = json.loads(its.get_cctv_by_name(keyword=query, limit=limit))
            sources_tried.append("its_traffic")
            if its_result.get("success") and its_result.get("count", 0) > 0:
                for cctv in its_result.get("cctvs", []):
                    cctv["source"] = "its_traffic"
                    all_results.append(cctv)
        except Exception as e:
            print(f"[CCTV] ITS 검색 실패: {e}")

    # --- 2단계: Windy 웹캠 검색 (ITS에서 못 찾은 경우) ---
    windy_key = bool(os.environ.get("WINDY_API_KEY", ""))
    print(f"[CCTV] ITS 결과: {len(all_results)}개, WINDY_API_KEY 설정: {windy_key}")
    if windy_key and len(all_results) == 0:
        try:
            windy = load_module("windy_webcam")
            sources_tried.append("windy_webcams")

            # 좌표 결정: 파라미터 > 지명 매핑 > 없으면 스킵
            search_lat, search_lon, auto_category = lat, lon, category

            if search_lat is None or search_lon is None:
                # 지명 매핑에서 좌표 찾기 (대소문자 무시)
                query_lower = query.strip().lower()
                for name, (plat, plon, pcat) in _LANDMARKS.items():
                    if name.lower() in query_lower:
                        search_lat, search_lon = plat, plon
                        if not auto_category:
                            auto_category = pcat
                        break

            print(f"[CCTV] Windy 좌표: lat={search_lat}, lon={search_lon}, category={auto_category}")
            if search_lat is not None and search_lon is not None:
                windy_result = json.loads(windy.search_webcam(
                    lat=search_lat, lon=search_lon,
                    radius_km=50,
                    category=auto_category,
                    limit=limit
                ))
                if windy_result.get("success") and windy_result.get("count", 0) > 0:
                    for webcam in windy_result.get("webcams", []):
                        webcam["source"] = "windy_webcams"
                        all_results.append(webcam)
            else:
                # 좌표 없으면 국가 필터로 시도
                # 한국어가 포함되어 있으면 KR, 아니면 국가 필터 없이 카테고리만
                import re
                has_korean = bool(re.search(r'[가-힣]', query))
                search_params = {"category": auto_category, "limit": limit}
                if has_korean:
                    search_params["country"] = "KR"
                print(f"[CCTV] Windy 좌표 없음, 국가 필터 검색: {search_params}")
                windy_result = json.loads(windy.search_webcam(**search_params))
                if windy_result.get("success") and windy_result.get("count", 0) > 0:
                    for webcam in windy_result.get("webcams", []):
                        webcam["source"] = "windy_webcams"
                        all_results.append(webcam)
        except Exception as e:
            print(f"[CCTV] Windy 검색 실패: {e}")

    if not all_results:
        return common.error_response(
            f"'{query}'에 해당하는 CCTV/웹캠을 찾을 수 없습니다.",
            sources_tried=sources_tried,
            hint="좌표(lat, lon)를 직접 지정하거나, [source:webcam]()으로 Windy 웹캠을 검색해보세요."
        )

    # --- 3단계: 첫 번째 결과의 이미지를 자동 캡처 ---
    auto_capture = None
    top_result = all_results[0]
    capture_url = top_result.get("image_url") or top_result.get("url", "")
    if capture_url:
        try:
            capture = load_module("capture")
            capture_result = json.loads(capture.capture_cctv(
                url=capture_url,
                source_type="auto"
            ))
            captured_path = capture_result.get("file_path", "")
            if capture_result.get("success") and captured_path:
                auto_capture = {
                    "file_path": captured_path,
                    "capture_method": capture_result.get("capture_method", ""),
                    "source_title": top_result.get("title") or top_result.get("name", ""),
                    "source_url": capture_url
                }
                print(f"[CCTV] 자동 캡처 성공: {auto_capture['file_path']}")
            else:
                print(f"[CCTV] 자동 캡처 실패: {capture_result.get('error', '?')}")
        except Exception as e:
            print(f"[CCTV] 자동 캡처 예외: {e}")

    return common.success_response(
        query=query,
        count=len(all_results),
        sources_tried=sources_tried,
        results=all_results[:limit],
        auto_capture=auto_capture,
        usage_hint="auto_capture.file_path의 이미지를 읽어서 사용자에게 현재 상황을 설명하세요." if auto_capture else "결과의 image_url 또는 url을 [source:cctv_capture](url)로 캡처하세요."
    )


# 도구 -> (모듈명, 함수명) 라우팅 테이블
_TOOL_ROUTING = {
    # ITS 교통 CCTV (좌표 범위 검색 — 개별 사용)
    "get_nearby_cctv": ("its_traffic", "get_nearby_cctv"),
    "get_cctv_by_name": ("its_traffic", "get_cctv_by_name"),
    "open_cctv": ("its_traffic", "open_cctv"),
    # Windy Webcams (개별 사용)
    "search_webcam": ("windy_webcam", "search_webcam"),
    "get_nearby_webcam": ("windy_webcam", "get_nearby_webcam"),
    # 화면 캡처
    "capture_cctv": ("capture", "capture_cctv"),
    # 통합 검색 — handler 내부 함수로 처리 (search_cctv는 아래 execute에서 분기)
}


def _list_cctv_sources() -> str:
    """사용 가능한 모든 CCTV 소스 상태 확인"""
    common = load_module("common")

    its_key = bool(os.environ.get("ITS_API_KEY", ""))
    windy_key = bool(os.environ.get("WINDY_API_KEY", ""))

    # ffmpeg 확인
    import shutil
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        for p in ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"]:
            if os.path.isfile(p):
                ffmpeg_path = p
                break

    sources = [
        {
            "id": "its_traffic",
            "name": "ITS 국가교통정보센터",
            "type": "api",
            "coverage": "한국 고속도로/국도",
            "status": "available" if its_key else "api_key_missing",
            "api_key_set": its_key,
            "tools": ["search_cctv", "get_nearby_cctv", "get_cctv_by_name", "open_cctv"]
        },
        {
            "id": "windy_webcams",
            "name": "Windy Webcams",
            "type": "api",
            "coverage": "전세계 (카테고리: beach, mountain, city, airport 등 18종)",
            "status": "available" if windy_key else "api_key_missing",
            "api_key_set": windy_key,
            "tools": ["search_webcam", "get_nearby_webcam"]
        }
    ]

    return common.success_response(
        sources=sources,
        capture_available=True,
        ffmpeg_installed=bool(ffmpeg_path),
        ffmpeg_path=ffmpeg_path or "",
        note="capture_cctv로 스트림 캡처 가능. 해안/국립공원/기타 CCTV는 가이드 파일(cctv_guide.md) 참조 → browser-action 패키지로 접속/캡처."
    )


def execute(tool_name: str, tool_input: dict, project_path: str = None) -> str:
    """
    도구 실행 진입점

    Args:
        tool_name: 실행할 도구 이름
        tool_input: 도구 입력 파라미터
        project_path: 프로젝트 경로

    Returns:
        JSON 형식의 결과 문자열
    """
    print(f"[CCTV] 도구 실행: {tool_name}")
    print(f"[CCTV] 입력: {tool_input}")

    try:
        # list_cctv_sources는 handler에서 직접 처리
        if tool_name == "list_cctv_sources":
            return _list_cctv_sources()

        # search_cctv는 통합 검색 함수로 처리
        if tool_name == "search_cctv":
            return _unified_search_cctv(**tool_input)

        # 라우팅 테이블에서 모듈/함수 찾기
        if tool_name not in _TOOL_ROUTING:
            return json.dumps({
                "success": False,
                "error": f"알 수 없는 도구: {tool_name}"
            }, ensure_ascii=False)

        module_name, func_name = _TOOL_ROUTING[tool_name]
        module = load_module(module_name)
        func = getattr(module, func_name)

        # capture_cctv는 project_path 전달
        if tool_name == "capture_cctv":
            tool_input["project_path"] = project_path

        return func(**tool_input)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
            "tool": tool_name
        }, ensure_ascii=False)


# 도구 목록
TOOLS = [
    "search_cctv", "get_nearby_cctv", "get_cctv_by_name", "open_cctv",
    "search_webcam", "get_nearby_webcam",
    "capture_cctv",
    "list_cctv_sources"
]


if __name__ == "__main__":
    print("CCTV 통합 도구 패키지 v2.0.0")
    print(f"도구 목록 ({len(TOOLS)}개): {TOOLS}")
    print()
    print("[소스 상태 확인]")
    result = _list_cctv_sources()
    data = json.loads(result)
    for source in data.get("sources", []):
        status_icon = "O" if source["status"] == "available" else "X"
        print(f"  [{status_icon}] {source['name']} ({source['coverage']})")
    print(f"\n  ffmpeg: {'설치됨' if data.get('ffmpeg_installed') else '미설치'}")
