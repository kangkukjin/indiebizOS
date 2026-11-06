"""Result-reference identity: certified content, historical evidence, and tampering."""
import boot_paths  # noqa: F401
import json
import base64
from copy import deepcopy
from decimal import Decimal

import pytest

import model_result_view as view
from ibl_v2_ir import ResultValue, digest, pack, projection
from supervision_store import TurnStore


def envelope(value, *, complete=True):
    return {"edition": 2, "success": True, "source_complete": complete,
            "value": value, "value_wire": {"protocol": "ibl-value/1", "data": pack(value)},
            "resume": {"run_id": "original-run"},
            "evidence": [{"kind": "ref", "parents": [i]} for i in range(300)]}


def test_mirrored_blocks_fit_once_and_both_original_paths_remain_readable(tmp_path, monkeypatch):
    store = TurnStore(tmp_path / 'mirror-evidence')
    monkeypatch.setattr(view, 'evidence_store', lambda: store)
    body = '원문 조건과 반례. ' * 797 + '끝 조건'
    value = {'text': body, 'blocks': [{'type': 'paragraph', 'page': 3, 'text': body}],
             '_display': {'mirror_fields': [{'field': 'text', 'collection': 'blocks',
                                             'text_field': 'text', 'separator': ''}]}}
    original = envelope(value)
    shown = view.project_result(original)
    assert shown['value']['text'] == {'$model_mirror_of': 'blocks'}
    assert shown['value']['blocks'][0]['text'] == body
    assert shown['value']['blocks'][0]['page'] == 3
    assert original['value']['text'] == body
    for path in (['value', 'text'], ['value', 'blocks', 0, 'text']):
        page = view.read_result({'id': shown['result_ref']['id'], 'path': path, 'limit': 12000})
        assert body in page['text']
        resolved, _ = view.resolve_input_refs({'x': {'$ref': shown['result_ref']['id'], 'path': path}}, store=store)
        assert resolved['x'] == body


def test_masked_sibling_keeps_exact_selected_wire_value(tmp_path, monkeypatch):
    store = TurnStore(tmp_path / "evidence")
    monkeypatch.setattr(view, "evidence_store", lambda: store)
    secret = "sk-" + "Ab3" * 12
    value = {"rows": [{"amount": Decimal("1.00000000000000000001"), "url": secret}],
             "public": "readable " * 80}
    original = envelope(value)
    original["value"] = projection(value)
    shown = view.project_result(original)
    ref = shown["result_ref"]
    assert "input_unavailable" in ref and "input_args" not in ref
    assert secret not in store.read_evidence(ref["id"], 0, None)["text"]
    restored, _ = view.resolve_input_refs({"amount": {"$ref": ref["id"],
                                          "path": ["value", "rows", 0, "amount"]}}, store=store)
    assert restored == {"amount": value["rows"][0]["amount"]}
    safe = next(p for p in ref["paths"] if p["path"] == ["value", "public"])
    assert view.resolve_input_refs(safe["input_args"], store=store)[0] == {"입력": value["public"]}
    page = view.read_result({"id": ref["id"], "path": ["value", "public"]})
    assert "input_unavailable" not in page
    assert view.resolve_input_refs(page["input_args"], store=store)[0] == {"입력": value["public"]}
    for path in (["value"], ["value", "rows"], ["value", "rows", 0, "url"]):
        with pytest.raises(ValueError, match="가린 자리"):
            view.resolve_input_refs({"x": {"$ref": ref["id"], "path": path}}, store=store)


def test_masked_collect_branch_does_not_block_other_branch(tmp_path):
    store = TurnStore(tmp_path / "evidence")
    value = [ResultValue(True, {"text": "sk-" + "Ab3" * 12}, None),
             ResultValue(True, {"text": "public"}, None)]
    original = envelope(value)
    original["value"] = projection(value)
    ref = store.evidence(original)
    selected = {"x": {"$ref": ref["id"], "path": ["value", 1, "value", "text"]}}
    assert view.resolve_input_refs(selected, store=store)[0] == {"x": "public"}
    selected["x"]["path"] = ["value", 1, "ok"]
    assert view.resolve_input_refs(selected, store=store)[0] == {"x": True}


