"""
ibl_exec_sense.py — 조건/case 의 소스 참조 평가: `node:action{…}.field` 파싱·실행·점 경로 추출·필드 힌트.

2026-08-23 ibl_executors.py 에서 이사(1500줄 규칙). 재수출 = ibl_executors.
★_evaluate_condition_and_value 는 파사드(ibl_executors)에 남긴다 — 시험이
  `ex._get_sense_value_checked` 를 monkeypatch 하므로 그 참조가 파사드 전역을 거쳐야 한다.
"""
import os
import re
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_FIELD_MISSING = object()  # 경로 부재 표지 — "값이 null"(정당한 부재)과 구별 (★B10-case)


def _get_sense_value(source: str, project_path: str, agent_id: str) -> Any:
    """
    case/if의 source 표현을 평가하여 실제 값 반환.

    지원하는 형태:
        node:action                      예: self:time
        node:action{params}              예: sense:price{symbol: "^KS11"}
        node:action{params}.field        예: sense:price{symbol: "^KS11"}.close
        node:action.field                예: self:time.hour

    sense뿐 아니라 self/limbs/others/engines 모두 허용한다.
    field가 지정된 경우 결과 dict에서 점 표기법으로 추출하고,
    없으면 기존 동작(`value` → `result` → str)을 유지한다.
    판정 불능 사유가 필요한 호출자는 _get_sense_value_checked 를 쓴다.
    """
    value, _err = _get_sense_value_checked(source, project_path, agent_id)
    return value


def _get_sense_value_checked(source: str, project_path: str, agent_id: str) -> Tuple[Any, Optional[str]]:
    """_get_sense_value 의 검침판 — (값, 판정불능 사유)를 돌려준다.

    ★B10-case (2026-08-17 상상훈련 11회차): 판정 불능(파싱 실패·실행 예외·필드 경로
    부재)과 "필드는 실존하되 값이 null"(정당한 부재)을 구별한다 — 후자는 (None, None).
    옛 코드는 셋 다 None 으로 접어 case 의 default 가 판정 불능을 "불일치"로 단정했다.
    """
    parsed = _parse_source_ref(source)
    if parsed is None:
        return None, f"source 표현을 해석하지 못했습니다: '{source}'."
    node, action, params, field = parsed

    try:
        from ibl_engine import execute_ibl
        step = {"_node": node, "action": action, "params": params}
        result = execute_ibl(step, project_path, agent_id)
    except Exception as e:
        return None, f"'{node}:{action}' 실행 실패: {e}."

    # 핸들러 다수가 JSON *문자열* 봉투를 반환한다 — 파싱 없이 점 추출하면 문자열에
    # 막혀 None → 조건이 조용히 거짓이 된다(센서 필드 조건 전멸 부류).
    if isinstance(result, str):
        try:
            _p = json.loads(result)
            if isinstance(_p, (dict, list)):
                result = _p
        except Exception:
            pass

    if field is not None:
        value = _extract_dotted_field_checked(result, field)
        if value is _FIELD_MISSING:
            # ★F20-2 (2026-08-22 상상훈련 20회차): 카탈로그 ⟨열⟩ 은 **items 기준**인데
            # 조건 좌변은 봉투 최상위만 봤다. 같은 액션의 같은 개념이 두 이름이라
            # (sense:host — 봉투 `disk_root.percent` / items `disk_percent`) 카탈로그에
            # 적힌 이름으로 조건을 걸면 판정 불능이 되고 **else 까지 보류돼 문장이
            # 통째로 죽었다**. `cpu_percent` 만 두 곳 이름이 우연히 같아 교재 대표
            # 예시가 돌고 있었다. 액션마다 봉투에 미러를 넣는 대신(=액션 수만큼 반복될
            # 덧대기) 조건 언어가 통화를 보게 한다 — 어휘 증식 0, 전 액션 일반 적용.
            # ★1행일 때만: 여러 행이면 어느 행의 값인지 언어가 정할 수 없다(정직 실패 유지).
            _items = result.get("items") if isinstance(result, dict) else None
            if isinstance(_items, list) and len(_items) == 1 and isinstance(_items[0], dict):
                value = _extract_dotted_field_checked(_items[0], field)
        if value is _FIELD_MISSING:
            # F13-4 (2026-08-19 상상훈련 13회차): 사용 가능한 경로를 동반한다 —
            # filter/sort 오류문 선례. 없으면 자가교정에 단독 프로브 1왕복이 더 든다.
            hints = _field_path_hints(result)
            hint_txt = f" 사용 가능한 필드: {hints}" if hints else ""
            return None, (f"필드 경로 '.{field}' 가 결과에 없습니다 — 경로를 확인하세요"
                          f"(예: stock quote 는 .data.current_price — 봉투 최상위가 아닙니다).{hint_txt}")
        return value, None

    if isinstance(result, dict):
        # 경로 없는 소스 참조의 값: value → result → message(산문 emitter·AI 술어 [table:brief]
        # 의 계약, 2026-08-22 M2) → 봉투 문자열. 옛 str(result) 폴백은 brief 의 yes/no 를
        # '{"success": true, "message": "yes"}' 로 감싸 비교가 늘 거짓이 되게 했다.
        for _k in ("value", "result", "message"):
            if _k in result and result[_k] is not None:
                return result[_k], None
        return str(result), None
    return result, None


def _field_path_hints(result: Any, max_paths: int = 24) -> List[str]:
    """조건 소스 결과에서 쓸 수 있는 점 경로 후보 — 최상위 + 1단 중첩 (F13-4).

    스칼라 값 경로만 후보로 낸다(dict 중간 노드는 자식 경로가 대신 말한다).
    items 같은 리스트 키는 경로 폭발이라 이름만 싣는다.
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

    중간 노드가 null 이거나 dict 가 아니면 그 아래 경로는 "부재"다(★B10-case).
    """
    current = result
    for key in field_path.split('.'):
        if not isinstance(current, dict) or key not in current:
            return _FIELD_MISSING
        current = current[key]
    return current


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
