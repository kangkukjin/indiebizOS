"""최근 여행 턴의 정지·출처·수정 왕복 재현. 실제 모델/외부 API/사용자 DB를 건드리지 않는다."""
import json
import sys
import time
from types import SimpleNamespace

import pytest
import boot_paths  # noqa: F401
from test_conscious_supervisor import supervisor, manager_tool  # noqa: F401
from test_memory_tree import mem  # noqa: F401
from test_supervisor_episode_repairs import memory_harness  # noqa: F401


@pytest.mark.parametrize("message", ["직행이면 점심을 어디서 먹을까?", "파일은 어디에 있나?"])
def test_recall_never_opens_user_disks(message, monkeypatch):
    from cognitive_recall import CognitiveRecallMixin
    import ibl_usage_rag
    import file_index
    monkeypatch.setattr(file_index, "disk_skeleton", lambda *a, **k: pytest.fail("회상 중 디스크 탐색"))
    monkeypatch.setattr(ibl_usage_rag, "build_execution_memory", lambda *a: ("reference", .5, "code"))
    runner = CognitiveRecallMixin()
    runner.config = {}
    for name in ("_memory_map_scent", "_execution_map_scent", "_limb_presence_scent", "_pending_repair_scent"):
        monkeypatch.setattr(runner, name, lambda: "map")
    monkeypatch.setattr(runner, "_decision_scent", lambda message: "decision")
    text, score, code = runner._build_execution_memory(message)
    assert "reference" in text and "map" in text and score == .5 and code == "code"
    assert "disk_skeleton" not in text


def test_pre_model_wait_is_visible_without_another_model(supervisor, monkeypatch):
    monkeypatch.setattr(supervisor, "review", lambda *a: pytest.fail("회상 정지에 새 AI 호출"))
    with supervisor.preparation("memory_map"):
        start = supervisor.preparing["started"]
        supervisor.tick(start + 11)
        supervisor.tick(start + 50)
        assert supervisor.state()["preparation"]["stage"] == "memory_map"
    rows = [json.loads(s) for s in (supervisor.store.directory / "events.jsonl").read_text().splitlines()]
    assert sum(r["kind"] == "recall.stalled" for r in rows) == 1
    assert rows[-1]["kind"] == "recall.finished" and supervisor.preparing is None


def test_hotel_fact_beyond_prefix_remains_discoverable(mem, monkeypatch):
    db, tree, project, agent, path = mem
    content = "다른 지역의 숙소 선호. " * 60 + "체스터톤스 호텔 예약함, 투룸 디럭스 로프트"
    mid = db.save(project, agent, content, "호텔 예약", "사용자선호", node="여행")
    monkeypatch.setattr(db, "_search_semantic", lambda *a, **k: [])
    row = db.search(project, agent, "체스터톤스 호텔 예약")[0]
    assert row["id"] == mid and "체스터톤스 호텔 예약함" in row["preview"]
    assert row["preview_truncated"] and row["content_chars"] == len(content)
    assert row["provenance"]["status"] == "unattributed"
    recalled = tree.recall(path, "여행")
    assert json.dumps(recalled, ensure_ascii=False).count("체스터톤스 호텔 예약함") == 1
    assert recalled["items"][0]["provenance"]["status"] == "unattributed"


def test_source_role_survives_recall_and_projection(mem):
    from ibl_envelope import _preview_currency
    db, tree, project, agent, path = mem
    source = json.dumps({"episode_id": 3507, "recorded_at": "2026-09-11", "evidence": [
        {"role": "assistant", "text": "이번 여행은 세 명"}]})
    db.save(project, agent, "이번 여행은 세 명", "여행", "작업기록", source_ref=source, node="여행")
    out = tree.recall(path, "여행")
    assert out["items"][0]["provenance"]["status"] == "assistant_record"
    projected = _preview_currency(out, {"rows": 1, "min_chars": 1, "prose_chars": 20}, 9000)
    assert projected["items"][0]["provenance"]["status"] == "assistant_record"


def test_questions_do_not_call_memory_extractor(memory_harness, monkeypatch):
    monkeypatch.setattr("consciousness_agent.oneshot_ai_call", lambda *a, **k: pytest.fail("질문뿐인 턴의 증류"))
    memory_harness.runner._distill_deep_memory("다음주 여행은 기억하고 있나?", "아내와 어머니가 가는 여행입니다")
    assert not memory_harness.saved and not memory_harness.updates


def test_user_correction_can_be_retained_but_question_and_assistant_cannot():
    from memory_evidence import durable_source_units, grounded_fact, source_units
    units = durable_source_units("이번 여행은 나와 두 형님 그리고 어머니가 가. 점심은 어디서 먹을까?")
    fact = {"source_ids": [1], "retention": "user_fact", "future_use": "향후 사용자 상황에 맞춘 계획"}
    assert grounded_fact(fact, units, "{}", durable_only=True)["content"] == units[0]["text"]
    assert grounded_fact({**fact, "source_ids": [2]}, units, "{}", durable_only=True) is None
    mixed = source_units("기억하나?", "아내와 어머니가 간다")
    assert grounded_fact({**fact, "source_ids": [2]}, mixed, "{}", durable_only=True) is None


