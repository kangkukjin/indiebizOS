"""런타임 통화 모양 실측 — 회귀 (2026-08-24 B36-3)

재현하는 결함: fixture 면제 액션(하드웨어·유료 LLM·인자 의존)은 주간 returns 스윕의
측정 우주 밖이라 선언 드리프트가 영영 안 잡혔다(table:structure 실측 — 면제 = 측정 사각).

처방 3겹을 고정한다:
  ① 판정기는 하나(B27-1) — classify_currency 가 봉투 다이어트(summarize_result)와
     런타임 기록(shape_of)의 공통 판정. 둘이 갈라지면 요약과 건강 기록이 서로 반박한다.
  ② record_action_health 가 shape 를 적는다 (지연 마이그레이션 포함).
  ③ returns_variants 선언(param-조건부 통화, F20-1 동형)을 빌드 검증기가 강제.

실행: .venv/bin/python -m pytest backend/test_runtime_shape.py
"""
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401


# ── ① 판정기 한 벌 ─────────────────────────────────────────────────────────────

_CASES = [
    # (결과, 기대 shape) — summarize_result 와 shape_of 가 같은 답을 내야 한다
    ({"success": True, "items": [{"a": 1}]}, "items"),
    ('{"success": true, "items": []}', "items"),
    ({"success": False, "error": "죽음"}, "error"),
    ({"error": "죽음"}, "error"),
    ({"success": True, "message": "빈손 성공"}, "message"),
    ({"success": True, "path": "/tmp/x"}, "effect"),
    ({"columns": ["a"], "rows": [[1]]}, "items"),   # 표 형 → derive_items 파생 (B27-1)
    ("[줄 1-4] 본문 텍스트", "text"),
    ('[{"bare": "list"}]', "list"),
    (None, "text"),
]


def test_single_judge_contract():
    from ibl_envelope import classify_currency, shape_of, summarize_result
    for raw, want in _CASES:
        got = shape_of(raw)
        assert got == want, f"shape_of({raw!r}) = {got!r}, 기대 {want!r}"
        # 요약과 기록이 같은 판정기를 읽는다 — 갈라지면 B27-1 재발
        assert summarize_result(raw)["shape"] == got, f"요약≠기록: {raw!r}"
        shape, obj, items, derived = classify_currency(raw)
        assert shape == got
        if shape == "items":
            assert isinstance(items, list)


def test_derived_items_marked():
    from ibl_envelope import classify_currency
    shape, _obj, items, derived = classify_currency({"columns": ["a"], "rows": [[1]]})
    assert shape == "items" and derived, "표 형 방출은 파생 표지를 달아야 한다"


# ── ② 기록 경로 ────────────────────────────────────────────────────────────────

def test_record_shape_with_migration(tmp_path, monkeypatch):
    """구 스키마 DB(shape 없음)에도 지연 마이그레이션으로 기록된다."""
    import pulse_db
    path = str(tmp_path / "world_pulse.db")
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE action_health (
        id INTEGER PRIMARY KEY AUTOINCREMENT, node TEXT NOT NULL, action TEXT NOT NULL,
        success INTEGER NOT NULL, response_ms INTEGER, source TEXT NOT NULL DEFAULT 'usage',
        timestamp TEXT NOT NULL, channel TEXT, error TEXT)""")
    conn.commit()
    conn.close()
    from pathlib import Path
    monkeypatch.setattr(pulse_db, "CONSCIOUSNESS_DB_PATH", Path(path))
    monkeypatch.setattr(pulse_db, "_AH_COLS_ENSURED", False)
    monkeypatch.setattr(pulse_db, "_in_test_process", lambda: False)
    pulse_db.record_action_health("sense", "video", True, 12,
                                  source="self_check", shape="items")
    pulse_db.record_action_health("self", "read", True, 3,
                                  source="self_check", shape="text")
    rows = sqlite3.connect(path).execute(
        "SELECT node, action, shape FROM action_health ORDER BY id").fetchall()
    assert rows == [("sense", "video", "items"), ("self", "read", "text")], rows


# ── ③ returns_variants 검증기 ─────────────────────────────────────────────────

def test_returns_variants_validator():
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "scripts"))
    from iblbuild_validators import _check_action
    base = {"returns": "scalar", "router": "system", "func": "x", "description": "d",
            "target_description": "t", "group": "system", "implementation": "i"}

    def issues(cfg):
        return [i for i in _check_action("x:y", cfg, {}) if "returns_variants" in i]

    ok = {**base, "params": {"tables": "boolean"},
          "returns_variants": {"tables=true": "items"}}
    assert issues(ok) == []
    # 오타 난 param 은 어떤 실행과도 안 맞아 선언이 조용히 죽는다 — 빌드가 막는다
    typo = {**base, "params": {"tables": "boolean"},
            "returns_variants": {"tabels=true": "items"}}
    assert any("미선언" in i for i in issues(typo))
    assert any("형식" in i for i in issues({**base, "returns_variants": {"tables": "items"}}))
    assert any("허용 안 됨" in i for i in issues(
        {**base, "params": {"t": "b"}, "returns_variants": {"t=1": "records"}}))


def test_live_declaration_has_read_variants():
    """정본 선언 실존 — self:read 의 param-조건부 통화가 파생까지 실려 있다."""
    import yaml
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    d = yaml.safe_load(open(os.path.join(root, "data", "ibl_nodes.yaml"), encoding="utf-8"))
    rv = d["nodes"]["self"]["actions"]["read"].get("returns_variants")
    assert rv == {"blocks=true": "items", "tables=true": "items"}, rv


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23 규약)
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__] + sys.argv[1:]))
