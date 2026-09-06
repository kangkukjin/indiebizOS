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
    if isinstance(obj, dict) and isinstance(obj.get("ref"), dict) and (obj.get("_spilled") or obj.get("spilled")):
        # 스필 참조 봉투(M5 자동 스필·write spill) — 변환자는 투명하게 본문을 읽는다
        try:
            from common.spill import resolve_ref
            resolved, _err = resolve_ref(obj)
            if _err is None and resolved is not obj:
                obj = resolved
        except Exception:
            pass
    if isinstance(obj, dict):
        r = obj.get("items")            # 단일 통화 — 모든 생산자가 items 방출
        if isinstance(r, list):
            return r, obj
        # (B53-2 의 자리는 여기가 아니라 `items:` 파라미터 주입 경로다 — execute 의 coerce_items_payload.
        #  여기서 columns/rows 를 items 로 파생하면 38회차 계약(명시 표형은 표형 유지·혼합 입력 정직
        #  거절)이 깨진다 — 2026-09-02 배터리 실측 7건.)
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
        # 단일 통화 items(행 dict) → table 재구성. 열은 첫 행 하나가 아니라 전 행에서
        # 처음 나타난 순서로 합친다. 희소 행의 뒤쪽 키를 첫 행 스키마로 잘라 버리면
        # union/join 같은 표 연산이 실제 값을 None 으로 바꾸는 침묵 손실이 된다(B36-1).
        items = obj.get("items")
        if isinstance(items, list) and items and all(isinstance(x, dict) for x in items):
            cols = []
            seen = set()
            for item in items:
                for key in item:
                    if key not in seen:
                        seen.add(key)
                        cols.append(key)
            return {"columns": cols, "rows": [[d.get(c) for c in cols] for d in items]}, obj
    return None, None


def _explicit_table(obj) -> bool:
    """★형태 보존(언어 개정 2026-09-06, ep2882): 명시 표형(columns/rows·table 키) 봉투인가 — items 재구성
    가능(_get_table 승격)과 다르다. 변환자는 입력 형태를 보존한다: items→items, 표형은 표형 입력에만. 옛
    union·select·rename·groupby 는 items 를 표로 바꿔 냈고 2차 union 의 0행 가지(승격 불가)에서 죽었다."""
    if not isinstance(obj, dict):
        return False
    t = obj.get("table")
    if isinstance(t, dict) and isinstance(t.get("rows"), list):
        return True
    return isinstance(obj.get("rows"), list) and isinstance(obj.get("columns"), list)


def _table_or_empty(obj):
    """표 경로 분기 승격 — _get_table, 단 빈 items 는 0행 표(0행 통화도 통화다, 2026-09-06)."""
    t = _get_table(obj)[0]
    if t is None and isinstance(obj, dict) and isinstance(obj.get("items"), list) and not obj["items"]:
        return {"columns": [], "rows": []}
    return t


# 봉투 범위·거울 재투영은 형제 envelope_scope 로 분리(2026-09-02, 1500줄 규칙). 재수출이라 호출부는 그대로다.
from common.pkg_utils import load_sibling as _load_sibling_scope

_scope = _load_sibling_scope(__file__, "envelope_scope")
_CURRENCY_KEYS = _scope._CURRENCY_KEYS
_reproject_mirrors = _scope._reproject_mirrors
_restate_scope = _scope._restate_scope


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
    _restate_scope(out, len(_orig[0]) if isinstance(_orig[0], list) else None, len(new_items))
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
    _prior = next((len(o) for o in _orig if isinstance(o, list)), None)
    _restate_scope(out, _prior, len(new_table.get("rows") or []))
    # 표 경로의 거울 키는 행 dict 로 투영한다 — 도메인 키에 열-배열을 꽂으면 모양이 깨진다.
    return _reproject_mirrors(out, _orig, _row_dicts(new_table))


# 정직한 거절 층(부재 판정·필드 오류문·each 봉투 처방)은 diagnostics.py 로 분리
# (2026-08-23, 1500줄 규칙). 재수출이라 기존 호출부는 그대로다.
from common.pkg_utils import load_sibling as _load_sibling_diag

_diag = _load_sibling_diag(__file__, "diagnostics")
_observed_fields = _diag._observed_fields
_absent_fields = _diag._absent_fields
_field_missing_error = _diag._field_missing_error


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
    # ★B53-2: 키만 찍으면 "찾지 못했습니다. 받은 봉투의 키: ['items']" 라는 자기모순이 난다 —
    #   그 자기모순을 막으려 세운 진단 한 벌(common.currency.currency_shape_note, B19-2)을 쓴다.
    try:
        from common.currency import currency_shape_note as _shape_note
        keys = _shape_note(prev)
    except ImportError:
        keys = sorted(prev.keys()) if isinstance(prev, dict) else type(prev).__name__
    return {"success": False,
            "error": f"{verb}: 입력에서 items 통화를 찾지 못했습니다. 받은 봉투: {keys} — "
                     f"앞 액션이 통화(items/table)를 내지 않는 생산자(returns: scalar/effect)일 수 "
                     f"있습니다. 통화를 내는 액션·op 으로 바꾸거나 선언(returns)을 확인하세요."}


# 조건 언어(where 미니 DSL)·정렬 키는 where_dsl.py 로 분리(2026-08-22, 1500줄 규칙).
# 이 파일은 통화 대수(관계대수)만 — 판정은 저 모듈이 한다.
from common.pkg_utils import load_sibling as _load_sibling_where

