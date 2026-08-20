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

+ 표준 코어 문서 emitter(2026-07-03 media_producer에서 이관 — 표준 코어 table 어휘가 개인
패키지에 살던 경계 이상 해소): [table:structure]=콘텐츠→문서 IR(경량 LLM 편집자),
[table:document]=문서 IR→html/pdf/png/docx/pptx/typst. 무거운 의존성(playwright·docx·pptx·typst)은
전부 함수 안 지연 import — 모듈레벨은 stdlib(json/re)만이라 폰 import-safe 불변식 유지.
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


def _get_items(obj):
    """객체에서 항목 리스트를 꺼낸다.

    단일 통화 `items`가 유일한 키다(2026-06-27 단일통화 컷오버 완료). 모든 생산자가
    native 풍부 dict를 items로 방출하므로 옛 카드 통화가 버리던 필드까지 in-pipe로 흐른다
    (예: zigbang lat/lng, business level). dict/list 가 아니면 통화 아님으로 (None, None) 반환.

    반환: (items_list, envelope_dict)  — envelope에 변환 결과를 다시 끼워 비파괴 반환용.
    """
    if isinstance(obj, dict):
        r = obj.get("items")            # 단일 통화 — 모든 생산자가 items 방출
        if isinstance(r, list):
            return r, obj
    if isinstance(obj, list):
        # F13-2 (2026-08-19 상상훈련 13회차): 병렬(&) 결과 봉투(분기별 JSON 봉투 문자열
        # 리스트)를 items 로 오인 채택하면 단항 변환자가 문자열 행으로 죽으며 원인을
        # 못 말한다("행 필드 예: []" 실측). 이항 변환자(_extract_many)의 몫으로 넘긴다 —
        # _no_currency_error 가 같은 감지로 정직한 안내를 낸다.
        if _parallel_envelope_shape(obj):
            return None, None
        return obj, {"items": obj}
    return None, None


def _parallel_envelope_shape(obj):
    """병렬(&) 결과 봉투 감지 — 원소 전부가 JSON dict 로 파싱되는 *문자열*인 2+ 리스트.

    스칼라 행 리스트(["가","나"] — each 스칼라 지원)와 dict 행 리스트(정상 items)는
    여기 안 걸린다(문자열이 dict 로 파싱될 때만).
    """
    if not isinstance(obj, list) or len(obj) < 2:
        return False
    for el in obj:
        if not isinstance(el, str):
            return False
        s = el.strip()
        if not s.startswith("{"):
            return False
        try:
            if not isinstance(json.loads(s), dict):
                return False
        except Exception:
            return False
    return True


def _get_items_for_fields(prev, fields):
    """★계약 입구의 원천 행 파고들기 (2026-08-16 상상훈련 F6).

    items(카드 투영)가 verb 가 요구하는 필드를 접었으면 원천 행(data/results —
    `_rows_for_field`)까지 거슬러 찾는다. 이 구제가 filter·sort 에만 개별로 붙어 있어
    같은 파이프 자리에서 select·dedup 만 죽는 비대칭이 생겼다(kosis org_id 실측) —
    verb 마다 붙이면 새 verb 에서 비대칭이 재생산되므로 입구 하나로 접는다.
    새 변환자는 _get_items 대신 이 함수를 쓰면 파고들기를 자동 상속한다.

    조건: **필드가 items 에 없을 때만** 파고든다 — 무조건 파고들면 카드 투영
    (title/meta)을 기대하는 표면·하류가 깨진다(filter 의 기존 규약 그대로).

    반환: (rows, envelope) — rows 는 items 이거나(필드가 이미 있으면) 원천 행.
    items 통화 자체가 없으면 (None, None) — 각 verb 의 table 분기·최종 폴백은 그대로 산다.
    """
    fields = [str(f) for f in (fields or []) if f]
    recs, env = _get_items(prev)
    if recs is None:
        return None, None
    dict_recs = [r for r in recs if isinstance(r, dict)]
    if not fields or not dict_recs:
        return recs, env
    missing = [f for f in fields if not any(f in r for r in dict_recs)]
    if not missing:
        return recs, env
    dug = _rows_for_field(prev, missing[0])
    if dug and all(any(f in r for r in dug) for f in fields):
        return dug, env
    return recs, env            # 파고들어도 없음 — 원래 items 로 정직한 필드 에러가 나게


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


_CURRENCY_KEYS = ("items", "table", "columns", "rows", "count")


def _reproject_mirrors(out, originals, new_rows):
    """거울 키(=통화를 도메인 이름으로 병기한 키)를 변환 결과로 함께 갱신한다.

    ★B15-1 (2026-08-20 상상훈련 15회차): `[self:trigger]{op:"list"}` 는 `items` 와
    `triggers` 에 **같은 리스트**를 병기한다(items 병행 방출 규약 — 그래야 `>> [table:*]`
    가 통화를 찾는다). 그런데 변환자는 `items` 만 갈아끼우고 `triggers` 는 그대로 두어,
    `take{n:1}` 뒤에도 `triggers` 에 전 건이 남았다 — **변환자는 일했는데 봉투가**
    **거짓말을 한다**(실측: items 1건/count 1 인데 triggers 3건, filter 전멸 뒤에도 3건).
    읽는 쪽(모델·사람·표면)은 도메인 이름을 먼저 믿으므로 "n개만 골라 알림"이 전량으로
    번진다. `message`/`text`/`table` 을 이미 여기서 떨어내는 것과 **같은 부류**이고,
    거울 키는 이름을 미리 알 수 없으므로 이름 목록이 아니라 **동일성**으로 찾는다.

    ★생산자 7곳(trigger list/history·switch·agents·guestpc limbs·pc-manager top·web
    sections)을 각각 고치지 않고 이 병목에서 닫는 이유: 8번째 병행 방출이 다시 감염된다
    (입구를 하나로 접은 `_get_items_for_fields` 선례, F6).

    판정 순서(오폭 방지): ①객체 동일성(is) 먼저 — 병기는 같은 객체를 두 키에 넣으므로
    대부분 여기서 잡힌다 ②값 동등(==) 폴백 — 복사본 병기(`list(x)`)용. 빈 리스트는
    값 동등을 건너뛴다(무관한 빈 리스트 오폭 방지). 원본과 **다른** 컬렉션은 손대지
    않는다 — 예: trigger list 의 `existing_schedules` 는 종류가 다른 원장이라 보존된다.

    `_mirrored` 는 순찰용 계수 표식이다(거울 키 증식 압력계 — 재투영이 "거울 키를
    마음껏 만들어도 된다"는 면허로 오독되지 않게. 하우스 교리는 단일 통화 {items}).
    """
    cands = [o for o in (originals or []) if isinstance(o, list)]
    mirrors = []
    for k, v in list(out.items()):
        if not cands or k in _CURRENCY_KEYS or not isinstance(v, list):
            continue
        hit = any(v is o for o in cands) or any(o and v == o for o in cands)
        if hit:
            out[k] = list(new_rows)
            mirrors.append(k)
    if mirrors:
        out["_mirrored"] = sorted(mirrors)

    # ★자백(2026-08-20 사용자 판정): 거울이 **아닌** 형제 컬렉션은 변환을 따라가지 못한다.
    #   두 부류가 있고 둘 다 기계가 대신 정할 수 없다 —
    #   ①종류가 다른 형제 원장(trigger list 의 existing_schedules): 애초에 다른 데이터라
    #     변환 대상이 아니다. 손대면 그건 통화 수리가 아니라 의미 결정이다.
    #   ②파생 원천(others:agents 의 projects 트리 — items 는 이걸 *펼쳐서* 만든 것):
    #     평평한 items 로는 되돌릴 수 없어 재투영이 원리적으로 불가능하다.
    #   그래서 드롭도 재투영도 아닌 **자백**을 택한다: 이 키들은 변환 전 상태라고 봉투에
    #   적어 둔다. 읽는 쪽(모델·사람)이 도메인 이름을 통화로 오독하는 것이 B15-1 의 실제
    #   피해였고, 자백은 그 오독만 막으면서 데이터는 하나도 안 버린다.
    untouched = [k for k, v in out.items()
                 if k not in _CURRENCY_KEYS and k not in mirrors and not str(k).startswith("_")
                 and isinstance(v, list) and v and any(isinstance(x, dict) for x in v)]
    if untouched:
        out["_untransformed"] = sorted(untouched)
    return out


