"""Jev 없이 배치/통화/불명/오류 계약 검증. 실 API 시험은 가이드에 기록한다."""
import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import boot_paths  # noqa: F401, E402

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "data/packages/installed/tools/ai-ops"
spec = importlib.util.spec_from_file_location("table_judge_test_module", PKG / "ai_ops_judge.py")
judge_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(judge_module)


@pytest.fixture
def mocked(monkeypatch):
    calls = []

    def request(payload):
        calls.append(copy.deepcopy(payload))
        answers = {}
        for key, question in payload["questions"].items():
            if question["type"] == "noul":
                answers[key] = {"type": "noul", "noul": 0.95}
            elif question["type"] == "choice":
                options = list(question["criteria"])
                answers[key] = {"type": "choice", "choice": options[0], "confidence": 0.9,
                                "probabilities": {k: float(i == 0) for i, k in enumerate(options)}}
            else:
                levels = question["criteria"]
                answers[key] = {"type": "score", "score": 0, "confidence": 0.9,
                                "legend": {str(i): s for i, s in enumerate(levels)},
                                "probabilities": {str(i): float(i == 0) for i in range(len(levels))}}
        return {"success": True, "data": {"answers": answers, "model": "jev-test",
                "usage": {"input_tokens": 40, "output_tokens": 20}}, "latency_ms": 1}

    monkeypatch.setattr(judge_module, "_request", request)
    return calls


def test_mixed_questions_batch_preserves_rows(mocked):
    rows = [{"id": 10, "text": "환불 요청", "nested": {"a": [1]}}, {"id": 20, "text": "문의"}]
    before = copy.deepcopy(rows)
    result = judge_module.judge({"items": rows, "questions": {
        "환불": {"instruction": "환불을 요청하는가?"},
        "종류": {"type": "choice", "instruction": "주요 요청은?", "criteria": {"refund": None, "other": "기타"}},
        "긴급성": {"type": "score", "instruction": "긴급성 수준?", "criteria": ["낮음", "높음"]},
    }})
    assert result["success"] and len(mocked) == 1
    assert rows == before
    assert result["rows_in"] == result["rows_out"] == 2
    assert result["questions_evaluated"] == 6
    assert result["usage"] == {"input_tokens": 40, "output_tokens": 20}
    for i, row in enumerate(result["items"]):
        assert {k: v for k, v in row.items() if not k.startswith("judgment_")} == rows[i]
        assert row["judgment_환불_value"] is True
        assert row["judgment_종류_value"] == "refund"
        assert row["judgment_긴급성_value"] == 0
        for j in range(3):
            assert f"`items[{i}]`" in mocked[0]["questions"][f"r{i}q{j}"]["instructions"]


@pytest.mark.parametrize("probability,value,status", [
    (0.8, True, "decided"), (0.2, False, "decided"), (0, False, "decided"),
    (1, True, "decided"), (0.5, None, "unknown"), (0.79, None, "unknown"),
])
def test_boolean_uncertainty_and_boundaries(probability, value, status):
    answer = judge_module._answer({"type": "noul", "noul": probability}, {"type": "boolean"}, 0.8)
    assert answer["value"] is value and answer["status"] == status
    assert "confidence" not in answer


@pytest.mark.parametrize("kind", ["choice", "score"])
def test_low_confidence_retains_raw_but_not_actionable_value(kind):
    criteria = {"a": "A", "b": "B"} if kind == "choice" else ["A", "B"]
    raw = {"type": kind, "confidence": 0.1,
           "probabilities": {"a": 0.5, "b": 0.5} if kind == "choice" else {"0": 0.5, "1": 0.5}}
    raw.update({"choice": "a"} if kind == "choice" else {"score": 0.5, "legend": {"0": "A", "1": "B"}})
    answer = judge_module._answer(raw, {"type": kind, "criteria": criteria}, 0.8)
    assert answer["value"] is None and answer["status"] == "unknown"
    assert answer[kind] == raw[kind]


@pytest.mark.parametrize("params", [
    {"items": []}, {"_prev_result": '{"items": []}'},
])
def test_empty_never_calls_provider(params, mocked):
    result = judge_module.judge({**params, "instruction": "관련 있는가?"})
    assert result["success"] and result["items"] == [] and result["api_calls"] == 0
    assert not mocked


