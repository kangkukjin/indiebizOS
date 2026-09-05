"""이음매 수리 2종 (2026-09-05, 시스템 AI 보고 — 문법은 맞는데 어휘끼리 안 맞물린 자리).

  ① `$변수.items` 가 table/blocks 통화(union·groupby·select 가 방출)에서 죽었다 — 파이프 이음매는
     derive_items 로 items 를 파생해 주는데 변수 경로 읽기만 원형을 그대로 읽었다(소비처 누락).
  ② `[self:ledger]{items_file}` 이 `[self:write]{format:"json"}` 이 낸 `{items, count}` 봉투 파일을
     항목 하나로 감싸 "upsert 항목마다 key 'id'가 필요합니다" 로 죽었다 — 어휘 설명이 권하는 조합.

실행: .venv/bin/python -m pytest -q backend/test_seam_repairs_2026_09_05.py
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: E402,F401

_PKG = Path(__file__).resolve().parent.parent / "data" / "packages" / "installed" / "tools"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── ① 변수 경로의 .items 파생 ──
def test_var_path_items_derives_from_table_currency():
    from workflow_binding import _extract_result_field_obj as ext
    table_env = json.dumps({"success": True, "table": {"columns": ["a", "b"], "rows": [[1, 2], [3, 4]]}})
    assert ext(table_env, "items") == [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
    assert ext(table_env, "items.1.a") == 3
    assert ext(table_env, "items.*.b") == [2, 4]
    # 최상위 columns/rows 형도, blocks(document) 통화도 같은 판정기
    assert ext(json.dumps({"columns": ["x"], "rows": [[9]]}), "items") == [{"x": 9}]
    assert ext(json.dumps({"blocks": [{"type": "p", "text": "t"}]}), "items.0.text") == "t"


def test_var_path_items_keeps_direct_items_and_honest_error():
    from workflow_binding import _extract_result_field_obj as ext
    assert ext(json.dumps({"items": [{"k": 1}], "table": {"columns": ["k"], "rows": [[5]]}}), "items.0.k") == 1
    with pytest.raises(ValueError, match="items"):
        ext(json.dumps({"success": True, "path": "/x"}), "items")      # 효과 봉투 — 통화 아님, 종전대로 정직 오류
    assert ext(json.dumps({"success": True, "path": "/x"}), "items?") is None


# ── ② ledger items_file 이 write format:"json" 봉투를 받는다 ──
@pytest.fixture
def lg(tmp_path, monkeypatch):
    mod = _load("_t_seam_ledger_ops", os.path.join(_PKG, "system_essentials", "ledger_ops.py"))
    monkeypatch.setattr(mod, "_ROOT", tmp_path)
    return mod


def test_ledger_items_file_accepts_write_json_envelope(lg, tmp_path):
    batch = tmp_path / "outputs" / "batch.json"
    batch.parent.mkdir(parents=True)
    # [self:write]{format:"json"} 가 파이프 싱크로 쓰는 모양(sink_ops V53-1 ⓑ)
    batch.write_text(json.dumps({"items": [{"id": "a", "v": 1}, {"id": "b", "v": 2}], "count": 2}), encoding="utf-8")
    out = lg.op_upsert({"path": "outputs/ledger.json", "target": "rows", "items_file": "outputs/batch.json"})
    assert out["success"], out
    assert out["count"] == 2 and [r["id"] for r in out["items"]] == ["a", "b"]
    # 맨 배열 파일은 종전대로
    batch.write_text(json.dumps([{"id": "c", "v": 3}]), encoding="utf-8")
    out = lg.op_append({"path": "outputs/ledger.json", "target": "rows", "items_file": "outputs/batch.json"})
    assert out["success"] and out["count"] == 3
    # 통화 아닌 dict 는 여전히 항목 하나(감싸기) — upsert 면 key 검사가 정직하게 거절
    batch.write_text(json.dumps({"success": True, "path": "/x"}), encoding="utf-8")
    out = lg.op_upsert({"path": "outputs/ledger.json", "target": "rows", "items_file": "outputs/batch.json"})
    assert out["success"] is False and "key 'id'" in out["error"]


if __name__ == "__main__":
    # 러너는 하나다 — 직접 실행도 pytest 에 위임한다.
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