def _emit_items(envelope, new_items):
    """변환된 항목들을 원 envelope에 비파괴로 끼워 반환.

    단일 통화 키 `items`로 내보낸다(2026-06-27 단일통화 컷오버 완료 — 옛 이중방출 은퇴).
    """
    out = dict(envelope) if isinstance(envelope, dict) else {}
    _orig = [out.get("items"), out.get("rows")]   # 거울 판정 기준 (덮어쓰기 전에 잡는다)
    out.pop("message", None)            # 변환 후 stale·O(items) 산문 제거 (파이프 블로업·정합성)
    out.pop("text", None)               # 동류 — 원본 전체를 서술하는 text 가 take(5) 뒤에도 15줄이면 거짓말(2026-08-08 실측)
    # stale 파생 뷰 제거 — message 와 같은 원리. items 만 갱신하고 낡은 table 을 남기면
    # 하류 소비자(spreadsheet/chart 는 table 우선)가 변환 전 데이터를 집는다(2026-08-07 실측).
    out.pop("table", None)
    if isinstance(out.get("columns"), list) and isinstance(out.get("rows"), list):
        out.pop("columns", None)
        out.pop("rows", None)
    out["items"] = new_items          # 단일 통화
    out["count"] = len(new_items)
    out.setdefault("success", True)
    return _reproject_mirrors(out, _orig, new_items)


def _emit_table(envelope, new_table):
    out = dict(envelope) if isinstance(envelope, dict) else {}
    _orig = [out.get("items"), out.get("rows")]   # 거울 판정 기준 (덮어쓰기 전에)
    out.pop("message", None)            # 변환 후 stale 산문 제거
    out.pop("text", None)               # 동류(2026-08-08)
    # 대칭: table 만 갱신하고 낡은 items 를 남기면 같은 stale 부류 (2026-08-07).
    out.pop("items", None)
    out.pop("count", None)
    if "table" in out:
        out["table"] = new_table
    else:
        out["columns"] = new_table.get("columns", [])
        out["rows"] = new_table.get("rows", [])
    out.setdefault("success", True)
    # 표 경로의 거울 키는 행 dict 로 투영한다 — 도메인 키에 열-배열을 꽂으면 모양이 깨진다.
    return _reproject_mirrors(out, _orig, _row_dicts(new_table))


def _field_missing_error(verb, missing, rows):
    """명시 파라미터가 가리키는 필드가 어느 행에도 없을 때의 정직한 에러.

    침묵-삼킴 금지 계약(2026-08-08, 3방식 실험 ⑧′): 잘못된 필드/형식을 조용히
    기본값으로 위장하면 '그럴듯하게 틀린' 결과가 나가고, 진짜 비용은 틀린 답이
    아니라 틀린 진단이다(실험자가 '기능이 없다'고 오진). sort 의 가드를 계열 전체로.
    """
    avail = []
    for r in rows or []:
        if isinstance(r, dict):
            avail = list(r.keys())
            break
    miss = "', '".join(str(m) for m in missing) if isinstance(missing, (list, tuple)) else str(missing)
    hint = f" 사용 가능한 필드: {avail}" if avail else ""
    return {"success": False, "error": f"{verb}: '{miss}' 필드가 어느 행에도 없습니다.{hint}"}


def _no_currency_error(verb, prev):
    """입력에 통화(items/table)가 없을 때 — 받은 봉투의 실제 모양을 보여주는 진단 에러.

    ⑬(실험 4): scalar/effect 액션을 >> 로 변환자에 물리면 여기서 멈춘다. 무엇이
    왔는지(키 목록)를 보여줘야 '기능이 없다'가 아니라 '이 생산자는 통화를 안 낸다
    (returns 선언 확인)'로 진단이 간다.
    """
    # F13-2: 병렬 봉투는 부류가 다르다 — "통화 없음"이 아니라 "이항 변환자 자리".
    if _parallel_envelope_shape(prev):
        return {"success": False,
                "error": f"{verb}: 입력이 병렬(&) 결과 봉투입니다 — 분기들은 이항 변환자"
                         f"(union/merge/join)가 먼저 받아야 합니다. 예: [A] & [B] >> [table:union] "
                         f">> [table:{verb}]. 분기 하나에만 전처리를 붙이려면 괄호 분기: "
                         "[A] & ([B] >> [table:rename]{map: {…}}) >> [table:merge]{by: \"…\"}."}
    keys = sorted(prev.keys()) if isinstance(prev, dict) else type(prev).__name__
    return {"success": False,
            "error": f"{verb}: 입력에서 items 통화를 찾지 못했습니다. 받은 봉투의 키: {keys} — "
                     f"앞 액션이 통화(items/table)를 내지 않는 생산자(returns: scalar/effect)일 수 "
                     f"있습니다. 통화를 내는 액션·op 으로 바꾸거나 선언(returns)을 확인하세요."}


