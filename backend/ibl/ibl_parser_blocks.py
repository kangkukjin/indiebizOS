"""IBL 파서 제어 블록 층 (2026-07-18 모듈화 — 1500줄 규칙)

ibl_parser.py 에서 verbatim 이동: goal/if·else/case 블록 파서 + 범위 표현식.
★재귀 하강의 본체 parse 는 import 하지 않는다 — ibl_parser 가 로드 끝에
register_parse() 로 주입(의존 역전). 이 모듈은 ibl_parser 를 모른다.
★파이프 설탕(_pipe_block)은 본체 잔류 — 표준-코어 가드가 ibl_parser.py 경로를 스캔.
"""
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from ibl_parser_values import IBLSyntaxError, _parse_params

# 본체 parse 주입 슬롯 — ibl_parser 가 자기 정의 직후 등록한다.
_PARSE: Optional[Callable[[str], List[Dict]]] = None


def register_parse(fn: Callable[[str], List[Dict]]) -> None:
    """재귀 하강용 본체 parse 를 주입 (ibl_parser 로드 말미에 1회)."""
    global _PARSE
    _PARSE = fn


# === Phase 26: Goal/Condition/Case 파서 ===

# Goal Block 패턴: [goal: "이름"]{...}
# 이름은 따옴표 유무 모두 허용 — [if:]/[case:] 의 조건·소스가 무따옴표라, goal 만
# 따옴표를 강제하면 무따옴표 goal 이 블록 감지를 그냥 지나쳐 무의미한 '파싱 실패'가 된다.
_GOAL_PATTERN = re.compile(
    r'^\s*\[goal:\s*(?:"([^"]+)"|([^\]"]+?))\s*\]\s*\{',
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

# 블록 헤더 접두 — 헤더 *본문*은 정규식이 아니라 깊이 인식 스캔(_block_header)으로 읽는다.
# (2026-08-22 M2: 조건식에 `[table:brief]{…} == "yes"` 같은 대괄호 술어가 오면 비탐욕 정규식
#  `\[if:\s*(.+?)\]\s*\{` 가 첫 `]{` 에서 끊겨 블록 전체가 '해석되지 않은 텍스트'로 죽었다.)
_IF_PREFIX = re.compile(r'^\s*\[if:\s*')
_ELSE_IF_PREFIX = re.compile(r'^\s*\[else\s+if:\s*')


def _block_header(text: str, prefix: "re.Pattern") -> Optional[Tuple[str, int]]:
    """`[키워드: 헤더]{` 를 깊이 인식으로 읽어 (헤더 본문, '{' 위치) — 모양이 아니면 None.

    헤더 안의 `[`·`{`·문자열은 깊이로 건너뛰고, 깊이 0 의 첫 `]` 가 헤더의 끝이다."""
    m = prefix.match(text)
    if not m:
        return None
    start = m.end()
    depth = 0
    in_s = False
    q = ''
    i, n = start, len(text)
    while i < n:
        c = text[i]
        if in_s:
            if c == '\\':
                i += 2
                continue
            if c == q:
                in_s = False
        elif c in '"\'':
            in_s = True
            q = c
        elif c in '[{':
            depth += 1
        elif c == '}':
            depth -= 1
        elif c == ']':
            if depth == 0:
                j = i + 1
                while j < n and text[j] in ' \t\r\n':
                    j += 1
                if j < n and text[j] == '{':
                    return text[start:i].strip(), j
                return None
            depth -= 1
        i += 1
    return None

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


def _find_top_level_key(body: str, key: str) -> Optional[Tuple[int, int]]:
    """중괄호/대괄호/문자열 *밖*(깊이 0)에서 `key :` 를 찾아 (키 시작, 값 시작) 반환.

    정규식으로 찾으면 문자열 값 속 같은 글자(예: success_condition: "strategy: [x]")에
    오탐한다 — 파라미터 경계는 깊이·문자열 상태를 알아야 정확하다."""
    depth = 0
    in_s = False
    q = ''
    i, n = 0, len(body)
    while i < n:
        c = body[i]
        if in_s:
            if c == '\\':
                i += 2
                continue
            if c == q:
                in_s = False
        elif c in '"\'':
            in_s = True
            q = c
        elif c in '{[':
            depth += 1
        elif c in '}]':
            depth -= 1
        elif depth == 0 and body.startswith(key, i) and (
                i == 0 or not (body[i - 1].isalnum() or body[i - 1] == '_')):
            j = i + len(key)
            while j < n and body[j] in ' \t\n\r':
                j += 1
            if j < n and body[j] == ':':
                j += 1
                while j < n and body[j] in ' \t\n\r':
                    j += 1
                return (i, j)
        i += 1
    return None


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

    goal_name = m.group(1) or (m.group(2) or "").strip()

    # 정규식이 매칭한 '{' 위치 사용 (goal_name 안의 '{'에 속지 않도록)
    brace_start = m.end() - 1
    body, end_pos = _extract_bracket_raw(code, brace_start, '{', '}')
    if body is None:
        raise IBLSyntaxError(f"Goal block 중괄호가 닫히지 않았습니다: {goal_name}")

    leftover = code[end_pos + 1:].strip()
    if leftover:
        # 조용히 버리면 블록 뒤 문장이 침묵 소실된다 — 문장 분리를 명시 요구.
        raise IBLSyntaxError(
            f"Goal 블록 뒤에 해석되지 않은 텍스트가 있습니다: '{leftover[:60]}' — "
            "블록과 다른 문장은 줄(또는 ;)로 분리하세요.")

    # strategy 값이 인라인 블록([if:]/[case:]/액션)이면 param 파서에 넣기 *전에*
    # 통째로 도려낸다 — 값 파서는 [ ] 대괄호에서 멈춰 '[if: ...]' 헤더만 남기고
    # {본문}을 침묵 소실시킨다(2026-08-16 실측: goal 속 strategy 는 이 경로로
    # 한 번도 온전히 파싱된 적이 없었다).
    strategy_block = None
    _found = _find_top_level_key(body, 'strategy')
    if _found and _found[1] < len(body) and body[_found[1]] == '[':
        _key_start, _val_start = _found
        action_text, _pos = _extract_action_at(body, _val_start)
        if action_text:
            # if/else 체인은 괄호 그룹 여러 개 — [else...]가 이어지는 동안 계속 삼킨다
            while True:
                _j = _pos
                while _j < len(body) and body[_j] in ' \t\n\r':
                    _j += 1
                if body.startswith('[else', _j):
                    _nxt, _pos2 = _extract_action_at(body, _j)
                    if not _nxt or _pos2 <= _j:
                        break
                    _pos = _pos2
                else:
                    break
            strategy_block = body[_val_start:_pos].strip()
            _before = body[:_key_start].rstrip()
            _after = body[_pos:].lstrip()
            if _before.endswith(','):
                _before = _before[:-1].rstrip()
            elif _after.startswith(','):
                _after = _after[1:].lstrip()
            body = (_before + (', ' if _before and _after else ' ') + _after).strip()

    # params 파싱
    params = _parse_params('{' + body + '}')

    if strategy_block is not None:
        parsed_strategy = _parse_block_body(strategy_block)
        if parsed_strategy is None:
            # str 로 조용히 남기면 소실이 재발한다 — 정직 거절.
            raise IBLSyntaxError(
                f"Goal '{goal_name}' 의 strategy 블록을 해석할 수 없습니다: "
                f"{strategy_block[:80]}")
        params['strategy'] = parsed_strategy

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
    hdr = _block_header(code, _IF_PREFIX)
    if hdr is None:
        if _IF_PREFIX.match(code):
            raise IBLSyntaxError("if 블록 헤더가 닫히지 않았습니다 — 형태: [if: 조건]{...}")
        return None

    branches = []
    pos = 0

    # 첫 번째 if — 헤더는 깊이 인식으로 읽었다(조건 안의 `[…]{…}`·'{' 에 속지 않음)
    condition_text, brace_start = hdr
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
        m_elif = _block_header(remaining, _ELSE_IF_PREFIX)
        if m_elif:
            cond, brace_start = m_elif
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

    if remaining:
        # 조용히 버리면 체인 뒤 문장이 침묵 소실된다 — 문장 분리를 명시 요구.
        # F16-1 (2026-08-20 상상훈련 16회차): 잔여가 [else 로 시작하면 진짜 원인은 십중팔구
        # 분기 몸 중괄호 누락([else] [A] 형태) — "줄로 분리" 처방은 오도라 정답 형태를 지목.
        if remaining.startswith('[else'):
            raise IBLSyntaxError(
                f"if/else 체인 뒤에 해석되지 않은 텍스트가 있습니다: '{remaining[:60]}' — "
                "분기 몸은 중괄호로 감쌉니다: [if: 조건]{[액션]} [else]{[액션]}. "
                "(중괄호 없는 [else] [액션] 형태는 파싱되지 않습니다.)")
        raise IBLSyntaxError(
            f"if/else 체인 뒤에 해석되지 않은 텍스트가 있습니다: '{remaining[:60]}' — "
            "블록과 다른 문장은 줄(또는 ;)로 분리하세요.")

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

    leftover = code[end_pos + 1:].strip()
    if leftover:
        # 조용히 버리면 블록 뒤 문장이 침묵 소실된다 — 문장 분리를 명시 요구.
        raise IBLSyntaxError(
            f"case 블록 뒤에 해석되지 않은 텍스트가 있습니다: '{leftover[:60]}' — "
            "블록과 다른 문장은 줄(또는 ;)로 분리하세요.")

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

    # try / repeat 시도 (프로그램급 IBL M3·M4)
    if body.startswith('[try]'):
        return _parse_try_block(body)
    if body.startswith('[repeat:'):
        return _parse_repeat_block(body)

    # 일반 step 시도 (parse 는 주입 슬롯 — register_parse 로 의존 역전)
    if _PARSE is None:
        raise RuntimeError(
            "ibl_parser_blocks: parse 미주입 — ibl_parser 를 먼저 import 해야 한다")
    try:
        steps = _PARSE(body)
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


# === 프로그램급 IBL M3·M4 — try/catch/finally · repeat (2026-08-22) ===
# 설계 정본: docs/IBL_PROGRAM_GRADE_DESIGN.md §2.4·§2.2. 헤더는 전부 깊이 인식 스캔(_block_header).
_TRY_PREFIX = re.compile(r'^\s*\[try\]\s*\{')
_CATCH_PREFIX = re.compile(r'^\s*\[catch\]\s*\{')
_FINALLY_PREFIX = re.compile(r'^\s*\[finally\]\s*\{')
_REPEAT_PREFIX = re.compile(r'^\s*\[repeat:\s*')

# 본체의 변수-인식 파서 주입 슬롯 — repeat 의 until 조건이 몸통 안의 `$x = …` 할당을 읽어야 한다.
_PARSE_VARS: Optional[Callable[[str], Tuple[List[Dict], Dict[str, int]]]] = None


def register_parse_vars(fn) -> None:
    global _PARSE_VARS
    _PARSE_VARS = fn


def _take_brace_body(text: str, prefix: "re.Pattern") -> Optional[Tuple[Any, str]]:
    """`[키워드]{…}` 를 먹고 (파싱된 몸, 나머지 텍스트). 모양이 아니면 None."""
    m = prefix.match(text)
    if not m:
        return None
    brace = m.end() - 1
    body, end = _extract_bracket_raw(text, brace, '{', '}')
    if body is None:
        raise IBLSyntaxError(f"{text[:12].strip()} 블록 중괄호가 닫히지 않았습니다.")
    parsed = _parse_block_body(body.strip())
    if parsed is None:
        label = text.lstrip().split(']', 1)[0].lstrip('[') or "블록"
        raise IBLSyntaxError(
            f"{label} 블록은 있지만 몸을 해석하지 못했습니다: {body.strip()[:60]!r}. "
            "몸에는 IBL 문장 또는 지원되는 한 줄 식을 쓰세요 "
            "(목록·사전 리터럴을 식에 직접 할당하는 문법은 지원하지 않습니다)."
        )
    return parsed, text[end + 1:].strip()


def _parse_try_block(code: str) -> Optional[Dict]:
    """[try]{…} [catch]{…} [finally]{…} → {"_try": True, "body", "catch", "finally"}.

    catch 안에서 `$error`(.step/.action/.error/.summary) 를 쓸 수 있다 — 실행기가 바인딩.
    catch·finally 는 선택이지만 둘 다 없으면 try 는 무의미하므로 명시 에러.
    """
    got = _take_brace_body(code, _TRY_PREFIX)
    if got is None:
        return None
    body, rest = got
    if body is None:
        raise IBLSyntaxError("try 몸이 비어 있습니다.")
    out: Dict[str, Any] = {"_try": True, "body": body, "catch": None, "finally": None}
    while rest:
        g = _take_brace_body(rest, _CATCH_PREFIX)
        if g is not None:
            if out["catch"] is not None:
                raise IBLSyntaxError("catch 블록이 두 번 나왔습니다.")
            out["catch"], rest = g
            continue
        g = _take_brace_body(rest, _FINALLY_PREFIX)
        if g is not None:
            if out["finally"] is not None:
                raise IBLSyntaxError("finally 블록이 두 번 나왔습니다.")
            out["finally"], rest = g
            continue
        raise IBLSyntaxError(
            f"try 블록 뒤에 해석되지 않은 텍스트가 있습니다: '{rest[:60]}' — "
            "형태: [try]{…} [catch]{…} [finally]{…} (블록과 다른 문장은 줄로 분리).")
    if out["catch"] is None and out["finally"] is None:
        raise IBLSyntaxError("try 에는 [catch]{…} 또는 [finally]{…} 가 하나 이상 필요합니다.")
    return out


def _split_top_commas(text: str) -> List[str]:
    parts, cur, depth, in_s, q = [], [], 0, False, ''
    for c in text:
        if in_s:
            cur.append(c)
            if c == q:
                in_s = False
            continue
        if c in '"\'':
            in_s, q = True, c
        elif c in '{[(':
            depth += 1
        elif c in '}])':
            depth -= 1
        if c == ',' and depth == 0:
            parts.append(''.join(cur).strip()); cur = []
        else:
            cur.append(c)
    if ''.join(cur).strip():
        parts.append(''.join(cur).strip())
    return parts


def _parse_repeat_block(code: str) -> Optional[Dict]:
    """[repeat: N]{…} · [repeat: until 조건, max: 30, every: "10s", collect: true]{…} · [repeat: while 조건, max: N]{…}

    → {"_repeat": True, "mode": count|until|while, "count", "condition", "max", "every", "collect", "var", "body", "body_vars"}
    until 은 몸통 실행 *뒤* 평가(몸통이 할당한 $변수를 읽는다), while 은 *앞* 평가(바깥 $변수).
    max 는 until/while 에 필수 — 상한 없는 루프 금지(헌법 원칙 5: 침묵 클램프 금지 → 상한은 신고된다).
    """
    hdr = _block_header(code, _REPEAT_PREFIX)
    if hdr is None:
        if _REPEAT_PREFIX.match(code):
            raise IBLSyntaxError("repeat 블록 헤더가 닫히지 않았습니다 — 형태: [repeat: until 조건, max: N]{...}")
        return None
    header, brace = hdr
    body_txt, end = _extract_bracket_raw(code, brace, '{', '}')
    if body_txt is None:
        raise IBLSyntaxError("repeat 블록 중괄호가 닫히지 않았습니다.")
    rest = code[end + 1:].strip()
    if rest:
        raise IBLSyntaxError(f"repeat 블록 뒤에 해석되지 않은 텍스트가 있습니다: '{rest[:60]}' — 줄로 분리하세요.")
    parts = _split_top_commas(header)
    if not parts:
        raise IBLSyntaxError("repeat 헤더가 비어 있습니다 — [repeat: 5] / [repeat: until 조건, max: N] / [repeat: while 조건, max: N]")
    head = parts[0]
    out: Dict[str, Any] = {"_repeat": True, "mode": None, "count": None, "condition": None,
                           "max": None, "every": None, "collect": False, "var": "i"}
    if re.fullmatch(r'\d+', head):
        out["mode"], out["count"] = "count", int(head)
    elif re.match(r'^until\s+', head):
        out["mode"], out["condition"] = "until", head[5:].strip()
    elif re.match(r'^while\s+', head):
        out["mode"], out["condition"] = "while", head[5:].strip()
    else:
        raise IBLSyntaxError(
            f"repeat 헤더 '{head[:40]}' 을 읽지 못했습니다 — 고정 횟수([repeat: 5]), "
            "until 조건([repeat: until $st.status == \"done\", max: 30, every: \"10s\"]), "
            "while 조건([repeat: while count($q) > 0, max: 100]) 중 하나여야 합니다.")
    for p in parts[1:]:
        km = re.match(r'^(\w+)\s*:\s*(.+)$', p, re.DOTALL)
        if not km:
            raise IBLSyntaxError(f"repeat 옵션 '{p[:40]}' 은 key: value 꼴이어야 합니다 (max/every/collect/as).")
        k, v = km.group(1), km.group(2).strip().strip('"\'')
        if k == "max":
            if not re.fullmatch(r'\d+', v):
                raise IBLSyntaxError("repeat max 는 정수여야 합니다.")
            out["max"] = int(v)
        elif k == "every":
            out["every"] = v
        elif k == "collect":
            out["collect"] = v.lower() in ("true", "1", "yes")
        elif k == "as":
            out["var"] = v.lstrip("$")
        else:
            raise IBLSyntaxError(f"repeat 가 모르는 옵션 '{k}' — max/every/collect/as 만.")
    if out["mode"] in ("until", "while") and out["max"] is None:
        raise IBLSyntaxError("repeat until/while 에는 max(반복 상한)가 필수입니다 — 상한 없는 루프는 금지.")
    if out["mode"] == "count" and out["max"] is None:
        out["max"] = out["count"]
    body_src = body_txt.strip()
    if not body_src:
        raise IBLSyntaxError("repeat 몸이 비어 있습니다.")
    if _PARSE_VARS is not None:
        steps, body_vars = _PARSE_VARS(body_src)
    else:
        steps, body_vars = _PARSE(body_src), {}
    out["body"] = steps
    out["body_vars"] = body_vars
    return out
