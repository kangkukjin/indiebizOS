"""3364/3377에서 드러난 원인에 대한 행동 회귀. 모델 네트워크 호출 없음."""
import importlib.util
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import boot_paths  # noqa: F401
from test_conscious_supervisor import supervisor, verdict, finish  # noqa: F401
from supervision_store import TurnStore, digest


def script_module(name):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("test_recipe_" + name, root / "data/scripts" / (name + ".py"))
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def test_soft_allocation_never_cancels_an_inflight_judgment(supervisor):
    supervisor.call_deadline = time.monotonic() + 60
    supervisor.usage["input"] = 600000
    supervisor.call_usage = {"input": 32479, "output": 2}
    supervisor.phase_usage["plan"] = {"input": 253964}
    assert not supervisor.call_cancelled()
    supervisor.call_usage = {}
    assert not supervisor.model_admitted("plan")
    assert supervisor.model_admitted("review")
    assert supervisor.model_admitted("final")
    supervisor.cancel_check = lambda: True
    assert supervisor.call_cancelled() and supervisor.call_stop["kind"] == "cancelled"


def test_hard_quota_does_not_start_repair_without_recheck(supervisor, monkeypatch):
    supervisor.config["budget_mode"] = "hard"
    supervisor.usage["input"] = 290000
    supervisor.final_usage["input"] = 70000
    monkeypatch.setattr("supervisor_runtime.invoke", lambda c, *a, **kw: verdict(c, "REWORK", instruction="fix"))
    supervisor.runner.ai.process_message_stream = lambda *a, **kw: pytest.fail("재검수 없는 보완")
    finish(supervisor, "candidate")
    assert "repair.skipped" in (supervisor.store.directory / "events.jsonl").read_text()


def test_unrelated_crawl_does_not_discard_failure_guidance(supervisor, monkeypatch):
    def fail():
        key = supervisor._start("inspect", {"url": "broken"})
        supervisor._finish(key, {"error": "timeout"}, True)
    fail(); fail()
    def invoke(c, *a, **kw):
        key = c._start("inspect", {"url": "unrelated"})
        c._finish(key, "new material")
        c.progress("unrelated crawl completed")
        return verdict(c, "REWORK", instruction="broken 주소의 대체 출처 사용")
    monkeypatch.setattr("supervisor_runtime.invoke", invoke)
    supervisor.review("repeated_failure")
    notice = supervisor.boundary()
    assert notice and notice["instruction"].startswith("broken")


def test_actual_recovery_invalidates_failure_guidance(supervisor, monkeypatch):
    for _ in range(2):
        key = supervisor._start("inspect", {"url": "broken"})
        supervisor._finish(key, {"error": "timeout"}, True)
    monkeypatch.setattr("supervisor_runtime.invoke", lambda c, *a, **kw: verdict(c, "REWORK", instruction="retry"))
    supervisor.review("repeated_failure")
    key = supervisor._start("inspect", {"url": "broken"})
    supervisor._finish(key, "recovered")
    assert supervisor.boundary() is None


def test_execution_phase_is_not_changed_by_concurrent_observation(supervisor):
    supervisor.phase = "review"
    row = supervisor.log("tool.started", role="execution")
    assert row["phase"] == "execute"


def test_substring_patch_preserves_paragraph_ids_and_is_atomic(tmp_path):
    store = TurnStore(tmp_path)
    original = "첫 문단 그대로.\n\n농업 외 유일한 사례.\n\n마지막 그대로."
    store.put_response(original)
    blocks = store.read_response()["blocks"]
    target = next(b for b in blocks if "유일한" in b["text"])
    patch = {"id": target["id"], "hash": target["hash"], "old_string": "유일한", "new_string": "추가 확인된"}
    store.patch(1, [patch])
    assert store.text == original.replace("유일한", "추가 확인된")
    assert store.blocks[0] == blocks[0] and store.blocks[-1] == blocks[-1]
    before = store.text
    with pytest.raises(ValueError):
        store.patch(1, [patch])
    assert store.text == before
    last = store.blocks[-1]
    with pytest.raises(ValueError):
        store.patch(2, [{"id": last["id"], "hash": last["hash"], "text": "new"}, patch])
    assert store.text == before


