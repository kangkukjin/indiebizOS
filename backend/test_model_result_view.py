"""Result-reference identity: certified content, historical evidence, and tampering."""
import boot_paths  # noqa: F401
import json

import pytest

import model_result_view as view
from ibl_v2_ir import digest, pack
from supervision_store import TurnStore


def envelope(value, *, complete=True):
    return {"edition": 2, "success": True, "source_complete": complete,
            "value": value, "value_wire": {"protocol": "ibl-value/1", "data": pack(value)},
            "resume": {"run_id": "original-run"},
            "evidence": [{"kind": "ref", "parents": [i]} for i in range(300)]}


def test_certified_reference_avoids_rehashing_trace_and_keeps_status(tmp_path, monkeypatch):
    import ibl_v2_ir
    store = TurnStore(tmp_path / "evidence")
    original = envelope({"rows": [{"qty": 3}], "source_complete": True}, complete=False)
    ref = store.evidence(original)
    real_digest = ibl_v2_ir.digest

    def bounded_digest(value):
        assert not (isinstance(value, dict) and "evidence" in value), "rehashed full trace"
        return real_digest(value)

    monkeypatch.setattr(ibl_v2_ir, "digest", bounded_digest)
    values, notes = view.resolve_input_refs({
        "a": {"$ref": ref['id']},
        "nested": [{"row": {"$ref": ref['id'], "path": ["value", "rows", 0]}}],
    }, store=store)
    assert values == {"a": original['value'], "nested": [{"row": {"qty": 3}}]}
    assert notes[0]['evidence'] == notes[1]['evidence']
    assert notes[0]['evidence'] == {
        "fingerprint": digest({"certified_evidence": ref['id']}),
        "fingerprint_scheme": "certified-evidence/1", "incomplete": True,
        "execution_success": True, "run_id": "original-run"}


def test_changed_certified_content_changes_identity_and_old_scheme_remains(tmp_path):
    store = TurnStore(tmp_path / "evidence")
    first, second = envelope({"n": 1}), envelope({"n": 2})
    refs = [store.evidence(v) for v in [first, second]]
    args = {"x": {"$ref": refs[0]['id']}}
    _, new = view.resolve_input_refs(args, store=store)
    _, changed = view.resolve_input_refs({"x": {"$ref": refs[1]['id']}}, store=store)
    assert new[0]['evidence']['fingerprint'] != changed[0]['evidence']['fingerprint']
    restored, old = view.resolve_input_refs(args, store=store, legacy_fingerprints=True)
    assert restored['x'] == first['value']
    assert old[0]['evidence'] == view.input_ref_evidence(first)
    assert old[0]['evidence']['fingerprint'] == digest(first)


@pytest.mark.parametrize("damage", ["text", "certificate", "masked"])
def test_certified_identity_never_bypasses_integrity_or_masking(tmp_path, damage):
    store = TurnStore(tmp_path / "evidence")
    ref = store.evidence(envelope({"n": 1}))
    if damage == "text":
        (store.directory / (ref['id'] + '.txt')).write_text(json.dumps(envelope({"n": 2})))
    elif damage == "certificate":
        (store.directory / (ref['id'] + '.evidence.json')).write_text('{}')
    else:
        ref = store.evidence(envelope({"api_key": "sk-test-not-a-real-key-12345678901234567890"}))
    with pytest.raises(ValueError, match="가린 자리"):
        view.resolve_input_refs({"x": {"$ref": ref['id']}}, store=store)


def test_call_list_pages_are_bounded_stable_and_survive_provider_transport(tmp_path, monkeypatch):
    from ibl_result_transport import provider_tool_result
    store = TurnStore(tmp_path)
    monkeypatch.setattr(view, "evidence_store", lambda: store)
    turns = [{"turn": "current", "current": True, "calls": [
        {"seq": i, "input": {"id": f"{i:064x}", "excerpt": "긴 본문" * 100},
         "result": {"id": f"{i + 100:064x}"}, "is_error": False} for i in range(30)]}]
    monkeypatch.setattr(store, "call_history", lambda: turns)
    page = view.read_result({"calls": True, "limit": 1200})
    chunks = []
    first_id = page["id"]
    monkeypatch.setattr(store, "call_history", lambda: pytest.fail("후속 조회에서 목록을 다시 만들면 안 됨"))
    while True:
        assert len(page["text"]) <= 1200 and page["id"] == first_id
        delivered = json.loads(provider_tool_result(json.dumps(page, ensure_ascii=False)))
        assert delivered["text"] == page["text"] and not delivered.get("_spilled")
        chunks.append(delivered["text"])
        if page["next_read"] is None:
            break
        page = view.read_result(page["next_read"])
    assert json.loads("".join(chunks))["turns"] == turns


@pytest.mark.parametrize("page_args", [{"limit": 0}, {"limit": 60001}, {"offset": -1}])
def test_call_list_validates_page_bounds_before_reading(monkeypatch, page_args):
    monkeypatch.setattr(view, "evidence_store", lambda: pytest.fail("invalid request read store"))
    with pytest.raises(ValueError, match="limit"):
        view.read_result({"calls": True, **page_args})


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
