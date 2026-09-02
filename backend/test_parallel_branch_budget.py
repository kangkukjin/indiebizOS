"""병렬 분기 시간 예산 회귀 — 전역 벽시계가 아닌 실행 시작+단계 수 기준 (2026-09-02).

실측 사고:
  (read >> struct) & (read >> struct) 두 가지가 각자의 정상 실행 한도보다 이른
  90초 전역 벽시계에 함께 잘렸다. max_workers=8 뒤의 가지는 시작 전 대기시간까지
  같은 벽시계에서 소비했다. 타임아웃 뒤 워커는 계속 돌지만 부모는 이미 실패를 확정했다.

처방:
  하위 라우터의 액션 실행 한도를 병렬의 한 단계 예산으로 빌리고, 괄호 파이프는 단계
  수만큼 합산한다. 예산은 워커가 실제 시작한 뒤부터 흐르며, 8개 초과는 배치별로 새로
  시작한다. 일부 가지의 타임아웃은 완료된 가지를 지우지 않고 현재 하위 단계를 말한다.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401


def _patch_budget(monkeypatch, wp, seconds):
    monkeypatch.setattr(wp, "_action_timeout_budget", lambda: seconds)
    monkeypatch.setattr(wp, "PARALLEL_TIMEOUT_GRACE", 0.0, raising=False)


def test_R1_괄호_파이프는_단계별_예산을_합산한다(monkeypatch):
    import ibl_engine
    import workflow_parallel as wp

    _patch_budget(monkeypatch, wp, 0.05)

    def _step(tool_input, project_path=None):
        time.sleep(0.035)
        return {"items": [{"action": tool_input["action"]}]}

    monkeypatch.setattr(ibl_engine, "execute_ibl", _step)
    branch = {"_branch_steps": [
        {"node": "self", "action": "read"},
        {"node": "self", "action": "struct"},
    ]}
    out = wp._execute_parallel([branch, branch], None, "")

    assert len(out) == 2
    assert all("error" not in row for row in out), out
    assert [row["items"][0]["action"] for row in out] == ["struct", "struct"]


def test_R2_워커_상한_뒤_가지가_대기시간을_예산으로_쓰지_않는다(monkeypatch):
    import ibl_engine
    import workflow_parallel as wp

    _patch_budget(monkeypatch, wp, 0.06)

    def _step(tool_input, project_path=None):
        time.sleep(0.04)
        return {"items": [{"action": tool_input["action"]}]}

    monkeypatch.setattr(ibl_engine, "execute_ibl", _step)
    branches = [{"node": "sense", "action": f"probe_{i}"} for i in range(9)]
    out = wp._execute_parallel(branches, None, "")

    assert len(out) == 9
    assert all("error" not in row for row in out), out


def test_R3_느린_가지_하나만_현재_하위단계로_실패한다(monkeypatch):
    import ibl_engine
    import workflow_parallel as wp

    _patch_budget(monkeypatch, wp, 0.03)

    def _step(tool_input, project_path=None):
        action = tool_input["action"]
        time.sleep(0.08 if action == "struct" else 0.005)
        return {"items": [{"action": action}]}

    monkeypatch.setattr(ibl_engine, "execute_ibl", _step)
    branches = [
        {"node": "sense", "action": "fast"},
        {"_branch_steps": [
            {"node": "self", "action": "read"},
            {"node": "self", "action": "struct"},
        ]},
    ]
    out = wp._execute_parallel(branches, None, "")

    assert "error" not in out[0], out
    assert "self:struct" in out[1]["error"], out
    assert out[1]["_branch_step_failed"] == "2/2"
    assert out[1]["budget_s"] == 0.06
    assert out[1]["elapsed_s"] >= 0.06


def test_R4_파이프_봉투도_괄호_가지의_현재_단계를_이름붙인다(monkeypatch):
    import ibl_engine
    import workflow_engine
    import workflow_parallel as wp

    _patch_budget(monkeypatch, wp, 0.02)

    def _step(tool_input, project_path=None):
        action = tool_input["action"]
        time.sleep(0.06 if action == "struct" else 0.005)
        return {"items": [{"action": action}]}

    monkeypatch.setattr(ibl_engine, "execute_ibl", _step)
    nested = {"_branch_steps": [
        {"node": "self", "action": "read"},
        {"node": "self", "action": "struct"},
    ]}
    env = workflow_engine.execute_pipeline(
        [{"_parallel": True, "branches": [nested]}], project_path=None)

    assert env["success"] is False, env
    assert "분기 1([self:struct])" in env["error"], env
    failed = env["results"][0]["branches_failed"][0]
    assert (failed["node"], failed["action"]) == ("self", "struct")


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__] + sys.argv[1:]))
