"""② 권한 연결(2026-10-05): 액션 `requires:` 관문 + 사람 승인 토큰 + 표면 $principal.

docs/APP_COMMON_FOUNDATION_GAPS_2026_10_05.md §1-②. 세 사실을 가른다 — 누구인가(principal, 기존), 무엇이 허용됐나
(requires 선언), 사람이 이 요청을 승인했나(approval_tokens: 주체·액션·op·요청 지문에 묶인 1회성 토큰).
"""
import boot_paths  # noqa: F401
import pytest
import principal as P


def _cfg(**requires):
    return {"ops": {"default": "list", "values": {"list": "x", "activate": "y", "deactivate": "z"}}, "requires": requires}


def test_declared_merges_action_level_with_op_override():
    import action_requires as R
    cfg = _cfg(principal=["owner"], ops={"activate": {"human_confirm": True}})
    assert R.declared(cfg, "list") == {"principal": ["owner"]}
    assert R.declared(cfg, "activate") == {"principal": ["owner"], "human_confirm": True}
    assert R.declared({"ops": {"values": {"a": ""}}}, "a") is None


def test_validate_rejects_bad_structure_and_unknown_ops():
    import action_requires as R
    assert R.validate({"principal": ["owner"], "human_confirm": True}, {"a"}) == []
    bad = R.validate({"principal": ["king"], "min_level": -1, "human_confirm": "yes", "ops": {"zz": {"bogus": 1}}, "extra": 1}, {"a"})
    joined = " ".join(bad)
    for needle in ("미지의 키", "principal", "min_level", "human_confirm", "'zz'", "ops.zz"):
        assert needle in joined, (needle, bad)


def test_gate_enforces_principal_kind_and_level():
    import action_requires as R
    cfg = _cfg(principal=["owner", "member"], min_level=3)
    token = P.set_transport(P.OWNER)
    try:
        assert R.gate("self", "x", cfg, "list") is None
        with P.narrow(P.member("m1", 2, "d")):
            deny = R.gate("self", "x", cfg, "list")
            assert deny and deny["error_type"] == "permission" and "등급 3" in deny["error"]
        with P.narrow(P.member("m2", 4, "d")):
            assert R.gate("self", "x", cfg, "list") is None
        with P.narrow(P.ANONYMOUS):
            deny = R.gate("self", "x", cfg, "list")
            assert deny and "주체만" in deny["error"]
    finally:
        P.reset_transport(token)


def test_gate_human_confirm_requires_token_bound_to_request_digest_once():
    import action_requires as R
    import approval_tokens as T
    from thread_context import set_approval, get_approval
    cfg = _cfg(ops={"activate": {"principal": ["owner"], "human_confirm": True}})
    token = P.set_transport(P.OWNER)
    prev = get_approval()
    try:
        set_approval(None, "digest-A")
        deny = R.gate("self", "package", cfg, "activate")
        assert deny and deny["approval_required"]["action"] == "self:package" and deny["approval_required"]["op"] == "activate"
        ch = deny["approval_required"]["challenge"]
        assert ch == T.challenge(P.current().key(), "self:package", "digest-A", "activate")
        # 다른 요청(지문)에 발급된 토큰은 맞지 않는다 — 승인 뒤 내용을 바꾸면 통과하지 못한다
        other = T.issue(T.challenge(P.current().key(), "self:package", "digest-B", "activate"))["token"]
        set_approval(other, "digest-A")
        assert R.gate("self", "package", cfg, "activate") is not None
        # 같은 지문에 발급된 토큰은 한 번 통과하고 소비된다
        good = T.issue(ch)["token"]
        set_approval(good, "digest-A")
        assert R.gate("self", "package", cfg, "activate") is None
        assert R.gate("self", "package", cfg, "activate") is not None  # 1회성
        # list 는 승인 불요
        set_approval(None, "digest-A")
        assert R.gate("self", "package", cfg, "list") is None
    finally:
        set_approval(*prev)
        P.reset_transport(token)


def test_tokens_expire_and_validate_challenge_shape():
    import approval_tokens as T
    with pytest.raises(ValueError):
        T.issue("short")
    ch = T.challenge("owner", "self:x", "d")
    t = T.issue(ch, ttl=10)
    assert not T.consume("nope", ch) and not T.consume(t["token"], T.challenge("owner", "self:y", "d"))
    assert T.consume(t["token"], ch) and not T.consume(t["token"], ch)


