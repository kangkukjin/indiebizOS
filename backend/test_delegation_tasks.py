"""비동기 실행·조건부 위임 수리 회귀 (2026-10-05, docs/ASYNC_DELEGATION_REPAIR_DESIGN_2026_10_05.md).

재현한 결함:
  · `[others:delegate]{scope:cross, mode:sync}` 가 mode 를 무시하고 접수 문구만 돌려줌
  · same 의 sync 가 임시 AIAgent(별도 실행기)로 돌아 async 와 실행기가 둘
  · background 접수가 task_id 없이 "작업을 시작했습니다" 만 돌려주고 예외는 traceback 으로만 사라짐
  · 위임 봉투에 origin 이 없어 훈련이 위임을 지나면 자식이 실사용으로 기록됨, 순환 위임 무방비
  · complete_task 가 결과를 500자로 잘라 조회가 요약밖에 못 줌, 자식 응답 중복 통지가 카운터를 두 번 뺌
실 모델·외부 발송 없음 — 저장소는 임시 DB, 러너는 대역.
"""
import json
import sqlite3
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
import yaml

import system_ai_memory as memory
import thread_context as tc

PROJECT = "fixture"
AGENT_ID = "agent_x"
AGENT_NAME = "조사자"


class FakeRunner:
    """AgentRunner 대역 — 레지스트리·메시지 큐·send_message 만."""
    _lock = threading.RLock()

    def __init__(self, target):
        self.agent_registry = {f"{PROJECT}:{AGENT_ID}": target}
        self.internal_messages = {}
        self.sent = []

    def get_agent_by_name(self, name, project_id=None):
        for runner in self.agent_registry.values():
            if runner.config.get("name") == name:
                return runner
        return None

    def get_agent_by_id(self, agent_id, project_id=None):
        return self.agent_registry.get(f"{project_id}:{agent_id}")

    def send_message(self, to_agent_id, message, from_agent="system", task_id=None, envelope=None):
        msg = {"content": message, "from_agent": from_agent, "task_id": task_id}
        if envelope:
            msg.update({k: envelope[k] for k in ("origin", "chain", "role", "allowed", "context") if k in envelope})   # = ENVELOPE_KEYS
        self.internal_messages.setdefault(to_agent_id, []).append(msg)
        self.sent.append(msg)
        return True


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "MEMORY_DB_PATH", tmp_path / "system.db")
    monkeypatch.setattr(memory, "DATA_PATH", tmp_path)
    project_path = tmp_path / "projects" / PROJECT
    project_path.mkdir(parents=True)
    (project_path / "agents.yaml").write_text(yaml.safe_dump({
        "agents": [{"id": AGENT_ID, "name": AGENT_NAME, "active": True}]}), encoding="utf-8")
    from conversation_db import ConversationDB
    db = ConversationDB(str(project_path / "conversations.db"))
    target = SimpleNamespace(config={"id": AGENT_ID, "name": AGENT_NAME}, db=db,
                             registry_key=f"{PROJECT}:{AGENT_ID}")
    runner = FakeRunner(target)
    monkeypatch.setitem(sys.modules, "agent_runner", SimpleNamespace(AgentRunner=runner))
    import delegation_tasks as dt
    import system_ai_tools
    monkeypatch.setattr(dt, "get_base_path", lambda: tmp_path)
    monkeypatch.setattr(system_ai_tools, "_get_base_path", lambda: tmp_path)
    monkeypatch.setattr(dt, "POLL_SECONDS", 0.02)
    previous = tc.snapshot()
    tc.clear_all_context()
    yield SimpleNamespace(tmp=tmp_path, project_path=str(project_path), db=db, target=target,
                          runner=runner, dt=dt)
    tc.restore(previous)


def _complete_child_later(world, parent_owner, parent_id, text, failed=False, delay=0.05):
    """대역 보고기 — 자식 메시지가 큐에 오르면 자식 행을 닫고 부모 원장에 child 별 1회 반영."""
    def run():
        deadline = time.time() + 3
        while time.time() < deadline:
            msgs = world.runner.internal_messages.get(f"{PROJECT}:{AGENT_ID}") or []
            if msgs:
                break
            time.sleep(0.01)
        time.sleep(delay)
        child = msgs[0]["task_id"]
        response = {"child_task_id": child, "from_agent": AGENT_NAME, "response": text[:500], "failed": failed}
        if parent_owner == "system":
            recorded = memory.record_child_response(parent_id, response)
        else:
            recorded = world.db.record_child_response(parent_id, response)
        assert recorded["mode"] == "sync" and not recorded["duplicate"]
        if failed:
            world.target.db.fail_task(child, text)
        else:
            world.target.db.complete_task(child, text)
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


