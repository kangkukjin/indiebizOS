"""실제 IBL 조합과 결정론 품질 관문. 외부 AI/YouTube만 고정 응답으로 대체한다."""
import copy
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401
import pytest

spec = importlib.util.spec_from_file_location("tips_helper", ROOT / "data/scripts/ai_tips_report.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
BODY = (ROOT / "data/idioms/ai_tips_report.ibl").read_text()
IDS = ("aaaaaaaaaaa", "bbbbbbbbbbb")
QUOTES = ("Before changing files, save a checkpoint and review the diff.",
          "Retry only the failed step; do not repeat a successful payment.")
TITLES = ("수정 전 체크포인트와 차이를 확인한다", "실패 단계만 재시도한다")


def fixture_ai(item):
    task, source = item["task"], item["input"]
    if "scan_id" in source:
        return {"scan_id": source["scan_id"], "decisions": [
            {"candidate_id": c["candidate_id"], "unit_ids": [u["unit_id"] for u in source["units"]
             if any(q in u["text"] for q in QUOTES) or "CAVEAT" in u["text"]],
             "uncertain": False, "reason": "방법과 멀리 떨어진 조건의 원문 위치"}
            for c in source["candidates"]]}
    if "queries:[{stratum,query}]" in task:
        return {"queries": [{"stratum": s, "query": "AI tips " + s} for s in helper.STRATA]}
    if "selected:[영상ID]" in task:
        return {"selected": list(IDS), "decisions": [
            {"video_id": r["video_id"], "reason": "서로 다른 복구 방식"} for r in source["videos"]]}
    if "repair_id,candidate_id" in task:
        return {"repair_id": source["repair_id"], "candidate_id": source["candidate"]["candidate_id"],
                "verdict": "unknown", "matched_ids": [], "reason": "fixture: 독립 확인 불가"}
    if "matched_ids:[known_id]" in task:
        return {"batch_id": source["batch_id"], "decisions": [
            {"candidate_id": r["candidate_id"], "verdict": "novel", "matched_ids": [],
             "reason": "기존 방법과 다른 복구 절차"} for r in source["candidates"]]}
    if "keep:boolean" in task:
        return {"decisions": [{"candidate_id": r["candidate_id"], "keep": True,
                               "reason": "기존 자료에 없는 구체 방법"} for r in source["candidates"]]}
    if "verdict:'pass|reject|needs_evidence'" in task:
        return {"video_id": source["video"]["video_id"], "decisions": [
            {"candidate_id": r["candidate_id"], "verdict": "pass", "reason": "원문에서 방법 확인",
             "tip": r["tip"], "how": r["how"], "hype": "직접 재현하지 않음",
             "implication_class": "이식 후보", "implication": "복구 작업에서 시험할 후보"}
            for r in source["tips"]]}
    if "summary:[{candidate_id,reason}]" in task:
        return {"summary": [{"candidate_id": r["candidate_id"], "reason": "복구 위험을 줄이는 방법"}
                            for r in source["tips"]], "try_ids": [],
                "video_opinions": [{"video_id": v["video_id"], "opinion": "구체적인 복구 조건을 제시한다"}
                                   for v in source["videos"]],
                "watch_points": ["다른 환경에서도 같은 방법이 가능한지 검토한다"], "limitations": []}
    if "report_hash,checks:" in task:
        return {"report_hash": source["report_hash"], "review_id": source.get("review_id"),
                "checks": {k: True for k in helper.CHECKS},
                "issues": []}
    raise AssertionError(task)


@pytest.fixture
def execute(tmp_path, monkeypatch):
    import ibl_engine
    import ibl_typecheck
    import ibl_usage_db
    import workflow_engine
    from ibl_parser import parse_with_vars
    from ibl_control_blocks import _execute_fn
    from ibl_executors import _execute_table_each
    from common import spill
    from tool_context import ToolContext

    spec = importlib.util.spec_from_file_location(
        "tips_dataops", ROOT / "data/packages/installed/tools/data-ops/handler.py")
    dataops = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dataops)
    from common.pkg_utils import load_sibling
    scriptops = load_sibling(str(ROOT / "data/packages/installed/tools/system_essentials/handler.py"), "script_ops")
    calls, stages = [], {}
    model_calls = []
    transcripts, struct_calls, struct_hooks = {}, [], []
    search_calls, search_responses = [], {}
    corrupt = {}
    class DB:
        def find_phrase_by_alias(self, name):
            return {"ibl_code": BODY, "alias": name} if name == "AI팁보고서쓰기" else None
        def update_success_by_code(self, *args, **kwargs):
            pass
    monkeypatch.setattr(ibl_usage_db, "IBLUsageDB", DB)
    monkeypatch.setattr(workflow_engine, "get_workflow", lambda name: None)
    monkeypatch.setattr(ibl_typecheck, "FN_CODE_SOURCES", [lambda n: BODY if n == "AI팁보고서쓰기" else None])
    monkeypatch.setattr(spill, "_root", lambda: str(tmp_path / "spill"))
    original = ibl_engine._execute_ibl_impl
    def leaf(ti, project, agent_id=None):
        # Test doubles must retain the real dispatcher depth guard.
        if (ti.get("_depth") or 0) > ibl_engine.MAX_NEST_DEPTH:
            return original(ti, project, agent_id)
        node, act = ti.get("_node"), ti.get("action")
        p = dict(ti.get("params") or {})
        if node == "fn":
            return _execute_fn(ti, project, agent_id)
        if node == "table" and act == "each":
            p["_depth"] = ti.get("_depth", 0)
            return _execute_table_each(p, project, agent_id=agent_id)
        if node == "table" and "data_" + str(act) in dataops._DISPATCH:
            return dataops.execute(p, ToolContext(project, "data_" + act))
        if node == "self" and act == "script":
            args, error, _ = scriptops._stdin_args(p)
            assert error is None, error
            stage = args["op"]
            if stage in corrupt:
                args = corrupt[stage](copy.deepcopy(args))
            stages[stage] = copy.deepcopy(args)
            try:
                out = helper.run(args)
            except Exception as exc:
                out = {"success": False, "error": str(exc)}
            return {"success": True, "id": p["id"], "exit_code": 0, **out}
        if node == "sense" and act == "search_youtube":
            query = p["query"]
            search_calls.append(query)
            override = search_responses.get(query.rsplit(" ", 1)[-1])
            if override is not None:
                return override(search_calls.count(query)) if callable(override) else copy.deepcopy(override)
            return {"success": True, "items": [{"video_id": vid} for vid in IDS]}
        if node == "sense" and act == "video":
            vid = p["video_id"]
            calls.append((p["op"], vid))
            if p["op"] == "info":
                return {"success": True, "items": [{"video_id": vid, "title": "Fixture " + vid,
                        "uploader": "Fixture Channel", "duration": 240, "upload_date": "2026-09-01"}]}
            if vid in transcripts:
                return {"success": True, "items": copy.deepcopy(transcripts[vid])}
            return {"success": True, "items": [{"start": 0.0, "duration": 8.0,
                                               "text": QUOTES[IDS.index(vid)]}]}
        if node == "self" and act == "struct":
            model_calls.append(("struct", p["schema"]))
            struct_calls.append(copy.deepcopy(p))
            for hook in struct_hooks:
                override = hook(p)
                if override is not None:
                    return override
            path = Path(p["file"])
            state = helper.load_json(path.parent / "state.json")
            vid = path.stem.removeprefix("transcript-")
            for job in state.get("source_plan", {}).get("jobs", {}).values():
                if job["request"]["path"] == str(path):
                    vid = job["request"]["video_id"]
            for record in state.get("source_evidence", {}).values():
                if record["path"] == str(path):
                    vid = record["video_id"]
            n = IDS.index(vid)
            assert isinstance(p["schema"], str)
            source = helper.load_json(Path(p["file"]))
            assert source["transcript"] == "\n".join(r["text"] for r in source["items"])
            records = [{"tip": TITLES[n], "timestamp": f"{int(r['start']) // 60:02d}:{int(r['start']) % 60:02d}",
                        "_quote": QUOTES[n]} for r in source["items"] if QUOTES[n] in r["text"]]
            if "candidate_id" in p["schema"]:
                ids = {k for k, v in state.get("source_detail_jobs", {}).items() if v["path"] == str(path)}
                chosen = [r for r in state["chosen"] if r["video_id"] == vid and (
                    not ids or vid in ids or r["candidate_id"] in ids)]
                records = [{**r, "how": TITLES[n], "tools": None, "hype": ""} for r in chosen]
            assert p["grounded"] is True
            return {"success": True, "grounded": True, "timestamp_grounded": len(records), "items": records}
        if node == "table" and act == "ai":
            source = p.get("_prev_result") if "_prev_result" in p else p.get("items")
            inputs = helper.rows(source)
            if inputs:
                model_calls.append(("ai", len(inputs)))
            return {"success": True, "items": [{**r, "result": fixture_ai(r)} for r in inputs],
                    "rows_in": len(inputs), "rows_out": len(inputs)}
        return original(ti, project, agent_id)
    monkeypatch.setattr(ibl_engine, "_execute_ibl_impl", leaf)
    monkeypatch.setattr(ibl_engine, "execute_ibl", leaf)
    def run(mode="draft", named=True, topic="복구"):
        config = {"root": str(tmp_path / "reports"), "date": "2026-09-23", "topic": topic,
                  "mode": mode, "run_id": "test"}
        code = ("[fn:AI팁보고서쓰기]" + json.dumps({"설정": config}, ensure_ascii=False) if named else
                "$설정=" + json.dumps(config, ensure_ascii=False) + "\n" + BODY)
        steps, _ = parse_with_vars(code)
        return workflow_engine.execute_pipeline(steps, str(tmp_path))
    run.stages, run.calls, run.corrupt = stages, calls, corrupt
    run.root = tmp_path / "reports"
    run.model_calls = model_calls
    run.transcripts, run.struct_calls, run.struct_hooks = transcripts, struct_calls, struct_hooks
    run.search_calls, run.search_responses = search_calls, search_responses
    return run


