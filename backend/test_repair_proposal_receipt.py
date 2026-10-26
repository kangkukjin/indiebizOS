"""제안 영수증의 판본 연결 — 긴문장 98회차 L98-1(검증 뒤 사본 변경)·L98-3(미추적 대상 diff)."""
import os
import shutil
import tempfile
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

from test_repair_staging import _load_handler, _make_repo, _ready_supervisor, _ungrant


@pytest.fixture
def proposal_repo():
    import supervision_bus
    saved = supervision_bus.current
    supervision_bus.current = lambda *args, **kwargs: _ready_supervisor()
    os.environ["INDIEBIZ_REPAIR_NO_SPAWN"] = "1"
    tmp = Path(tempfile.mkdtemp(prefix="stg_receipt_")).resolve()
    _make_repo(tmp)
    (tmp / "frontend").mkdir()
    h = _load_handler()
    h._REPO_ROOT = tmp
    _ungrant()
    st = h._staging_mod()
    try:
        yield tmp, h, st
    finally:
        supervision_bus.current = saved
        _ungrant()
        shutil.rmtree(tmp, ignore_errors=True)


def _propose(st, h, tmp, rel, old, new):
    return st.op_propose({"_repo_root": str(tmp), "_red_check": h._red_zone_violation,
                          "_red_is_live": h._red_is_live_path, "path": str(tmp / rel),
                          "old_string": old, "new_string": new, "reason": "영수증 판본 시험"})


def test_untracked_target_gets_text_diff_and_candidate_hash(proposal_repo):
    tmp, h, st = proposal_repo
    rel = "backend/cognition/untracked_subject.py"
    (tmp / rel).write_text("def fold(x):\n    return 'failed'\n")  # 커밋하지 않은 미추적 파일
    r = _propose(st, h, tmp, rel, "return 'failed'", "return 'unverified'")
    assert r.get("success") is True, r
    assert "-    return 'failed'" in r["diff"] and "+    return 'unverified'" in r["diff"], r["diff"]
    assert r["candidate_hash"]
    key = r["key"]                      # 제안 응답이 세션 키를 준다(status 전체 목록을 훑지 않아도 된다)
    assert key == "proposal-" + r["proposal_id"]
    s = st.op_status({"_repo_root": str(tmp), "key": key})
    item = s["items"][0]
    assert item["candidate_hash"] == r["candidate_hash"] and item["verified_current"] is True
    assert item["files"] == [rel]
    st.op_discard({"_repo_root": str(tmp), "proposal_id": r["proposal_id"]})


def test_status_marks_candidate_changed_after_verification(proposal_repo):
    tmp, h, st = proposal_repo
    rel = "backend/cognition/victim.py"
    r = _propose(st, h, tmp, rel, "VALUE = 'original'", "VALUE = 'repaired'")
    assert r.get("success") is True and r["verified"] is True, r
    key = "proposal-" + r["proposal_id"]
    staged = tmp / r["worktree"] / rel
    stat = staged.stat()
    staged.write_text("VALUE = 'REPAIRED'\n")                       # 같은 크기
    os.utime(staged, ns=(stat.st_atime_ns, stat.st_mtime_ns))        # 같은 mtime — 내용 해시만 다르다
    s = st.op_status({"_repo_root": str(tmp), "key": key})
    item = s["items"][0]
    assert item["verified_current"] is False and item["verified"] is False, item
    assert item["candidate_hash_now"] != item["candidate_hash"] and "미검증" in item["verified_note"]
    # 전체 목록은 다시 세지 않지만 영수증 판본은 드러낸다.
    listing = st.op_status({"_repo_root": str(tmp)})
    mine = next(i for i in listing["items"] if i["key"] == key)
    assert mine["candidate_hash"] == r["candidate_hash"] and "verified_current" not in mine
    # 사본에서 범위 밖 파일을 더 바꾸면 key 조회의 files 가 그것을 드러낸다.
    (tmp / r["worktree"] / "backend/cognition/bystander.py").write_text("OTHER = 'changed in copy'\n")
    s = st.op_status({"_repo_root": str(tmp), "key": key})
    assert set(s["items"][0]["files"]) == {rel, "backend/cognition/bystander.py"}
    st.op_discard({"_repo_root": str(tmp), "proposal_id": r["proposal_id"]})


if __name__ == "__main__":
    pytest.main([__file__])