def test_cross_sync_waits_for_the_accepted_task_and_returns_full_result(world):
    from routing_system import _delegate_unified
    memory.create_task("parent1", "user@gui", "gui", "원요청")
    tc.set_current_task_id("parent1")
    tc.set_task_origin("training")
    full = "결과 본문 " * 200  # 500자 초과 — 전문이 돌아와야 한다
    _complete_child_later(world, "system", "parent1", full)
    result = _delegate_unified({"scope": "cross", "mode": "sync", "agent_id": f"{PROJECT}/{AGENT_ID}",
                                "message": "조사해줘"}, world.project_path)
    assert result["success"] is True and result["sync"] is True, result
    assert result["response"] == full and len(result["response"]) > 500
    assert result["state"] == "succeeded" and result["task_ref"]["owner"] == PROJECT
    assert result["status_url"] == f"/projects/{PROJECT}/agents/{AGENT_ID}/tasks/{result['task_ref']['task_id']}"
    # 결과를 손에 든 부모 턴이 "위임 중"으로 열려 있지 않다.
    assert tc.did_call_agent() is False
    parent = memory.get_task("parent1")
    assert parent["pending_delegations"] == 0
    entry = json.loads(parent["delegation_context"])["delegations"][0]
    assert entry["mode"] == "sync" and entry["child_task_id"] == result["task_ref"]["task_id"]
    # 봉투 — 출처와 조상 사슬이 자식 메시지에 실린다.
    msg = world.runner.internal_messages[f"{PROJECT}:{AGENT_ID}"][0]
    assert msg["origin"] == "training" and msg["chain"] == ["system_ai"]


def test_cross_async_returns_receipt_not_completion(world):
    from routing_system import _delegate_unified
    memory.create_task("parent2", "user@gui", "gui", "원요청")
    tc.set_current_task_id("parent2")
    result = _delegate_unified({"scope": "cross", "agent_id": f"{PROJECT}/{AGENT_ID}", "message": "조사"},
                               world.project_path)
    assert result["accepted"] is True and result["state"] == "queued"
    assert result["child_task_id"] and result["task_ref"] == {"kind": "delegation", "owner": PROJECT, "task_id": result["child_task_id"]}   # ③ 접수증 통화: kind 동반
    assert "접수" in result["message"] and tc.did_call_agent() is True
    child = world.db.get_task(result["child_task_id"])
    assert child["parent_task_id"] == "parent2" and child["requester_channel"] == "system_ai"


def _fake_system_runner(monkeypatch):
    # 위임자는 프로젝트 에이전트(시스템 AI 가 자기에게 위임하면 순환으로 거절되는 것이 맞다)
    tc.set_current_project_id(PROJECT)
    tc.set_current_agent_id(AGENT_ID)
    queued = []
    class FakeSystemAIRunner:
        @classmethod
        def send_message(cls, content, from_agent, task_id=None, project_id=None, envelope=None):
            queued.append({"content": content, "from_agent": from_agent, "task_id": task_id, "envelope": envelope})
    monkeypatch.setitem(sys.modules, "system_ai_runner", SimpleNamespace(SystemAIRunner=FakeSystemAIRunner))
    return queued


def test_system_scope_async_returns_receipt_with_preissued_task(world, monkeypatch):
    """③ 2차: scope:system 도 접수 시점에 시스템 작업을 선발급해 task_ref·status_url 을 돌려준다(옛 경로는 id 없는 문구뿐)."""
    from routing_system import _delegate_unified
    queued = _fake_system_runner(monkeypatch)
    memory.create_task("parent5", "user@gui", "gui", "원요청")
    tc.set_current_task_id("parent5")
    result = _delegate_unified({"scope": "system", "message": "AI 동향 보고서 써줘", "from_agent": "앱"}, world.project_path)
    assert result["accepted"] is True and result["state"] == "queued" and result["queued"] is True
    child = result["task_ref"]["task_id"]
    assert result["task_ref"] == {"kind": "delegation", "owner": "system", "task_id": child}
    assert result["status_url"] == f"/system-ai/tasks/{child}"
    assert queued and queued[0]["task_id"] == child and queued[0]["envelope"]["chain"]
    row = memory.get_task(child)
    assert row["parent_task_id"] == "parent5" and row["requester_channel"] == "delegate" and row["delegated_to"] == "system_ai"
    assert world.dt.task_view("system", child)["state"] == "running"


def test_system_scope_sync_waits_for_the_preissued_task(world, monkeypatch):
    from routing_system import _delegate_unified
    queued = _fake_system_runner(monkeypatch)
    def finish_later():
        deadline = time.time() + 3
        while time.time() < deadline and not queued:
            time.sleep(0.01)
        time.sleep(0.05)
        memory.complete_task(queued[0]["task_id"], "보고서 본문")
    threading.Thread(target=finish_later, daemon=True).start()
    result = _delegate_unified({"scope": "system", "mode": "sync", "message": "보고서"}, world.project_path)
    assert result["success"] is True and result["state"] == "succeeded" and result["response"] == "보고서 본문"
    assert result["task_ref"]["owner"] == "system" and result["sync"] is True