def final(result):
    assert result["success"], str(result.get("error") or result.get("traceback") or result)[-3000:]
    return helper.rows(helper.unpack(result["final_result"]))[0]


def test_empty_searches_preserve_scope_and_finish_without_retry(execute):
    execute.search_responses.update(korean={"success": True, "items": [], "count": 0},
                                    specific={"success": True, "items": [], "count": 0})
    out = final(execute())
    state = helper.load_json(execute.root / "_runs/test/state.json")
    assert set(state["search"]["empty_strata"]) == {"korean", "specific"}
    assert len(execute.search_calls) == 5
    assert "결과 0건인 검색 층" in Path(out["report"]).read_text()
    assert final(execute()) == out
    assert len(execute.search_calls) == 5


def test_only_failed_search_retries_and_successes_survive(execute):
    execute.search_responses["korean"] = lambda n: (
        {"success": False, "error": "network timeout"} if n == 1 else
        {"success": True, "items": [], "count": 0})
    final(execute())
    state = helper.load_json(execute.root / "_runs/test/state.json")
    assert len(execute.search_calls) == 6
    assert execute.search_calls.count("AI tips korean") == 2
    assert [r["status"] for r in state["search_outcomes"]["korean"]["attempts"]] == ["error", "empty"]
    assert all(len(r["attempts"]) == 1 for s, r in state["search_outcomes"].items() if s != "korean")


def test_persistent_search_failure_stops_and_manual_resume_only_calls_failed(execute):
    execute.search_responses["korean"] = {"success": False, "error": "network timeout"}
    result = execute("commit")
    assert not result["success"]
    assert len(execute.search_calls) == 6
    state = helper.load_json(execute.root / "_runs/test/state.json")
    assert len(state["search_outcomes"]) == 5
    assert "search" not in state["receipts"]
    assert not (execute.root / "db/tips.json").exists()
    execute.search_responses["korean"] = {"success": True, "items": []}
    final(execute("commit"))
    assert len(execute.search_calls) == 7
    assert execute.search_calls[-1] == "AI tips korean"


def test_all_empty_searches_do_not_invent_report_or_retry(execute):
    execute.search_responses.update({s: {"success": True, "items": []} for s in helper.STRATA})
    assert not execute("commit")["success"]
    assert len(execute.search_calls) == 5
    assert not (execute.root / "db/tips.json").exists()
    assert not execute("commit")["success"]
    assert len(execute.search_calls) == 5


@pytest.mark.parametrize("mutation", ["missing", "query", "duplicate", "count", "partial"])
def test_search_protocol_errors_are_not_retried_or_accepted(execute, mutation):
    def corrupt(args):
        data = args["data"]
        if mutation == "missing":
            data["items"].pop()
        elif mutation == "duplicate":
            data["items"].append(copy.deepcopy(data["items"][0]))
        elif mutation == "query":
            helper.unpack(data["items"][0])["query"] = "changed"
        else:
            helper.unpack(data["items"][0])["data"][mutation] = 999 if mutation == "count" else True
        return args
    execute.corrupt["search"] = corrupt
    assert not execute("commit")["success"]
    assert len(execute.search_calls) == 5
    assert not (execute.root / "db/tips.json").exists()


def test_search_attempt_receipts_reject_mutation_and_replay_idempotently():
    state = {"queries": [{"stratum": s, "query": "AI tips " + s} for s in helper.STRATA]}
    data = [{**q, "data": {"success": True, "items": []}}
            for q in helper.searchflow.requests(state)]
    assert helper.searchflow.accept(state, data) == []
    before = copy.deepcopy(state)
    assert helper.searchflow.accept(state, data) == []
    assert state == before
    data[0]["data"]["items"] = [{"video_id": IDS[0]}]
    with pytest.raises(ValueError, match="입력 변경"):
        helper.searchflow.accept(state, data)
    state["search_outcomes"]["korean"]["status"] = "error"
    with pytest.raises(ValueError, match="지문 변경"):
        helper.searchflow.requests(state)


def test_old_flattened_failed_search_resumes_only_failed_queries(execute):
    final(execute())
    state_path = execute.root / "_runs/test/state.json"
    state = helper.load_json(state_path)
    state.pop("completed")
    state.pop("search_outcomes")
    state["receipts"] = {"queries": state["receipts"]["queries"]}
    old = {"items": [{**q, **({"_error": "검색 결과가 없습니다."} if q["stratum"] == "korean"
                              else {"video_id": IDS[0]})} for q in state["queries"]],
           "success": True, "error_count": 1}
    state["last_failure"] = {"stage": "search", "input_hash": helper.digest(old), "kind": "invalid"}
    helper.atomic(state_path, state)
    helper.atomic(state_path.parent / "input-search.json", old)
    pending = helper.run({"op": "queries", "run": str(state_path.parent), "data": {"items": []}})
    assert pending["items"] == [{"stratum": "korean", "query": "AI tips korean", "attempt": 2}]
    restored = helper.load_json(state_path)
    assert restored["search_outcomes"]["korean"]["status"] == "error"
    assert all(restored["search_outcomes"][s]["status"] == "ok" for s in helper.STRATA if s != "korean")



