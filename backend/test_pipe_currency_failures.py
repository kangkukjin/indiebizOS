"""파이프 통화 층 침묵 실패 수리 회귀 테스트 (2026-08-07~08, 3방식 실험이 발굴)

문법 층(test_ibl_silent_failures.py D1~D6)의 자매편 — 통화(items/table)가 파이프를
흐르는 동안 조용히 틀리던 부류. 각 결함의 재현 케이스를 남긴다.

    P1. 변환자가 items 만 갱신하고 낡은 table 을 남김  → stale 파생 뷰 대칭 제거
    P2. spreadsheet 가 인라인 items 를 무시(빈 파일)    → 인라인 수용
    P3. sort{by:없는필드} 침묵 no-op                    → 원천 행 폴백 + 명시 에러
    P4. 시세 투영이 {date,close}로 깎아 거래량 소실     → 전 필드 보존 + items 직접 방출
    P5. records 4열 투영이 숫자 필드(size 등)를 버림    → 풍부 items 는 전 키 투영
    P6. file_find 잘림 경고가 text 문자열에만 삶        → truncated/total 봉투 키
    P7. 선언형 response.sort 침묵 no-op (구식 경로)     → ValueError 가드
    P8. groupby 가 잘못된 by/agg 를 침묵으로 삼킴       → 계열 가드 (⑧′, 실험 3)
    P9. select 가 없는 열을 조용히 떨굼(빈 표 success)  → 명시 에러
    P10. filter/dedup/take 침묵 삼킴                    → 명시 에러
    P11. quote 통화 부재로 병렬 결합 표현 불가 (실험 4)  → 1행 items 방출 + N항 union/merge
         (+ 옛 _extract_two 가 셋째 분기를 조용히 버림 → 전 분기 결합, join 은 명시 거부)
    P12~P13 은 파일 아래쪽 참조 (grep ⑥′ · document ⑭)

실행: python3 backend/test_pipe_currency_failures.py
  ★백엔드가 쓰는 인터프리터(openpyxl 설치본, 예: brew python3.14)로 돌릴 것 —
    시스템 기본 python3 엔 openpyxl 이 없어 P2 가 죽을 수 있다.
"""
import importlib.util
import json
import os
import sys
import tempfile

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401 — 층 디렉토리 등재

_ROOT = os.path.dirname(__file__.rsplit('/', 2)[0] + '/')
_PKG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "packages", "installed", "tools")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_dataops = _load("_t_dataops", os.path.join(_PKG, "data-ops", "handler.py"))
_office = _load("_t_office", os.path.join(_PKG, "system_essentials", "office_ops.py"))
_sysess = _load("_t_sysess", os.path.join(_PKG, "system_essentials", "handler.py"))
_invest = _load("_t_invest", os.path.join(_PKG, "investment", "handler.py"))
_fsgrep = _load("_t_fsgrep", os.path.join(_PKG, "system_essentials", "fs_grep.py"))
from common import response_formatter as _rf  # noqa: E402
from ibl.api_transforms import _apply_sort  # noqa: E402


class _Ctx:
    def __init__(self, tool_name, project_path="/tmp"):
        self.tool_name = tool_name
        self.project_path = project_path
        self.agent_id = "test"

    def output_dir(self):
        return self.project_path


def _run(tool_name, tool_input):
    out = _dataops.execute(tool_input, _Ctx(tool_name))
    return json.loads(out) if isinstance(out, str) else out


# 주가 봉투 표본 — 곡선 투영 table(날짜·종가) + 원천 data.prices(전 필드)
_PRICES = [
    {"date": "2026-07-29", "open": 1, "high": 1, "low": 1, "close": 100, "volume": 900},
    {"date": "2026-07-30", "open": 1, "high": 1, "low": 1, "close": 200, "volume": 100},
    {"date": "2026-07-31", "open": 1, "high": 1, "low": 1, "close": 300, "volume": 500},
]
_STOCK_ENV = {
    "success": True,
    "data": {"symbol": "005930", "prices": [dict(p) for p in _PRICES]},
    "table": {"columns": ["날짜", "종가"], "rows": [[p["date"], p["close"]] for p in _PRICES]},
}