def test_patch_growth_remains_pageable(tmp_path):
    store = TurnStore(tmp_path)
    store.put_response("short")
    b = store.blocks[0]
    store.patch(1, [{"id": b["id"], "hash": b["hash"], "text": "한" * 8000}])
    assert all(len(b["text"]) <= 2000 for b in store.blocks)
    assert store.text == "한" * 8000


def test_verbose_result_can_be_recovered_without_rerunning(tmp_path, monkeypatch):
    import model_result_view as view
    store = TurnStore(tmp_path)
    monkeypatch.setattr(view, "evidence_store", lambda: store)
    body = {"items": [{"text": "data" * 100, "index": i} for i in range(60)]}
    raw = {"success": True, "results": [{"step": 1, "result": json.dumps(body)}], "final_result": json.dumps(body)}
    out = view.project_result(raw, verbose=True)
    assert len(json.dumps(out)) < len(json.dumps(raw)) / 2
    ref = out["result_ref"]
    page = view.read_result({"id": ref["id"], "limit": 24000})
    text = page["text"]
    while page["next_offset"] is not None:
        page = view.read_result({"id": ref["id"], "offset": page["next_offset"], "limit": 24000})
        text += page["text"]
    assert json.loads(text) == raw


def test_action_discovery_checks_permissions_and_keeps_listen():
    from model_result_view import describe_actions
    out = describe_actions(["sense:listen"], ["sense"])
    assert "path" in json.dumps(out) and out["executed"] is False
    denied = describe_actions(["engines:search"], ["sense"])
    assert denied["actions"][0].get("error")


def test_display_policy_controls_model_copy_and_keeps_structured_diagnostics(tmp_path, monkeypatch):
    import model_result_view as view
    import ibl_retyping
    store = TurnStore(tmp_path / "evidence")
    monkeypatch.setattr(view, "evidence_store", lambda: store)
    policy = tmp_path / "lifecycle.yaml"
    policy.write_text("envelope_preview:\n  rows: 2\n  min_chars: 10\n  prose_chars: 80\n  step_chars: 20\n")
    monkeypatch.setattr(ibl_retyping, "_POLICY_PATH", str(policy))
    monkeypatch.setattr(ibl_retyping, "_block_cache", {})
    original = {"success": False, "results": [{"step": 7, "type": "action", "error": "오류" * 500}],
                "final_result": {"items": [{"text": "긴 산문" * 50} for _ in range(5)]}}
    out = view.project_result(original)
    assert len(out["final_result"]["items"]) == 2
    assert out["final_result"]["_preview"]["total"] == 5
    assert out["results"][0]["step"] == 7 and out["results"][0]["type"] == "action"
    assert "result_ref" in out["results"][0]["error"]
    assert store.read_evidence(out["result_ref"]["id"], 0, None)["text"] == json.dumps(
        original, ensure_ascii=False, indent=2)


def test_compact_environment_preserves_available_capabilities():
    from ibl_access import build_environment
    full = build_environment(expose_idioms=False)
    compact = build_environment(expose_idioms=False, compact=True)
    assert len(compact) < len(full) * .65
    assert "sense:listen" in compact and "describe" in compact


def test_research_quota_requires_user_provenance():
    from supervisor_handoff import criteria_contract
    result = criteria_contract("적용 사례를 찾아줘", {"criteria": [{"text": "3개 직업", "user_quote": "3개 직업"}]})
    assert result["criteria"][0]["source"] == "proposed"
    result = criteria_contract("3개 직업의 사례를 찾아줘", {"criteria": [{"text": "3개 직업", "user_quote": "3개 직업"}]})
    assert result["criteria"][0]["source"] == "user"


def test_verification_reuse_invalidates_dependency_or_criteria(tmp_path):
    from verification_cache import VerificationCache
    file, source = tmp_path / "report", tmp_path / "source"
    file.write_text("보고서"); source.write_text("원문")
    store = TurnStore(tmp_path / "evidence")
    key = store.evidence("본문 검토")['id']
    cache = VerificationCache()
    cache.remember([{"path": str(file), "status": "passed", "coverage": "whole text", "tool_version": "v1",
                     "dependencies": [str(source)], "evidence_ids": [key]}], "criteria1", store)
    assert len(cache.valid("criteria1")) == 1
    assert not cache.valid("criteria2")
    source.write_text("바뀐 원문")
    assert not cache.valid("criteria1")