def _where_fields(where):
    """where 조건이 명시적으로 가리키는 필드 이름들(존재 검증용).

    전-필드 substring 형태(연산자 없는 문자열)는 필드를 지목하지 않으므로 [].
    """
    if isinstance(where, str):
        m = _CMP_RE.match(where)
        return [m.group(1).strip()] if m else []
    if isinstance(where, list):
        out = []
        for w in where:
            out.extend(_where_fields(w))
        return out
    if isinstance(where, dict):
        f = where.get("field") or where.get("col") or where.get("column")
        if f:
            return [str(f)]
        return [str(k) for k in where.keys() if k not in ("op", "value")]
    return []


def _row_dicts(table):
    """table rows → [{col: val}] (where/sort/dedup이 items와 같은 코드 쓰도록)."""
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
    """items|table → 부분집합. params.where (미니 DSL). condition 별칭 수용.

    where 가 지목한 필드가 어느 행에도 없으면 빈 결과 대신 에러(⑧′ — 빈 결과와
    '필드 오타'는 구별돼야 한다).
    """
    where = params.get("where") or params.get("condition")
    # 파고들기는 입구(_get_items_for_fields)가 담당 — R5 개별 구현을 F6 에서 입구로 접음.
    recs, env = _get_items_for_fields(prev, _where_fields(where))
    if recs is not None:
        dict_recs = [r for r in recs if isinstance(r, dict)]
        if dict_recs:
            missing = [f for f in _where_fields(where) if not any(f in r for r in dict_recs)]
            if missing:
                return _field_missing_error("filter", missing, dict_recs)
        return _emit_items(env, [r for r in dict_recs if _match(r, where)])
    table, env = _get_table(prev)
    if table is not None:
        dicts = _row_dicts(table)
        if dicts:
            missing = [f for f in _where_fields(where) if not any(f in d for d in dicts)]
            if missing:
                return _field_missing_error("filter", missing, dicts)
        kept = [d for d in dicts if _match(d, where)]
        cols = table.get("columns") or []
        rows = [[d.get(str(c)) for c in cols] for d in kept]
        return _emit_table(env, {"columns": cols, "rows": rows})
    # items/table 이 없어도 도메인 봉투의 원천 행(data/results)이 있으면 거기서 (sort 와 대칭)
    _wf = _where_fields(where)
    dug = _rows_for_field(prev, _wf[0] if _wf else None)
    if dug:
        missing = [f for f in _wf if not any(f in r for r in dug)]
        if missing:
            return _field_missing_error("filter", missing, dug)
        return _emit_items({}, [r for r in dug if _match(r, where)])
    return _no_currency_error("filter", prev)


def _op_sort(prev, params):
    """items|table → 정렬. params.by(필드/열명), params.desc(bool).

    by 가 items/table 에 없으면 원천 행(data/results — groupby 의 _rows_for_field 선례)까지
    거슬러 찾고, 그래도 없으면 에러(2026-08-07 — 옛 침묵 no-op 은 원순서를 success 로
    돌려줘 하류 전체가 조용히 틀렸다. filter 의 '침묵 부분일치 금지' 원칙과 동일).
    """
    by = params.get("by")
    desc = bool(params.get("desc", False))
    # F13-3 (2026-08-19 상상훈련 13회차): 자연 동의어 order:"desc"/"asc" 값-해석 —
    # 예전엔 경고만 뜨고 오름차순이 success 로 나가 요청 의미가 반전됐다.
    # 값-해석이라 aliases 블록(이름 별칭)으로는 못 나른다("desc" 문자열은 truthy).
    if "desc" not in params and "order" in params:
        desc = str(params.get("order") or "").strip().lower() in (
            "desc", "descending", "reverse", "내림차순")
    if not by:
        return {"success": False, "error": "sort: by(정렬 기준 필드/열명)가 필요합니다."}
    by = str(by)
    # 파고들기는 입구가 담당 (F6) — by 가 카드 투영에 접혔으면 원천 행이 돌아온다.
    recs, env = _get_items_for_fields(prev, [by])
    if recs is not None:
        dict_recs = [r for r in recs if isinstance(r, dict)]
        if not dict_recs or any(by in r for r in dict_recs):
            srt = sorted(dict_recs, key=_sort_key(by), reverse=desc)
            return _emit_items(env, srt)
    table, tenv = _get_table(prev)
    if table is not None and by in [str(c) for c in (table.get("columns") or [])]:
        dicts = _row_dicts(table)
        dicts.sort(key=_sort_key(by), reverse=desc)
        cols = table.get("columns") or []
        rows = [[d.get(str(c)) for c in cols] for d in dicts]
        return _emit_table(tenv, {"columns": cols, "rows": rows})
    # 손실 투영(예: 주가 table=날짜·종가)이 정렬 키를 접은 경우 — 원천 행까지 거슬러 찾기
    dug = _rows_for_field(prev, by)
    if dug and any(by in r for r in dug):
        srt = sorted(dug, key=_sort_key(by), reverse=desc)
        base_env = env if env is not None else (tenv if tenv is not None else (prev if isinstance(prev, dict) else {}))
        return _emit_items(base_env, srt)
    if recs is None and table is None and not dug:
        return _no_currency_error("sort", prev)
    # 어디에도 없는 필드 → 침묵 no-op 대신 정직한 실패 + 실제 필드 안내
    avail = []
    if recs:
        first = next((r for r in recs if isinstance(r, dict)), None)
        if first:
            avail = list(first.keys())
    if not avail and table is not None:
        avail = [str(c) for c in (table.get("columns") or [])]
    if not avail and dug:
        avail = list(dug[0].keys())
    hint = f" 사용 가능한 필드: {avail}" if avail else ""
    return {"success": False, "error": f"sort: '{by}' 필드가 어느 행에도 없습니다.{hint}"}


def _op_take(prev, params):
    """items|table → 상위 n. params.n (기본 10). 음수면 뒤에서 n개."""
    n = params.get("n", params.get("limit", 10))
    try:
        n = int(n)
    except Exception:
        # 비정수 n 을 조용히 10 으로 위장하지 않는다(⑧′)
        return {"success": False, "error": f"take: n 이 정수가 아닙니다: {n!r}"}
    recs, env = _get_items(prev)
    if recs is not None:
        sliced = recs[n:] if n < 0 else recs[:n]
        return _emit_items(env, sliced)
    table, env = _get_table(prev)
    if table is not None:
        rows = table.get("rows") or []
        sliced = rows[n:] if n < 0 else rows[:n]
        return _emit_table(env, {"columns": table.get("columns") or [], "rows": sliced})
    return _no_currency_error("take", prev)


