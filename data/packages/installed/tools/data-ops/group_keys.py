"""group_keys.py — 관계 키 어휘 한 벌 (handler.py 에서 분할, 1500줄 관문).

관계대수의 키 자리 — γ(groupby)·τ(sort)·δ(dedup)·⋈(join) 가 무엇을 "같은 것"으로
보는지의 판정이 여기 모인다. 값의 뜻(동등·순서) 자체는 common.value_semantics 가
소유하고, 이 모듈은 그 판정을 **키 자리의 문법**으로 옮긴다:

  · key_names   — 키 자리 값 → 키 이름 목록 (2026-09-07 언어 개정: 스칼라 | 복합키 목록)
  · join_key / join_row_key / join_keys — 조인 키(빈 값은 키가 아니다)
  · dedup_key   — 중복 판정 키(부분이 비면 중복 판정 밖)
  · sort_multi  — 다단계 정렬(안정 정렬을 덜 중요한 키부터 겹친다)

handler 가 load_sibling 으로 붙여 이름을 재수출하므로 기존 호출부는 그대로다.
"""

from common.value_semantics import group_identity, relation_identity


__all__ = ["group_identity", "relation_identity", "norm_key", "join_key",
           "join_row_key", "join_keys", "key_names", "dedup_key", "sort_multi"]



def norm_key(s):
    """B38 falsey 스칼라 보존 + B41 구조 키의 재귀적·순서 독립 정규화."""
    return relation_identity(s)


def join_key(value):
    """join 가능한 정규화 키. null·빈/공백 문자열은 관계 식별자가 아니다.

    B38-2·G38-1(2026-08-25): items 경로는 null 을 빼고 table 경로는 ``""`` 로
    조인했으며, 빈 문자열은 양쪽 모두에서 서로 연결됐다. 외부 자료의 빈 ID 둘을 같은
    실체로 묶는 거짓 양성을 막기 위해 모든 통화 모양이 이 판정 한 벌을 쓴다.
    """
    key = norm_key(value)
    return key if key else None


def join_row_key(values):
    """복합 조인키 — 부분이 하나라도 관계 식별자가 아니면 그 행은 조인 대상 밖.

    `join_key` 의 판정(null·빈/공백 문자열은 키가 아니다)을 부분마다 적용한다:
    키 일부가 비어 있는 두 행을 같은 실체로 묶으면 복합키를 쓴 이유가 사라진다.
    """
    parts = [join_key(v) for v in values]
    return tuple(parts) if all(p is not None for p in parts) else None


def join_keys(row, keys):
    """행 dict 에서 복합 조인키."""
    return join_row_key([row.get(k) for k in keys])


def key_names(raw, verb, slot="by"):
    """키 자리(by/on) 값 → 키 이름 목록 (언어 개정 2026-09-07 — 키 자리는 속성 집합).

    관계대수의 γ(groupby)·τ(sort)·δ(dedup)·⋈(join) 는 키를 스칼라가 아니라
    **속성 집합**으로 받는다. 스칼라 전용이던 옛 판에서 복합키 문장
    `[table:groupby]{by: ["아파트명","계약유형"]}`(단지×유형 교차집계)은 타입 관문에서
    "목록의 항목마다 실행하려면 each" 로 거절됐다 — 그 처방은 이 자리에서 틀렸다
    (each 로 돌리면 키마다 따로 그룹핑돼 의도와 다른 답이 success 로 나간다).
    실측 2회: ep2532(09-01)·ep2951(09-07), 둘 다 부동산 보고서.

    반환 (keys, error). 빈 값은 ([], None) — "필요합니다" 판정은 호출자 몫이다
    (dedup 만 기본 키를 허용하므로 여기서 한 벌로 못 정한다).
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return [], None
    if isinstance(raw, dict):
        return [], {"success": False,
                    "error": f"{verb}: {slot} 에는 열 이름(또는 복합키 목록)이 와야 하는데 사전이 왔습니다."}
    if not isinstance(raw, (list, tuple)):
        return [str(raw)], None
    if not raw:
        return [], {"success": False,
                    "error": f"{verb}: {slot} 가 빈 목록입니다 — 키 열 이름을 하나 이상 적으세요."}
    keys = []
    for k in raw:
        if isinstance(k, (list, tuple, dict)):
            return [], {"success": False,
                        "error": f"{verb}: {slot} 목록의 항목은 열 이름(문자열)이어야 합니다 — "
                                 f"중첩된 {'목록' if isinstance(k, (list, tuple)) else '사전'}이 왔습니다."}
        name = str(k).strip()
        if not name:
            return [], {"success": False, "error": f"{verb}: {slot} 목록에 빈 이름이 있습니다."}
        if name in keys:
            # 같은 열을 두 번 적으면 groupby 는 같은 열을 두 번 내고 join 은 조건을 두 번
            # 건다 — 조용히 접으면 사용자가 적은 것과 다른 문장이 된다(⑧′ 부류).
            return [], {"success": False,
                        "error": f"{verb}: {slot} 에 '{name}' 이 두 번 나옵니다 — 복합키의 열은 서로 달라야 합니다."}
        keys.append(name)
    return keys, None


def dedup_key(values):
    """복합 중복키 — 부분이 하나라도 키가 아니면(빈 값·공백) 그 행은 중복 판정 밖.

    단일 키 규약(`if k and k in seen`)의 확장이다: 빈 ID 둘을 같은 실체로 묶는 거짓
    양성을 막는 `join_key` 의 판정과 같은 방향 — 다만 dedup 은 키 없는 행을
    *버리지 않고* 통과시킨다(옛 계약 그대로).
    """
    parts = [norm_key(v) for v in values]
    return tuple(parts) if all(parts) else None


def sort_multi(records, keys, desc, sort_one):
    """다단계 정렬 — 키 목록의 **뒤에서 앞으로** 안정 정렬을 겹친다(2026-09-07 개정).

    한 벌짜리 복합 키 함수를 새로 만들지 않는 이유: 주입받는 단일 키 정렬기(sort_one)는 수치·날짜·
    문자열·결측의 버킷 순서를 고정하고 버킷 *안* 에서만 방향을 뒤집는 계약을 갖는다.
    복합 키로 그 판정을 다시 짜면 단일 키 정렬과 두 벌이 되어 갈라진다 — 안정 정렬을
    겹치면 같은 판정 한 벌로 다단계가 나온다(desc 는 전 키에 같이 걸린다;
    방향을 섞으려면 덜 중요한 키부터 sort 를 두 번 잇는다).
    """
    out = list(records)
    for k in reversed(keys):
        out = sort_one(out, k, desc)
    return out