@pytest.mark.parametrize("mutation", ["none", "missing", "changed", "rejected"])
def test_partitioned_final_review_keeps_every_reason_and_requires_every_pass(execute, mutation):
    final(execute())
    state = helper.load_json(execute.root / "_runs/test/state.json")
    state.pop("completed")
    original = copy.deepcopy(execute.stages["finish"]["data"]["items"][0])
    original.pop("result")
    decisions = [{"candidate_id": "c1", "verdict": "novel", "matched_ids": [],
                  "batch_ids": ["b" + str(i)], "reason": str(i) + "원문 비교 근거" * 250}
                 for i in range(45)]
    original["input"]["novelty"]["decisions"] = decisions
    request = helper.final_review_tasks(state, {"items": [original]})
    assert request["count"] > 1
    assert all(helper.request_size(r) < helper.REQUEST_CAP for r in request["items"])
    assert [d for r in request["items"] for d in r["input"]["novelty"]["decisions"]] == decisions
    assert all(r["input"]["markdown"] == state["markdown"] for r in request["items"])
    data = {"items": [{**r, "result": fixture_ai(r)} for r in request["items"]]}
    if mutation == "missing":
        data["items"].pop()
    elif mutation == "changed":
        data["items"][-1]["input"]["novelty"]["decisions"].pop()
    elif mutation == "rejected":
        data["items"][-1]["result"]["checks"]["novelty"] = False
        data["items"][-1]["result"]["issues"] = ["마지막 분할 근거 모순"]
    if mutation == "none":
        assert helper.stage_finish(state, data)["items"][0]["status"] == "reviewed_draft"
        assert len(state["final_review"]["parts"]) == request["count"]
    else:
        with pytest.raises(ValueError):
            helper.stage_finish(state, data)
        assert not state.get("completed")



def test_feedback_handoff_uses_exact_ledger_entries_without_rewriting_audit(execute):
    known = [{"tip": "첫 기존 팁", "how": "원본 절차", "source": {"url": "https://example.com"}},
             {"tip": "다른 기존 팁", "how": "별도 원본"}]
    helper.atomic(execute.root / "db/tips.json", known)
    final(execute())
    state = helper.load_json(execute.root / "_runs/test/state.json")
    original = copy.deepcopy(state["novelty"])
    state["revision_feedback"] = "k1의 설명이 충돌함. k999는 존재하지 않음."
    view = helper.novelty_view(state)
    assert view["feedback_known"] == [{"known_id": "k1", **known[0]}]
    assert state["novelty"] == original
    assert view["full_audit_hash"] == helper.digest(original)

def test_named_full_pipeline_draft_keeps_production_ledgers_unchanged(execute):
    out = final(execute())
    assert out["status"] == "reviewed_draft" and out["new_tips"] == 2
    assert not (execute.root / "db/tips.json").exists()
    assert not (execute.root / "_covered_videos.json").exists()
    text = Path(out["report"]).read_text()
    assert all(q in text for q in QUOTES)
    assert "다룬 영상 2편(후보 등재 2편)" in text
    assert len(execute.calls) == 4


def test_full_pipeline_commit_and_idempotent_finish(execute):
    out = final(execute("commit"))
    assert out["status"] == "committed"
    tips = helper.load_json(execute.root / "db/tips.json")
    assert len(tips) == 2 and {t["_quote"] for t in tips} == set(QUOTES)
    first = (execute.root / "db/tips.json").read_bytes()
    assert helper.run(execute.stages["finish"])["items"][0] == out
    assert (execute.root / "db/tips.json").read_bytes() == first


@pytest.mark.parametrize("stage,mutate", [
    ("candidates", lambda data: data.update(truncated=True)),
    ("candidates", lambda data: helper.unpack(data["items"][0])["data"].update(dropped_ungrounded=1)),
    ("candidates", lambda data: helper.unpack(data["items"][0])["data"]["items"][0].update(timestamp="08:00")),
    ("chosen", lambda data: data["items"][0]["result"]["decisions"].pop()),
    ("reviewed", lambda data: data["items"][0]["result"]["decisions"][0].update(verdict="needs_evidence")),
    ("finish", lambda data: data["items"][0]["result"]["checks"].update(novelty=False)),
    ("finish", lambda data: data["items"][0]["result"].update(report_hash="changed")),
])
def test_bad_evidence_never_reaches_ledgers(execute, stage, mutate):
    def corrupt(args):
        data = helper.unpack(args["data"])
        mutate(data)
        args["data"] = data
        return args
    execute.corrupt[stage] = corrupt
    result = execute("commit")
    assert not result["success"]
    assert not (execute.root / "db/tips.json").exists()
    assert not (execute.root / "_covered_videos.json").exists()
    assert stage in execute.stages


def test_ledger_changed_during_research_stops_commit(execute):
    def corrupt(args):
        helper.atomic(execute.root / "db/tips.json", [{"tip": "다른 보고서"}])
        return args
    execute.corrupt["finish"] = corrupt
    assert not execute("commit")["success"]
    assert helper.load_json(execute.root / "db/tips.json") == [{"tip": "다른 보고서"}]


def test_freshness_boundary_missing_date_and_long_video_limits():
    state = {"config": {"date": "2026-09-23", "topic": "복구"}, "run": "/fixture",
             "search": {"candidates": [{"video_id": vid, "strata": ["english"]} for vid in IDS]}}
    wrappers = [{"video_id": v, "data": {"items": [
        {"video_id": v, "title": "title", "channel": "channel", "duration": 60,
         "upload_date": "2026-03-27"}]}} for v in IDS]
    helper.stage_metadata(state, {"items": wrappers})
    assert len(state["metadata"]) == 2  # 180일 경계 포함
    wrappers[0]["data"]["items"][0]["upload_date"] = "2026-03-26"
    with pytest.raises(ValueError, match="2편 미만"):
        helper.stage_metadata(state, {"items": wrappers})




def test_named_and_expanded_have_identical_report(execute):
    named = final(execute())
    expected = Path(named["report"]).read_bytes()
    # 새 폴더로 같은 초기 입력을 주는 확장 호출: 캐시 사용 비교가 아니다.
    import shutil
    shutil.rmtree(execute.root)
    expanded = final(execute(named=False))
    assert Path(expanded["report"]).read_bytes() == expected


def test_full_reentry_does_not_repeat_completed_external_calls(execute):
    first = final(execute("commit"))
    calls = list(execute.calls)
    again = final(execute("commit"))
    assert first == again and execute.calls == calls
    assert len(helper.load_json(execute.root / "db/tips.json")) == 2


def test_failed_review_resumes_without_researching_again(execute):
    def fail(args):
        args["data"]["items"][0]["result"]["decisions"][0]["verdict"] = "needs_evidence"
        return args
    execute.corrupt["reviewed"] = fail
    assert not execute()["success"]
    calls = list(execute.calls)
    execute.corrupt.clear()
    assert final(execute())["status"] == "reviewed_draft"
    assert execute.calls == calls


def test_changed_source_blocks_finish(execute):
    def changed(args):
        path = Path(args["run"]) / ("transcript-" + IDS[0] + ".json")
        helper.atomic(path, {"items": [{"start": 0, "text": "different source"}]})
        return args
    execute.corrupt["finish"] = changed
    assert not execute("commit")["success"]
    assert not (execute.root / "db/tips.json").exists()


def test_partial_commit_is_recoverable_without_duplicate_rows(execute, monkeypatch):
    real_atomic = helper.atomic
    failed = False
    def crash(path, value, text=False):
        nonlocal failed
        if path == execute.root / "db/tips.json" and not failed:
            failed = True
            raise OSError("simulated interrupted write")
        return real_atomic(path, value, text=text)
    monkeypatch.setattr(helper, "atomic", crash)
    assert not execute("commit")["success"]
    assert not helper.load_json(execute.root / "_report_transaction.json").get("done")
    out = final(execute("commit"))
    assert out["status"] == "committed"
    assert len(helper.load_json(execute.root / "db/tips.json")) == 2
    assert helper.load_json(execute.root / "_report_transaction.json")["done"]


