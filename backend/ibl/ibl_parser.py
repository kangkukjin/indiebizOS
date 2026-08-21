"""
ibl_parser.py - IBL 텍스트 파서

IBL 코드 텍스트를 파싱하여 실행 가능한 step 리스트로 변환합니다.

문법:
    # 단일 명령 — 모든 값은 named parameter
    [node:action]{key: "value"}

    # 파이프라인 (>> 로 연결, 순차 실행)
    [sense:web_search]{query: "AI 뉴스"} >> [self:file]{path: "결과.md"}

    # 병렬 실행 (& 로 연결, 동시 실행)
    [sense:web_search]{query: "AI"} & [sense:search]{source: "gnews", query: "부동산"}

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
    """IBL 코드 → step 리스트 (parse_with_vars 의 steps 만)."""
    return parse_with_vars(code)[0]


def parse_with_vars(code: str) -> Tuple[List[Dict], Dict[str, int]]:
    """
    IBL 코드를 파싱하여 실행 가능한 step 리스트로 변환 (+ $변수명→최종 step 인덱스 맵 — repeat until 이 몸통 할당을 읽는 데 씀, 2026-08-22 M4)

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

    # 블록([goal:]/[if:]/[case:]) 감지는 *문장 단위* — 아래 statement 루프에서 한다.
    # 옛 전체-코드 전용 감지는 두 가지로 절름발이였다: 다단 문장 속 블록은 아예 파싱
    # 불가('해석되지 않은 텍스트'), 코드가 블록으로 *시작*하면 뒤따르는 문장을 조용히
    # 버렸다(침묵 액션 소실 부류). 블록 뒤 잉여 텍스트는 이제 각 블록 파서가 명시 거절.

    # 파이프라인 파싱
    # 전처리: 주석 제거, 줄 정규화 (멀티라인 { } 블록은 한 문장으로 병합됨)
    lines = _preprocess(code)
    if not lines:
        raise IBLSyntaxError("파싱 가능한 코드가 없습니다.")

    # 변수 바인딩과 명령문 분리
    statements, assign_names = _extract_statements(lines)

    # [else]/[else if:] 로 시작하는 문장 = 앞 문장 if 체인의 연속.
    # 물리 줄이 갈라져 있어도 잇는다 ([if: c]{...} 줄 다음의 [else]{...} 줄).
    _m_stmts: List[str] = []
    _m_names: List[Optional[str]] = []
    for _s, _n in zip(statements, assign_names):
        if _m_stmts and _s.lstrip().startswith(('[else', '[catch]', '[finally]')):
            _m_stmts[-1] = _m_stmts[-1] + ' ' + _s
        else:
            _m_stmts.append(_s)
            _m_names.append(_n)
    statements, assign_names = _m_stmts, _m_names

    all_steps = []
    # 변수명 → 그 변수가 할당된 문장의 *최종* step 인덱스 (파이프라인이면 마지막 step).
    # 문장이 step 으로 펼쳐진 *뒤* 채워지므로, 뒤 문장의 $var 참조가 정확한 인덱스로
    # 치환된다({{_step_N_result}} — 실행기가 step 별 결과를 저장해 치환. D4).
    variables: Dict[str, int] = {}
    for _stmt_idx, stmt in enumerate(statements):
        # 문장 전체가 블록([goal:]/[if:]/[case:])이면 블록 step 하나로 —
        # desugar·파이프 분리에 넣으면 블록 내부 문장이 난도질당한다.
        # [on_error: stop|skip|null] 문장 접두(프로그램급 IBL M3, 설계 §2.4): 이 문장의 >> 파이프에서
        # step 실패를 어떻게 넘길지 — skip=실패 step 을 건너뛰고 직전 통화로, null=빈 items 로 계속.
        # 기본은 stop(현행). 실행기가 건너뛴 step 을 봉투에 신고한다(조용한 계속 금지).
        _on_err = None
        _pm = _ON_ERROR_RE.match(stmt)
        if _pm:
            _on_err = _pm.group(1).lower()
            stmt = stmt[_pm.end():].strip()
            if not stmt:
                raise IBLSyntaxError("[on_error: …] 뒤에 문장이 없습니다 — 예: [on_error: skip] [A] >> [B] >> [C]")
        _stmt_start = len(all_steps)
        # 문장에 깊이 0 의 >> 가 있으면 파이프 경로로(블록이 첫 세그먼트여도: `[repeat:…]{…} >> [table:dedup]`, M6)
        _piped = len(_split_pipeline(stmt)) > 1
        # 식 할당 `$n = 0` / `$n = $n + 1` / `$s = $r.count * 2` (M6 — 카운터·상태 변수): 우변이 액션이
        # 아니면 한 줄 식 문장. $변수는 값 바인딩(_vars), 평가는 ibl_control_blocks._execute_assign.
        if assign_names[_stmt_idx] and not _piped and not stmt.lstrip().startswith(('[', '(')):
            blk = {"_assign": True, "name": assign_names[_stmt_idx], "expr": stmt.strip()}
            refs = set(_var_names(stmt))
            vars_used = {n: i for n, i in variables.items() if n in refs}
            if vars_used:
                blk["_vars"] = vars_used
            if _stmt_idx > 0:
                blk["_seq_boundary"] = True
            blk["_assign_name"] = assign_names[_stmt_idx]
            all_steps.append(blk)
            variables[assign_names[_stmt_idx]] = len(all_steps) - 1
            continue
        blk = None if _piped else _parse_statement_block(stmt)
        if blk is not None:
            # 블록도 앞 문장의 $변수를 본다 (2026-08-22 프로그램급 IBL M2): 분기 몸의
            # 파라미터는 일반 step 처럼 {{_step_N_result}} 치환, 조건식·case 소스 안의 $변수는
            # 텍스트 치환이 아니라 *값 바인딩* — 파서는 이름→step 인덱스(_vars)만 적고
            # 실행기(workflow_engine)가 실행 시점에 _var_values 로 값을 실어 준다.
            if variables:
                blk = _resolve_block_variables(blk, variables)
            if _stmt_idx > 0:
                blk["_seq_boundary"] = True
            if _on_err:
                blk["_on_error"] = _on_err
            if assign_names[_stmt_idx]:
                blk["_assign_name"] = assign_names[_stmt_idx]
            all_steps.append(blk)
            if assign_names[_stmt_idx]:
                variables[assign_names[_stmt_idx]] = len(all_steps) - 1
            continue
        # 파이프 문법 설탕(| where:/sort:/take:/select:/dedup:)을 >> [table:동사] 로 desugar.
        # 의미는 engines 변환자에 이미 있고, 이건 빈도 높은 단항 변환자의 짧은 문법 표면.
        stmt = _desugar_pipe_sugar(stmt)
        # >> 로 파이프라인 분리
        segments = _split_pipeline(stmt)  # [(text, operator), ...]
        for idx, (seg_text, operator) in enumerate(segments):
            # 각 세그먼트 내에서 & 또는 ?? 연산자 처리
            parsed = _parse_group(seg_text.strip())
            if parsed is None:
                _st = seg_text.strip()
                # F16-1 (2026-08-20 상상훈련 16회차): 분기 헤더가 홀로 오면(중괄호 몸 누락)
                # 맨 "파싱 실패"는 자가교정을 못 이끈다 — 정답 형태를 오류문에 동반.
                if _st.startswith(('[if:', '[case:', '[else')):
                    raise IBLSyntaxError(
                        f"파싱 실패: {_st} — 분기 몸은 같은 문장에서 중괄호로 감쌉니다: "
                        "[if: 조건]{[액션]} [else]{[액션]} / "
                        '[case: 소스]{"값": [액션], default: [액션]}. '
                        "헤더와 몸을 줄로 나누면 파싱되지 않습니다.")
                raise IBLSyntaxError(f"파싱 실패: {_st}")
            # 변수 참조 치환 — 앞 문장들에서 할당된 변수만 보인다(자기/앞선 참조 방지)
            # 파이프 속 블록(M6: `[A] >> [if:…]{…} >> [B]`, `[repeat:…]{…} >> [table:dedup]`)은 블록 규약으로.
            if _is_block_step(parsed):
                parsed = _resolve_block_variables(parsed, variables) if variables else parsed
            else:
                parsed = _resolve_variables(parsed, variables)
            # 문장 경계 표식 — 문장들은 한 리스트로 평탄화되므로, 실행기가 "여기부터 새 문장"을
            # 알 방법이 이 표식뿐이다. 경계에서는 앞 문장의 실패가 전파되지 않고
            # _prev_result 도 넘어가지 않는다(독립이란 뜻이므로). 첫 step 에만 붙인다.
            if _stmt_idx > 0 and idx == 0:
                parsed["_seq_boundary"] = True
            all_steps.append(parsed)
        if _on_err:
            for _st in all_steps[_stmt_start:]:
                _st["_on_error"] = _on_err
        if assign_names[_stmt_idx] and all_steps:
            variables[assign_names[_stmt_idx]] = len(all_steps) - 1
            all_steps[-1]["_assign_name"] = assign_names[_stmt_idx]   # $return 규약·재개 진단용 표지

    if not all_steps:
        raise IBLSyntaxError("실행 가능한 명령이 없습니다.")

    return all_steps, variables


