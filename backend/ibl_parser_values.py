"""IBL 파서 값/파라미터 추출 층 (2026-07-18 모듈화 — 1500줄 규칙)

ibl_parser.py 에서 verbatim 이동: {params} 파싱(_parse_params/_parse_relaxed_params)과
값 추출기(문자열·괄호·숫자·비인용). 리프 모듈(파서 내부 의존 없음) — IBLSyntaxError 도
여기 산다(blocks·본체가 공유, 순환 없는 최하층). 본체가 재수출하므로
`from ibl_parser import IBLSyntaxError` 경로 불변.
"""
import json
import re
from typing import Dict, Optional, Tuple


class IBLSyntaxError(Exception):
    """IBL 문법 오류"""
    pass


def _parse_params(text: str) -> dict:
    """
    파라미터 블록 파싱.

    JSON5(unquoted keys, single/double quotes, trailing commas, comments 등 허용)를
    우선 시도하고, 실패하면 표준 JSON → relaxed_params 순으로 폴백.

    JSON5는 사람이 손으로 쓰는 JSON-like 형식의 표준이고, 우리가 그동안 만들던
    헬퍼들(_quote_unquoted_keys, replace 변환)이 사실상 JSON5의 부분집합을
    재발명하는 것이었다. 표준에 위임하면 따옴표 변환·키 quote 같은 미봉책이
    모두 불필요해진다.
    """
    if not text:
        return {}

    # 1. JSON5 시도 — unquoted keys, 양쪽 따옴표, trailing comma 등 모두 처리
    try:
        import pyjson5
        result = pyjson5.loads(text)
        if isinstance(result, dict):
            return result
    except Exception:
        pass

    # 2. 표준 JSON (JSON5 라이브러리 부재 또는 파싱 실패 시 보험)
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # 3. 최후 폴백: 간단한 key: value 파싱
    return _parse_relaxed_params(text)


def _parse_relaxed_params(text: str) -> dict:
    """
    느슨한 파라미터 파싱 — 배열 [...], 중첩 객체 {...} 포함 지원

    { query: "임대차", page: 1 }                      → {"query": "임대차", "page": 1}
    { data: [1, 2, 3], nested: {a: 1} }               → {"data": [1,2,3], "nested": {"a": 1}}
    { items: [{name: "A"}, {name: "B"}], count: 2 }   → {"items": [...], "count": 2}
    """
    # 중괄호 제거
    inner = text.strip()
    if inner.startswith('{'):
        inner = inner[1:]
    if inner.endswith('}'):
        inner = inner[:-1]
    inner = inner.strip()

    if not inner:
        return {}

    params = {}
    i = 0
    n = len(inner)

    while i < n:
        # 공백, 쉼표 건너뛰기
        while i < n and inner[i] in ' \t\n\r,':
            i += 1
        if i >= n:
            break

        # key 추출 (알파벳, 숫자, _)
        key_start = i
        while i < n and (inner[i].isalnum() or inner[i] == '_'):
            i += 1
        key = inner[key_start:i]
        if not key:
            break

        # 공백 건너뛰기
        while i < n and inner[i] in ' \t':
            i += 1

        # : 건너뛰기
        if i < n and inner[i] == ':':
            i += 1
        else:
            break

        # 공백 건너뛰기
        while i < n and inner[i] in ' \t':
            i += 1

        if i >= n:
            break

        # value 추출
        value, i = _extract_value(inner, i)
        params[key] = value

    return params


def _extract_value(text: str, pos: int):
    """
    위치 pos에서 value를 추출. (value, new_pos) 반환.

    지원 타입: "string", 'string', [array], {object}, number, true/false/null, 미따옴표 문자열
    """
    if pos >= len(text):
        return "", pos

    ch = text[pos]

    # 문자열 (큰따옴표)
    if ch == '"':
        return _extract_string(text, pos, '"')

    # 문자열 (작은따옴표)
    if ch == "'":
        return _extract_string(text, pos, "'")

    # 배열
    if ch == '[':
        return _extract_bracket(text, pos, '[', ']')

    # 중첩 객체
    if ch == '{':
        return _extract_bracket(text, pos, '{', '}')

    # 숫자 (음수 포함)
    if ch in '-0123456789':
        return _extract_number(text, pos)

    # boolean / null
    if text[pos:pos + 4] == 'true':
        return True, pos + 4
    if text[pos:pos + 5] == 'false':
        return False, pos + 5
    if text[pos:pos + 4] == 'null':
        return None, pos + 4

    # 따옴표 없는 문자열 (다음 , 또는 } 까지)
    return _extract_unquoted(text, pos)


def _extract_string(text: str, pos: int, quote: str):
    """따옴표 문자열 추출"""
    i = pos + 1  # 여는 따옴표 건너뛰기
    result = []
    while i < len(text):
        if text[i] == '\\' and i + 1 < len(text):
            result.append(text[i + 1])
            i += 2
        elif text[i] == quote:
            i += 1  # 닫는 따옴표 건너뛰기
            return ''.join(result), i
        else:
            result.append(text[i])
            i += 1
    return ''.join(result), i


def _extract_bracket(text: str, pos: int, open_br: str, close_br: str):
    """bracket 매칭으로 배열/객체 추출. JSON 파싱 시도 후 실패하면 재귀."""
    depth = 0
    i = pos
    while i < len(text):
        ch = text[i]
        if ch == open_br:
            depth += 1
        elif ch == close_br:
            depth -= 1
            if depth == 0:
                raw = text[pos:i + 1]
                # 1. JSON5 시도 — 모든 JSON-like 입력의 표준 해석기
                try:
                    import pyjson5
                    return pyjson5.loads(raw), i + 1
                except Exception:
                    pass
                # 2. 표준 JSON (JSON5 부재 시 보험)
                try:
                    return json.loads(raw), i + 1
                except (json.JSONDecodeError, ValueError):
                    pass
                # 3. 중첩 객체면 재귀적 relaxed 파싱
                if open_br == '{':
                    return _parse_relaxed_params(raw), i + 1
                # 배열이면 원본 문자열 반환 (최선)
                return raw, i + 1
        elif ch in '"\'':
            # 문자열 리터럴 내부 건너뛰기
            quote = ch
            i += 1
            while i < len(text) and text[i] != quote:
                if text[i] == '\\':
                    i += 1
                i += 1
        i += 1
    # 닫는 bracket을 못 찾으면 원본 반환
    return text[pos:], len(text)


def _extract_number(text: str, pos: int):
    """숫자 추출 (정수/실수, 음수 포함)"""
    i = pos
    if i < len(text) and text[i] == '-':
        i += 1
    while i < len(text) and text[i].isdigit():
        i += 1
    if i < len(text) and text[i] == '.':
        i += 1
        while i < len(text) and text[i].isdigit():
            i += 1
    raw = text[pos:i]
    try:
        return float(raw) if '.' in raw else int(raw), i
    except ValueError:
        return raw, i


def _extract_unquoted(text: str, pos: int):
    """따옴표 없는 문자열: 다음 , 또는 } 또는 ] 까지"""
    i = pos
    while i < len(text) and text[i] not in ',}]':
        i += 1
    return text[pos:i].strip(), i
