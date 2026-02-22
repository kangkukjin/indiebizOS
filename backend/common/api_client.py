"""
api_client.py - 범용 HTTP 클라이언트

모든 도구 패키지의 HTTP API 호출을 통합합니다.
인증, 타임아웃, 에러 처리, 응답 표준화를 자동으로 처리합니다.

사용법:
    from common.api_client import api_call, api_call_raw

    # 서비스 기반 호출 (인증 자동 처리)
    data = api_call("kakao", "/v2/local/search/keyword.json", params={"query": "강남 맛집"})

    # 직접 URL 호출
    data = api_call_raw("https://api.example.com/data", headers={...}, params={...})
"""

import requests
from typing import Optional, Dict, Any, Union
from .auth_manager import get_api_headers, get_auth_query_params, check_api_key


# 서비스별 기본 URL 레지스트리
_BASE_URLS: Dict[str, str] = {
    "kakao": "https://dapi.kakao.com",
    "kakao-navi": "https://apis-navi.kakaomobility.com",
    "naver": "https://openapi.naver.com",
    "ninjas": "https://api.api-ninjas.com/v1",
    "law": "http://www.law.go.kr/DRF",
    "amadeus": "https://test.api.amadeus.com",
    "kosis": "https://kosis.kr/openapi",
    "fmp": "https://financialmodelingprep.com/api",
    "finnhub": "https://finnhub.io/api/v1",
    "dart": "https://opendart.fss.or.kr/api",
    "data_go_kr": "https://apis.data.go.kr",
    "kopis": "http://www.kopis.or.kr/openApi/restful",
    "data4library": "http://data4library.kr/api",
    "radio_browser": "https://de1.api.radio-browser.info/json",
    "sec_edgar": "https://data.sec.gov",
    "coingecko": "https://api.coingecko.com/api/v3",
}

# 기본 설정
DEFAULT_TIMEOUT = 10
DEFAULT_MAX_RETRIES = 0


def api_call(
    service: str,
    endpoint: str,
    *,
    method: str = "GET",
    params: Dict[str, Any] = None,
    data: Any = None,
    json_body: Any = None,
    extra_headers: Dict[str, str] = None,
    timeout: int = None,
    base_url: str = None,
    raw_response: bool = False,
) -> Union[dict, list, str]:
    """
    서비스 기반 API 호출 (인증 자동 처리)

    Args:
        service: 서비스 이름 (예: "kakao", "naver", "law")
        endpoint: 엔드포인트 경로 (예: "/v2/local/search/keyword.json")
        method: HTTP 메서드 (기본: "GET")
        params: 쿼리 파라미터
        data: form 데이터
        json_body: JSON 바디
        extra_headers: 추가 헤더
        timeout: 타임아웃 (초, 기본: 10)
        base_url: 기본 URL 오버라이드
        raw_response: True면 response.text 반환

    Returns:
        파싱된 JSON 응답 (dict/list) 또는 에러 dict {"error": "..."}

    Raises:
        없음. 모든 예외는 {"error": "..."} 형태로 반환됩니다.
    """
    # API 키 확인
    key_ok, key_error = check_api_key(service)
    if not key_ok:
        return {"error": key_error}

    # URL 구성
    url_base = base_url or _BASE_URLS.get(service, "")
    if not url_base:
        return {"error": f"알 수 없는 서비스: {service}. base_url을 직접 지정하세요."}
    url = f"{url_base}{endpoint}" if endpoint else url_base

    # 인증 헤더 구성
    headers = get_api_headers(service) or {}
    if extra_headers:
        headers.update(extra_headers)

    # 인증 쿼리 파라미터 (query_param 방식)
    merged_params = dict(params or {})
    auth_params = get_auth_query_params(service)
    if auth_params:
        merged_params.update(auth_params)

    # HTTP 호출
    return _do_request(
        method=method,
        url=url,
        headers=headers,
        params=merged_params,
        data=data,
        json_body=json_body,
        timeout=timeout or DEFAULT_TIMEOUT,
        raw_response=raw_response,
        service=service,
    )


def api_call_raw(
    url: str,
    *,
    method: str = "GET",
    headers: Dict[str, str] = None,
    params: Dict[str, Any] = None,
    data: Any = None,
    json_body: Any = None,
    timeout: int = None,
    raw_response: bool = False,
) -> Union[dict, list, str]:
    """
    직접 URL로 HTTP 호출 (인증 직접 처리)

    Args:
        url: 전체 URL
        method: HTTP 메서드
        headers: 요청 헤더
        params: 쿼리 파라미터
        data: form 데이터
        json_body: JSON 바디
        timeout: 타임아웃 (초)
        raw_response: True면 response.text 반환

    Returns:
        파싱된 JSON 응답 또는 에러 dict
    """
    return _do_request(
        method=method,
        url=url,
        headers=headers or {},
        params=params or {},
        data=data,
        json_body=json_body,
        timeout=timeout or DEFAULT_TIMEOUT,
        raw_response=raw_response,
    )


def _do_request(
    method: str,
    url: str,
    headers: dict,
    params: dict,
    data: Any,
    json_body: Any,
    timeout: int,
    raw_response: bool,
    service: str = None,
) -> Union[dict, list, str]:
    """내부 HTTP 요청 실행"""
    try:
        response = requests.request(
            method=method.upper(),
            url=url,
            headers=headers,
            params=params if params else None,
            data=data,
            json=json_body,
            timeout=timeout,
        )

        # HTTP 에러 상태 코드 처리
        if response.status_code == 401:
            svc = f" ({service})" if service else ""
            return {"error": f"API 인증 실패{svc}. API 키를 확인하세요. (HTTP 401)"}
        elif response.status_code == 400:
            return {"error": f"잘못된 요청: {response.text[:500]} (HTTP 400)"}
        elif response.status_code == 403:
            return {"error": f"접근 거부 (HTTP 403)"}
        elif response.status_code == 404:
            return {"error": f"리소스를 찾을 수 없습니다 (HTTP 404)"}
        elif response.status_code == 429:
            return {"error": f"API 요청 한도 초과. 잠시 후 다시 시도하세요. (HTTP 429)"}
        elif response.status_code >= 500:
            return {"error": f"서버 오류 (HTTP {response.status_code})"}
        elif response.status_code != 200:
            return {"error": f"API 오류: HTTP {response.status_code} - {response.text[:300]}"}

        # raw 텍스트 반환
        if raw_response:
            return response.text

        # JSON 파싱 시도
        try:
            return response.json()
        except ValueError:
            return response.text

    except requests.exceptions.Timeout:
        svc = f" ({service})" if service else ""
        return {"error": f"API 요청 시간 초과{svc} ({timeout}초)"}
    except requests.exceptions.ConnectionError:
        return {"error": "네트워크 연결 실패. 인터넷 연결을 확인하세요."}
    except Exception as e:
        return {"error": f"API 호출 실패: {str(e)}"}


def register_base_url(service: str, base_url: str):
    """런타임에 서비스 기본 URL 등록"""
    _BASE_URLS[service] = base_url


def get_base_url(service: str) -> Optional[str]:
    """서비스 기본 URL 조회"""
    return _BASE_URLS.get(service)