@pytest.mark.parametrize("params", [
    {}, {"items": [1]}, {"items": None}, {"items": [{"judgment_result_value": "original"}]},
    {"items": [{}] * 101}, {"items": [{"text": "가" * 60_000}]},
    {"items": [{}], "threshold": 0.5}, {"items": [{}], "threshold": True},
    {"items": [{}], "threshold": float("nan")}, {"items": [{}], "type": "chat"},
    {"items": [{}], "type": "choice", "criteria": {"a": "A"}},
    {"items": [{}], "type": "score", "criteria": ["A"]},
    {"items": [{}], "criteria": {"true": "yes"}},
    {"items": [{}], "questions": {"q": {"instruction": "判定"}}},
    {"_prev_result": {"success": False, "items": [], "error": "failed"}},
])
def test_invalid_inputs_fail_before_paid_call(params, mocked):
    result = judge_module.judge({"instruction": "관련 있는가?", **params})
    assert not result["success"] and result["api_calls"] == 0 and not mocked


def test_explicit_items_and_custom_field(mocked):
    result = judge_module.judge({"items": '[{"judgment_result_value":"keep"}]', "as": "재판정", "instruction": "맞나?"})
    assert result["success"] and result["items"][0]["judgment_result_value"] == "keep"
    assert result["items"][0]["재판정_result_value"] is True


@pytest.mark.parametrize("answers", [
    {}, {"r0q0": {"type": "noul", "noul": 2}},
    {"r0q0": {"type": "noul", "noul": True}},
    {"r0q0": {"type": "choice", "choice": "x"}},
    {"r0q0": {"type": "noul", "noul": 0.9}, "extra": {}},
])
def test_bad_provider_response_has_no_success_currency(monkeypatch, answers):
    monkeypatch.setattr(judge_module, "_request", lambda _: {
        "success": True, "data": {"answers": answers}, "latency_ms": 1})
    result = judge_module.judge({"items": [{}], "instruction": "맞나?"})
    assert not result["success"] and result["error_type"] == "response"
    assert "items" not in result


def test_transport_does_not_expose_provider_error_or_follow_redirect(monkeypatch):
    import requests
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(status_code=401, text="sensitive-key-and-input")

    monkeypatch.setattr(judge_module, "_key", lambda: "test-only-secret")
    monkeypatch.setattr(requests, "post", post)
    result = judge_module._request({"state": "private"})
    assert result["api_calls"] == 1 and not result["success"]
    assert "sensitive" not in json.dumps(result) and "test-only-secret" not in json.dumps(result)
    assert calls[0][1]["allow_redirects"] is False and len(calls) == 1


def test_network_failure_never_becomes_false_or_retries(monkeypatch):
    import requests
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        raise requests.Timeout("secret reflected in exception")

    monkeypatch.setattr(judge_module, "_key", lambda: "test-only-secret")
    monkeypatch.setattr(requests, "post", post)
    result = judge_module._request({})
    assert not result["success"] and result["error_type"] == "network"
    assert len(calls) == 1 and "secret" not in json.dumps(result)


def test_usage_is_recorded_once(monkeypatch):
    import requests
    from providers.base import ProviderMetrics
    recorded = []
    usage = {"input_tokens": 123, "output_tokens": 12}
    monkeypatch.setattr(judge_module, "_key", lambda: "test-only-secret")
    monkeypatch.setattr(requests, "post", lambda *a, **k: SimpleNamespace(
        status_code=200, json=lambda: {"answers": {}, "usage": usage}))
    monkeypatch.setattr(ProviderMetrics, "record_usage", lambda self, ms, u, **k: recorded.append(u))
    assert judge_module._request({})["success"]
    assert recorded == [usage]


@pytest.mark.parametrize("criteria", [{"a": "A", "b": "B"}, "잘못된 타입도 핸들러가 거절"])
def test_criteria_belongs_to_action_not_extra_llm_quality_check(criteria):
    from ibl_quality import pop_criteria
    ti = {"_node": "table", "action": "judge", "params": {
        "instruction": "분류", "type": "choice", "criteria": criteria}}
    before = copy.deepcopy(ti)
    assert pop_criteria(ti) is None
    assert ti == before


def test_documented_seeds_parse():
    from ibl_param_vocab import code_syntax_error
    seeds = json.loads((ROOT / "data/packages/installed/tools/ai-ops/judge_examples.json").read_text())
    for seed in seeds:
        assert not code_syntax_error(seed["ibl_code"]), seed["intent"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