def test_transcript_spill_is_resolved_in_full(tmp_path, monkeypatch):
    from common import spill
    monkeypatch.setattr(spill, "_root", lambda: str(tmp_path))
    # 반환 봉투가 파일 참조로 바뀌어도 미리보기를 근거로 쓰면 안 된다.
    source = {"items": [{"start": 0, "text": QUOTES[0]}, {"start": 10, "text": QUOTES[1]}]}
    ref = spill.spill_write(json.dumps(source))
    assert helper.segments(ref) == source["items"]
    # each의 명시 투영은 ref만 남길 수 있으며 saved_to_file은 원문 TXT다.
    projected = {"items": [], "ref": ref["ref"], "saved_to_file": True,
                 "file_path": str(tmp_path / "must-not-read-preview.txt")}
    assert helper.segments(projected) == source["items"]


def test_normalized_transcript_obeys_real_struct_input_contract():
    spec = importlib.util.spec_from_file_location(
        "tips_aiops", ROOT / "data/packages/installed/tools/ai-ops/handler.py")
    aiops = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(aiops)
    segments = [{"start": 0, "text": QUOTES[0]}, {"start": 10, "text": QUOTES[1]}]
    envelope = helper.transcript_document(segments)
    src, _, body = aiops._src_from_envelope(envelope, "test")
    assert (src and src.get("text")) or body == envelope["transcript"]
    assert aiops._time_segments(envelope)


def test_saved_report_mutation_blocks_finish(execute):
    def mutate(args):
        (Path(args["run"]) / "draft.md").write_text("검수 후 다른 본문")
        return args
    execute.corrupt["finish"] = mutate
    assert not execute("commit")["success"]
    assert not (execute.root / "db/tips.json").exists()




def test_revision_preserves_rejection_and_reuses_sources(execute):
    def reject(args):
        args["data"]["items"][0]["result"]["checks"]["actionability"] = False
        args["data"]["items"][0]["result"]["issues"] = ["추상적 방법 재검토"]
        return args
    execute.corrupt["finish"] = reject
    assert not execute()["success"]
    directory = execute.root / "_runs/test"
    before = helper.load_json(directory / "state.json")
    calls = list(execute.calls)
    result = helper.run({"op": "revise", "run": str(directory),
                         "from": "reviewed", "reason": "추상적 방법을 원문으로 재검토"})
    assert result["items"][0]["status"] == "revision_ready"
    state = helper.load_json(directory / "state.json")
    assert "reviewed" not in state["receipts"] and "draft" not in state["receipts"]
    assert state["sources"] == before["sources"]
    assert helper.load_json(directory / "revision-2.json") == before
    assert helper.load_json(directory / "revision-1-input-finish.json")
    assert helper.load_json(directory / "revision-2-input-finish.json")
    execute.corrupt.clear()
    assert final(execute())["status"] == "reviewed_draft"
    assert execute.calls == calls
    with pytest.raises(ValueError, match="완료된 보고서"):
        helper.run({"op": "revise", "run": str(directory),
                    "from": "reviewed", "reason": "완료 후 수정 시도"})


def test_final_review_receives_actual_metadata_and_search_scope(execute):
    final(execute())
    source = execute.stages["finish"]["data"]["items"][0]["input"]
    assert source["prior_counts"] == {"tips": 0, "covered": 0}
    assert {v["video_id"] for v in source["videos"]} == set(IDS)
    assert {v["video_id"] for v in source["metadata"]} == set(IDS)
    assert len(source["search"]["candidates"]) == 2




def test_editorial_references_are_readable_titles_before_final_review(execute):
    def mention(args):
        args["data"]["items"][0]["result"]["summary"][0]["reason"] = "c2와 보완적이다"
        return args
    execute.corrupt["draft"] = mention
    out = final(execute())
    assert "c2와" not in Path(out["report"]).read_text()
    assert "‘" + TITLES[1] + "’와 보완적이다" in Path(out["report"]).read_text()


def test_unknown_editorial_reference_blocks_report(execute):
    def mention(args):
        args["data"]["items"][0]["result"]["summary"][0]["reason"] = "c999와 비교한다"
        return args
    execute.corrupt["draft"] = mention
    assert not execute("commit")["success"]
    assert not (execute.root / "db/tips.json").exists()

def test_static_contract_and_real_registration_gates():
    sys.path.insert(0, str(ROOT / "scripts"))
    from register_idiom import _gates
    info = _gates("AI팁보고서쓰기", "자막 근거와 내용 검토를 유지하며 주제별 AI 팁 보고서를 만들 때", BODY)
    assert info
    from ibl_typecheck import typecheck_code
    result = typecheck_code("[def:AI팁보고서쓰기]{\n" + BODY + "\n}")
    assert result["ok"] and result["fn_returns"]["AI팁보고서쓰기"].startswith("items")


def test_accepted_extraction_survives_next_request_preparation_failure(execute, monkeypatch):
    prepare = helper.prepare_comparison
    def blocked(state):
        raise ValueError("fixture: 다음 요청 입력 상한")
    monkeypatch.setattr(helper, "prepare_comparison", blocked)
    assert not execute()["success"]
    directory = execute.root / "_runs/test"
    state = helper.load_json(directory / "state.json")
    assert "candidates" in state["receipts"] and len(state["candidates"]) == 2
    before = list(execute.model_calls)
    response = helper.run({"op": "candidates", "run": str(directory), "data": {"items": []}})
    assert response["status"] == "blocked" and response["accepted"]
    assert response["resume"]["op"] == "candidates"
    assert helper.load_json(directory / "state.json")["preparation_failure"] == response
    monkeypatch.setattr(helper, "prepare_comparison", prepare)
    assert final(execute())["status"] == "reviewed_draft"
    # 앞 단계 table:ai와 1차 struct 호출을 반복하지 않는다.
    assert execute.model_calls[:len(before)] == before
    assert sum(k == "struct" and "candidate_id" not in v for k, v in execute.model_calls) == 2
    assert "preparation_failure" not in helper.load_json(directory / "state.json")


def test_large_ledger_is_fully_compared_and_not_repeated_in_editorial(execute):
    known = [{"tip": "기존 팁 " + str(i), "how": "다른 방법 " * 80} for i in range(647)]
    helper.atomic(execute.root / "db/tips.json", known)
    final(execute())
    state = helper.load_json(execute.root / "_runs/test/state.json")
    batches = state["comparison_batches"]
    assert len(batches) > 1
    ids = [k for batch in batches.values() for k in batch["known_ids"]]
    assert len(ids) == len(set(ids)) == len(known)
    assert set(ids) == {"k" + str(i + 1) for i in range(len(known))}
    for stage in ("draft", "finish"):
        source = execute.stages[stage]["data"]["items"][0]["input"]
        assert "known" not in source
        assert source["novelty_scope" if stage == "draft" else "novelty"]["known_count"] == 647
    assert helper.load_json(execute.root / "db/tips.json") == known


@pytest.mark.parametrize("mutation", ["missing_batch", "missing_candidate", "unknown", "bad_id"])
def test_incomplete_comparison_cannot_reach_selection(execute, mutation):
    helper.atomic(execute.root / "db/tips.json", [{"tip": "기존", "how": "원본"}])
    def corrupt(args):
        data = args["data"]["items"]
        if mutation == "missing_batch":
            data.clear()
        elif mutation == "missing_candidate":
            data[0]["result"]["decisions"].pop()
        elif mutation == "unknown":
            data[0]["result"]["decisions"][0]["verdict"] = "unknown"
        else:
            data[0]["result"]["decisions"][0].update(verdict="duplicate", matched_ids=["outside"])
        return args
    execute.corrupt["compared"] = corrupt
    assert not execute()["success"]
    assert "chosen" not in execute.stages


def test_completed_reentry_makes_zero_new_model_calls(execute):
    final(execute())
    before = list(execute.model_calls)
    final(execute())
    assert execute.model_calls == before