def test_engine_leaf_applies_requires_for_edition2_programs(monkeypatch):
    """[self:package]{op:"activate"} 는 승인 없이는 approval_required 로 거절되고, 승인 토큰과 같은 요청이면 set_package_active 를
    HUMAN_AUTHORITY 로 부른다(요청 지문은 api_ibl 이 싣는 것을 여기서 흉내)."""
    import vocabulary_lifecycle as VL
    import approval_tokens as T
    from thread_context import set_approval, get_approval
    from project_manager import ProjectManager
    from ibl_v2_entry import handle_request
    calls = []
    monkeypatch.setattr(VL, "set_package_active", lambda pid, active, *, authority=None, profile=None:
                        (calls.append((pid, active, authority is VL.HUMAN_AUTHORITY, profile)) or {"success": True, "package_id": pid, "active": active}))
    pp = str(ProjectManager().get_project_path("앱모드"))
    code = '[self:package]{op: "activate", package_id: "record-ops"}'
    digest = T.request_digest(code, {}, [])
    token = P.set_transport(P.OWNER)
    prev = get_approval()
    try:
        set_approval(None, digest)
        r = handle_request({"code": code, "edition": 2, "inputs": {}, "declared_inputs": []}, pp, None)
        assert r["success"] is False
        ask = (r.get("diagnostic") or {}).get("details", {}).get("approval_required")
        assert ask and ask["action"] == "self:package" and ask["op"] == "activate", r
        assert calls == []
        set_approval(T.issue(ask["challenge"])["token"], digest)
        r = handle_request({"code": code, "edition": 2, "inputs": {}, "declared_inputs": [], "resume": r['resume']}, pp, None)
        assert r["success"] is True, r.get("error")
        assert calls == [("record-ops", True, True, "owner")]
    finally:
        set_approval(*prev)
        P.reset_transport(token)


def test_manifest_carries_principal_and_validator_allows_it():
    import importlib.util, sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("iblbuild_appview", root / "scripts/iblbuild_appview.py")
    av = importlib.util.module_from_spec(spec); sys.path.insert(0, str(root / "scripts")); spec.loader.exec_module(av)
    block = {"edition": 2, "inputs": [], "action": '[self:list]{path: $principal.kind}', "view": [{"type": "kv", "rows": []}]}
    assert av._validate_app_block("t", block, {"self:list"}) == []


def test_activation_route_is_thin_passage_over_requires_gate(monkeypatch):
    """② 2차: 조종실 HTTP `/vocabulary/{id}/activation` 은 사람 통로 증명 뒤 `[self:package]{op, package_id, profile}` 를 관문 위로
    보내는 얇은 통로다 — 라우트가 HUMAN_AUTHORITY 를 직접 건네지 않고, 관문이 소비한 뒤 핸들러가 건넨다. 주체가 owner 가 아니면
    (사람 표면이어도) requires.principal 이 거절한다."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import api_vocabulary as V
    import vocabulary_lifecycle as VL
    calls = []
    monkeypatch.setattr(V, "human_authority", lambda request: VL.HUMAN_AUTHORITY)   # 사람 표면 증명은 기존 검사 그대로(여기선 통과)
    monkeypatch.setattr(VL, "set_package_active", lambda pid, active, *, authority=None, profile=None:
                        (calls.append((pid, active, authority is VL.HUMAN_AUTHORITY, profile)) or {"success": True, "package_id": pid, "active": active}))
    app = FastAPI()
    @app.middleware("http")
    async def identify(request, call_next):
        tok = P.set_transport(P.ANONYMOUS if request.headers.get("x-test-anonymous") else P.OWNER)
        try:
            return await call_next(request)
        finally:
            P.reset_transport(tok)
    app.include_router(V.router)
    import approval_tokens as T
    with TestClient(app) as c:
        before = T.pending_count()
        r = c.post("/vocabulary/record-ops/activation", json={"active": True, "profile": "member"})
        assert r.status_code == 200 and r.json()["active"] is True, r.text
        assert calls == [("record-ops", True, True, "member")]
        assert T.pending_count() == before   # 통로가 발급한 토큰은 관문이 소비했다(남는 토큰 없음)
        assert c.post("/vocabulary/record-ops/activation", json={"active": False, "profile": "king"}).status_code == 400
        denied = c.post("/vocabulary/record-ops/activation", json={"active": False}, headers={"x-test-anonymous": "1"})
        assert denied.status_code == 400 and "주체만" in denied.json()["detail"], denied.text
        assert len(calls) == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
