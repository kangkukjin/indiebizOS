"""data-ops 패키지 소유 정책 — 집계 관측·그룹 표시값·since 원장 키 형식.

값의 뜻(동등·순서·숫자 관측·집계 누산)은 common.value_semantics 한 벌이 소유한다.
이 모듈은 그 판정을 다시 정하지 않고, 패키지가 소유해야 하는 정책만 둔다:
집계 대상의 관측 의미(행 수/실존 수/유한 수치), 그룹 키의 엄격 JSON 표시,
since 원장의 저장 키 형식과 옛 str(dict) 키 호환. (Codex 흡수, 2026-08-26)
"""

import ast
import json
import math

from common.value_semantics import aggregate_numbers, group_identity, numeric_value


def persistent_keys(value):
    """since 원장용 (정본 키, 옛 str 키) — scalar 저장 형식은 그대로 보존한다.

    구조형 키를 str(dict) 로 저장하면 필드 순서가 키를 갈라 같은 실체가 거짓 new 로
    오보된다. 정본 키는 순서 독립 group_identity 의 JSON 직렬화다.
    """
    legacy = str(value)
    if not isinstance(value, (list, tuple, dict)):
        return legacy, legacy
    identity = group_identity(value)
    canonical = "\x1ejson:" + json.dumps(
        identity, ensure_ascii=False, separators=(",", ":"), default=str)
    return canonical, legacy


def legacy_persistent_alias(stored_key):
    """옛 str(list/dict) 원장 키를 가능할 때 현재 정본 키로 해석한다."""
    try:
        value = ast.literal_eval(stored_key)
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        return stored_key
    if not isinstance(value, (list, tuple, dict)):
        return stored_key
    return persistent_keys(value)[0]


def persisted_seen(rows):
    """원장 행을 현재 키와 옛 구조형 키의 정본 별칭으로 함께 색인한다."""
    seen, legacy = {}, {}
    for stored_key, watched in rows:
        seen[stored_key] = watched
        alias = legacy_persistent_alias(stored_key)
        if alias != stored_key:  # vj-ok: 정본 키 이관 내부 비교
            seen.setdefault(alias, watched)
            legacy.setdefault(alias, stored_key)
    return seen, legacy


def migrate_since_keys(conn, stream, canonical_key, legacy_key, legacy_seen):
    """구조형 키의 옛 순서 의존 원장 레코드를 읽은 뒤 정본 키로 점진 이관한다."""
    if legacy_key != canonical_key:  # vj-ok: 정본 키 이관 내부 비교
        conn.execute("DELETE FROM since_seen WHERE stream=? AND k=?",
                     (stream, legacy_key))
    old_stored_key = legacy_seen.get(canonical_key)
    if old_stored_key and old_stored_key != legacy_key:  # vj-ok: 정본 키 이관 내부 비교
        conn.execute("DELETE FROM since_seen WHERE stream=? AND k=?",
                     (stream, old_stored_key))


def aggregate_members(op, members, src):
    """집계 대상의 관측 의미 — 행 수/non-null 수/유한 수치를 한 벌로 판정한다.

    row_count(agg 생략)는 그룹의 행 수, count(열)는 그 열의 실존(non-null) 관측 수
    (G39-1·B40-3 — 둘을 섞으면 null 그룹 2행이 0 으로 나온다). 수치 집계는 유한
    관측만 세고 건너뛴 수를 함께 반환해 호출자가 침묵 제외를 신고하게 한다.
    반환값은 (value, skipped, error)."""
    if op == "row_count":
        return len(members), 0, None
    if op == "count":
        return sum(1 for member in members
                   if src in member and member.get(src) is not None), 0, None

    nums = []
    skipped = 0
    for member in members:
        value = member.get(src) if src in member else None
        number = numeric_value(value)
        if number is None:
            skipped += 1
            continue
        nums.append(number)
    if not nums:
        return None, skipped, None
    value, error = aggregate_numbers(op, nums)
    return value, skipped, error


def attach_group_reports(res, group_key_coercions, aggregation_skips, aggregation_errors):
    """groupby 결과 봉투에 침묵 제외·표시 강제·표현 불능 신고를 자백한다."""
    if not (isinstance(res, dict) and res.get("success", True)):
        return res

    def _warn(text):
        res["warning"] = f"{res['warning']} · {text}" if res.get("warning") else text

    if group_key_coercions:
        total = sum(item["nonfinite_parts"] for item in group_key_coercions)
        res["group_key_coercions"] = group_key_coercions
        _warn(f"groupby: 그룹 키 표시값의 NaN/Infinity 부분 {total}개를 엄격한 JSON "
              "문자열로 표시했습니다 — 세부는 group_key_coercions")
    if aggregation_skips:
        total = sum(item["skipped"] for item in aggregation_skips)
        res["aggregation_skips"] = aggregation_skips
        _warn(f"groupby: 수치 집계에서 결측·비수치·비유한 값 {total}건을 "
              "제외했습니다 — 세부는 aggregation_skips")
    if aggregation_errors:
        res["aggregation_errors"] = aggregation_errors
        _warn(f"groupby: 수치 집계 결과 {len(aggregation_errors)}칸을 유한 JSON 수로 "
              "표현할 수 없어 null 로 표시했습니다 — 세부는 aggregation_errors")
    return res


def strict_json_value(value):
    """NaN/Infinity 를 엄격 JSON 문자열로 바꾸고 바뀐 원소 수를 함께 돌려준다."""
    if isinstance(value, float) and not math.isfinite(value):
        if math.isnan(value):
            return "NaN", 1
        return ("Infinity" if value > 0 else "-Infinity"), 1
    if isinstance(value, (list, tuple)):
        out, changed = [], 0
        for item in value:
            safe, count = strict_json_value(item)
            out.append(safe)
            changed += count
        return out, changed
    if isinstance(value, dict):
        if any(isinstance(key, float) and not math.isfinite(key) for key in value):
            # JSON object key 에는 NaN/Infinity 가 올 수 없다. 문자열로 덮으면 기존
            # "NaN" 키와 충돌하므로 pair 표현으로 바꿔 모든 항목을 보존한다.
            pairs, changed = [], 0
            for key, item in value.items():
                safe_key, key_count = strict_json_value(key)
                safe_item, item_count = strict_json_value(item)
                pairs.append([safe_key, safe_item])
                changed += key_count + item_count
            return {"$object_pairs": pairs}, changed
        out, changed = {}, 0
        for key, item in value.items():
            safe, count = strict_json_value(item)
            out[key] = safe
            changed += count
        return out, changed
    return value, 0
