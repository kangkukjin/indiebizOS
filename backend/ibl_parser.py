"""
ibl_parser.py - IBL 텍스트 파서

IBL 코드 텍스트를 파싱하여 실행 가능한 step 리스트로 변환합니다.

문법:
    # 단일 명령
    [node:action](target) { "key": "value" }

    # 파이프라인 (>> 로 연결, 순차 실행)
    [source:web_search]("AI 뉴스") >> [system:file]("결과.md")

    # 병렬 실행 (& 로 연결, 동시 실행)
    [source:web_search]("AI") & [source:search_news]("부동산")

    # Fallback (?? 로 연결, 실패 시 대체)
    [source:web_search](primary) ?? [source:crawl](backup)

    # 혼합 파이프라인
    [source:web_search]("AI") & [source:search_news]("부동산") >> [system:file]("결과.md")
    [source:web_search](main) ?? [source:crawl](fallback) >> [messenger:send](telegram)

    # 멀티라인 파이프라인
    [source:web_search](search_laws) { "query": "근로기준법" }
      >> [system:file]("법률검색.md")
      >> [messenger:send]("telegram") { "to": "me" }

    # 변수 바인딩
    $result = [source:web_search]("AI 뉴스")
    [messenger:send]("telegram") { "body": "$result" }

사용법:
    from ibl_parser import parse, parse_step

    # 파이프라인 파싱
    steps = parse('[source:web_search]("AI") >> [system:file]("out.md")')
    # → [{"_node": "source", ...}, {"_node": "system", ...}]

    # 병렬 파싱
    steps = parse('[source:web_search]("AI") & [source:search_news]("부동산")')
    # → [{"_parallel": True, "branches": [step1, step2]}]

    # Fallback 파싱
    steps = parse('[source:web_search](main) ?? [source:crawl](backup)')
    # → [{"_fallback_chain": [step1, step2]}]

    # 단일 명령 파싱
    step = parse_step('[source:web_search](search_laws) { "query": "임대차" }')
    # → {"_node": "source", "action": "web_search", "target": "search_laws", "params": {"query": "임대차"}}
"""

import re
import json
from typing import List, Dict, Optional, Any, Tuple


# === 공개 API ===

def parse(code: str) -> List[Dict]:
    """
    IBL 코드를 파싱하여 실행 가능한 step 리스트로 변환

    Args:
        code: IBL 코드 텍스트

    Returns:
        step 리스트. 각 step은 {_node, action, target, params}
        파이프라인이면 여러 개, 단일 명령이면 1개.

    Raises:
        IBLSyntaxError: 문법 오류
    """
    if not code or not code.strip():
        raise IBLSyntaxError("빈 코드입니다.")

    # 전처리: 주석 제거, 줄 정규화
    lines = _preprocess(code)
    if not lines:
        raise IBLSyntaxError("파싱 가능한 코드가 없습니다.")

    # 변수 바인딩과 명령문 분리
    statements, variables = _extract_statements(lines)

    all_steps = []
    for stmt in statements:
        # >> 로 파이프라인 분리
        segments = _split_pipeline(stmt)
        for seg in segments:
            # 각 세그먼트 내에서 & 또는 ?? 연산자 처리
            parsed = _parse_group(seg.strip())
            if parsed is None:
                raise IBLSyntaxError(f"파싱 실패: {seg.strip()}")
            # 변수 참조 치환
            parsed = _resolve_variables(parsed, variables)
            all_steps.append(parsed)

    if not all_steps:
        raise IBLSyntaxError("실행 가능한 명령이 없습니다.")

    return all_steps


def parse_step(text: str) -> Optional[Dict]:
    """
    단일 IBL 명령 파싱

    Args:
        text: 예) '[api:call](search_laws) { "query": "임대차" }'

    Returns:
        {_node, action, target, params} 또는 None
    """
    return _parse_step(text.strip())


# === 예외 ===

class IBLSyntaxError(Exception):
    """IBL 문법 오류"""
    pass


# === 내부 구현 ===

# 단일 명령 패턴: [node:action](target)
# - [node:action] 필수
# - (target) 선택
# - { params } 는 regex가 아닌 _extract_bracket으로 추출 (따옴표 인식)
_STEP_PATTERN = re.compile(
    r'\[(\w+):(\w+)\]'           # [node:action]
    r'(?:\s*\(([^)]*)\))?',      # (target) - 선택적
    re.DOTALL
)