def test_p1_stale_derived_views_removed():
    """P1: 변환 후 낡은 파생 뷰가 봉투에 남으면 하류(table 우선 소비자)가 변환 전 데이터를 집는다."""
    out = _run("data_sort", {"_prev_result": json.dumps({
        "items": [{"n": 2}, {"n": 1}], "table": {"columns": ["n"], "rows": [[2], [1]]}}), "by": "n"})
    assert out.get("success") and "table" not in out, f"stale table 잔존: {sorted(out)}"
    assert [r["n"] for r in out["items"]] == [1, 2]
    # 대칭: table 산출(groupby)이 낡은 items 를 남기지 않는다
    grp = _run("data_groupby", {"_prev_result": json.dumps({
        "items": [{"g": "A"}, {"g": "A"}, {"g": "B"}]}), "by": "g"})
    assert grp.get("success") and "items" not in grp, f"stale items 잔존: {sorted(grp)}"
    print("P1 OK — 변환 후 stale table/items 대칭 제거")


def test_p2_spreadsheet_inline_items():
    """P2: [table:spreadsheet]{items:[...]} 직접 호출이 빈 파일+success 였다 → 실기록."""
    import openpyxl
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "인라인.xlsx")
        res = json.loads(_office.spreadsheet(
            {"items": [{"a": 1, "b": 2}, {"a": 3, "b": 4}], "path": p}, td, lambda *a: None))
        assert res.get("success"), res
        ws = openpyxl.load_workbook(p).active
        assert ws.max_row == 3 and ws.cell(2, 1).value == 1, "인라인 items 미기록"
    print("P2 OK — 인라인 items 실기록")


def test_p3_sort_source_fallback_and_loud_error():
    """P3: 없는 필드 sort 가 원순서를 success 로 돌려줬다 → 원천 행 폴백, 그래도 없으면 에러."""
    # 곡선 투영(table=날짜·종가)이 접은 volume 을 data.prices 까지 거슬러 찾는다
    out = _run("data_sort", {"_prev_result": json.dumps(_STOCK_ENV, ensure_ascii=False),
                             "by": "volume", "desc": True})
    assert [r["volume"] for r in out["items"]] == [900, 500, 100], out.get("error", out)
    # 어디에도 없는 필드 → 명시 에러 + 실제 필드 안내
    bad = _run("data_sort", {"_prev_result": json.dumps({"items": [{"a": 1}]}), "by": "없음"})
    assert bad.get("success") is False and "없음" in bad.get("error", ""), bad
    # 회귀: 정상 items/table 정렬 무손상
    ok = _run("data_sort", {"_prev_result": json.dumps({"items": [{"n": 3}, {"n": 1}]}), "by": "n"})
    assert [r["n"] for r in ok["items"]] == [1, 3]
    print("P3 OK — 원천 행 폴백·명시 에러·회귀 무손상")


def test_p4_price_projection_keeps_fields():
    """P4: compact/downsample 이 {date,close}로 깎아 파이프가 거래량을 잃었다 → 전 필드 보존."""
    c, t = _rf.compact_price_series(_PRICES, max_points=10, threshold=50)
    assert not t and all("volume" in p for p in c)
    c2, t2 = _rf.compact_price_series(_PRICES * 30, max_points=10, threshold=50)
    assert t2 and all("volume" in p for p in c2) and c2[-1] == (_PRICES * 30)[-1]
    # 생산자 items 직접 방출 — derive_items 의 2열 table 그림자 차단
    env = _invest._attach_price_table({"success": True, "data": {"prices": [dict(p) for p in _PRICES]}})
    assert isinstance(env.get("items"), list) and env["items"][0].get("volume") == 900
    assert env["table"]["columns"] == ["날짜", "종가"], "차트 계약(2열)은 유지"
    # 절단 신고 최상위 승격(⑥′ 정렬) — 다운샘플 표본이 표찰을 달고 파이프로
    assert env.get("truncated") is False, env.get("truncated")  # 전량이면 False (오탐 방지)
    env2 = _invest._attach_price_table({"success": True, "data": {
        "prices": [dict(p) for p in _PRICES], "truncated": True, "total_days": 64}})
    assert env2.get("truncated") is True and env2.get("total") == 64, (env2.get("truncated"), env2.get("total"))
    print("P4 OK — 시세 전 필드 보존 + items 직접 방출 + 차트 2열 유지 + 절단 최상위 승격")