@pytest.mark.parametrize("surface", [None, "web"])
def test_app_button_can_start_system_delegation(world, monkeypatch, surface):
    """실 REST 진입 문맥: 운영자 권한의 system_ai 는 AI가 실행 중이라는 뜻이 아니다."""
    import asyncio
    from api_ibl import IBLRequest, execute_ibl_code
    from routing_system import register_all

    queued = _fake_system_runner(monkeypatch)
    tc.clear_all_context()
    register_all()
    result = asyncio.run(execute_ibl_code(IBLRequest(
        code='[others:delegate]{scope:"system",message:"보고서 써줘",from_agent:"정기보고앱"}',
        project_path=world.project_path, surface=surface)))
    assert queued, result
    msg = queued[0]
    assert msg["envelope"]["chain"] == ["app"]
    assert msg["envelope"]["origin"] == "user"
    assert memory.get_task(msg["task_id"])["parent_task_id"] is None


def test_scheduled_pipeline_can_start_system_delegation(world, monkeypatch):
    from ibl_scheduled import execute_scheduled
    from routing_system import register_all

    queued = _fake_system_runner(monkeypatch)
    tc.clear_all_context()
    register_all()
    result = execute_scheduled(
        '[others:delegate]{scope:"system",message:"보고서 써줘"}', world.project_path, None)
    assert queued, result
    msg = queued[0]
    assert msg["envelope"]["chain"] == ["scheduler"]
    assert msg["envelope"]["origin"] == "scheduler"
    assert memory.get_task(msg["task_id"])["parent_task_id"].startswith("task_schedule_")


@pytest.mark.parametrize("channel", [None, "agent", "app", "scheduler"])
def test_system_ancestor_cannot_be_bypassed_by_channel_or_sender(world, monkeypatch, channel):
    from routing_system import _delegate_unified

    queued = _fake_system_runner(monkeypatch)
    tc.set_delegation_chain(["system_ai"])
    tc.set_call_channel(channel, override=True)
    result = _delegate_unified({"scope": "system", "message": "되돌려", "from_agent": "정기보고앱"},
                               world.project_path)
    assert result["error_type"] == "delegation_cycle"
    assert not queued


@pytest.mark.parametrize("agent_id", ["system_ai", "system_ai_delegation"])
def test_system_ai_cannot_delegate_to_itself(world, monkeypatch, agent_id):
    from routing_system import _delegate_unified

    queued = _fake_system_runner(monkeypatch)
    tc.set_current_agent_id(agent_id)
    tc.set_call_channel("agent", override=True)
    result = _delegate_unified({"scope": "system", "message": "되돌려", "from_agent": "앱"},
                               world.project_path)
    assert result["error_type"] == "delegation_cycle"
    assert not queued


# ── ⑨ 위임의 실행 범위 지정(2026-10-05): role·allowed·context — allowed 는 좁히기만·상속 ──

def test_allowed_narrows_only_and_inherits(world):
    from delegation_tasks import narrowed_allowed, envelope, received
    tc.set_allowed_nodes(None)
    eff, clamped = narrowed_allowed(["sense"])
    assert "sense" in eff and {"self", "others", "table"} <= set(eff) and clamped == []     # 무제한 부모 = 요청 그대로(코어 포함)
    assert narrowed_allowed(None) == (None, [])
    tc.set_allowed_nodes({"sense", "self", "others", "table"})
    eff, clamped = narrowed_allowed(["limbs", "sense"])
    assert "limbs" not in eff and "sense" in eff and clamped == ["limbs"]                   # 부모 밖은 잘린다
    assert narrowed_allowed(None) == (sorted({"sense", "self", "others", "table"}), [])     # 요청 없음 = 상속
    tc.set_current_project_id(PROJECT); tc.set_current_agent_id(AGENT_ID)
    env = envelope("other:agent", role="forage", allowed=["limbs"], context={"q": 1})
    assert env["allowed_clamped"] == ["limbs"] and "limbs" not in env["allowed"] and env["role"] == "forage" and env["context"] == {"q": 1}
    # 수신 측은 처리 동안 집합을 세우고 끝나면 복원
    tc.set_allowed_nodes(None)
    with received({"allowed": ["sense", "self", "table"], "chain": ["a"]}):
        assert tc.get_allowed_nodes() == {"sense", "self", "table"}
        inner = envelope("x:y", allowed=["limbs", "others"])
        assert inner["allowed"] == ["self", "sense", "table"] or set(inner["allowed"]) <= {"sense", "self", "table"}   # 하위 위임은 넓히지 못한다
        assert "limbs" in inner["allowed_clamped"]
    assert tc.get_allowed_nodes() is None