# 변수 할당 패턴: $name = [node:action](...)
_VAR_ASSIGN_PATTERN = re.compile(
    r'^\$(\w+)\s*=\s*(.+)$',
    re.DOTALL
)

# 변수 참조 패턴: $name
_VAR_REF_PATTERN = re.compile(r'\$(\w+)')


def _preprocess(code: str) -> List[str]:
    """전처리: 주석 제거, 빈 줄 제거, 연속 줄 합치기, 멀티라인 블록 병합"""
    lines = []
    for line in code.split('\n'):
        # # 주석 제거 (문자열 내부가 아닌 경우)
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        if not stripped:
            continue
        lines.append(stripped)

    if not lines:
        return []

    # 1단계: >> 로 시작하는 줄을 이전 줄에 합치기 (멀티라인 파이프라인)
    merged = [lines[0]]
    for line in lines[1:]:
        if line.startswith('>>'):
            merged[-1] = merged[-1] + ' ' + line
        else:
            merged.append(line)

    # 2단계: 멀티라인 { } 블록 병합
    #   이전 줄의 { } 균형이 맞지 않으면 다음 줄을 합침
    result = []
    i = 0
    while i < len(merged):
        current = merged[i]
        depth = _count_brace_depth(current)
        while depth > 0 and i + 1 < len(merged):
            i += 1
            current = current + '\n' + merged[i]
            depth += _count_brace_depth(merged[i])
        result.append(current)
        i += 1

    return result


def _count_brace_depth(text: str) -> int:
    """텍스트 내 { } 균형 계산 (문자열 내부 무시)"""
    depth = 0
    in_string = False
    string_char = None
    i = 0
    while i < len(text):
        ch = text[i]
        if not in_string:
            if ch == '"' or ch == "'":
                in_string = True
                string_char = ch
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
        else:
            if ch == '\\' and i + 1 < len(text):
                i += 1  # 이스케이프 건너뛰기
            elif ch == string_char:
                in_string = False
        i += 1
    return depth


def _extract_statements(lines: List[str]) -> Tuple[List[str], Dict[str, str]]:
    """
    변수 할당과 명령문을 분리

    Returns:
        (statements, variables)
        - statements: 실행할 명령문 리스트
        - variables: {변수명: 값} (나중에 순차 실행 결과로 채워짐)
    """
    statements = []
    variables = {}  # 변수명 → 위치 정보 (몇 번째 step의 결과인지)

    step_index = 0
    for line in lines:
        m = _VAR_ASSIGN_PATTERN.match(line)
        if m:
            var_name = m.group(1)
            expr = m.group(2).strip()
            variables[var_name] = step_index
            statements.append(expr)
            # 파이프라인 내 step 수 세기
            step_index += len(_split_pipeline(expr))
        else:
            statements.append(line)
            step_index += len(_split_pipeline(line))

    return statements, variables


def _split_pipeline(text: str) -> List[str]:
    """
    >> 연산자로 파이프라인 분리

    '[a:b]("x") >> [c:d]("y")' → ['[a:b]("x")', '[c:d]("y")']

    중괄호 {} 내부의 >>는 무시 (JSON 문자열 안의 >>)
    """
    segments = []
    current = []
    depth = 0  # { } 깊이 추적

    i = 0
    chars = text
    while i < len(chars):
        ch = chars[i]

        if ch == '{':
            depth += 1
            current.append(ch)
        elif ch == '}':
            depth -= 1
            current.append(ch)
        elif ch == '>' and i + 1 < len(chars) and chars[i + 1] == '>' and depth == 0:
            # >> 발견 (중괄호 밖)
            seg = ''.join(current).strip()
            if seg:
                segments.append(seg)
            current = []
            i += 2  # >> 건너뛰기
            continue
        elif ch == '"' or ch == "'":
            # 문자열 리터럴 건너뛰기
            quote = ch
            current.append(ch)
            i += 1
            while i < len(chars) and chars[i] != quote:
                if chars[i] == '\\':
                    current.append(chars[i])
                    i += 1
                    if i < len(chars):
                        current.append(chars[i])
                else:
                    current.append(chars[i])
                i += 1
            if i < len(chars):
                current.append(chars[i])  # 닫는 따옴표
        else:
            current.append(ch)

        i += 1

    # 마지막 세그먼트
    seg = ''.join(current).strip()
    if seg:
        segments.append(seg)

    return segments