_wdsl = _load_sibling_where(__file__, "where_dsl")
_WhereError = _wdsl._WhereError
_OPS = _wdsl._OPS
_match = _wdsl._match
_where_fields = _wdsl._where_fields
_sort_key = _wdsl._sort_key
_sort_records = _wdsl._sort_records
_as_num = _wdsl._as_num
_num_eq = _wdsl._num_eq
_num_cmp = _wdsl._num_cmp
_parse_where_str = _wdsl._parse_where_str
_group_keys = _load_sibling_where(__file__, "group_keys")
_group_identity, _relation_identity = _group_keys.group_identity, _group_keys.relation_identity
# 관계 키 어휘(키 자리 문법)는 형제 모듈이 소유 — 이름만 재수출해 호출부는 불변.
_norm, _join_key, _join_keys = _group_keys.norm_key, _group_keys.join_key, _group_keys.join_keys
_join_row_key, _key_names, _dedup_key = _group_keys.join_row_key, _group_keys.key_names, _group_keys.dedup_key


def _sort_multi(records, keys, desc=False):
    """다단계 정렬 — 단일 키 판정기(_sort_records)를 형제 모듈에 주입한다."""
    return _group_keys.sort_multi(records, keys, desc, _sort_records)
# 패키지 소유 정책(집계 관측·그룹 표시값·since 원장 키) — 값의 뜻은 common 이 소유.
_value_semantics = _load_sibling_where(__file__, "dataops_value_semantics")

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




# ───────────────────────── 단항 동사 ─────────────────────────

def _op_filter(prev, params):
    """where 문법 오류(모르는 연산자·깨진 정규식)를 정직 거절로 바꾸는 겉옷 (B19-1)."""
    try:
        return _op_filter_impl(prev, params)
    except _WhereError as e:
        return {"success": False, "error": f"filter: {e}"}


def _op_filter_impl(prev, params):
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
        return _diag._empty_filter_note(_emit_items(env, [r for r in dict_recs if _match(r, where)]), where, dict_recs, _where_fields(where))
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
        return _diag._empty_filter_note(_emit_table(env, {"columns": cols, "rows": rows}), where, dicts, _where_fields(where))
    # items/table 이 없어도 도메인 봉투의 원천 행(data/results)이 있으면 거기서 (sort 와 대칭)
    _wf = _where_fields(where)
    dug = _rows_for_field(prev, _wf[0] if _wf else None)
    if dug:
        missing = [f for f in _wf if not any(f in r for r in dug)]
        if missing:
            return _field_missing_error("filter", missing, dug)
        return _diag._empty_filter_note(_emit_items({}, [r for r in dug if _match(r, where)]), where, dug, _wf)
    return _no_currency_error("filter", prev)


def _op_sort(prev, params):
    """items|table → 정렬. params.by(필드/열명 또는 다단계 키 목록), params.desc(bool).

    by 가 목록이면 다단계 정렬(2026-09-07 언어 개정) — 앞 키가 우선, 동점을 뒤 키가
    가른다. desc 는 전 키에 같이 걸린다(방향을 섞으려면 덜 중요한 키부터 sort 를 두 번).

    by 가 items/table 에 없으면 원천 행(data/results — groupby 의 _rows_for_field 선례)까지
    거슬러 찾고, 그래도 없으면 에러(2026-08-07 — 옛 침묵 no-op 은 원순서를 success 로
    돌려줘 하류 전체가 조용히 틀렸다. filter 의 '침묵 부분일치 금지' 원칙과 동일).
    """
    by_raw = params.get("by")
    desc = bool(params.get("desc", False))
    # F13-3 (2026-08-19 상상훈련 13회차): 자연 동의어 order:"desc"/"asc" 값-해석 —
    # 예전엔 경고만 뜨고 오름차순이 success 로 나가 요청 의미가 반전됐다.
    # 값-해석이라 aliases 블록(이름 별칭)으로는 못 나른다("desc" 문자열은 truthy).
    if "desc" not in params and "order" in params:
        desc = str(params.get("order") or "").strip().lower() in (
            "desc", "descending", "reverse", "내림차순")
    keys, kerr = _key_names(by_raw, "sort", "by")
    if kerr:
        return kerr
    if not keys:
        return {"success": False, "error": "sort: by(정렬 기준 필드/열명)가 필요합니다."}
    by = keys[0] if len(keys) == 1 else list(keys)   # 진단문에 적히는 표기
    # 파고들기는 입구가 담당 (F6) — by 가 카드 투영에 접혔으면 원천 행이 돌아온다.
    recs, env = _get_items_for_fields(prev, keys)
    if recs is not None:
        dict_recs = [r for r in recs if isinstance(r, dict)]
        if not dict_recs or all(any(k in r for r in dict_recs) for k in keys):
            srt = _sort_multi(dict_recs, keys, desc)
            return _emit_items(env, srt)
    table, tenv = _get_table(prev)
    if table is not None and all(  # vj-ok: 열 이름 실존 검사
            k in [str(c) for c in (table.get("columns") or [])] for k in keys):
        dicts = _row_dicts(table)
        dicts = _sort_multi(dicts, keys, desc)
        cols = table.get("columns") or []
        rows = [[d.get(str(c)) for c in cols] for d in dicts]
        return _emit_table(tenv, {"columns": cols, "rows": rows})
    # 손실 투영(예: 주가 table=날짜·종가)이 정렬 키를 접은 경우 — 원천 행까지 거슬러 찾기
    dug = _rows_for_field(prev, keys)
    if dug and all(any(k in r for r in dug) for k in keys):
        srt = _sort_multi(dug, keys, desc)
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
    _rows = [r for r in (recs or []) if isinstance(r, dict)] or dug or []
    miss = [k for k in keys if not any(k in r for r in _rows)] if _rows else list(keys)
    if avail:
        miss = [k for k in keys if k not in avail] or miss
    return {"success": False,
            "error": f"sort: '{"', '".join(miss)}' 필드가 어느 행에도 없습니다.{hint}"}


