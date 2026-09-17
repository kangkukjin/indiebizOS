"""용례 재검토 관문 (2026-09-18) — 액션의 행동 계약이 바뀌면 빌드가 그 액션의 용례를 다시 보게 한다."""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__)); import boot_paths  # noqa
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import iblbuild_example_review as R


def _data(target_description="content 를 저장한다", ops_returns="effect"):
    return {"nodes": {"self": {"actions": {"memory": {
        "description": "기억", "target_description": target_description, "returns": "items",
        "ops": {"values": {"save": "저장"}, "returns": {"save": ops_returns}},
        "prompt_budget": 3}}}}}                      # 계약이 아닌 필드


def test_behaviour_change_is_flagged_until_acknowledged(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "LEDGER", tmp_path / "ledger.json")
    monkeypatch.setattr(R, "examples_of", lambda q, root=None: [(1, "기억해둬", '[self:memory]{op: "save"}')])
    base = _data()
    assert R.changed_actions(base) == {"self:memory": ["(신규)"]}
    assert R.ack(base, "all") == 1 and R.changed_actions(base) == {}

    # 09-12 의 실제 변화: save 가 저장을 그만두고 안내만 한다 — 문장은 그대로, 뜻이 바뀐다
    moved = _data(target_description="즉시 저장하지 않는다. saved:false 를 돌려준다", ops_returns="scalar")
    assert R.changed_actions(moved) == {"self:memory": ["ops", "target_description"]}
    issue = R.validate_example_review(moved, tmp_path)[0]
    assert "용례 1건" in issue and "--ack self:memory" in issue

    assert R.ack(moved, ["self:memory"]) == 1 and not R.validate_example_review(moved, tmp_path)
    assert json.loads((tmp_path / "ledger.json").read_text())["actions"]["self:memory"]["examples"] == 1


def test_non_contract_fields_do_not_trigger(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "LEDGER", tmp_path / "ledger.json")
    base = _data(); R.ack(base, "all")
    base["nodes"]["self"]["actions"]["memory"]["prompt_budget"] = 99
    assert R.changed_actions(base) == {}


def test_retired_action_leaves_the_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "LEDGER", tmp_path / "ledger.json")
    R.ack(_data(), "all")
    R.ack({"nodes": {"self": {"actions": {}}}}, "all")
    assert json.loads((tmp_path / "ledger.json").read_text())["actions"] == {}


def test_live_ledger_matches_live_vocabulary():
    assert R.validate_example_review(R._load_data()) == [], "계약이 바뀐 액션의 용례를 읽고 --ack 할 것"


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__] + sys.argv[1:]))