def test_bounded_repair_preserves_owner_provider_and_task_resources(supervisor):
    from supervisor_handoff import repair_execution
    provider = SimpleNamespace(system_prompt="짧은 공통 규칙", _last_prompt_usage={"input": 380924, "cache_read": 370000},
                               tools=["tool"], no_tools=False, disable_session_persistence=False)
    supervisor.runner.ai._provider = provider
    supervisor.store.put_response("stored")
    with repair_execution(supervisor, {"repair_scope": "local", "instruction": "문장 수정"}, [{"content": "old"}]) as (ai, history, state):
        assert ai is not supervisor.runner.ai and ai._provider is not provider
        assert ai._provider.tools == ["tool"] and not ai._provider.no_tools
        assert ai._provider.disable_session_persistence and history == []
        assert state["goal"] == supervisor.message and state["response"]["hash"] == digest("stored")
    assert not provider.disable_session_persistence


def test_all_execution_invocations_count_including_repairs():
    from model_call_context import count_execution_rounds
    rows = [{"event": "round", "role": "execution", "round": n} for count in (17, 11, 10) for n in range(1, count + 1)]
    assert count_execution_rounds(rows) == 38
    rows += [{"event": "round", "role": "oneshot:slide", "round": 1}]
    assert count_execution_rounds(rows) == 38


def test_oneshot_contract_is_explicit_and_parent_accounting_is_separate(monkeypatch):
    import episode_logger as el
    from providers.base import BaseProvider
    from consciousness_agent import call_oneshot_provider
    events, roles = [], []
    monkeypatch.setattr(el, "record_trajectory_event", lambda kind, data: events.append((kind, data)))
    class Fake(BaseProvider):
        def init_client(self):
            return True
        def process_message(self, message, **kwargs):
            from model_call_context import fields
            roles.append(fields())
            if message == "parent":
                child = Fake("", "test-model", "prompt", [])
                call_oneshot_provider(child, "child", role="slide")
            else:
                assert self.no_tools and self.disable_session_persistence and not self.tools
                assert kwargs["history"] == [] and kwargs["execute_tool"] is None
            self._notify_round(1, 30)
            self.metrics.record_usage(1, {"prompt_tokens": 20, "completion_tokens": 2})
            return "ok"
    provider = Fake("", "test-model", "prompt", [])
    provider.no_tools = False
    provider.process_message("parent")
    assert len(roles) == 2 and roles[1]["parent_call_id"] == roles[0]["call_id"]
    assert roles[1]["role"] == "oneshot:slide" and provider.no_tools is False
    assert len([e for e in events if e[0] == "model.usage"]) == 2
    inputs = [data for kind, data in events if kind == "model.input"]
    assert len(inputs) == 2 and {row["message_chars"] for row in inputs} == {5, 6}
    assert {row["call_id"] for row in inputs} == {row["call_id"] for row in roles}


def test_input_shape_counts_once_and_does_not_copy_image_or_message(monkeypatch):
    from providers.base import BaseProvider
    import episode_logger as el
    events = []
    monkeypatch.setattr(el, "record_trajectory_event", lambda kind, data: events.append((kind, data)))

    class Fake(BaseProvider):
        def init_client(self):
            return True

        def process_message(self, message, **kwargs):
            return list(self.process_message_stream(message, **kwargs))

        def process_message_stream(self, message, **kwargs):
            yield {"type": "final", "content": "ok"}

    provider = Fake("", "test", "system", [])
    provider.process_message("private-message", history=[{"content": [
        {"type": "text", "text": "abc"}, {"type": "image", "source": {"data": "secret-image"}},
    ]}], images=["secret-image"])
    inputs = [data for kind, data in events if kind == "model.input"]
    assert len(inputs) == 1 and inputs[0]["history_chars"] == 3 and inputs[0]["images"] == 1
    assert inputs[0]["system_chars"] == 6 and inputs[0]["message_chars"] == 15
    assert "secret-image" not in json.dumps(events) and "private-message" not in json.dumps(events)


def test_template_reuses_outer_html_and_escapes_only_text():
    obj = script_module("슬라이드틀적용")
    out = obj.specs("<h1>{{title}}</h1>{{visual_html}}", [{"id": "s001", "title": "A&B", "fields": {"visual_html": "<svg/>"}}])
    assert out[0][1]["custom_html"] == "<h1>A&amp;B</h1><svg/>"
    with pytest.raises(ValueError):
        obj.specs("{{missing}}", [{"id": "s001", "title": "title"}])