# [table:chunk] 는 형제 모듈 chunk_ops.py (2026-09-05 어휘 개정, 1500줄 규칙 분리) — 형제 로더로만 불러온다(패키지 폴더는 sys.path 에 없다)
_chunk_ops = _load_sibling_where(__file__, "chunk_ops")
_op_chunk = _chunk_ops._op_chunk


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
    # 형태 보존(언어 개정 2026-09-06): 표 경로는 명시 표형 입력에만 — items 는 아래 items 경로.
    table, env = _get_table(prev) if _explicit_table(prev) else (None, None)
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

    # 형태 보존(언어 개정 2026-09-06): 표 경로는 명시 표형 입력에만.
    table, env = _get_table(prev) if _explicit_table(prev) else (None, None)
    if table is not None:
        src_cols = [str(c) for c in (table.get("columns") or [])]
        # 부재 판정은 판정기에게 (B28-1) — 관측이 0이면 부재를 주장하지 않는다
        missing = _absent_fields(list(m), _observed_fields(columns=src_cols))
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
        # 부재 판정은 판정기에게 (B28-1) — 빈손이면 형제 8개 verb 처럼 0행으로 흘려보낸다
        missing = _absent_fields(list(m), _observed_fields(rows=dict_recs))
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
    """items|table → 중복 제거(첫 항목 유지). params.by(키 필드/열 또는 복합키 목록, 기본 title).

    by 가 목록이면 그 열들의 조합이 같은 행을 중복으로 본다(2026-09-07 언어 개정).

    by 미지정 시 items는 title, table은 첫 열을 키로. 정규화(공백/대소문자) 후 동등 비교.
    (newspaper 내부에 묻혀있던 _dedup_rank를 통화 동사로 끌어올림 — 전 생산자 공용화.)
    """
    keys, kerr = _key_names(params.get("by"), "dedup", "by")
    if kerr:
        return kerr
    # 파고들기는 입구가 담당 (F6). 기본(title)은 관례라 파고들지 않는다.
    recs, env = _get_items_for_fields(prev, keys or None)
    if recs is not None:
        dict_recs = [r for r in recs if isinstance(r, dict)]
        # 명시 by 가 어느 행에도 없으면 무동작이 success 로 위장된다(⑧′). 기본(title)은 관례라 관대.
        if keys and dict_recs:
            missing = [k for k in keys if not any(k in r for r in dict_recs)]
            if missing:
                return _field_missing_error("dedup", missing, dict_recs)
        use = keys or ["title"]
        seen, out = set(), []
        for r in dict_recs:
            k = _dedup_key([r.get(c) for c in use])
            if k and k in seen:
                continue
            seen.add(k)
            out.append(r)
        return _emit_items(env, out)
    table, env = _get_table(prev)
    if table is not None:
        cols = [str(c) for c in (table.get("columns") or [])]
        missing = [k for k in keys if k not in cols]
        if missing:
            # 잘못된 by 를 조용히 첫 열로 폴백하면 엉뚱한 키로 중복 제거된다(⑧′)
            return {"success": False,
                    "error": f"dedup: '{"', '".join(missing)}' 열이 없습니다. 실제 열: {cols}"}
        idx = [cols.index(k) for k in keys] if keys else [0]
        seen, rows = set(), []
        for r in table.get("rows") or []:
            k = _dedup_key([(r[i] if i < len(r) else None) for i in idx])
            if k and k in seen:
                continue
            seen.add(k)
            rows.append(r)
        return _emit_table(env, {"columns": cols, "rows": rows})
    return _no_currency_error("dedup", prev)


# 명시 count(field)는 실존(non-null) 관측 수. 기본 그룹 행수 count는 _op_groupby가
# 내부 명세 row_count 로 별도 처리한다(G39-1) — 공개 op를 하나 더 만들지 않는다.
# 관측·누산의 실제 판정은 value_semantics.aggregate_members 한 벌이다.
_agg_spec = _load_sibling_where(__file__, "agg_spec")
_AGG = _agg_spec._AGG

_aggregate_members = _value_semantics.aggregate_members

_group_output_value = _value_semantics.strict_json_value


def _rows_for_field(obj, field):
    """그룹/집계 키 field(이름 하나 또는 복합키 목록)를 담은 표현을 list-of-dicts 로 반환.

    공유 통화 items(및 table) 외에도 도메인 생산자가 원천 행을 다른 키
    (data/results)에 담는 경우까지 후보로 본다. 옛 손실적 카드 투영이 도메인 필드를
    meta 문자열로 접어 groupby 가 그 필드를 못 찾던 문제(예: realty 가 '법정동'을 meta 로
    접음 — 원천은 data:[{...법정동...}] 에 그대로 있음)를 푼다.

    후보 중 field 를 **전부** 가진 첫 리스트를 우선(없으면 첫 비어있지 않은 리스트)으로
    고른다. 복합키(2026-09-07 언어 개정)에서는 키 하나만 가진 투영을 고르면 나머지
    키가 "필드 없음" 으로 죽으므로, 판정은 키 집합 단위여야 한다.
    """
    fields = [str(f) for f in ([field] if isinstance(field, str) else list(field or [])) if f]
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
    if fields:
        for _, rows in cands:
            if all(any(f in r for r in rows) for f in fields):
                return rows
    for _, rows in cands:
        if rows:
            return rows
    return cands[0][1]


