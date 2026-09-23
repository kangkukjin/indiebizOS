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
            {"video_id": r["video_id"], "reason": "서로 다른 복구 방식",
             "source_assessment": "제공 채널 정보만 확인, 전문성 미확인",
             "popularity_assessment": "제공된 반응 수치 범위에서 평가"} for r in source["videos"]]}
    if "keep:boolean" in task:
        return {"decisions": [{"candidate_id": r["candidate_id"], "keep": True,
                               "reason": "이번 후보 중 실행 가능한 구체 방법",
                               "source_assessment": "출처 정보의 한계를 인지함",
                               "popularity_assessment": "인기만으로 가치를 판정하지 않음",
                               "value_assessment": "원문에 실행 가능한 복구 행동이 있어 시험할 가치"} for r in source["candidates"]]}
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
    model_calls, ai_inputs = [], []
    transcripts, struct_calls, struct_hooks = {}, [], []
    metadata_overrides = {}
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
                        "uploader": "Fixture Channel", "duration": 240, "upload_date": "2026-09-01", **metadata_overrides.get(vid, {})}]}
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
            ai_inputs.extend(copy.deepcopy(inputs))
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
    run.model_calls, run.ai_inputs = model_calls, ai_inputs
    run.transcripts, run.struct_calls, run.struct_hooks = transcripts, struct_calls, struct_hooks
    run.metadata_overrides = metadata_overrides
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
    ("finish", lambda data: data["items"][0]["result"]["checks"].update(within_report_uniqueness=False)),
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
    prepare = helper.prepare_selection
    def blocked(state):
        raise ValueError("fixture: 다음 요청 입력 상한")
    monkeypatch.setattr(helper, "prepare_selection", blocked)
    assert not execute()["success"]
    directory = execute.root / "_runs/test"
    state = helper.load_json(directory / "state.json")
    assert "candidates" in state["receipts"] and len(state["candidates"]) == 2
    before = list(execute.model_calls)
    response = helper.run({"op": "candidates", "run": str(directory), "data": {"items": []}})
    assert response["status"] == "blocked" and response["accepted"]
    assert response["resume"]["op"] == "candidates"
    assert helper.load_json(directory / "state.json")["preparation_failure"] == response
    monkeypatch.setattr(helper, "prepare_selection", prepare)
    assert final(execute())["status"] == "reviewed_draft"
    # 앞 단계 table:ai와 1차 struct 호출을 반복하지 않는다.
    assert execute.model_calls[:len(before)] == before
    assert sum(k == "struct" and "candidate_id" not in v for k, v in execute.model_calls) == 2
    assert "preparation_failure" not in helper.load_json(directory / "state.json")


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


def test_quote_crossing_two_partial_segments_keeps_source_time(tmp_path):
    # Episode 4016: neither whole segment is inside the quote, but the quote
    # is an exact continuous span starting at 1757.279 seconds.
    segs = [
        {"start": 1757.279, "text": "layers. So it depends on which layer you"},
        {"start": 1759.679, "text": "want to add these LLM test in. You can"},
    ]
    path = tmp_path / "source.json"
    helper.atomic(path, {"items": segs})
    state = {"sources": {IDS[0]: {"path": str(path), "hash": helper.digest(segs)}}}
    row = {"_quote": "So it depends on which layer you\nwant to add these LLM test in.",
           "timestamp": "29:17"}
    helper.grounded(state, IDS[0], row)
    with pytest.raises(ValueError, match="시간 위치"):
        helper.grounded(state, IDS[0], {**row, "timestamp": "00:00"})


def test_shared_short_segment_does_not_prove_quote_location(tmp_path):
    segs = [{"start": 0, "text": "the"},
            {"start": 120, "text": "Review the complete evidence before publishing."}]
    path = tmp_path / "source.json"
    helper.atomic(path, {"items": segs})
    state = {"sources": {IDS[0]: {"path": str(path), "hash": helper.digest(segs)}}}
    row = {"_quote": segs[1]["text"], "timestamp": "00:00"}
    with pytest.raises(ValueError, match="시간 위치"):
        helper.grounded(state, IDS[0], row)
    helper.grounded(state, IDS[0], {**row, "timestamp": "02:00"})


def test_quote_location_checks_later_occurrences_and_normalized_text(tmp_path):
    segs = [{"start": 0, "text": "prefix ＡＢＣ"}, {"start": 4, "text": "def suffix"},
            {"start": 120, "text": "prefix ABC"}, {"start": 124, "text": "def suffix"}]
    path = tmp_path / "source.json"
    helper.atomic(path, {"items": segs})
    state = {"sources": {IDS[0]: {"path": str(path), "hash": helper.digest(segs)}}}
    helper.grounded(state, IDS[0], {"_quote": "ABC\n def", "timestamp": "02:00"})
    with pytest.raises(ValueError, match="원문에 없는"):
        helper.grounded(state, IDS[0], {"_quote": "ABC invented def", "timestamp": "02:00"})


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
    assert "source_requests" not in execute.stages
    assert "sources_indexed" not in execute.stages
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
    assert "chosen" not in state["receipts"]
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