def test_same_scope_delegate_carries_role_allowed_context(world):
    from routing_system import _delegate_unified
    tc.set_allowed_nodes(None)
    memory.create_task("parent9", "user@gui", "gui", "원요청")
    tc.set_current_task_id("parent9")
    result = _delegate_unified({"agent_id": AGENT_NAME, "message": "조사", "role": "forage", "allowed": ["sense"],
                                "context": {"query": "맛집", "need": 3}}, world.project_path)
    result = json.loads(result) if isinstance(result, str) else result   # same 접수는 도구 문자열 봉투
    assert result["accepted"] is True, result
    msg = world.runner.internal_messages[f"{PROJECT}:{AGENT_ID}"][0]
    assert msg["role"] == "forage" and "sense" in msg["allowed"] and msg["context"] == {"query": "맛집", "need": 3}
    assert "[context — 위임자가 준 구조화 맥락]" in msg["content"] and '"need": 3' in msg["content"]
    big = {"blob": "x" * (70 * 1024)}
    bad = _delegate_unified({"agent_id": AGENT_NAME, "message": "조사", "context": big}, world.project_path)
    bad = json.loads(bad) if isinstance(bad, str) else bad
    assert bad.get("success") is False and "64KB" in bad["error"]


def test_execution_rejects_nodes_outside_allowed_set():
    """완료 조건: 허용 집합 밖 낱말 호출이 거절된다 — 실행 관문이 스레드 allowed_nodes 를 읽는다."""
    from project_manager import ProjectManager
    from ibl_v2_entry import handle_request
    pp = str(ProjectManager().get_project_path("앱모드"))
    prev = tc.get_allowed_nodes()
    tc.set_allowed_nodes({"sense", "self", "table"})
    try:
        r = handle_request({"code": '[limbs:phone]{op: "info"}', "edition": 2, "inputs": {}, "declared_inputs": []}, pp, None)
        assert r["success"] is False, r
        r = handle_request({"code": '[self:time]{}', "edition": 2, "inputs": {}, "declared_inputs": []}, pp, None)
        assert r["success"] is True, r.get("error")
    finally:
        tc.set_allowed_nodes(prev)


def test_forage_route_is_thin_passage_over_delegation_scope(world, monkeypatch):
    """첫 소비자: /forage/chat 이 role=forage·allowed=[sense]·context=사냥판을 위임 봉투와 같은 계약(scoped)으로 세운다."""
    import api_system_ai as S
    seen = {}
    def fake_process(message, history=None, images=None, **kw):
        seen["allowed_now"] = tc.get_allowed_nodes()
        seen["force_role"] = kw.get("force_role"); seen["allowed_set"] = kw.get("allowed_set")
        return ("- [a](https://a.test) — x", None)
    monkeypatch.setattr(S, "process_system_ai_message", fake_process)
    monkeypatch.setattr(S, "load_system_ai_config", lambda: {"enabled": True, "apiKey": "k", "provider": "anthropic", "model": "m"})
    tc.set_allowed_nodes(None)
    out = S.forage_chat(S.ForageMessage(message="평택 맛집", count=5))
    assert out.response.startswith("- [a]")
    assert seen["force_role"] == "forage" and "sense" in seen["allowed_now"] and "limbs" not in seen["allowed_now"]
    assert seen["allowed_set"] == seen["allowed_now"] and tc.get_allowed_nodes() is None   # 같은 집합, 끝나면 복원


def test_cross_sync_timeout_keeps_task_running_and_settles_to_async(world, monkeypatch):
    from routing_system import _delegate_unified
    monkeypatch.setattr(world.dt, "SYNC_WAIT_SECONDS", 0.15)
    memory.create_task("parent3", "user@gui", "gui", "원요청")
    tc.set_current_task_id("parent3")
    result = _delegate_unified({"scope": "cross", "mode": "sync", "agent_id": f"{PROJECT}/{AGENT_ID}",
                                "message": "오래 걸리는 일"}, world.project_path)
    assert result["success"] is False and result["accepted"] is True and result["state"] == "running"
    assert "계속 실행 중" in result["error"]
    child = result["task_ref"]["task_id"]
    assert world.db.get_task(child)["status"] == "pending"      # 실패·취소로 바꾸지 않는다
    assert tc.did_call_agent() is True                          # 턴은 위임 대기로 남는다
    entry = json.loads(memory.get_task("parent3")["delegation_context"])["delegations"][0]
    assert entry["mode"] == "async"                             # 이후 보고는 평소대로 부모 러너에 전달
    recorded = memory.record_child_response("parent3", {"child_task_id": child, "response": "늦은 결과"})
    assert recorded["mode"] == "async" and recorded["remaining"] == 0