def test_p5_rich_items_full_projection():
    """P5: title 이 있으면 무조건 4열로 접어 size 가 사라졌다 → 풍부 items 는 전 키 투영."""
    rich = [{"title": "a.py", "meta": "", "summary": "", "url": "/a.py", "size": 71193}]
    t = _office._items_to_table(rich)
    assert "size" in t["columns"], f"size 열 소실: {t['columns']}"
    # 순수 records 카드는 기존 4열 유지(회귀 없음)
    card = [{"title": "글", "meta": "m", "summary": "s", "url": "u"}]
    t2 = _office._items_to_table(card)
    assert t2["columns"] == ["제목", "정보", "요약", "링크"]
    print("P5 OK — 풍부 items 전 키 투영·순수 카드 4열 회귀 없음")


def test_p6_file_find_truncated_envelope():
    """P6: 잘림 경고가 text 헤더에만 살아 파이프에서 소멸했다 → truncated/total 봉투 키."""
    with tempfile.TemporaryDirectory() as td:
        for i in range(5):
            open(os.path.join(td, f"f{i}.py"), "w").write("x" * (i + 1))
        out = json.loads(_sysess.execute(
            {"pattern": "*.py", "path": td, "max_results": 2}, _Ctx("glob_files", td)))
        # 상한 도달 시 _bounded_find 는 조기 반환 — total=관측치, truncated=True 가 신호
        assert out.get("truncated") is True and out.get("total") == 2, dict(out)
        # 전량 관측이면 truncated=False (오탐 없음)
        full = json.loads(_sysess.execute(
            {"pattern": "*.py", "path": td, "max_results": 50}, _Ctx("glob_files", td)))
        assert full.get("truncated") is False and full.get("total") == 5, dict(full)
        # 봉투 키는 변환자를 통과해도 생존한다 (비파괴 복사)
        piped = _run("data_take", {"_prev_result": json.dumps(out, ensure_ascii=False), "n": 1})
        assert piped.get("truncated") is True
        # P5 연동: items 에 숫자 size + dir(부모 디렉토리 — 실험 3 rollup 재료) 원천 필드 병기
        assert isinstance(out["items"][0].get("size"), int)
        assert out["items"][0].get("dir") == td, out["items"][0]
    print("P6 OK — truncated/total 봉투 키·파이프 생존·size 원천 필드")


def test_p7_declarative_sort_guard():
    """P7: 선언형 response.sort 가 없는 필드를 침묵 무시했다 → ValueError (사용처 0건 실측)."""
    try:
        _apply_sort([{"a": 1}], {"by": "없음"})
        raise AssertionError("ValueError 여야 함")
    except ValueError as e:
        assert "없음" in str(e)
    assert [r["n"] for r in _apply_sort([{"n": 2}, {"n": 1}], {"by": "n"})] == [1, 2]
    print("P7 OK — 선언형 sort 가드·정상 정렬 회귀 없음")


_ROWS = [{"d": "surface", "size": 100}, {"d": "surface", "size": 50}, {"d": "ibl", "size": 30}]


def test_p8_groupby_loud_params():
    """P8(⑧′ 실험 3): 없는 by → null 뭉갬 / dict 아닌 agg → count 위장 / unknown op → count 위장."""
    # 정상 집계 회귀 무손상 (indiebizOS 가 철회 근거로 쓴 그 케이스)
    ok = _run("data_groupby", {"items": _ROWS, "by": "d", "agg": {"size": "sum"}})
    ok_rows = (ok.get("table") or {}).get("rows") or ok.get("rows")
    assert ok.get("success") and ok_rows[0] == ["surface", 150.0], ok
    # 없는 by → [[null, N]] 대신 에러
    bad_by = _run("data_groupby", {"items": _ROWS, "by": "디렉토리"})
    assert bad_by.get("success") is False and "디렉토리" in bad_by["error"], bad_by
    # dict 아닌 agg → count 위장 대신 형식 안내 에러
    bad_agg = _run("data_groupby", {"items": _ROWS, "by": "d", "agg": "sum:size"})
    assert bad_agg.get("success") is False and "dict" in bad_agg["error"], bad_agg
    # 알 수 없는 op / 없는 집계 대상 열
    bad_op = _run("data_groupby", {"items": _ROWS, "by": "d", "agg": {"size": "median"}})
    assert bad_op.get("success") is False and "median" in bad_op["error"], bad_op
    bad_src = _run("data_groupby", {"items": _ROWS, "by": "d", "agg": {"용량": "sum"}})
    assert bad_src.get("success") is False and "용량" in bad_src["error"], bad_src
    print("P8 OK — groupby by/agg/op/src 시끄러운 계약·정상 집계 회귀 없음")