def test_milestone_observation_occurs_once_without_progress_reports(supervisor, monkeypatch):
    calls = []
    monkeypatch.setattr(supervisor, "review", lambda reason, paused=False: calls.append((reason, paused)))
    result = {"success": True, "supervision_checkpoint": {"hash": "h", "source": "source.md"}}
    for _ in range(2):
        supervisor.run_tool("inspect", {}, lambda: result)
    assert calls == [("milestone", True)]


def test_hard_limit_is_shared_by_execution_and_helpers():
    from providers.base import ProviderMetrics, turn_limit_reason, turn_token_scope
    with turn_token_scope("worker", "quota-test", hard_token_limit=40):
        ProviderMetrics().record_usage(1, {"prompt_tokens": 20, "completion_tokens": 2})
        assert turn_limit_reason() is None
        ProviderMetrics().record_usage(1, {"prompt_tokens": 20, "completion_tokens": 2})
        assert turn_limit_reason()["kind"] == "task_budget"
    assert turn_limit_reason() is None


def test_multiple_substrings_share_one_atomic_patch(tmp_path):
    store = TurnStore(tmp_path)
    store.put_response("같은 연도, 유일한 사례")
    b = store.blocks[0]
    store.patch(1, [{"id": b["id"], "hash": b["hash"], "replacements": [
        {"old_string": "같은 연도", "new_string": "다른 시점"},
        {"old_string": "유일한", "new_string": "추가 확인된"}]}])
    assert store.text == "다른 시점, 추가 확인된 사례"


def test_interrupted_cli_snapshots_are_charged_once(monkeypatch):
    import episode_logger as el
    from providers.base import BaseProvider
    events = []
    monkeypatch.setattr(el, "record_trajectory_event", lambda kind, data: events.append((kind, data)))
    class Partial(BaseProvider):
        def init_client(self):
            return True
        def process_message(self, message, **kwargs):
            for output in (1, 4):
                el.notify_response_snapshot("CLI", "model", "response1", {"input": 200, "output": output, "cache_read": 100}, [])
            raise RuntimeError("interrupted")
    provider = Partial("", "model", "prompt", [])
    with pytest.raises(RuntimeError):
        provider.process_message("test")
    assert provider.metrics.total_input_tokens == 200
    assert provider.metrics.total_output_tokens == 4
    charges = [e[1] for e in events if e[0] == "model.usage"]
    assert len(charges) == 1 and charges[0]["usage_partial"]


