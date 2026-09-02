"""53회차 상상훈련 수리 회귀 — 축: **축적 왕복**(sink→source: 쌓은 것이 되읽혀 통화로 다시 사는가).

격자 = 축적 싱크 8종(write JSON/MD · spreadsheet · sheet append · ledger · notebook · memory ·
finance · 원장 누적 관용구) × 되읽기 × 소비 5종(파이프 머리 · items 주입 · 조건 · 안티조인 ·
되먹임 삭제). 47회차가 축적 문형 8건을 전부 "검수만" 하고 지나갔던 밭이다.

재현하는 결함(전부 2026-09-02 실측, 보고서 `outputs/imagination_training/2026-09-02_53회차.md`):

  B53-1 **dry-run 이 `$변수[.경로] >>` 파이프 머리에 거짓 빨강.** 파서는 08-27(파이프 머리)·
     09-01(`$a & $b` 병렬 분기)에 `_var_emit` step 을 열었는데 검수기는 그것을 빈 액션으로
     읽어 "노드가 지정되지 않았습니다" — 실행은 정상. B49-1(do 재파싱)과 같은 속의 두 번째 →
     밭 이관: 관문 `scripts/check_validate_parity.py`(fixture·교재 전수, 거짓 빨강 0).
  B53-2 **고전 변환자의 `items:"$변수"` 주입이 columns/rows 봉투를 못 읽고 오류문이 자기모순**
     ("받은 봉투의 키: ['items']"). brief·each·파이프 이음매는 몸의 단일 게이트(derive_items)로
     파생하는데 data-ops 만 손으로 읽었다(B19-2·B51-1 속의 세 번째) → 관문
     `scripts/check_items_injection.py`(items 파라미터를 읽는 함수는 coerce_items_payload 경유).
  B53-3 **`content:"$변수"` 가 통화 없는 원형 + 선별 전 생산자 필드(data)를 파일에 쓴다.**
     변환자가 행과 같은 열을 가진 형제 dict 를 자백(_untransformed)하지 않았고, 문자열 직렬화
     (_v4_var_payload)가 자백을 읽지도, columns/rows 를 파생하지도 않았다.
  B53-4 **파이프 싱크가 정직 표지(warning·_untransformed·errors)를 원장 파일에 저장** — 되읽기가
     옛 경고를 현재 사건처럼 재방출. 제외 목록이 손 목록(branches_skipped 하나)이었다.
  B53-5 **memory save 가 유효집합 밖 category 를 말없이 '기타'로** → 같은 category 검색 0건.
  B53-6 **finance 되읽기 items 가 카드(title/meta/summary/url)라 금액·id 가 통화에 없다** —
     합계·조건·되먹임 삭제 전부 불가(단일 통화 위반). 축적 어휘 중 finance 만 남은 카드 통화.
  V53-1 ⓑ(사용자 판정) **`[self:write]{format:"json"}` 통화 보존 스위치** — 파이프 싱크의
     텍스트/JSON 갈림(11회차 규칙)은 유지, 스위치가 있을 때만 {items, count} JSON 원장.
  F53-3 같은 xlsx 셀을 read 는 숫자·sheet find 는 문자열로 → 독자 타입 정규화 한 벌(normalize_cell).
  F53-4 문자열 where 에 열 벡터가 박힌 실패의 오류문이 구조형 where 를 가리키지 않았다.
  B51-4 승격 경고가 `passthrough_rows`(경로 표지)를 "부분 실패·절단"이라 불렀다(늑대소년).
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)
import boot_paths  # noqa: E402,F401

_PKG = os.path.join(_ROOT, "data", "packages", "installed", "tools")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_dataops = _load("_t53_dataops", os.path.join(_PKG, "data-ops", "handler.py"))
_diag = _load("_t53_diag", os.path.join(_PKG, "data-ops", "diagnostics.py"))
_sysess = _load("_t53_sysess", os.path.join(_PKG, "system_essentials", "handler.py"))
_sheet = _load("_t53_sheet", os.path.join(_PKG, "system_essentials", "sheet_ops.py"))
_office = _load("_t53_office", os.path.join(_PKG, "system_essentials", "office_ops.py"))
_fin = _load("_t53_fin", os.path.join(_PKG, "finance-record", "handler.py"))
_mem = _load("_t53_mem", os.path.join(_PKG, "memory", "handler.py"))


class _Ctx:
    def __init__(self, tool_name, project_path="/tmp"):
        self.tool_name = tool_name
        self.project_path = project_path
        self.agent_id = "test53"

    def output_dir(self):
        return self.project_path

    def resolve_output_path(self, raw, guard=None):
        p = raw if os.path.isabs(raw) else os.path.join(self.project_path, raw)
        return {"path": p, "redirected": False}


def _dj(s):
    return json.loads(s) if isinstance(s, str) else s


# ─────────────────────────── B53-1 · 검수↔실행 정합 ───────────────────────────

def test_B53_1_var_pipe_head_validates_green():
    from api_ibl import validate_code
    for code in ('$q = [self:read]{path: "x.json"}\n$q.items >> [table:take]{n: 1}',
                 '$q = [self:time]\n$q >> [table:take]{n: 1}',
                 '$a = [self:time]\n$b = [self:time]\n$a & $b >> [table:union]'):
        v = validate_code(code)
        assert v["valid"] is True, (code, v)
        kinds = [s["kind"] for s in v["steps"]]
        assert "var" in kinds, kinds
        assert all(s.get("node") != "" for s in v["steps"]), v["steps"]
    # 미할당 변수는 파서의 정직 에러(검수가 아니라 문법)
    v = validate_code('$없음.items >> [table:take]{n: 1}')
    assert v["valid"] is False and v.get("syntax_error")


def test_B53_1_validate_code_is_the_router_body():
    """라우터와 관문이 같은 함수를 쓴다 — 본체가 갈라지면 관문이 표면을 대변하지 못한다."""
    import api_ibl
    src = open(api_ibl.__file__, encoding="utf-8").read()
    assert "return validate_code(code)" in src
    assert "def validate_code(code: str) -> dict" in src


def test_B53_1_parity_gate_selftest():
    r = subprocess.run([sys.executable, os.path.join(_ROOT, "scripts", "check_validate_parity.py"), "--self-test"],
                       capture_output=True, text=True, cwd=_ROOT, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr


# ─────────────────────────── B53-2 · items 주입 단일 게이트 ───────────────────────────

_ROWS_ENV = {"success": True, "columns": ["symbol", "current_price"], "rows": [["x", 1], ["y", 2]]}


def test_B53_2_fix_lives_at_injection_not_in_get_items():
    """수리 자리의 경계 — `_get_items` 는 38회차 계약(명시 표형은 표형 유지·혼합 입력 정직 거절)을
    지켜 표형 봉투에서 items 를 파생하지 **않는다**. 되읽기의 단일 게이트는 `items:` 주입 경로
    (execute 의 coerce_items_payload)에 선다. 2026-09-02 실측: _get_items 에서 파생하자 배터리 7건이
    깨졌다(round38·round46·union_dead_branch·value_semantics)."""
    rows, env = _dataops._get_items(dict(_ROWS_ENV))
    assert rows is None and env is None
    src = open(_dataops.__file__, encoding="utf-8").read()
    assert "coerce_items_payload as _coerce_items_payload" in src


def test_B53_2_items_param_columns_rows_json_string():
    for verb, extra in (("data_take", {"n": 1}), ("data_select", {"columns": ["symbol"]}),
                        ("data_filter", {"where": "current_price > 1"})):
        out = _dj(_dataops.execute({"items": json.dumps(_ROWS_ENV), **extra}, _Ctx(verb)))
        assert out.get("success") is True, (verb, out)
        # select 는 items 입력에도 표형 경로(_get_table)를 먼저 타는 기존 계약 — 표형도 같은 통화
        # (파이프 이음매·되읽기 게이트가 items 로 파생한다). 어느 얼굴이든 행이 있어야 한다.
        from common.currency import derive_items
        rows = derive_items(dict(out)).get("items")
        assert isinstance(rows, list) and rows, (verb, out)


def test_B53_2_no_currency_error_is_not_self_contradictory():
    e = _dataops._no_currency_error("take", {"items": {"x": 1}})
    assert "items 자리에" in e["error"], e
    assert "받은 봉투의 키: ['items']" not in e["error"], e
    # 통화가 아닌 dict 를 items 로 주면 그 dict 의 실제 키가 보인다(자기 포장지 금지)
    out = _dj(_dataops.execute({"items": json.dumps({"success": True, "business": {"id": 1}}), "n": 1},
                               _Ctx("data_take")))
    assert out.get("success") is False and "business" in out["error"], out


def test_B53_2_items_injection_gate_selftest_and_clean():
    gate = os.path.join(_ROOT, "scripts", "check_items_injection.py")
    for args in (["--self-test"], []):
        r = subprocess.run([sys.executable, gate] + args, capture_output=True, text=True, cwd=_ROOT, timeout=120)
        assert r.returncode == 0, r.stdout + r.stderr


# ─────────────────────────── B53-3 · 변수 직렬화 = 통화 ───────────────────────────

def test_B53_3_var_payload_derives_items_and_skips_untransformed():
    from workflow_binding import _v4_var_payload
    env = {"success": True, "data": {"symbol": "x", "current_price": 1, "open": 2, "high": 3},
           "summary": "다이제스트", "columns": ["symbol", "current_price"], "rows": [["x", 1]],
           "_untransformed": ["data"]}
    out = json.loads(_v4_var_payload(json.dumps(env, ensure_ascii=False)))
    assert out == [{"symbol": "x", "current_price": 1}], out          # 선별된 열만 — data 누출 없음
    # columns/rows 만 있는 변환자 결과(자백 없음)도 통화로
    out2 = json.loads(_v4_var_payload(json.dumps({"success": True, "columns": ["a"], "rows": [[1]]})))
    assert out2 == [{"a": 1}]
    # 통화가 아닌 효과 봉투는 원형 유지(안전 방향)
    raw = json.dumps({"success": True, "business": {"id": 12}})
    assert json.loads(_v4_var_payload(raw)) == {"success": True, "business": {"id": 12}}


def test_B53_3_transformer_confesses_row_shaped_sibling_dict():
    row = {"symbol": "x", "current_price": 1, "open": 2, "high": 3}
    out = {"success": True, "data": dict(row), "summary": "s", "memory": {"used_gb": 1, "total_gb": 2},
           "items": [{"symbol": "x"}]}
    res = _dataops._reproject_mirrors(out, [[dict(row)]], [{"symbol": "x"}])
    assert "data" in (res.get("_untransformed") or []), res
    assert "memory" not in (res.get("_untransformed") or []), res       # 열이 다른 메타 dict 는 오폭 없음


# ─────────────────────────── B53-4 · V53-1 ⓑ · 쓰기 싱크 ───────────────────────────

def _write(td, name, prev=None, **extra):
    inp = {"path": os.path.join(td, name), **extra}
    if prev is not None:
        inp["_prev_result"] = json.dumps(prev, ensure_ascii=False)
    return _dj(_sysess.execute(inp, _Ctx("write_file", td)))


def test_B53_4_write_sink_strips_honesty_markers_and_reports():
    with tempfile.TemporaryDirectory() as td:
        prev = {"success": True, "items": [{"u": 1}], "count": 1,
                "warning": "분기 2개 중 1개가 실패해 건너뛰었습니다", "_untransformed": ["x"],
                "errors": [{"e": 1}], "branches_failed": [{"step": 2}]}
        r = _write(td, "ledger.json", prev)
        assert r["success"] is True, r
        saved = json.load(open(os.path.join(td, "ledger.json"), encoding="utf-8"))
        for k in ("warning", "_untransformed", "errors", "branches_failed"):
            assert k not in saved, (k, saved)
        assert saved["items"] == [{"u": 1}]
        assert set(r["excluded_meta"]) >= {"warning", "_untransformed", "errors", "branches_failed"}, r


def test_V53_1_format_json_preserves_currency_regardless_of_message():
    feed_like = {"success": True, "message": "### 긱뉴스 최신 글\n- a\n- b", "count": 2,
                 "items": [{"title": "a", "url": "u1"}, {"title": "b", "url": "u2"}]}
    with tempfile.TemporaryDirectory() as td:
        # 11회차 규칙(현행): message 가 있으면 산문 + note
        r0 = _write(td, "seen.txt", feed_like)
        assert r0.get("extracted") == "message" and "format" in (r0.get("note") or ""), r0
        assert open(os.path.join(td, "seen.txt"), encoding="utf-8").read().startswith("###")
        # ⓑ 스위치: 언제나 통화 JSON
        r1 = _write(td, "seen.json", feed_like, format="json")
        assert r1["success"] is True and r1.get("format") == "json", r1
        saved = json.load(open(os.path.join(td, "seen.json"), encoding="utf-8"))
        assert saved == {"items": feed_like["items"], "count": 2}, saved
        # 명시 content(JSON 목록 문자열 = $변수 직렬화 결과)
        r2 = _dj(_sysess.execute({"path": os.path.join(td, "v.json"), "content": json.dumps([{"a": 1}]),
                                  "format": "json"}, _Ctx("write_file", td)))
        assert r2["success"] is True
        assert json.load(open(os.path.join(td, "v.json"), encoding="utf-8")) == {"items": [{"a": 1}], "count": 1}
        # JSON 이 아닌 content 에 format:json → 정직 거절
        r3 = _dj(_sysess.execute({"path": os.path.join(td, "x.json"), "content": "평문", "format": "json"},
                                 _Ctx("write_file", td)))
        assert r3["success"] is False and "JSON" in r3["error"], r3


def test_V53_1_ledger_accumulate_roundtrip_is_idempotent():
    """원장 누적 관용구의 저장 쪽: 되읽은 원장(items) + 새 행 → union 결과를 format:json 으로 되쓴다."""
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "quotes.json")
        _write(td, "quotes.json", {"success": True, "items": [{"symbol": "a"}], "count": 1}, format="json")
        first = json.load(open(p, encoding="utf-8"))
        union = _dj(_dataops.execute({"_prev_result": json.dumps([json.dumps(first), json.dumps({"items": [{"symbol": "b"}, {"symbol": "a"}]})])},
                                     _Ctx("data_union")))
        dedup = _dj(_dataops.execute({"_prev_result": json.dumps(union), "by": "symbol"}, _Ctx("data_dedup")))
        _write(td, "quotes.json", dedup, format="json")
        again = json.load(open(p, encoding="utf-8"))
        assert again["count"] == 2 and {r["symbol"] for r in again["items"]} == {"a", "b"}, again
        assert "warning" not in again and not any(k.startswith("_") for k in again)


def test_V53_1_catalog_and_textbook_teach_format_json():
    y = open(os.path.join(_PKG, "system_essentials", "ibl_actions.yaml"), encoding="utf-8").read()
    assert "format: string" in y and 'format:"json"' in y
    tb = open(os.path.join(_ROOT, "data", "common_prompts", "fragments", "12_ibl_only.md"), encoding="utf-8").read()
    assert 'format: "json"' in tb and "$변수.경로 >> [액션]" in tb
    assert "구조 보존이 필요하면 table:spreadsheet/structure 로 저장하세요" not in open(_sysess.__file__, encoding="utf-8").read()


# ─────────────────────────── B53-5 · memory category ───────────────────────────

def test_B53_5_memory_category_normalization_is_reported_and_search_rejects():
    with tempfile.TemporaryDirectory() as td:
        r = _dj(_mem.execute({"op": "save", "content": "IT53 시험 기억", "category": "상상훈련_스크래치"},
                             _Ctx("memory_op", td)))
        assert r.get("memory_id") and r.get("category_normalized", {}).get("used") == "기타", r
        assert "warning" in r
        s = _dj(_mem.execute({"op": "search", "query": "IT53", "category": "상상훈련_스크래치"}, _Ctx("memory_op", td)))
        assert s.get("success") is False and "유효" in s["error"], s
        ok = _dj(_mem.execute({"op": "save", "content": "정상 분류", "category": "작업기록"}, _Ctx("memory_op", td)))
        assert "category_normalized" not in ok, ok


# ─────────────────────────── B53-6 · finance 통화 ───────────────────────────

def test_B53_6_finance_items_carry_data_fields():
    tx = _fin._tx_items([{"id": 19, "tx_type": "expense", "amount": 1250.0, "category": "교통",
                          "counterparty": "버스", "occurred_at": "2026-09-02", "note": "", "source": ""}])[0]
    assert tx["record_id"] == 19 and tx["record_type"] == "transaction"
    assert tx["amount"] == 1250 and isinstance(tx["amount"], int) and tx["kind"] == "지출"
    assert tx["date"] == "2026-09-02" and tx["title"].startswith("버스")
    h = _fin._hold_items([{"id": 4, "kind": "asset", "asset_type": "securities", "name": "삼성",
                           "value": 2527500.0, "as_of": "2026-09-02"}])[0]
    assert h["record_id"] == 4 and h["record_type"] == "holding" and h["value"] == 2527500
    assert h["name"] == "삼성" and h["asset_type"] == "securities"


# ─────────────────────────── F53-3 · 독자 타입 한 벌 ───────────────────────────

def test_F53_3_sheet_find_and_read_xlsx_share_cell_typing():
    import openpyxl
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "장부.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["아파트명", "거래금액", "전용면적"])
        ws.append(["가경", "92,000", "105.64"])
        wb.save(p)
        f = _sheet.op_find({"path": p})
        assert f["success"] and f["items"][0]["거래금액"] == 92000 and f["items"][0]["전용면적"] == 105.64, f
        r = _dj(_office.read_xlsx({"path": p}, td))
        assert r["table"]["rows"][0][1] == 92000 and r["table"]["rows"][0][2] == 105.64, r
        # sheet append 도 items 주입 게이트를 쓴다(columns/rows JSON 문자열 수용)
        a = _sheet.op_append({"path": p, "items": json.dumps({"columns": ["아파트명", "거래금액", "전용면적"],
                                                             "rows": [["오송", "62,000", "84.9"]]})})
        assert a.get("success") is True, a
        assert _sheet.op_find({"path": p})["matched"] == 2


def test_F53_3_normalize_cell_rules():
    from common.currency import normalize_cell
    assert normalize_cell("92,000") == 92000 and normalize_cell("105.64") == 105.64
    assert normalize_cell("=SUM(A1:A3)") == "=SUM(A1:A3)" and normalize_cell("010-1234") == "010-1234"
    assert normalize_cell(None, none="") == "" and normalize_cell(None) is None
    assert normalize_cell(True) is True and normalize_cell(7) == 7


# ─────────────────────────── F53-4 · B51-4 ───────────────────────────

def test_F53_4_filter_error_points_to_structured_where():
    e = _diag._field_missing_error("filter", 'url not_in ["https://x"', [{"url": "u"}])
    assert "구조형" in e["error"] and "not_in" in e["error"], e
    plain = _diag._field_missing_error("filter", "없는필드", [{"url": "u"}])
    assert "구조형" not in plain["error"]


def test_B51_4_promotion_wording_separates_route_markers():
    from ibl_honesty import describe_promoted, HONESTY_ROUTE_KEYS, HONESTY_KEYS
    assert set(HONESTY_ROUTE_KEYS) <= set(HONESTY_KEYS)
    s = describe_promoted(["passthrough_rows"])
    assert "경로·출처" in s and "부분 실패" not in s, s
    s2 = describe_promoted(["error_count", "passthrough_rows"])
    assert "부분 실패·절단(error_count)" in s2 and "passthrough_rows" in s2, s2
    src = open(os.path.join(_HERE, "ibl", "workflow_engine.py"), encoding="utf-8").read()
    assert "describe_promoted" in src and "부분 실패·절단을 신고했습니다" not in src


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
