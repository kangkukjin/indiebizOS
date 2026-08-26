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

from common.value_semantics import dumps_public_result, require_finite_numbers


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
    return dumps_public_result(data, ensure_ascii=ensure_ascii, indent=indent,
                               producer="response_formatter")


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
        require_finite_numbers(data)
        json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)

    return str(filepath)


def downsample_prices(prices: list, max_points: int = 10) -> list:
    """시계열 [{date, close, ...}] 을 max_points 이하로 다운샘플해 반환 (행 필드는 원본 보존).

    여러 시세 도구(tool_krx/tool_fmp/tool_yfinance)에서 중복되던 다운샘플 로직 통합.
    마지막 점(최신가)은 항상 포함. max_points 가 크면 사실상 전체 반환.
    ★행을 {date, close} 로 깎지 않는다(2026-08-07) — volume·open 등을 버리면 하류
    파이프([table:sort]{by:volume} 등)가 정렬·필터할 재료 자체를 잃는다.
    """
    if not prices:
        return []
    total = len(prices)
    step = max(1, total // max(1, max_points))
    sampled = list(prices[::step])
    if sampled[-1] != prices[-1]:
        sampled.append(prices[-1])
    return [dict(p) for p in sampled]


def compact_price_series(prices: list, max_points: int = 10, threshold: int = 50):
    """시세 시계열 compact 화. threshold 이하면 전체, 초과면 다운샘플 (행 필드는 원본 보존).

    시세 도구들이 항상 동일한 `prices` 키를 내도록 shape 통일용. 반환: (compact, truncated).
    ★{date, close} 투영 은퇴(2026-08-07) — 거래량 등이 파이프에서 죽는 원인이었다.
    """
    total = len(prices or [])
    if total <= threshold:
        return [dict(p) for p in (prices or [])], False
    return downsample_prices(prices, max_points), True


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