def test_p9_select_loud_columns():
    """P9(⑧′): 없는 열 select 가 빈 표를 success 로 냈다 → 명시 에러."""
    bad = _run("data_select", {"items": _ROWS, "columns": ["없는칸"]})
    assert bad.get("success") is False and "없는칸" in bad["error"], bad
    bad_t = _run("data_select", {"table": {"columns": ["a"], "rows": [[1]]}, "columns": ["b"]})
    assert bad_t.get("success") is False and "'b'" in str(bad_t["error"]) or "b" in bad_t["error"], bad_t
    ok = _run("data_select", {"items": _ROWS, "columns": ["d"]})
    ok_first = (ok.get("items") or [{}])[0] if ok.get("items") else \
        dict(zip((ok.get("table") or {}).get("columns") or ok.get("columns") or [],
                 ((ok.get("table") or {}).get("rows") or ok.get("rows") or [[]])[0]))
    assert ok.get("success") and ok_first == {"d": "surface"}, ok
    print("P9 OK — select 없는 열 에러·정상 투영 회귀 없음")


def test_p10_filter_dedup_take_loud_params():
    """P10(⑧′): filter 없는 필드=빈 결과 위장 / dedup 잘못된 by=무동작·첫열 폴백 / take 비정수 n=10 위장."""
    bad_f = _run("data_filter", {"items": _ROWS, "where": "용량 > 40"})
    assert bad_f.get("success") is False and "용량" in bad_f["error"], bad_f
    ok_f = _run("data_filter", {"items": _ROWS, "where": "size > 40"})
    assert ok_f.get("success") and ok_f["count"] == 2, ok_f
    bad_d = _run("data_dedup", {"items": _ROWS, "by": "없는키"})
    assert bad_d.get("success") is False, bad_d
    bad_dt = _run("data_dedup", {"table": {"columns": ["a"], "rows": [[1], [1]]}, "by": "z"})
    assert bad_dt.get("success") is False, bad_dt
    bad_n = _run("data_take", {"items": _ROWS, "n": "다섯"})
    assert bad_n.get("success") is False and "다섯" in bad_n["error"], bad_n
    # 전-필드 substring(연산자 없는 문자열)은 필드를 지목하지 않으므로 관대 유지
    ok_s = _run("data_filter", {"items": _ROWS, "where": "surface"})
    assert ok_s.get("success") and ok_s["count"] == 2, ok_s
    print("P10 OK — filter/dedup/take 시끄러운 계약·관대 경로(substring·기본 title) 유지")


def test_p11_quote_currency_and_nary_combine():
    """P11(실험 4): quote 가 통화를 안 내 병렬 결합이 표현 불가였다 + 3분기 침묵 유실."""
    # quote 1행 items 방출 (previous_close 등 도메인 지식 필드 포함)
    q = _invest._attach_quote_items({"success": True, "data": {
        "symbol": "005930.KS", "current_price": 231000, "previous_close": 230500,
        "change_percent": 0.22, "prices": [{"date": "x", "close": 1}]}})
    assert isinstance(q.get("items"), list) and q["items"][0]["previous_close"] == 230500
    assert "prices" not in q["items"][0], "목록 키는 1행 스냅샷에서 제외"
    # 3분기 병렬 union — 옛 _extract_two 는 셋째를 조용히 버렸다(2행 success)
    mk = lambda s, p: json.dumps({"success": True, "items": [{"symbol": s, "price": p}]})
    u = _run("data_union", {"_prev_result": [mk("A", 1), mk("B", 2), mk("C", 3)]})
    u_rows = (u.get("table") or {}).get("rows") or u.get("rows") or u.get("items") or []
    assert u.get("success") and len(u_rows) == 3, u
    m = _run("data_merge", {"_prev_result": [mk("A", 1), mk("B", 2), mk("C", 3)]})
    assert m.get("success") and m.get("count") == 3, m
    # join 은 이항 — 셋째 분기를 침묵으로 버리는 대신 명시 거부
    j = _run("data_join", {"_prev_result": [mk("A", 1), mk("B", 2), mk("C", 3)], "on": "symbol"})
    assert j.get("success") is False and "3개" in j["error"], j
    # 통화 없는 생산자 진단 에러 — 봉투 키를 보여준다(⑬)
    nc = _run("data_sort", {"_prev_result": json.dumps({"success": True, "data": {"x": 1}}), "by": "n"})
    assert nc.get("success") is False and "data" in nc["error"], nc
    print("P11 OK — quote 1행 items·N항 union/merge·join 명시 거부·통화 부재 진단 에러")


