"""요청 주체(principal) 축 — 읽기 격리·좁힘 불변조건·그랜트 (2026-09-14, 외부 서비스 앱 0단계).

정본: docs/EXTERNAL_SERVICE_APP_HANDOFF.md §3-3·§4·§6-2.
영속 경로는 건드리지 않는다 — 해마 DB 검색·이웃 원장·부탁 로그·증류는 전부 monkeypatch.
"""
import json
import threading

import pytest

import sys
import boot_paths  # noqa: E402,F401

import principal as P


@pytest.fixture(autouse=True)
def _owner_context():
    P._current.set(None)
    yield
    P._current.set(None)


# ── 순수 규칙 ────────────────────────────────────────────────────────────────

def test_default_is_owner_and_narrowing_only():
    assert P.current().is_owner
    with P.narrow(P.body("7", 4, "dev7"), "t") as p:
        assert p.kind == "body" and p.id == "7"
        # 넓힘 거절: 좁힌 안에서 owner 주장 → 현재 유지
        with P.narrow(P.OWNER, "t") as q:
            assert q == p
        # 같은 등급 다른 신원 거절
        with P.narrow(P.body("8", 4), "t") as r:
            assert r == p
        # 더 좁힘은 허용
        with P.narrow(P.ANONYMOUS, "t") as a:
            assert a.kind == "anonymous"
        assert P.current() == p
    assert P.current().is_owner


def test_transport_principal_rules():
    assert P.transport_principal(external=False, session_ok=False).is_owner
    assert P.transport_principal(external=True, session_ok=True).is_owner
    assert P.transport_principal(external=True, session_ok=False).kind == "anonymous"


def test_snapshot_restore_carries_principal():
    import thread_context as tc
    seen = {}
    with P.narrow(P.body("3", 4), "t"):
        snap = tc.snapshot()

    def worker():
        prev = tc.snapshot()
        tc.restore(snap)
        seen["in"] = P.current().key()
        tc.restore(prev)
        seen["after"] = P.current().key()

    t = threading.Thread(target=worker); t.start(); t.join()
    assert seen["in"] == "body:3"
    assert seen["after"] == "owner"


# ── 해마 회상 ────────────────────────────────────────────────────────────────

class _R:
    def __init__(self, i, intent, code, score=0.9):
        self.id = i; self.intent = intent; self.ibl_code = code; self.score = score
        self.nodes = "sense"; self.category = "single"; self.alias = ""; self.returns = ""
        self.success_count = 1; self.fail_count = 0; self.avg_ms = 10; self.avg_tokens = 10
        self.topic = ""; self.tags = ""; self.difficulty = 1; self.source = "test"; self.last_seen = None
        self.success_rate = -1.0; self.implementation = ""; self.created_at = None


MARK = "표식-주인-진료기록-8f3a"


@pytest.fixture
def hippo(monkeypatch):
    from ibl_usage_db import IBLUsageDB
    import ibl_usage_rag as rag
    import ibl_registry
    monkeypatch.setattr(IBLUsageDB, "__init__", lambda self, *a, **k: None)
    monkeypatch.setattr(IBLUsageDB, "search_hybrid",
                        lambda self, query, top_k=5, **kw: [_R(1, f"{MARK} 폴더 정리", "[self:read]{path:\"/x\"}")])
    monkeypatch.setattr(ibl_registry, "code_is_own", lambda code: True)
    monkeypatch.setattr(rag.IBLUsageRAG, "_is_ibl_relevant", lambda self, q: True)
    monkeypatch.setattr(rag.IBLUsageRAG, "search_phrases", lambda self, q, allowed_nodes=None: [])
    r = rag.IBLUsageRAG(); r.clear_cache()
    yield rag
    rag.IBLUsageRAG().clear_cache()


def test_owner_recalls_marker_but_body_does_not(hippo):
    rag = hippo
    assert MARK in rag.IBLUsageRAG().get_references("진료기록 폴더 정리해줘")
    with P.narrow(P.body("9", 4), "t"):
        assert rag.IBLUsageRAG().get_references("진료기록 폴더 정리해줘") == ""
        assert rag.get_top_score("진료기록 폴더 정리해줘") == 0.0
        assert rag.get_top("진료기록 폴더 정리해줘") == (0.0, "")
        xml, score, code = rag.build_execution_memory("진료기록 폴더 정리해줘")
        assert xml == "" and score == 0.0 and code == ""


def test_cache_warmed_by_owner_not_served_to_body(hippo):
    rag = hippo
    q = "진료기록 폴더 정리해줘"
    assert MARK in rag.IBLUsageRAG().get_references(q)      # 주인이 캐시를 데운다
    with P.narrow(P.body("9", 4), "t"):
        assert rag.IBLUsageRAG().get_references(q) == ""     # 같은 질의, 다른 주체 → 캐시 미스여야 한다
    assert MARK in rag.IBLUsageRAG().get_references(q)      # 주인은 여전히 본다


def test_concurrent_owner_and_bodies(hippo):
    rag = hippo
    q = "진료기록 폴더 정리해줘"
    out = {}

    def run(name, p):
        for _ in range(20):
            if p is None:
                out.setdefault(name, set()).add(MARK in rag.IBLUsageRAG().get_references(q))
            else:
                with P.narrow(p, "t"):
                    out.setdefault(name, set()).add(MARK in rag.IBLUsageRAG().get_references(q))

    ts = [threading.Thread(target=run, args=("owner", None)),
          threading.Thread(target=run, args=("A", P.body("A", 4))),
          threading.Thread(target=run, args=("B", P.body("B", 4)))]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert out["owner"] == {True}
    assert out["A"] == {False} and out["B"] == {False}


