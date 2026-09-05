"""union 효과 봉투 1행 규약 (2026-09-05 언어 개정, ep2827).

`[self:write] & [self:write] >> [table:union]` — 부수효과 분기의 결과(items/table 없는 success 봉투)를
union 이 "통화 종류가 같아야" 로 거절했다. 효과 봉투는 분기당 1행으로 받고 effect_rows 로 신고한다.
table 과의 혼합·죽은 분기 규약은 종전대로.

실행: .venv/bin/python -m pytest -q backend/test_union_effect_rows.py
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

_PKG = Path(__file__).resolve().parent.parent / "data" / "packages" / "installed" / "tools"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_ops = _load("_t_union_eff_dataops", os.path.join(_PKG, "data-ops", "handler.py"))

W1 = {"success": True, "path": "/x/a.json", "size": 10, "message": "저장", "_internal": 1}
W2 = {"success": True, "path": "/x/b.json", "size": 20, "message": "저장"}
ROWS = {"success": True, "items": [{"t": 1}, {"t": 2}]}


def test_two_effect_envelopes_become_two_rows():
    out = _ops._op_union([json.dumps(W1, ensure_ascii=False), json.dumps(W2, ensure_ascii=False)], {})
    assert out.get("success") is not False, out
    items = out["items"]
    assert [r["path"] for r in items] == ["/x/a.json", "/x/b.json"]
    assert "_internal" not in items[0]                      # 내부 표지는 행이 아니다
    assert out["effect_rows"] == [1, 2] and "효과 봉투" in out["note"]


def test_items_plus_effect_mix_keeps_items_and_adds_one_row():
    out = _ops._op_union([json.dumps(ROWS), json.dumps(W2)], {})
    assert out.get("success") is not False, out
    assert len(out["items"]) == 3 and out["effect_rows"] == [2]


def test_table_plus_effect_still_rejected():
    tbl = {"success": True, "table": {"columns": ["a"], "rows": [[1]]}}
    out = _ops._op_union([json.dumps(tbl), json.dumps(W2)], {})
    assert out.get("success") is False and "통화 종류" in out["error"]


def test_dead_branch_protocol_unchanged():
    dead = {"success": False, "error": "고장"}
    out = _ops._op_union([json.dumps(W1), json.dumps(dead)], {})
    assert out.get("success") is not False and out["effect_rows"] == [1]
    assert out.get("branches_skipped") or "분기" in json.dumps(out, ensure_ascii=False)

if __name__ == "__main__":
    # 러너는 하나다 — 직접 실행도 pytest 에 위임한다.
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
