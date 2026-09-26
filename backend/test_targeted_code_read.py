"""범위 조합과 실제 IBL 검색→읽기→보고 회귀. 모델·외부 네트워크 호출 없음."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401

spec = importlib.util.spec_from_file_location("targeted_code_read", ROOT / "data/scripts/targeted_code_read.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
SOURCE = json.loads((ROOT / "data/idioms/code_read_seeds.json").read_text())[0]["ibl_code"]


def target(name):
    return {"name": name, "pattern": "^def " + name + r"\("}


def run(project, targets, **params):
    from ibl_edition import source_context
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    inputs = {"대상": targets, "루트": "sample.py", **params}
    code = "[fn:대상별좁혀읽기]{" + ",".join(f"{key}:${key}" for key in inputs) + "}"
    plan = compile_program(code, load_registry(str(project)), inputs=inputs,
                           definitions={"대상별좁혀읽기": SOURCE})
    assert not plan.issues, plan.report()
    with source_context(2):
        return Runtime(plan, inputs).run()


def test_fourth_target_is_not_lost_and_overlapping_ranges_are_read_once(tmp_path):
    (tmp_path / "sample.py").write_text("".join(f"def {name}():\n    pass\n" for name in "abcd"))
    out = run(tmp_path, [target(name) for name in "abcd"])
    assert out["success"] and out["source_complete"], out
    value = out["value"]
    assert value["all_targets_read"]
    assert [row["name"] for row in value["items"]] == list("abcd")
    assert value["items"][3]["matches"][0]["line"] == 7
    assert value["unmerged_ranges"] == 4 and value["read_requests"] == 1
    assert value["ranges"][0]["end_line"] == 8  # EOF는 절단 실패가 아니다.
    assert sum(e.get("action") == "self:read" for e in out["evidence"]) == 1
    assert len(value["ranges"][0]["excerpt_sha256"]) == 64


def test_missing_and_invalid_targets_are_reported_without_losing_good_target(tmp_path):
    (tmp_path / "sample.py").write_text("def a():\n    pass\n")
    out = run(tmp_path, [target("a"), target("absent"), {"name": "bad", "pattern": "["}])
    assert out["success"], out
    assert [row["status"] for row in out["value"]["items"]] == ["read", "not_found", "search_failed"]
    assert not out["value"]["all_targets_read"]
    assert all(row["reason"] for row in out["value"]["items"][1:])


def test_search_limit_cannot_claim_complete(tmp_path):
    (tmp_path / "sample.py").write_text("def a():\n    pass\ndef a():\n    pass\n")
    out = run(tmp_path, [target("a")], 검색상한=1)
    assert out["success"], out
    assert not out["value"]["all_targets_read"]
    assert out["value"]["items"][0]["status"] in {"partial", "search_failed"}
    assert out["value"]["items"][0]["reason"]


def planned_pair():
    config = helper.prepare({"targets": [target("a"), target("b")], "before": 0, "after": 0})
    searches = [{"name": name, "result": {"items": [{"파일": "sample.py", "줄번호": i,
                 "내용": f"def {name}():"}], "total": 1, "truncated": False}}
                for name, i in (("a", 1), ("b", 3))]
    return helper.plan({"config": config, "searches": searches})


@pytest.mark.parametrize("second", [
    {"problem": "접근 거절"},
    {"result": {"text": "def changed():\n", "data": {"total_lines": 4, "start_line": 3}}},
    {"result": {"text": "", "data": {"total_lines": 4, "start_line": 3}}},
])
def test_read_failure_file_change_and_short_read_keep_target_reason(second):
    plan = planned_pair()
    reads = [{"id": "range-1", "result": {"text": "def a():\n", "data": {"total_lines": 4, "start_line": 1}}},
             {"id": "range-2", **second}]
    value = helper.finish({"plan": plan, "reads": reads})
    assert [row["status"] for row in value["items"]] == ["read", "partial"]
    assert value["items"][1]["reason"] and not value["all_targets_read"]


def test_duplicate_positions_are_collapsed_but_each_target_keeps_its_reference():
    config = helper.prepare({"targets": [target("a"), target("b")]})
    hit = {"파일": "same.py", "줄번호": 5, "내용": "def a(): # b"}
    searches = [{"name": name, "result": {"items": [hit, hit], "total": 2, "truncated": False}}
                for name in ("a", "b")]
    plan = helper.plan({"config": config, "searches": searches})
    assert len(plan["ranges"]) == 1
    assert all(len(row["matches"]) == 1 for row in plan["items"])
    assert plan["items"][0]["matches"][0]["range_id"] == plan["items"][1]["matches"][0]["range_id"]


@pytest.mark.parametrize("targets", [[], [target("a"), target("a")], ["a"], [{"name": "a", "pattern": ""}]])
def test_invalid_target_contract_is_rejected(targets):
    with pytest.raises(ValueError):
        helper.prepare({"targets": targets})


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