def test_recall_mixin_yields_nothing_for_body(monkeypatch):
    """주인 것(1상 전부)은 주체가 owner 가 아니면 통째로 닫힌다 — 공통 흐름의 personal 관문."""
    import ibl_usage_rag as rag
    import associative_recall as AR
    from cognitive_recall import CognitiveRecallMixin
    monkeypatch.setattr(rag, "build_execution_memory_detail", lambda m, a=None, **kw: {
        "xml": f"<execution_memory>{MARK}</execution_memory>", "top_score": 0.9, "top_code": "[x:y]", "presented": []})
    monkeypatch.setattr("decision_ledger.scent_xml", lambda q="": f"<decision_ledger>{MARK}</decision_ledger>")
    monkeypatch.setattr(AR, "SOURCES", tuple(s for s in AR.SOURCES if s.name in ("hippocampus", "decision_ledger")))

    class Agent(CognitiveRecallMixin):
        config = {}

    a = Agent()
    r = a._associate("정리해줘").route(None)
    assert MARK in r.text() and (r.reflex.score, r.reflex.code) == (0.9, "[x:y]")
    assert [b.source for b in r.blocks] == ["hippocampus", "decision_ledger"]
    with P.narrow(P.body("9", 4), "t"):
        r = a._associate("정리해줘").route(None)
        assert r.text() == "" and (r.reflex.score, r.reflex.code) == (0.0, "") and r.blocks == []


def test_distill_skipped_for_body(monkeypatch):
    import ibl_usage_rag as rag
    from ibl_usage_db import IBLUsageDB
    def boom(self, *a, **k): raise AssertionError("해마 DB 를 열면 안 된다")
    monkeypatch.setattr(IBLUsageDB, "__init__", boom)
    with P.narrow(P.body("9", 4), "t"):
        assert rag.distill_experience("정리해줘", [{"tool": "execute_ibl", "input": {"code": "[self:read]{}"}, "success": True}], 0.1) is False


def test_deep_memory_and_forage_closed_for_body(monkeypatch):
    import sys, os
    mem_pkg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "data", "packages", "installed", "tools", "memory")
    if mem_pkg not in sys.path:
        sys.path.insert(0, mem_pkg)
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("_mem_handler_probe", os.path.join(mem_pkg, "handler.py"))
    mem_handler = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(mem_handler)

    class DB:
        VALID_CATEGORIES = {"기타"}
        def search(self, **kw): return [{"content": MARK, "preview": MARK, "category": "기타"}]
    monkeypatch.setattr(mem_handler, "_search_conversations", lambda *a, **k: [])
    assert MARK in mem_handler._memory_search(DB(), {"query": "진료"}, "/tmp/p", "a")
    with P.narrow(P.body("9", 4), "t"):
        out = json.loads(mem_handler._memory_search(DB(), {"query": "진료"}, "/tmp/p", "a"))
        assert out["count"] == 0 and out["memories"] == []

    import forage_memory as fm
    with P.narrow(P.body("9", 4), "t"):
        res = fm.recall(query="진료")
        assert not res["map"] and not res.get("territory") and res.get("closed") == "principal"
        assert fm.recall_xml(query="진료") == ""


# ── 그랜트·부탁 경로 ─────────────────────────────────────────────────────────

def test_red_grant_requires_owner_even_with_origin_user():
    import thread_context as tc
    import red_grant
    red_grant.revoke_grant()
    try:
        _owner_origin = "user"  # 변수 경유 — test_user_surface_pipeline 의 AST 표면 스캐너가 테스트를 표면으로 오인하지 않게(런타임 동일)
        with tc.actor_context(agent_id="system_ai", task_id="task_t1", origin=_owner_origin):
            with P.narrow(P.member("5", 4, "devA"), "t"):
                assert red_grant.issue_grant("system_ai", "task_t1", "x") == {}
                assert red_grant.active_grant("task_t1", "system_ai") is None
            # 주인은 발급된다
            assert red_grant.issue_grant("system_ai", "task_t1", "x")
            assert red_grant.active_grant("task_t1", "system_ai")
            # 발급 뒤 주체가 좁혀지면 조회도 닫힌다
            with P.narrow(P.member("5", 4, "devA"), "t"):
                assert red_grant.active_grant("task_t1", "system_ai") is None
    finally:
        red_grant.revoke_grant()


def test_body_ask_narrows_to_body_and_owner_surface_stays_owner(monkeypatch):
    import body_ask
    import body_trust
    seen = {}
    monkeypatch.setattr(body_ask, "_log", lambda rec: None)          # 실제 로그에 쓰지 않는다
    monkeypatch.setattr(body_trust, "get_body_level", lambda d: 4 if d == "dev-neighbor" else None)
    def fake_compile(message, correction="", payload=None):
        seen["principal"] = P.current().key()
        return {"ok": False, "error": "stop", "compiler": "test"}
    monkeypatch.setattr(body_ask, "_compile", fake_compile)
    monkeypatch.setattr(body_ask, "_neighbor_id_of", lambda device_id: "42", raising=False)

    body_ask.handle_ask("정리해줘", device_id="dev-neighbor", from_body="폰")
    assert seen["principal"] == "body:42"
    assert P.current().is_owner                                       # 범위를 나가면 복원

    body_ask.handle_ask("정리해줘")                                     # 신원 없음 = 소유주 표면
    assert seen["principal"] == "owner"

    out = body_ask.handle_ask("정리해줘", device_id="stranger-x")
    assert out.get("trust") == "unknown"


if __name__ == "__main__":                      # 러너는 하나 — pytest
    sys.exit(pytest.main([__file__, "-q"]))
