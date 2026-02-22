"""
response_formatter.py - 응답 포맷 표준화

모든 도구 패키지의 응답 형식을 통일합니다.

현재 3가지 응답 패턴이 혼재:
    - dict: {"error": "..."} 또는 {"success": False, "error": "..."}
    - JSON string: json.dumps(result)
    - 원시 텍스트: response.text

이 모듈은 표준 응답 형식을 정의합니다.

사용법:
    from common.response_formatter import success_response, error_response, format_json
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


def success_response(data: Any = None, message: str = "", **extra) -> dict:
    """
    성공 응답 생성

    Args:
        data: 응답 데이터
        message: 사용자에게 보여줄 메시지
        **extra: 추가 필드 (예: total=10, map_data={...})

    Returns:
        {"success": True, "data": ..., "message": ...}
    """
    result = {"success": True}
    if data is not None:
        result["data"] = data
    if message:
        result["message"] = message
    result.update(extra)
    return result


def error_response(error: str, code: str = None) -> dict:
    """
    에러 응답 생성

    Args:
        error: 에러 메시지
        code: 에러 코드 (선택, 예: "AUTH_MISSING", "TIMEOUT")

    Returns:
        {"success": False, "error": ...}
    """
    result = {"success": False, "error": error}
    if code:
        result["error_code"] = code
    return result


def format_json(data: Any, ensure_ascii: bool = False, indent: int = 2) -> str:
    """
    JSON 문자열 변환 (한글 유지)

    기존 패키지들의 json.dumps(result, ensure_ascii=False, indent=2) 패턴을 통합.

    Args:
        data: 변환할 데이터
        ensure_ascii: ASCII만 사용 (기본: False, 한글 유지)
        indent: 들여쓰기 (기본: 2)

    Returns:
        JSON 문자열
    """
    return json.dumps(data, ensure_ascii=ensure_ascii, indent=indent)


def save_large_data(data: Any, category: str, identifier: str, base_dir: str = None) -> str:
    """
    대량 데이터를 파일로 저장하고 경로 반환

    여러 도구에서 반복되는 대량 데이터 저장 패턴을 통합.
    예: investment, web, culture 등

    Args:
        data: 저장할 데이터 (list 또는 dict)
        category: 카테고리 (예: "investment", "news")
        identifier: 식별자 (예: 종목코드, 검색어)
        base_dir: 기본 저장 디렉토리 (기본: outputs/{category})

    Returns:
        저장된 파일 경로 문자열
    """
    from runtime_utils import get_base_path
    if base_dir:
        output_dir = Path(base_dir)
    else:
        output_dir = get_base_path() / "outputs" / category
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # identifier에서 파일명에 부적합한 문자 제거
    safe_id = "".join(c for c in str(identifier) if c.isalnum() or c in "-_.")
    filename = f"{safe_id}_{timestamp}.json"
    filepath = output_dir / filename

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return str(filepath)


def is_error(response: Any) -> bool:
    """
    응답이 에러인지 확인

    다양한 에러 형식을 모두 처리:
        - {"error": "..."} (기존 일부 패키지)
        - {"success": False, ...} (기존 일부 패키지)
        - 문자열이면서 "에러:" 또는 "오류:"로 시작

    Args:
        response: 확인할 응답

    Returns:
        에러 여부
    """
    if isinstance(response, dict):
        if "error" in response:
            return True
        if response.get("success") is False:
            return True
    if isinstance(response, str):
        if response.startswith(("에러:", "오류:", "Error:")):
            return True
    return False


def get_error_message(response: Any) -> Optional[str]:
    """
    응답에서 에러 메시지 추출

    Args:
        response: 응답 데이터

    Returns:
        에러 메시지 또는 None
    """
    if isinstance(response, dict):
        return response.get("error")
    if isinstance(response, str) and is_error(response):
        return response
    return None