def _op_groupby(prev, params):
    """items|table|도메인 행목록 → 그룹 집계. params.by(그룹 키 또는 복합키 목록), params.agg.

    agg 형태: {새열명: [op, 원본열]} 또는 {원본열: op}. op = count/sum/avg/min/max.
    기본: agg 없으면 그룹별 count.  반환 = [by열들, 집계열들].

    by 가 목록이면 교차집계(2026-09-07 언어 개정) — 키마다 제 열로 나오므로 하류
    filter/sort 가 그 열들을 그대로 쓴다.

    형제 동사들처럼 items 를 받는다. 나아가 옛 카드 투영이 그룹 키를 접은 경우
    원천 data/items 행까지 거슬러 키를 찾는다(_rows_for_field).
    """
    by_raw = params.get("by")
    if by_raw is None:
        by_raw = params.get("key")            # 별칭은 **미지정일 때만** 넘긴다 — `or` 사슬은
    if by_raw is None:                        # by: [] 를 삼켜 형제 동사와 다른 진단을 냈다
        by_raw = params.get("group_by")
    keys, kerr = _key_names(by_raw, "groupby", "by")
    if kerr:
        return kerr
    if not keys:
        return {"success": False, "error": "groupby: by(그룹 키 열)가 필요합니다."}
    dicts = _rows_for_field(prev, keys)
    if not dicts:
        # F16-2 (2026-08-20 상상훈련 16회차): _rows_for_field 는 빈 리스트를 후보에서
        # 제외하므로 items:[] (통화 실존·0행)와 통화 부재가 여기서 접힌다. 빈손은
        # filter/take 처럼 0행으로 흘려보낸다(F17 "빈손 계약은 verb 마다 심사"의 잔여 verb).
        recs, _env0 = _get_items(prev)
        if recs is not None and len(recs) == 0:
            return {"success": True, "items": [], "count": 0,
                    "message": "groupby: 0행 입력 — 집계할 행이 없습니다."}
        return {"success": False, "error": "groupby: 입력에서 items 통화(또는 data/items 행 목록)를 찾지 못했습니다."}
    missing = [k for k in keys if not any(k in d for d in dicts)]
    if missing:
        # 없는 by 를 조용히 받으면 전 행이 null 한 그룹으로 뭉개진다(⑧′ 실측: [[null, 83]])
        return _field_missing_error("groupby", missing, dicts)
    _, env = _get_table(prev)
    env = env or {}
    # agg 모양 사전·정규화는 형제 모듈(agg_spec.py, 1500줄 규칙 분리 2026-08-27)
    specs, auto_named, _agg_err = _agg_spec.normalize_agg(
        params.get("agg"), dicts, _field_missing_error)
    if _agg_err:
        return _agg_err
    # 그룹핑 (입력 순서 보존). 표시값은 엄격 JSON — NaN/Infinity 키가 통화에 실려
    # 직렬화를 깨지 않게 하되, 강제한 수를 group_key_coercions 로 자백한다.
    groups, labels, order = {}, {}, []
    group_key_coercions = []
    for d in dicts:
        values = [d.get(k) for k in keys]
        gid = tuple(_group_identity(v) for v in values)
        if gid not in groups:
            groups[gid] = []
            cells = []
            for key_name, raw_value in zip(keys, values):
                label, changed = _group_output_value(raw_value)
                cells.append(label)
                if changed:
                    group_key_coercions.append({
                        "field": key_name, "key": label, "nonfinite_parts": changed,
                    })
            labels[gid] = cells
            order.append(gid)
        groups[gid].append(d)
    # 복합키는 키마다 제 열로 나온다(2026-09-07 언어 개정) — 합성 문자열 한 칸으로 접으면
    # 하류 filter{계약유형 == '전세'}·sort 가 다시 쪼개야 한다(ep2951 이 하려던 바로 그 다음 문장).
    out_cols = list(keys) + [s[0] for s in specs]
    out_rows = []
    aggregation_skips = []
    aggregation_errors = []
    for gid in order:
        cells = labels[gid]
        gk = cells[0] if len(cells) == 1 else list(cells)   # 신고문의 그룹 표기
        members = groups[gid]
        row = list(cells)
        for out_col, op, src in specs:
            value, skipped, aggregate_error = _aggregate_members(op, members, src)
            row.append(value)
            if skipped:
                aggregation_skips.append({
                    "group": gk, "output": out_col, "op": op,
                    "source": src, "skipped": skipped, "rows": len(members),
                })
            if aggregate_error:
                aggregation_errors.append({
                    "group": gk, "output": out_col, "op": op,
                    "source": src, "error": aggregate_error,
                })
        out_rows.append(row)
    # 형태 보존(언어 개정 2026-09-06): 집계도 변환자다 — items 입력엔 items(그룹 행 dict),
    # 명시 표형 입력에만 표형. 옛 판은 늘 표를 내 `$집계.items` 참조·2차 union 을 막았다.
    if _explicit_table(prev):
        res = _emit_table(env, {"columns": out_cols, "rows": out_rows})
    else:
        res = _emit_items(env, [dict(zip(out_cols, row)) for row in out_rows])
    res = _value_semantics.attach_group_reports(
        res, group_key_coercions, aggregation_skips, aggregation_errors)
    if auto_named and isinstance(res, dict) and res.get("success", True):
        # 자동 명명 열을 봉투에 자백 — 다음 스텝(sort{by:...} 등)이 이 이름을 알아야
        # 한 왕복으로 이어진다 (ep1116: 'count_name' 을 몰라 하류 sort 가 죽었다).
        note = (f"groupby: 집계열 이름 = {auto_named} ({{원본열: op}} 형태는 'op_원본열' 자동 명명 — "
                f"직접 정하려면 {{새열명: [op, 원본열]}})")
        res["message"] = f"{res['message']} · {note}" if res.get("message") else note
    return res


# ───────────────────────── 이항 동사 (& 병렬 두 입력) ─────────────────────────

