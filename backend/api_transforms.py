"""
api_transforms.py - 선언적 YAML 응답 변환 엔진

api_registry.yaml의 `response:` 블록을 해석하여 API 응답을 변환합니다.
Python 코드 없이 YAML 선언만으로 응답 변환이 가능합니다.

지원 연산:
  extract  - 중첩 데이터 추출 (점 경로, 배열 인덱스, XML 태그)
  first    - 배열에서 첫 번째 요소
  fields   - 필드 선택/이름변경/변환
  filter   - 조건 필터링
  sort     - 정렬
  limit    - 결과 수 제한
  wrap     - 표준 응답 포장

사용법:
    from api_transforms import apply_declarative_transform

    response_config = {
        "extract": "items",
        "fields": {"name": {"from": "title", "clean_html": True}},
        "limit": 20,
        "wrap": {"success": True, "count": "_count", "data": "_results"}
    }
    result = apply_declarative_transform(raw_data, response_config, tool_input)
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from common.html_utils import clean_html


# === 메인 함수 ===

def apply_declarative_transform(
    raw_data: Any,
    response_config: dict,
    tool_input: dict
) -> Any:
    """YAML response: 설정 기반 응답 변환

    Args:
        raw_data: API 원본 응답 데이터
        response_config: YAML의 response: 블록
        tool_input: 도구에 전달된 입력 파라미터

    Returns:
        변환된 응답 데이터
    """
    if not response_config or not isinstance(response_config, dict):
        return raw_data

    data = raw_data

    # 1. extract - 중첩 데이터 추출
    extract_path = response_config.get("extract")
    if extract_path:
        data = _extract_path(data, extract_path)

    # 2. first - 배열에서 첫 요소
    if response_config.get("first"):
        if isinstance(data, list) and data:
            data = data[0]
        elif isinstance(data, list):
            data = None

    # 3. fields - 필드 매핑 (배열 또는 단일 객체)
    fields_config = response_config.get("fields")
    if fields_config:
        if isinstance(data, list):
            data = [_map_fields(item, fields_config) for item in data if isinstance(item, dict)]
        elif isinstance(data, dict):
            data = _map_fields(data, fields_config)

    # 4. filter - 조건 필터링
    filter_config = response_config.get("filter")
    if filter_config and isinstance(data, list):
        data = _apply_filter(data, filter_config)

    # 5. sort - 정렬
    sort_config = response_config.get("sort")
    if sort_config and isinstance(data, list):
        data = _apply_sort(data, sort_config)

    # 6. limit - 결과 수 제한
    limit = response_config.get("limit")
    if limit and isinstance(data, list):
        data = data[:limit]

    # 7. wrap - 표준 응답 포장
    wrap_config = response_config.get("wrap")
    if wrap_config:
        return _apply_wrap(raw_data, data, wrap_config, tool_input)

    return data


# === 1. extract: 중첩 데이터 추출 ===

def _extract_path(data: Any, path) -> Any:
    """점(.) 경로, 배열 인덱스, XML 태그로 데이터 추출

    지원 패턴:
      "items"           -> data["items"]
      "data.results"    -> data["data"]["results"]
      "[0]"             -> data[0]
      "data[0].name"    -> data["data"][0]["name"]
      1                 -> data[1]  (정수 인덱스 직접 지원)

    XML 파싱 결과에서도 태그명으로 중첩 탐색합니다.
    """
    if path is None or data is None:
        return data

    # 정수 인덱스 직접 지원 (예: extract: 1)
    if isinstance(path, int):
        if isinstance(data, list) and 0 <= path < len(data):
            return data[path]
        return None

    if not path:
        return data

    parts = _parse_path(path)
    current = data

    for part in parts:
        if current is None:
            return None

        if isinstance(part, int):
            # 배열 인덱스
            if isinstance(current, list) and 0 <= part < len(current):
                current = current[part]
            else:
                return None
        elif isinstance(current, dict):
            if part in current:
                current = current[part]
            else:
                # XML 중첩 탐색: body > items > {part} 등
                found = _extract_xml_nested(current, part)
                if found is not None:
                    current = found
                else:
                    return None
        else:
            return None

    return current


def _parse_path(path: str) -> list:
    """경로 문자열을 파트 리스트로 분리

    "data[0].name" -> ["data", 0, "name"]
    "items"        -> ["items"]
    "[0]"          -> [0]
    """
    import re
    parts = []
    for segment in path.split("."):
        if not segment:
            continue
        # "[0]" 또는 "data[0]" 패턴
        match = re.match(r'^(\w*)(?:\[(\d+)\])?$', segment)
        if match:
            name, idx = match.groups()
            if name:
                parts.append(name)
            if idx is not None:
                parts.append(int(idx))
        else:
            parts.append(segment)
    return parts


def _extract_xml_nested(data: dict, tag_name: str) -> Any:
    """XML 파싱 결과에서 중첩 태그 탐색

    body > items > tag_name, response > body > tag_name 등
    """
    # 직접 존재
    if tag_name in data:
        return data[tag_name]

    # 한 단계 아래 탐색
    for key in ("body", "response", "dbs", "items", "result", "data"):
        if key in data and isinstance(data[key], dict):
            if tag_name in data[key]:
                return data[key][tag_name]
            # 두 단계까지
            for subkey in ("body", "items", "result", "data"):
                sub = data[key].get(subkey)
                if isinstance(sub, dict) and tag_name in sub:
                    return sub[tag_name]
    return None


# === 3. fields: 필드 매핑 ===

def _map_fields(item: dict, fields_config: dict) -> dict:
    """단일 객체의 필드를 변환 설정에 따라 매핑

    fields_config 예시:
        name: {from: title, clean_html: true}
        price: {from: lprice}
        mall: {from: mallName, default: "네이버"}
        category: {template: "{category1} > {category2}"}
        site: {value: "naver"}
        datetime: {from: datetime, timestamp_to_str: "%Y-%m-%d %H:%M"}
    """
    result = {}

    for output_key, config in fields_config.items():
        if isinstance(config, str):
            # 축약형: "name: title" -> {from: "title"}
            result[output_key] = item.get(config, "")
            continue

        if not isinstance(config, dict):
            result[output_key] = config
            continue

        value = None

        # value: 상수값
        if "value" in config:
            result[output_key] = config["value"]
            continue

        # template: 템플릿 조합
        if "template" in config:
            result[output_key] = _apply_template(config["template"], item)
            continue

        # from: 소스 필드에서 가져오기
        if "from" in config:
            source_key = config["from"]
            # 점 경로 지원: "nested.field"
            if "." in source_key:
                value = _get_nested(item, source_key)
            else:
                value = item.get(source_key)

        # default: 값이 없을 때 기본값
        if value is None and "default" in config:
            value = config["default"]

        if value is None:
            value = ""

        # 변환 적용
        value = _apply_field_transforms(value, config, item)

        result[output_key] = value

    return result


def _apply_field_transforms(value: Any, config: dict, item: dict) -> Any:
    """필드 값에 변환 적용"""
    # clean_html: HTML 태그 제거
    if config.get("clean_html") and isinstance(value, str):
        value = clean_html(value)

    # timestamp_to_str: 유닉스 타임스탬프 -> 문자열
    if "timestamp_to_str" in config:
        fmt = config["timestamp_to_str"]
        try:
            if isinstance(value, (int, float)) and value > 0:
                value = datetime.fromtimestamp(value).strftime(fmt)
            else:
                value = ""
        except (ValueError, OSError, OverflowError):
            value = ""

    # to_int: 정수 변환
    if config.get("to_int"):
        try:
            value = int(value)
        except (ValueError, TypeError):
            pass

    # to_str: 문자열 변환
    if config.get("to_str"):
        value = str(value) if value is not None else ""

    return value


def _apply_template(template: str, item: dict) -> str:
    """템플릿 문자열에 item 필드 대입

    "{category1} > {category2}" + item -> "가전 > 노트북"
    """
    try:
        return template.format_map(_SafeDict(item))
    except (KeyError, ValueError):
        return template


class _SafeDict(dict):
    """format_map에서 없는 키를 빈 문자열로 처리"""
    def __missing__(self, key):
        return ""


def _get_nested(data: dict, dotted_key: str) -> Any:
    """점(.) 경로로 중첩 값 접근: "a.b.c" -> data["a"]["b"]["c"]"""
    current = data
    for part in dotted_key.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


# === 4. filter: 조건 필터링 ===

def _apply_filter(data: list, filter_config: Union[dict, list]) -> list:
    """리스트 데이터를 조건에 따라 필터링

    단일 필터:
        filter: {field: status, eq: "active"}

    다중 필터 (AND):
        filter:
          - {field: status, eq: "active"}
          - {field: score, gte: 50}

    지원 연산자: eq, ne, gt, gte, lt, lte, contains, not_contains, in, not_in
    """
    if isinstance(filter_config, dict):
        filter_config = [filter_config]

    if not isinstance(filter_config, list):
        return data

    result = data
    for condition in filter_config:
        if not isinstance(condition, dict):
            continue
        result = [item for item in result if _match_condition(item, condition)]

    return result


def _match_condition(item: Any, condition: dict) -> bool:
    """단일 조건 매칭"""
    field = condition.get("field", "")
    if not field:
        return True

    value = item.get(field) if isinstance(item, dict) else None

    if "eq" in condition:
        return value == condition["eq"]
    if "ne" in condition:
        return value != condition["ne"]
    if "gt" in condition:
        return _safe_compare(value, condition["gt"], ">")
    if "gte" in condition:
        return _safe_compare(value, condition["gte"], ">=")
    if "lt" in condition:
        return _safe_compare(value, condition["lt"], "<")
    if "lte" in condition:
        return _safe_compare(value, condition["lte"], "<=")
    if "contains" in condition:
        return isinstance(value, str) and condition["contains"] in value
    if "not_contains" in condition:
        return not (isinstance(value, str) and condition["not_contains"] in value)
    if "in" in condition:
        return value in condition["in"]
    if "not_in" in condition:
        return value not in condition["not_in"]

    return True


def _safe_compare(a: Any, b: Any, op: str) -> bool:
    """안전한 비교 (타입 불일치 시 False)"""
    try:
        if op == ">":
            return a > b
        elif op == ">=":
            return a >= b
        elif op == "<":
            return a < b
        elif op == "<=":
            return a <= b
    except (TypeError, ValueError):
        pass
    return False


# === 5. sort: 정렬 ===

def _apply_sort(data: list, sort_config: dict) -> list:
    """리스트 데이터 정렬

    sort: {by: date, order: desc}
    sort: {by: price, order: asc, type: number}
    """
    sort_key = sort_config.get("by")
    if not sort_key:
        return data

    reverse = sort_config.get("order", "asc") == "desc"
    sort_type = sort_config.get("type", "auto")

    def key_func(item):
        val = item.get(sort_key, "") if isinstance(item, dict) else ""
        if sort_type == "number":
            try:
                return float(val)
            except (ValueError, TypeError):
                return 0
        return str(val) if val is not None else ""

    try:
        return sorted(data, key=key_func, reverse=reverse)
    except TypeError:
        return data


# === 7. wrap: 응답 포장 ===

def _apply_wrap(
    raw_data: Any,
    processed_data: Any,
    wrap_config: dict,
    tool_input: dict
) -> dict:
    """변환된 데이터를 표준 응답 형식으로 포장

    wrap 설정 예시:
        wrap:
          success: true           # 상수
          count: _count           # 결과 수 자동 계산
          data: _results          # 변환된 데이터
          total: {from_root: total}  # 원본 응답에서 가져오기
          message: {template: "'{query}' 검색 결과 {_count}개"}

    특수 플레이스홀더:
      _results  -> processed_data
      _count    -> len(processed_data) if list
    """
    result = {}
    count = len(processed_data) if isinstance(processed_data, list) else (1 if processed_data else 0)

    for key, config in wrap_config.items():
        if config == "_results":
            result[key] = processed_data
        elif config == "_count":
            result[key] = count
        elif isinstance(config, dict):
            if "from_root" in config:
                # 원본 응답에서 값 가져오기 (점 경로 지원)
                root_key = config["from_root"]
                if isinstance(raw_data, dict):
                    if "." in str(root_key):
                        result[key] = _get_nested(raw_data, str(root_key))
                        if result[key] is None:
                            result[key] = 0
                    else:
                        result[key] = raw_data.get(root_key, 0)
                else:
                    result[key] = 0
            elif "template" in config:
                # 템플릿 문자열
                tmpl_data = dict(tool_input)
                tmpl_data["_count"] = count
                result[key] = _apply_template(config["template"], tmpl_data)
            elif "from_input" in config:
                # tool_input에서 값 가져오기
                result[key] = tool_input.get(config["from_input"], "")
            else:
                result[key] = config
        else:
            # 상수 (true, false, 숫자, 문자열)
            result[key] = config

    return result