def _op_select(prev, params):
    """table → 열 투영. params.columns(남길 열 이름 배열). items는 필드 추림."""
    cols_keep = params.get("columns") or params.get("cols") or params.get("fields")
    if not cols_keep:
        return {"success": False, "error": "select: columns(남길 열/필드 이름 배열)가 필요합니다."}
    cols_keep = [str(c) for c in cols_keep]
    table, env = _get_table(prev)
    if table is not None:
        src_cols = [str(c) for c in (table.get("columns") or [])]
        missing = [c for c in cols_keep if c not in src_cols]
        if missing:
            # 열이 접혔으면 입구 파고들기 (F6) — _get_table 이 카드 items 에서 표를
            # *재구성*한 경우(kosis 실측) 원천 행(data)에는 그 열이 살아 있다.
            dug, denv = _get_items_for_fields(prev, cols_keep)
            if dug:
                dug_dicts = [r for r in dug if isinstance(r, dict)]
                if dug_dicts and not any(
                        c for c in cols_keep if not any(c in r for r in dug_dicts)):
                    out = [{k: r.get(k) for k in cols_keep if k in r} for r in dug_dicts]
                    return _emit_items(denv if denv is not None else env, out)
            # 없는 열을 조용히 떨구면 빈 표가 success 로 나간다(⑧′)
            return {"success": False,
                    "error": f"select: 열 {missing} 이(가) 없습니다. 실제 열: {src_cols}"}
        idx = [src_cols.index(c) for c in cols_keep]
        new_cols = [src_cols[i] for i in idx]
        new_rows = [[(r[i] if i < len(r) else None) for i in idx] for r in (table.get("rows") or [])]
        return _emit_table(env, {"columns": new_cols, "rows": new_rows})
    recs, env = _get_items_for_fields(prev, cols_keep)
    if recs is not None:
        dict_recs = [r for r in recs if isinstance(r, dict)]
        if dict_recs:
            missing = [k for k in cols_keep if not any(k in r for r in dict_recs)]
            if missing:
                return _field_missing_error("select", missing, dict_recs)
        out = [{k: r.get(k) for k in cols_keep if k in r} for r in dict_recs]
        return _emit_items(env, out)
    return _no_currency_error("select", prev)


def _norm(s):
    import re
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _op_rename(prev, params):
    """열/필드 이름 바꾸기(관계대수 ρ). map={옛이름: 새이름}. table·items 둘 다.

    소스가 다른 두 통화를 join 으로 묶기 전 키 이름을 맞추는 용도(2026-08-16
    molit '아파트명' vs naver 'title' 실측에서 어휘화). 없는 이름을 조용히 넘기거나
    기존 열을 덮어쓰면 침묵 소실이라 전부 명시 에러. 교환(A↔B)은 원자적으로 허용.
    """
    m = params.get("map") or params.get("columns")
    if not isinstance(m, dict) or not m:
        return {"success": False, "error": (
            'rename: map({옛이름: 새이름})이 필요합니다. '
            '예: [table:rename]{map: {"아파트명": "단지명"}}')}
    m = {str(k): str(v) for k, v in m.items()}
    targets = list(m.values())
    if len(set(targets)) != len(targets):
        return {"success": False,
                "error": f"rename: 새 이름이 서로 겹칩니다: {sorted(targets)} — 한 이름에 두 열을 접으면 값이 소실됩니다."}

    table, env = _get_table(prev)
    if table is not None:
        src_cols = [str(c) for c in (table.get("columns") or [])]
        missing = [k for k in m if k not in src_cols]
        if missing:
            return {"success": False,
                    "error": f"rename: 열 {missing} 이(가) 없습니다. 실제 열: {src_cols}"}
        clash = [v for k, v in m.items() if v in src_cols and v not in m]
        if clash:
            return {"success": False,
                    "error": f"rename: 새 이름 {clash} 이(가) 기존 열과 겹칩니다 — 덮어쓰면 그 열이 소실됩니다."}
        new_cols = [m.get(c, c) for c in src_cols]
        return _emit_table(env, {"columns": new_cols, "rows": table.get("rows") or []})

    recs, env = _get_items(prev)
    if recs is not None:
        dict_recs = [r for r in recs if isinstance(r, dict)]
        missing = [k for k in m if not any(k in r for r in dict_recs)]
        if missing:
            sample = sorted({kk for r in dict_recs[:20] for kk in r.keys()})[:12]
            return {"success": False,
                    "error": f"rename: 필드 {missing} 이(가) 없습니다. 행 필드 예: {sample}"}
        clash = [v for k, v in m.items()
                 if v not in m and any(v in r for r in dict_recs)]
        if clash:
            return {"success": False,
                    "error": f"rename: 새 이름 {clash} 이(가) 기존 필드와 겹칩니다 — 덮어쓰면 그 값이 소실됩니다."}
        out = []
        for r in recs:
            out.append({m.get(k, k): v for k, v in r.items()} if isinstance(r, dict) else r)
        return _emit_items(env, out)
    return _no_currency_error("rename", prev)


def _op_dedup(prev, params):
    """items|table → 중복 제거(첫 항목 유지). params.by(키 필드/열, 기본 title).

    by 미지정 시 items는 title, table은 첫 열을 키로. 정규화(공백/대소문자) 후 동등 비교.
    (newspaper 내부에 묻혀있던 _dedup_rank를 통화 동사로 끌어올림 — 전 생산자 공용화.)
    """
    by = params.get("by")
    # 파고들기는 입구가 담당 (F6). 기본(title)은 관례라 파고들지 않는다.
    recs, env = _get_items_for_fields(prev, [by] if by else None)
    if recs is not None:
        dict_recs = [r for r in recs if isinstance(r, dict)]
        # 명시 by 가 어느 행에도 없으면 무동작이 success 로 위장된다(⑧′). 기본(title)은 관례라 관대.
        if by and dict_recs and not any(str(by) in r for r in dict_recs):
            return _field_missing_error("dedup", by, dict_recs)
        key = str(by) if by else "title"
        seen, out = set(), []
        for r in dict_recs:
            k = _norm(r.get(key))
            if k and k in seen:
                continue
            seen.add(k)
            out.append(r)
        return _emit_items(env, out)
    table, env = _get_table(prev)
    if table is not None:
        cols = [str(c) for c in (table.get("columns") or [])]
        if by and str(by) not in cols:
            # 잘못된 by 를 조용히 첫 열로 폴백하면 엉뚱한 키로 중복 제거된다(⑧′)
            return {"success": False, "error": f"dedup: '{by}' 열이 없습니다. 실제 열: {cols}"}
        ki = cols.index(str(by)) if by else 0
        seen, rows = set(), []
        for r in table.get("rows") or []:
            k = _norm(r[ki] if ki < len(r) else None)
            if k and k in seen:
                continue
            seen.add(k)
            rows.append(r)
        return _emit_table(env, {"columns": cols, "rows": rows})
    return _no_currency_error("dedup", prev)


