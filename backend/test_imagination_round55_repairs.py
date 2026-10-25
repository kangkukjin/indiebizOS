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
from test_ibl_v2_core import value

PARENTS = [{"id": "d1", "name": "집A", "floors": 2}, {"id": "d2", "name": "집B", "floors": 1}]
SCALAR_REPORT = {"success": True, "coverage_ratio": 23.33, "building_area": 70, "floors": [{"f": 1}], "_internal": 1}
EFFECT_DRAWING = {"success": True, "path": "/x/front.png", "format": "png"}
CURRENCY = {"success": True, "items": [{"date": "d1"}, {"date": "d2"}]}


def test_collection_explicitly_preserves_business_keys_and_origins():
    module=_load('_native_collect55', Path(__file__).resolve().parents[1]/'data/scripts/judgment_idioms.py')
    out=module.collect_values({'keep':['id','name','floors'],'results':[{'ok':True,'source':row,'value':SCALAR_REPORT} for row in PARENTS]})
    assert len(out['items'])==2
    assert out['items'][0]['coverage_ratio']==23.33
    assert out['items'][0]['name']=='집A'
    # success and private-looking user keys are data after the native boundary.
    assert out['items'][0]['success'] is True
    assert out['items'][0]['_internal']==1
    assert out['collect_renamed']


def test_effect_result_can_be_explicitly_promoted_to_a_row():
    assert value('$rows >> [table:each]{return {id:$it.id,path:$drawing.path}}',
                 inputs={'rows':PARENTS,'drawing':EFFECT_DRAWING}) == [
                     {'id':'d1','path':'/x/front.png'},{'id':'d2','path':'/x/front.png'}]


def test_default_map_retains_the_actual_result():
    assert value('$rows >> [table:each]{return $report}',inputs={'rows':PARENTS,'report':SCALAR_REPORT}) == [SCALAR_REPORT,SCALAR_REPORT]
    assert value('$rows >> [table:each]{mode:"flat_map"}{return $currency.items}',inputs={'rows':PARENTS,'currency':CURRENCY}) == CURRENCY['items']*2


def test_scalar_projection_is_explicit():
    assert value('$rows >> [table:each]{return {id:$it.id,value:"답변 산문"}}',inputs={'rows':PARENTS}) == [
        {'id':'d1','value':'답변 산문'},{'id':'d2','value':'답변 산문'}]


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
    kind, keys, more = _sweep._shape(env)        # more = 상한에 잘린 열 수(09-18: 저장은 전체+more, 절단은 표시 쪽)
    assert kind == "scalar" and more == 0
    assert keys[:3] == ["design", "design.site", "design.floors"] and "rooms[].name" in keys and "_trace" not in keys
    assert _sweep._shape({"success": True, "items": [{"a": 1}]}) == ("items", ["a"], 0)
    assert _sweep._shape({"success": False, "error": "x"}) == (None, [], 0)


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
    # 최근 성공들의 합집합(27회차 L27-1) — 가장 최근 한 줄만 적으면 op·mode 로 갈리는 반환의 한 변이만 '관측'이 된다
    assert shapes["engines:arch_report"] == {"kind": "scalar", "keys": ["coverage_ratio", "building_area", "old"],
                                             "observed": "2026-09-06", "source": "usage"}
    assert shapes["sense:weather"]["keys"] == ["date"]          # fixture 관측이 이긴다
    assert "engines:arch_create" not in shapes                   # 실패 봉투는 수확 안 함




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


def test_L27_1_harvest_unions_real_usage_and_ignores_isolated_sources(tmp_path):
    """시험 대역이 돌려준 키는 관측이 아니고, 꽉 찬 줄(원장 상한 16키)을 봤으면 목록은 전체가 아니다(more → 검사기 기권)."""
    (tmp_path / "data").mkdir()
    conn = sqlite3.connect(str(tmp_path / "data" / "world_pulse.db"))
    conn.execute("CREATE TABLE action_health (node TEXT, action TEXT, success INTEGER, keys TEXT, shape TEXT, timestamp TEXT, source TEXT)")
    full = [f"k{i}" for i in range(16)]
    conn.executemany("INSERT INTO action_health VALUES (?,?,?,?,?,?,?)", [
        ("others", "delegate", 1, json.dumps(["queued", "task_id", "message"]), "message", "2026-10-07T05:52:16", "test"),
        ("others", "delegate", 1, json.dumps(["accepted", "task_ref", "state"]), "message", "2026-10-07T05:00:00", "training"),
        ("others", "delegate", 1, json.dumps(["accepted", "task_ref", "state", "queued"]), "message", "2026-10-06T10:00:00", None),
        ("others", "delegate", 1, json.dumps(["response", "state"]), "message", "2026-10-05T10:00:00", "usage"),
        ("engines", "wide", 1, json.dumps(full), "message", "2026-10-06T10:00:00", "usage"),
    ])
    conn.commit(); conn.close()
    shapes = {"others:delegate": {"kind": "scalar", "keys": ["queued", "target", "message"], "source": "usage"}}
    assert _sweep.harvest_from_health(shapes, tmp_path) == 2
    assert shapes["others:delegate"]["keys"] == ["accepted", "task_ref", "state", "queued", "response"]
    assert shapes["others:delegate"]["observed"] == "2026-10-06" and "more" not in shapes["others:delegate"]
    assert shapes["engines:wide"]["keys"] == full and shapes["engines:wide"]["more"] == 1
