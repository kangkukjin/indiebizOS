"""IBL 파서 제어 블록 층 (2026-07-18 모듈화 — 1500줄 규칙)

ibl_parser.py 에서 verbatim 이동: goal/if·else/case 블록 파서 + 범위 표현식.
★유일한 편차: _parse_block_body 의 재귀 parse 호출을 지연 import 로(순환 차단).
★파이프 설탕(_pipe_block)은 본체 잔류 — 표준-코어 가드가 ibl_parser.py 경로를 스캔.
"""
import re
from typing import Dict, List, Optional, Tuple

from ibl_parser_values import IBLSyntaxError, _parse_params


# === Phase 26: Goal/Condition/Case 파서 ===

# Goal Block 패턴: [goal: "이름"]{...}
_GOAL_PATTERN = re.compile(
    r'^\s*\[goal:\s*"([^"]+)"\]\s*\{',
    re.DOTALL
)

# if 조건문 패턴: [if: condition]{...}
_IF_PATTERN = re.compile(
    r'^\s*\[if:\s*(.+?)\]\s*\{',
    re.DOTALL
)

# else if 패턴: [else if: condition]{...}
_ELSE_IF_PATTERN = re.compile(
    r'\[else\s+if:\s*(.+?)\]\s*\{',
    re.DOTALL
)

# else 패턴: [else]{...}
_ELSE_PATTERN = re.compile(
    r'\[else\]\s*\{',
    re.DOTALL
)

# case문 패턴: [case: sense:field]{...}
_CASE_PATTERN = re.compile(
    r'^\s*\[case:\s*(.+?)\]\s*\{',
    re.DOTALL
)

# 범위 표현식 패턴들
_RANGE_PATTERNS = [
    (re.compile(r'^>=\s*(\d+(?:\.\d+)?)\s*(%?)$'), 'gte'),
    (re.compile(r'^>\s*(\d+(?:\.\d+)?)\s*(%?)$'), 'gt'),
    (re.compile(r'^<=\s*(\d+(?:\.\d+)?)\s*(%?)$'), 'lte'),
    (re.compile(r'^<\s*(\d+(?:\.\d+)?)\s*(%?)$'), 'lt'),
    (re.compile(r'^==\s*(\d+(?:\.\d+)?)\s*(%?)$'), 'eq'),
    (re.compile(r'^(\d+(?:\.\d+)?)\s*~\s*(\d+(?:\.\d+)?)\s*(%?)$'), 'range'),
]

# Goal Block에서 인식하는 시간/안전 키워드
_GOAL_TIME_KEYS = {'deadline', 'until', 'within', 'by', 'every', 'schedule'}
_GOAL_SAFETY_KEYS = {'max_rounds', 'max_cost'}
_GOAL_META_KEYS = {'success_condition', 'resources', 'report_to', 'strategy'}


def _parse_goal_block(code: str) -> Optional[Dict]:
    """
    Goal Block 파싱

    [goal: "이름"]{
        success_condition: "조건",
        max_rounds: 100,
        max_cost: 5.0,
        ...
    }

    Returns:
        {"_goal": True, "name": "...", ...} 또는 None (goal 아님)

    Raises:
        IBLSyntaxError: goal 문법 오류
    """
    m = _GOAL_PATTERN.match(code)
    if not m:
        return None

    goal_name = m.group(1)

    # 정규식이 매칭한 '{' 위치 사용 (goal_name 안의 '{'에 속지 않도록)
    brace_start = m.end() - 1
    body, end_pos = _extract_bracket_raw(code, brace_start, '{', '}')
    if body is None:
        raise IBLSyntaxError(f"Goal block 중괄호가 닫히지 않았습니다: {goal_name}")

    # params 파싱
    params = _parse_params('{' + body + '}')

    # 필수 필드 검증
    has_max_rounds = 'max_rounds' in params
    has_max_cost = 'max_cost' in params
    if not has_max_rounds and not has_max_cost:
        raise IBLSyntaxError(
            f"Goal '{goal_name}'에 max_rounds 또는 max_cost가 필요합니다. "
            f"무한루프 방지를 위한 필수 안전장치입니다."
        )

    # strategy 내부의 if/case 파싱 시도
    if 'strategy' in params and isinstance(params['strategy'], str):
        strategy_parsed = _parse_if_else(params['strategy']) or _parse_case(params['strategy'])
        if strategy_parsed:
            params['strategy'] = strategy_parsed

    result = {
        "_goal": True,
        "name": goal_name,
    }
    result.update(params)

    return result