# [table:since] 는 형제 모듈 since_ops.py — 유일하게 원장(data/table_since.db)을 쥔
# 변환자라 순수 대수와 갈라 둔다. 통화 도우미는 인자로 넘긴다(branch_protocol 선례).
_since_ops = _load_sibling_where(__file__, "since_ops")
# ★원장 연결은 **이 이름으로** 넘긴다 — 시험이 임시 DB 로 갈아끼우는 지점이
# handler 쪽 이름이라(test_condition_observability 등 3건), 형제 모듈이 제 전역을
# 쓰면 monkeypatch 가 조용히 헛돌아 실제 원장에 쓰게 된다(★시험이 실물에 쓰는 부류).
_since_conn = _since_ops.since_conn


def _op_since(prev, params):
    return _since_ops.op_since(prev, params, _get_items, _emit_items,
                               _no_currency_error, _field_missing_error, _value_semantics,
                               _since_conn)


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


# 죽은 분기 규약(2026-08-30 언어 개정, ep2355) — 정본=branch_protocol.py, 통화 getter 는 주입.
_branch_proto = _load_sibling_where(__file__, "branch_protocol")


def _handle_dead_branches(op_name, objs, params):
    return _branch_proto.handle_dead_branches(op_name, objs, params, _get_items, _get_table)


def _op_union(prev, params):
    """병렬(&) 분기들의 table(또는 items)을 행 결합. 같은 통화끼리.

    table: 열 이름으로 통합(순서 보존, 한쪽에만 있는 열은 다른쪽 None). items: 단순 concat.
    중복 제거가 필요하면 뒤에 >> dedup. 분기 수 제한 없음(셋 이상 전부).
    죽은 분기=기본 건너뛰고 신고, on_error:"stop"=전부-아니면-실패 (2026-08-30 개정).
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
    _total = len(objs)
    objs, _dead, _err = _handle_dead_branches("union", objs, params)
    if _err:
        return _err
    # ★형태 보존(언어 개정 2026-09-06): 표 경로는 명시 표형 분기가 있을 때만 — items 끼리는 items(선언
    #   emits:items 와 한 벌). 옛 판은 표를 내고 `& 0행 items >> union` 에서 '1=table, 2=items' 로 죽었다(ep2882).
    tables = ([_table_or_empty(o) for o in objs]
              if any(_explicit_table(o) for o in objs) else [None] * len(objs))
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
        return _branch_proto.attach_dead_note(
            _attach_branch_warning(_attach_shape_warning(env, col_sets), objs), _dead, _total)
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
        return _branch_proto.attach_dead_note(
            _attach_branch_warning(_attach_shape_warning(env, key_sets), objs), _dead, _total)
    # 효과 봉투(write·notify 같은 부수효과 결과 — items/table 없는 success 봉투)는 **1행 통화**로
    # 받는다(2026-09-05 언어 개정, ep2827): 병렬 부수효과 문장 `[self:write] & [self:write] >>
    # [table:union]` 이 "통화 종류가 같아야" 로 죽던 자리. 결과 = 효과 행(분기당 1행) + items 행,
    # effect_rows 로 어느 분기가 효과였는지 신고. table 과의 혼합은 종전대로 정직 거절.
    eff_idx = [i for i, o in enumerate(objs, 1) if _is_effect_env(o)]
    if eff_idx and all(il is not None or _is_effect_env(o) for il, o in zip(item_lists, objs)):
        out = []
        for il, o in zip(item_lists, objs):
            out.extend(il if il is not None else [_effect_row(o)])
        env = _emit_items(_carry_flags(objs), out)
        env["effect_rows"] = eff_idx
        env["note"] = (f"분기 {eff_idx} 은(는) 효과 봉투(부수효과 결과)라 1행씩 실었습니다 — "
                       "행 = 그 봉투의 필드(path·size·message …).")
        return _branch_proto.attach_dead_note(_attach_branch_warning(env, objs), _dead, _total)
    return {"success": False,  # 죽은 분기는 걸러진 뒤 = 진짜 통화 혼합 — 분기별 통화를 이름 대 준다
            "error": "union: 모든 입력의 통화 종류가 같아야 합니다(전부 table 또는 전부 items). "
                     f"분기별 통화: {_branch_proto.currency_kinds(objs, _get_items, _get_table)}."}


def _is_effect_env(o) -> bool:
    """효과 봉투 판정 — 성공 dict 이면서 통화(items/table)를 안 실은 것(부수효과 액션의 결과 모양)."""
    return (isinstance(o, dict) and o.get("success") is True
            and _get_items(o)[0] is None and _get_table(o)[0] is None)


def _effect_row(o: dict) -> dict:  # 효과 봉투→1행. 정본=common.currency.effect_row([table:each]{collect} 와 한 벌, 2026-09-06 G55-1)
    from common.currency import effect_row
    return effect_row(o)


def _attach_branch_warning(env, objs):
    """★B24-1(c) 24회차 상상훈련: 병렬 가지가 죽어도 이항 변환자가 **조용히 삼켰다**.
    죽은 가지의 봉투는 items:[] 라 union/merge/join 이 0행으로 흘려보내고, 사용자는
    "두 소스를 합쳤다" 로 읽는다(실측: 살아있는 3행만 나오고 경고 0). 결합은 정직하게
    하되 무엇이 빠졌는지 말한다 — _attach_shape_warning(공유 칸 0)과 같은 배관."""
    bad = []
    for i, o in enumerate(objs or [], 1):
        if isinstance(o, dict) and (o.get("success") is False
                                    or (o.get("error") and o.get("success") is not True)):
            bad.append(i)
    if not bad:
        return env
    note = (f"결합 입력 중 분기 {', '.join(map(str, bad))} 이(가) 실패했습니다 — "
            f"그 분기는 0행으로 흘렀습니다. 결과는 부분입니다(살아남은 분기만 합쳐졌습니다).")
    prev = env.get("warning") if isinstance(env, dict) else None
    return {**env, "warning": (prev + " / " + note) if prev else note}


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
    """병렬(&) 분기들의 items를 합친다(concat). params.by 지정 시 그 키(또는 복합키 목록)로 중복 제거.

    여러 검색 결과를 한 목록으로 모을 때. (table 결합은 union.) 분기 수 제한 없음.
    죽은 분기=기본 건너뛰고 신고, on_error:"stop"=전부-아니면-실패 (union 과 한 벌).
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
    _total = len(objs)
    objs, _dead, _err = _handle_dead_branches("merge", objs, params)
    if _err:
        return _err
    item_lists = [_get_items(o)[0] for o in objs]
    if any(il is None for il in item_lists):
        _no = [str(i) for i, il in enumerate(item_lists, 1) if il is None]  # 죽은 분기는 걸러진 뒤 — 남은 건 table 전용 산 분기
        return {"success": False,
                "error": f"merge: 분기 {', '.join(_no)} 에 items 통화가 없습니다(표형 table 만 실림) — "
                         f"표형 결합은 table:union."}
    out = []
    for il in item_lists:
        out.extend(il)
    keys, kerr = _key_names(params.get("by"), "merge", "by")
    if kerr:
        return kerr
    if keys or params.get("dedup"):
        use = keys or ["title"]        # 복합키(2026-09-07 개정) — dedup 과 같은 판정 한 벌
        seen, dd = set(), []
        for r in out:
            if not isinstance(r, dict):
                continue
            k = _dedup_key([r.get(c) for c in use])
            if k and k in seen:
                continue
            seen.add(k)
            dd.append(r)
        out = dd
    return _branch_proto.attach_dead_note(
        _attach_branch_warning(_emit_items(_carry_flags(objs), out), objs), _dead, _total)