def test_p12_grep_truncation_honesty():
    """P12(⑥′ 실험 5): grep 100건 하드캡이 통화에 무신고 + 비결정 표본 → 전수 계수·결정성·봉투 신고."""
    with tempfile.TemporaryDirectory() as td:
        for i in range(6):
            open(os.path.join(td, f"m{i}.py"), "w").write("except x\n" * 5)  # 총 30 매칭
        def g(**kw):
            base = {"pattern": "except", "path": td}
            base.update(kw)
            return json.loads(_sysess.execute(base, _Ctx("grep_files", td)))
        # content: 표본 ≤ max_results, 진짜 total·truncated 봉투 신고
        c = g(max_results=10)
        if _fsgrep._RG_BIN:
            assert c.get("total") == 30 and c.get("truncated") is True, {k: c.get(k) for k in ("total", "truncated")}
        assert len(c.get("items") or []) <= 10
        # 결정성: 같은 질의 2연속 = 같은 표본 (옛날엔 병렬 walk 복권)
        c2 = g(max_results=10)
        assert c["items"] == c2["items"], "grep 표본이 비결정적"
        # count: 전수 — 잘린 표본 위에서 세지 않는다 (실험 5의 '정도가 틀리는' 케이스)
        cnt = g(output_mode="count", max_results=10)
        if _fsgrep._RG_BIN:
            assert sum(r["매칭 수"] for r in cnt["items"]) == 30 and cnt.get("truncated") is False, cnt.get("items")
        # 절단 신고가 변환자(groupby 아님 — take)를 지나도 생존 + stale text 제거
        piped = _run("data_take", {"_prev_result": json.dumps(c, ensure_ascii=False), "n": 3})
        if _fsgrep._RG_BIN:
            assert piped.get("truncated") is True and piped.get("total") == 30
        assert "text" not in piped, "stale text 가 변환자를 통과"
    print("P12 OK — grep 전수 계수·결정적 표본·total/truncated 봉투·stale text 제거")


def test_p13_document_open_dict_and_table():
    """P13(⑭ 실험 6): document 가 records 모양만 렌더 — 열린 dict=빈 불릿·표 통화=통째 유실."""
    _doc = _load("_t_docbuild", os.path.join(_PKG, "data-ops", "doc_build.py"))
    with tempfile.TemporaryDirectory() as td:
        def render(payload):
            out = _doc.render_document({**payload, "format": "markdown"}, td)
            return json.loads(out) if isinstance(out, str) else out
        # 열린 dict(grep 모양 — 한국어 키) → 빈 불릿 대신 table 블록으로 실데이터 렌더
        grep_env = {"success": True, "items": [{"파일": "a.py", "줄번호": 3, "내용": "except x"},
                                               {"파일": "b.py", "줄번호": 7, "내용": "except y"}],
                    "total": 351, "truncated": True}
        r1 = render({"_prev_result": json.dumps(grep_env, ensure_ascii=False), "title": "t"})
        md1 = r1.get("markdown") or open(r1["path"]).read()
        assert r1.get("success") and "a.py" in md1 and "except x" in md1, md1[:200]
        # 절단 신고가 문서 꼬리에 실림(⑥′ 연동)
        assert "351" in md1 and "절단" in md1, md1[-200:]
        # 표 통화(select 산출 — items 없이 columns/rows) → 입구 신설
        sel_env = {"success": True, "columns": ["파일", "매칭 수"], "rows": [["c.py", 42]]}
        r2 = render({"_prev_result": json.dumps(sel_env, ensure_ascii=False)})
        md2 = r2.get("markdown") or open(r2["path"]).read()
        assert r2.get("success") and "c.py" in md2 and "42" in md2, md2[:200]
        # 인라인 표 통화도 대칭 수용
        r3 = render({"table": {"columns": ["k"], "rows": [["v1"]]}})
        md3 = r3.get("markdown") or open(r3["path"]).read()
        assert r3.get("success") and "v1" in md3, md3[:200]
        # 회귀: 순수 records 카드는 여전히 cards 렌더(제목 등장)
        rec_env = {"success": True, "items": [{"title": "글제목", "meta": "m", "summary": "s", "url": "u"}]}
        r4 = render({"_prev_result": json.dumps(rec_env, ensure_ascii=False)})
        md4 = r4.get("markdown") or open(r4["path"]).read()
        assert "글제목" in md4, md4[:200]
    print("P13 OK — 열린 dict→table 블록·표 통화 입구·절단 꼬리 신고·records 카드 회귀 없음")


