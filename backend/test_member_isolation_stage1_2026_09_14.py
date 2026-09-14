"""외부 서비스 앱 1단계 — 회원 격리(부재·권한·쓰기·귀속·세션) (2026-09-14).

정본: docs/EXTERNAL_SERVICE_APP_HANDOFF.md §3-0·§3-3·§3-4·§3-6·§6. 영속 경로는 전부 임시화/monkeypatch.
"""
import json
import sys
import threading
from pathlib import Path

import pytest

import boot_paths  # noqa: E402,F401

import principal as P
import member_profile as MP

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

MARK_A, MARK_B = "표식-회원A-진료기록-7c1d", "표식-회원B-연말정산-2e9f"


@pytest.fixture(autouse=True)
def _owner_context():
    """요청 문맥이 없는 시험 프로세스에서는 authenticate 가 세운 주체가 다음 시험으로 샌다 — 매 시험 owner 로."""
    P._current.set(None)
    yield
    P._current.set(None)


# ── 빌드 선언 검증 ──────────────────────────────────────────────────────────

def test_fingerprint_parity_between_build_and_runtime():
    from iblbuild_derive import handler_fingerprint as build_fp
    pkg = ROOT / "data" / "packages" / "installed" / "tools" / "guest-helper"
    assert build_fp(pkg) == MP.handler_fingerprint(pkg)


def _pkg(tmp_path, name="pkg1", body="def handler():\n    return 1\n"):
    d = tmp_path / "data" / "packages" / "installed" / "tools" / name
    d.mkdir(parents=True)
    (d / "handler.py").write_text(body, encoding="utf-8")
    (d / "tool.json").write_text(json.dumps({"tools": [{"name": "t1", "input_schema": {"type": "object"}}]}), encoding="utf-8")
    return d


def test_validate_lands_on_rules(tmp_path, monkeypatch):
    from iblbuild_lands_on import validate_lands_on
    import iblbuild_derive
    d = _pkg(tmp_path)
    monkeypatch.setattr(iblbuild_derive, "build_tool_index", lambda root: {"t1": (d, {})})
    fp = iblbuild_derive.handler_fingerprint(d)
    data = {"nodes": {
        "sense": {"actions": {
            "ok_body": {"lands_on": "body", "limb_op": {"op": "read", "path": "$path"}},
            "bad_body": {"lands_on": "body"},
            "ok_hub": {"lands_on": "hub", "tool": "t1", "path_audited": {"at": "2026-09-14", "impl": fp}},
            "stale_hub": {"lands_on": "hub", "tool": "t1", "path_audited": {"at": "2026-09-14", "impl": "0000000000000000"}},
            "noaudit_hub": {"lands_on": "hub", "tool": "t1"},
            "core_hub": {"lands_on": "hub", "path_audited": {"at": "x", "impl": "y"}},
            "effect_hub": {"lands_on": "hub", "tool": "t1", "returns": "effect", "path_audited": {"at": "x", "impl": fp}},
            "orphan": {"limb_op": {"op": "read"}},
            "bad_val": {"lands_on": "cloud"},
        }},
        "others": {"actions": {"ask": {"lands_on": "hub", "tool": "t1", "path_audited": {"at": "x", "impl": fp}}}},
    }}
    issues = validate_lands_on(data, tmp_path)
    txt = "\n".join(issues)
    assert "sense:ok_body" not in txt and "sense:ok_hub" not in txt
    for bad in ("bad_body", "stale_hub", "noaudit_hub", "core_hub", "effect_hub", "orphan", "bad_val", "others:ask"):
        assert bad in txt, (bad, txt)


# ── 프로파일 축 ────────────────────────────────────────────────────────────

def test_profile_axis_is_owner_intersect_member(monkeypatch):
    import vocabulary_state as vs
    state = {"version": 1, "revision": 1, "active": {"a": True, "b": True, "c": False},
             "profiles": {"member": {"active": {"a": True, "c": True}}}}
    monkeypatch.setattr(vs, "read_state", lambda root=None: state)
    assert vs.is_active("a") and vs.is_active("b") and not vs.is_active("c")
    assert vs.is_active("a", profile="member")
    assert vs.is_active("b", profile="member")          # 회원 지원 기능은 별도 공개 없이 기본 허용
    assert not vs.is_active("c", profile="member")      # 회원 허용이어도 주인이 잠재움
    state["profiles"]["member"]["active"]["b"] = False
    assert not vs.is_active("b", profile="member")      # 공통 예외 설정은 유지
    assert not vs.is_active("a", profile="unknown")


# ── 부재·권한 ─────────────────────────────────────────────────────────────