def _op_flatten(prev, params):
    """행 속 중첩 목록 필드를 펼쳐(unnest) 행들로.

    field 경로의 값이 목록이면 그 원소들이 새 행이 되고, {items: [...]} 봉투면
    items 로 자동 승격. keep=[부모 필드]는 각 새 행에 승계(충돌 시 _2 접미 —
    침묵 오선택 방지). 목록 아닌 행은 건너뛰되 skipped_rows 로 신고한다.
    ★기본값 "_result" 는 은퇴한 옛 each 계약의 잔영이다 — 지금은 그 자리로 온
    옛 문장에게 "flatten 을 빼라"는 참인 처방을 돌려주는 이행 진단용으로만 남는다.
    """
    recs, env = _get_items(prev)
    if recs is None:
        t, _ = _get_table(prev)
        if t is not None:
            return {"success": False,
                    "error": "flatten: items 통화 전용입니다(표형 table 셀엔 중첩 목록이 없습니다)."}
        return {"success": False,
                "error": "flatten: 입력에서 items 통화를 찾지 못했습니다. 중첩 목록을 가진 통화 뒤(>>)에 놓고 field 로 그 필드를 지목하세요."}
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
        # 걷는 규칙의 정본은 common.field_path 한 벌 (2026-08-27 경로 방언 통일 —
        # 리스트 숫자 인덱스는 블록 술어의 문서화된 경로 문법을 승계한다)
        from common.field_path import MISSING, walk_path
        value = walk_path(row, path)
        return None if value is MISSING else value

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
        elif isinstance(v, dict):
            # ★레코드 하나도 '펼 수 있는 것'이다 (2026-08-23).
            # each 의 do 가 목록이 아니라 **레코드 하나**를 내는 경우(대다수의 조회 액션이
            # 그렇다)가 여기로 떨어져 "목록을 가진 행이 없습니다" 로 거절됐다. 그런데 형제
            # 변환자들의 오류문은 바로 그 상황에서 ">> [table:flatten] 을 붙이세요" 라고
            # 안내한다 — **안내대로 했는데 안 되는** 상태였다. 안내가 맞는지까지 봐야
            # 안내다. 레코드는 1행짜리 표이므로 그대로 한 행이 된다(손실 0).
            # 스칼라는 계속 건너뛴다 — {value: …} 로 감싸면 field 오타가 조용히
            # '성공'으로 위장돼 정직한 거절이 사라진다.
            v = [v]
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
        # ★기본 field(_result)로 왔는데 어느 행에도 _result 가 없다 = 입력이 **이미 평탄**하다.
        #   `[table:each]` 가 통화를 그대로 내게 된 뒤(2026-08-23 언어 개정) 옛 관용구
        #   `each >> flatten` 이 정확히 여기로 온다(retired-ok: 옛 문장을 이름 불러
        #   거절하는 이행 진단). "목록이 없다"만 말하면 사용자는 field 를
        #   고치려 들지만, 참인 처방은 **flatten 을 빼는 것**이다.
        if field == "_result":
            return {"success": False,
                    "error": (f"flatten: 입력이 이미 평탄합니다 — 어느 행에도 '_result' 가 없습니다"
                              f"(행 {len(recs)}개). 행 필드 예: {sample} — [table:each] 는 통화를 "
                              f"그대로 내므로 flatten 없이 바로 이으세요. 중첩 목록을 펴려는 "
                              f"것이었다면 field 로 그 필드를 지목하세요.")}
        return {"success": False,
                "error": (f"flatten: field '{field}' 에서 목록을 가진 행이 없습니다"
                          f"(행 {len(recs)}개 전부 건너뜀). 행 필드 예: {sample}")}
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
    """두 table을 키 열로 inner join. params.on(양쪽 공통 키 열명 또는 복합키 목록, 필수).

    결과 열 = 좌측 전체 + 우측(키 제외). 서로 다른 소스를 한 키로 묶어 분석.
    on 이 목록이면 복합키 조인(2026-09-07 언어 개정) — 키 일부가 빈 행은 조인 밖.
    예: [sense:stock]{op:history} & [sense:world_bank]{...} >> [table:join]{on: "연도"}.
    """
    keys, kerr = _key_names(params.get("on") or params.get("key"), "join", "on")
    if kerr:
        return kerr
    if not keys:
        return {"success": False, "error": "join: on(조인 키 열 이름)이 필요합니다."}
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
    # B38-2(2026-08-25): items 봉투도 _get_table 이 투영할 수 있으므로 table 을 먼저
    # 물으면 직접 병렬 items 만 table 경로를 타고, 변수 raw list 는 items 경로를 탔다.
    # 공개 통화 모양을 **강제 투영 전에** 판별해 문장 경계가 의미를 바꾸지 않게 한다.
    ra, _ = _get_items(a)
    rb, _ = _get_items(b)
    if ra is not None or rb is not None:
        if ra is None or rb is None:
            return {"success": False, "error": "join: 두 입력이 같은 통화여야 합니다(둘 다 table 또는 둘 다 items)."}
        # 두 입력이 items 통화면 items inner join (table 분기와 대칭).
        # items 행도 dict 라 키 필드로 조인 가능 — merge/union 이 items 를 받는 것과 일관.
        # ★키 실존은 표 경로처럼 **먼저** 본다(2026-09-07): 없는 키는 전 행에서 키 없음이 되어
        #   0행이 success 로 나갔다 — 복합키에서는 오타 하나가 조용히 빈 표가 된다(⑧′ 부류).
        for _side, _rows in (("좌", ra), ("우", rb)):
            _dicts = [r for r in _rows if isinstance(r, dict)]
            if not _dicts:
                continue
            _missing = [k for k in keys if not any(k in r for r in _dicts)]
            if _missing:
                return {"success": False,
                        "error": f"join: 키 '{"', '".join(_missing)}' 이(가) {_side}측 items 의 "
                                 f"어느 행에도 없습니다. 실제 필드: {list(_dicts[0].keys())}"}
        index = {}
        for r in rb:
            if not isinstance(r, dict):
                continue
            key = _join_keys(r, keys)
            if key is not None:
                index.setdefault(key, []).append(r)
        out = []
        for l in ra:
            if not isinstance(l, dict):
                continue
            key = _join_keys(l, keys)
            if key is None:
                continue
            lkeys = list(l.keys())
            for r in index.get(key, []):
                add = [k for k in r.keys() if k not in keys]
                disp = _suffix_collisions(lkeys, add)  # 동명 필드 _2 (침묵 오선택 방지)
                merged = dict(l)
                for orig, name in zip(add, disp):
                    merged[name] = r[orig]
                out.append(merged)
        return _attach_branch_warning(_emit_items(_carry_flags([a, b], with_total=False), out), [a, b])
    ta, _ = _get_table(a)
    tb, _ = _get_table(b)
    if ta is None or tb is None:
        return {"success": False, "error": "join: 두 입력이 같은 통화여야 합니다(둘 다 table 또는 둘 다 items)."}
    ca = [str(c) for c in (ta.get("columns") or [])]
    cb = [str(c) for c in (tb.get("columns") or [])]
    missing = [k for k in keys if k not in ca or k not in cb]
    if missing:
        return {"success": False,
                "error": f"join: 키 '{"', '".join(missing)}'이(가) 양쪽 table 열에 "
                         f"모두 있어야 합니다(좌:{ca} 우:{cb})."}
    lki = [ca.index(k) for k in keys]
    rki = [cb.index(k) for k in keys]
    # 우측을 키로 인덱싱
    index = {}
    for r in tb.get("rows") or []:
        key = _join_row_key([(r[i] if i < len(r) else None) for i in rki])
        if key is not None:
            index.setdefault(key, []).append(r)
    extra = [c for c in cb if c not in keys]  # 우측에서 가져올 열(키 제외, 읽기는 원본 이름)
    out_cols = ca + _suffix_collisions(ca, extra)  # 표시 이름만 충돌 회피
    out_rows = []
    for r in ta.get("rows") or []:
        key = _join_row_key([(r[i] if i < len(r) else None) for i in lki])
        if key is None:
            continue
        for rb_row in index.get(key, []):
            rbd = {cb[i]: (rb_row[i] if i < len(rb_row) else None) for i in range(len(cb))}
            out_rows.append(list(r) + [rbd.get(c) for c in extra])
    return _attach_branch_warning(
        _emit_table({**_carry_flags([a, b], with_total=False), "table": {}},
                    {"columns": out_cols, "rows": out_rows}), [a, b])


