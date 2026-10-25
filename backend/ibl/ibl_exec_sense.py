"""Historical source-reference parsing and field diagnostics, with no execution.

Current programs use explicit values through the edition-2 runtime.
"""
import os
import re
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_FIELD_MISSING = object()  # 경로 부재 표지 — "값이 null"(정당한 부재)과 구별 (★B10-case)


def _field_path_hints(result: Any, max_paths: int = 24) -> List[str]:
    """조건 소스 결과에서 쓸 수 있는 점 경로 후보 — 최상위 + 1단 중첩 (F13-4).

    스칼라 값 경로만 후보로 낸다(dict 중간 노드는 자식 경로가 대신 말한다).

    ★B25-1 (2026-08-23): 리스트 키는 이름만 싣던 옛 판이 결함의 **공범**이었다 —
    `.items.0.max_temp` 가 판정 불능이 됐을 때 힌트가 `items` 에서 멈춰,
    쓸 수 있는 진짜 경로를 한 번도 안 보여 줬다. 이제 첫 행의 스칼라 칸을
    `items.0.칸` 형태로 몇 개 싣는다(경로 폭발은 max_paths 와 행당 상한이 막는다).
    """
    hints: List[str] = []
    if not isinstance(result, dict):
        return hints
    for k, v in result.items():
        if not isinstance(k, str) or k.startswith("_"):
            continue
        if isinstance(v, dict):
            sub = [f"{k}.{sk}" for sk, sv in v.items()
                   if isinstance(sk, str) and not isinstance(sv, (dict, list))]
            hints.extend(sub if sub else [k])
        elif isinstance(v, list):
            first = v[0] if v and isinstance(v[0], dict) else None
            sub = [f"{k}.0.{sk}" for sk, sv in (first or {}).items()
                   if isinstance(sk, str) and not sk.startswith("_")
                   and not isinstance(sv, (dict, list))] if first else []
            hints.extend(sub[:6] if sub else [k])
        else:
            hints.append(k)
        if len(hints) >= max_paths:
            break
    return hints[:max_paths]


def _parse_source_ref(source: str) -> Optional[Tuple[str, str, Dict, Optional[str]]]:
    """
    case/if의 source 참조식을 (node, action, params, field)로 분해.

    유효하지 않으면 None.
    """
    import re

    src = source.strip()
    m = re.match(r'^(\w+):(\w+)', src)
    if not m:
        return None
    node, action = m.group(1), m.group(2)
    rest = src[m.end():]

    params: Dict[str, Any] = {}
    if rest.startswith('{'):
        from ibl_parser import _extract_bracket_raw, _parse_params, IBLSyntaxError
        body, end_pos = _extract_bracket_raw(rest, 0, '{', '}')
        if body is None:
            return None
        try:
            params = _parse_params('{' + body + '}') or {}
        except IBLSyntaxError:
            # 2026-08-22: 파라미터를 끝까지 못 읽은 것을 params={} 로 눙치면
            # 조건이 인자를 잃은 채 조용히 평가된다 — 이 함수의 정직한
            # 실패 모양(None = 유효하지 않은 참조)으로 돌려준다.
            return None
        except Exception:
            params = {}
        rest = rest[end_pos + 1:]

    field: Optional[str] = None
    rest = rest.strip()
    if rest.startswith('.'):
        fm = re.match(r'^\.(\w+(?:\.\w+)*)\s*$', rest)
        if fm:
            field = fm.group(1)

    return (node, action, params, field)


def _extract_dotted_field(result: Any, field_path: str) -> Any:
    """중첩 dict에서 점 표기법으로 필드 추출 ('close', 'data.price')."""
    value = _extract_dotted_field_checked(result, field_path)
    return None if value is _FIELD_MISSING else value


def _extract_dotted_field_checked(result: Any, field_path: str) -> Any:
    """점 표기 추출의 검침판 — 경로 부재는 _FIELD_MISSING, 값이 진짜 null 이면 None.

    중간 노드가 null 이거나 dict/list 가 아니면 그 아래 경로는 "부재"다(★B10-case).

    ★B25-1 (2026-08-23 상상훈련 25회차): 경로 해소기를 **정본 하나로 접었다.**
    옛 판은 `isinstance(current, dict)` 만 봐서 리스트 인덱스(`items.0.max_temp`)를
    못 넘었다. 같은 조건 언어의 다른 좌변(`$변수.items.0.max_temp`)은 이미
    `ibl_predicates.walk_path` 로 넘어가고 있었으므로 **한 문법이 좌변 종류에 따라
    두 갈래로 갈려** 있었다 — 소스 참조 쪽만 판정 불능이 되고, 판정 불능은 else 까지
    보류시키므로 문장이 통째로 죽었다.
    `items` 는 IBL 의 단일 통화라 "방금 조회한 통화의 첫 행을 보고 분기"가 조건문의
    가장 흔한 수요인데 그 자리가 막혀 있었던 것이다. F20-2(20회차)가 붙인 items 폴백은
    행이 정확히 1개일 때만 발동해(위 74~80줄) 같은 구멍의 국소 덧대기였다 — 그 폴백은
    `.items.0.x` 아닌 `.x` 표기를 받아 주는 별개 편의라 그대로 둔다.
    """
    from ibl_predicates import walk_path, _MISSING as _PRED_MISSING
    value = walk_path(result, field_path)
    return _FIELD_MISSING if value is _PRED_MISSING else value


def _find_top_level_comparison_op(text: str) -> Optional[Tuple[int, int, str]]:
    """
    조건식에서 {}/[]/문자열 밖의 첫 비교 연산자 위치 찾기.

    좌→우 스캔. 2자 연산자(==, !=, >=, <=)를 먼저 시도.
    """
    depth = 0
    in_string = False
    string_char: Optional[str] = None
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if in_string:
            if c == '\\' and i + 1 < n:
                i += 2
                continue
            if c == string_char:
                in_string = False
            i += 1
            continue
        if c == '"' or c == "'":
            in_string = True
            string_char = c
            i += 1
            continue
        if c in '{[':
            depth += 1
            i += 1
            continue
        if c in '}]':
            depth -= 1
            i += 1
            continue
        if depth == 0:
            two = text[i:i+2]
            if two in ('==', '!=', '>=', '<='):
                return (i, i + 2, two)
            if c == '>' or c == '<':
                return (i, i + 1, c)
        i += 1
    return None
