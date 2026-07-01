"""data-ops — 통화→통화 변환자 (currency algebra).

IBL의 깊이(depth)를 만드는 부품. 생산자(sense:* 등)가 내는 공유 통화를 입력으로,
같은 통화를 출력하는 닫힌(closure) 동사들. >> 파이프로 임의 깊이 조합:

    [sense:realty]{...} >> [table:filter]{where:"전세"} >> [table:sort]{by:price} >> [table:take]{n:5}

각 동사는 도메인에 무관 — 한 번 짜서 34개 생산자 × 임의 깊이에 곱해진다. 이 파일이
없던 시절엔 sort/top-N/dedup이 ~19개 핸들러에 사적으로 중복 구현돼 있었다(부채 회수).

통화 (단일):
  - items = {"items": [ {…열린 필드…} ]}  — 유일한 컬렉션 통화(2026-06-27 컷오버 완료).
    목록형·table 모두 items로 수렴. table(columns/rows)은 items의 파생 뷰(_get_table 가 items→table 재구성).
    변환자는 내부에서 행 dict(=items)로 정규화해 도메인·통화종류 무관하게 한 코드로 처리한다.

단항(filter/sort/take/select/dedup/groupby)·이항(join/union/merge, & 병렬 두 입력) 모두 구현됨.
"""

import json
import re


# ───────────────────────── 통화 추출/주입 (공유) ─────────────────────────

def _parse_prev(prev):
    """_prev_result(JSON 문자열 또는 dict/list) → 파이썬 객체."""
    if prev is None:
        return None
    if isinstance(prev, (dict, list)):
        return prev
    if isinstance(prev, str):
        try:
            return json.loads(prev)
        except Exception:
            return None
    return None


def _get_records(obj):
    """객체에서 항목 리스트를 꺼낸다.

    단일 통화 `items`가 유일한 키다(2026-06-27 컷오버 완료 — records 생산자 0). 모든 생산자가
    native 풍부 dict를 items로 방출하므로 records가 버리던 필드까지 in-pipe로 흐른다
    (예: zigbang lat/lng, business level). dict/list 가 아니면 통화 아님으로 (None, None) 반환.

    반환: (items_list, envelope_dict)  — envelope에 변환 결과를 다시 끼워 비파괴 반환용.
    """
    if isinstance(obj, dict):
        r = obj.get("items")            # 단일 통화 — 모든 생산자가 items 방출(2026-06-27 컷오버 완료, records 생산자 0)
        if isinstance(r, list):
            return r, obj
    if isinstance(obj, list):
        return obj, {"items": obj}
    return None, None


def _get_table(obj):
    """객체에서 표준 table 통화를 꺼낸다. ({table:{columns,rows}} 또는 최상위 columns/rows)

    반환: (table_dict, envelope_dict).
    """
    if isinstance(obj, dict):
        t = obj.get("table")
        if isinstance(t, dict) and isinstance(t.get("rows"), list):
            return {"columns": t.get("columns") or [], "rows": t["rows"]}, obj
        if isinstance(obj.get("rows"), list) and isinstance(obj.get("columns"), list):
            return {"columns": obj["columns"], "rows": obj["rows"]}, obj
        # 단일 통화 items(행 dict) → table 재구성: 첫 dict의 키 순서=열, 값=행(§3 table 흡수).
        items = obj.get("items")
        if isinstance(items, list) and items and all(isinstance(x, dict) for x in items):
            cols = list(items[0].keys())
            return {"columns": cols, "rows": [[d.get(c) for c in cols] for d in items]}, obj
    return None, None


def _emit_records(envelope, new_records):
    """변환된 항목들을 원 envelope에 비파괴로 끼워 반환.

    단일 통화 키 `items`로 내보낸다(2026-06-27 컷오버 완료 — 옛 records dual-emit 은퇴).
    """
    out = dict(envelope) if isinstance(envelope, dict) else {}
    out.pop("message", None)            # 변환 후 stale·O(items) 산문 제거 (파이프 블로업·정합성)
    out["items"] = new_records          # 단일 통화
    out["count"] = len(new_records)
    out.setdefault("success", True)
    return out


def _emit_table(envelope, new_table):
    out = dict(envelope) if isinstance(envelope, dict) else {}
    out.pop("message", None)            # 변환 후 stale 산문 제거
    if "table" in out:
        out["table"] = new_table
    else:
        out["columns"] = new_table.get("columns", [])
        out["rows"] = new_table.get("rows", [])
    out.setdefault("success", True)
    return out