def _parse_group(text: str) -> Optional[Dict]:
    """
    >> 로 분리된 하나의 세그먼트를 파싱.
    내부에 & 또는 ?? 연산자가 있으면 특수 노드로 변환.

    반환:
    - 일반 step: {_node, action, target, params}
    - 병렬: {_parallel: True, branches: [step, ...]}
    - Fallback: {_fallback_chain: [step, ...]}
    """
    if not text:
        return None

    # & 연산자 확인 (병렬)
    parallel_parts = _split_by_operator(text, '&')
    if len(parallel_parts) > 1:
        branches = []
        for part in parallel_parts:
            step = _parse_step(part.strip())
            if step is None:
                raise IBLSyntaxError(f"병렬 요소 파싱 실패: {part.strip()}")
            branches.append(step)
        return {"_parallel": True, "branches": branches}

    # ?? 연산자 확인 (fallback)
    fallback_parts = _split_by_operator(text, '??')
    if len(fallback_parts) > 1:
        chain = []
        for part in fallback_parts:
            step = _parse_step(part.strip())
            if step is None:
                raise IBLSyntaxError(f"fallback 요소 파싱 실패: {part.strip()}")
            chain.append(step)
        return {"_fallback_chain": chain}

    # 일반 단일 step
    return _parse_step(text)


def _split_by_operator(text: str, operator: str) -> List[str]:
    """
    연산자(&, ??)로 텍스트 분리.
    문자열 리터럴과 중괄호 내부의 연산자는 무시.

    Args:
        text: 파싱할 텍스트
        operator: 분리할 연산자 ('&' 또는 '??')
    """
    segments = []
    current = []
    depth = 0        # { } 깊이
    in_string = False
    string_char = None
    op_len = len(operator)

    i = 0
    chars = text
    while i < len(chars):
        ch = chars[i]

        # 문자열 리터럴 추적
        if not in_string and (ch == '"' or ch == "'"):
            in_string = True
            string_char = ch
            current.append(ch)
            i += 1
            continue
        elif in_string:
            if ch == '\\' and i + 1 < len(chars):
                current.append(ch)
                current.append(chars[i + 1])
                i += 2
                continue
            elif ch == string_char:
                in_string = False
            current.append(ch)
            i += 1
            continue

        # 중괄호 깊이 추적
        if ch == '{':
            depth += 1
            current.append(ch)
        elif ch == '}':
            depth -= 1
            current.append(ch)
        elif depth == 0 and chars[i:i+op_len] == operator:
            # 연산자 발견 (중괄호/문자열 밖)
            # & 의 경우: && 가 아닌지 확인 (미래 확장 대비)
            if operator == '&' and i + 1 < len(chars) and chars[i + 1] == '&':
                current.append(ch)
            else:
                seg = ''.join(current).strip()
                if seg:
                    segments.append(seg)
                current = []
                i += op_len
                continue
        else:
            current.append(ch)

        i += 1

    # 마지막 세그먼트
    seg = ''.join(current).strip()
    if seg:
        segments.append(seg)

    return segments


def _parse_step(text: str) -> Optional[Dict]:
    """
    단일 IBL 명령 파싱

    [node:action](target) { params }

    Returns:
        {_node, action, target, params} 또는 None
    """
    if not text:
        return None

    m = _STEP_PATTERN.search(text)
    if not m:
        return None

    node = m.group(1)
    action = m.group(2)
    target_raw = m.group(3)

    # target 처리: 따옴표 제거
    target = ""
    if target_raw is not None:
        target = target_raw.strip().strip('"').strip("'")

    # params 처리: regex 이후 남은 텍스트에서 { 를 찾아 _extract_bracket으로 추출
    params = {}
    remaining = text[m.end():].strip()
    if remaining.startswith('{'):
        extracted, _ = _extract_bracket(remaining, 0, '{', '}')
        if isinstance(extracted, dict):
            params = extracted
        elif isinstance(extracted, str):
            params = _parse_params(extracted)

    return {
        "_node": node,
        "action": action,
        "target": target,
        "params": params,
    }


