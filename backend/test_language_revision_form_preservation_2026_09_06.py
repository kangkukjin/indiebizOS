"""형태 보존 규약 — 언어 개정 2026-09-06 (ep2882 AI 동향 보고서 57액션 프로그램 step 27 사망).

규칙: 변환자는 통화의 **형태**를 보존한다 — items 가 들어오면 items 가 나가고, 표형(columns/rows)은
명시 표형 입력을 받은 자리에서만 유지된다. 빈 items 도 통화다(표 경로 승격 시 0행 표).

죽었던 자리: `$전체1 = $투자 & $기술 >> [table:union]` 이 표를 내고, `$전체1 & $논문(0행) >> [table:union]` 이
'1=table, 2=items' 로 죽었다(빈 items 는 승격되지 않아서). 같은 부류: select 가 items 를 표로 바꿔
`${최신.items.0.path}` 바인딩이 "items 필드가 없습니다" 로 죽었다(09-05 수리는 경로 앞의 점 때문에 한 번도 안 돌았다).

실행: .venv/bin/python -m pytest -q backend/test_language_revision_form_preservation_2026_09_06.py
"""
import importlib.util
import json
import os
from pathlib import Path

_PKG = Path(__file__).resolve().parent.parent / "data" / "packages" / "installed" / "tools"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


H = _load("_t_form_pres_dataops", os.path.join(_PKG, "data-ops", "handler.py"))

A = {"success": True, "items": [{"title": "a", "url": "u1"}]}
B = {"success": True, "items": [{"title": "b", "url": "u2"}]}
EMPTY = {"success": True, "items": [], "count": 0}
TABLE = {"success": True, "table": {"columns": ["title"], "rows": [["t"]]}}


def _u(objs):
    return H._op_union([json.dumps(o, ensure_ascii=False) for o in objs], {})


def test_union_items_in_items_out():
    r = _u([A, B])
    assert r.get("success") is not False and isinstance(r.get("items"), list)
    assert "table" not in r and [x["title"] for x in r["items"]] == ["a", "b"]


def test_union_result_then_empty_items_chains():
    """ep2882 step 27 재현 — 2차 union 에 0행 가지."""
    r1 = _u([A, B])
    r2 = _u([r1, EMPTY])
    assert r2.get("success") is not False, r2.get("error")
    assert len(r2["items"]) == 2


def test_union_explicit_table_with_empty_items_promotes_zero_rows():
    r = _u([TABLE, EMPTY])
    assert r.get("success") is not False, r.get("error")
    assert r["table"]["rows"] == [["t"]]           # 명시 표형이 있으면 표형 유지, 빈 items 는 0행 표


def test_union_explicit_table_with_items_stays_table():
    r = _u([TABLE, A])
    assert r.get("success") is not False and "table" in r


def test_select_rename_groupby_preserve_items_form():
    s = H._op_select(dict(A), {"columns": ["title"]})
    assert s["items"] == [{"title": "a"}] and "table" not in s and "columns" not in s
    rn = H._op_rename(dict(A), {"map": {"title": "제목"}})
    assert rn["items"][0]["제목"] == "a" and "table" not in rn
    g = H._op_groupby({"success": True, "items": [{"g": "x", "v": 1}, {"g": "x", "v": 2}]},
                      {"by": "g", "agg": {"n": ["count", "v"]}})
    assert g["items"] == [{"g": "x", "n": 2}]


def test_explicit_table_input_keeps_table_form():
    t = {"success": True, "columns": ["g", "v"], "rows": [["x", 1], ["x", 2]]}
    s = H._op_select(dict(t), {"columns": ["g"]})
    assert s.get("columns") == ["g"] and "items" not in s
    g = H._op_groupby(dict(t), {"by": "g", "agg": {"n": ["count", "v"]}})
    tbl = g.get("table") or g
    assert tbl["columns"] == ["g", "n"] and tbl["rows"] == [["x", 2]]


def test_binding_items_path_on_table_form_derives(tmp_path):
    """`${a.items.0.path}` — 파서가 넘기는 경로는 점으로 시작한다(.items.0.path). 09-05 수리의 가드가
    그 점 때문에 한 번도 돌지 않았던 자리(ep2882 3번 호출)."""
    from workflow_binding import _extract_result_field_obj
    raw = json.dumps({"success": True, "columns": ["name", "path"], "rows": [["a", "/x/a.md"]]})
    assert _extract_result_field_obj(raw, ".items.0.path") == "/x/a.md"
    assert _extract_result_field_obj(raw, "items.0.path") == "/x/a.md"


def test_engine_end_to_end_select_then_read(tmp_path):
    f = tmp_path / "one.md"
    f.write_text("hello", encoding="utf-8")
    from system_tools import _execute_ibl_unified
    code = ('$a = [table:take]{items: [{"name": "one", "path": "%s"}], n: 1} >> [table:select]{columns: ["name", "path"]}\n'
            '$b = [self:read]{path: "${a.items.0.path}"}' % str(f))
    out = json.loads(_execute_ibl_unified({"code": code}, str(tmp_path), agent_id="probe"))
    assert out.get("success") is True, out.get("error")


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
