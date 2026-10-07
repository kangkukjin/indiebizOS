"""긴문장 28회차 수리 회귀(2026-10-07) — L28-5 번들 CLI 탐색, L28-4 승인 전 대상 존재 확인, (L28-1 은 test_delegation_tasks 에)."""
import boot_paths  # noqa: F401
import os
import sys
from types import SimpleNamespace
import pytest
import principal as P


def _bundle(tmp_path, *parts):
    p = tmp_path.joinpath("Library", "Application Support", "Claude", "claude-code", *parts, "claude.app", "Contents", "MacOS", "claude")
    p.parent.mkdir(parents=True)
    p.write_text("#!/bin/sh\n"); p.chmod(0o755)
    return str(p)


@pytest.mark.skipif(not hasattr(os, "getuid"), reason="실행 권한 비트로 찾는 번들 배치(POSIX)")
def test_find_claude_binary_sees_hashed_bundle_dir_and_prefers_newest(monkeypatch, tmp_path):
    """L28-5: 실제 배치는 claude-code/<ver>/<빌드 해시>/claude.app — 한 단계만 보던 탐색이 None 을 돌려줬다."""
    from pathlib import Path
    import providers.claude_code as C
    monkeypatch.setattr(C.shutil, "which", lambda name: None)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    old = _bundle(tmp_path, "2.1.288", "48d54124d3c3")
    assert C.find_claude_binary() == old
    new = _bundle(tmp_path, "2.1.289", "ee67e3f1ea60")
    assert C.find_claude_binary() == new                      # 최신 판 우선
    flat = _bundle(tmp_path, "2.1.290")
    assert C.find_claude_binary() == flat                     # 옛 평평한 배치도 그대로


def _cfg(**requires):
    return {"ops": {"default": "list", "values": {"list": "x", "delete": "y"}}, "requires": requires}


def test_gate_checks_target_exists_before_asking_a_human(monkeypatch):
    """L28-4: exists 함수가 실패 봉투를 내면 approval_required 없이 그 봉투로 거절, 대상이 있으면 승인을 묻는다."""
    import action_requires as R
    from thread_context import set_approval, get_approval
    calls = []
    def exists(params):
        calls.append(dict(params))
        return None if params.get("switch_id") == "ok" else {"success": False, "error": f"스위치 없음: {params.get('switch_id')}"}
    monkeypatch.setitem(sys.modules, "fake_exists_mod", SimpleNamespace(exists=exists))
    cfg = _cfg(ops={"delete": {"principal": ["owner"], "human_confirm": True, "exists": "fake_exists_mod:exists"}})
    token = P.set_transport(P.OWNER); prev = get_approval()
    try:
        set_approval(None, "digest")
        deny = R.gate("self", "switch", cfg, "delete", {"op": "delete", "switch_id": "nope"})
        assert deny and "스위치 없음: nope" in deny["error"] and "approval_required" not in deny and deny["error_type"] == "not_found"
        ask = R.gate("self", "switch", cfg, "delete", {"op": "delete", "switch_id": "ok"})
        assert ask and ask["approval_required"]["op"] == "delete"
        assert calls == [{"op": "delete", "switch_id": "nope"}, {"op": "delete", "switch_id": "ok"}]
        assert R.gate("self", "switch", cfg, "list", {"op": "list"}) is None     # list 는 exists 도 승인도 불요
        broken = _cfg(ops={"delete": {"human_confirm": True, "exists": "no_such_mod:fn"}})
        assert "찾지 못했습니다" in R.gate("self", "switch", broken, "delete", {})["error"]   # fail-closed
    finally:
        set_approval(*prev); P.reset_transport(token)


def test_validate_accepts_exists_shape_only():
    import action_requires as R
    assert R.validate({"ops": {"delete": {"human_confirm": True, "exists": "launcher_ops:switch_exists"}}}, {"delete"}) == []
    bad = R.validate({"ops": {"delete": {"exists": "nocolon"}}}, {"delete"})
    assert any("모듈:함수" in b for b in bad), bad


def test_switch_delete_of_missing_switch_does_not_ask_for_approval(monkeypatch, tmp_path):
    """라이브 어휘: [self:switch]{op:"delete"} 가 없는 id 면 승인 거절 대신 '스위치 없음'(별칭 id 로 불러도)."""
    import launcher_ops
    from switch_manager import SwitchManager
    sm = SwitchManager(); sm.switches_file = tmp_path / "switches.json"; sm.switches_file.write_text("[]")   # 실 switches.json 보호
    monkeypatch.setattr(launcher_ops, "_sm", lambda: sm)
    from thread_context import set_approval, get_approval
    from project_manager import ProjectManager
    from ibl_v2_entry import handle_request
    import approval_tokens as T
    pp = str(ProjectManager().get_project_path("앱모드"))
    token = P.set_transport(P.OWNER); prev = get_approval()
    try:
        for code in ('[self:switch]{op: "delete", switch_id: "deadbeef"}', '[self:switch]{op: "delete", id: "deadbeef"}'):
            set_approval(None, T.request_digest(code, {}, []))
            r = handle_request({"code": code, "edition": 2, "inputs": {}, "declared_inputs": []}, pp, None)
            assert r["success"] is False and "스위치 없음: deadbeef" in r["error"], r
            assert not (r.get("diagnostic") or {}).get("details", {}).get("approval_required"), r["diagnostic"]
        assert launcher_ops.project_exists({"project_id": "없는프로젝트_28"})["error"].startswith("프로젝트 없음")
        assert launcher_ops.project_exists({}) and launcher_ops.switch_exists({})
    finally:
        set_approval(*prev); P.reset_transport(token)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