_BLOCK_PREFIXES = ('[goal:', '[if:', '[case:', '[try]', '[repeat:')


def _is_block_step(st: Any) -> bool:
    return isinstance(st, dict) and any(st.get(k) for k in ("_goal", "_condition", "_case", "_try", "_repeat", "_assign"))


def _parse_statement_block(stmt: str) -> Optional[Dict]:
    """문장 하나가 통째로 블록([goal:]/[if:]/[case:])이면 그 블록 step, 아니면 None.

    접두 검사로 일반 문장은 블록 정규식에 안 태운다. 블록 패턴이 접두만 맞고
    본문이 어긋나면 각 블록 파서가 IBLSyntaxError 를 던진다(조용한 통과 금지).
    """
    s = stmt.strip()
    if s.startswith('[goal:'):
        return _parse_goal_block(s)
    if s.startswith('[if:'):
        return _parse_if_else(s)
    if s.startswith('[case:'):
        return _parse_case(s)
    if s.startswith('[try]'):
        return _parse_try_block(s)
    if s.startswith('[repeat:'):
        return _parse_repeat_block(s)
    return None


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
    register_parse as _register_parse,
    _parse_try_block,
    _parse_repeat_block,
    register_parse_vars as _register_parse_vars,
)

# 재귀 하강 주입 — 블록 파서는 본체를 모른다(의존 역전, 순환 간선 제거).
_register_parse(parse)
_register_parse_vars(parse_with_vars)