def test_masked_wire_selector_key_is_not_trusted(tmp_path):
    store = TurnStore(tmp_path / "evidence")
    value = {"sk-" + "Ab3" * 12: "hidden name", "safe": 7}
    ref = store.evidence(envelope(value))
    with pytest.raises(ValueError, match="가린 자리"):
        view.resolve_input_refs({"x": {"$ref": ref["id"], "path": ["value", "safe"]}}, store=store)


@pytest.mark.parametrize("field", ["ok", "value"])
def test_selected_result_requires_boolean_discriminator(tmp_path, field):
    store = TurnStore(tmp_path / "evidence")
    original = envelope(None)
    original["value_wire"]["data"] = ["result", "true", ["scalar", 7], ["scalar", None]]
    ref = store.evidence(original)
    with pytest.raises(ValueError):
        view.resolve_input_refs({"x": {"$ref": ref["id"], "path": ["value", field]}}, store=store)


def test_failed_partial_can_reuse_unmasked_field(tmp_path, monkeypatch):
    store = TurnStore(tmp_path / "evidence")
    monkeypatch.setattr(view, "evidence_store", lambda: store)
    value = {"safe": Decimal("1.00000000000000000001"), "hidden": "sk-" + "Ab3" * 12}
    original = {"edition": 2, "success": False, "diagnostic": {"partial": projection(value)},
                "partial_wire": {"protocol": "ibl-value/1", "data": pack(value)}}
    ref = store.evidence(original)
    page = view.read_result({"id": ref["id"], "path": ["diagnostic", "partial", "safe"]})
    assert view.resolve_input_refs(page["input_args"], store=store)[0] == {"입력": value["safe"]}
    with pytest.raises(ValueError, match="가린 자리"):
        view.resolve_input_refs({"x": {"$ref": ref["id"], "path": ["diagnostic", "partial"]}}, store=store)


@pytest.mark.parametrize("success", [True, False])
def test_execution_metadata_projection_preserves_outcomes_and_lossless_reads(tmp_path, monkeypatch, success):
    store = TurnStore(tmp_path / "evidence")
    monkeypatch.setattr(view, "evidence_store", lambda: store)
    original = envelope({"status": "running", "task_ref": {"task_id": "pending-job"}}, complete=False)
    original.update(success=success, executed=True, run_status="suspended", evidence=[],
                    waiting={"task_id": "pending-job"}, error="still pending" if not success else None,
                    continuation={"reuse_args": {"reuse": {"run_id": "original-run"}}})
    original["precheck_warnings"] = [{
        "code": "RECORD_LENGTH", "severity": "warning", "message": "필드 수와 행 수는 다릅니다.",
        "hint": "계약을 확인하세요.", "facts": {"known_type": "Record"},
        "location": {"source": "count", "source_hash": "a" * 64, "line": 3, "column": 8},
        "call_path": [{"function": "count", "call": {"line": i, "source_hash": "b" * 64}}
                      for i in range(12)]}]
    entries = []
    for scope, revision, passed in [("first", "v1", True), ("second", "v1", True),
                                    ("first", "v2", True), ("first", "v2", False)]:
        item = {"id": "fn:count", "success": passed, "source_hash": "c" * 64,
                "function_ref": {"scope_id": scope, "revision": revision,
                                 "function_id": "d" * 64, "definition": "details " * 80}}
        entries.extend([item, deepcopy(item)])
    original["capability_usage"] = entries
    before = deepcopy(original)
    shown = view.project_result(original)
    assert original == before
    for field in ("value", "success", "source_complete", "run_status", "waiting", "error",
                  "resume", "continuation"):
        assert shown[field] == original[field]
    warnings = shown["precheck_warnings"]
    assert len(warnings) == 1 and warnings[0]["detail_index"] == 0
    for field in ("code", "severity", "message", "hint", "facts", "location"):
        assert warnings[0][field] == original["precheck_warnings"][0][field]
    grouped = shown["capability_usage"]
    assert len(grouped) == 4 and [row["count"] for row in grouped] == [2] * 4
    assert [row["success"] for row in grouped] == [True, True, True, False]
    assert [row["detail_indices"] for row in grouped] == [[0, 1], [2, 3], [4, 5], [6, 7]]
    for field, detail in shown["metadata_details"].items():
        page = view.read_result(detail["read_args"])
        assert page["read_scope"]["complete"]
        assert json.loads(page["text"]) == original[field]
        assert detail["count"] == len(original[field])
    restored, _ = view.resolve_input_refs(shown["result_ref"]["input_args"], store=store)
    assert restored["입력"] == original["value"]
    assert shown["result_ref"]["max_limit"] == 60000


