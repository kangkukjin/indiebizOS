"""재실행 턴의 적용 예약 자기수용감각 (2026-08-31 ep2461 봉합).

재실행은 새 컨텍스트다 — 자기 세션에 적용 예약분이 대기 중인 줄 모르면, 라이브·git 에
안 보이는 그 파일을 '없다'고 판단해 재작성·직접 커밋하고, 턴 종료 후 지연 적용이 그
나중 판본을 옛 초안으로 덮는다(last-writer-loses). 계약 2:
  ① 재실행 피드백 메시지에 원장 기반 '재작성 금지' 문단이 주입된다
     (_scheduled_repair_agent_note — 예약 없으면 빈 문자열).
  ② 상태 읽기(_scheduled_repair_state)는 신선한 apply_scheduled 만 사실로 인정한다
     (없음/다른 상태/좌초된 옛 예약 → None).
op_status 의 전면 배치·외침은 test_repair_staging.py S16 이 본다.
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401,E402

from cognitive_eval import CognitiveEvalMixin  # noqa: E402


def _mixin():
    return object.__new__(CognitiveEvalMixin)


def _ledger(tmp: Path, key: str, status: str, scheduled_at: datetime,
            rels=("backend/test_pending.py",), verify_cmd=""):
    d = tmp / "data" / "system_ai_state" / "repair_sessions"
    d.mkdir(parents=True, exist_ok=True)
    files = {f"/live/{r}": {"op": "write", "rel": r, "staged": f"/wt/{r}"} for r in rels}
    (d / f"{key}.json").write_text(json.dumps({
        "key": key, "status": status, "worktree": f".worktrees/repair-{key}",
        "scheduled_at": scheduled_at.isoformat(), "files": files,
    }), encoding="utf-8")
    if verify_cmd:
        (d / f"{key}.apply.json").write_text(
            json.dumps({"verify_cmd": verify_cmd}), encoding="utf-8")


def _with_context(tmp: Path, task_id: str):
    import thread_context
    thread_context.clear_all_context()
    if task_id:
        thread_context.set_current_task_id(task_id)
    os.environ["INDIEBIZ_BASE_PATH"] = str(tmp)


def teardown_function(_fn):
    import thread_context
    thread_context.clear_all_context()
    os.environ.pop("INDIEBIZ_BASE_PATH", None)


def test_fresh_scheduled_yields_state_and_forbids_rewrite():
    tmp = Path(tempfile.mkdtemp(prefix="selfaware_"))
    _ledger(tmp, "task_aware", "apply_scheduled", datetime.now(),
            rels=("backend/test_pending.py",), verify_cmd="pytest -q")
    _with_context(tmp, "task_aware")
    m = _mixin()
    state = m._scheduled_repair_state()
    assert state and state["rels"] == ["backend/test_pending.py"]
    assert state["verify_cmd"] == "pytest -q"
    note = m._scheduled_repair_agent_note()
    assert "재작성" in note and "backend/test_pending.py" in note
    assert ".worktrees/repair-task_aware" in note      # 격리본 읽기 통로 안내
    assert "git" in note                               # '안 보이는 것이 정상' 근거


def test_absent_or_wrong_status_yields_nothing():
    tmp = Path(tempfile.mkdtemp(prefix="selfaware_"))
    m = _mixin()
    _with_context(tmp, "task_none")                    # 세션 원장 자체가 없음
    assert m._scheduled_repair_state() is None
    assert m._scheduled_repair_agent_note() == ""
    _ledger(tmp, "task_applied", "applied", datetime.now())
    _with_context(tmp, "task_applied")                 # 이미 적용됨 — 예약 아님
    assert m._scheduled_repair_state() is None
    _with_context(tmp, "")                             # 태스크 컨텍스트 없음
    assert m._scheduled_repair_state() is None


def test_stale_schedule_is_not_this_turns_fact():
    tmp = Path(tempfile.mkdtemp(prefix="selfaware_"))
    _ledger(tmp, "task_stale", "apply_scheduled",
            datetime.now() - timedelta(seconds=CognitiveEvalMixin._SCHEDULED_FRESH_S + 60))
    _with_context(tmp, "task_stale")
    m = _mixin()
    assert m._scheduled_repair_state() is None         # 좌초된 옛 예약 — 주입 금지
    assert m._scheduled_repair_agent_note() == ""


if __name__ == "__main__":                             # 러너는 pytest 하나 (단일 러너 규약)
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