@pytest.fixture
def synth(monkeypatch, tmp_path):
    d = _pkg(tmp_path, "pkg1")
    fp = MP.handler_fingerprint(d)
    man = {"version": 1, "actions": {
        "self:read": {"lands_on": "body", "package": "pkg1", "side_effect": False, "limb_op": {"op": "read", "path": "$path"}},
        "sense:calc": {"lands_on": "hub", "package": "pkg1", "side_effect": False, "path_audited": {"at": "x", "impl": fp}},
        "sense:stale": {"lands_on": "hub", "package": "pkg1", "side_effect": False, "path_audited": {"at": "x", "impl": "dead"}},
        "sense:asleep": {"lands_on": "hub", "package": "pkg2", "side_effect": False, "path_audited": {"at": "x", "impl": fp}},
    }}
    monkeypatch.setattr(MP, "manifest", lambda root=None: man)
    monkeypatch.setattr(MP, "_package_dir", lambda pid, root=None: d if pid in ("pkg1", "pkg2") else None)
    import vocabulary_state as vs
    monkeypatch.setattr(vs, "is_active", lambda pid, root=None, profile=None: (pid == "pkg1") if profile == "member" else True)
    monkeypatch.setattr(vs, "action_owner", lambda node, action, cfg=None, root=None: None)
    return man


def test_visible_and_gate(synth):
    assert MP.visible("self", "package", {}) and MP.gate("self", "package", {}) is None   # 주인: 무영향
    with P.narrow(P.member("7", 4, "devA"), "t"):
        assert not MP.visible("self", "package", {})
        assert MP.gate("self", "package", {})["error_type"] == "permission"       # 선언 없음=거절
        assert MP.visible("self", "read", {})
        assert MP.gate("self", "read", {})["error_type"] == "no_body"             # body: 1단계는 정직 거절
        assert MP.visible("sense", "calc", {}) and MP.gate("sense", "calc", {}) is None
        assert not MP.visible("sense", "stale", {})
        assert MP.gate("sense", "stale", {})["error_type"] == "permission"        # 옛 지문=닫힘
        assert not MP.visible("sense", "asleep", {})
        assert MP.gate("sense", "asleep", {})["error_type"] == "permission"       # 회원 프로파일 잠듦
    with P.narrow(P.member("7", 4, ""), "t"):
        assert MP.gate("self", "read", {})["error_type"] == "no_body"             # 바인딩 기기 없음


def test_engine_gate_refuses_member_before_handler(monkeypatch, tmp_path):
    """직접 친 IBL 이 잎에서 거절된다 — 핸들러는 닿지 않는다(부재≠권한)."""
    import ibl_engine
    called = {"n": 0}
    monkeypatch.setattr(ibl_engine, "_route_handler", lambda *a, **k: called.__setitem__("n", called["n"] + 1) or {"success": True})
    from system_tools import _execute_ibl_unified
    with P.narrow(P.member("7", 4, "devA"), "t"):
        out = _execute_ibl_unified({"code": '[sense:weather]{city: "서울"}'}, str(tmp_path), agent_id="member:7")
    if isinstance(out, str):
        try:
            out = json.loads(out)
        except Exception:
            pass
    text = json.dumps(out, ensure_ascii=False) if not isinstance(out, str) else out
    assert "permission" in text or "회원 세션에 없는" in text, text
    assert called["n"] == 0


def test_skeletonize_strips_values():
    code = '[self:write]{path: "/Users/kim/진료기록.txt", content: "비밀 메모", n: 3} >> [table:sort]{by: "date"}'
    sk = MP.skeletonize(code)
    for leak in ("진료기록", "비밀", "/Users/kim", "date"):
        assert leak not in sk
    assert "[self:write]" in sk and "[table:sort]" in sk and "path" not in sk


# ── 쓰기 격리 ─────────────────────────────────────────────────────────────

def test_after_response_writes_nothing_for_member(monkeypatch):
    import ibl_usage_rag as rag
    from cognitive_distill import CognitiveDistillMixin

    class Boom(Exception):
        pass

    def boom(*a, **k):
        raise Boom("주인 저장소에 쓰면 안 된다")
    monkeypatch.setattr(rag, "distill_experience", boom)
    monkeypatch.setattr(rag, "record_recall_outcome", boom)

    class Agent(CognitiveDistillMixin):
        _log = staticmethod(lambda *a, **k: None)
        def _distill_deep_memory(self, *a, **k): raise Boom("심층")
        def _distill_forage_memory(self, *a, **k): raise Boom("포식")
    a = Agent()
    tc = [{"tool": "execute_ibl", "input": {"code": "[self:read]{}"}, "success": True}]
    with P.narrow(P.member("7", 4, "devA"), "t"):
        a._after_response(MARK_A, "응답", tool_calls=tc, hippo_score=0.1)      # 예외 없이 조용히 돌아온다
        import distill_queue
        monkeypatch.setattr(distill_queue, "enqueue", boom, raising=False)
        a._after_response_async(MARK_A, "응답", tool_calls=tc, hippo_score=0.1)