def _row_dicts(table):
    """table rows → [{col: val}] (where/sort/dedup이 records와 같은 코드 쓰도록)."""
    cols = table.get("columns") or []
    out = []
    for r in table.get("rows") or []:
        d = {}
        for i, c in enumerate(cols):
            d[str(c)] = r[i] if i < len(r) else None
        out.append(d)
    return out


# ───────────────────────── where 미니 DSL ─────────────────────────

_OPS = {
    "==": lambda a, b: _num_eq(a, b),
    "eq": lambda a, b: _num_eq(a, b),
    "!=": lambda a, b: not _num_eq(a, b),
    "ne": lambda a, b: not _num_eq(a, b),
    "<": lambda a, b: _num_cmp(a, b) < 0,
    "lt": lambda a, b: _num_cmp(a, b) < 0,
    "<=": lambda a, b: _num_cmp(a, b) <= 0,
    "le": lambda a, b: _num_cmp(a, b) <= 0,
    ">": lambda a, b: _num_cmp(a, b) > 0,
    "gt": lambda a, b: _num_cmp(a, b) > 0,
    ">=": lambda a, b: _num_cmp(a, b) >= 0,
    "ge": lambda a, b: _num_cmp(a, b) >= 0,
    "contains": lambda a, b: str(b).lower() in str(a).lower(),
    "in": lambda a, b: (a in b) if isinstance(b, (list, tuple, set)) else (str(a).lower() in str(b).lower()),
}


def _as_num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except Exception:
        return None


def _num_eq(a, b):
    na, nb = _as_num(a), _as_num(b)
    if na is not None and nb is not None:
        return na == nb
    return str(a).strip().lower() == str(b).strip().lower()


def _num_cmp(a, b):
    na, nb = _as_num(a), _as_num(b)
    if na is not None and nb is not None:
        return (na > nb) - (na < nb)
    sa, sb = str(a), str(b)
    return (sa > sb) - (sa < sb)


_CMP_RE = re.compile(r"^\s*(.+?)\s*(>=|<=|==|!=|>|<|=)\s*(.+?)\s*$")


def _match(item, where):
    """item(dict) 이 where 조건을 만족하나.

    where 형태:
      - str "필드 op 값"  : 비교 연산자(>= <= > < == != =)가 있으면 단일 비교로 파싱
                            (예 "연도 >= 2000" → {field:연도, op:>=, value:2000}).
                            모델이 자연스럽게 쓰는 SQL식 문자열을 침묵 부분일치로 삼키지 않는다.
      - str S            : 연산자 없으면 아무 필드 값에 S가 부분일치 (전 필드 substring)
      - {field, op, value}: SQL식 단일 조건 (op 기본 ==; field=col/column 별칭)
      - {col: value, ...}: 각 열=값 동등(AND) 단축형
      - [cond, cond, ...]: AND 결합
    """
    if where is None or where == "":
        return True
    if isinstance(where, str):
        m = _CMP_RE.match(where)
        if m:  # 비교 연산자가 든 문자열 → 단일 비교로 해석 (침묵 부분일치 함정 제거)
            field, op, val = m.group(1).strip(), m.group(2), m.group(3).strip()
            if op == "=":
                op = "=="
            if len(val) >= 2 and val[0] in "\"'" and val[-1] == val[0]:
                val = val[1:-1]  # 따옴표 제거
            fn = _OPS.get(op, _OPS["=="])
            return fn(item.get(field), val)
        s = where.lower()
        return any(s in str(v).lower() for v in item.values())
    if isinstance(where, list):
        return all(_match(item, w) for w in where)
    if isinstance(where, dict):
        field = where.get("field") or where.get("col") or where.get("column")
        if field is not None:  # 구조형 {field, op, value}
            op = str(where.get("op", "==")).lower()
            val = where.get("value")
            fn = _OPS.get(op, _OPS["=="])
            return fn(item.get(str(field)), val)
        # 단축형 {col: value, ...} — 모두 동등(AND)
        return all(_num_eq(item.get(str(k)), v) for k, v in where.items())
    return True


# ───────────────────────── sort 키 (수치 인식) ─────────────────────────

def _sort_key(field):
    def key(item):
        v = item.get(str(field)) if isinstance(item, dict) else None
        n = _as_num(v)
        # 숫자 먼저(0) 안정 정렬, 그다음 문자열(1). None은 맨 뒤.
        if v is None:
            return (2, 0.0, "")
        if n is not None:
            return (0, n, "")
        return (1, 0.0, str(v).lower())
    return key