def _parse_if_else(code: str) -> Optional[Dict]:
    """
    if/else 조건문 파싱

    [if: condition]{...} [else if: condition]{...} [else]{...}

    Returns:
        {"_condition": True, "branches": [...]} 또는 None

    각 branch: {"condition": "..." 또는 None (else), "action": {...}}
    """
    m = _IF_PATTERN.match(code)
    if not m:
        return None

    branches = []
    pos = 0

    # 첫 번째 if
    condition_text = m.group(1).strip()
    # 정규식이 매칭한 '{' 위치 사용 (condition 안의 '{'에 속지 않도록)
    brace_start = m.end() - 1
    body, end_pos = _extract_bracket_raw(code, brace_start, '{', '}')
    if body is None:
        raise IBLSyntaxError(f"if 블록 중괄호가 닫히지 않았습니다.")

    action = _parse_block_body(body.strip())
    branches.append({"condition": condition_text, "action": action})
    pos = end_pos + 1

    # else if / else 처리
    remaining = code[pos:].strip()
    while remaining:
        # else if
        m_elif = _ELSE_IF_PATTERN.match(remaining)
        if m_elif:
            cond = m_elif.group(1).strip()
            brace_start = remaining.index('{', m_elif.start())
            body, end_pos = _extract_bracket_raw(remaining, brace_start, '{', '}')
            if body is None:
                raise IBLSyntaxError("else if 블록 중괄호가 닫히지 않았습니다.")
            action = _parse_block_body(body.strip())
            branches.append({"condition": cond, "action": action})
            remaining = remaining[end_pos + 1:].strip()
            continue

        # else
        m_else = _ELSE_PATTERN.match(remaining)
        if m_else:
            brace_start = remaining.index('{', m_else.start())
            body, end_pos = _extract_bracket_raw(remaining, brace_start, '{', '}')
            if body is None:
                raise IBLSyntaxError("else 블록 중괄호가 닫히지 않았습니다.")
            action = _parse_block_body(body.strip())
            branches.append({"condition": None, "action": action})
            remaining = remaining[end_pos + 1:].strip()
            continue

        break  # if/else 체인 끝

    return {"_condition": True, "branches": branches}


def _parse_case(code: str) -> Optional[Dict]:
    """
    case문 파싱

    [case: sense:field]{
        "값1": [goal: ...]{...},
        "> 20%": [goal: ...]{...},
        "10~20%": [goal: ...]{...},
        default: [goal: ...]{...}
    }

    Returns:
        {"_case": True, "source": "sense:field", "branches": [...], "default": {...}}
    """
    m = _CASE_PATTERN.match(code)
    if not m:
        return None

    source = m.group(1).strip()

    # 전체 body 추출 — 정규식이 매칭한 '{' 위치 사용 (source 안의 '{'에 속지 않도록)
    brace_start = m.end() - 1
    body, end_pos = _extract_bracket_raw(code, brace_start, '{', '}')
    if body is None:
        raise IBLSyntaxError("case 블록 중괄호가 닫히지 않았습니다.")

    # body 내의 각 분기를 파싱
    branches = []
    default_action = None

    # 분기 파싱: "패턴": [action], default: [action]
    inner = body.strip()
    i = 0
    n = len(inner)

    while i < n:
        # 공백/쉼표 건너뛰기
        while i < n and inner[i] in ' \t\n\r,':
            i += 1
        if i >= n:
            break

        # default 키워드 확인
        if inner[i:i+7] == 'default':
            i += 7
            # : 건너뛰기
            while i < n and inner[i] in ' \t\n\r:':
                i += 1
            # action 파싱
            action_text, end = _extract_action_at(inner, i)
            if action_text:
                default_action = _parse_block_body(action_text)
                i = end
            continue

        # "패턴": action 파싱
        if inner[i] == '"' or inner[i] == "'":
            quote = inner[i]
            i += 1
            pat_start = i
            while i < n and inner[i] != quote:
                if inner[i] == '\\':
                    i += 1
                i += 1
            pattern = inner[pat_start:i]
            i += 1  # 닫는 따옴표

            # : 건너뛰기
            while i < n and inner[i] in ' \t\n\r:':
                i += 1

            # action 파싱
            action_text, end = _extract_action_at(inner, i)
            if action_text:
                branch = {"pattern": pattern, "action": _parse_block_body(action_text)}

                # 범위 표현식 파싱 시도
                range_expr = parse_range_expression(pattern)
                if range_expr:
                    branch["range"] = range_expr

                branches.append(branch)
                i = end
            continue

        i += 1  # 파싱 불가능한 문자 건너뛰기

    return {
        "_case": True,
        "source": source,
        "branches": branches,
        "default": default_action
    }