# ── 작업 귀속 ─────────────────────────────────────────────────────────────

def test_job_result_ownership():
    import phone_jobs
    from api_limb import _job_owned
    jid = phone_jobs.enqueue("devA", '{"op":"read"}')
    assert phone_jobs.owner_of(jid) == "devA"
    assert _job_owned(jid, {"device_id": "devA"})
    assert not _job_owned(jid, {"device_id": "devB"})
    assert not _job_owned("nope", {"device_id": "devA"})
    phone_jobs.pull_blocking("devA", 0)


# ── 회원 열쇠 결합 ─────────────────────────────────────────────────────────

def test_member_key_links_existing_neighbor(monkeypatch, tmp_path):
    import limb_keys, body_trust
    monkeypatch.setattr(limb_keys, "_store_path", lambda: tmp_path / "limb_keys.json")
    limb_keys.invalidate()
    contacts = {}
    class FakeBM:
        def get_neighbor(self, nid): return {"id": nid, "name": "가족A", "info_level": 3} if nid == 42 else None
        def get_neighbor_by_contact(self, ctype, val): return contacts.get(val)
        def add_contact(self, nid, ctype, val): contacts[val] = {"id": nid, "info_level": 3}; return {"ok": True}
    import business_manager
    monkeypatch.setattr(business_manager, "BusinessManager", FakeBM)
    m = limb_keys.mint("A의PC", ttl_days=0, neighbor_id=42)
    link = body_trust.link_body(m["device_id"], 42)
    assert link["linked"] and link["level"] == 3
    assert body_trust.link_body(m["device_id"], 42)["linked"]                  # 멱등
    assert not body_trust.link_body(m["device_id"], 43)["linked"]              # 다른 이웃에 재결합 거절
    assert not body_trust.link_body("dev-x", 99)["linked"]                     # 없는 이웃
    rec = limb_keys.validate(m["key"])
    assert rec["neighbor_id"] == 42 and body_trust.get_body_level(m["device_id"]) == 3
    limb_keys.invalidate()


def test_api_member_identity_and_principal(monkeypatch):
    import api_member, limb_keys, body_trust
    monkeypatch.setattr(limb_keys, "validate", lambda k: {"device_id": "devA", "neighbor_id": 7, "alias": "A", "approved": True} if k == "kA"
                        else ({"device_id": "devL", "alias": "L"} if k == "kL" else None))
    monkeypatch.setattr(body_trust, "get_body_level", lambda d: 4 if d == "devA" else None)
    monkeypatch.setattr(body_trust, "get_body_neighbor_id", lambda d: 7 if d == "devA" else None)
    assert api_member._member_of("bad")[1]["error"] == "invalid_or_expired_key"
    assert api_member._member_of("kL")[1]["error"] == "not_member_key"
    (rec, nid, level), err = api_member._member_of("kA")
    assert err is None and nid == "7" and level == 4
    assert api_member._principal_for(rec, nid, level).key() == "member:7"       # owner 기저에서 세움
    P._current.set(None)
    with P.narrow(P.ANONYMOUS, "t"):
        assert api_member._principal_for(rec, nid, level).key() == "member:7"   # 외부 공개 경로 기저에서 세움
    P._current.set(None)
    with P.narrow(P.body("9", 4), "t"):
        assert api_member._principal_for(rec, nid, level) is None              # 다른 신원 문맥=불일치


# ── 회원 세션(테넌트 경계) ────────────────────────────────────────────────

@pytest.fixture
def mgr(monkeypatch, tmp_path):
    import member_session as ms
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "member_policy.json").write_text(json.dumps({"daily_turns": 3, "max_sessions_per_member": 1}), encoding="utf-8")
    monkeypatch.setattr(ms, "_base", lambda: tmp_path)
    import agent_pipeline

    class FakeRunner:
        config = {"name": "회원도우미"}
        def __init__(self, s): self.s = s
        def cognitive_stream(self, message, history, **kw):
            yield {"final": f"echo:{message}:{P.current().key()}:hist={len(history)}"}
    monkeypatch.setattr(ms.MemberSession, "_ensure_runner", lambda self: setattr(self, "runner", FakeRunner(self)) if self.runner is None else None)
    monkeypatch.setattr(agent_pipeline, "drain_stream", lambda gen: next(gen))
    m = ms.MemberSessionManager(base=tmp_path)
    return m, tmp_path


