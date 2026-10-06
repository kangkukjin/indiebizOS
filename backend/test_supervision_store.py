"""증거의 JSON 구조·마스킹 경로·읽기/입력 참조 계약."""
import json

import boot_paths  # noqa: F401
import pytest

import model_result_view as view
from supervision_store import TurnStore


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