def test_block_id_does_not_return_the_whole_response(supervisor):
    supervisor.store.put_response("앞\n\n고칠 문장\n\n뒤" + "지도" * 3000)
    block = next(b for b in supervisor.store.blocks if "고칠 문장" in b["text"])
    page = manager_tool(supervisor, {"op": "response", "id": block["id"]})["result"]
    assert page["blocks"] == [block] and page["next_offset"] is None
    assert len(json.dumps(page, ensure_ascii=False)) < 500


def test_changed_review_reuses_read_receipts_and_invalidates_new_criteria(supervisor):
    from supervisor_review import response_review_page
    supervisor.store.put_response("앞\n\n틀린 값\n\n지도" + "좌표" * 1000)
    first = response_review_page(supervisor)
    old = next(b for b in supervisor.store.blocks if "틀린 값" in b["text"])
    supervisor.store.patch(1, [{"id": old["id"], "hash": old["hash"], "old_string": "틀린 값", "new_string": "맞는 값"}])
    second = response_review_page(supervisor)
    assert second["mode"] == "changed_blocks" and len(second["blocks"]) == 1
    assert "좌표" not in json.dumps(second, ensure_ascii=False) and supervisor.store.fully_read()
    assert len(json.dumps(second, ensure_ascii=False)) < len(json.dumps(first, ensure_ascii=False)) / 3
    supervisor.framing = {"achievement_criteria": "새 출처 기준"}
    assert response_review_page(supervisor)["mode"] == "full_read_required"


def test_legacy_local_scope_and_small_repair_do_not_resume_large_session(supervisor):
    from supervisor_runtime import parse_decision
    from supervisor_handoff import repair_execution
    decision = parse_decision(json.dumps({"status": "REWORK", "reason": "산술 오류",
        "instruction": 'repair_scope="local". 한 문장만 수정'}))
    assert decision["repair_scope"] == "local"
    provider = SimpleNamespace(system_prompt="실행 규약" * 10000, tools=[{"name": "execute_ibl"}],
                               _last_prompt_usage={"input": 125000, "cache_read": 124000},
                               disable_session_persistence=False)
    supervisor.runner.ai._provider = provider
    supervisor.store.put_response("수정할 응답")
    with repair_execution(supervisor, decision, [{"content": "큰 세션"}]) as (ai, history, packet):
        assert history == [] and ai._provider.disable_session_persistence
        assert len(ai.system_prompt) < 1500 and [t["name"] for t in ai.tools] == ["supervision"]
        assert packet["execution_rules"]["chars"] == 50000
    assert provider.system_prompt == "실행 규약" * 10000 and not provider.disable_session_persistence


def test_wrong_first_repair_is_rejected_before_another_final_review(supervisor):
    from quantity_checks import calculate
    assert calculate("a+b", {"a": 285, "b": 45}, "minutes")["duration"] == "5시간 30분"
    assert calculate("a+b+c+d", {"a": 285, "b": 45, "c": 60, "d": 30}, "minutes")["value"] == 420
    supervisor.store.put_response("차 안 시간이 5시간 5분입니다.")
    b = supervisor.store.blocks[0]
    wrong = "주행만 4시간 45분(실측 285분), 휴식 45분까지 더하면 차 안 시간이 5시간 15분입니다."
    with pytest.raises(ValueError, match="시간 합산 오류"):
        supervisor.store.patch(1, [{"id": b["id"], "hash": b["hash"], "text": wrong}])
    assert supervisor.store.version == 1
    correct = wrong.replace("5시간 15분", "5시간 30분")
    supervisor.store.patch(1, [{"id": b["id"], "hash": b["hash"], "text": correct}])
    assert supervisor.store.text == correct


@pytest.mark.parametrize("expr", ["2**100000000", "'x'*100000000", "__import__('os')", "1/0"])
def test_calculator_bounds_resource_use(expr):
    from quantity_checks import calculate
    with pytest.raises((ValueError, ZeroDivisionError)):
        calculate(expr)


def test_context_update_cannot_start_weather_or_route_queries(supervisor, monkeypatch):
    from turn_scope import context_program
    nodes = {"nodes": {"self": {"actions": {"memory": {"context_update_ops": ["read", "recall", "save"]}}}}}
    monkeypatch.setattr("ibl_access.load_nodes_raw", lambda: nodes)
    supervisor.request_intent = "context_update"
    assert context_program('[self:memory]{op:"recall",node:"여행"}')
    assert not context_program('[self:memory]{op:"delete",memory_id:1}')
    out = supervisor.run_tool("execute_ibl", {"code": '[sense:weather]{city:"속초"}'}, lambda: pytest.fail("요청 밖 조회"))
    assert json.loads(out)["not_executed"]
    assert supervisor.run_tool("execute_ibl", {"code": '[self:memory]{op:"recall",node:"여행"}'}, lambda: "기억") == "기억"