def test_two_members_are_isolated(mgr):
    m, base = mgr
    ra = m.turn("A", "devA", 4, "가족A", MARK_A)
    rb = m.turn("B", "devB", 2, "직원B", MARK_B)
    assert ra["success"] and rb["success"]
    assert ra["response"].endswith("member:A:hist=0") and rb["response"].endswith("member:B:hist=0")
    ra2 = m.turn("A", "devA", 4, "가족A", "다시")
    assert ra2["response"].endswith("member:A:hist=2")
    sa, sb = m.sessions[("A", "devA")], m.sessions[("B", "devB")]
    assert MARK_B not in json.dumps(list(sa.history), ensure_ascii=False)
    assert MARK_A not in json.dumps(list(sb.history), ensure_ascii=False)
    assert P.current().is_owner                                                 # 턴 뒤 주체 복원
    usage = (base / "data" / "member_usage.json").read_text(encoding="utf-8")
    assert MARK_A not in usage and MARK_B not in usage and '"turns": 2' in usage   # 메타 저장소: 허용 필드만
    assert m.turn("A", "devA", 4, "가족A", "셋").get("success")
    assert m.turn("A", "devA", 4, "가족A", "넷")["error_type"] == "limit"         # 일일 한도
    assert m.turn("A", "devA2", 4, "가족A", "x")["error_type"] == "limit"        # 세션 수 상한(=1)
    sb.lock.acquire()
    try:
        assert m.turn("B", "devB", 2, "직원B", "x")["error_type"] == "busy"        # 동시 턴 상한
    finally:
        sb.lock.release()


def test_session_tmp_dir_lifecycle(mgr):
    m, base = mgr
    m.turn("A", "devA", 4, "가족A", "안녕")
    s = m.sessions[("A", "devA")]
    s.dir.mkdir(parents=True, exist_ok=True); (s.dir / "x.txt").write_text("t", encoding="utf-8")
    assert m.close("A", "devA") and not s.dir.exists()
    orphan = base / "data" / "_member_tmp" / "Z-devZ-deadbeef"; orphan.mkdir(parents=True)
    assert m.sweep_orphans() == 1 and not orphan.exists()


def test_concurrent_turns_keep_principal_per_thread(mgr):
    m, _ = mgr
    out = {}
    def run(nid, dev, mark):
        for i in range(5):
            r = m.turn(nid, dev, 4, nid, f"{mark}-{i}")
            out.setdefault(nid, set()).add(r.get("response", "").split(":")[2] if r.get("success") else r.get("error_type"))
    ts = [threading.Thread(target=run, args=("A", "devA", MARK_A)), threading.Thread(target=run, args=("B", "devB", MARK_B))]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert out["A"] <= {"member", "limit"} and out["B"] <= {"member", "limit"}
    assert all(("member:A" in json.dumps(list(m.sessions[("A", "devA")].history))) for _ in [0])


def test_member_runner_prompt_hides_undeclared_words(monkeypatch, tmp_path):
    """부재 층 실증 — 회원 주체에서 세운 러너의 카탈로그에 선언 없는 낱말이 없다."""
    import member_session as ms
    from ai_agent import AIAgent
    monkeypatch.setattr(AIAgent, "_init_provider", lambda self: None)
    import vocabulary_state as vs
    real_is_active = vs.is_active
    monkeypatch.setattr(vs, "is_active", lambda pid, root=None, profile=None: real_is_active(pid, root) if profile == "member" else real_is_active(pid, root))
    (tmp_path / "data").mkdir(exist_ok=True)
    monkeypatch.setattr(ms, "_base", lambda: tmp_path)
    s = ms.MemberSession("A", "devA", 4, "가족A", tmp_path, ms.load_policy(tmp_path))
    try:
        with P.narrow(P.member("A", 4, "devA"), "t"):
            s._ensure_runner()
            prompt = s.runner.ai.system_prompt
        # 부재는 카탈로그(<ibl_actions>)의 사실이다 — 개요 산문이 낱말 이름을 언급하는 것과 구별한다.
        cat = prompt[prompt.index("<ibl_actions>"):prompt.index("</ibl_actions>")]
        assert "self:read" in cat and "self:write" in cat
        for hidden in ("[self:package]", "[self:install_lib]", "[others:", "[limbs:guestpc]", "[self:limb]"):
            assert hidden not in cat, hidden
        assert "회원" in prompt
    finally:
        s.close()


if __name__ == "__main__":                      # 러너는 하나 — pytest
    sys.exit(pytest.main([__file__, "-q"]))