# ───────────────────────── 단항 동사 ─────────────────────────

def _op_filter(prev, params):
    """records|table → 부분집합. params.where (미니 DSL). condition 별칭 수용."""
    where = params.get("where") or params.get("condition")
    recs, env = _get_records(prev)
    if recs is not None:
        return _emit_records(env, [r for r in recs if isinstance(r, dict) and _match(r, where)])
    table, env = _get_table(prev)
    if table is not None:
        kept = [d for d in _row_dicts(table) if _match(d, where)]
        cols = table.get("columns") or []
        rows = [[d.get(str(c)) for c in cols] for d in kept]
        return _emit_table(env, {"columns": cols, "rows": rows})
    return {"error": "filter: 입력에서 records/table 통화를 찾지 못했습니다."}


def _op_sort(prev, params):
    """records|table → 정렬. params.by(필드/열명), params.desc(bool)."""
    by = params.get("by")
    desc = bool(params.get("desc", False))
    if not by:
        return {"error": "sort: by(정렬 기준 필드/열명)가 필요합니다."}
    recs, env = _get_records(prev)
    if recs is not None:
        srt = sorted([r for r in recs if isinstance(r, dict)], key=_sort_key(by), reverse=desc)
        return _emit_records(env, srt)
    table, env = _get_table(prev)
    if table is not None:
        dicts = _row_dicts(table)
        dicts.sort(key=_sort_key(by), reverse=desc)
        cols = table.get("columns") or []
        rows = [[d.get(str(c)) for c in cols] for d in dicts]
        return _emit_table(env, {"columns": cols, "rows": rows})
    return {"error": "sort: 입력에서 records/table 통화를 찾지 못했습니다."}


def _op_take(prev, params):
    """records|table → 상위 n. params.n (기본 10). 음수면 뒤에서 n개."""
    n = params.get("n", params.get("limit", 10))
    try:
        n = int(n)
    except Exception:
        n = 10
    recs, env = _get_records(prev)
    if recs is not None:
        sliced = recs[n:] if n < 0 else recs[:n]
        return _emit_records(env, sliced)
    table, env = _get_table(prev)
    if table is not None:
        rows = table.get("rows") or []
        sliced = rows[n:] if n < 0 else rows[:n]
        return _emit_table(env, {"columns": table.get("columns") or [], "rows": sliced})
    return {"error": "take: 입력에서 records/table 통화를 찾지 못했습니다."}


def _op_select(prev, params):
    """table → 열 투영. params.columns(남길 열 이름 배열). records는 필드 추림."""
    cols_keep = params.get("columns") or params.get("cols") or params.get("fields")
    if not cols_keep:
        return {"error": "select: columns(남길 열/필드 이름 배열)가 필요합니다."}
    cols_keep = [str(c) for c in cols_keep]
    table, env = _get_table(prev)
    if table is not None:
        src_cols = [str(c) for c in (table.get("columns") or [])]
        idx = [src_cols.index(c) for c in cols_keep if c in src_cols]
        new_cols = [src_cols[i] for i in idx]
        new_rows = [[(r[i] if i < len(r) else None) for i in idx] for r in (table.get("rows") or [])]
        return _emit_table(env, {"columns": new_cols, "rows": new_rows})
    recs, env = _get_records(prev)
    if recs is not None:
        out = [{k: r.get(k) for k in cols_keep if k in r} for r in recs if isinstance(r, dict)]
        return _emit_records(env, out)
    return {"error": "select: 입력에서 records/table 통화를 찾지 못했습니다."}


def _norm(s):
    import re
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _op_dedup(prev, params):
    """records|table → 중복 제거(첫 항목 유지). params.by(키 필드/열, 기본 title).

    by 미지정 시 records는 title, table은 첫 열을 키로. 정규화(공백/대소문자) 후 동등 비교.
    (newspaper 내부에 묻혀있던 _dedup_rank를 통화 동사로 끌어올림 — 전 생산자 공용화.)
    """
    by = params.get("by")
    recs, env = _get_records(prev)
    if recs is not None:
        key = by or "title"
        seen, out = set(), []
        for r in recs:
            if not isinstance(r, dict):
                continue
            k = _norm(r.get(key))
            if k and k in seen:
                continue
            seen.add(k)
            out.append(r)
        return _emit_records(env, out)
    table, env = _get_table(prev)
    if table is not None:
        cols = [str(c) for c in (table.get("columns") or [])]
        ki = cols.index(str(by)) if (by and str(by) in cols) else 0
        seen, rows = set(), []
        for r in table.get("rows") or []:
            k = _norm(r[ki] if ki < len(r) else None)
            if k and k in seen:
                continue
            seen.add(k)
            rows.append(r)
        return _emit_table(env, {"columns": cols, "rows": rows})
    return {"error": "dedup: 입력에서 records/table 통화를 찾지 못했습니다."}


