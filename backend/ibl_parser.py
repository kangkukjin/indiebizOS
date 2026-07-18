"""
ibl_parser.py - IBL 텍스트 파서

IBL 코드 텍스트를 파싱하여 실행 가능한 step 리스트로 변환합니다.

문법:
    # 단일 명령 — 모든 값은 named parameter
    [node:action]{key: "value"}

    # 파이프라인 (>> 로 연결, 순차 실행)
    [sense:web_search]{query: "AI 뉴스"} >> [self:file]{path: "결과.md"}

    # 병렬 실행 (& 로 연결, 동시 실행)
    [sense:web_search]{query: "AI"} & [sense:search_gnews]{query: "부동산"}

    # Fallback (?? 로 연결, 실패 시 대체)
    [sense:web_search]{query: "main"} ?? [sense:crawl]{url: "backup"}

    # 멀티라인 파이프라인
    [sense:web_search]{query: "근로기준법"}
      >> [self:file]{path: "법률검색.md"}
      >> [others:channel_send]{channel_type: "telegram", to: "me"}

    # 변수 바인딩
    $result = [sense:web_search]{query: "AI 뉴스"}
    [others:channel_send]{channel_type: "telegram", body: "$result"}

    # (target) 문법은 폐지됨 — 사용 시 IBLSyntaxError 발생

    # Phase 26: Goal Block
    [goal: "목표 이름"]{
        success_condition: "조건",
        max_rounds: 100,
        max_cost: 5.0,
        every: "매일 08:00",
        deadline: "2026-12-31"
    }

    # Phase 26: 조건문 (if/else)
    [if: sense:kospi < 2400]{
        [goal: "방어적 재편"]{max_rounds: 10}
    } [else]{
        [goal: "성장주 모니터링"]{max_rounds: 30}
    }

    # Phase 26: 케이스문 (case)
    [case: sense:market_status]{
        "상승장": [goal: "매수"]{max_rounds: 20},
        "하락장": [goal: "손절"]{max_rounds: 10},
        default: [goal: "관망"]{max_rounds: 5}
    }

사용법:
    from ibl_parser import parse, parse_step

    # 파이프라인 파싱
    steps = parse('[sense:web_search]{query: "AI"} >> [self:file]{path: "out.md"}')

    # 단일 명령 파싱
    step = parse_step('[sense:web_search]{query: "임대차"}')
    # → {"_node": "sense", "action": "web_search", "params": {"query": "임대차"}}
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
        Phase 26: goal block, if/else, case도 지원.

    Raises:
        IBLSyntaxError: 문법 오류
    """
    if not code or not code.strip():
        raise IBLSyntaxError("빈 코드입니다.")

    stripped = code.strip()

    # Phase 26: Goal Block 감지
    goal = _parse_goal_block(stripped)
    if goal is not None:
        return [goal]

    # Phase 26: if/else 조건문 감지
    condition = _parse_if_else(stripped)
    if condition is not None:
        return [condition]

    # Phase 26: case문 감지
    case = _parse_case(stripped)
    if case is not None:
        return [case]

    # 기존 파이프라인 파싱
    # 전처리: 주석 제거, 줄 정규화
    lines = _preprocess(code)
    if not lines:
        raise IBLSyntaxError("파싱 가능한 코드가 없습니다.")

    # 변수 바인딩과 명령문 분리
    statements, variables = _extract_statements(lines)

    all_steps = []
    for _stmt_idx, stmt in enumerate(statements):
        # 파이프 문법 설탕(| where:/sort:/take:/select:/dedup:)을 >> [table:동사] 로 desugar.
        # 의미는 engines 변환자에 이미 있고, 이건 빈도 높은 단항 변환자의 짧은 문법 표면.
        stmt = _desugar_pipe_sugar(stmt)
        # >> 로 파이프라인 분리
        segments = _split_pipeline(stmt)  # [(text, operator), ...]
        for idx, (seg_text, operator) in enumerate(segments):
            # 각 세그먼트 내에서 & 또는 ?? 연산자 처리
            parsed = _parse_group(seg_text.strip())
            if parsed is None:
                raise IBLSyntaxError(f"파싱 실패: {seg_text.strip()}")
            # 변수 참조 치환
            parsed = _resolve_variables(parsed, variables)
            # 문장 경계 표식 — 문장들은 한 리스트로 평탄화되므로, 실행기가 "여기부터 새 문장"을
            # 알 방법이 이 표식뿐이다. 경계에서는 앞 문장의 실패가 전파되지 않고
            # _prev_result 도 넘어가지 않는다(독립이란 뜻이므로). 첫 step 에만 붙인다.
            if _stmt_idx > 0 and idx == 0:
                parsed["_seq_boundary"] = True
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