def test_receipt_tampering_and_old_version_are_rejected(execute):
    final(execute())
    path = execute.root / "_runs/test/state.json"
    state = helper.load_json(path)
    state["receipts"]["finish"]["output"]["items"][0]["new_tips"] = 999
    helper.atomic(path, state)
    with pytest.raises(ValueError, match="지문"):
        helper.run(execute.stages["finish"])
    state["version"] = 1
    helper.atomic(path, state)
    with pytest.raises(ValueError, match="버전"):
        helper.run(execute.stages["finish"])




def force_uncertain(args):
    args["data"]["items"][0]["result"]["decisions"][0]["verdict"] = "unknown"
    return args


def repair_model(monkeypatch, verdict="novel", mutate=None):
    original = fixture_ai
    def respond(item):
        if "repair_id,candidate_id" not in item["task"]:
            return original(item)
        source = item["input"]
        assert source["source_scope"] == "complete"
        assert "0.0s " in source["transcript"]
        result = {"repair_id": source["repair_id"],
                  "candidate_id": source["candidate"]["candidate_id"],
                  "verdict": verdict, "matched_ids": [],
                  "reason": "전문과 기존 자료 전체를 확인한 판정"}
        if mutate:
            mutate(result, source)
        return result
    monkeypatch.setitem(globals(), "fixture_ai", respond)


@pytest.mark.parametrize("missing", [False, True])
def test_full_source_repair_completes_all_comparison_pairs(execute, monkeypatch, missing):
    helper.atomic(execute.root / "db/tips.json", [{"tip": "기존", "how": "다른 방법"}])
    repair_model(monkeypatch)
    def corrupt(args):
        if missing:
            args["data"]["items"][0]["result"]["decisions"].pop()
        else:
            force_uncertain(args)
        return args
    execute.corrupt["compared"] = corrupt
    out = final(execute())
    assert out["new_tips"] == 2
    state = helper.load_json(execute.root / "_runs/test/state.json")
    assert state["comparison_repair_used"]
    assert len(state["novelty"]["decisions"]) == 2
    assert all(d["verdict"] == "novel" for d in state["novelty"]["decisions"])
    before = list(execute.model_calls)
    execute.corrupt.clear()
    final(execute())
    assert execute.model_calls == before
    assert helper.run(execute.stages["comparison_repair"])["cached"]
    altered = copy.deepcopy(execute.stages["comparison_repair"])
    altered["data"]["items"][0]["result"]["reason"] = "changed"
    with pytest.raises(ValueError, match="입력 변경"):
        helper.run(altered)


def test_verified_unsupported_candidate_is_excluded_with_reason(execute, monkeypatch):
    helper.atomic(execute.root / "db/tips.json", [{"tip": "기존", "how": "다른 방법"}])
    repair_model(monkeypatch, "unsupported")
    execute.corrupt["compared"] = force_uncertain
    out = final(execute())
    assert out["new_tips"] == 1
    state = helper.load_json(execute.root / "_runs/test/state.json")
    rejected = {d["candidate_id"] for d in state["novelty"]["decisions"]
                if d["verdict"] == "unsupported"}
    assert len(rejected) == 1
    assert rejected.isdisjoint(t["candidate_id"] for t in state["final_tips"])
    assert "근거가 확인되지 않아 제외" in Path(out["report"]).read_text()


@pytest.mark.parametrize("mutation", [
    lambda r, s: r.update(candidate_id="outside"),
    lambda r, s: r.update(verdict="duplicate", matched_ids=["outside"]),
    lambda r, s: r.update(verdict="unknown"),
    lambda r, s: r.update(reason=""),
])
def test_bad_full_source_repair_stays_blocked(execute, monkeypatch, mutation):
    helper.atomic(execute.root / "db/tips.json", [{"tip": "기존", "how": "다른 방법"}])
    repair_model(monkeypatch, mutate=mutation)
    execute.corrupt["compared"] = force_uncertain
    assert not execute("commit")["success"]
    assert "chosen" not in execute.stages
    assert helper.load_json(execute.root / "db/tips.json") == [{"tip": "기존", "how": "다른 방법"}]
    with pytest.raises(ValueError, match="1회"):
        helper.run({"op": "comparison_retry", "run": str(execute.root / "_runs/test")})


def test_repair_checks_source_integrity_before_acceptance(execute, monkeypatch):
    helper.atomic(execute.root / "db/tips.json", [{"tip": "기존", "how": "다른 방법"}])
    repair_model(monkeypatch)
    execute.corrupt["compared"] = force_uncertain
    def change(args):
        path = execute.root / "_runs/test/transcript-aaaaaaaaaaa.json"
        helper.atomic(path, {"items": [{"start": 0, "text": "changed"}]})
        return args
    execute.corrupt["comparison_repair"] = change
    assert not execute()["success"]
    assert "chosen" not in execute.stages


def test_novelty_view_retains_every_relevant_reason_and_batch(execute):
    final(execute())
    state = helper.load_json(execute.root / "_runs/test/state.json")
    selected = {state["final_tips"][0]["candidate_id"]}
    view = helper.novelty_view(state, selected)
    expanded = [{**{k: v for k, v in r.items() if k != "batch_ids"}, "batch_id": bid}
                for r in view["decisions"] for bid in r["batch_ids"]]
    expected = [r for r in state["novelty"]["decisions"] if r["candidate_id"] in selected]
    assert sorted(expanded, key=helper.canonical) == sorted(expected, key=helper.canonical)




@pytest.mark.parametrize("conflict", [False, True])
def test_full_source_retry_split_preserves_all_known_and_conflicts(execute, monkeypatch, conflict):
    known = [{"tip": "기존 " + str(i), "how": "다른 방법 " * 150} for i in range(120)]
    helper.atomic(execute.root / "db/tips.json", known)
    def response(result, source):
        if source["repair_id"] == "r1":
            result.update(verdict="unsupported" if conflict else "duplicate",
                          matched_ids=[] if conflict else [source["known"][0]["known_id"]])
    repair_model(monkeypatch, mutate=response)
    def corrupt(args):
        for row in args["data"]["items"]:
            row["result"]["decisions"][0]["verdict"] = "unknown"
        return args
    execute.corrupt["compared"] = corrupt
    result = execute()
    state = helper.load_json(execute.root / "_runs/test/state.json")
    requests = state["comparison_retry"]["requests"]
    assert len(requests) > 1
    ids = [r["known_id"] for item in requests for r in item["input"]["known"]]
    assert len(ids) == len(set(ids)) == len(known)
    assert all(helper.request_size(item) < helper.REQUEST_CAP for item in requests)
    if conflict:
        assert not result["success"] and "chosen" not in execute.stages
    else:
        assert final(result)["new_tips"] == 1
        assert state["novelty"]["matched_known"][0]["known_id"] == "k1"
    assert helper.load_json(execute.root / "db/tips.json") == known



def needs_official_evidence(execute):
    def stop(args):
        args["data"]["items"][0]["result"]["decisions"][0].update(
            verdict="needs_evidence", reason="공식 표기와 적용 환경 확인 필요")
        return args
    execute.corrupt["reviewed"] = stop
    assert not execute("commit")["success"]
    run = execute.stages["reviewed"]["run"]
    return run, {"op": "evidence", "run": run, "candidate_ids": ["c1"],
                 "data": {"items": [{"url": "https://example.org/official",
                                    "paragraph_index": 1, "text": "Official spelling and conditions."}]}}