def _parse_params(text: str) -> dict:
    """
    파라미터 블록 파싱

    { "key": "value", "num": 42 } → dict

    JSON 호환 형식을 우선 시도,
    실패하면 간단한 key: value 형식으로 파싱
    """
    if not text:
        return {}

    # 1. JSON 직접 파싱 시도
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # 2. 작은따옴표 → 큰따옴표 변환 후 재시도
    try:
        converted = text.replace("'", '"')
        result = json.loads(converted)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # 3. 간단한 key: value 파싱 (따옴표 없는 키 지원)
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
                # 1. JSON 직접 파싱
                try:
                    return json.loads(raw), i + 1
                except (json.JSONDecodeError, ValueError):
                    pass
                # 2. 작은따옴표 → 큰따옴표 변환 후 재시도
                try:
                    converted = raw.replace("'", '"')
                    return json.loads(converted), i + 1
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


def _resolve_variables(step: dict, variables: dict) -> dict:
    """
    step 내의 변수 참조($name)를 {{_prev_result}} 패턴으로 변환

    현재는 간단한 구현: $var → {{_step_N_result}} (N = 변수가 할당된 step 인덱스)
    파이프라인에서 순차 실행 시 이전 결과가 자동 전달되므로,
    직전 step 결과는 {{_prev_result}}로 자동 사용됨.

    독립 변수(비직전 참조)는 향후 확장.
    """
    if not variables:
        return step

    resolved = {}
    for key, val in step.items():
        if isinstance(val, str):
            for var_name in variables:
                val = val.replace(f"${var_name}", "{{_prev_result}}")
            resolved[key] = val
        elif isinstance(val, dict):
            resolved[key] = _resolve_variables(val, variables)
        elif isinstance(val, list):
            # _parallel.branches, _fallback_chain 리스트 처리
            resolved[key] = [
                _resolve_variables(item, variables) if isinstance(item, dict) else item
                for item in val
            ]
        else:
            resolved[key] = val

    return resolved


# === 유틸리티 ===

def format_step(step: dict) -> str:
    """step을 IBL 텍스트로 포맷팅 (역변환)"""
    # 병렬 노드
    if step.get("_parallel"):
        branches = step.get("branches", [])
        return " & ".join(format_step(b) for b in branches)

    # Fallback 노드
    if "_fallback_chain" in step:
        chain = step["_fallback_chain"]
        return " ?? ".join(format_step(s) for s in chain)

    # 일반 step
    node = step.get("_node", step.get("node", "?"))
    action = step.get("action", "?")
    target = step.get("target", "")
    params = step.get("params", {})

    result = f"[{node}:{action}]"
    if target:
        result += f'("{target}")'
    if params:
        result += " " + json.dumps(params, ensure_ascii=False)

    return result


def format_pipeline(steps: list) -> str:
    """step 리스트를 IBL 파이프라인 텍스트로 포맷팅"""
    if not steps:
        return ""
    if len(steps) == 1:
        return format_step(steps[0])

    parts = [format_step(steps[0])]
    for step in steps[1:]:
        parts.append(f"  >> {format_step(step)}")

    return "\n".join(parts)


# === 테스트 ===