def test_small_execution_metadata_is_not_inflated(tmp_path, monkeypatch):
    monkeypatch.setattr(view, "evidence_store", lambda: TurnStore(tmp_path / "evidence"))
    original = envelope(1)
    original.update(capability_usage=[{"id": "script:small", "success": True}],
                    precheck_warnings=[{"code": "NOTICE", "message": "확인"}])
    shown = view.project_result(original)
    assert shown["capability_usage"] == original["capability_usage"]
    assert shown["precheck_warnings"] == original["precheck_warnings"]
    assert "metadata_details" not in shown


def test_describe_driver_briefs_preserve_permission_and_local_shadowing(monkeypatch):
    import guide_registry
    import ibl_v2_store
    selected = []

    def briefs(names):
        selected.append(list(names))
        return [{'file': 'driver.md'}] if names else []

    monkeypatch.setattr(guide_registry, 'callable_control_briefs', briefs)
    monkeypatch.setattr(ibl_v2_store, 'describe', lambda name, allowed: (
        {'error': 'denied'} if name == 'denied' else {'name': name}))
    monkeypatch.setattr(view, 'observed_returns_of_alias', lambda name: None)
    result = view.describe_actions(['fn:driver', 'fn:denied'], None, edition=2)
    assert selected[-1] == ['fn:driver'] and result['control_briefs']
    monkeypatch.setattr(ibl_v2_store, 'program_functions', lambda *args: {'driver': {'local': True}})
    result = view.describe_actions(['fn:driver'], None, edition=2, program='local code')
    assert selected[-1] == [] and 'control_briefs' not in result
    result = view.describe_actions(['limbs:browser'], {'self'}, edition=2)
    assert selected[-1] == [] and 'control_briefs' not in result
    result = view.describe_actions(['limbs:browser'], None, edition=2)
    assert selected[-1] == ['limbs:browser'] and result['control_briefs']


def test_function_description_keeps_contract_and_recovers_internal_graph(tmp_path, monkeypatch):
    import ibl_v2_store
    from ibl_result_transport import provider_tool_result
    store = TurnStore(tmp_path / 'descriptions')
    monkeypatch.setattr(view, 'evidence_store', lambda: store)
    contract = {'required': ['input'], 'params': {'input': 'Text'}, 'result': 'Text',
                'effects': ['write'], 'requirements': [{'input': 'nonempty'}]}
    definition = {'callable_contract': contract, 'component_contract': {'completion': 'verify effect'},
                  'source_hash': 'a' * 64, 'function_ref': {'revision': 'r1'},
                  'warnings': ['verification required'], 'components': {'inner': 'graph ' * 8000},
                  'guards': [{'test': 'pending'}], 'guards_total': 1,
                  'semantic_interface': {'formula': 'symbolic ' * 1000}}
    original = deepcopy(definition)
    monkeypatch.setattr(ibl_v2_store, 'describe', lambda *a: definition)
    monkeypatch.setattr(view, 'observed_returns_of_alias', lambda name: None)
    result = view.describe_actions(['fn:sample'], None)
    shown = result['actions'][0]['definition']
    assert definition == original
    for field in ('callable_contract', 'component_contract', 'warnings', 'source_hash', 'function_ref'):
        assert shown[field] == original[field]
    assert len(json.dumps(result)) < len(json.dumps(original)) / 4
    delivered = json.loads(provider_tool_result(json.dumps(result, ensure_ascii=False)))
    assert delivered['actions'][0]['definition'] == shown
    for key in shown['detail_fields']:
        page = view.read_result({'id': shown['result_ref']['id'], 'path': [key], 'limit': 60000})
        assert page['read_scope']['complete']
        assert json.loads(page['text']) == original[key]
    # The same presentation applies when a local definition shadows a saved one.
    monkeypatch.setattr(ibl_v2_store, 'program_functions', lambda *a: {'sample': definition})
    local = view.describe_actions(['fn:sample'], None, program='local')['actions'][0]['definition']
    assert local['callable_contract'] == contract and local['detail_fields'] == shown['detail_fields']


