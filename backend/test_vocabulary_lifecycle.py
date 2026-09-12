"""네 인수 원칙: 선택 권한·보존·호출 차단·회상 후보·복구."""
from types import SimpleNamespace

import pytest
import vocabulary_state as state
from test_vocabulary_state import box
from vocabulary_lifecycle import HUMAN_AUTHORITY, set_package_active


def test_sleep_wake_preserves_files_and_uses_one_reset(box, monkeypatch):
    import ibl_routing
    calls = []
    monkeypatch.setattr(ibl_routing, "invalidate_runtime_caches", lambda: calls.append(1) or [])
    before = {p: p.read_bytes() for p in box.rglob('*') if p.is_file()}
    assert not set_package_active("awake", False)["success"]
    assert state.is_active("awake")
    assert set_package_active("awake", False, authority=HUMAN_AUTHORITY)["success"]
    with pytest.raises(ValueError, match="잠들어"):
        state.require_tool_active("awake")
    assert set_package_active("awake", True, authority=HUMAN_AUTHORITY)["success"]
    state.require_tool_active("awake")
    assert len(calls) == 2
    assert all(p.read_bytes() == content for p, content in before.items())


def test_failed_reset_restores_selection(box, monkeypatch):
    import ibl_routing
    answers = iter([["failed"], []])
    monkeypatch.setattr(ibl_routing, "invalidate_runtime_caches", lambda: next(answers))
    with pytest.raises(RuntimeError, match="실패"):
        set_package_active("awake", False, authority=HUMAN_AUTHORITY)
    assert state.is_active("awake")


def test_required_cannot_sleep(box):
    with pytest.raises(ValueError, match="필수어휘"):
        set_package_active("base", False, authority=HUMAN_AUTHORITY)


def test_rag_refills_after_sleeping_top_results(monkeypatch):
    import ibl_usage_rag as rag
    rows = [SimpleNamespace(id=i, ibl_code="sleep" if i < 10 else "awake") for i in range(13)]
    class DB:
        def search_hybrid(self, top_k, **kwargs):
            return rows[:top_k]
    monkeypatch.setattr(rag, "_own_only", lambda rs: [r for r in rs if r.ibl_code == "awake"])
    assert [r.id for r in rag._search_active(DB(), top_k=2)] == [10, 11]


def test_http_without_user_metadata_rejected(monkeypatch):
    import sys
    from starlette.requests import Request
    from api_vocabulary import human_authority
    monkeypatch.setitem(sys.modules, "api_launcher_web", SimpleNamespace(
        is_external_request=lambda req: False, verify_session=lambda req: False))
    request = Request({"type": "http", "headers": [], "method": "POST", "path": "/vocabulary/x/activation"})
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        human_authority(request)
    assert exc.value.status_code == 403


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
