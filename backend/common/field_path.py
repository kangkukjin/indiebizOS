"""점 경로 해석의 단일 코어 — "경로가 가리키는 값"의 뜻은 여기 한 벌만 둔다.

왜: 같은 뜻의 워커가 5개 방언으로 갈라져 있었다(2026-08-27 census) —
블록 술어 walk_path(dict 키+리스트 숫자 인덱스·결측=_MISSING) ·
api_transforms 추출기(대괄호 문법·XML 폴백·`.0.` 미지원) ·
api_transforms _get_nested(dict 전용·인덱스 없음) ·
workflow_binding $변수 추출(숫자 인덱스·정직 오류) · data-ops flatten _dig(dict 전용).
같은 경로 "items.0.title" 이 표면마다 다른 답(값/None/오류)을 냈다 — 값 의미론과
같은 속(한 낱말 한 판결)의 구조 접근판이다.

계약:
  · 문법 = 점 분리. 숫자 조각은 **리스트에서만** 인덱스다(dict 의 "0" 키는 문자열 키 우선
    — 블록 술어의 기존 문서화된 계약을 전 표면의 정본으로 삼는다).
  · 대괄호(`data[0].name`)는 응답 변환(response 블록) 전용 확장 — `brackets=True` 로만 켠다.
    다른 표면의 경로 문법을 넓히는 것은 언어 개정이므로 여기서 하지 않는다.
  · 결측은 MISSING 표지 — 값 null 과 구별한다. 결측을 어떻게 말할지(오류/None/보류)는
    호출자 정책이다(value_semantics 가 판정 불능을 호출자 번역에 맡기는 것과 동일).
  · 한 단계 실패 시 fallback(현재값, 조각) 훅 — 도메인 폴백(XML 중첩 태그 탐색)은
    호출자 정책이지 경로 문법이 아니다.
"""

import re
from typing import Any, Callable, List, Optional, Union

MISSING = object()          # 경로 부재 표지 (값 null 과 구별)

_BRACKET_SEG = re.compile(r"^(\w*)(?:\[(\d+)\])?$")


def parse_path(path: str, *, brackets: bool = False) -> List[Union[str, int]]:
    """경로 문자열 → 조각 목록. 조각은 str(키/숫자문자열) 또는 int(대괄호 인덱스).

    숫자 조각은 str 로 남긴다 — dict 의 "0" 키와 리스트 인덱스를 걷는 시점에
    구별해야 하기 때문(int 로 미리 접으면 {"0": x} 를 잃는다).
    """
    parts: List[Union[str, int]] = []
    for segment in str(path or "").lstrip(".").split("."):
        if not segment:
            continue
        if brackets:
            m = _BRACKET_SEG.match(segment)
            if m and m.group(2) is not None:
                name, idx = m.groups()
                if name:
                    parts.append(name)
                parts.append(int(idx))
                continue
        parts.append(segment)
    return parts


def walk_path(obj: Any, path: str, *, brackets: bool = False,
              fallback: Optional[Callable[[Any, str], Any]] = None,
              on_missing: Optional[Callable[[Any, Union[str, int]], Any]] = None) -> Any:
    """경로를 걷는다. 결측이면 MISSING(또는 on_missing 의 반환/예외).

    한 단계의 판정 순서: dict 문자열 키 → 리스트 숫자 인덱스 → fallback → 결측.
    int 조각(대괄호)은 리스트 인덱스만 뜻한다(dict 에는 결측 — 기존 추출기 계약).

    `*` 조각 = 열 벡터 사상 (언어 개정 2026-08-28, 사용자 판정 "언어의 한계는 다 고쳐"):
    리스트의 각 원소에 나머지 경로를 적용해 목록을 낸다 — `$성공.items.*.video_id` 가
    id 벡터(원형 list)가 되어 not_in 안티조인의 value 로 들어간다. 계약:
      · dict 에 문자열 키 "*" 가 실제로 있으면 그 키가 우선(기존 판정 순서 보존).
      · 리스트가 아니면 결측(억지 사상 없음).
      · 원소별 결측은 None 자리 유지($items.field 바인딩 선례 — 위치 보존),
        단 **전 원소 결측이면 정직 오류**(오타가 침묵 [] 로 새는 것 방지).
    """
    return _walk_parts(obj, parse_path(path, brackets=brackets), path,
                       fallback=fallback, on_missing=on_missing)


def _walk_parts(cur: Any, parts: List[Union[str, int]], path: str, *,
                fallback: Optional[Callable[[Any, str], Any]] = None,
                on_missing: Optional[Callable[[Any, Union[str, int]], Any]] = None) -> Any:
    for i, seg in enumerate(parts):
        nxt = MISSING
        if isinstance(seg, int):
            if isinstance(cur, list) and 0 <= seg < len(cur):
                nxt = cur[seg]
        elif isinstance(cur, dict):
            if seg in cur:
                nxt = cur[seg]
        elif seg == "*" and isinstance(cur, list):
            rest = parts[i + 1:]
            if not rest:
                return list(cur)
            mapped = [_walk_parts(el, rest, path, fallback=fallback, on_missing=None)
                      for el in cur]
            if cur and all(v is MISSING for v in mapped):
                if on_missing is not None:
                    return on_missing(cur, ".".join(str(p) for p in rest))
                return MISSING
            return [None if v is MISSING else v for v in mapped]
        elif isinstance(cur, list) and isinstance(seg, str) and seg.isdigit() and int(seg) < len(cur):
            nxt = cur[int(seg)]
        if nxt is MISSING and fallback is not None and isinstance(seg, str):
            found = fallback(cur, seg)
            if found is not None:
                nxt = found
        if nxt is MISSING:
            if on_missing is not None:
                return on_missing(cur, seg)
            return MISSING
        cur = nxt
    return cur
