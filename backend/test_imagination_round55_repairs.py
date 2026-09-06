"""55회차 상상훈련 수리 회귀 — 축: **설계 왕복**(engines:arch_* 10종, 미조합 100%)의 뿌리는 arch 가 아니라
통화 경계였다. 사용자 판정(2026-09-06) "국소만 빼고 다 고쳐" — F55-2/F55-3(arch 국소)은 제외.

  G55-1 `[table:each]{collect: true}` — do 가 통화를 안 내는 행(효과·스칼라)의 결과를 `{원 행…, 결과 키…}`
        행으로 승격. 승격 규칙은 union 의 효과 행과 **같은 함수**(`common.currency.effect_row`).
  G55-2 `[table:document]{as: "images", src_field, caption_field}` — items N행 → image 블록 N개.
  B55-1 부작용 정직성 관문 — 구현이 쓰기 원시에 닿는 scalar/items 액션은 `side_effect` 선언 필수
        (arch_create·arch_modify 가 dry-run 'read' 로 표시되던 자리). 이름 목록이 아니라 코드 앵커.
  F55-1 스칼라·효과 봉투의 ⟨키⟩ 관측 — shape 스윕이 통화 아닌 봉투의 키를 적고, 카탈로그는 ⟨키⟩ 로
        라벨을 가르며, 정적 검사기는 ⟨키⟩를 열로 쓰지 않는다. fixture 없는 액션은 실사용 원장에서 수확.

실행: .venv/bin/python -m pytest -q backend/test_imagination_round55_repairs.py
"""
import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import boot_paths  # noqa: E402,F401

_ROOT = Path(_HERE).parent
_PKGS = _ROOT / "data" / "packages" / "installed" / "tools"
sys.path.insert(0, str(_ROOT / "scripts"))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ───────────────────────── G55-1 each collect ─────────────────────────

import ibl_engine  # noqa: E402
from ibl.ibl_exec_each import _execute_table_each  # noqa: E402

PARENTS = [{"id": "d1", "name": "집A", "floors": 2}, {"id": "d2", "name": "집B", "floors": 1}]
SCALAR_REPORT = {"success": True, "coverage_ratio": 23.33, "building_area": 70, "floors": [{"f": 1}], "_internal": 1}
EFFECT_DRAWING = {"success": True, "path": "/x/front.png", "format": "png"}
CURRENCY = {"success": True, "items": [{"date": "d1"}, {"date": "d2"}]}


def _run(do, params=None, result=None):
    orig = ibl_engine.execute_ibl

    def _fake(ti, pp, agent_id=None, **kw):
        return dict(result) if isinstance(result, dict) else result
    ibl_engine.execute_ibl = _fake
    try:
        return _execute_table_each({"items": PARENTS, "do": do, **(params or {})}, ".")
    finally:
        ibl_engine.execute_ibl = orig


def test_G55_1_collect_promotes_scalar_result_to_row():
    out = _run("[engines:arch_report]{design_id: $it.id}", {"collect": True}, SCALAR_REPORT)
    assert out["success"] is not False, out
    rows = out["items"]
    assert len(rows) == 2 and out["collected_rows"] == 2
    assert rows[0]["name"] == "집A" and rows[0]["coverage_ratio"] == 23.33   # 원 행 + 결과 키
    assert "success" not in rows[0] and "_internal" not in rows[0]          # 잉여·내부 표지는 행이 아니다
    assert "passthrough_rows" not in out                                     # 승격했으니 통과 신고가 아니다
    # 원 행 이름이 먼저 — 겹친 결과 키(floors)는 _2 로 밀리고 봉투가 말한다
    assert rows[0]["floors"] == 2 and rows[0]["floors_2"] == [{"f": 1}]
    assert out["collect_renamed"] == {"floors": "floors_2"}
    assert "collect" in out["message"] and "floors_2" in out["message"]


def test_G55_1_collect_effect_envelope_same_as_union_row():
    """대조 실측의 핵심 — 같은 효과 봉투를 union 과 each 가 같은 규칙으로 행으로 만든다."""
    from common.currency import effect_row
    ops = _load("_t55_dataops", _PKGS / "data-ops" / "handler.py")
    union_row = ops._effect_row(EFFECT_DRAWING)
    assert union_row == effect_row(EFFECT_DRAWING)
    out = _run("[engines:arch_elevation]{design_id: $it.id}", {"collect": "true"}, EFFECT_DRAWING)
    assert [r["path"] for r in out["items"]] == ["/x/front.png", "/x/front.png"]
    assert out["items"][0]["id"] == "d1" and "success" not in out["items"][0]


def test_G55_1_default_unchanged_and_currency_ignores_collect():
    out = _run("[engines:arch_report]{design_id: $it.id}", None, SCALAR_REPORT)
    assert out["passthrough_rows"] == 2 and "coverage_ratio" not in out["items"][0]
    out2 = _run("[sense:weather]{city: $it.name}", {"collect": True}, CURRENCY)
    assert [r["date"] for r in out2["items"]] == ["d1", "d2", "d1", "d2"]
    assert out2["rows_replaced"] == 2 and "collected_rows" not in out2