def test_same_sync_shares_the_async_accept_path(world):
    import routing_system
    from routing_system import _delegate_unified
    assert not hasattr(routing_system, "_agent_ask_sync"), "임시 AIAgent 동기 실행기는 은퇴했다"
    world.db.create_task("p_same", "user@gui", "gui", "원요청", "호출자")
    tc.set_current_project_id(PROJECT)
    tc.set_current_agent_id("caller")
    tc.set_current_agent_name("호출자")
    tc.set_current_task_id("p_same")
    _complete_child_later(world, PROJECT, "p_same", "동기 결과")
    result = _delegate_unified({"mode": "sync", "agent_id": AGENT_NAME, "message": "요약해줘",
                                "_prev_result": "앞 단계 값"}, world.project_path)
    assert result["success"] is True and result["response"] == "동기 결과", result
    msg = world.runner.sent[0]
    assert "앞 단계 값" in msg["content"] and msg["chain"] == [f"{PROJECT}:caller"]
    entry = json.loads(world.db.get_task("p_same")["delegation_context"])["delegations"][0]
    assert entry["mode"] == "sync" and entry["child_task_id"] == result["task_ref"]["task_id"]
    assert tc.did_call_agent() is False


def test_same_sync_without_task_context_still_has_a_task_to_wait_on(world):
    from routing_system import _delegate_unified
    tc.set_current_project_id(PROJECT)
    tc.set_current_agent_id("caller")
    world.dt.SYNC_WAIT_SECONDS = 0.1
    result = _delegate_unified({"mode": "sync", "agent_id": AGENT_NAME, "message": "x"}, world.project_path)
    assert result["accepted"] is True and result["task_ref"]["task_id"]
    row = world.db.get_task(result["task_ref"]["task_id"])
    assert row["requester_channel"] == "pipeline" and row["parent_task_id"] is None


def test_same_async_with_orphan_task_id_gets_its_own_task_row(world):
    """L28-1(긴문장 28회차): 호출 문맥의 task_id 에 부모 행이 없으면(앱 표면·훈련·직접 호출이 준 임의 id) 접수증이 그 id 를
    실어 [self:task] 가 unknown 이었다 — 이제 부모 없는 자식 행을 만들고 접수증·메시지·child_task_id 가 전부 그 행을 가리킨다."""
    from routing_system import _delegate_unified
    tc.set_current_project_id(PROJECT)
    tc.set_current_agent_id("caller")
    tc.set_current_task_id("LSI28_ghost")          # DB 에 없는 작업 id
    result = _delegate_unified({"mode": "async", "agent_id": AGENT_NAME, "message": "요약해줘"}, world.project_path)
    result = json.loads(result) if isinstance(result, str) else result   # same·async 는 접수증 JSON 문자열
    assert result["accepted"] is True, result
    tid = result["task_ref"]["task_id"]
    assert tid != "LSI28_ghost" and result["child_task_id"] == tid and result["task_id"] == tid
    row = world.db.get_task(tid)
    assert row and row["requester_channel"] == "pipeline" and row["parent_task_id"] is None
    assert world.runner.sent[0]["task_id"] == tid and world.runner.sent[0]["content"].startswith(f"[task:{tid}]")
    view = world.dt.task_status(result["task_ref"])
    assert view["state"] == "running" and view["task_ref"]["task_id"] == tid     # 접수증으로 회수된다


def test_same_async_refuses_when_no_task_row_can_be_made(world, monkeypatch):
    """행을 못 만들면 없는 작업의 접수증 대신 거절 — 메시지도 보내지 않는다."""
    import system_tools_delegate as S
    from routing_system import _delegate_unified
    tc.set_current_project_id(PROJECT)
    monkeypatch.setattr(S, "_create_standalone_task", lambda *a, **k: None)
    result = _delegate_unified({"mode": "async", "agent_id": AGENT_NAME, "message": "x"}, world.project_path)
    result = json.loads(result) if isinstance(result, str) else result
    assert result["success"] is False and result.get("error_type") == "delegation_task_row", result
    assert world.runner.sent == []


def test_workflow_outside_same_project_is_rejected_in_execution_and_contract(world):
    from routing_system import _delegate_unified
    for scope in ("cross", "system"):
        result = _delegate_unified({"mode": "workflow", "scope": scope, "agent_id": f"{PROJECT}/{AGENT_ID}",
                                    "message": "m", "steps": ["[self:now]{}"]}, world.project_path)
        assert result["success"] is False and result["error_type"] == "capability", result
    nodes = yaml.safe_load((Path(__file__).resolve().parents[1] / "data/ibl_nodes_src/others.yaml")
                           .read_text(encoding="utf-8"))
    contract = nodes["others"]["actions"]["delegate"]["callable_contract"]
    by_scope = {v["when"]["scope"]: v for v in contract["variants"] if set(v["when"]) == {"scope"}}
    assert by_scope["cross"]["enums"]["mode"] == ["async", "sync"]
    assert by_scope["system"]["enums"]["mode"] == ["async", "sync"]