def test_oversize_descriptions_use_scoped_result_reader_instead_of_file_spill(tmp_path, monkeypatch):
    import ibl_v2_store
    from ibl_result_transport import provider_tool_result
    store = TurnStore(tmp_path / 'oversize-descriptions')
    monkeypatch.setattr(view, 'evidence_store', lambda: store)
    monkeypatch.setattr(ibl_v2_store, 'describe', lambda name, allowed: {
        'callable_contract': {'params': {name: 'Text'}, 'result': 'Text', 'note': 'contract ' * 8000}})
    monkeypatch.setattr(view, 'observed_returns_of_alias', lambda name: None)
    result = view.describe_actions(['fn:first', 'fn:second'], None)
    delivered = json.loads(provider_tool_result(json.dumps(result, ensure_ascii=False)))
    ref = delivered['result_ref']
    assert ref['scope'] == 'tool_result' and 'path' not in ref
    assert [r['action'] for r in ref['paths']] == ['fn:first', 'fn:second']
    text = []
    request = {**ref['read_args'], 'path': ['actions', 1]}
    while request:
        page = view.read_result(request)
        text.append(page['text'])
        request = page['next_read']
    assert json.loads(''.join(text)) == result['actions'][1]


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


@pytest.mark.parametrize("size,preview_expected", [(20, False), (3000, True), (9000, True)])
def test_model_wire_omission_keeps_preview_decision_and_raw_result(
        tmp_path, monkeypatch, size, preview_expected):
    import model_value_preview

    store = TurnStore(tmp_path / "evidence")
    monkeypatch.setattr(view, "evidence_store", lambda: store)
    original = envelope({"text": "가" * size}, complete=False)
    before = deepcopy(original)
    preview_calls = []
    real_preview = model_value_preview.preview_value

    def observe_preview(*args, **kwargs):
        preview_calls.append(True)
        return real_preview(*args, **kwargs)

    monkeypatch.setattr(model_value_preview, "preview_value", observe_preview)
    shown = view.project_result(original)
    assert bool(preview_calls) is preview_expected
    assert "value_wire" not in shown and "partial_wire" not in shown
    assert shown["value"] == original["value"]
    assert shown["success"] is True and shown["source_complete"] is False
    assert shown["resume"] == original["resume"]
    assert original == before
    raw = view.read_result({"id": shown["result_ref"]["id"]})
    assert json.loads(raw["text"]) == before
    restored, notes = view.resolve_input_refs(shown["result_ref"]["input_args"], store=store)
    assert restored["입력"] == before["value"]
    assert notes[0]["evidence"]["incomplete"] is True


def test_model_wire_omission_keeps_exact_typed_input(tmp_path, monkeypatch):
    store = TurnStore(tmp_path / "evidence")
    monkeypatch.setattr(view, "evidence_store", lambda: store)
    value = {"amount": Decimal("1.2300"), "id": 2**70,
             "result": ResultValue(True, [False, None, Decimal("0.01")])}
    original = envelope(value)
    original["value"] = projection(value)
    shown = view.project_result(original)
    assert shown["value"] == projection(value) and "value_wire" not in shown
    restored, _ = view.resolve_input_refs(shown["result_ref"]["input_args"], store=store)
    assert pack(restored["입력"]) == pack(value)
    assert isinstance(restored["입력"]["amount"], Decimal)
    assert isinstance(restored["입력"]["result"], ResultValue)