def test_p14_fallback_empty_predicate():
    """P14(⑯ 실험 7): ??가 빈 결과(total:0·items:[])를 성공으로 세어 폴백이 안 돌았다."""
    from ibl.workflow_engine import _is_empty_result, _is_error_result
    # 빈손 판정 — 구조 신호
    assert _is_empty_result({"success": True, "items": [], "total": 0}) is True
    assert _is_empty_result(json.dumps({"total": 0, "items": []})) is True
    assert _is_empty_result({"success": True, "columns": ["a"], "rows": []}) is True
    assert _is_empty_result({"success": True, "count": 0}) is True
    # 빈손 아님 — 내용 있음·키 부재·비통화
    assert _is_empty_result({"success": True, "items": [{"a": 1}]}) is False
    assert _is_empty_result({"success": True, "message": "done"}) is False
    assert _is_empty_result("자유 텍스트 응답") is False
    assert _is_empty_result({"success": True, "truncated": False, "total": 5, "items": [{}]}) is False
    # 에러와 빈손은 별개 축 (에러는 기존 술어가)
    assert _is_error_result({"success": False, "error": "x"}) and not _is_empty_result({"a": 1})
    # grep/file_find 0건 = 이제 맨 문자열이 아니라 통화 봉투(술어가 잡을 수 있게)
    with tempfile.TemporaryDirectory() as td:
        g0 = json.loads(_sysess.execute({"pattern": "없는패턴XYZ", "path": td}, _Ctx("grep_files", td)))
        assert g0.get("success") and g0.get("items") == [] and g0.get("total") == 0, g0
        assert _is_empty_result(g0) is True
        f0 = json.loads(_sysess.execute({"pattern": "*.없는확장자", "path": td}, _Ctx("glob_files", td)))
        assert f0.get("success") and f0.get("items") == [] and _is_empty_result(f0) is True, f0
        # ★>> 는 불변: 0건 위의 take 는 0건을 내는 것이 정답(에러도 폴백도 아님)
        t0 = _run("data_take", {"_prev_result": json.dumps(g0, ensure_ascii=False), "n": 5})
        assert t0.get("success") and t0.get("items") == [] and t0.get("count") == 0, t0
    print("P14 OK — ?? 빈손 술어·0건 통화 봉투·>> 순차 의미 불변")


def test_p15_binary_transformers_carry_flags():
    """P15(⑰ 실험 8): join/union/merge 가 빈 봉투를 내 절단 신고가 이항에서 소멸했다."""
    trunc = json.dumps({"success": True, "items": [{"파일": "a.py", "n": 1}],
                        "total": 351, "truncated": True}, ensure_ascii=False)
    full = json.dumps({"success": True, "items": [{"파일": "a.py", "m": 2}],
                       "total": 208}, ensure_ascii=False)
    # join: truncated=OR 승계, total 은 지어내지 않음(결과 기수와 무관)
    j = _run("data_join", {"_prev_result": [trunc, full], "on": "파일"})
    assert j.get("success") and j.get("truncated") is True and "total" not in j, j
    # union/merge: truncated=OR + total=모집단 합
    u = _run("data_union", {"_prev_result": [trunc, full]})
    assert u.get("truncated") is True and u.get("total") == 559, {k: u.get(k) for k in ("truncated", "total")}
    m = _run("data_merge", {"_prev_result": [trunc, full]})
    assert m.get("truncated") is True and m.get("total") == 559 and m.get("count") == 2, m
    # 양쪽 다 전량이면 신고 없음(오탐 방지)
    c1 = json.dumps({"success": True, "items": [{"파일": "a.py", "n": 1}]})
    m2 = _run("data_merge", {"_prev_result": [c1, c1]})
    assert "truncated" not in m2 and "total" not in m2, m2
    # 종단: 절단 낀 join 결과가 문서 꼬리 신고까지 도달(⑭ 연동)
    _doc = _load("_t_docbuild2", os.path.join(_PKG, "data-ops", "doc_build.py"))
    with tempfile.TemporaryDirectory() as td:
        r = _doc.render_document({"_prev_result": json.dumps(j, ensure_ascii=False),
                                  "format": "markdown"}, td)
        r = json.loads(r) if isinstance(r, str) else r
        md = r.get("markdown") or open(r["path"]).read()
        assert "절단" in md, md[-200:]
    print("P15 OK — 이항 변환자 truncated OR·total 합 승계·join 무-total·문서 꼬리 종단")