def test_cycle_guard_rejects_ancestor_and_self(world):
    from routing_system import _delegate_unified
    memory.create_task("parent4", "user@gui", "gui", "원요청")
    tc.set_current_task_id("parent4")
    tc.set_delegation_chain(["system_ai", f"{PROJECT}:{AGENT_ID}"])
    result = _delegate_unified({"scope": "cross", "agent_id": f"{PROJECT}/{AGENT_ID}", "message": "되돌려"},
                               world.project_path)
    assert result["success"] is False and result["error_type"] == "delegation_cycle"
    assert memory.get_task("parent4")["pending_delegations"] == 0 and not world.runner.sent
    # 자기 자신에게 (same)
    tc.set_delegation_chain(None)
    tc.set_current_project_id(PROJECT)
    tc.set_current_agent_id(AGENT_ID)
    world.db.create_task("p_self", "user@gui", "gui", "원요청", AGENT_NAME)
    tc.set_current_task_id("p_self")
    raw = json.loads(_delegate_unified({"agent_id": AGENT_NAME, "message": "나에게"}, world.project_path))
    assert raw["success"] is False and raw["error_type"] == "delegation_cycle"
    assert tc.did_call_agent() is False


def test_received_envelope_sets_origin_and_chain_for_the_duration(world):
    tc.set_task_origin("user")
    with world.dt.received({"origin": "training", "chain": ["system_ai"]}):
        assert tc.in_rehearsal() is True and tc.get_delegation_chain() == ["system_ai"]
        # 자식이 다시 위임하면 사슬이 자란다
        env = world.dt.envelope("other:agent")
        assert env["origin"] == "training" and env["chain"] == ["system_ai"]
    assert tc.get_task_origin() == "user" and tc.get_delegation_chain() == []
    with world.dt.received({"content": "봉투 없는 메시지"}):
        assert tc.in_rehearsal() is False


def test_child_response_is_recorded_once_per_child(world):
    memory.create_task("parent5", "user@gui", "gui", "원요청")
    ctx = {"delegations": [{"child_task_id": "c1", "mode": "async"}, {"child_task_id": "c2", "mode": "async"}],
           "responses": []}
    memory.update_task_delegation("parent5", json.dumps(ctx), increment_pending=True)
    memory.update_task_delegation("parent5", json.dumps(ctx), increment_pending=True)
    first = memory.record_child_response("parent5", {"child_task_id": "c1", "response": "a"})
    again = memory.record_child_response("parent5", {"child_task_id": "c1", "response": "a (재전송)"})
    other = memory.record_child_response("parent5", {"child_task_id": "c2", "response": "b"})
    assert (first["remaining"], first["duplicate"]) == (1, False)
    assert (again["remaining"], again["duplicate"]) == (1, True)
    assert (other["remaining"], other["duplicate"]) == (0, False)
    responses = json.loads(memory.get_task("parent5")["delegation_context"])["responses"]
    assert [r["response"] for r in responses] == ["a", "b"]
    # 프로젝트 저장소도 같은 계약
    world.db.create_task("pp", "u", "gui", "o", "d")
    world.db.update_task_delegation("pp", json.dumps(ctx), increment_pending=True)
    assert world.db.record_child_response("pp", {"child_task_id": "c1", "response": "a"})["duplicate"] is False
    assert world.db.record_child_response("pp", {"child_task_id": "c1", "response": "a"})["duplicate"] is True


def test_full_result_preserved_and_projection_states(world):
    long_text = "x" * 1500
    memory.create_task("t_done", "u", "gui", "o")
    memory.complete_task("t_done", long_text)
    assert memory.get_task("t_done")["result"] == long_text
    world.db.create_task("p_done", "u", "gui", "o", AGENT_NAME)
    world.db.complete_task("p_done", long_text)
    assert world.db.get_task("p_done")["result"] == long_text

    view = world.dt.task_view("system", "t_done")
    assert view["state"] == "succeeded" and view["result"] == long_text and view["error"] is None
    assert view["status_url"] == "/system-ai/tasks/t_done" and view["run_id"]

    memory.create_task("t_fail", "u", "gui", "o")
    assert memory.fail_task("t_fail", "터짐") is True
    assert memory.fail_task("t_fail", "다시") is False            # 닫힌 작업은 덮지 않는다
    failed = world.dt.task_view("system", "t_fail")
    assert failed["state"] == "failed" and failed["error"] == "터짐" and failed["result"] is None

    memory.create_task("t_wait", "u", "gui", "o")
    memory.update_task_delegation("t_wait", json.dumps({"delegations": [{"child_task_id": "k", "mode": "sync"}]}))
    waiting = world.dt.task_view("system", "t_wait")
    assert waiting["state"] == "waiting_children" and waiting["children"] == [
        {"child_task_id": "k", "delegated_to": None, "mode": "sync", "responded": False}]
    assert world.dt.task_view("system", "없는작업") is None
    assert world.dt.task_view("없는프로젝트", "x") is None


class _NoEpisode:
    @staticmethod
    def start_episode(*a, **k):
        return None

    @staticmethod
    def end_episode(*a, **k):
        return None


