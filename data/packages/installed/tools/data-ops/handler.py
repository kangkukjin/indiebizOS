"""data-ops — 통화→통화 변환자 (currency algebra).

IBL의 깊이(depth)를 만드는 부품. 생산자(sense:* 등)가 내는 공유 통화를 입력으로,
같은 통화를 출력하는 닫힌(closure) 동사들. >> 파이프로 임의 깊이 조합:

    [sense:realty]{...} >> [engines:filter]{where:"전세"} >> [engines:sort]{by:price} >> [engines:take]{n:5}

각 동사는 도메인에 무관 — 한 번 짜서 34개 생산자 × 임의 깊이에 곱해진다. 이 파일이
없던 시절엔 sort/top-N/dedup이 ~19개 핸들러에 사적으로 중복 구현돼 있었다(부채 회수).

두 통화:
  - records = [{title, meta?, summary?, url?, image?}]  (목록형)  → envelope {records:[...]}
  - table   = {columns:[...], rows:[[...]]}              (표형)    → envelope {table:{...}} 또는 최상위

이번 단계(단항, 단일 _prev_result 입력): filter / sort / take / select / dedup / groupby.
이항(join/union/merge, & 병렬 두 입력)은 다음 단계.
"""

import json


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
    """객체에서 records 리스트를 꺼낸다. ({records:[...]} 또는 리스트 자체)

    반환: (records_list, envelope_dict)  — envelope에 변환 결과를 다시 끼워 비파괴 반환용.
    """
    if isinstance(obj, dict):
        r = obj.get("records")
        if isinstance(r, list):
            return r, obj
    if isinstance(obj, list):
        return obj, {"records": obj}
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
    return None, None


def _emit_records(envelope, new_records):
    """변환된 records를 원 envelope에 비파괴로 끼워 반환."""
    out = dict(envelope) if isinstance(envelope, dict) else {}
    out["records"] = new_records
    out["count"] = len(new_records)
    out.setdefault("success", True)
    return out


def _emit_table(envelope, new_table):
    out = dict(envelope) if isinstance(envelope, dict) else {}
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


def _match(item, where):
    """item(dict) 이 where 조건을 만족하나.

    where 형태:
      - str S            : 아무 필드 값에 S가 부분일치 (전 필드 substring 검색)
      - {field, op, value}: SQL식 단일 조건 (op 기본 ==; field=col/column 별칭)
      - {col: value, ...}: 각 열=값 동등(AND) 단축형
      - [cond, cond, ...]: AND 결합
    """
    if where is None or where == "":
        return True
    if isinstance(where, str):
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


def _op_groupby(prev, params):
    """table → 그룹 집계. params.by(그룹 키 열), params.agg.

    agg 형태: {새열명: [op, 원본열]} 또는 {원본열: op}. op = count/sum/avg/min/max.
    기본: agg 없으면 그룹별 count.  반환 table = [by열, 집계열들].
    """
    by = params.get("by") or params.get("key") or params.get("group_by")
    if not by:
        return {"error": "groupby: by(그룹 키 열)가 필요합니다."}
    table, env = _get_table(prev)
    if table is None:
        return {"error": "groupby: table 통화가 필요합니다(표형 입력)."}
    by = str(by)
    dicts = _row_dicts(table)
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
        return {"error": "union: & 병렬로 두 입력이 필요합니다. 예: [A] & [B] >> [engines:union]"}
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
        return _emit_records({"records": []}, list(ra) + list(rb))
    return {"error": "union: 두 입력의 통화 종류가 같아야 합니다(둘 다 table 또는 둘 다 records)."}


def _op_merge(prev, params):
    """두 records를 합친다(concat). params.by 지정 시 그 키로 중복 제거.

    여러 검색 결과를 한 목록으로 모을 때. (table 결합은 union.)
    """
    a, b = _extract_two(prev)
    if a is None or b is None:
        return {"error": "merge: & 병렬로 두 records 입력이 필요합니다. 예: [A] & [B] >> [engines:merge]"}
    ra, _ = _get_records(a)
    rb, _ = _get_records(b)
    if ra is None or rb is None:
        return {"error": "merge: 두 입력 모두 records 통화여야 합니다(표형 결합은 engines:union)."}
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
    return _emit_records({"records": []}, out)


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
    예: [sense:stock]{op:history} & [sense:world_bank]{...} >> [engines:join]{on: "연도"}.
    """
    on = params.get("on") or params.get("key")
    if not on:
        return {"error": "join: on(조인 키 열 이름)이 필요합니다."}
    on = str(on)
    a, b = _extract_two(prev)
    if a is None or b is None:
        return {"error": "join: & 병렬로 두 table 입력이 필요합니다. 예: [A] & [B] >> [engines:join]{on: \"연도\"}"}
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
        return _emit_records({"records": []}, out)
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
            "records/table 통화를 받습니다. 예: [sense:search]{...} >> [engines:filter]{where:...}"
        )}
    return fn(prev, params)