# [on_error: stop|skip|null] 문장 접두 (M3)
_ON_ERROR_RE = re.compile(r'^\s*\[on_error:\s*(stop|skip|null)\s*\]\s*', re.I)


_STEP_PATTERN = re.compile(
    r'\[(\w+):(\w+)\]'           # [node:action]
    r'(?:\s*\(([^)]*)\))?',      # (target) - 감지용 (사용 시 에러)
    re.DOTALL
)

# 변수 할당·참조 표기는 common.ibl_vars 가 단일 진실 (2026-08-22 괄호형 `${이름}` 도입).
# 맨몸 `$이름` 과 괄호 `${이름}` 이 같은 뜻이고, 괄호는 한글 조사·단위가 이름에 먹히는 것을
# 막는 경계 표시다(`"$n건"`=변수 n건 / `"${n}건"`=변수 n + 글자 건).
from common.ibl_vars import (ASSIGN_RE as _VAR_ASSIGN_PATTERN,  # noqa: E402
                             REF_RE as _VAR_REF_PATTERN,
                             find_names as _var_names, sub_ref as _sub_var_ref)


def _preprocess(code: str) -> List[str]:
    """전처리: 주석 제거, 빈 줄 제거, 연속 줄 합치기, 멀티라인 블록 병합

    ★문자열 보호(D3, 2026-08-05): 주석 판정을 줄 단위가 아니라 *문자열 상태를 줄 경계
    너머로 승계*하며 한다. 예전엔 `#` 로 시작하는 줄을 무조건 버려, multi-line string
    파라미터(content: "...") 안의 마크다운 헤딩(`# 제목`)·빈 줄이 조용히 삭제됐다
    (self:write 본문 손상 실측). 열린 문자열 안의 줄은 전부 내용이므로 보존한다.
    주석 줄은 스캔하지 않고 버린다 — 주석 속 따옴표(예: # don't)가 상태를 오염시키지 않게.
    """
    entries = []  # (line, 줄 시작 시점의 in_string 여부)
    in_string = False
    string_char = None
    for line in code.split('\n'):
        stripped = line.strip()
        if not in_string:
            if not stripped or stripped.startswith('#'):
                continue
        entries.append((stripped, in_string))
        _d, in_string, string_char = _scan_line_state(stripped, in_string, string_char)

    if not entries:
        return []

    # 1단계: 이어지는 줄을 이전 줄에 합치기.
    #   - 열린 문자열 안에서 시작하는 줄 = 앞 줄 문자열의 내용 → '\n' 으로 병합(내용 보존)
    #   - >> 로 시작하는 줄 = 멀티라인 파이프라인 → ' ' 로 병합
    merged = []
    for line, was_in_string in entries:
        if merged and was_in_string:
            merged[-1] = merged[-1] + '\n' + line
        elif merged and line.startswith('>>'):
            merged[-1] = merged[-1] + ' ' + line
        else:
            merged.append(line)

    # 2단계: 멀티라인 { } 블록 병합
    #   이전 줄의 { } 균형이 맞지 않으면 다음 줄을 합침 (문자열 상태 승계 —
    #   문자열 안의 중괄호가 깊이를 오염시키지 않게)
    result = []
    i = 0
    while i < len(merged):
        current = merged[i]
        depth, s_in, s_ch = _scan_line_state(current, False, None)
        while (depth > 0 or s_in) and i + 1 < len(merged):
            i += 1
            current = current + '\n' + merged[i]
            d2, s_in, s_ch = _scan_line_state(merged[i], s_in, s_ch)
            depth += d2
        result.append(current)
        i += 1

    return result


