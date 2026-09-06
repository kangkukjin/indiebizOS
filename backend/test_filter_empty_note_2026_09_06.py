"""filter 0행의 말하는 빈손 (2026-09-06, ep2882 AI 동향 보고서 수리 신호 ③).

`[sense:search]{…} >> [table:filter]{where: "lambda.ai"}` 가 0행을 내고 봉투는 count:0 만 말해
모델이 "where 가 url 필드를 보지 않는다"로 오진했다. 0행은 옳았다(검색 결과에 그 도메인 없음).
빈손은 자기 기준(조건·본 필드·입력 행수)을 말해야 정당한 0행과 고장이 구별된다.

실행: .venv/bin/python -m pytest -q backend/test_filter_empty_note_2026_09_06.py
"""
import importlib.util
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


_ops = _load("_t_filter_empty_note_dataops", os.path.join(_PKG, "data-ops", "handler.py"))

ROWS = [{"title": "Anthropic deal", "url": "https://blockspace.media/a", "summary": "x"},
        {"title": "Lambda 35B", "url": "https://techrepublic.com/b", "summary": "y"}]


def test_substring_zero_rows_says_all_fields_were_searched():
    out = _ops._op_filter({"success": True, "items": ROWS}, {"where": "lambda.ai"})
    assert out["success"] is True and out["items"] == [] and out["count"] == 0
    assert out["rows_in"] == 2
    note = out["note"]
    assert "전-필드 부분일치" in note and "'lambda.ai'" in note
    for f in ("title", "url", "summary"):
        assert f in note                                     # 어느 필드를 봤는지 말한다
    assert "contains" in note                                # 다음 걸음(한 필드만 보는 형태)


def test_operator_zero_rows_names_condition_and_field():
    out = _ops._op_filter({"success": True, "items": ROWS}, {"where": "title contains 구글"})
    assert out["count"] == 0 and out["rows_in"] == 2
    assert "title" in out["note"] and "0행" in out["note"]


def test_nonempty_result_has_no_note():
    out = _ops._op_filter({"success": True, "items": ROWS}, {"where": "techrepublic"})
    assert out["count"] == 1 and "note" not in out and "rows_in" not in out


def test_empty_input_is_upstreams_empty_hand():
    out = _ops._op_filter({"success": True, "items": []}, {"where": "lambda.ai"})
    assert out["count"] == 0 and "note" not in out


def test_table_path_zero_rows_also_speaks():
    tbl = {"success": True, "columns": ["title", "url"], "rows": [["a", "https://x.com"], ["b", "https://y.com"]]}
    out = _ops._op_filter(tbl, {"where": "lambda.ai"})
    assert out["rows"] == [] and out["rows_in"] == 2 and "전-필드 부분일치" in out["note"]


if __name__ == "__main__":
    # 러너는 하나다 — 직접 실행도 pytest 에 위임한다.
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