def test_system_ai_background_receipt_carries_task_and_records_failure(world, monkeypatch):
    import api_system_ai
    import episode_logger
    monkeypatch.setattr(episode_logger, "EpisodeLogger", _NoEpisode)
    monkeypatch.setattr(api_system_ai, "load_system_ai_config",
                        lambda: {"enabled": True, "apiKey": "k", "provider": "anthropic", "model": "m"})
    monkeypatch.setattr(api_system_ai, "init_all_docs", lambda: None)
    monkeypatch.setattr(api_system_ai, "_docs_initialized", True)

    def explode(**kwargs):
        raise RuntimeError("모델 호출 실패 sk-abcdefghijklmnopqrstuvwxyz0123")
    monkeypatch.setattr(api_system_ai, "process_system_ai_message", explode)
    monkeypatch.setattr(api_system_ai.threading, "Thread",
                        lambda target, **kw: SimpleNamespace(start=target))
    receipt = api_system_ai.chat_with_system_ai(api_system_ai.ChatMessage(message="해줘", background=True))
    assert receipt.response == "작업을 시작했습니다." and receipt.task_id and receipt.state == "queued"
    assert receipt.status_url == f"/system-ai/tasks/{receipt.task_id}"
    view = api_system_ai.get_system_ai_task(receipt.task_id)
    assert view["state"] == "failed" and "모델 호출 실패" in view["error"]
    assert "sk-abcdefghijklmnopqrstuvwxyz0123" not in view["error"]   # 비밀 마스킹
    assert view["task_ref"] == {"kind": "delegation", "owner": "system", "task_id": receipt.task_id}
    # 옛 클라이언트(메시지 폴링)도 실패를 본다
    rows = memory.get_recent_conversations(limit=5)
    assert any(r["role"] == "assistant" and r["content"].startswith("[실패]") for r in rows)
    with pytest.raises(api_system_ai.HTTPException) as missing:
        api_system_ai.get_system_ai_task("task_없음")
    assert missing.value.status_code == 404
    # 동기 경로의 예외도 작업에 남는다
    with pytest.raises(api_system_ai.HTTPException):
        api_system_ai.chat_with_system_ai(api_system_ai.ChatMessage(message="해줘"))
    with sqlite3.connect(world.tmp / "system.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM tasks WHERE status='failed'").fetchone()[0] == 2


def test_system_ai_background_success_is_visible_as_succeeded_with_full_result(world, monkeypatch):
    import api_system_ai
    import episode_logger
    monkeypatch.setattr(episode_logger, "EpisodeLogger", _NoEpisode)
    monkeypatch.setattr(api_system_ai, "load_system_ai_config",
                        lambda: {"enabled": True, "apiKey": "k", "provider": "anthropic", "model": "m"})
    monkeypatch.setattr(api_system_ai, "_docs_initialized", True)
    long_answer = "답 " * 600
    monkeypatch.setattr(api_system_ai, "process_system_ai_message", lambda **kw: (long_answer, []))
    monkeypatch.setattr(api_system_ai.threading, "Thread",
                        lambda target, **kw: SimpleNamespace(start=target))
    receipt = api_system_ai.chat_with_system_ai(api_system_ai.ChatMessage(message="해줘", background=True))
    view = api_system_ai.get_system_ai_task(receipt.task_id, wait=1)
    assert view["state"] == "succeeded" and view["result"] == long_answer
    assert tc.get_current_task_id() is None


def test_agent_task_route_checks_stored_owner(world, monkeypatch):
    import api_agents
    monkeypatch.setattr(api_agents, "project_manager",
                        SimpleNamespace(get_project_path=lambda pid: Path(world.project_path)))
    monkeypatch.setattr(api_agents, "agent_runners", {})
    world.db.create_task("t_agent", "user@gui", "gui", "명령", AGENT_NAME)
    world.db.complete_task("t_agent", "에이전트 결과")
    view = api_agents.get_agent_task(PROJECT, AGENT_ID, "t_agent")
    assert view["state"] == "succeeded" and view["result"] == "에이전트 결과"
    assert view["status_url"] == f"/projects/{PROJECT}/agents/{AGENT_ID}/tasks/t_agent"
    with pytest.raises(api_agents.HTTPException) as other:
        api_agents.get_agent_task(PROJECT, "다른에이전트", "t_agent")
    assert other.value.status_code == 404


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))