def test_G55_1_collect_bare_scalar_goes_to_value():
    out = _run("[self:ask]{q: $it.name}", {"collect": True}, "답변 산문")
    assert out["items"][0]["value"] == "답변 산문" and out["items"][0]["id"] == "d1"


# ───────────────────────── G55-2 document as: images ─────────────────────────

_doc = _load("_t55_doc_build", _PKGS / "data-ops" / "doc_build.py")
DRAWINGS = [{"path": "/x/front.png", "format": "png", "title": "정면"},
            {"path": "/x/rear.png", "format": "png", "title": "후면"},
            {"format": "png", "title": "빈 행"}]


def test_G55_2_items_become_image_blocks(tmp_path):
    out = json.loads(_doc.render_document(
        {"items": DRAWINGS, "as": "images", "format": "markdown", "filename": "입면도"}, str(tmp_path)))
    assert out["success"] is True, out
    assert out["images"] == 2 and out["src_field"] == "path" and out["images_skipped"] == 1
    assert "![정면](/x/front.png)" in out["markdown"] and "![후면](/x/rear.png)" in out["markdown"]
    assert "건너뛰었습니다" in out["message"]


def test_G55_2_explicit_fields_and_pipe_entry(tmp_path):
    rows = [{"file": "/x/a.png", "label": "A"}, {"file": "/x/b.png", "label": "B"}]
    prev = json.dumps({"success": True, "items": rows}, ensure_ascii=False)
    out = json.loads(_doc.render_document(
        {"_prev_result": prev, "as": "images", "src_field": "file", "caption_field": "label",
         "format": "markdown", "filename": "그림"}, str(tmp_path)))
    assert out["images"] == 2 and "![A](/x/a.png)" in out["markdown"]


def test_G55_2_no_src_is_honest_failure_and_unknown_as_rejected(tmp_path):
    out = json.loads(_doc.render_document(
        {"items": [{"title": "x"}], "as": "images", "format": "markdown"}, str(tmp_path)))
    assert out["success"] is False and "src_field" in out["error"]
    out2 = json.loads(_doc.render_document({"items": DRAWINGS, "as": "figures"}, str(tmp_path)))
    assert out2["success"] is False and "images" in out2["error"]
    # as 미지정 = 종전 자동(표) — 개정이 기본을 바꾸지 않는다
    out3 = json.loads(_doc.render_document(
        {"items": DRAWINGS[:2], "format": "markdown", "filename": "표"}, str(tmp_path)))
    assert out3["success"] is True and "![" not in out3["markdown"] and "path" in out3["markdown"]


# ───────────────────────── B55-1 부작용 정직성 관문 ─────────────────────────

from iblbuild_side_effect_scan import write_primitives_of, validate_side_effect_honesty  # noqa: E402


def _pkg(tmp_path, handler_src):
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "handler.py").write_text(handler_src, encoding="utf-8")
    return d


def test_B55_1_scanner_resolves_def_map_and_inline_if_chain(tmp_path):
    d = _pkg(tmp_path, '''
import os, json
def _save(design):
    with open("/tmp/x.json", "w") as f:
        json.dump(design, f)
def create_thing(params):
    return _save(params)
def read_thing(params):
    return {"ok": True, "n": [1, 2].count(1)}
_TOOL_MAP = {"mapped_write": _save, "mapped_read": read_thing}
def execute(tool_input, context):
    tool_name = context.tool_name
    if tool_name == "inline_write":
        os.makedirs("/tmp/y", exist_ok=True)
        return "ok"
    elif tool_name == "inline_read":
        return json.dumps({"items": []})
''')
    r, prims = write_primitives_of(d, "create_thing")
    assert r and any("open(mode='w')" in p for p in prims)
    assert write_primitives_of(d, "read_thing") == (True, [])
    r, prims = write_primitives_of(d, "mapped_write")
    assert r and prims
    r, prims = write_primitives_of(d, "inline_write")
    assert r and any(".makedirs()" in p for p in prims)
    assert write_primitives_of(d, "inline_read") == (True, [])
    assert write_primitives_of(d, "no_such_tool") == (False, [])


def test_B55_1_live_registry_has_no_undeclared_writers():
    """실물 census: 쓰기 원시에 닿는 scalar/items 액션은 전부 선언을 갖는다(arch_create·modify 포함)."""
    import yaml
    data = yaml.safe_load((_ROOT / "data" / "ibl_nodes.yaml").read_text(encoding="utf-8"))
    issues, unresolved = validate_side_effect_honesty(data, _ROOT)
    assert issues == [], issues
    assert unresolved == [], unresolved
    arch = data["nodes"]["engines"]["actions"]
    assert arch["arch_create"]["side_effect"] is True and arch["arch_modify"]["side_effect"] is True
    from ibl_safety import is_side_effect
    assert is_side_effect(arch["arch_create"]) and is_side_effect(arch["arch_modify"])
    assert not is_side_effect(arch["arch_list"])


