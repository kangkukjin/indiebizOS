"""
auth_manager.py - API 키 중앙 관리

모든 도구 패키지의 API 키를 통합 관리합니다.
키 조회 우선순위: 환경변수 → 패키지 config.json → 글로벌 config

사용법:
    from common.auth_manager import get_api_key, get_api_headers

    # 단일 키
    key = get_api_key("LAW_API_KEY")

    # 패키지 config.json에서 키 조회 (fallback)
    key = get_api_key("LAW_API_KEY", package_dir="/path/to/legal")

    # API 인증 헤더 생성
    headers = get_api_headers("kakao")  # {"Authorization": "KakaoAK xxx"}
    headers = get_api_headers("naver")  # {"X-Naver-Client-Id": "xxx", ...}
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict


# 알려진 API 서비스별 인증 설정
# 새 API를 추가할 때 여기에 등록하면 get_api_headers()로 자동 생성
_AUTH_REGISTRY: Dict[str, dict] = {
    "kakao": {
        "type": "header",
        "header_name": "Authorization",
        "prefix": "KakaoAK ",
        "env_var": "KAKAO_REST_API_KEY",
    },
    "naver": {
        "type": "header_pair",
        "headers": {
            "X-Naver-Client-Id": "NAVER_CLIENT_ID",
            "X-Naver-Client-Secret": "NAVER_CLIENT_SECRET",
        },
    },
    "ninjas": {
        "type": "header",
        "header_name": "X-Api-Key",
        "prefix": "",
        "env_var": "NINJAS_API_KEY",
    },
    "law": {
        "type": "query_param",
        "key_name": "OC",
        "env_var": "LAW_API_KEY",
    },
    "amadeus": {
        "type": "oauth2",
        "env_vars": {
            "client_id": "AMADEUS_API_KEY",
            "client_secret": "AMADEUS_API_SECRET",
        },
    },
    "dart": {
        "type": "query_param",
        "key_name": "crtfc_key",
        "env_var": "DART_API_KEY",
    },
    "kosis": {
        "type": "query_param",
        "key_name": "apiKey",
        "env_var": "KOSIS_API_KEY",
    },
    "fmp": {
        "type": "query_param",
        "key_name": "apikey",
        "env_var": "FMP_API_KEY",
    },
    "finnhub": {
        "type": "query_param",
        "key_name": "token",
        "env_var": "FINNHUB_API_KEY",
    },
    "data_go_kr": {
        "type": "query_param",
        "key_name": "serviceKey",
        "env_var": "DATA_GO_KR_API_KEY",
    },
    "molit": {
        "type": "query_param",
        "key_name": "serviceKey",
        "env_var": "MOLIT_API_KEY",
    },
    "kopis": {
        "type": "query_param",
        "key_name": "service",
        "env_var": "KOPIS_API_KEY",
    },
    "data4library": {
        "type": "query_param",
        "key_name": "authKey",
        "env_var": "DATA4LIBRARY_API_KEY",
    },
}


def get_api_key(env_var: str, package_dir: str = None, config_key: str = "api_key") -> Optional[str]:
    """
    API 키 조회 (환경변수 → 패키지 config.json)

    Args:
        env_var: 환경변수 이름 (예: "LAW_API_KEY")
        package_dir: 패키지 디렉토리 경로 (config.json fallback용)
        config_key: config.json 내 키 이름 (기본: "api_key")

    Returns:
        API 키 문자열 또는 None
    """
    # 1. 환경변수 확인
    key = os.environ.get(env_var)
    if key:
        return key

    # 2. 패키지 config.json 확인
    if package_dir:
        config_path = Path(package_dir) / "config.json"
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    key = config.get(config_key) or config.get(env_var)
                    if key:
                        return key
            except (json.JSONDecodeError, IOError):
                pass

    return None


def get_api_headers(service_name: str) -> Optional[Dict[str, str]]:
    """
    서비스별 API 인증 헤더 생성

    Args:
        service_name: 서비스 이름 (예: "kakao", "naver", "ninjas")

    Returns:
        인증 헤더 딕셔너리 또는 None (키가 없을 때)
    """
    auth_config = _AUTH_REGISTRY.get(service_name)
    if not auth_config:
        return None

    auth_type = auth_config["type"]

    if auth_type == "header":
        key = os.environ.get(auth_config["env_var"], "")
        if not key:
            return None
        prefix = auth_config.get("prefix", "")
        return {auth_config["header_name"]: f"{prefix}{key}"}

    elif auth_type == "header_pair":
        headers = {}
        for header_name, env_var in auth_config["headers"].items():
            val = os.environ.get(env_var, "")
            if not val:
                return None
            headers[header_name] = val
        return headers

    return None


def get_auth_query_params(service_name: str) -> Optional[Dict[str, str]]:
    """
    서비스별 API 인증 쿼리 파라미터 생성

    Args:
        service_name: 서비스 이름 (예: "law", "kosis", "dart")

    Returns:
        인증 쿼리 파라미터 딕셔너리 또는 None
    """
    auth_config = _AUTH_REGISTRY.get(service_name)
    if not auth_config or auth_config["type"] != "query_param":
        return None

    key = os.environ.get(auth_config["env_var"], "")
    if not key:
        return None

    return {auth_config["key_name"]: key}


def check_api_key(service_name: str) -> tuple:
    """
    서비스의 API 키 존재 여부 확인

    Args:
        service_name: 서비스 이름

    Returns:
        (bool, str): (키 존재 여부, 에러 메시지 또는 "")
    """
    auth_config = _AUTH_REGISTRY.get(service_name)
    if not auth_config:
        return False, f"알 수 없는 서비스: {service_name}"

    auth_type = auth_config["type"]

    if auth_type in ("header", "query_param"):
        env_var = auth_config["env_var"]
        if os.environ.get(env_var):
            return True, ""
        return False, f"{env_var} 환경변수가 설정되지 않았습니다."

    elif auth_type == "header_pair":
        missing = []
        for _, env_var in auth_config["headers"].items():
            if not os.environ.get(env_var):
                missing.append(env_var)
        if missing:
            return False, f"{', '.join(missing)} 환경변수가 설정되지 않았습니다."
        return True, ""

    elif auth_type == "oauth2":
        missing = []
        for _, env_var in auth_config["env_vars"].items():
            if not os.environ.get(env_var):
                missing.append(env_var)
        if missing:
            return False, f"{', '.join(missing)} 환경변수가 설정되지 않았습니다."
        return True, ""

    return False, f"알 수 없는 인증 타입: {auth_type}"


def register_auth(service_name: str, auth_config: dict):
    """
    런타임에 새 서비스 인증 설정 등록

    Args:
        service_name: 서비스 이름
        auth_config: 인증 설정 딕셔너리
    """
    _AUTH_REGISTRY[service_name] = auth_config


def list_services() -> list:
    """등록된 모든 서비스 목록 반환"""
    return list(_AUTH_REGISTRY.keys())