# IBLSyntaxError·값 추출기는 ibl_parser_values, 제어 블록 파서는 ibl_parser_blocks 로
# 이동 (2026-07-18 모듈화 — 1500줄 규칙). 재수출로 기존 import 경로 전부 불변.
from ibl_parser_values import (  # noqa: E402,F401
    IBLSyntaxError,
    _parse_params,
    _parse_relaxed_params,
    _extract_value,
    _extract_string,
    _extract_bracket,
    _extract_number,
    _extract_unquoted,
)
from ibl_parser_blocks import (  # noqa: E402,F401
    _parse_goal_block,
    _parse_if_else,
    _parse_case,
    _extract_action_at,
    _parse_block_body,
    _extract_bracket_raw,
    parse_range_expression,
)


_STEP_PATTERN = re.compile(
    r'\[(\w+):(\w+)\]'           # [node:action]
    r'(?:\s*\(([^)]*)\))?',      # (target) - 감지용 (사용 시 에러)
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

    # `;` = 한 줄 안의 줄바꿈. 독립 문장을 한 줄에 늘어놓는 순차 연산자로,
    # 여기서 개행과 **같은 것**으로 접는다(실행기는 둘을 구분하지 않는다).
    # 문자열·중괄호 안의 `;` 는 _split_by_operator 가 알아서 무시한다.
    lines = [s for line in lines for s in (_split_by_operator(line, ';') or [line])]

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


def _split_pipeline(text: str) -> List[tuple]:
    """
    >> 연산자로 파이프라인 분리

    '[a:b]{} >> [c:d]{}'  → [('[a:b]{}', '>>'), ('[c:d]{}', None)]
    '[a:b]{} >> [c:d]{} >> [e:f]{}' → [('[a:b]{}', '>>'), ('[c:d]{}', '>>'), ('[e:f]{}', None)]

    각 튜플: (세그먼트 텍스트, 이 세그먼트 뒤에 오는 연산자)
    중괄호 {} 내부의 >>는 무시 (JSON 문자열 안)
    """
    segments = []  # [(text, operator)]
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
            # >> 발견 (중괄호 밖) — 기계적 파이프
            seg = ''.join(current).strip()
            if seg:
                segments.append((seg, '>>'))
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

    # 마지막 세그먼트 (뒤에 연산자 없음)
    seg = ''.join(current).strip()
    if seg:
        segments.append((seg, None))

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


# ───────────────────── 파이프 문법 설탕 (단항 변환자 desugar) ─────────────────────
# [node:action]{...} | where: X | sort: Y desc | take: N | select: a,b | dedup: f
#   → ... >> [table:filter]{where:X} >> [table:sort]{by:"Y",desc:true} >> ...
# 닫힌 계급(보편·고빈도) 단항 변환자에만 문법 표면을 준다. 이항(join/union/merge)·
# 구조적(groupby)은 동사 형태 유지. 의미는 table 동사가 정본 — 이건 desugar 표면뿐.
#
# ★교재 안내 은퇴(2026-06-17): `|` 단축은 프롬프트 교재(12_ibl_only.md)·의식 프롬프트에서
# 제거됨 — 실사용 0(합성/증류 코퍼스·저장 워크플로우 모두), 연상 예시가 100% `>>`라 모델이
# 안 썼고, `>>`와 기능 동일한 설탕이라 능력 손실 없음. desugar 는 **관대한 입력 호환**으로만
# 유지(stray `|` 를 에러 대신 >> 로 흡수, 프롬프트 비용 0). 새 코드/문서는 `>> [table:동사]` 사용.
_PIPE_SUGAR = {
    "where": "filter", "filter": "filter",
    "sort": "sort", "orderby": "sort", "order_by": "sort",
    "take": "take", "limit": "take", "head": "take", "top": "take",
    "select": "select", "project": "select", "columns": "select",
    "dedup": "dedup", "unique": "dedup", "distinct": "dedup",
}


def _pipe_looks_numeric(s: str) -> bool:
    try:
        float(str(s).replace(",", "").strip())
        return True
    except Exception:
        return False


def _pipe_block(verb: str, val: str) -> str:
    """파이프 op 값 → 해당 table 변환자 블록 문자열.

    ★결합 명시(2026-07-03): 아래 [table:filter/sort/take/select/dedup] 하드코딩은
    파이프 단축문법(`|where` 등)을 table 노드 어휘로 펼치는 레거시 흡수용 *코드젠*이다.
    table 변환자의 액션명/파라미터 키(where·by·n·columns)가 바뀌면 여기도 함께 바꿔야
    한다. 어휘 자체는 정의처(패키지 ibl_actions.yaml)가 소유하고, 이 함수는 그 어휘를
    생성하는 문법 설탕이라 파라미터 별칭 데이터화(aliases: 블록) 대상에서 의도적으로 제외."""
    val = (val or "").strip()
    if verb == "filter":
        # where 값은 복합(문자열/{field,op,value})일 수 있어 대체로 그대로.
        # 단, 따옴표·중괄호·대괄호·숫자가 아닌 맨 단어는 substring 문자열로 자동 인용.
        v = val
        if v and v[0] not in "\"'{[" and not _pipe_looks_numeric(v):
            v = '"%s"' % v
        return '[table:filter]{where: %s}' % (v or '""')
    if verb == "sort":
        toks = val.split()
        field = toks[0].strip('"\'') if toks else ""
        desc = len(toks) > 1 and toks[1].lower() in ("desc", "내림", "내림차순")
        s = '[table:sort]{by: "%s"' % field
        if desc:
            s += ", desc: true"
        return s + "}"
    if verb == "take":
        n = val if _pipe_looks_numeric(val) else "10"
        return '[table:take]{n: %s}' % n
    if verb == "select":
        cols = [c.strip().strip('"\'') for c in val.split(",") if c.strip()]
        arr = ", ".join('"%s"' % c for c in cols)
        return '[table:select]{columns: [%s]}' % arr
    if verb == "dedup":
        by = val.strip('"\'')
        return '[table:dedup]{by: "%s"}' % by if by else '[table:dedup]{}'
    return ""


def _desugar_pipe_sugar(text: str) -> str:
    """| op: val 체인을 >> [table:동사]{...} 로 펼친다. 최상위 | 없으면 그대로."""
    if "|" not in text:
        return text
    parts = _split_by_operator(text, "|")  # { } · 문자열 깊이 인식
    if len(parts) <= 1:
        return text
    out = [parts[0].strip()]
    for seg in parts[1:]:
        seg = seg.strip()
        if not seg:
            continue
        # 설탕 op 값 뒤에 >> 가 오면(예: | take: 5 >> [table:document]{}) 그 뒤는
        # 일반 파이프라인 연속이다 — 분리해 그대로 잇는다(설탕→렌더 혼용 허용).
        tail = ""
        ss = _split_by_operator(seg, ">>")
        if len(ss) > 1:
            seg = ss[0].strip()
            tail = " >> " + " >> ".join(s.strip() for s in ss[1:])
        if ":" in seg:
            kw, val = seg.split(":", 1)
        else:
            kw, val = seg, ""
        kw = kw.strip().lower()
        verb = _PIPE_SUGAR.get(kw)
        if not verb:
            raise IBLSyntaxError(
                f"알 수 없는 파이프 연산자 '| {kw}'. 지원: where/sort/take/select/dedup. "
                "예: [sense:search_ddg]{query: \"X\"} | where: \"전세\" | sort: price desc | take: 5"
            )
        out.append(">> " + _pipe_block(verb, val) + tail)
    return " ".join(out)


# Deprecated action-name aliases → canonical (node, action) [+ optional injected params].
#
# 2026-06-03 #24 레거시 별칭 완전 은퇴: 모든 방출/교재/운영/코퍼스 표면을 캐노니컬
# 어휘로 마이그레이션한 뒤(코퍼스+해마 재색인 포함), 159개 별칭을 전부 제거했다.
# 시스템이 단 하나의 어휘만 말하도록 — 옛 이름(price·gallery·ask_sync·slide 등)은
# 이제 "노드에 X 액션 없음" 에러로 명시적으로 실패한다(조용한 번역 → 명시적 실패).
# 폐지 매핑 이력은 changelog 및 backend/migrate_alias_retirement.py 참조.
#
# 이 맵은 전환기 별칭 메커니즘으로 남겨둔다(필요 시 일시적으로 채웠다 은퇴). 기본은 비움.
_ACTION_NAME_ALIASES: Dict[Tuple[str, str], Tuple] = {}


def _parse_step(text: str) -> Optional[Dict]:
    """
    단일 IBL 명령 파싱

    [node:action]{params}

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

    canonical = _ACTION_NAME_ALIASES.get((node, action))
    injected_params: dict = {}
    if canonical is not None:
        if len(canonical) >= 3:
            node, action, injected_params = canonical[0], canonical[1], dict(canonical[2] or {})
        else:
            node, action = canonical[0], canonical[1]

    # (target) 구문 감지 → 에러 (폐지됨)
    if target_raw is not None:
        stripped = target_raw.strip().strip('"').strip("'")
        if stripped:
            raise IBLSyntaxError(
                f"(target) 문법은 폐지되었습니다. params를 사용하세요.\n"
                f"  잘못된 코드: [{node}:{action}](\"{stripped}\")\n"
                f"  올바른 코드: [{node}:{action}]{{key: \"{stripped}\"}}\n"
                f"  (key는 액션에 맞는 파라미터 이름으로 바꾸세요)"
            )
        # 빈 괄호 ()는 허용 (파라미터 없는 호출)

    # params 처리: regex 이후 남은 텍스트에서 { 를 찾아 _extract_bracket으로 추출
    params = {}
    remaining = text[m.end():].strip()
    tail = remaining
    if remaining.startswith('{'):
        extracted, _bend = _extract_bracket(remaining, 0, '{', '}')
        if isinstance(extracted, dict):
            params = extracted
        elif isinstance(extracted, str):
            params = _parse_params(extracted)
        tail = remaining[_bend:].strip() if isinstance(_bend, int) and _bend > 0 else ""

    # 노드 주소지정 @별칭 (다중 노드): [node:action]{...}@폰2 → target_node="폰2".
    # params 블록 밖(tail)에서만 찾아 파라미터 값 내 @(이메일 등)와 충돌 없음. 한글 별칭 허용.
    target_node = None
    if tail.startswith('@'):
        mt = re.match(r'@([^\s\(\)\{\}\[\]&|>?@]+)', tail)
        if mt:
            target_node = mt.group(1)

    # 별칭 정규화로 주입된 파라미터를 병합 (사용자 명시값 우선)
    if injected_params:
        for k, v in injected_params.items():
            if k not in params:
                params[k] = v

    step = {
        "_node": node,
        "action": action,
        "target": "",
        "params": params,
    }
    if target_node:
        step["target_node"] = target_node
    return step



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
    params = step.get("params", {})

    result = f"[{node}:{action}]"
    # target은 더 이상 출력하지 않음 (params에 병합됨)
    if params:
        result += json.dumps(params, ensure_ascii=False)

    return result


def format_pipeline(steps: list) -> str:
    """step 리스트를 IBL 파이프라인 텍스트로 포맷팅"""
    if not steps:
        return ""
    if len(steps) == 1:
        return format_step(steps[0])

    parts = [format_step(steps[0])]
    for i, step in enumerate(steps[1:], 1):
        parts.append(f"  >> {format_step(step)}")

    return "\n".join(parts)


# === 테스트 ===

if __name__ == "__main__":
    print("=== IBL Parser Tests ===\n")

    # 1. 단일 명령 (named params)
    s1 = parse_step('[limbs:call]{tool: "search_laws", query: "근로기준법"}')
    print(f"1. 단일: {s1}")
    assert s1["_node"] == "limbs"
    assert s1["action"] == "call"
    assert s1["params"]["tool"] == "search_laws"
    assert s1["params"]["query"] == "근로기준법"

    # 2. params 없는 명령
    s2 = parse_step('[limbs:list]')
    print(f"2. params 없음: {s2}")
    assert s2["_node"] == "limbs"
    assert s2["action"] == "list"
    assert s2["target"] == ""
    assert s2["params"] == {}

    # 3. 단일 param
    s3 = parse_step('[sense:web_search]{query: "AI 뉴스"}')
    print(f"3. 단일 param: {s3}")
    assert s3["params"]["query"] == "AI 뉴스"
    assert s3["target"] == ""

    # 4. 파이프라인
    p1 = parse('[sense:web_search]{query: "AI"} >> [self:file]{path: "결과.md"}')
    print(f"4. 파이프라인: {len(p1)} steps")
    assert len(p1) == 2
    assert p1[0]["_node"] == "sense"
    assert p1[1]["_node"] == "self"

    # 5. 멀티라인 파이프라인
    code5 = """
    [limbs:call]{tool: "search_laws", query: "임대차"}
      >> [self:file]{path: "법률.md"}
      >> [others:channel_send]{channel_type: "telegram", to: "me"}
    """
    p2 = parse(code5)
    print(f"5. 멀티라인: {len(p2)} steps")
    assert len(p2) == 3
    assert p2[2]["params"]["to"] == "me"

    # 6. 느슨한 params (따옴표 없는 키)
    s6 = parse_step('[limbs:call]{tool: "search_laws", query: "임대차", page: 1}')
    print(f"6. 느슨한 params: {s6}")
    assert s6["params"]["query"] == "임대차"
    assert s6["params"]["page"] == 1

    # 7. 주석 + 여러 명령문
    code7 = """
    # 첫 번째 검색
    [sense:web_search]{query: "뉴스"}
    # 두 번째 검색
    [limbs:call]{tool: "search_laws", query: "민법"}
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

    # === 병렬 & Fallback 테스트 ===
    print("\n--- 병렬 & Fallback Tests ---")

    # 11. 병렬 실행 (&)
    p11 = parse('[sense:web_search]{query: "AI"} & [sense:search_gnews]{query: "부동산"}')
    print(f"11. 병렬: {p11}")
    assert len(p11) == 1
    assert p11[0]["_parallel"] == True
    assert len(p11[0]["branches"]) == 2
    assert p11[0]["branches"][0]["_node"] == "sense"
    assert p11[0]["branches"][0]["action"] == "web_search"
    assert p11[0]["branches"][1]["action"] == "search_gnews"

    # 12. 3개 병렬
    p12 = parse('[sense:web_search]{query: "A"} & [sense:web_search]{query: "B"} & [sense:web_search]{query: "C"}')
    print(f"12. 3개 병렬: branches={len(p12[0]['branches'])}")
    assert p12[0]["_parallel"] == True
    assert len(p12[0]["branches"]) == 3

    # 13. Fallback (??)
    p13 = parse('[limbs:call]{tool: "primary"} ?? [limbs:call]{tool: "backup"}')
    print(f"13. Fallback: {p13}")
    assert len(p13) == 1
    assert "_fallback_chain" in p13[0]
    assert len(p13[0]["_fallback_chain"]) == 2

    # 14. 3개 Fallback 체인
    p14 = parse('[limbs:call]{tool: "a"} ?? [limbs:call]{tool: "b"} ?? [limbs:call]{tool: "c"}')
    print(f"14. 3개 Fallback: chain={len(p14[0]['_fallback_chain'])}")
    assert len(p14[0]["_fallback_chain"]) == 3

    # 15. 병렬 >> 순차 혼합
    p15 = parse('[sense:web_search]{query: "AI"} & [sense:search_gnews]{query: "부동산"} >> [self:file]{path: "결과.md"}')
    print(f"15. 병렬+순차: {len(p15)} steps")
    assert len(p15) == 2
    assert p15[0]["_parallel"] == True
    assert p15[1]["_node"] == "self"

    # 16. Fallback >> 순차 혼합
    p16 = parse('[limbs:call]{tool: "main"} ?? [limbs:call]{tool: "backup"} >> [others:channel_send]{channel_type: "telegram"}')
    print(f"16. Fallback+순차: {len(p16)} steps")
    assert len(p16) == 2
    assert "_fallback_chain" in p16[0]
    assert p16[1]["_node"] == "others"

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

    # === (target) 폐지 확인 테스트 ===
    print("\n--- (target) 폐지 확인 Tests ---")

    # 20. (target) 사용 시 에러 발생
    try:
        parse_step('[sense:web_search]("AI 뉴스")')
        assert False, "IBLSyntaxError가 발생해야 함"
    except IBLSyntaxError as e:
        print(f"20. target 에러: {e}")
        assert "폐지" in str(e)

    # 21. 빈 괄호 ()는 허용
    s21 = parse_step('[self:open]()')
    print(f"21. 빈 괄호: {s21}")
    assert s21["_node"] == "self"
    assert s21["target"] == ""

    # 22. 여러 params
    s22 = parse_step('[sense:kr_investor]{market: "STK", start_date: "2026-02-01", end_date: "2026-02-26"}')
    print(f"22. 여러 params: {s22}")
    assert s22["params"]["market"] == "STK"
    assert s22["params"]["start_date"] == "2026-02-01"
    assert s22["params"]["end_date"] == "2026-02-26"

    # 23. 변수 바인딩
    code23 = """
    $result = [sense:web_search]{query: "AI 뉴스"}
    [others:channel_send]{channel_type: "telegram", body: "$result"}
    """
    p23 = parse(code23)
    print(f"23. 변수 바인딩: {len(p23)} steps")
    assert len(p23) == 2

    print("\n=== 모든 테스트 통과 ===")