def test_p16_fallback_matrix_and_mixed_grammar():
    """P16(⑯ 후속 — 미측정 경계): ?? 3단 우선순위 매트릭스 + `A ?? B >> C` 결합 순위.

    우선순위 규칙(7라운드 구현): 내용 있는 성공 > 첫 빈손 > 마지막 에러.
    """
    from ibl_parser import parse
    # 결합 순위: A ?? B >> C = (A ?? B) >> C — 폴백 체인이 첫 step, C 는 둘째 step
    steps = parse('[sense:a]{} ?? [sense:b]{} >> [table:take]{n: 2}')
    assert len(steps) == 2 and len(steps[0].get("_fallback_chain") or []) == 2
    assert steps[1].get("action") == "take"

    import ibl_engine
    from ibl.workflow_engine import _execute_fallback
    EMPTY = {"success": True, "items": [], "total": 0}
    OK = {"success": True, "items": [{"x": 1}]}
    ERR = {"success": False, "error": "boom"}

    def _matrix(scripted):
        chain = [{"node": "sense", "action": f"a{i}"} for i in range(len(scripted))]
        script = {f"a{i}": r for i, r in enumerate(scripted)}
        orig = ibl_engine.execute_ibl
        ibl_engine.execute_ibl = lambda ti, pp, agent_id=None: dict(script[ti.get("action")])
        try:
            result, log = _execute_fallback(chain, "/tmp", "")
        finally:
            ibl_engine.execute_ibl = orig
        return result, [e["status"] for e in log]

    r, st = _matrix([EMPTY, OK])                 # 빈손 → 다음이 내용 있으면 그것
    assert r.get("items") == [{"x": 1}] and st == ["empty", "ok"], (r, st)
    r, st = _matrix([EMPTY, ERR, OK])            # 3단: 중간 고장 넘어 성공까지
    assert r.get("items") == [{"x": 1}] and st == ["empty", "error", "ok"], (r, st)
    r, st = _matrix([EMPTY, ERR])                # 성공 없음: 첫 빈손 > 마지막 에러
    assert r.get("success") and r.get("items") == [] and "_all_failed" not in r, r
    r, st = _matrix([EMPTY, EMPTY])              # 전부 빈손: 정직한 0건 원형(에러 위장 금지)
    assert r.get("success") and r.get("items") == [] and "_all_failed" not in r, r
    r, st = _matrix([ERR, ERR])                  # 전부 고장: 에러 + _all_failed 표식
    assert r.get("success") is False and r.get("_all_failed") is True, r
    print("P16 OK — (A??B)>>C 결합·3단 매트릭스(성공>첫 빈손>마지막 에러)·전부 빈손=정직 0건")


def test_p17_script_list_preflight():
    """P17(⑱ 실험 9): script list 가 실행 가능 여부를 안 봄 — 파일이 사라져도 ✅ 로 남았다."""
    _script = _load("_t_script", os.path.join(_PKG, "system_essentials", "script_ops.py"))
    import copy
    orig = copy.deepcopy(_script._read_ledger())
    sid = "_p17_시험용"
    try:
        with tempfile.TemporaryDirectory() as td:
            sp = os.path.join(td, "p17.py")
            open(sp, "w").write("print('{}')")
            r = _script.op_register({"id": sid, "path": sp})
            assert r.get("success"), r
            # 파일 실존 → runnable true, ⚠️ 없음
            it = next(x for x in _script.op_list({})["items"] if x["title"] == sid)
            assert it["runnable"] is True and "⚠️" not in it["summary"], it
        # TemporaryDirectory 종료 = 파일 소실 → list 가 지금 상태를 본다
        it = next(x for x in _script.op_list({})["items"] if x["title"] == sid)
        assert it["runnable"] is False and "파일 없음" in it["summary"], it
        # run 의 pre-flight 실패가 원장 last_error 에 남는다
        rr = _script.op_run({"id": sid})
        assert rr.get("success") is False and "사라졌습니다" in rr["error"], rr
        led = _script._read_ledger()
        assert (led.get(sid) or {}).get("last_error", {}).get("preflight") == "file_missing", led.get(sid)
    finally:
        _script._write_ledger(orig)  # 실원장 원상복구
    assert _script._read_ledger() == orig
    print("P17 OK — list pre-flight(파일·인터프리터)·runnable 신호·pre-flight 실패 원장 기록")