def _extract_action_at(text: str, pos: int) -> Tuple[str, int]:
    """
    텍스트의 pos 위치에서 [goal:...]{...} 또는 [node:action]{...} 추출

    Returns:
        (action_text, end_position) 또는 ("", pos)
    """
    if pos >= len(text):
        return ("", pos)

    # [로 시작하는 위치 찾기
    while pos < len(text) and text[pos] in ' \t\n\r':
        pos += 1

    if pos >= len(text) or text[pos] != '[':
        return ("", pos)

    start = pos

    # [ ] 매칭
    bracket_depth = 0
    i = pos
    while i < len(text):
        if text[i] == '[':
            bracket_depth += 1
        elif text[i] == ']':
            bracket_depth -= 1
            if bracket_depth == 0:
                i += 1
                break
        i += 1

    # { } 매칭 (있으면)
    while i < len(text) and text[i] in ' \t\n\r':
        i += 1

    if i < len(text) and text[i] == '{':
        body, end_pos = _extract_bracket_raw(text, i, '{', '}')
        if body is not None:
            i = end_pos + 1

    return (text[start:i], i)


def _parse_block_body(body: str) -> Optional[Dict]:
    """
    조건문/case문 내부의 action body를 파싱.
    goal block이면 goal로 파싱, 아니면 일반 step으로 파싱.
    """
    body = body.strip()
    if not body:
        return None

    # goal block 시도
    goal = _parse_goal_block(body)
    if goal is not None:
        return goal

    # if/else 시도
    condition = _parse_if_else(body)
    if condition is not None:
        return condition

    # case 시도
    case = _parse_case(body)
    if case is not None:
        return case

    # 일반 step 시도 (parse 는 지연 import — 본체와의 재귀 순환을 로드 시점에서 차단)
    try:
        from ibl_parser import parse
        steps = parse(body)
        if len(steps) == 1:
            return steps[0]
        return steps
    except IBLSyntaxError:
        return None


def _extract_bracket_raw(text: str, start: int,
                         open_ch: str, close_ch: str) -> Tuple[Optional[str], int]:
    """
    text[start] 위치의 여는 괄호부터 닫는 괄호까지 내용 추출 (문자열 리터럴 인식)

    Returns:
        (내부 내용 문자열, 닫는 괄호 위치) 또는 (None, -1)
    """
    if start >= len(text) or text[start] != open_ch:
        return (None, -1)

    depth = 0
    in_string = False
    string_char = None
    i = start

    while i < len(text):
        ch = text[i]
        if not in_string:
            if ch == '"' or ch == "'":
                in_string = True
                string_char = ch
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    return (text[start + 1:i], i)
        else:
            if ch == '\\' and i + 1 < len(text):
                i += 1
            elif ch == string_char:
                in_string = False
        i += 1

    return (None, -1)


def parse_range_expression(expr: str) -> Optional[Dict]:
    """
    범위 표현식 파싱 (case문에서 사용)

    지원 형식:
        "> 20%"  → {"op": "gt", "value": 20.0, "unit": "%"}
        ">= 100" → {"op": "gte", "value": 100.0, "unit": ""}
        "< 10%"  → {"op": "lt", "value": 10.0, "unit": "%"}
        "<= 50"  → {"op": "lte", "value": 50.0, "unit": ""}
        "== 0"   → {"op": "eq", "value": 0.0, "unit": ""}
        "10~20%" → {"op": "range", "min": 10.0, "max": 20.0, "unit": "%"}

    Returns:
        범위 dict 또는 None (범위 표현식이 아님)
    """
    expr = expr.strip()

    for pattern, op_name in _RANGE_PATTERNS:
        m = pattern.match(expr)
        if m:
            if op_name == 'range':
                return {
                    "op": "range",
                    "min": float(m.group(1)),
                    "max": float(m.group(2)),
                    "unit": m.group(3)
                }
            else:
                return {
                    "op": op_name,
                    "value": float(m.group(1)),
                    "unit": m.group(2)
                }

    return None


# === 내부 구현 ===

# 단일 명령 패턴: [node:action]{params}
# - [node:action] 필수
# - {params} 는 regex가 아닌 _extract_bracket으로 추출
# - (target)은 감지하여 에러 메시지 제공 (폐지됨)
