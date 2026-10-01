"""폴더변화 — 대조·확인 대기·확인의 계약."""
import importlib.util
import os
import time
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location("folder_watch", Path(__file__).with_name("폴더변화.py"))


@pytest.fixture
def fw(tmp_path, monkeypatch):
    mod = importlib.util.module_from_spec(_SPEC)
    _SPEC.loader.exec_module(mod)
    monkeypatch.setattr(mod, "STATE_DIR", tmp_path / "state")
    root = tmp_path / "proj"
    (root / "outputs").mkdir(parents=True)
    (root / "outputs" / "a.md").write_text("a")
    (root / "conversations.db").write_text("x")
    mod.root = root
    return mod


def _touch(path, text, age=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    t = time.time() + 5 - age          # 수정 시각을 확실히 움직인다(초 단위 비교)
    os.utime(path, (t, t))


def test_first_check_sets_baseline_and_reports_nothing(fw):
    out = fw.main({"path": str(fw.root)})
    assert out["first_check"] and out["count"] == 0 and out["watched_files"] == 1   # DB 는 기본 제외
    assert fw.main({"path": str(fw.root)})["count"] == 0


def test_changes_are_added_modified_removed_and_runtime_files_are_ignored(fw):
    fw.main({"path": str(fw.root)})
    _touch(fw.root / "outputs" / "b.md", "b")
    _touch(fw.root / "outputs" / "a.md", "aa")
    _touch(fw.root / "conversations.db", "xx")
    _touch(fw.root / "memory_tree_001" / "가지" / "memory.md", "m")
    out = fw.main({"path": str(fw.root), "exclude": ["memory_tree_*/*"]})
    assert {(r["path"], r["change"]) for r in out["items"]} == {("outputs/b.md", "added"), ("outputs/a.md", "modified")}
    assert out["by_dir"] == {"outputs": 2}
    (fw.root / "outputs" / "b.md").unlink()
    out = fw.main({"path": str(fw.root), "exclude": ["memory_tree_*/*"]})
    assert [(r["path"], r["change"]) for r in out["items"]] == [("outputs/b.md", "removed")]


def test_unacked_changes_come_back_until_acked(fw):
    args = {"path": str(fw.root), "name": "resurvey", "commit": False}
    fw.main(args)
    _touch(fw.root / "outputs" / "b.md", "b")
    first = fw.main(args)
    assert first["count"] == 1 and first["awaiting_ack"]
    _touch(fw.root / "outputs" / "c.md", "c")                       # 받는 쪽이 죽은 사이의 변화
    again = fw.main(args)
    assert {r["path"] for r in again["items"]} == {"outputs/b.md", "outputs/c.md"}
    assert fw.main({**args, "op": "ack"})["acked"]
    _touch(fw.root / "outputs" / "d.md", "d")                       # 확인 뒤의 변화만 남는다
    assert [r["path"] for r in fw.main(args)["items"]] == ["outputs/d.md"]


def test_ack_promotes_what_was_shown_not_what_exists_now(fw):
    args = {"path": str(fw.root), "commit": False}
    fw.main(args)
    _touch(fw.root / "outputs" / "b.md", "b")
    fw.main(args)
    _touch(fw.root / "outputs" / "late.md", "l")                    # 대조와 확인 사이에 생긴 것
    fw.main({**args, "op": "ack"})
    assert [r["path"] for r in fw.main(args)["items"]] == ["outputs/late.md"]
    assert not fw.main({**args, "op": "ack", "name": "다른 이름"})["acked"]


def test_since_bounds_the_first_check(fw):
    _touch(fw.root / "outputs" / "old.md", "o", age=3600)
    _touch(fw.root / "outputs" / "new.md", "n")
    cut = fw._iso(time.time() - 60)
    out = fw.main({"path": str(fw.root), "since": cut, "commit": False})
    assert "outputs/new.md" in {r["path"] for r in out["items"]} and "outputs/old.md" not in {r["path"] for r in out["items"]}
    assert "outputs/new.md" in {r["path"] for r in fw.main({"path": str(fw.root), "commit": False})["items"]}


def test_watchignore_in_the_folder_silences_declared_routine_additions(fw):
    args = {"path": str(fw.root), "commit": False}
    fw.main(args)
    _touch(fw.root / "outputs" / "chart_20260926_093505.png", "c1")
    assert fw.main(args)["count"] == 1
    (fw.root / ".watchignore").write_text("# 매일 쌓이는 차트 — 이름 규칙은 문서에 있다\noutputs/chart_*.png\n")
    out = fw.main(args)
    assert out["count"] == 0 and out["ignore_patterns"] == ["outputs/chart_*.png"] and out["ignored"] == 1
    _touch(fw.root / "outputs" / "chart_20260927_090000.png", "c2")
    _touch(fw.root / "outputs" / "report.md", "r")
    out = fw.main(args)
    assert [r["path"] for r in out["items"]] == ["outputs/report.md"] and out["ignored"] == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