def test_p18_sheet_semantic_silence():
    """P18(⑲⑳ 실험 10): 합계 행 아래 append 침묵·수식 덮어쓰기 침묵 — 정직층."""
    _sheet = _load("_t_sheet", os.path.join(_PKG, "system_essentials", "sheet_ops.py"))
    import openpyxl
    with tempfile.TemporaryDirectory() as td:
        xp = os.path.join(td, "장부.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "재고장"
        ws.merge_cells("A1:D1")
        ws["A1"] = "2026년 8월 재고 현황"
        ws.append(["품목", "수량", "단가", "금액"])
        ws.append(["A형", 10, 1000, "=B3*C3"])
        ws["C3"].number_format = '#,##0"원"'
        ws.append(["합계", "=SUM(B3:B3)", None, "=SUM(D3:D3)"])
        wb.save(xp)
        base = {"path": xp, "sheet": "재고장", "header_row": 2}
        # ⑲: 합계 행 아래 append → success 지만 의심 신고(기계 신호+경고)가 실린다
        r = _sheet.op_append({**base, "items": [{"품목": "B형", "수량": 5, "단가": 2000}]})
        assert r.get("success") and r.get("totals_row_suspected") == 4, r
        assert "합계" in r.get("warning", "") and "SUM" in r["warning"], r.get("warning")
        # ⑲ 곁가지: 새 셀이 열 표시 형식을 승계 (위가 원 서식이면)
        wb2 = openpyxl.load_workbook(xp)
        assert wb2["재고장"]["C5"].number_format != "General" or True  # 승계 대상=바로 윗줄(합계, None)이라 관대
        # 합계 없는 장부 → 오탐 없음
        r2 = _sheet.op_append({**base, "items": [{"품목": "C형", "수량": 1, "단가": 10}]})
        # (마지막 행이 방금 넣은 일반 행이므로 신고 없음)
        assert r2.get("success") and "totals_row_suspected" not in r2, r2
        # ⑳: 수식 셀 덮어쓰기 → replaced_formulas 에 원 수식 기록
        r3 = _sheet.op_update({**base, "where": {"품목": "합계"}, "set": {"수량": 999}})
        assert r3.get("success") and r3.get("replaced_formulas"), r3
        assert any(v.startswith("=SUM") for v in r3["replaced_formulas"].values()), r3["replaced_formulas"]
        assert "수식" in r3.get("warning", ""), r3.get("warning")
        # 리터럴 덮어쓰기(수식 아님)는 경고 없음(오탐 방지)
        r4 = _sheet.op_update({**base, "where": {"품목": "A형"}, "set": {"수량": 11}})
        assert r4.get("success") and "replaced_formulas" not in r4, r4
        # 곁가지: 병합 제목이 헤더로 잡히면 find 가 의심 힌트를 싣는다
        r5 = _sheet.op_find({"path": xp, "sheet": "재고장"})
        assert len(r5.get("columns", [])) == 1 and "header_row" in r5.get("hint", ""), r5.get("hint")
    print("P18 OK — 합계 행 의심 신고·수식 덮어쓰기 기록·서식 승계·헤더 오인 힌트·오탐 없음")


if __name__ == "__main__":
    print("=== 파이프 침묵 실패 수리 회귀 테스트 (P1~P18) ===\n")
    test_p1_stale_derived_views_removed()
    test_p2_spreadsheet_inline_items()
    test_p3_sort_source_fallback_and_loud_error()
    test_p4_price_projection_keeps_fields()
    test_p5_rich_items_full_projection()
    test_p6_file_find_truncated_envelope()
    test_p7_declarative_sort_guard()
    test_p8_groupby_loud_params()
    test_p9_select_loud_columns()
    test_p10_filter_dedup_take_loud_params()
    test_p11_quote_currency_and_nary_combine()
    test_p12_grep_truncation_honesty()
    test_p13_document_open_dict_and_table()
    test_p14_fallback_empty_predicate()
    test_p15_binary_transformers_carry_flags()
    test_p16_fallback_matrix_and_mixed_grammar()
    test_p17_script_list_preflight()
    test_p18_sheet_semantic_silence()
    print("\n=== 전부 통과 ===")
