"""
CCTV 및 실시간 웹캠 통합 도구 패키지

소스:
  - ITS 국가교통정보센터 (한국 교통 CCTV)
  - Windy Webcams (전세계 웹캠)
  - 해양수산부 연안 CCTV (한국 해안/해변)
  - 국립공원 CCTV (한국 국립공원)
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

# 도구 -> (모듈명, 함수명) 라우팅 테이블
_TOOL_ROUTING = {
    # ITS 교통 CCTV
    "search_cctv": ("its_traffic", "search_cctv"),
    "get_nearby_cctv": ("its_traffic", "get_nearby_cctv"),
    "get_cctv_by_name": ("its_traffic", "get_cctv_by_name"),
    "open_cctv": ("its_traffic", "open_cctv"),
    # Windy Webcams
    "search_webcam": ("windy_webcam", "search_webcam"),
    "get_nearby_webcam": ("windy_webcam", "get_nearby_webcam"),
    # 해양수산부 연안 CCTV
    "search_coastal_cctv": ("coastal_cctv", "search_coastal_cctv"),
    # 국립공원 CCTV
    "search_park_cctv": ("park_cctv", "search_park_cctv"),
    # 화면 캡처
    "capture_cctv": ("capture", "capture_cctv"),
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
        },
        {
            "id": "coastal_mof",
            "name": "해양수산부 연안 CCTV",
            "type": "scraping",
            "coverage": "한국 해안/해변 약 20개소",
            "status": "available",
            "api_key_set": None,
            "tools": ["search_coastal_cctv"]
        },
        {
            "id": "national_parks",
            "name": "국립공원 CCTV",
            "type": "scraping",
            "coverage": "한국 국립공원 17곳",
            "status": "available",
            "api_key_set": None,
            "tools": ["search_park_cctv"]
        }
    ]

    return common.success_response(
        sources=sources,
        capture_available=True,
        ffmpeg_installed=bool(ffmpeg_path),
        ffmpeg_path=ffmpeg_path or "",
        note="capture_cctv 도구로 모든 소스의 CCTV 화면을 캡처하여 AI 분석에 활용할 수 있습니다."
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
    "search_coastal_cctv",
    "search_park_cctv",
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