_AGG = {
    "count": lambda vs: len(vs),
    "sum": lambda vs: round(sum(_as_num(v) or 0 for v in vs), 6),
    "avg": lambda vs: round(sum(_as_num(v) or 0 for v in vs) / len(vs), 6) if vs else 0,
    "min": lambda vs: min((_as_num(v) for v in vs if _as_num(v) is not None), default=None),
    "max": lambda vs: max((_as_num(v) for v in vs if _as_num(v) is not None), default=None),
}


def _rows_for_field(obj, field):
    """그룹/집계 키 field 를 실제로 담은 표현을 골라 list-of-dicts 로 반환.

    공유 통화(table/records) 외에도 도메인 생산자가 원천 행을 담는 흔한 키
    (data/items/results)까지 후보로 본다. records 투영이 도메인 필드를 접어버려
    groupby 가 그 필드를 못 찾는 문제(예: realty records 가 '법정동'을 meta 문자열로
    접음 — 원천은 data:[{...법정동...}] 에 그대로 있음)를 푼다.

    후보 중 field 를 가진 첫 리스트를 우선(없으면 첫 비어있지 않은 리스트)으로 고른다.
    """
    cands = []  # [(키, list-of-dicts)]
    if isinstance(obj, list):
        cands.append(("(root)", [x for x in obj if isinstance(x, dict)]))
    elif isinstance(obj, dict):
        t, _ = _get_table(obj)
        if t is not None:
            cands.append(("table", _row_dicts(t)))
        for k in ("data", "items", "results", "records"):
            v = obj.get(k)
            if isinstance(v, list) and any(isinstance(x, dict) for x in v):
                cands.append((k, [x for x in v if isinstance(x, dict)]))
    if not cands:
        return None
    if field:
        for _, rows in cands:
            if any(field in r for r in rows):
                return rows
    for _, rows in cands:
        if rows:
            return rows
    return cands[0][1]


def _op_groupby(prev, params):
    """records|table|도메인 행목록 → 그룹 집계. params.by(그룹 키), params.agg.

    agg 형태: {새열명: [op, 원본열]} 또는 {원본열: op}. op = count/sum/avg/min/max.
    기본: agg 없으면 그룹별 count.  반환 table = [by열, 집계열들].

    형제 동사들처럼 records 도 받는다. 나아가 records 투영이 그룹 키를 접은 경우
    원천 data/items 행까지 거슬러 키를 찾는다(_rows_for_field).
    """
    by = params.get("by") or params.get("key") or params.get("group_by")
    if not by:
        return {"error": "groupby: by(그룹 키 열)가 필요합니다."}
    by = str(by)
    dicts = _rows_for_field(prev, by)
    if not dicts:
        return {"error": "groupby: 입력에서 records/table 통화(또는 data/items 행 목록)를 찾지 못했습니다."}
    _, env = _get_table(prev)
    env = env or {}
    agg = params.get("agg")
    # agg 정규화 → [(out_col, op, src_col)]
    specs = []
    if isinstance(agg, dict):
        for k, v in agg.items():
            if isinstance(v, (list, tuple)) and len(v) == 2:  # {새열: [op, 원본열]}
                specs.append((str(k), str(v[0]).lower(), str(v[1])))
            else:  # {원본열: op}
                specs.append((f"{v}_{k}", str(v).lower(), str(k)))
    if not specs:
        specs = [("count", "count", by)]
    # 그룹핑 (입력 순서 보존)
    groups, order = {}, []
    for d in dicts:
        gk = d.get(by)
        if gk not in groups:
            groups[gk] = []
            order.append(gk)
        groups[gk].append(d)
    out_cols = [by] + [s[0] for s in specs]
    out_rows = []
    for gk in order:
        members = groups[gk]
        row = [gk]
        for out_col, op, src in specs:
            vals = [m.get(src) for m in members]
            fn = _AGG.get(op, _AGG["count"])
            row.append(fn(vals))
        out_rows.append(row)
    return _emit_table(env, {"columns": out_cols, "rows": out_rows})