def test_supplement_keeps_review_required_and_preserves_sources(execute):
    run, args = needs_official_evidence(execute)
    before = len(execute.calls)
    result = helper.run(args)
    assert result["items"][0]["status"] == "evidence_added"
    assert helper.run(args) == result
    state = helper.load_json(Path(run) / "state.json")
    assert len(state["supplements"]) == 1 and "reviewed" not in state["receipts"]
    assert not execute("commit")["success"]  # attaching a source alone cannot approve it
    execute.corrupt.clear()
    out = final(execute("commit"))
    assert len(execute.calls) == before
    review = execute.stages["reviewed"]["data"]["items"][0]["input"]
    assert review["supplements"][0]["sources"][0]["text"] == "[1] Official spelling and conditions."
    finishing = execute.stages["finish"]["data"]["items"][0]["input"]
    assert finishing["supplements"] == review["supplements"]
    assert "https://example.org/official" in Path(out["report"]).read_text()


@pytest.mark.parametrize("bad", ["candidate", "partial", "source"])
def test_supplement_rejects_wrong_candidate_partial_or_missing_source(execute, bad):
    run, args = needs_official_evidence(execute)
    if bad == "candidate":
        args["candidate_ids"] = ["c999"]
    elif bad == "partial":
        args["data"]["partial"] = True
    else:
        args["data"]["items"][0]["url"] = "file:///tmp/not-a-web-source"
    with pytest.raises(ValueError):
        helper.run(args)
    assert not helper.load_json(Path(run) / "state.json").get("supplements")
    assert not (execute.root / "db/tips.json").exists()


def test_changed_supplement_cannot_pass_final_review(execute):
    run, args = needs_official_evidence(execute)
    result = helper.run(args)
    execute.corrupt.clear()
    def change(args):
        path = Path(result["items"][0]["evidence"])
        source = helper.load_json(path)
        source["items"][0]["text"] = "Changed after independent review."
        helper.atomic(path, source)
        return args
    execute.corrupt["finish"] = change
    assert not execute("commit")["success"]
    assert not (execute.root / "db/tips.json").exists()


def test_structural_criteria_removed_but_semantic_review_remains():
    assert "criteria:" not in BODY
    assert BODY.count("preserve_rows:true") == BODY.count("[table:ai]")
    assert 'op:"reviewed"' in BODY and 'op:"finish"' in BODY
    assert "원문과 팁을 독립 대조" in BODY and "품질 기준을 독립 검토" in BODY


def test_one_automatic_revision_keeps_research_and_rechecks_quality(execute):
    attempts = []
    def reject_once(args):
        attempts.append(copy.deepcopy(args))
        if len(attempts) == 1:
            args["data"]["items"][0]["result"]["checks"]["actionability"] = False
            args["data"]["items"][0]["result"]["issues"] = ["방법의 적용 조건을 명확히 하라"]
        return args
    execute.corrupt["finish"] = reject_once
    out = final(execute("commit"))
    state = helper.load_json(Path(out["evidence"]))
    assert len(attempts) == 2 and state["auto_revision_used"]
    assert len(state["revisions"]) == 1
    assert state["final_review"]["checks"]["actionability"] is True
    assert "방법의 적용 조건" in state["revision_feedback"]
    assert "방법의 적용 조건" in execute.stages["reviewed"]["data"]["items"][0]["input"]["revision"]
    assert len(execute.calls) == 4  # 메타·자막을 두 번 수집하지 않는다.
    assert sum(k == "struct" for k, _ in execute.model_calls) == 4
    assert len(helper.load_json(execute.root / "db/tips.json")) == 2
    assert helper.load_json(Path(out["evidence"]).parent / "revision-1-input-finish.json")


def test_repeated_quality_rejection_stops_after_one_revision_across_reentry(execute):
    attempts = []
    def reject(args):
        attempts.append(1)
        args["data"]["items"][0]["result"]["checks"]["actionability"] = False
        args["data"]["items"][0]["result"]["issues"] = ["아직 구체 방법이 없음"]
        return args
    execute.corrupt["finish"] = reject
    assert not execute("commit")["success"]
    assert len(attempts) == 2
    assert not (execute.root / "db/tips.json").exists()
    assert not execute("commit")["success"]
    assert len(attempts) == 3  # 미완료 검수는 재실행하지만 자동 보완은 재충전하지 않는다.
    state = helper.load_json(execute.root / "_runs/test/state.json")
    assert len(state["revisions"]) == 1


@pytest.mark.parametrize("mutation", ["hash", "source", "malformed"])
def test_invalid_final_evidence_is_not_automatically_revised(execute, mutation):
    def corrupt(args):
        result = args["data"]["items"][0]["result"]
        result["checks"]["actionability"] = False
        if mutation == "hash":
            result["report_hash"] = "wrong"
        elif mutation == "source":
            helper.atomic(Path(args["run"]) / ("transcript-" + IDS[0] + ".json"),
                          {"items": [{"start": 0, "text": "변경된 원문"}]})
        else:
            result["checks"]["grounding"] = "true"
        return args
    execute.corrupt["finish"] = corrupt
    assert not execute("commit")["success"]
    state = helper.load_json(execute.root / "_runs/test/state.json")
    assert not state.get("revisions")
    assert not (execute.root / "db/tips.json").exists()


def test_empty_method_cannot_pass_content_review(execute):
    def corrupt(args):
        args["data"]["items"][0]["result"]["decisions"][0]["how"] = "  "
        return args
    execute.corrupt["reviewed"] = corrupt
    assert not execute("commit")["success"]
    assert "finish" not in execute.stages
    state = helper.load_json(execute.root / "_runs/test/state.json")
    assert not state.get("revisions")


def test_empty_transcript_segment_cannot_validate_wrong_timestamp(tmp_path):
    path = tmp_path / "source.json"
    segs = [{"start": 0, "text": ""}, {"start": 120, "text": QUOTES[0]}]
    helper.atomic(path, {"items": segs})
    state = {"sources": {IDS[0]: {"path": str(path), "hash": helper.digest(segs)}}}
    with pytest.raises(ValueError, match="시간 위치"):
        helper.grounded(state, IDS[0], {"_quote": QUOTES[0], "timestamp": "00:00"})
    helper.grounded(state, IDS[0], {"_quote": QUOTES[0], "timestamp": "02:00"})


@pytest.mark.parametrize("topic", ["교사활용", "문서업무", "코딩"])
def test_topic_is_input_through_review_and_report(execute, topic):
    out = final(execute(topic=topic))
    state = helper.load_json(Path(out["evidence"]))
    assert state["config"]["topic"] == topic
    assert topic in Path(out["report"]).read_text().splitlines()[0]
    assert execute.stages["queries"]["data"]["items"][0]["input"]["topic"] == topic
    assert execute.stages["videos"]["data"]["items"][0]["input"]["topic"] == topic
    assert execute.stages["draft"]["data"]["items"][0]["input"]["topic"] == topic
    assert set(state["final_review"]["checks"]) == set(helper.CHECKS)


def test_recent_topics_remain_ten_entries(execute):
    helper.atomic(execute.root / "_covered_videos.json",
                  {"covered": [], "recent_topics": [{"topic": str(i)} for i in range(20)]})
    final(execute("commit"))
    history = helper.load_json(execute.root / "_covered_videos.json")["recent_topics"]
    assert len(history) == 10 and history[-1]["topic"] == "복구"


def test_comparison_uses_verified_neighboring_source_not_only_anchor(tmp_path):
    path = tmp_path / "source.json"
    segs = [{"start": 40, "text": "Earlier unrelated content"},
            {"start": 60, "text": "Before the anchor"},
            {"start": 90, "text": QUOTES[0]},
            {"start": 120, "text": "Then combine the answers into one response."},
            {"start": 181, "text": "Outside the declared excerpt"}]
    helper.atomic(path, {"items": segs})
    state = {"sources": {IDS[0]: {"path": str(path), "hash": helper.digest(segs)}},
             "candidates": [{"candidate_id": "c1", "video_id": IDS[0],
                             "timestamp": "01:30", "_quote": QUOTES[0]}]}
    row = helper.comparison_candidates(state)[0]
    assert row["source_context"]["items"] == segs[1:4]
    assert row["source_context"]["scope"] == "excerpt"
    assert "source_context" not in state["candidates"][0]
    helper.atomic(path, {"items": segs[:-1]})
    with pytest.raises(ValueError, match="자막이 변경"):
        helper.comparison_candidates(state)


