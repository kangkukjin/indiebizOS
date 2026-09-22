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
    if "queries:[{stratum,query}]" in task:
        return {"queries": [{"stratum": s, "query": "AI tips " + s} for s in helper.STRATA]}
    if "selected:[영상ID]" in task:
        return {"selected": list(IDS), "decisions": [
            {"video_id": r["video_id"], "reason": "서로 다른 복구 방식"} for r in source["videos"]]}
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
        return {"report_hash": source["report_hash"], "checks": {k: True for k in helper.CHECKS},
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
            return {"success": True, "items": [{"video_id": vid} for vid in IDS]}
        if node == "sense" and act == "video":
            vid = p["video_id"]
            calls.append((p["op"], vid))
            if p["op"] == "info":
                return {"success": True, "items": [{"video_id": vid, "title": "Fixture " + vid,
                        "uploader": "Fixture Channel", "duration": 240, "upload_date": "2026-09-01"}]}
            return {"success": True, "items": [{"start": 0.0, "duration": 8.0,
                                               "text": QUOTES[IDS.index(vid)]}]}
        if node == "self" and act == "struct":
            model_calls.append(("struct", p["schema"]))
            vid = Path(p["file"]).stem.removeprefix("transcript-")
            n = IDS.index(vid)
            assert isinstance(p["schema"], str)
            source = helper.load_json(Path(p["file"]))
            assert source["transcript"] == "\n".join(r["text"] for r in source["items"])
            record = {"tip": TITLES[n], "timestamp": "00:00", "_quote": QUOTES[n]}
            if "candidate_id" in p["schema"]:
                state = helper.load_json(Path(p["file"]).parent / "state.json")
                chosen = next(r for r in state["chosen"] if r["video_id"] == vid)
                record.update(candidate_id=chosen["candidate_id"], how=TITLES[n], tools=None, hype="")
            assert p["grounded"] is True
            return {"success": True, "grounded": True, "timestamp_grounded": 1, "items": [record]}
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
    def run(mode="draft", named=True):
        config = {"root": str(tmp_path / "reports"), "date": "2026-09-23", "topic": "복구",
                  "mode": mode, "run_id": "test"}
        code = ("[fn:AI팁보고서쓰기]" + json.dumps({"설정": config}, ensure_ascii=False) if named else
                "$설정=" + json.dumps(config, ensure_ascii=False) + "\n" + BODY)
        steps, _ = parse_with_vars(code)
        return workflow_engine.execute_pipeline(steps, str(tmp_path))
    run.stages, run.calls, run.corrupt = stages, calls, corrupt
    run.root = tmp_path / "reports"
    run.model_calls = model_calls
    return run


def final(result):
    assert result["success"], str(result.get("error") or result.get("traceback") or result)[-3000:]
    return helper.rows(helper.unpack(result["final_result"]))[0]


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
    assert helper.load_json(directory / "revision-1.json") == before
    assert helper.load_json(directory / "revision-1-input-finish.json")
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
    monkeypatch.setattr(helper, "prepare_comparison", prepare)
    assert final(execute())["status"] == "reviewed_draft"
    # 앞 단계 table:ai와 1차 struct 호출을 반복하지 않는다.
    assert execute.model_calls[:len(before)] == before
    assert sum(k == "struct" and "candidate_id" not in v for k, v in execute.model_calls) == 2


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
        assert source["novelty"]["known_count"] == 647
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


def test_structural_criteria_removed_but_semantic_review_remains():
    assert "criteria:" not in BODY
    assert BODY.count("preserve_rows:true") == 7
    assert 'op:"reviewed"' in BODY and 'op:"finish"' in BODY
    assert "원문과 팁을 독립 대조" in BODY and "품질 기준을 독립 검토" in BODY
