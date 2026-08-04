"""
common - IndieBiz OS 공통 유틸리티 모듈

Phase 0 (IBL 기반 정리)의 핵심 모듈.
모든 도구 패키지가 공유하는 공통 기능을 제공합니다.

모듈:
    - api_client: 범용 HTTP 클라이언트 (인증, 타임아웃, 에러 처리 통합)
    - auth_manager: API 키 중앙 관리
    - html_utils: HTML 파싱 유틸리티
    - response_formatter: 응답 포맷 표준화
    - http_fetch: 크롬 TLS 위장 GET/세션 단일 소스 (curl_cffi, 폰=urllib 폴백)
    - geocode: 키리스 지오코딩(Nominatim) 단일 소스
    - pkg_utils: 패키지 형제 모듈 로드(load_sibling) 정본

(http_fetch/geocode/pkg_utils 는 지연 의존 — 여기서 eager import 하지 않는다)
"""

from .api_client import api_call, api_call_raw
from .auth_manager import get_api_key, get_api_headers
from .html_utils import clean_html, extract_text
from .response_formatter import success_response, error_response, format_json
