"""병렬 가지의 컨텍스트 승계 회귀 — 리허설 표식이 스레드를 건넌다 (2026-08-23)

재현한 결함(실측):
  `origin: "training"` 으로 실행해도 **병렬 가지만** 건강 원장에 `source='usage'` 로 쌓였다.
      [sense:stock]{op:"quote", ticker:"ZZZZINVALID"} & [sense:weather]{city:"수원"}
        → usage / usage      ← 누수
      [sense:stock]{op:"quote", ticker:"ZZZZINVALID"}          (단일)  → training ✓
      … ?? …  ·  [table:each]{…}  ·  [try]{…}                          → training ✓
  훈련 창 실측: 44행이 usage 로 기록(그중 실패 5건). E28-3('리허설은 삶이 아니다')이
  막으려던 사고가 병렬 통로로만 계속 샜다 — E28-3 주석 자체가 "actor_context 가
  each·폴백·병렬 가지까지 전파한다" 고 적어 뒀는데 **병렬은 사실이 아니었다.**

원인(단일 지점):
  `workflow_parallel._execute_parallel` 이 자식 스레드로 넘길 컨텍스트를 **손으로 5칸만
  열거**했다(task_id·agent_id·agent_name·project_id·allowed_nodes). 뒤에 추가된
  `task_origin`(= `in_rehearsal()` 이 읽는 칸)이 목록에 없었다. `threading.local` 은
  스레드를 안 건너므로 병렬 가지에서만 표식이 증발했다.

처방:
  호출부마다 플래그를 나르는 땜질이 아니라 **경계 한 지점**에서 컨텍스트를 통째 승계
  (`thread_context.snapshot()/restore()`). 같은 저장소의 다른 스레드 경계 둘
  (`ibl_engine._run_router_safely`, `ibl_routing` 워커)이 이미 쓰던 관용에 맞춘 것이다.
  열거 목록은 반드시 뒤처지므로, 통째 승계라야 다음 칸이 생겨도 자동으로 건너간다.

실행: .venv/bin/python -m pytest backend/test_parallel_context_inherit.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401


def _branches():
    return [{"node": "sense", "action": "probe_a"}, {"node": "sense", "action": "probe_b"}]


def _run_and_capture(monkeypatch):
    """병렬 가지 안에서 본 (in_rehearsal, task_origin, project_id) 를 걷어 온다."""
    import ibl_engine
    import thread_context
    import workflow_parallel as wp

    seen = []

    def _fake_execute(tool_input, project_path=None):
        seen.append({
            "action": tool_input.get("action"),
            "in_rehearsal": thread_context.in_rehearsal(),
            "origin": thread_context.get_task_origin(),
            "project_id": thread_context.get_current_project_id(),
        })
        return {"items": [{"x": 1}]}

    monkeypatch.setattr(ibl_engine, "execute_ibl", _fake_execute)
    wp._execute_parallel(_branches(), None, "")
    return seen


def test_R1_리허설_표식이_병렬_가지로_건너간다(monkeypatch):
    """이 시험이 이번 수리의 본체다 — 옛 코드(5칸 열거)에서는 실패한다."""
    import thread_context
    with thread_context.actor_context(origin="training"):
        assert thread_context.in_rehearsal(), "부모 스레드부터 리허설이어야 시험이 성립한다"
        seen = _run_and_capture(monkeypatch)
    assert len(seen) == 2, f"두 가지가 다 돌아야 한다: {seen}"
    for row in seen:
        assert row["in_rehearsal"] is True, f"병렬 가지에서 리허설 표식이 사라졌다: {row}"
        assert row["origin"] == "training"


def test_R2_실사용은_리허설로_물들지_않는다(monkeypatch):
    """반대 방향 — 격리가 과하게 걸려 실사용까지 훈련으로 찍히면 안 된다."""
    import thread_context
    thread_context.clear_all_context()
    seen = _run_and_capture(monkeypatch)
    assert len(seen) == 2
    for row in seen:
        assert row["in_rehearsal"] is False, f"실사용이 리허설로 찍혔다: {row}"


def test_R3_옛_5칸도_여전히_건너간다(monkeypatch):
    """통째 승계로 바꾸면서 원래 나르던 칸을 떨어뜨리지 않았는지 — 회귀 방지."""
    import thread_context
    thread_context.clear_all_context()
    thread_context.set_current_project_id("부동산")
    seen = _run_and_capture(monkeypatch)
    for row in seen:
        assert row["project_id"] == "부동산", f"기존에 나르던 칸이 유실됐다: {row}"


def test_R4_경계는_열거가_아니라_통째_승계여야_한다():
    """손 열거로 되돌아가면 다음 칸이 또 조용히 빠진다 — 그 회귀를 막는다."""
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "ibl", "workflow_parallel.py"), encoding="utf-8").read()
    assert "_tc.snapshot()" in src and "_tc.restore(" in src, \
        "병렬 경계가 snapshot/restore 관용을 쓰지 않는다"
    for setter in ("set_current_task_id(", "set_current_agent_name(", "set_allowed_nodes("):
        assert setter not in src, f"손 열거 복원이 되살아났다: {setter}"


def test_R5_형제_경계들과_같은_관용이다():
    """IBL 의 스레드 경계 셋이 한 관용을 쓴다(이탈이 결함이었으므로)."""
    here = os.path.dirname(os.path.abspath(__file__))
    for rel in (("ibl", "ibl_engine.py"), ("ibl", "ibl_routing.py"),
                ("ibl", "workflow_parallel.py")):
        src = open(os.path.join(here, *rel), encoding="utf-8").read()
        assert ".snapshot()" in src and ".restore(" in src, f"{rel} 이 관용에서 이탈했다"


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__, "-q"] + _sys.argv[1:]))
