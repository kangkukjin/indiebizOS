"""재판정·표본·복구 정보가 생산자에서 소비자까지 뜻을 보존한다."""
import boot_paths  # noqa: F401
import asyncio
import json
import shutil
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ibl_v2_adapters import decode_envelope
from ibl_v2_ir import Fault


@pytest.mark.parametrize("second,expected", [
    ({"unjudgeable": True, "reason": "판정자 응답 없음"}, "unjudged"),
    ({"pass": True}, "pass_after_retry"),
    ({"pass": False, "reason": "여전히 미달"}, "fail"),
])
@pytest.mark.parametrize("as_json", [False, True])
def test_retry_verdict_reaches_distillation(monkeypatch, tmp_path, second, expected, as_json):
    import ibl_quality as quality
    from agent_pipeline import _quality_of_result
    from ibl_distill_value import outcome_evidence
    judgments = iter([{"pass": False, "reason": "필수 근거 없음"}, second])
    calls = []
    monkeypatch.setattr(quality, "_action_config", lambda *a: {"ai_call": True})
    monkeypatch.setattr(quality, "_declared_props", lambda *a: {"instruction"})
    monkeypatch.setattr(quality, "_judge", lambda *a: next(judgments))
    tool_input = {"params": {"instruction": "근거를 포함하라"}}
    payload = {"success": True, "items": [{"text": "결과" * 600}]}

    def rerun(request):
        calls.append(request)
        return json.dumps(payload) if as_json else payload

    result = quality.apply_criteria("근거 포함", payload, tool_input, "table", "ai", ".", "test", rerun)
    raw = json.loads(result) if isinstance(result, str) else result
    assert len(calls) == 1
    assert "필수 근거 없음" in calls[0]["params"]["instruction"]
    assert raw["criteria_verdict"] == expected
    assert tool_input["_quality_meta"]["criteria_verdict"] == expected
    if expected == "fail":
        assert raw["success"] is False
        return
    assert raw["_criteria_retried"] is True
    assert raw["criteria_feedback"] == "필수 근거 없음"
    import model_result_view as view
    from supervision_store import TurnStore
    monkeypatch.setattr(view, "evidence_store", lambda: TurnStore(tmp_path / "results"))
    displayed = view.project_result(raw)
    assert displayed["criteria_verdict"] == expected
    assert displayed["criteria_feedback"] == "필수 근거 없음"
    verdict, feedback = _quality_of_result(result)
    assert (verdict, feedback) == (expected, "필수 근거 없음")
    record = json.loads(outcome_evidence([(1, {
        "result": result, "quality": verdict, "quality_feedback": feedback,
    })], None))["call_results"][0]
    assert record["quality"] == expected
    assert record["quality_feedback"] == "필수 근거 없음"
    if expected == "unjudged":
        assert "판정자 응답 없음" in raw["criteria_note"]
        assert "통과" not in raw["criteria_note"]


@pytest.mark.parametrize("reverse", [False, True])
def test_mixed_pipeline_never_promotes_unjudged(reverse):
    from agent_pipeline import _quality_of_result
    steps = [
        {"criteria_verdict": "pass_after_retry", "criteria_feedback": "앞 단계"},
        {"criteria_verdict": "unjudged", "_criteria_retried": True,
         "criteria_feedback": "뒤 단계 근거 없음"},
    ]
    if reverse:
        steps.reverse()
    assert _quality_of_result({"results": steps}) == ("unjudged", "뒤 단계 근거 없음")
    assert _quality_of_result({"_criteria_retried": True}) == (None, None)
    assert _quality_of_result({"final_result": json.dumps(steps)}) == (None, None)