def _scan_line_state(text: str, in_string: bool, string_char: Optional[str]):
    """한 줄을 스캔해 (중괄호 깊이 변화량, 끝 시점 문자열 상태)를 반환.

    문자열 리터럴 내부의 중괄호는 세지 않고, 문자열 열림/닫힘 상태를 줄 경계
    너머로 승계할 수 있게 시작 상태를 인자로 받는다. (D3 — _preprocess 전용)
    """
    depth = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if in_string:
            if ch == '\\':
                i += 1  # 이스케이프 건너뛰기
            elif ch == string_char:
                in_string = False
                string_char = None
        else:
            if ch == '"' or ch == "'":
                in_string = True
                string_char = ch
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
        i += 1
    return depth, in_string, string_char


def _extract_statements(lines: List[str]) -> Tuple[List[str], List[Optional[str]]]:
    """
    변수 할당과 명령문을 분리

    Returns:
        (statements, assign_names)
        - statements: 실행할 명령문 리스트
        - assign_names: statements 와 정렬된 리스트. 그 문장이 `$name = ...` 할당이면
          변수명, 아니면 None. 실제 step 인덱스 바인딩은 parse() 가 문장을 step 으로
          펼친 뒤에 계산한다 (desugar 로 step 수가 변할 수 있어 여기서 세면 어긋난다).
    """
    statements = []
    assign_names: List[Optional[str]] = []

    # `;` = 한 줄 안의 줄바꿈. 독립 문장을 한 줄에 늘어놓는 순차 연산자로,
    # 여기서 개행과 **같은 것**으로 접는다(실행기는 둘을 구분하지 않는다).
    # 문자열·중괄호 안의 `;` 는 _split_by_operator 가 알아서 무시한다.
    lines = [s for line in lines for s in (_split_by_operator(line, ';') or [line])]

    for line in lines:
        m = _VAR_ASSIGN_PATTERN.match(line)
        if m:
            assign_names.append(m.group(1) or m.group(2))
            statements.append(m.group(3).strip())
        else:
            assign_names.append(None)
            statements.append(line)

    return statements, assign_names


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
    paren = 0  # ( ) 깊이 — 괄호 분기 파이프 안의 >> 는 분기 소유 (G13-1, 2026-08-19)

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
        elif ch == '(' and depth == 0:
            paren += 1
            current.append(ch)
        elif ch == ')' and depth == 0:
            paren = max(0, paren - 1)   # 홀로 남은 ')' 가 이후 전체를 잠그지 않게
            current.append(ch)
        elif (ch == '>' and i + 1 < len(chars) and chars[i + 1] == '>'
              and depth == 0 and paren == 0):
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

    # 파이프 속 블록 세그먼트 (M6): `[A] >> [if: 조건]{…} [else]{…} >> [B]` — 블록은 _prev_result 를 받아
    # 몸에 넘기고, 블록 결과(분기 결과·repeat items)가 다음 step 의 통화가 된다.
    if text.lstrip().startswith(_BLOCK_PREFIXES):
        blk = _parse_statement_block(text.strip())
        if blk is not None:
            return blk

    # ★혼용 거부(D1, 2026-08-05): 한 세그먼트에 & 와 ?? 가 섞이면 명시 파스 에러.
    #   예전엔 & 를 먼저 무조건 분할하고 각 조각을 _parse_step(첫 매치만)이 먹어,
    #   '[a:b]{} ?? [c:d]{} & [e:f]{}' 에서 c:d 가 조용히 사라졌다(액션 침묵 소실).
    #   두 연산자는 우선순위가 정의돼 있지 않다 — >> 로 단계를 나누거나 문장(줄/;)을 분리할 것.
    parallel_parts = _split_by_operator(text, '&')
    fallback_parts = _split_by_operator(text, '??')
    if len(parallel_parts) > 1 and len(fallback_parts) > 1:
        raise IBLSyntaxError(
            "한 세그먼트 안에서 & (병렬)와 ?? (폴백)를 섞을 수 없습니다 — 우선순위가 "
            "정의되지 않아 액션이 유실됩니다. >> 로 단계를 나누거나 문장을 분리하세요.\n"
            f"  문제 구간: {text[:120]}"
        )
    if len(parallel_parts) > 1:
        branches = []
        for part in parallel_parts:
            p = part.strip()
            # 괄호 분기 파이프 (G13-1, 2026-08-19 상상훈련 13회차): 분기 하나에만
            # 전처리를 붙이는 표현 — [A] & ([B] >> [table:rename]{...}) >> [table:merge].
            branch = _parse_paren_branch(p)
            if branch is None:
                branch = _parse_step(p)
            if branch is None:
                raise IBLSyntaxError(f"병렬 요소 파싱 실패: {p}")
            branches.append(branch)
        return {"_parallel": True, "branches": branches}

    # ?? 연산자 확인 (fallback)
    if len(fallback_parts) > 1:
        chain = []
        for part in fallback_parts:
            # 괄호 파이프 가지 (프로그램급 IBL M3): A ?? (B >> C) — 병렬 괄호 분기와 같은 규칙·같은 파서.
            step = _parse_paren_branch(part.strip())
            if step is None:
                step = _parse_step(part.strip())
            if step is None:
                raise IBLSyntaxError(f"fallback 요소 파싱 실패: {part.strip()}")
            chain.append(step)
        return {"_fallback_chain": chain}

    # 일반 단일 step
    step = _parse_step(text)
    if step is None and text.lstrip().startswith('('):
        raise IBLSyntaxError(
            "괄호 분기는 병렬(&)·폴백(??)의 분기 자리에서만 씁니다 — 단독 파이프는 괄호 없이 >> 로 이으세요.")
    return step