# ── 문서 IR(공유 문서 모델) → 산출물 emitter ───────────────────────────
# 문서 IR: {title?, blocks:[{type, ...}]}. 블록 타입:
#   heading{level,text} · paragraph{text} · list{ordered?,items[]} · image{src,caption?}

# 문서 emitter(structure/document)는 doc_build.py·doc_formats.py 로 분리(2026-08-06,
# 1500줄 규칙). 이 파일은 통화 대수(관계대수)만 — 두 도메인은 서로를 참조하지 않는다.
from common.pkg_utils import load_sibling

_docs = load_sibling(__file__, "doc_build")
structure_document = _docs.structure_document
render_document = _docs.render_document


# ───────────── compute — 파생 열(관계대수 π 확장, 2026-08-21) ─────────────
# 왜: 전세가율·기여도·증감률 같은 열끼리의 산술이 없어 모델이 *이미 받은 숫자를* 파이썬
# 소스에 손으로 다시 타이핑했다(ep1325 `sam0, sam1 = 70300, 271000`) — 통화가 모델
# 컨텍스트를 거쳐 나오는 자리. groupby 는 집계(행→1)만, 이건 행→행 파생.
# ★2026-08-22 M5 정리: 식 화이트리스트·함수 집합의 정본은 common/safe_expr (reduce 와 공유) —
# 두 벌로 두면 허용 구문이 갈라진다. 여기선 그 정본을 compute 의 이름으로 재수출만 한다.
from common.safe_expr import compile_expr as _safe_compile, eval_expr as _safe_eval