def test_turn_that_ends_in_error_closes_the_delegated_task_as_failed(world, monkeypatch):
    """긴문장 27회차 L27-6: 응답 없이 오류로 끝난 턴이 "AI 응답 생성 실패: …" 글을 결과로 succeeded 가 됐다."""
    import agent_pipeline
    import system_ai_core as core
    import system_ai_runner as runner_mod
    monkeypatch.setattr(core, "get_system_ai_runner", lambda: SimpleNamespace(
        cognitive_stream=lambda *a, **k: iter(()), ai=SimpleNamespace(get_last_tool_images=lambda: [])))
    monkeypatch.setattr(agent_pipeline, "drain_stream", lambda stream: {"final": "", "error": "AI가 초기화되지 않았습니다."})
    # 채팅 표면은 옛 동작(글로 보여 준다), 작업을 닫는 호출자는 사실 신호를 받는다
    assert core.process_system_ai_message("요약해줘")[0] == "AI 응답 생성 실패: AI가 초기화되지 않았습니다."
    with pytest.raises(core.SystemAITurnFailed, match="초기화"):
        core.process_system_ai_message("요약해줘", raise_on_failure=True)

    monkeypatch.setattr(runner_mod, "save_conversation", lambda *a, **k: None)
    fake = SimpleNamespace(_send_to_gui=lambda *a, **k: None)
    memory.create_task("t_turn_fail", "u", "api", "o")
    runner_mod.SystemAIRunner._finalize_task(fake, "t_turn_fail", "AI 응답 생성 실패: AI가 초기화되지 않았습니다.", failed=True)
    view = world.dt.task_view("system", "t_turn_fail")
    assert view["state"] == "failed" and "초기화" in view["error"] and view["result"] is None
    memory.create_task("t_turn_ok", "u", "api", "o")
    runner_mod.SystemAIRunner._finalize_task(fake, "t_turn_ok", "요약입니다")
    assert world.dt.task_view("system", "t_turn_ok")["state"] == "succeeded"


@pytest.mark.parametrize('owner', ['system', PROJECT])
def test_durable_reports_survive_queue_loss_and_ack_only_after_parent(world, owner):
    from steer_inbox import turn_hold
    import runtime_work
    dt = world.dt
    agent = 'system_ai' if owner == 'system' else AGENT_NAME
    db = memory if owner == 'system' else world.db
    if owner == 'system':
        db.create_task('outbox', 'u', 'gui', 'request')
    else:
        db.create_task('outbox', 'u', 'gui', 'request', agent)
    context = {'delegations': [{'child_task_id': 'c', 'mode': 'async'}], 'responses': []}
    db.update_task_delegation('outbox', json.dumps(context), increment_pending=True)
    response = {'child_task_id': 'c', 'response': 'durable value', 'delivery_pending': True,
                'delivery_envelope': {'origin': 'training'}, 'failed': True}
    db.record_child_response('outbox', response)
    assert db.record_child_response('outbox', response)['duplicate']
    with turn_hold('outbox'):
        assert dt.recover_reports(owner, agent) == []
    messages = dt.recover_reports(owner, agent)
    assert len(messages) == 1 and messages[0]['origin'] == 'training'
    assert '실패' in messages[0]['content']
    # Queue is thrown away as at a restart; durable outbox still yields it.
    messages = dt.recover_reports(owner, agent)
    assert dt.recover_reports(owner, agent, queued=['outbox']) == []
    for msg in runtime_work.message_stream(lambda: messages.pop(0) if messages else None):
        assert dt.recover_reports(owner, agent)  # not acked while processing
    assert dt.recover_reports(owner, agent) == []


@pytest.mark.parametrize('owner', ['system', PROJECT])
def test_task_cancellation_is_request_until_execution_confirms(world, monkeypatch, owner):
    import task_receipts as T
    monkeypatch.setenv('INDIEBIZ_RUNTIME_STATE_DIR', str(world.tmp))
    db = memory if owner == 'system' else world.db
    if owner == 'system':
        db.create_task('cancel-one', 'u', 'gui', 'request')
    else:
        db.create_task('cancel-one', 'u', 'gui', 'request', AGENT_NAME)
    ref = T.ref('delegation', 'cancel-one', owner)
    assert world.dt.task_cancel(ref)['state'] == T.CANCEL_REQUESTED
    world.dt.confirm_task_cancelled(owner, 'cancel-one')
    assert world.dt.task_status(ref)['state'] == T.CANCELLED
    assert world.dt.task_cancel(T.ref('delegation', 'absent', owner))['state'] == T.UNKNOWN


@pytest.mark.parametrize('owner', ['system', PROJECT])
def test_runner_without_ai_does_not_ack_durable_report(world, monkeypatch, owner):
    import runtime_work
    calls = []
    message = {'task_id': 'pending', 'content': 'result', '_delivery_ack': lambda: calls.append('acked')}
    monkeypatch.setattr(world.dt, 'recover_reports', lambda *a: [message])
    if owner == 'system':
        from system_ai_runner import SystemAIRunner
        monkeypatch.setattr(SystemAIRunner, 'internal_messages', runtime_work.WorkMessages())
        monkeypatch.setattr(SystemAIRunner, 'held_reports', [])
        runner = SystemAIRunner.__new__(SystemAIRunner)
        runner.ai = None
        runner._check_internal_messages()
    else:
        from agent_communication import AgentCommunicationMixin
        runner = AgentCommunicationMixin()
        runner.config, runner.project_id = {'name': AGENT_NAME}, PROJECT
        runner.registry_key, runner.ai = 'fixture-key', None
        runner._check_internal_messages()
    assert calls == []