def test_publisher_and_popularity_reach_video_choice_tip_choice_review_and_report(execute):
    observed = '2026-09-24T00:00:00+00:00'
    execute.metadata_overrides[IDS[0]] = {
        'view_count': 123456, 'like_count': 3210, 'comment_count': 56,
        'channel_follower_count': 7890, 'channel_is_verified': True,
        'channel_id': 'UCsource', 'channel_url': 'https://www.youtube.com/@source',
        'description': 'Publisher describes firsthand implementation. ' * 100,
        'observed_at': observed}
    execute.metadata_overrides[IDS[1]] = {'view_count': 0, 'like_count': None}
    result = final(execute())
    state = helper.load_json(execute.root / '_runs/test/state.json')
    requests = execute.stages['videos']['data']['items'][0]['input']['videos']
    assert requests[0]['view_count'] == 123456 and requests[0]['description_truncated']
    assert requests[1]['view_count'] == 0 and requests[1]['like_count'] is None
    profiles = execute.stages['chosen']['data']['items'][0]['input']['source_profiles']
    assert profiles[0]['channel_id'] == 'UCsource' and profiles[0]['observed_at'] == observed
    assert profiles[0]['selection_assessment']['source_assessment']
    reviews = execute.stages['reviewed']['data']['items']
    first = next(r for r in reviews if r['video_id'] == IDS[0])
    assert first['input']['video']['view_count'] == 123456
    assert first['input']['tip_selections']
    finish = execute.stages['finish']['data']['items'][0]['input']
    assert finish['videos'][0]['view_count'] == 123456 and finish['tip_selections']
    report = Path(result['report']).read_text()
    assert '조회 123,456' in report and '조회 0' in report and '좋아요 미확인' in report
    assert '선정 가치 판단' in report and '출처 판단' in report and observed in report
    assert state['video_decisions'][IDS[0]]['popularity_assessment']


@pytest.mark.parametrize('stage,field', [('videos', 'source_assessment'), ('videos', 'popularity_assessment'),
                                        ('chosen', 'source_assessment'), ('chosen', 'popularity_assessment'),
                                        ('chosen', 'value_assessment')])
def test_missing_selection_judgment_cannot_pass(execute, stage, field):
    def corrupt(args):
        args['data']['items'][0]['result']['decisions'][0].pop(field)
        return args
    execute.corrupt[stage] = corrupt
    assert not execute('commit')['success']
    assert not (execute.root / 'db/tips.json').exists()
    if stage == 'videos':
        assert not any(op == 'transcript' for op, _ in execute.calls)


def test_sixty_candidates_keep_identity_and_metrics_with_explicit_description_excerpts():
    ids = [f'{i:011d}' for i in range(60)]
    state = {'config': {'date': '2026-09-24', 'topic': '평가'}, 'run': '/fixture',
             'search': {'candidates': [{'video_id': vid, 'strata': ['english']} for vid in ids]}}
    wrappers = [{'video_id': vid, 'data': {'items': [{'video_id': vid, 'title': 'A detailed source title ' * 4,
                 'duration': 120, 'uploader': 'Source Publisher', 'upload_date': '2026-09-20',
                 'description': 'Publisher disclosure and described expertise. ' * 200,
                 'view_count': i, 'like_count': None, 'channel_url': 'https://www.youtube.com/@publisher',
                 'observed_at': '2026-09-24T00:00:00+00:00'}]}} for i, vid in enumerate(ids)]
    request = helper.stage_metadata(state, {'items': wrappers})['items'][0]
    assert helper.request_size(request) < helper.REQUEST_CAP
    assert [r['video_id'] for r in request['input']['videos']] == ids
    assert [r['view_count'] for r in request['input']['videos']] == list(range(60))
    assert all(r['description_truncated'] and r['like_count'] is None for r in request['input']['videos'])