_AGG = {
    "count": lambda vs: len(vs),
    "sum": lambda vs: round(sum(_as_num(v) or 0 for v in vs), 6),
    "avg": lambda vs: round(sum(_as_num(v) or 0 for v in vs) / len(vs), 6) if vs else 0,
    "min": lambda vs: min((_as_num(v) for v in vs if _as_num(v) is not None), default=None),
    "max": lambda vs: max((_as_num(v) for v in vs if _as_num(v) is not None), default=None),
}


def _rows_for_field(obj, field):
    """그룹/집계 키 field 를 실제로 담은 표현을 골라 list-of-dicts 로 반환.

    공유 통화 items(및 table) 외에도 도메인 생산자가 원천 행을 다른 키
    (data/results)에 담는 경우까지 후보로 본다. 옛 손실적 카드 투영이 도메인 필드를
    meta 문자열로 접어 groupby 가 그 필드를 못 찾던 문제(예: realty 가 '법정동'을 meta 로
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
        for k in ("data", "items", "results"):
            v = obj.get(k)
            if isinstance(v, list) and any(isinstance(x, dict) for x in v):
                cands.append((k, [x for x in v if isinstance(x, dict)]))
            elif isinstance(v, dict):
                # 도메인 봉투가 행 목록을 한 겹 더 안에 담는 경우 (예: 주가 data.prices —
                # 곡선 투영 table 이 접은 volume 등 원천 필드가 여기 산다, 2026-08-07)
                for kk, vv in v.items():
                    if isinstance(vv, list) and any(isinstance(x, dict) for x in vv):
                        cands.append((f"{k}.{kk}", [x for x in vv if isinstance(x, dict)]))
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
    """items|table|도메인 행목록 → 그룹 집계. params.by(그룹 키), params.agg.

    agg 형태: {새열명: [op, 원본열]} 또는 {원본열: op}. op = count/sum/avg/min/max.
    기본: agg 없으면 그룹별 count.  반환 table = [by열, 집계열들].

    형제 동사들처럼 items 를 받는다. 나아가 옛 카드 투영이 그룹 키를 접은 경우
    원천 data/items 행까지 거슬러 키를 찾는다(_rows_for_field).
    """
    by = params.get("by") or params.get("key") or params.get("group_by")
    if not by:
        return {"success": False, "error": "groupby: by(그룹 키 열)가 필요합니다."}
    by = str(by)
    dicts = _rows_for_field(prev, by)
    if not dicts:
        return {"success": False, "error": "groupby: 입력에서 items 통화(또는 data/items 행 목록)를 찾지 못했습니다."}
    if not any(by in d for d in dicts):
        # 없는 by 를 조용히 받으면 전 행이 null 한 그룹으로 뭉개진다(⑧′ 실측: [[null, 83]])
        return _field_missing_error("groupby", by, dicts)
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
    elif agg:
        # dict 아닌 agg("sum:size" 등)를 조용히 버리면 count 로 위장된다(⑧′ 실측)
        return {"success": False,
                "error": f"groupby: agg 는 dict 여야 합니다 — {{원본열: op}} 또는 {{새열명: [op, 원본열]}}, "
                         f"op={'/'.join(_AGG)}. 받은 값: {agg!r}"}
    for out_col, op, src in specs:
        if op not in _AGG:
            return {"success": False, "error": f"groupby: 알 수 없는 집계 op '{op}' (가능: {'/'.join(_AGG)})"}
        if op != "count" and not any(src in d for d in dicts):
            return _field_missing_error("groupby", src, dicts)
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


# ───────────────────────── since (검침 — 시간 차분) ─────────────────────────

_SINCE_CAP = 5000                     # 스트림당 기준선 키 상한 — 초과분은 오래 안 보인 것부터 정리
_SINCE_ID_CANDIDATES = ("url", "id", "link", "title")


def _since_conn():
    """검침 원장 연결 — 스트림별 last-seen 키·감시값 (data/table_since.db, WAL).

    사라진 키를 지우지 않고 누적한다: 회전 소스(검색·RSS '최근 N개 창')에서 빠졌다
    재등장한 행을 '새 것'으로 오보하지 않기 위해 (warehouse_feed 의 RSS 스냅샷 누적 선례).
    """
    import sqlite3
    from pathlib import Path
    path = Path(__file__).resolve().parents[5] / "data" / "table_since.db"   # notebook_core 선례
    conn = sqlite3.connect(str(path), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS since_seen ("
        " stream TEXT NOT NULL, k TEXT NOT NULL, watched TEXT,"
        " first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,"
        " PRIMARY KEY (stream, k))")
    return conn


def _op_since(prev, params):
    """items → 지난 검침 이후 새 행만 (+watch 필드 변화 행). 기준선은 스트림(key)별.

    warehouse_feed 의 seed/new/changed diff 를 통화 변환자로 일반화 — 모든 items
    생산자에 곱해져 감시자가 된다. 첫 검침은 기준선만 저장하고 빈 items 를 정직하게
    반환한다(첫 실행에 전부를 '새 것'으로 쏟으면 트리거 알림이 스팸이 된다).
    """
    key = params.get("key")
    if not key or not str(key).strip():
        return {"success": False, "error": (
            "since: key(검침 스트림 이름)가 필요합니다 — 감시 파이프마다 고유한 이름을 주세요. "
            '예: [sense:feed]{url:...} >> [table:since]{key: "하다뉴스"}')}
    key = str(key).strip()

    recs, env = _get_items(prev)
    if recs is None:
        return _no_currency_error("since", prev)
    rows = [r for r in recs if isinstance(r, dict)]

    by = params.get("by")
    if by:
        by = str(by)
        if rows and not any(by in r for r in rows):
            return _field_missing_error("since", [by], rows)
    else:
        by = next((c for c in _SINCE_ID_CANDIDATES
                   if rows and all(r.get(c) not in (None, "") for r in rows)), None)
        if rows and not by:
            avail = sorted({f for r in rows for f in r.keys()})
            return {"success": False, "error": (
                "since: 행 식별 필드를 못 골랐습니다(후보 url/id/link/title 이 모든 행에 없음). "
                f"by 로 지정하세요. 사용 가능한 필드: {avail[:12]}")}

    watch = params.get("watch") or []
    if isinstance(watch, str):
        watch = [watch]
    watch = [str(w) for w in watch if w]
    if watch and rows:
        missing = [w for w in watch if not any(w in r for r in rows)]
        if missing:
            return _field_missing_error("since", missing, rows)
    peek = bool(params.get("peek"))

    from datetime import datetime
    now = datetime.now().isoformat(timespec="seconds")
    conn = _since_conn()
    trimmed = 0
    try:
        seen = {r[0]: r[1] for r in conn.execute(
            "SELECT k, watched FROM since_seen WHERE stream=?", (key,))}
        first_run = not seen
        out, n_new, n_changed = [], 0, 0
        for r in rows:
            rk = str(r.get(by))
            if rk not in seen:
                if not first_run:
                    out.append({**r, "_since": "new"})
                    n_new += 1
            elif watch:
                try:
                    prev_wv = json.loads(seen[rk]) if seen[rk] else None
                except Exception:
                    prev_wv = None
                cur_wv = {w: r.get(w) for w in watch}
                # 감시 시작 전 키(prev_wv 없음)는 변화 판정 불가 — 거짓 changed 금지.
                if prev_wv is not None and cur_wv != prev_wv:
                    out.append({**r, "_since": "changed", "_since_prev": prev_wv})
                    n_changed += 1
        if not peek:
            for r in rows:
                rk = str(r.get(by))
                wjson = (json.dumps({w: r.get(w) for w in watch},
                                    ensure_ascii=False, sort_keys=True)
                         if watch else None)
                conn.execute(
                    "INSERT INTO since_seen (stream,k,watched,first_seen,last_seen)"
                    " VALUES (?,?,?,?,?) ON CONFLICT(stream,k) DO UPDATE SET"
                    " watched=excluded.watched, last_seen=excluded.last_seen",
                    (key, rk, wjson, now, now))
            total = conn.execute(
                "SELECT COUNT(*) FROM since_seen WHERE stream=?", (key,)).fetchone()[0]
            if total > _SINCE_CAP:
                trimmed = total - _SINCE_CAP
                conn.execute(
                    "DELETE FROM since_seen WHERE rowid IN (SELECT rowid FROM since_seen"
                    " WHERE stream=? ORDER BY last_seen ASC LIMIT ?)", (key, trimmed))
            conn.commit()
        baseline = conn.execute(
            "SELECT COUNT(*) FROM since_seen WHERE stream=?", (key,)).fetchone()[0]
    finally:
        conn.close()

    result = _emit_items(env, out)
    result["since_key"] = key
    result["since_by"] = by
    result["baseline_total"] = baseline
    if first_run:
        if peek:
            result["note"] = (f"첫 검침(peek) — 기준선 저장 안 함({len(rows)}행 미기록). "
                              "peek 없이 호출하면 기준선이 저장됩니다.")
        else:
            result["note"] = (f"첫 검침 — 기준선 {len(rows)}행 저장(스트림 '{key}'). "
                              "다음 호출부터 지난 검침 이후 새 행만 흐릅니다.")
    elif not out:
        result["note"] = f"지난 검침 이후 새 항목 없음 (기준선 {baseline}행)."
    else:
        parts = ([f"새 {n_new}건"] if n_new else []) + ([f"변경 {n_changed}건"] if n_changed else [])
        result["note"] = "지난 검침 이후 " + "·".join(parts) + "."
    if trimmed:
        result["note"] += f" (기준선 상한 {_SINCE_CAP} 초과 — 오래 안 보인 {trimmed}키 정리)"
    if peek and not first_run:
        result["note"] += " (peek — 기준선 안 올림)"
    return result


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


def _carry_flags(objs, with_total=True):
    """이항+ 결합의 최소 승계 봉투 — 정직 신호만 (⑰, 2026-08-08 실험 8).

    이항 변환자가 빈 봉투({})를 내면 ⑥′·⑭에서 봉한 절단 신고가 join/union/merge
    한 번에 다시 침묵한다(351건 중 8건 표가 전량인 척 문서화 — 실측). 승계 규칙:
      - truncated = OR — 한쪽이라도 잘렸으면 결과는 잘린 표본
      - total = 전 입력이 명시한 total 의 합 (union/merge 의 모집단 합.
        join 은 결과 기수가 입력 total 과 무관하므로 with_total=False 로 생략 —
        지어낸 total 은 또 다른 거짓말)
    그 외 도메인 필드는 승계하지 않는다 — 두 봉투를 합치는 규칙은 없고,
    한쪽 것을 실으면 거짓 출처가 된다.
    """
    env = {}
    dicts = [o for o in objs if isinstance(o, dict)]
    if any(o.get("truncated") for o in dicts):
        env["truncated"] = True
    if with_total and dicts:
        totals = [o.get("total") for o in dicts]
        if all(isinstance(t, (int, float)) and not isinstance(t, bool) for t in totals):
            env["total"] = sum(totals)
    return env


def _extract_many(prev):
    """& 병렬 결과에서 **전 분기** 추출 — [obj, ...] (2026-08-08, 실험 4 후속).

    옛 union/merge 는 _extract_two 로 prev[0]·prev[1]만 집어 **세 번째 분기를
    조용히 버렸다** — 3종목 병렬 결합이 2행으로 나가며 success:true(⑧′ 부류).
    """
    if not isinstance(prev, list) or len(prev) < 2:
        return None
    out = []
    for e in prev:
        if isinstance(e, str):
            try:
                e = json.loads(e)
            except Exception:
                e = None
        out.append(e)
    return out


def _op_union(prev, params):
    """병렬(&) 분기들의 table(또는 items)을 행 결합. 같은 통화끼리. params 없음.

    table: 열 이름으로 통합(순서 보존, 한쪽에만 있는 열은 다른쪽 None). items: 단순 concat.
    중복 제거가 필요하면 뒤에 >> dedup. 분기 수 제한 없음(셋 이상 전부).
    """
    objs = _extract_many(prev)
    if not objs:
        return {"success": False, "error": "union: & 병렬로 두 개 이상의 입력이 필요합니다. 예: [A] & [B] >> [table:union]"}
    _bad = sum(1 for o in objs if o is None)
    if _bad:
        # 입력 개수 탓으로 돌리면 자가교정 단서가 틀린다 — 진짜 원인은 분기 출력이 통화가 아님.
        return {"success": False,
                "error": f"union: 분기 {len(objs)}개 중 {_bad}개의 출력이 통화(items/table)로 파싱되지 않습니다"
                         f"(스칼라·평문 반환 등) — 통화를 내는 액션·op 으로 바꾸세요."}
    tables = [_get_table(o)[0] for o in objs]
    if all(t is not None for t in tables):
        cols = []
        for t in tables:
            for c in (t.get("columns") or []):
                if str(c) not in cols:
                    cols.append(str(c))

        def remap(t):
            tcols = [str(c) for c in (t.get("columns") or [])]
            out = []
            for r in t.get("rows") or []:
                d = {tcols[i]: (r[i] if i < len(r) else None) for i in range(len(tcols))}
                out.append([d.get(c) for c in cols])
            return out

        all_rows = []
        for t in tables:
            all_rows.extend(remap(t))
        env = _emit_table({**_carry_flags(objs), "table": {}}, {"columns": cols, "rows": all_rows})
        col_sets = [{str(c) for c in (t.get("columns") or [])} for t in tables if t.get("columns")]
        return _attach_shape_warning(env, col_sets)
    item_lists = [_get_items(o)[0] for o in objs]
    if all(il is not None for il in item_lists):
        out = []
        for il in item_lists:
            out.extend(il)
        env = _emit_items(_carry_flags(objs), out)
        # 분기별 *유효 칸*(null 아닌 값이 실제로 채워지는 키) — canonical null-패딩(title:null
        # 등)은 유효 칸이 아니다. 패딩 키로 재면 혼합 결합이 경고를 영원히 피해간다.
        key_sets = []
        for il in item_lists:
            ks = set()
            for it in il:
                if isinstance(it, dict):
                    ks |= {k for k, v in it.items() if v is not None}
            if ks:
                key_sets.append(ks)
        return _attach_shape_warning(env, key_sets)
    return {"success": False, "error": "union: 모든 입력의 통화 종류가 같아야 합니다(전부 table 또는 전부 items)."}


def _attach_shape_warning(env, key_sets):
    """★2026-08-17 상상훈련 11회차 판정(F1 증거 후속): union 분기 간 공유 유효 칸이
    0이면 이어붙인 표가 반쪽 열로 갈라진다(kv형 profile + records형 disclosures 혼합
    31행 실측). 결합은 정직하게 하되 조용히 넘기지 않는다 — 비차단 경고를 직렬화
    앞머리에 (param_warning 첫 키 선례)."""
    if len(key_sets) >= 2 and not set.intersection(*key_sets):
        return {"warning": "union: 분기 간 공유 칸(값이 채워지는 열)이 하나도 없습니다 — "
                           "서로 다른 모양의 목록을 이어붙였습니다. 후속 filter/sort/select 가 "
                           "반쪽 표에서 돌 수 있으니 분기 통화의 칸을 확인하세요.", **env}
    return env


def _op_merge(prev, params):
    """병렬(&) 분기들의 items를 합친다(concat). params.by 지정 시 그 키로 중복 제거.

    여러 검색 결과를 한 목록으로 모을 때. (table 결합은 union.) 분기 수 제한 없음.
    """
    objs = _extract_many(prev)
    if not objs:
        return {"success": False, "error": "merge: & 병렬로 두 개 이상의 items 입력이 필요합니다. 예: [A] & [B] >> [table:merge]"}
    _bad = sum(1 for o in objs if o is None)
    if _bad:
        # 입력 개수 탓으로 돌리면 자가교정 단서가 틀린다 — 진짜 원인은 분기 출력이 통화가 아님.
        return {"success": False,
                "error": f"merge: 분기 {len(objs)}개 중 {_bad}개의 출력이 통화(items)로 파싱되지 않습니다"
                         f"(스칼라·평문 반환 등) — 통화를 내는 액션·op 으로 바꾸세요."}
    item_lists = [_get_items(o)[0] for o in objs]
    if any(il is None for il in item_lists):
        return {"success": False, "error": "merge: 모든 입력이 items 통화여야 합니다(표형 결합은 table:union)."}
    out = []
    for il in item_lists:
        out.extend(il)
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
    return _emit_items(_carry_flags(objs), out)


def _op_flatten(prev, params):
    """행 속 중첩 목록을 펼쳐(unnest) 행들로 — each 의 출구.

    field(기본 "_result") 경로의 값이 목록이면 그 원소들이 새 행이 되고,
    {items: [...]} 봉투면 items 로 자동 승격(each 가 do 결과를 _result 에 통째로
    붙이는 계약의 짝). keep=[부모 필드]는 각 새 행에 승계(충돌 시 _2 접미 —
    침묵 오선택 방지). 목록 아닌 행은 건너뛰되 skipped_rows 로 신고한다.
    """
    recs, env = _get_items(prev)
    if recs is None:
        t, _ = _get_table(prev)
        if t is not None:
            return {"success": False,
                    "error": "flatten: items 통화 전용입니다(표형 table 셀엔 중첩 목록이 없습니다)."}
        return {"success": False,
                "error": "flatten: 입력에서 items 통화를 찾지 못했습니다. each 결과 뒤(>>)에 놓으세요."}
    field = str(params.get("field") or "_result")
    keep = params.get("keep") or []
    if not isinstance(keep, list):
        keep = [keep]
    keep = [str(k) for k in keep]

    # ★F14-2 (2026-08-20 14회차): keep 미실존 필드의 침묵 무시 차단 — dedup 규율 이식.
    # 전무(어느 행에도 없음)가 keep 전체면 이름 오타 확정 → 정직 오류.
    # 일부만 전무면 진행하되 keep_missing 으로 신고(행마다 다른 필드는 정상 케이스).
    keep_missing = []
    if keep and recs:
        keep_missing = [k for k in keep
                        if not any(isinstance(r, dict) and k in r for r in recs)]
        if keep_missing and len(keep_missing) == len(keep):
            sample = sorted({kk for r in recs[:20] if isinstance(r, dict) for kk in r.keys()})[:12]
            return {"success": False,
                    "error": (f"flatten: keep {keep} 이(가) 어느 행에도 없습니다. "
                              f"사용 가능한 필드: {sample}")}

    def _dig(row, path):
        cur = row
        for part in path.split("."):
            if not isinstance(cur, dict):
                return None
            cur = cur.get(part)
        return cur

    out = []
    skipped = 0
    for r in recs:
        if not isinstance(r, dict):
            skipped += 1
            continue
        v = _dig(r, field)
        if isinstance(v, str):
            # each 가 _result 를 JSON 문자열로 붙였을 수 있다 — 파싱 시도
            try:
                _p = json.loads(v)
                if isinstance(_p, (dict, list)):
                    v = _p
            except Exception:
                pass
        if isinstance(v, dict) and isinstance(v.get("items"), list):
            v = v["items"]
        if not isinstance(v, list):
            skipped += 1
            continue
        carry = {k: r.get(k) for k in keep if k in r}
        for sub in v:
            base = dict(sub) if isinstance(sub, dict) else {"value": sub}
            if carry:
                disp = _suffix_collisions(list(base.keys()), list(carry.keys()))
                for (ck, cv), name in zip(carry.items(), disp):
                    base[name] = cv
            out.append(base)
    if not out:
        # ★F17 확장 (2026-08-17 12회차): 입력 0행은 실수가 아니라 정당한 빈손 — 0건 통화로
        # 파이프를 완주시킨다(each 와 같은 수리 — "목록 필드가 없다" 오류의 전제는
        # "행이 있는데"라 행 0개엔 성립하지 않는다).
        if not recs:
            res = _emit_items(env, [])
            res["message"] = "flatten: 입력 0행 — 펼칠 것 없음 (빈 목록)"
            return res
        sample = sorted({kk for r in recs[:20] if isinstance(r, dict) for kk in r.keys()})[:12]
        return {"success": False,
                "error": (f"flatten: field '{field}' 에서 목록을 가진 행이 없습니다"
                          f"(행 {len(recs)}개 전부 건너뜀). 행 필드 예: {sample} — "
                          f"each 뒤라면 field: \"_result\" 또는 \"_result.items\" 를 확인하세요.")}
    res = _emit_items(env, out)
    if skipped:
        res["skipped_rows"] = skipped
    if keep_missing:
        res["keep_missing"] = keep_missing
        res["warning"] = (f"keep 중 어느 행에도 없는 필드: {keep_missing} — 승계되지 않았습니다.")
    return res


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
        return {"success": False, "error": "join: on(조인 키 열 이름)이 필요합니다."}
    on = str(on)
    # left/right 직접 공급(& 병렬 대신 — $변수 참조로 파이프 낀 가지를 먹일 때).
    # 명시 파라미터가 파이프 입력보다 우선한다. (리터럴 get = 코퍼스-param 가드 가시성)
    if params.get("left") is not None and params.get("right") is not None:
        prev = [params.get("left"), params.get("right")]
    if isinstance(prev, list) and len(prev) > 2:
        # 셋째 분기를 조용히 버리지 않는다(⑧′ 부류) — join 은 이항 연산
        return {"success": False,
                "error": f"join: 입력이 {len(prev)}개 — join 은 두 입력만 받습니다. 여러 개는 [table:union/merge]로 합치거나 둘씩 나눠 join 하세요."}
    if not isinstance(prev, list) or len(prev) < 2:
        return {"success": False, "error": "join: & 병렬로 두 입력이 필요합니다. 예: [A] & [B] >> [table:join]{on: \"연도\"}"}
    a, b = _extract_two(prev)
    if a is None or b is None:
        # 입력 개수 탓으로 돌리면 자가교정 단서가 틀린다 — 진짜 원인은 분기 출력이 통화가 아님.
        _sides = "·".join(s for s, o in (("첫째", a), ("둘째", b)) if o is None)
        return {"success": False,
                "error": f"join: {_sides} 분기의 출력이 통화(items/table)로 파싱되지 않습니다"
                         f"(스칼라·평문 반환 등) — 통화를 내는 액션·op 으로 바꾸세요."}
    ta, _ = _get_table(a)
    tb, _ = _get_table(b)
    if ta is None or tb is None:
        # 두 입력이 items 통화면 items inner join (table 분기와 대칭).
        # items 행도 dict 라 키 필드로 조인 가능 — merge/union 이 items 를 받는 것과 일관.
        ra, _ = _get_items(a)
        rb, _ = _get_items(b)
        if ra is None or rb is None:
            return {"success": False, "error": "join: 두 입력이 같은 통화여야 합니다(둘 다 table 또는 둘 다 items)."}
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
        return _emit_items(_carry_flags([a, b], with_total=False), out)
    ca = [str(c) for c in (ta.get("columns") or [])]
    cb = [str(c) for c in (tb.get("columns") or [])]
    if on not in ca or on not in cb:
        return {"success": False, "error": f"join: 키 '{on}'이 양쪽 table 열에 모두 있어야 합니다(좌:{ca} 우:{cb})."}
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
    return _emit_table({**_carry_flags([a, b], with_total=False), "table": {}}, {"columns": out_cols, "rows": out_rows})


# ── 문서 IR(공유 문서 모델) → 산출물 emitter ───────────────────────────
# 문서 IR: {title?, blocks:[{type, ...}]}. 블록 타입:
#   heading{level,text} · paragraph{text} · list{ordered?,items[]} · image{src,caption?}

# 문서 emitter(structure/document)는 doc_build.py·doc_formats.py 로 분리(2026-08-06,
# 1500줄 규칙). 이 파일은 통화 대수(관계대수)만 — 두 도메인은 서로를 참조하지 않는다.
from common.pkg_utils import load_sibling

_docs = load_sibling(__file__, "doc_build")
structure_document = _docs.structure_document
render_document = _docs.render_document


_DISPATCH = {
    "data_filter": _op_filter,
    "data_sort": _op_sort,
    "data_take": _op_take,
    "data_select": _op_select,
    "data_rename": _op_rename,
    "data_flatten": _op_flatten,
    "data_dedup": _op_dedup,
    "data_since": _op_since,
    "data_groupby": _op_groupby,
    "data_join": _op_join,
    "data_union": _op_union,
    "data_merge": _op_merge,
}


def execute(tool_input: dict, context):
    """표준 시그니처. context.tool_name 으로 동사 분기, _prev_result에서 통화 수용."""
    tool_name = getattr(context, "tool_name", None)
    # 표준 코어 emitter(table:structure/document) — 변환자와 달리 산출 경로(output_dir) 사용.
    if tool_name == "structure_document":
        return structure_document(tool_input, context.output_dir())
    if tool_name == "render_document":
        return render_document(tool_input, context.output_dir())
    fn = _DISPATCH.get(tool_name)
    if not fn:
        return {"success": False, "error": f"data-ops: 알 수 없는 변환자 '{tool_name}'."}
    params = dict(tool_input or {})
    prev = _parse_prev(params.get("_prev_result"))
    if prev is None:
        # 파이프 입력(>>)이 없으면 params 에서 통화를 직접 수용 — 단독 호출/자가점검 지원.
        # (파이프 통화와 params 통화는 같은 모양이라 정합적이다.)
        # 이항(merge/join/union): (left,right)/(table1,table2)/(a,b) 쌍 또는 inputs 리스트 → [A, B].
        # 단항(filter/sort/take/select/dedup/groupby): items(단일 통화) 또는 table(표형).
        for k1, k2 in (("left", "right"), ("table1", "table2"), ("a", "b")):
            if params.get(k1) is not None and params.get(k2) is not None:
                prev = [params[k1], params[k2]]
                break
        if prev is None:
            if isinstance(params.get("inputs"), list):
                prev = params["inputs"]
            elif params.get("items") is not None:
                prev = {"items": params["items"]}
            elif params.get("table") is not None:
                prev = {"table": params["table"]}
    if prev is None:
        return {"success": False, "error": (
            f"{tool_name}: 입력 통화가 없습니다. 변환자는 >> 파이프로 앞 액션의 "
            "items 통화(표형은 table)를 받습니다. 예: [sense:search]{...} >> [table:filter]{where:...}"
        )}
    return fn(prev, params)