def test_context_classification_uses_existing_single_call(monkeypatch):
    from cognitive_consciousness import CognitiveConsciousnessMixin
    calls = []
    monkeypatch.setattr("consciousness_agent.oneshot_ai_call", lambda *a, **k: calls.append(a) or "CONTEXT_UPDATE")
    assert CognitiveConsciousnessMixin()._classify_request("숙소 예약되었다.") == "CONTEXT_UPDATE"
    assert len(calls) == 1


def test_process_tree_exit_race_is_not_unknown(monkeypatch):
    import restart_process as mod
    import psutil
    monkeypatch.setattr(mod, "alive", lambda ident: True)
    def gone(pid):
        raise psutil.NoSuchProcess(pid)
    monkeypatch.setattr(mod.psutil, "Process", gone)
    assert mod.tree({"pid": 10, "born": 1}) == []


def test_process_tree_permission_error_remains_unknown(monkeypatch):
    import restart_process as mod
    import psutil
    monkeypatch.setattr(mod, "alive", lambda ident: True)
    def denied(pid):
        raise psutil.AccessDenied(pid)
    monkeypatch.setattr(mod.psutil, "Process", denied)
    with pytest.raises(psutil.AccessDenied):
        mod.tree({"pid": 10, "born": 1})


def test_lazy_agent_mailbox_is_a_service_not_the_starting_turn(monkeypatch):
    import threading
    import runtime_work as work
    from agent_runner import AgentRunner
    reg = work.WorkRegistry("fixture")
    reg.gate("ACTIVE")
    monkeypatch.setattr(work, "_registry", reg)
    seen = []
    class Thread:
        def __init__(self, **kw):
            pass
        def start(self):
            seen.append(work.parent_token())
    runner = AgentRunner.__new__(AgentRunner)
    runner.running = False
    runner.cancel_event = threading.Event()
    runner.config = {"name": "fixture"}
    monkeypatch.setattr(runner, "_init_ai", lambda: None)
    monkeypatch.setattr(threading, "Thread", Thread)
    monkeypatch.setattr("node_registry.invalidate_agent_cache", lambda: None)
    with work.scope("start request"):
        parent = work.parent_token()
        runner.start()
        assert work.parent_token() == parent
    assert seen == [None] and reg.snapshot()["active_children"] == 0


def test_model_monitor_is_service_but_load_keeps_request_owner(monkeypatch):
    import runtime_work as work
    from ibl_usage_db import IBLUsageDB
    reg = work.WorkRegistry("fixture")
    reg.gate("ACTIVE")
    monkeypatch.setattr(work, "_registry", reg)
    monkeypatch.setattr(IBLUsageDB, "_model", None)
    monkeypatch.setattr(IBLUsageDB, "_model_loading", False)
    monkeypatch.setattr(IBLUsageDB, "_model_load_attempted", False)
    monkeypatch.setattr(IBLUsageDB, "_resolve_model_dir", classmethod(lambda cls: "fixture"))
    seen = []
    def constructor(path):
        seen.append(work.parent_token())
        assert reg.snapshot()["active_roots"] == 1
        return object()
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=constructor))
    with work.scope("finite model load"):
        parent = work.parent_token()
        assert IBLUsageDB._load_model_sync()
        assert work.parent_token() == parent
    assert seen == [None] and reg.snapshot()["active_roots"] == 0


def test_managed_generation_clears_legacy_identity(tmp_path):
    from restart_controller import Controller
    from test_restart_controller import Adapter
    ctl = Controller(tmp_path, tmp_path, adapter=Adapter())
    ctl.save(legacy=True, serving_worker={"pid": 10}, legacy_keeper={"pid": 11})
    ctl.start_generation({"digest": "fixture"})
    assert not ctl.state["legacy"]
    assert ctl.state["serving_worker"] is None and ctl.state["legacy_keeper"] is None


def test_slow_directory_request_does_not_block_health(tmp_path, monkeypatch):
    import asyncio
    import os
    import threading
    import httpx
    from fastapi import FastAPI
    import api_pcmanager
    app = FastAPI()
    app.include_router(api_pcmanager.router)
    @app.get("/fixture-health")
    async def health():
        return {"ready": True}
    entered, release = threading.Event(), threading.Event()
    scan = os.scandir
    def slow(path):
        if str(path) == str(tmp_path):
            entered.set()
            if not release.wait(2):
                raise TimeoutError("fixture release missing")
        return scan(path)
    monkeypatch.setattr(os, "scandir", slow)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
            task = asyncio.create_task(client.get(api_pcmanager.router.prefix + "/list", params={"path": str(tmp_path)}))
            try:
                assert await asyncio.to_thread(entered.wait, 1)
                response = await asyncio.wait_for(client.get("/fixture-health"), .5)
                assert response.json() == {"ready": True} and not task.done()
            finally:
                release.set()
                response = await task
            assert response.status_code == 200
    asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