def test_comparison_context_counts_towards_request_limit(execute, monkeypatch):
    helper.atomic(execute.root / "db/tips.json", [{"tip": "기존", "how": "절차"}])
    original = helper.comparison_candidates
    def oversized(state):
        candidates = original(state)
        candidates[0]["source_context"]["items"][0]["text"] = "근거" * helper.REQUEST_CAP
        return candidates
    monkeypatch.setattr(helper, "comparison_candidates", oversized)
    assert not execute()["success"]
    state = helper.load_json(execute.root / "_runs/test/state.json")
    assert "candidates" in state["receipts"] and "compared" not in state["receipts"]
    assert "chosen" not in execute.stages


def large_comparison(execute, monkeypatch):
    known = [{"tip": "기존 " + str(i), "how": "서로 다른 기존 방법 " * 70} for i in range(80)]
    helper.atomic(execute.root / "db/tips.json", known)
    original = helper.comparison_candidates
    def contexts(state):
        candidates = original(state)
        for row in candidates:
            row["source_context"]["items"].append({"start": 1, "text": "보존된 이웃 문맥 " * 2300})
        return candidates
    monkeypatch.setattr(helper, "comparison_candidates", contexts)
    return known


def test_two_axis_comparison_completes_every_pair_and_reuses_plan(execute, monkeypatch):
    from collections import Counter
    known = large_comparison(execute, monkeypatch)
    final(execute())
    state = helper.load_json(execute.root / "_runs/test/state.json")
    requests = execute.stages["compared"]["data"]["items"]
    assert len(requests) > 2
    assert all(helper.request_size(r) < helper.REQUEST_CAP for r in requests)
    expected = {(cid, "k" + str(i + 1)) for cid in ("c1", "c2") for i in range(len(known))}
    actual = Counter((c["candidate_id"], k["known_id"]) for r in requests
                     for c in r["input"]["candidates"] for k in r["input"]["known"])
    assert set(actual) == expected and set(actual.values()) == {1}
    source = {r["candidate_id"]: r for r in helper.comparison_candidates(state)}
    assert all(c == source[c["candidate_id"]] for r in requests for c in r["input"]["candidates"])
    assert len(state["novelty"]["decisions"]) == sum(len(r["input"]["candidates"]) for r in requests)
    # 재진입 때 더 큰 상한을 사용할 수 있어도 이미 보낸 배치·ID·원문은 유지한다.
    monkeypatch.setattr(helper, "REQUEST_CAP", helper.REQUEST_CAP * 2)
    before = [{k: r[k] for k in ("batch_id", "task", "input")} for r in requests]
    assert helper.prepare_comparison(state)["items"] == before
    assert helper.load_json(execute.root / "db/tips.json") == known


@pytest.mark.parametrize("mutation", ["outside_candidate", "input", "missing_batch", "scope_gap", "scope_overlap"])
def test_partitioned_comparison_rejects_scope_and_input_corruption(execute, monkeypatch, mutation):
    large_comparison(execute, monkeypatch)
    def corrupt(args):
        rows = args["data"]["items"]
        if mutation == "outside_candidate":
            other = next(r for r in rows if r["input"]["candidates"][0]["candidate_id"] !=
                         rows[0]["input"]["candidates"][0]["candidate_id"])
            rows[0]["result"]["decisions"].append(other["result"]["decisions"][0])
        elif mutation == "input":
            rows[0]["input"]["candidates"][0]["source_context"]["items"].pop()
        elif mutation == "missing_batch":
            rows.pop()
        else:
            path = Path(args["run"]) / "state.json"
            state = helper.load_json(path)
            if mutation == "scope_gap":
                state["comparison_batches"].pop(rows[-1]["batch_id"])
                rows.pop()
            else:
                state["comparison_batches"]["extra"] = state["comparison_batches"][rows[0]["batch_id"]]
            helper.atomic(path, state)
        return args
    execute.corrupt["compared"] = corrupt
    assert not execute()["success"]
    assert "chosen" not in execute.stages


@pytest.mark.parametrize("missing", [False, True])
def test_partitioned_uncertain_retry_only_repairs_assigned_candidates(execute, monkeypatch, missing):
    large_comparison(execute, monkeypatch)
    repair_model(monkeypatch)
    def corrupt(args):
        if missing:
            args["data"]["items"][0]["result"]["decisions"].clear()
        else:
            force_uncertain(args)
        return args
    execute.corrupt["compared"] = corrupt
    final(execute())
    state = helper.load_json(execute.root / "_runs/test/state.json")
    repaired = helper.load_json(Path(state["run"]) / "comparison-after-retry.json")["items"]
    for wrapper in repaired:
        ids = {d["candidate_id"] for d in wrapper["result"]["decisions"]}
        assert ids == set(state["comparison_batches"][wrapper["batch_id"]]["candidate_ids"])
    first = execute.stages["compared"]["data"]["items"][0]["input"]["candidates"][0]["candidate_id"]
    assert {r["input"]["candidate"]["candidate_id"] for r in state["comparison_retry"]["requests"]} == {first}


def test_legacy_comparison_plan_keeps_original_requests(execute):
    helper.atomic(execute.root / "db/tips.json", [{"tip": "기존", "how": "다른 방법"}])
    final(execute())
    state = helper.load_json(execute.root / "_runs/test/state.json")
    for batch in state["comparison_batches"].values():
        batch.pop("candidate_ids")
    original = execute.stages["compared"]["data"]
    assert helper.prepare_comparison(state)["items"] == [
        {k: r[k] for k in ("batch_id", "task", "input")} for r in original["items"]]
    audit, _ = helper.comparison_audit(state, original)
    assert len(audit) == 2


def long_source(execute):
    filler = [{"start": float(i * 10), "text": (f"Background {i}. " + "context " * 120)}
              for i in range(1, 160)]
    source = [{"start": 0.0, "text": QUOTES[0]}, *filler,
              {"start": 1600.0, "text": "CAVEAT: Only use this method after checking the backup."},
              {"start": 1610.0, "text": QUOTES[0]}]
    execute.transcripts[IDS[0]] = source
    return source


def test_long_transcript_full_pipeline_keeps_tail_caveat_and_all_intervals(execute):
    source = long_source(execute)
    out = final(execute())
    state = helper.load_json(execute.root / "_runs/test/state.json")
    assert helper.source_segments(state, IDS[0]) == source
    plan = state["source_plan"]
    jobs = [r for r in plan["jobs"].values() if r["request"]["video_id"] == IDS[0]]
    assert len(jobs) > 4
    assert [i for r in jobs for i in range(r["first"], r["last"])] == list(
        range(len(helper.sourceflow.units(source))))
    assert set(state["source_extractions"]) == set(plan["jobs"])
    assert set(state["source_scans"]) == set(state["source_scan"]["jobs"])
    assert any(c["timestamp"] == "26:50" for c in state["candidates"])
    assert len(state["candidates"]) == 3
    for cid in state["source_evidence"]:
        evidence, scope = helper.sourceflow.evidence(helper.source_api(), state, cid)
        assert any("CAVEAT" in r["text"] for r in evidence)
        assert scope["scanned_units"] == len(helper.sourceflow.units(source))
    assert all(helper.request_size(r) < helper.REQUEST_CAP for r in state["source_scan"]["jobs"].values())
    assert "관련 위치의 선택에는 AI 판단" in Path(out["report"]).read_text()
    calls = len(execute.model_calls)
    assert final(execute()) == out
    assert len(execute.model_calls) == calls