def _parse_paren_branch(text: str) -> Optional[Dict]:
    """병렬 분기의 괄호 파이프 '([A]{} >> [B]{})' → {_branch_steps: [step, ...]} (G13-1).

    괄호가 분기 *전체*를 감싸는 경우만(첫 '(' 의 짝이 마지막 문자) — 아니면 None 을
    돌려 일반 step 파싱으로 넘긴다. 괄호 안은 >> 로 이은 일반 step 들만 허용:
    중첩 병렬/폴백/블록은 명시 에러(우선순위 미정의 → 침묵 소실 방지, D1 과 같은 원칙).
    (단일 step) 은 괄호가 무의미하므로 그 step 자체로 푼다.
    """
    t = text.strip()
    if not t.startswith('(') or not t.endswith(')'):
        return None
    # 첫 괄호의 짝 찾기 — 문자열·중괄호 안의 괄호는 구조가 아니다
    depth = 0
    brace = 0
    in_str = False
    str_ch = None
    close_idx = -1
    i = 0
    while i < len(t):
        ch = t[i]
        if in_str:
            if ch == '\\':
                i += 2
                continue
            if ch == str_ch:
                in_str = False
            i += 1
            continue
        if ch in ('"', "'"):
            in_str = True
            str_ch = ch
        elif ch == '{':
            brace += 1
        elif ch == '}':
            brace -= 1
        elif ch == '(' and brace == 0:
            depth += 1
        elif ch == ')' and brace == 0:
            depth -= 1
            if depth == 0:
                close_idx = i
                break
        i += 1
    if close_idx != len(t) - 1:
        return None                      # 괄호가 전체를 안 감쌈 — 일반 파싱으로
    inner = t[1:-1].strip()
    if not inner:
        raise IBLSyntaxError("괄호 분기가 비어 있습니다: ()")
    steps = []
    for seg_text, _op in _split_pipeline(inner):
        st = _parse_step(seg_text.strip())
        if st is None:
            raise IBLSyntaxError(
                f"괄호 분기 파이프 파싱 실패: {seg_text.strip()} — 괄호 분기 안은 "
                "[node:action]{...} step 을 >> 로 이은 파이프만 허용합니다"
                "(중첩 병렬/폴백/블록 불가).")
        steps.append(st)
    if len(steps) == 1:
        return steps[0]
    return {"_branch_steps": steps}


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
    paren = 0        # ( ) 깊이 — 괄호 분기 안의 연산자는 분기 소유 (G13-1, 2026-08-19)
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
        elif ch == '(' and depth == 0:
            paren += 1
            current.append(ch)
        elif ch == ')' and depth == 0:
            paren = max(0, paren - 1)
            current.append(ch)
        elif depth == 0 and paren == 0 and chars[i:i+op_len] == operator:
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
                "예: [sense:search]{query: \"X\"} | where: \"전세\" | sort: price desc | take: 5"
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

    # ★침묵 흡수 방지(D2, 2026-08-05): [node:action] 앞에 해석 안 되는 텍스트가 있으면
    #   명시 에러. 예전엔 search() 가 중간 매치를 잡아 앞부분을 조용히 버렸다.
    lead = text[:m.start()].strip()
    if lead:
        raise IBLSyntaxError(
            f"스텝 앞에 해석되지 않은 텍스트가 있습니다: '{lead[:80]}'\n"
            f"  전체: {text[:160]}"
        )

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
    leftover = tail
    if tail.startswith('@'):
        mt = re.match(r'@([^\s\(\)\{\}\[\]&|>?@]+)', tail)
        if mt:
            target_node = mt.group(1)
            leftover = tail[mt.end():].strip()

    # ★침묵 흡수 방지(D2, 2026-08-05): 스텝 문법이 소비하지 않은 잔여 텍스트가 있으면
    #   명시 에러. 예전엔 '[a:b]{} [c:d]{}' (>> 누락 오타)가 한 스텝으로 조용히 흡수돼
    #   c:d 가 실행되지 않았다. 단, `#` 로 시작하는 잔여는 인라인 주석으로 무해 폐기
    #   (기존 관대함 유지 — 코드가 아니라 실행 유실이 없다).
    if leftover and not leftover.startswith('#'):
        hint = ""
        if _STEP_PATTERN.search(leftover):
            hint = " 여러 스텝을 이으려면 >> (순차), & (병렬), ?? (폴백) 연산자를 쓰세요."
        raise IBLSyntaxError(
            f"스텝 뒤에 해석되지 않은 텍스트가 있습니다: '{leftover[:80]}'.{hint}\n"
            f"  전체: {text[:160]}"
        )

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



