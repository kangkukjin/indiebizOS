"""증거의 JSON 구조·마스킹 경로·읽기/입력 참조 계약."""
import json

import boot_paths  # noqa: F401
import pytest

import model_result_view as view
from supervision_store import TurnStore, _ledger_turns


@pytest.mark.parametrize("separator", ["\u0085", "\u2028", "\u2029", "\n"])
def test_jsonl_tool_index_preserves_text_separators(tmp_path, separator):
    store = TurnStore(tmp_path)
    text = f"원문 앞{separator}원문 뒤"
    inp = store.evidence({"query": text})
    result = store.evidence(text)
    store.log("tool.started", id="read", name="read", input=inp)
    store.log("tool.finished", id="read", evidence=result, is_error=False)
    calls = store.tool_index()
    assert len(calls) == 1
    assert calls[0]["input"]["id"] == inp["id"]
    assert calls[0]["result"]["id"] == result["id"]
    assert store.read_evidence(calls[0]["result"]["id"], 0, None)["text"] == text
    assert [e["seq"] for e in store.read_events()["events"]] == [1, 2]


def test_jsonl_tool_index_does_not_hide_malformed_records(tmp_path):
    store = TurnStore(tmp_path)
    (tmp_path / "events.jsonl").write_text('{"kind": "unfinished\n', encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        store.tool_index()


def test_lineage_jsonl_preserves_unicode_in_metadata(tmp_path):
    ledger = tmp_path / "lineage.jsonl"
    records = [{"turn": "first", "note": "앞\u2028중간\u2029뒤"}, {"turn": "second"}]
    ledger.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
                      encoding="utf-8")
    assert _ledger_turns(ledger) == ["first", "second"]


@pytest.mark.parametrize("serialized", [False, True])
def test_masked_web_example_keeps_json_and_unaffected_branch_readable(tmp_path, monkeypatch, serialized):
    store = TurnStore(tmp_path)
    monkeypatch.setattr(view, "evidence_store", lambda: store)
    secret = "DEMO_KEY_PLACEHOLDER"
    value = {"value": {"pages": [
        {"text": "Cresta 날짜·본문", "count": 7},
        {"text": f'curl -H "x-api-key: {secret}" \\\n https://example.invalid'},
    ]}}
    raw = json.dumps(value, ensure_ascii=False) if serialized else value
    ref = store.evidence(raw)
    page = store.read_evidence(ref["id"], 0, None)
    masked = json.loads(page["text"])
    assert secret not in page["text"]
    assert masked["value"]["pages"][0] == value["value"]["pages"][0]
    assert ref["masked_paths"] == [["value", "pages", 1, "text"]]
    clean = view.read_result({"id": ref["id"], "path": ["value", "pages", 0]})
    assert json.loads(clean["text"]) == value["value"]["pages"][0]
    resolved, _ = view.resolve_input_refs(clean["input_args"], store=store)
    assert resolved["입력"] == value["value"]["pages"][0]
    masked_page = view.read_result({"id": ref["id"], "path": ["value", "pages", 1]})
    assert "input_unavailable" in masked_page
    with pytest.raises(ValueError, match="가린 자리"):
        view.resolve_input_refs({"x": {"$ref": ref["id"]}}, store=store)
    assert secret in (raw if isinstance(raw, str) else raw["value"]["pages"][1]["text"])


@pytest.mark.parametrize("raw", ['{ "n": 2, "text": "본문" }', '[1, 2]', '"문자열"', 'null', '42'])
def test_unmasked_serialized_evidence_preserves_exact_original_bytes(tmp_path, raw):
    store = TurnStore(tmp_path)
    ref = store.evidence(raw)
    assert store.read_evidence(ref["id"], 0, None)["text"] == raw
    assert not ref.get("masked_paths")


def test_plain_prose_and_json_string_secrets_remain_masked(tmp_path):
    store = TurnStore(tmp_path)
    for raw in ('password: DEMO_KEY_PLACEHOLDER', json.dumps('password: DEMO_KEY_PLACEHOLDER')):
        ref = store.evidence(raw)
        text = store.read_evidence(ref["id"], 0, None)["text"]
        assert "DEMO_KEY_PLACEHOLDER" not in text
        assert ref["masked_paths"] == [[]]
        if raw.startswith('"'):
            assert "****" in json.loads(text)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