def test_video_recipe_reuses_stages_and_regenerates_only_changed_notes(tmp_path, monkeypatch):
    recipe = script_module("영상제작파이프라인")
    original_module = recipe.module
    directory = tmp_path / "deck1"
    directory.mkdir()
    (directory / "slides").mkdir()
    books = tmp_path / "books"; books.mkdir()
    for name in ("intro.wav", "outro.wav"):
        (books / name).write_bytes(name.encode())
    voice = tmp_path / "voice.wav"; voice.write_bytes(b"voice")
    source = tmp_path / "source.md"
    prep = original_module("나레이션원고추출")
    source.write_text(f"## s001 — 첫장\n{prep.INTRO} 첫 내용.\n\n## s002 — 끝장\n다음 내용. {prep.OUTRO}\n")
    for sid in ("s001", "s002"):
        (directory / "slides" / (sid + ".png")).write_bytes(sid.encode())
    deck = {"lecture_id": "deck1", "slide_order": ["s001", "s002"], "slides": {
            sid: {"png_file": "slides/" + sid + ".png", "speaker_note": "old"} for sid in ("s001", "s002")}}
    (directory / "deck.json").write_text(json.dumps(deck))
    calls = []
    def modules(name):
        if name == "나레이션생성":
            return SimpleNamespace(default_voice=lambda: "selected", load_voice=lambda v: (voice, "reference"))
        if name == "영상음량정렬":
            return SimpleNamespace(measure=lambda p: {"seconds": 2, "lufs": -21, "true_peak": -2})
        return original_module(name)
    monkeypatch.setattr(recipe, "module", modules)
    def run(name, args):
        calls.append((name, args))
        out = Path(args["out_dir"]); out.mkdir(exist_ok=True)
        if name == "나레이션생성":
            for sid, text in args["texts"].items():
                (out / (sid + ".wav")).write_bytes(text.encode())
        else:
            for src in Path(args["raw_dir"]).glob("*.wav"):
                (out / src.name).write_bytes(src.read_bytes() + b"joined")
        return {"success": True, "items": []}
    monkeypatch.setattr(recipe, "script", run)
    def build(*a, **kw):
        calls.append(("render", {}))
        output = directory / "result.mp4"
        output.write_bytes(b"video" + b"".join(p.read_bytes() for p in sorted((directory / "narration").glob("*.wav"))))
        return {"output": str(output), "missing_notes": [], "skipped": []}
    monkeypatch.setattr(recipe.deck_video, "build", build)
    monkeypatch.setattr(recipe.lecture_store, "set_roots", lambda *a, **kw: None)
    args = {"lecture_id": "deck1", "lecture_dir": str(directory), "source": str(source), "bookends": str(books)}
    inspected = recipe.execute(args)
    assert calls == []
    run_args = {**args, "mode": "run", "manifest_hash": inspected["manifest_hash"]}
    assert recipe.execute(run_args)["success"]
    assert len(calls) == 3
    assert recipe.execute(run_args)["success"] and len(calls) == 3
    source.write_text(source.read_text().replace("첫 내용", "고친 내용"))
    with pytest.raises(ValueError):
        recipe.execute(run_args)
    inspected = recipe.execute(args)
    recipe.execute({**run_args, "manifest_hash": inspected["manifest_hash"]})
    narration_calls = [a for name, a in calls if name == "나레이션생성"]
    assert len(narration_calls) == 2 and list(narration_calls[-1]["texts"]) == ["s001"]
    voice.write_bytes(b"changed voice outside the default voice folder")
    inspected = recipe.execute(args)
    recipe.execute({**run_args, "manifest_hash": inspected["manifest_hash"]})
    assert list([a for name, a in calls if name == "나레이션생성"][-1]["texts"]) == ["s001", "s002"]


def test_large_handoff_remains_bounded_and_full_evidence_is_recoverable(supervisor):
    from supervisor_handoff import bounded_handoff
    state = {"goal": "user goal", "repair": {"instruction": "긴 지시" * 50000}, "jobs": []}
    result = bounded_handoff(supervisor, state)
    assert len(json.dumps(result, ensure_ascii=False)) < supervisor.config["repair_context_chars"]
    assert result["goal"] == "user goal" and result["full_checkpoint"]["id"]
    page = supervisor.store.read_evidence(result["repair"]["evidence"]["id"], 0, 12000)
    assert "긴 지시" in page["text"]


def test_global_quota_protects_recheck_even_in_soft_supervisor_mode(supervisor, monkeypatch):
    from providers.base import turn_token_scope
    monkeypatch.setattr("supervisor_runtime.invoke", lambda c, *a, **kw: verdict(c, "REWORK", instruction="fix"))
    supervisor.runner.ai.process_message_stream = lambda *a, **kw: pytest.fail("전체 한도 밖 보완")
    with turn_token_scope("test", "repair-quota", hard_token_limit=50000):
        finish(supervisor, "candidate")
    assert "repair.skipped" in (supervisor.store.directory / "events.jsonl").read_text()


def test_visual_layout_reuse_requires_unchanged_pixels_and_validator(tmp_path):
    from verification_cache import VerificationCache
    image, validator = tmp_path / "slide.png", tmp_path / "validator.py"
    image.write_bytes(b"pixels"); validator.write_text("v1")
    cache, store = VerificationCache(), TurnStore(tmp_path / "evidence")
    artifacts = [{"_path": str(image), "base64": "pixels"}]
    pending, report = cache.visual_input(artifacts, "criteria", store)
    assert pending == artifacts and len(report["attached"]) == 1
    cache.remember([{"path": str(image), "status": "passed", "coverage": "visual_layout",
                     "tool_version": "v1", "validator_paths": [str(validator)],
                     "evidence_ids": [report["attached"][0]["evidence_id"]]}], "criteria", store)
    assert cache.visual_input(artifacts, "criteria", store)[0] is None
    validator.write_text("v2")
    assert cache.visual_input(artifacts, "criteria", store)[0] == artifacts


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