def test_model_partial_wire_omission_keeps_failure_and_recovery(tmp_path, monkeypatch):
    store = TurnStore(tmp_path / "evidence")
    monkeypatch.setattr(view, "evidence_store", lambda: store)
    partial = [{"amount": Decimal("12.3400")}]
    original = {"edition": 2, "success": False, "source_complete": False,
                "error": "source unavailable", "resume": {"run_id": "failed-run"},
                "continuation": {"run_id": "failed-run", "reuse_args": {"code": "return 1"}},
                "diagnostic": {"has_partial": True, "partial": projection(partial),
                               "code": "SOURCE", "details": {}},
                "partial_wire": {"protocol": "ibl-value/1", "data": pack(partial)}}
    before = deepcopy(original)
    shown = view.project_result(original)
    assert "partial_wire" not in shown
    for key in ("success", "source_complete", "error", "diagnostic", "resume", "continuation"):
        assert shown[key] == before[key]
    assert original == before
    restored, notes = view.resolve_input_refs({"partial": {
        "$ref": shown["result_ref"]["id"], "path": ["diagnostic", "partial"]}}, store=store)
    assert pack(restored["partial"]) == pack(partial)
    assert notes[0]["evidence"]["incomplete"] is True


def test_app_boundary_retains_wire(monkeypatch):
    import system_tools_ibl
    import thread_context

    original = envelope({"value": 42})
    monkeypatch.setattr(thread_context, "get_call_channel", lambda: "app")
    monkeypatch.setattr(view, "project_result", lambda *_: pytest.fail("app used model projection"))
    shown = system_tools_ibl._preview_boundary(original, {})
    assert shown["value_wire"] == original["value_wire"]
    assert shown["value"] == original["value"]


def test_wire_omission_keeps_image_delivery_and_original(tmp_path, monkeypatch):
    from image_envelopes import harvest_images

    store = TurnStore(tmp_path / "evidence")
    monkeypatch.setattr(view, "evidence_store", lambda: store)
    blob = base64.b64encode(b"image-bytes" * 100).decode()
    original = envelope({"image_base64": blob, "mime_type": "image/png"})
    before = deepcopy(original)
    shown = view.project_result(original)
    text, images = harvest_images(json.dumps(shown))
    assert len(images) == 1 and images[0]["b64"] == blob
    assert images[0]["media_type"] == "image/png" and blob not in text
    assert "value_wire" not in shown and original == before
    raw = view.read_result({"id": shown["result_ref"]["id"]})
    assert json.loads(raw["text"]) == before


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))


def test_compile_failure_folds_declarations_but_preserves_diagnostic_and_retrieval(tmp_path, monkeypatch):
    store = TurnStore(tmp_path)
    monkeypatch.setattr(view, 'evidence_store', lambda: store)
    diagnostic = {'code': 'MISSING_FIELD', 'message': 'verified is optional',
                  'source_span': {'line': 4, 'column': 2}, 'hint': 'get(value,"verified",false)'}
    original = {'edition': 2, 'success': False, 'executed': False, 'diagnostic': diagnostic,
                'issues': [diagnostic], 'functions': {'send': {'code': 'definition ' * 5000}},
                'components': {}, 'source_complete': False}
    projected = view.project_v2_result(original)
    assert projected['diagnostic'] == diagnostic and projected['issues'] == [diagnostic]
    assert projected['success'] is False and projected['executed'] is False
    assert len(json.dumps(projected)) < 6000
    args = projected['compile_context']['functions']['read_args']
    page = view.read_result({**args, 'limit': 12000})
    assert 'definition' in json.dumps(page)
    # Stored original still owns the complete declarations, not the display copy.
    stored = json.loads((tmp_path / (args['id'] + '.txt')).read_text())
    assert stored['functions'] == original['functions']


def test_expansion_keeps_original_observation_and_coordinates(tmp_path, monkeypatch):
    store = TurnStore(tmp_path / 'observation')
    monkeypatch.setattr(view, 'evidence_store', lambda: store)
    ref = store.evidence({'value': {'text': '앞🙂가운데끝', 'revision': 'source-v1'}})
    page = view.read_result({'id': ref['id'], 'path': ['value', 'text'], 'offset': 1, 'limit': 2})
    assert page['text'] == '🙂가'
    assert page['read_scope'] == {'source_ref': ref['id'], 'revision': ref['id'],
        'observation': 'stored', 'unit': 'unicode_chars', 'path': ['value', 'text'],
        'start': 1, 'end': 3, 'total_chars': 6, 'complete': False, 'format': 'text'}
    newer = store.evidence({'value': {'text': '다른 관측', 'revision': 'source-v2'}})
    assert newer['id'] != ref['id']
    assert view.read_result({'id': ref['id'], 'path': ['value', 'text']})['text'] == '앞🙂가운데끝'