# ───────────────────────── 이항 동사 (& 병렬 두 입력) ─────────────────────────

def _extract_two(prev):
    """& 병렬 결과에서 두 객체 추출.

    prev = [elem0, elem1] (각 elem은 dict 또는 JSON 문자열 — 병렬 분기 결과).
    반환: (obj0, obj1) 둘 다 dict/list로 파싱. 부족하면 (None, None).
    """
    if not isinstance(prev, list) or len(prev) < 2:
        return None, None

    def _parse_elem(e):
        if isinstance(e, str):
            try:
                return json.loads(e)
            except Exception:
                return None
        return e

    return _parse_elem(prev[0]), _parse_elem(prev[1])


def _op_union(prev, params):
    """두 table(또는 두 records)을 행 결합. 같은 통화끼리. params 없음.

    table: 열 이름으로 통합(순서 보존, 한쪽에만 있는 열은 다른쪽 None). records: 단순 concat.
    중복 제거가 필요하면 뒤에 >> dedup.
    """
    a, b = _extract_two(prev)
    if a is None or b is None:
        return {"error": "union: & 병렬로 두 입력이 필요합니다. 예: [A] & [B] >> [table:union]"}
    ta, _ = _get_table(a)
    tb, _ = _get_table(b)
    if ta is not None and tb is not None:
        cols = [str(c) for c in (ta.get("columns") or [])]
        for c in (tb.get("columns") or []):
            if str(c) not in cols:
                cols.append(str(c))

        def remap(t):
            tcols = [str(c) for c in (t.get("columns") or [])]
            out = []
            for r in t.get("rows") or []:
                d = {tcols[i]: (r[i] if i < len(r) else None) for i in range(len(tcols))}
                out.append([d.get(c) for c in cols])
            return out

        return _emit_table({"table": {}}, {"columns": cols, "rows": remap(ta) + remap(tb)})
    ra, _ = _get_records(a)
    rb, _ = _get_records(b)
    if ra is not None and rb is not None:
        return _emit_records({}, list(ra) + list(rb))
    return {"error": "union: 두 입력의 통화 종류가 같아야 합니다(둘 다 table 또는 둘 다 records)."}


def _op_merge(prev, params):
    """두 records를 합친다(concat). params.by 지정 시 그 키로 중복 제거.

    여러 검색 결과를 한 목록으로 모을 때. (table 결합은 union.)
    """
    a, b = _extract_two(prev)
    if a is None or b is None:
        return {"error": "merge: & 병렬로 두 records 입력이 필요합니다. 예: [A] & [B] >> [table:merge]"}
    ra, _ = _get_records(a)
    rb, _ = _get_records(b)
    if ra is None or rb is None:
        return {"error": "merge: 두 입력 모두 records 통화여야 합니다(표형 결합은 table:union)."}
    out = list(ra) + list(rb)
    by = params.get("by")
    if by or params.get("dedup"):
        key = by or "title"
        seen, dd = set(), []
        for r in out:
            if not isinstance(r, dict):
                continue
            k = _norm(r.get(key))
            if k and k in seen:
                continue
            seen.add(k)
            dd.append(r)
        out = dd
    return _emit_records({}, out)


def _suffix_collisions(base_cols, add_cols):
    """add_cols 이름이 base_cols(또는 서로)와 충돌하면 _2,_3.. 접미사 — *표시 이름만*.
    (읽기는 원본 이름으로 따로 한다. 동명 열이 겹치면 다운스트림 select/sort가 이름으로
     둘째 열을 못 집어 조용히 첫째를 오선택하는 침묵 함정을 막는다.)"""
    used = set(base_cols)
    out = []
    for c in add_cols:
        name = c
        if name in used:
            i = 2
            while f"{c}_{i}" in used:
                i += 1
            name = f"{c}_{i}"
        used.add(name)
        out.append(name)
    return out