def test_selection_remains_ai_judgment_and_captions_only_follow_selected_videos():
    ids = ['a' * 11, 'b' * 11, 'c' * 11]
    state = {'config': {'date': '2026-09-24', 'topic': '평가'}, 'run': '/fixture',
             'search': {'candidates': [{'video_id': vid, 'strata': [s]} for vid, s in zip(ids, ['english','korean','action'])]}}
    wrappers = [{'video_id': vid, 'data': {'items': [{'video_id': vid, 'title': vid, 'duration': 60,
                 'uploader': 'Publisher', 'upload_date': '2026-09-20', 'view_count': n}]}}
                for vid, n in zip(ids, [1000000, 10, 0])]
    helper.stage_metadata(state, {'items': wrappers})
    decision = {'selected': ids[1:], 'decisions': [{'video_id': vid, 'reason': '전문 출처와 구체 행동 우선',
                 'source_assessment': '제공 정보 범위에서 출처를 평가',
                 'popularity_assessment': '많은 조회수가 낮은 실용성을 보상하지 않음'} for vid in ids]}
    decision['decisions'][0].pop('source_assessment')
    decision['decisions'][0].pop('popularity_assessment')
    result = helper.stage_videos(state, {'items': [{'result': decision}]})
    assert [r['video_id'] for r in result['items']] == ids[1:]
    assert result['items'][1]['view_count'] == 0


@pytest.mark.parametrize('bad', [True, -1, '1000', 2.5, None])
def test_bad_or_missing_popularity_is_unknown_not_zero(bad):
    result = helper.selection.source_fields({'view_count': bad})
    assert result['view_count'] is None
    assert helper.selection.source_fields({'view_count': 0})['view_count'] == 0


@pytest.mark.parametrize("size", [0, 655, 2000])
def test_prior_tip_count_does_not_add_model_calls_or_feed_history(execute, size):
    marker = "OLD_TIP_BODY_NOT_FOR_AI"
    old = [{"tip": TITLES[i % 2], "topic": "복구",
            "how": TITLES[i % 2] if i < 2 else marker * 50, "note": marker} for i in range(size)]
    helper.atomic(execute.root / "db/tips.json", old)
    helper.atomic(execute.root / "ai_tips_report_2026-09-22_old.md", marker, text=True)
    out = final(execute("commit"))
    assert out["new_tips"] == 2 and out["tips"] == size + 2
    assert helper.load_json(execute.root / "db/tips.json")[:size] == old
    assert sum(k == "ai" for k, _ in execute.model_calls) == 7
    assert len(execute.struct_calls) == 4
    assert all("known" not in r for r in execute.struct_calls)
    assert marker not in json.dumps(execute.ai_inputs)
    for request in execute.ai_inputs:
        source = request["input"]
        assert not {"known", "novelty", "novelty_scope", "previous_report"}.intersection(source)
    assert not {"compared", "comparison_retry", "comparison_repair"}.intersection(execute.stages)
    assert "within_report_uniqueness" in execute.stages["finish"]["data"]["items"][0]["result"]["checks"]
    before = copy.deepcopy(execute.model_calls)
    assert final(execute("commit")) == out
    assert execute.model_calls == before


def test_previously_handled_video_is_excluded_before_metadata_and_transcript(execute):
    old_id = "oldvideo123"
    assert len(old_id) == 11
    helper.atomic(execute.root / "_covered_videos.json", {
        "covered": [{"id": old_id, "verdict": "tips_1"}], "recent_topics": []})
    execute.search_responses.update({s: {"success": True, "items": [
        {"video_id": old_id}, *[{"video_id": vid} for vid in IDS]]} for s in helper.STRATA})
    final(execute())
    assert all(vid != old_id for _, vid in execute.calls)
    assert set(execute.calls) == {(op, vid) for op in ("info", "transcript") for vid in IDS}


def test_final_review_rejects_overlarge_report_without_silent_truncation(execute):
    final(execute())
    state = helper.load_json(execute.root / "_runs/test/state.json")
    request = copy.deepcopy(execute.stages["finish"]["data"])
    request["items"][0]["input"]["markdown"] = "x" * helper.REQUEST_CAP
    with pytest.raises(ValueError, match="상한"):
        helper.final_review_tasks(state, request)


def test_new_default_run_preserves_old_state_and_removed_ops_cannot_resume(tmp_path):
    config = {"root": str(tmp_path), "topic": "복구", "date": "2026-09-24"}
    old_dir = tmp_path / "_runs" / (config["date"] + "-" + helper.digest(config["topic"])[:12])
    old = {"version": 2, "run": str(old_dir), "config": config, "marker": "old evidence"}
    helper.atomic(old_dir / "state.json", old)
    before = (old_dir / "state.json").read_bytes()
    result = helper.start(config)
    assert result["run"] != str(old_dir) and result["run"].endswith("-v3")
    for op in ("compared", "comparison_retry", "comparison_repair", "sources_indexed"):
        with pytest.raises(ValueError, match="버전"):
            helper.run({"op": op, "run": str(old_dir), "data": {"items": []}})
    assert (old_dir / "state.json").read_bytes() == before
    for op in ("compared", "comparison_retry", "comparison_repair"):
        with pytest.raises(ValueError, match="알 수 없는 단계"):
            helper.run({"op": op, "run": result["run"], "data": {"items": []}})