def _resolve_variables(step: dict, variables: Dict[str, int]) -> dict:
    """
    step 내의 변수 참조($name)를 {{_step_N_result}} 패턴으로 변환

    N = 그 변수가 할당된 문장의 최종 step 인덱스. workflow_engine 이 step 별 결과를
    저장해 실행 시점에 실제 값으로 치환한다 (D4 — 예전엔 전부 {{_prev_result}} 로
    뭉개지고 문장 경계가 prev_result 를 비워 빈 문자열이 주입됐다).

    이름 경계 매칭 — $a 가 $abc 안에 부분 매칭되지 않게 (?!\\w) 로 막는다.
    """
    if not variables:
        return step

    resolved = {}
    for key, val in step.items():
        if isinstance(val, str):
            for var_name, step_idx in variables.items():
                # $var.field.path — 필드 경로를 템플릿에 실어 실행기가 추출하게 한다
                # (2026-08-16 상상훈련 G1: 경로 없이 통짜 치환하면 `.lat` 이 리터럴로 남았다).
                val = _sub_var_ref(val, var_name,
                                   lambda path, _i=step_idx: "{{_step_%d_result%s}}" % (_i, path))
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


def _resolve_block_variables(blk: dict, variables: Dict[str, int], nested: bool = False) -> dict:
    """블록([if:]/[case:]/[try]/[repeat:]/식 할당) 의 $변수 처리 (2026-08-22 M2 → M6 개정).

    블록 *몸* 은 파서가 치환하지 않는다 — 몸은 안쪽 파이프(자기 step 인덱스)로 실행되는데, 바깥 인덱스의
    `{{_step_N_result}}` 를 몸에 박아 두면 바깥 주입이 안쪽 인덱스와 충돌한다(M6 실측: repeat 몸의
    `$n = $n + 1` 이 늘 바깥 0 을 읽음). 대신 블록 전체 텍스트가 참조하는 바깥 변수 이름만 `_vars`
    = {이름: step 인덱스} 로 적고, 실행기가 실행 직전에 값으로 바인딩(조건·식)하거나 치환(몸 파라미터,
    `_subst_var_refs` — v4/경로 규약은 파서 치환과 동일)한다. 중첩 블록(nested)엔 _vars 를 붙이지 않고
    실행기가 _var_values 를 내려보낸다. goal 블록은 스케줄러 의미라 불변."""
    if not isinstance(blk, dict) or blk.get("_goal"):
        return blk
    out = dict(blk)
    if nested:
        return out
    refs = set(_var_names(json.dumps(blk, ensure_ascii=False)))
    vars_used = {name: idx for name, idx in variables.items() if name in refs}
    if vars_used:
        out["_vars"] = vars_used
    return out