def test_long_extraction_failure_resumes_only_unaccepted_chunks(execute):
    from collections import Counter
    long_source(execute)
    failed = []
    def once(p):
        if Path(p["file"]).stem == "chunk-" + IDS[0] + "-3" and not failed:
            failed.append(True)
            return {"success": False, "error": "fixture extraction outage"}
    execute.struct_hooks.append(once)
    assert not execute()["success"]
    state = helper.load_json(execute.root / "_runs/test/state.json")
    done = [r["request"]["path"] for k, r in state["source_plan"]["jobs"].items()
            if k in state["source_extractions"]]
    assert done and "candidates" not in state["receipts"]
    before = Counter(r["file"] for r in execute.struct_calls)
    final(execute())
    after = Counter(r["file"] for r in execute.struct_calls)
    assert all(after[p] == before[p] for p in done)


@pytest.mark.parametrize("fault", ["missing", "wrong_id", "duplicate_unit", "changed_input", "partial"])
def test_long_source_scan_rejects_incomplete_or_changed_evidence(execute, fault):
    long_source(execute)
    def corrupt(args):
        row = args["data"]["items"][0]
        decisions = row["result"]["decisions"]
        if fault == "missing":
            decisions.pop()
        elif fault == "wrong_id":
            decisions[0]["unit_ids"] = ["s99999:0"]
        elif fault == "duplicate_unit":
            unit = row["input"]["units"][0]["unit_id"]
            decisions[0]["unit_ids"] = [unit, unit]
        elif fault == "changed_input":
            row["input"]["units"][0]["text"] = "changed"
        else:
            args["data"]["partial"] = True
        return args
    execute.corrupt["source_scanned"] = corrupt
    assert not execute("commit")["success"]
    state = helper.load_json(execute.root / "_runs/test/state.json")
    assert "compared" not in state["receipts"]
    assert not (execute.root / "db/tips.json").exists()


def test_long_scan_resume_preserves_successful_siblings(execute):
    long_source(execute)
    failed = []
    def once(args):
        row = args["data"]["items"][0]
        if "-3-scan-" in row["scan_id"] and not failed:
            failed.append(True)
            row["result"]["decisions"] = []
        return args
    execute.corrupt["source_scanned"] = once
    assert not execute()["success"]
    state = helper.load_json(execute.root / "_runs/test/state.json")
    before = copy.deepcopy(state["source_scans"])
    assert before
    structs = len(execute.struct_calls)
    final(execute())
    state = helper.load_json(execute.root / "_runs/test/state.json")
    assert all(state["source_scans"][k] == v for k, v in before.items())
    # 재개 후에는 선정 후보의 상세 추출만 남는다.
    assert len(execute.struct_calls) - structs == len(state["source_detail_jobs"])


@pytest.mark.parametrize("target", ["source", "chunk", "receipt", "evidence"])
def test_long_source_mutation_cannot_pass_final_review(execute, target):
    long_source(execute)
    def corrupt(args):
        state_path = Path(args["run"]) / "state.json"
        state = helper.load_json(state_path)
        if target == "receipt":
            next(iter(state["source_scans"].values()))["response"]["result"]["decisions"][0]["reason"] = "changed"
            helper.atomic(state_path, state)
        else:
            path = (state["sources"][IDS[0]]["path"] if target == "source" else
                    next(iter(state["source_plan"]["jobs"].values()))["request"]["path"] if target == "chunk" else
                    next(iter(state["source_evidence"].values()))["path"])
            doc = helper.load_json(Path(path))
            doc["items"][0]["text"] += "changed"
            helper.atomic(Path(path), doc)
        return args
    execute.corrupt["finish"] = corrupt
    assert not execute("commit")["success"]
    assert not (execute.root / "db/tips.json").exists()


def test_long_uncertain_source_index_cannot_be_approved(execute, monkeypatch):
    long_source(execute)
    original = fixture_ai
    def respond(item):
        result = original(item)
        if "scan_id" in result:
            result["decisions"][0]["uncertain"] = True
        return result
    monkeypatch.setitem(globals(), "fixture_ai", respond)
    assert not execute("commit")["success"]
    assert not (execute.root / "db/tips.json").exists()


def test_long_single_segment_is_partitioned_without_losing_characters():
    source = [{"start": 3.0, "text": "alpha " * 15000}]
    pieces = helper.sourceflow.units(source)
    assert "".join(u["text"] for u in pieces) == source[0]["text"]
    chunks = helper.sourceflow.chunks(pieces)
    assert [i for r in chunks for i in range(r["first"], r["last"])] == list(range(len(pieces)))


def test_long_novelty_retry_uses_scanned_verbatim_evidence(execute, monkeypatch):
    long_source(execute)
    helper.atomic(execute.root / "db/tips.json", [{"tip": "기존", "how": "다른 방법"}])
    original = fixture_ai
    seen = []
    def respond(item):
        source = item["input"]
        if "repair_id" not in source:
            return original(item)
        seen.append(source)
        assert source["source_scope"] == "full_source_scan_selected_verbatim_evidence"
        assert "CAVEAT" in source["transcript"]
        return {"repair_id": source["repair_id"], "candidate_id": source["candidate"]["candidate_id"],
                "verdict": "novel", "matched_ids": [], "reason": "전 구간 색인과 원문 대조"}
    monkeypatch.setitem(globals(), "fixture_ai", respond)
    execute.corrupt["compared"] = force_uncertain
    final(execute())
    assert seen
    state = helper.load_json(execute.root / "_runs/test/state.json")
    assert isinstance(state["comparison_retry"]["scope_hash"], str)
    assert all(helper.request_size(r) < helper.REQUEST_CAP for r in state["comparison_retry"]["requests"])


def test_long_evidence_reentry_does_not_overwrite_corruption(execute):
    long_source(execute)
    final(execute())
    state = helper.load_json(execute.root / "_runs/test/state.json")
    helper.sourceflow.indexed(helper.source_api(), state)
    path = Path(next(iter(state["source_evidence"].values()))["path"])
    document = helper.load_json(path)
    document["items"][0]["text"] += "tampered"
    helper.atomic(path, document)
    with pytest.raises(ValueError, match="근거 묶음 변경"):
        helper.sourceflow.indexed(helper.source_api(), state)
    assert helper.load_json(path) == document


def test_long_revision_reuses_extraction_and_scan_but_rechecks_content(execute):
    long_source(execute)
    failures = []
    def once(args):
        if not failures:
            failures.append(True)
            for row in args["data"]["items"]:
                row["result"]["checks"]["actionability"] = False
                row["result"]["issues"] = ["구체 방법과 조건을 다시 대조할 것"]
        return args
    execute.corrupt["finish"] = once
    final(execute())
    state = helper.load_json(execute.root / "_runs/test/state.json")
    assert state["auto_revision_used"]
    assert len(execute.struct_calls) == len(state["source_plan"]["jobs"]) + len(state["source_detail_jobs"])


def test_old_long_transcript_failure_reuses_recorded_captions(execute, monkeypatch):
    long_source(execute)
    original = helper.STAGES['transcripts']
    def previous_limit(state, data):
        raise ValueError('자막이 단일 추출 상한을 넘습니다. 전체 분할 검토가 필요합니다')
    monkeypatch.setitem(helper.STAGES, 'transcripts', previous_limit)
    assert not execute()['success']
    calls = list(execute.calls)
    monkeypatch.setitem(helper.STAGES, 'transcripts', original)
    final(execute())
    assert execute.calls == calls


def test_character_parts_rejoin_without_inventing_spaces_or_times():
    for text in ('단일긴원문' * 1500, 'a natural sentence. ' * 900):
        source = [{'start': 10.0, 'text': text}]
        units = helper.sourceflow.units(source)
        assert len(units) > 2
        assert helper.sourceflow.source_rows(units) == source
        disconnected = helper.sourceflow.source_rows([units[0], units[2]])
        assert len(disconnected) == 2
        assert all(r['start'] == 10.0 for r in disconnected)