def _op_join(prev, params):
    """두 table을 키 열로 inner join. params.on(양쪽 공통 키 열명, 필수).

    결과 열 = 좌측 전체 + 우측(키 제외). 서로 다른 소스를 한 키로 묶어 분석.
    예: [sense:stock]{op:history} & [sense:world_bank]{...} >> [table:join]{on: "연도"}.
    """
    on = params.get("on") or params.get("key")
    if not on:
        return {"error": "join: on(조인 키 열 이름)이 필요합니다."}
    on = str(on)
    a, b = _extract_two(prev)
    if a is None or b is None:
        return {"error": "join: & 병렬로 두 table 입력이 필요합니다. 예: [A] & [B] >> [table:join]{on: \"연도\"}"}
    ta, _ = _get_table(a)
    tb, _ = _get_table(b)
    if ta is None or tb is None:
        # 두 입력이 records 통화면 records inner join (table 분기와 대칭).
        # records 도 dict 라 키 필드로 조인 가능 — merge/union 이 records 를 받는 것과 일관.
        ra, _ = _get_records(a)
        rb, _ = _get_records(b)
        if ra is None or rb is None:
            return {"error": "join: 두 입력이 같은 통화여야 합니다(둘 다 table 또는 둘 다 records)."}
        index = {}
        for r in rb:
            if isinstance(r, dict) and r.get(on) is not None:
                index.setdefault(_norm(r.get(on)), []).append(r)
        out = []
        for l in ra:
            if not isinstance(l, dict) or l.get(on) is None:
                continue
            lkeys = list(l.keys())
            for r in index.get(_norm(l.get(on)), []):
                add = [k for k in r.keys() if k != on]
                disp = _suffix_collisions(lkeys, add)  # 동명 필드 _2 (침묵 오선택 방지)
                merged = dict(l)
                for orig, name in zip(add, disp):
                    merged[name] = r[orig]
                out.append(merged)
        return _emit_records({}, out)
    ca = [str(c) for c in (ta.get("columns") or [])]
    cb = [str(c) for c in (tb.get("columns") or [])]
    if on not in ca or on not in cb:
        return {"error": f"join: 키 '{on}'이 양쪽 table 열에 모두 있어야 합니다(좌:{ca} 우:{cb})."}
    lki, rki = ca.index(on), cb.index(on)
    # 우측을 키로 인덱싱
    index = {}
    for r in tb.get("rows") or []:
        k = _norm(r[rki] if rki < len(r) else None)
        index.setdefault(k, []).append(r)
    extra = [c for c in cb if c != on]  # 우측에서 가져올 열(키 제외, 읽기는 원본 이름)
    out_cols = ca + _suffix_collisions(ca, extra)  # 표시 이름만 충돌 회피
    out_rows = []
    for r in ta.get("rows") or []:
        k = _norm(r[lki] if lki < len(r) else None)
        for rb_row in index.get(k, []):
            rbd = {cb[i]: (rb_row[i] if i < len(rb_row) else None) for i in range(len(cb))}
            out_rows.append(list(r) + [rbd.get(c) for c in extra])
    return _emit_table({"table": {}}, {"columns": out_cols, "rows": out_rows})


_DISPATCH = {
    "data_filter": _op_filter,
    "data_sort": _op_sort,
    "data_take": _op_take,
    "data_select": _op_select,
    "data_dedup": _op_dedup,
    "data_groupby": _op_groupby,
    "data_join": _op_join,
    "data_union": _op_union,
    "data_merge": _op_merge,
}


def execute(tool_input: dict, context):
    """표준 시그니처. context.tool_name 으로 동사 분기, _prev_result에서 통화 수용."""
    tool_name = getattr(context, "tool_name", None)
    fn = _DISPATCH.get(tool_name)
    if not fn:
        return {"error": f"data-ops: 알 수 없는 변환자 '{tool_name}'."}
    params = dict(tool_input or {})
    prev = _parse_prev(params.get("_prev_result"))
    if prev is None:
        # 파이프 입력(>>)이 없으면 params 에서 통화를 직접 수용 — 단독 호출/자가점검 지원.
        # (파이프 통화와 params 통화는 같은 모양이라 정합적이다.)
        # 이항(merge/join/union): (left,right)/(table1,table2)/(a,b) 쌍 또는 inputs 리스트 → [A, B].
        # 단항(filter/sort/take/select/dedup/groupby): records 또는 table.
        for k1, k2 in (("left", "right"), ("table1", "table2"), ("a", "b")):
            if params.get(k1) is not None and params.get(k2) is not None:
                prev = [params[k1], params[k2]]
                break
        if prev is None:
            if isinstance(params.get("inputs"), list):
                prev = params["inputs"]
            elif params.get("records") is not None:
                prev = {"records": params["records"]}
            elif params.get("table") is not None:
                prev = {"table": params["table"]}
    if prev is None:
        return {"error": (
            f"{tool_name}: 입력 통화가 없습니다. 변환자는 >> 파이프로 앞 액션의 "
            "records/table 통화를 받습니다. 예: [sense:search]{...} >> [table:filter]{where:...}"
        )}
    return fn(prev, params)