# === 유틸리티 ===

def format_step(step: dict) -> str:
    """step을 IBL 텍스트로 포맷팅 (역변환)"""
    # 괄호 분기 파이프 (G13-1)
    if step.get("_branch_steps"):
        return "(" + " >> ".join(format_step(s) for s in step["_branch_steps"]) + ")"

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
    p11 = parse('[sense:web_search]{query: "AI"} & [sense:search]{source: "gnews", query: "부동산"}')
    print(f"11. 병렬: {p11}")
    assert len(p11) == 1
    assert p11[0]["_parallel"] == True
    assert len(p11[0]["branches"]) == 2
    assert p11[0]["branches"][0]["_node"] == "sense"
    assert p11[0]["branches"][0]["action"] == "web_search"
    assert p11[0]["branches"][1]["action"] == "search"

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
    p15 = parse('[sense:web_search]{query: "AI"} & [sense:search]{source: "gnews", query: "부동산"} >> [self:file]{path: "결과.md"}')
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

    # 23. 변수 바인딩 — $var 가 할당 문장의 최종 step 인덱스로 치환돼야 함 (D4)
    code23 = """
    $result = [sense:web_search]{query: "AI 뉴스"}
    [others:channel_send]{channel_type: "telegram", body: "$result"}
    """
    p23 = parse(code23)
    print(f"23. 변수 바인딩: {len(p23)} steps, body={p23[1]['params']['body']}")
    assert len(p23) == 2
    assert p23[1]["params"]["body"] == "{{_step_0_result}}"

    # 23b. 파이프라인 할당 — 변수는 그 문장의 *마지막* step 결과를 가리킴 (D4)
    code23b = """
    $r = [sense:web_search]{query: "A"} >> [table:take]{n: 3}
    [others:channel_send]{channel_type: "telegram", body: "$r"}
    """
    p23b = parse(code23b)
    print(f"23b. 파이프 할당: body={p23b[2]['params']['body']}")
    assert len(p23b) == 3
    assert p23b[2]["params"]["body"] == "{{_step_1_result}}"

    # 23c. 이름 경계 — $r 이 $result 안에 부분 매칭되지 않아야 함 (D4)
    code23c = """
    $r = [sense:web_search]{query: "A"}
    $result = [sense:web_search]{query: "B"}
    [others:channel_send]{channel_type: "telegram", body: "$result / $r"}
    """
    p23c = parse(code23c)
    print(f"23c. 이름 경계: body={p23c[2]['params']['body']}")
    assert p23c[2]["params"]["body"] == "{{_step_1_result}} / {{_step_0_result}}"

    # === 침묵 실패 수리 회귀 테스트 (2026-08-05) ===
    print("\n--- 침묵 실패 수리 Tests (D1~D4) ---")

    # 24. D1: & 와 ?? 혼용 → 명시 파스 에러 (예전엔 c:d 가 조용히 소실)
    try:
        parse('[sense:web_search]{query: "a"} ?? [sense:crawl]{url: "b"} & [sense:search]{source: "gnews", query: "c"}')
        assert False, "혼용은 IBLSyntaxError 여야 함"
    except IBLSyntaxError as e:
        print(f"24. D1 혼용 거부: {str(e).splitlines()[0]}")
        assert "섞을 수 없습니다" in str(e)

    # 25. D2: >> 누락 오타 → 명시 파스 에러 (예전엔 둘째 스텝이 조용히 흡수·유실)
    try:
        parse('[sense:web_search]{query: "a"} [self:file]{path: "b.md"}')
        assert False, ">> 누락은 IBLSyntaxError 여야 함"
    except IBLSyntaxError as e:
        print(f"25. D2 잔여 텍스트 거부: {str(e).splitlines()[0]}")
        assert "해석되지 않은" in str(e)

    # 25b. D2: @별칭 뒤 잔여도 거부, @별칭 자체는 정상
    s25 = parse_step('[self:read]{path: "a.md"}@폰2')
    assert s25["target_node"] == "폰2"
    try:
        parse_step('[self:read]{path: "a.md"}@폰2 [self:open]{}')
        assert False
    except IBLSyntaxError:
        print("25b. D2 @별칭 뒤 잔여 거부 OK")

    # 25c. D2: 인라인 주석은 무해 폐기 (기존 관대함 유지)
    s25c = parse('[sense:web_search]{query: "a"} # 검색')
    assert len(s25c) == 1 and s25c[0]["action"] == "web_search"
    print("25c. D2 인라인 주석 허용 OK")

    # 26. D3: multi-line string 파라미터 안의 # 헤딩·빈 줄 보존 (예전엔 삭제돼 본문 손상)
    code26 = '''[self:write]{path: "t.md", content: "제목
# 헤딩입니다

본문"}'''
    p26 = parse(code26)
    c26 = p26[0]["params"]["content"]
    print(f"26. D3 문자열 내 헤딩 보존: {c26!r}")
    assert "# 헤딩입니다" in c26
    assert "\n\n" in c26  # 빈 줄도 내용
    assert p26[0]["params"]["path"] == "t.md"

    # 26b. D3: 문자열 밖 주석은 여전히 제거
    p26b = parse('# 주석\n[sense:web_search]{query: "a"}\n# 주석2')
    assert len(p26b) == 1
    print("26b. D3 문자열 밖 주석 제거 OK")

    print("\n=== 모든 테스트 통과 ===")