@pytest.mark.parametrize("op,params", [
    ("changes", {}), ("log", {}), ("file", {"path": "backend/new/mod.py"}),
    ("diff", {}), ("writes", {}), ("trajectory", {"run_id": "fixture"}),
])
def test_body_limit_is_selection_through_adapter(monkeypatch, op, params):
    from test_body_vocab import _load, _make_repo
    import episode_logger
    body = _load()
    root = Path(_make_repo())
    monkeypatch.setattr(body, "_repo_root", lambda: str(root))
    monkeypatch.setattr(body, "_join_episode_requests", lambda *a: None)
    monkeypatch.setattr(episode_logger, "get_trajectory", lambda **kw: [
        {"event_seq": i} for i in range(4)
    ])
    try:
        (root / "readme.md").write_text("changed\n")
        (root / "backend/new/mod.py").write_text("changed\n")
        (root / "data").mkdir()
        (root / "data/write_ledger.jsonl").write_text("\n".join(
            json.dumps({"ts": datetime.now().isoformat(), "path": f"outputs/{i}"})
            for i in range(3)
        ))
        result = getattr(body, f"op_{op}")({**params, "limit": 1})
        assert result["success"] and result["truncated"]
        assert result["total"] > len(result["items"]) == 1
        value, evidence = decode_envelope(result, {"value_path": "/items"})
        assert value == result["items"]
        assert evidence["markers"]["truncations"][0]["scope"] == "selection"
        whole = getattr(body, f"op_{op}")({**params, "limit": 1000})
        assert not whole["truncated"]
        assert not whole.get("truncations")
    finally:
        shutil.rmtree(root)


@pytest.mark.parametrize("extra", [
    {}, {"truncations": [{"scope": "source"}]},
    {"truncations": [{"scope": "selection"}], "rows_dropped": 1},
])
def test_real_source_loss_still_fails(extra):
    with pytest.raises(Fault) as caught:
        decode_envelope({"success": True, "items": [1], "truncated": True, **extra}, {})
    assert caught.value.code == "PARTIAL_SOURCE"


def test_browser_recovery_survives_error_boundary(monkeypatch, tmp_path):
    from test_episode4023_repairs import load, PACKAGES
    monkeypatch.syspath_prepend(str(PACKAGES / "browser-action"))
    browser = load("browser-action/browser_interact.py")
    monkeypatch.setattr(browser, "check_stale_ref", lambda *a: None)
    monkeypatch.setattr(browser, "find_locator", AsyncMock(return_value=None))
    session = SimpleNamespace(get_ref=lambda ref: {"role": "button", "name": "closed menu"})
    locator, error = asyncio.run(browser._resolve_locator(session, object(), {"ref": "e55"}))
    assert locator is None
    with pytest.raises(Fault) as caught:
        decode_envelope(error, {})
    assert caught.value.code == "TOOL"
    assert caught.value.details["error_code"] == "REF_NOT_RESOLVED"
    assert caught.value.details["recovery"] == error["recovery"]
    import model_result_view as view
    from supervision_store import TurnStore
    monkeypatch.setattr(view, "evidence_store", lambda: TurnStore(tmp_path / "results"))
    displayed = view.project_v2_result({"edition": 2, "success": False, "error": caught.value.view()})
    assert displayed["error"]["details"]["recovery"] == error["recovery"]


def test_unjudged_reaches_actual_distillation_prompt(monkeypatch, tmp_path):
    from test_distill_source_recovery_2026_09_09 import _arm
    rag, stored, asked, runs = _arm(monkeypatch, tmp_path, [])
    prepared = rag.prepare_experience("근거 있는 요약", [{
        "tool_name": "execute_ibl", "input": {"code": '[table:ai]{instruction:"근거 포함"}'},
        "success": True, "quality": "unjudged", "quality_feedback": "필수 근거 없음",
        "result": {"items": [{"text": "매우 긴 결과" * 1000}], "criteria_verdict": "unjudged"},
    }], 0)
    assert prepared
    assert '"quality": "unjudged"' in prepared["prompt"]
    assert "필수 근거 없음" in prepared["prompt"]
    assert "재시도 후에야 통과했다" not in prepared["prompt"]
    assert stored == asked == runs == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