def test_B55_1_gate_flags_undeclared_writer(tmp_path, monkeypatch):
    d = _pkg(tmp_path, '''
def make_it(params):
    open("/tmp/z", "w").write("x")
    return {"success": True}
''')
    import iblbuild_side_effect_scan as m
    monkeypatch.setattr(m, "build_tool_index", lambda root: {"make_it": (d, {})})
    data = {"nodes": {"engines": {"actions": {
        "mk": {"router": "handler", "tool": "make_it", "returns": "scalar"},
        "mk_declared": {"router": "handler", "tool": "make_it", "returns": "scalar", "side_effect": False},
        "mk_effect": {"router": "handler", "tool": "make_it", "returns": "effect"},
    }}}}
    issues, unresolved = m.validate_side_effect_honesty(data, tmp_path)
    assert len(issues) == 1 and "[engines:mk]" in issues[0] and unresolved == []


# ───────────────────────── F55-1 스칼라·효과 ⟨키⟩ 관측 ─────────────────────────

_sweep = _load("_t55_shape_sweep", _ROOT / "scripts" / "ibl_shape_sweep.py")


def test_F55_1_sweep_records_scalar_keys_with_one_nested_layer():
    env = {"success": True, "design": {"site": {"width": 20}, "floors": []}, "report": "x",
           "rooms": [{"name": "거실", "area": 30}], "_trace": 1}
    kind, keys = _sweep._shape(env)
    assert kind == "scalar"
    assert keys[:3] == ["design", "design.site", "design.floors"] and "rooms[].name" in keys and "_trace" not in keys
    assert _sweep._shape({"success": True, "items": [{"a": 1}]}) == ("items", ["a"])
    assert _sweep._shape({"success": False, "error": "x"}) == (None, [])


def test_F55_1_harvest_from_health_only_fills_unobserved(tmp_path):
    (tmp_path / "data").mkdir()
    conn = sqlite3.connect(str(tmp_path / "data" / "world_pulse.db"))
    conn.execute("CREATE TABLE action_health (node TEXT, action TEXT, success INTEGER, keys TEXT, shape TEXT, timestamp TEXT)")
    conn.executemany("INSERT INTO action_health VALUES (?,?,?,?,?,?)", [
        ("engines", "arch_report", 1, json.dumps(["coverage_ratio", "building_area"]), "message", "2026-09-06T23:00:00"),
        ("engines", "arch_report", 1, json.dumps(["old"]), "message", "2026-09-05T23:00:00"),
        ("sense", "weather", 1, json.dumps(["should_not_win"]), "dict", "2026-09-06T23:00:00"),
        ("engines", "arch_create", 0, json.dumps(["error"]), "error", "2026-09-06T23:00:00"),
    ])
    conn.commit(); conn.close()
    shapes = {"sense:weather": {"kind": "items", "keys": ["date"], "source": "fixture"}}
    n = _sweep.harvest_from_health(shapes, tmp_path)
    assert n == 1
    assert shapes["engines:arch_report"] == {"kind": "scalar", "keys": ["coverage_ratio", "building_area"],
                                             "observed": "2026-09-06", "source": "usage"}
    assert shapes["sense:weather"]["keys"] == ["date"]          # fixture 관측이 이긴다
    assert "engines:arch_create" not in shapes                   # 실패 봉투는 수확 안 함


def test_F55_1_catalog_label_and_typecheck_ignore(monkeypatch):
    import ibl_access, ibl_typecheck
    fake = {"engines:arch_report": {"kind": "scalar", "keys": ["coverage_ratio", "building_area"]},
            "sense:weather": {"kind": "items", "keys": ["date", "max_temp"]}}
    monkeypatch.setattr(ibl_access, "_return_shapes", lambda: fake)
    assert ibl_access._shape_suffix("engines:arch_report") == " ⟨키: coverage_ratio·building_area⟩"
    assert ibl_access._shape_suffix("sense:weather") == " ⟨열: date·max_temp⟩"
    assert ibl_typecheck._catalog_cols("engines", "arch_report", {}) is None
    assert ibl_typecheck._catalog_cols("sense", "weather", {}) == ["date", "max_temp"]


def test_F55_1_action_health_records_keys(tmp_path, monkeypatch):
    import pulse_db
    db = tmp_path / "pulse.db"
    monkeypatch.setattr(pulse_db, "_get_pulse_db", lambda: sqlite3.connect(str(db)))
    monkeypatch.setattr(pulse_db, "_AH_COLS_ENSURED", False)
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE action_health (node TEXT, action TEXT, success INTEGER, response_ms INTEGER, source TEXT, timestamp TEXT)")
    conn.commit(); conn.close()
    pulse_db.record_action_health("engines", "arch_report", True, 12, source="self_check",
                                  shape="message", keys=["coverage_ratio", "building_area"])
    row = sqlite3.connect(str(db)).execute("SELECT keys, shape FROM action_health").fetchone()
    assert json.loads(row[0]) == ["coverage_ratio", "building_area"] and row[1] == "message"


if __name__ == "__main__":
    # 러너는 하나다 — 직접 실행도 pytest 에 위임한다.
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
