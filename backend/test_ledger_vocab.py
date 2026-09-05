"""[self:ledger] 회귀 — 등록 스크립트에서 승격한 원장 낱말 (2026-09-04, 사용자 판정 언어 개정).

옛 스크립트 시험(test_registered_report_scripts) 넷을 여기로 옮겼다 — 관문 넷은 전부 실사고 유래라
낱말이 바뀌어도 계약은 그대로여야 한다:
  L1  append/upsert + max_items 롤링(갱신 행은 최신 위치로)
  L2  set 은 value 키 필수 — 부재는 거절(null 은 명시 가능), 파일 불변
  L3  set 은 target 필수·key 거절 — 루트 교체는 replace_root 명시로만
  L4  enum_fields·list_limits 는 넘으면 쓰지 않고 실패
  L5  select 는 읽기 전용 items 통화 + 봉투 규모 불변식(total=모집단, limit 표본이면 truncated)
  L6  디스패처·기본 op·저장소 밖 경로 거절 · 가이드 표면에 옛 스크립트 id 잔재 없음

실행: .venv/bin/python -m pytest backend/test_ledger_vocab.py -q
"""
import json
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)
import boot_paths  # noqa: E402,F401

PKG = os.path.join(ROOT, "data", "packages", "installed", "tools", "system_essentials")
sys.path.insert(0, PKG)


@pytest.fixture
def lg(tmp_path, monkeypatch):
    import ledger_ops
    monkeypatch.setattr(ledger_ops, "_ROOT", tmp_path)
    return ledger_ops


def _saved(tmp_path, rel):
    return json.loads((tmp_path / rel).read_text(encoding="utf-8"))


def test_l1_append_upsert_rolling(lg, tmp_path):
    path = "outputs/ledger.json"
    first = lg.op_append({"path": path, "items": [{"id": "a", "v": 1}, {"id": "b", "v": 2}]})
    assert first["success"] and first["count"] == 2
    second = lg.op_upsert({"path": path, "key": "id", "max_items": 2,
                           "items": [{"id": "a", "v": 3}, {"id": "c", "v": 4}]})
    assert second["success"] and second["count"] == 2
    assert _saved(tmp_path, path) == [{"id": "a", "v": 3}, {"id": "c", "v": 4}]


def test_l2_set_requires_value_key(lg, tmp_path):
    path = "outputs/policy.json"
    assert lg.op_set({"path": path, "op": "set", "target": "explore_first", "value": True})["success"]
    for bad in ({"path": path, "target": "explore_first", "items": [False]}, {"path": path}):
        r = lg.op_set(bad)
        assert r["success"] is False and "value" in r["error"]
        assert _saved(tmp_path, path) == {"explore_first": True}
    assert lg.op_set({"path": path, "target": "explore_first", "value": None})["success"]
    assert _saved(tmp_path, path) == {"explore_first": None}


def test_l3_set_refuses_root_replace_and_key_typo(lg, tmp_path):
    path = "outputs/rotation.json"
    lg.op_upsert({"path": path, "target": "queue", "key": "slug", "item": {"slug": "wonju", "verdict": "관심"}})
    before = _saved(tmp_path, path)
    for bad, needle in ((
        {"path": path, "key": "explore_first", "value": ["asan"]}, "target"),
        ({"path": path, "value": ["asan"]}, "replace_root")):
        r = lg.op_set(bad)
        assert r["success"] is False and needle in r["error"]
        assert _saved(tmp_path, path) == before
    assert lg.op_set({"path": path, "target": "explore_first", "value": ["asan"]})["success"]
    saved = _saved(tmp_path, path)
    assert saved["explore_first"] == ["asan"] and saved["queue"] == before["queue"]
    assert lg.op_set({"path": path, "value": {"fresh": True}, "replace_root": True})["success"]
    assert _saved(tmp_path, path) == {"fresh": True}


def test_l4_enum_fields_and_list_limits(lg, tmp_path):
    path = "outputs/rotation.json"
    enums = {"verdict": ["미판정", "관심", "보류", "기각"]}
    ok = lg.op_upsert({"path": path, "target": "queue", "key": "slug", "enum_fields": enums,
                       "item": {"slug": "nowon", "verdict": "관심", "sub_verdicts": {"노원": "보류"}}})
    assert ok["success"]
    r = lg.op_upsert({"path": path, "target": "queue", "key": "slug", "enum_fields": enums,
                      "item": {"slug": "nowon", "verdict": "노원=보류 / 도봉=관심"}})
    assert r["success"] is False and "sub_verdicts" in r["error"]
    assert _saved(tmp_path, path)["queue"][0]["verdict"] == "관심"
    limits = {"tags": {"max_items": 2, "max_item_len": 5}}
    r = lg.op_append({"path": "outputs/cov.json", "item": {"tags": ["짧다", "이건 너무 긴 태그다"]}, "list_limits": limits})
    assert r["success"] is False and "5자" in r["error"]
    r = lg.op_append({"path": "outputs/cov.json", "item": {"tags": ["a", "b", "c"]}, "list_limits": limits})
    assert r["success"] is False and "상한" in r["error"]
    assert not (tmp_path / "outputs/cov.json").exists()


def test_l5_select_currency_and_scope_invariant(lg, tmp_path):
    from ibl_honesty import scope_violation
    path = "outputs/covered.json"
    lg.op_append({"path": path, "target": "covered",
                  "items": [{"id": i, "topic": "코딩" if i % 2 else "보존", "memo": "x" * 50} for i in range(6)]})
    r = lg.op_select({"path": path, "target": "covered", "fields": ["id"], "where": {"topic": "코딩"}})
    assert r["success"] and r["items"] == [{"id": 1}, {"id": 3}, {"id": 5}]
    assert r["total"] == 3 and r["truncated"] is False and scope_violation(r) is None
    r2 = lg.op_select({"path": path, "target": "covered", "where": {"topic": "코딩"}, "limit": 1})
    assert r2["total"] == 3 and r2["count"] == 1 and r2["truncated"] is True and scope_violation(r2) is None
    # items_file — 큰 payload 는 파일로
    (tmp_path / "outputs/batch.json").write_text(json.dumps([{"id": 9}]), encoding="utf-8")
    assert lg.op_append({"path": path, "target": "covered", "items_file": "outputs/batch.json"})["success"]
    assert lg.op_select({"path": path, "target": "covered", "where": {"id": 9}})["count"] == 1


def test_l6_dispatch_default_and_root_guard(lg):
    import importlib.util
    _p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "packages", "installed", "tools", "system_essentials", "handler.py")
    _spec = importlib.util.spec_from_file_location("tool_handler_system_essentials_under_test", _p)
    handler = sys.modules.get(_spec.name) or importlib.util.module_from_spec(_spec)
    if _spec.name not in sys.modules:
        sys.modules[_spec.name] = handler; _spec.loader.exec_module(handler)   # 맨 import handler 금지(모듈 이름 충돌)
    assert set(handler._OP_DISPATCHERS["ledger_op"]) == {"select", "append", "upsert", "set"}
    assert handler._OP_DEFAULTS["ledger_op"] == "select"
    r = lg.op_append({"path": "/etc/ledger.json", "item": {"id": 1}})
    assert r["success"] is False and "저장소" in r["error"]
    for g in ("housing_report", "ai_trend_report", "youtube_ai_tips_report"):
        text = open(os.path.join(ROOT, "data", "guides", g + ".md"), encoding="utf-8").read()
        assert "[self:ledger]" in text
        assert "json" + "원장" not in text, g       # retired-ok: 이관 검산 — 옛 스크립트 id 잔재 금지


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-q"]))