if __name__ == "__main__":
    print("=== IBL Parser Tests ===\n")

    # 1. 단일 명령
    s1 = parse_step('[api:call](search_laws) { "query": "근로기준법" }')
    print(f"1. 단일: {s1}")
    assert s1["_node"] == "api"
    assert s1["action"] == "call"
    assert s1["target"] == "search_laws"
    assert s1["params"]["query"] == "근로기준법"

    # 2. target 없는 명령
    s2 = parse_step('[api:list]')
    print(f"2. target 없음: {s2}")
    assert s2["_node"] == "api"
    assert s2["action"] == "list"
    assert s2["target"] == ""

    # 3. params 없는 명령
    s3 = parse_step('[web:search]("AI 뉴스")')
    print(f"3. params 없음: {s3}")
    assert s3["target"] == "AI 뉴스"
    assert s3["params"] == {}

    # 4. 파이프라인
    p1 = parse('[web:search]("AI") >> [fs:write]("결과.md")')
    print(f"4. 파이프라인: {len(p1)} steps")
    assert len(p1) == 2
    assert p1[0]["_node"] == "web"
    assert p1[1]["_node"] == "fs"

    # 5. 멀티라인 파이프라인
    code5 = """
    [api:call](search_laws) { "query": "임대차" }
      >> [fs:write]("법률.md")
      >> [channel:send]("telegram") { "to": "me" }
    """
    p2 = parse(code5)
    print(f"5. 멀티라인: {len(p2)} steps")
    assert len(p2) == 3
    assert p2[2]["params"]["to"] == "me"

    # 6. 느슨한 params (따옴표 없는 키)
    s6 = parse_step("[api:call](search_laws) { query: \"임대차\", page: 1 }")
    print(f"6. 느슨한 params: {s6}")
    assert s6["params"]["query"] == "임대차"
    assert s6["params"]["page"] == 1

    # 7. 주석 + 여러 명령문
    code7 = """
    # 첫 번째 검색
    [web:search]("뉴스")
    # 두 번째 검색
    [api:call](search_laws) { "query": "민법" }
    """
    p3 = parse(code7)
    print(f"7. 여러 명령: {len(p3)} steps")
    assert len(p3) == 2

    # 8. 역변환
    formatted = format_pipeline(p1)
    print(f"8. 역변환:\n{formatted}")

    # 9. 빈 코드 에러
    try:
        parse("")
        assert False, "에러가 발생해야 함"
    except IBLSyntaxError as e:
        print(f"9. 빈 코드 에러: {e}")

    # 10. 잘못된 문법 에러
    try:
        parse("이건 IBL이 아닙니다")
        assert False, "에러가 발생해야 함"
    except IBLSyntaxError as e:
        print(f"10. 문법 에러: {e}")

    # === Phase 9: 병렬 & Fallback 테스트 ===
    print("\n--- Phase 9 Tests ---")

    # 11. 병렬 실행 (&)
    p11 = parse('[web:search]("AI") & [web:news]("부동산")')
    print(f"11. 병렬: {p11}")
    assert len(p11) == 1
    assert p11[0]["_parallel"] == True
    assert len(p11[0]["branches"]) == 2
    assert p11[0]["branches"][0]["_node"] == "web"
    assert p11[0]["branches"][0]["action"] == "search"
    assert p11[0]["branches"][1]["action"] == "news"

    # 12. 3개 병렬
    p12 = parse('[web:search]("A") & [web:search]("B") & [web:search]("C")')
    print(f"12. 3개 병렬: branches={len(p12[0]['branches'])}")
    assert p12[0]["_parallel"] == True
    assert len(p12[0]["branches"]) == 3

    # 13. Fallback (??)
    p13 = parse('[api:call](primary) ?? [api:call](backup)')
    print(f"13. Fallback: {p13}")
    assert len(p13) == 1
    assert "_fallback_chain" in p13[0]
    assert len(p13[0]["_fallback_chain"]) == 2

    # 14. 3개 Fallback 체인
    p14 = parse('[api:call](a) ?? [api:call](b) ?? [api:call](c)')
    print(f"14. 3개 Fallback: chain={len(p14[0]['_fallback_chain'])}")
    assert len(p14[0]["_fallback_chain"]) == 3

    # 15. 병렬 >> 순차 혼합
    p15 = parse('[web:search]("AI") & [web:news]("부동산") >> [fs:write]("결과.md")')
    print(f"15. 병렬+순차: {len(p15)} steps")
    assert len(p15) == 2
    assert p15[0]["_parallel"] == True
    assert p15[1]["_node"] == "fs"

    # 16. Fallback >> 순차 혼합
    p16 = parse('[api:call](main) ?? [api:call](backup) >> [channel:send](telegram)')
    print(f"16. Fallback+순차: {len(p16)} steps")
    assert len(p16) == 2
    assert "_fallback_chain" in p16[0]
    assert p16[1]["_node"] == "channel"

    # 17. 역변환 (병렬)
    f17 = format_step(p11[0])
    print(f"17. 병렬 역변환: {f17}")
    assert '&' in f17

    # 18. 역변환 (Fallback)
    f18 = format_step(p13[0])
    print(f"18. Fallback 역변환: {f18}")
    assert '??' in f18

    # 19. 혼합 파이프라인 역변환
    f19 = format_pipeline(p15)
    print(f"19. 혼합 역변환:\n{f19}")
    assert '&' in f19
    assert '>>' in f19

    print("\n=== 모든 테스트 통과 ===")