def _compute_compile(expr):
    """(code, 식별자 이름들, col("…") 열 이름들) — common.safe_expr.compile_expr 위임."""
    return _safe_compile(expr)


def _op_compute(prev, params):
    """items 각 행에 파생 열 추가. set={새열: "식"} — 식은 열 이름(식별자) 또는 col("열")·숫자·
    + - * / // % ** · round/abs/min/max/int/float/len · 비교·조건식(a if c else b).
    숫자 문자열("3,500")은 수치로 읽는다. 없는 열=정직 에러(실제 열 동봉), 0 나눗셈·형 오류=그 행 None + 신고."""
    spec = params.get("set") or params.get("columns") or params.get("expr")
    if isinstance(spec, str) and params.get("as"):
        spec = {str(params["as"]): spec}
    if not isinstance(spec, dict) or not spec:
        return {"success": False, "error": 'compute: set={새열: "식"} 이 필요합니다. 예: [table:compute]{set: {전세가율: "보증금 / 매매가 * 100"}}'}
    compiled = {}
    need_names, need_cols = set(), set()
    for new_col, expr in spec.items():
        try:
            code, names, cols = _compute_compile(expr)
        except (SyntaxError, ValueError) as e:
            return {"success": False, "error": f"compute: '{new_col}' 식 오류 — {e}"}
        compiled[str(new_col)] = code
        need_names.update(names); need_cols.update(cols)
    recs, env = _get_items_for_fields(prev, sorted(need_names | need_cols)) if (need_names or need_cols) else (None, None)
    if recs is None:
        items, env = _get_items(prev)
        recs = items
    if recs is None:
        table, tenv = _get_table(prev)
        if table is not None:
            recs, env = _row_dicts(table), tenv
    if recs is None:
        return _no_currency_error("compute", prev)
    dict_recs = [r for r in recs if isinstance(r, dict)]
    if not dict_recs:
        return _emit_items(env, [])
    missing = [k for k in sorted(need_names | need_cols) if not any(k in r for r in dict_recs)]
    if missing:
        return _field_missing_error("compute", missing, dict_recs)
    out, errors = [], 0
    sample_err = None
    for r in dict_recs:
        row = dict(r)
        # scope 구성·유한 결과 관문의 정본은 common.safe_expr.eval_expr (reduce 와 공유).
        for new_col, code in compiled.items():
            try:
                row[new_col] = _safe_eval(code, r)
            except Exception as e:
                row[new_col] = None
                errors += 1
                sample_err = sample_err or f"{new_col}: {type(e).__name__} {e}"
        out.append(row)
    res = _emit_items(env, out)
    if errors:
        res["compute_errors"] = errors
        res["note"] = f"compute: {errors}칸 계산 실패 → None (예: {sample_err}). 0 나눗셈·빈 값·문자 열을 확인하세요."
    return res


_DISPATCH = {
    "data_compute": _op_compute,
    "data_filter": _op_filter,
    "data_sort": _op_sort,
    "data_take": _op_take,
    "data_chunk": _op_chunk,
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
        # context 도 넘긴다 — 산출 경로 해소기(J29-1)가 거기 산다.
        return render_document(tool_input, context.output_dir(), context)
    fn = _DISPATCH.get(tool_name)
    if not fn:
        return {"success": False, "error": f"data-ops: 알 수 없는 변환자 '{tool_name}'."}
    params = dict(tool_input or {})
    if tool_name == "data_chunk":
        # 평문 통화(자막·크롤 본문)를 받는 유일한 변환자 — _parse_prev 는 JSON 아닌 문자열을 버리므로 원문을 직접 준다.
        raw = params.get("_prev_result")
        prev = _parse_prev(raw)
        if prev is None and isinstance(raw, str) and raw.strip():
            prev = raw
        if prev is None and params.get("items") is not None:
            _it = params["items"]          # 파이프 머리에서 본문을 직접 줄 때 — items: [{text: "…"}]
            prev = {"items": _it} if isinstance(_it, list) else _it
        if prev is None and params.get("text") is None:
            return {"success": False, "error": "chunk: 입력이 없습니다 — >> 앞 통화(문자열/봉투) 또는 text 파라미터."}
        return fn(prev, params)
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
                _it = params["items"]
                # ★B53-2 (2026-09-02): 되읽기는 몸의 정본 하나 — coerce_items_payload(list · {items} ·
                #   columns/rows·table 봉투 · 그 JSON 문자열). 종전엔 여기서 list/{items} 만 손으로
                #   풀어 `$변수`(변환자 결과=columns/rows) 주입이 죽었다(brief 는 통과 — 게이트가 갈렸다).
                #   못 읽으면 **원형을 그대로** 넘겨 _no_currency_error 가 실제 모양을 말하게 한다.
                try:
                    from common.currency import coerce_items_payload as _coerce_items_payload
                    _rows = _coerce_items_payload(_it)
                except ImportError:
                    _rows = _it if isinstance(_it, list) else None
                if _rows is not None:
                    prev = {"items": _rows}
                else:
                    if isinstance(_it, str):
                        try:
                            _it = json.loads(_it)
                        except Exception:
                            pass
                    prev = _it if isinstance(_it, dict) else {"items": _it}
            elif params.get("table") is not None:
                prev = {"table": params["table"]}
    if prev is None:
        return {"success": False, "error": (
            f"{tool_name}: 입력 통화가 없습니다. 변환자는 >> 파이프로 앞 액션의 "
            "items 통화(표형은 table)를 받습니다. 예: [sense:search]{...} >> [table:filter]{where:...}"
        )}
    return fn(prev, params)
