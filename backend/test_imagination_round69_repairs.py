"""상상훈련 69회차 수리 가드 — 결과 참조 왕복의 값 통로(inputs $ref · read_result · result_ref).

공통 뿌리: 참조 해석기가 표시·인용용 저장본(공개 투영 + 비밀 마스킹)을 값 운반 통로로 읽었다.
정본: docs/experiments/imagination_round69_2026_09_28/report.md
"""
import json
from decimal import Decimal

import boot_paths  # noqa: F401
import pytest

from ibl_v2_ir import pack


@pytest.fixture
def view(tmp_path, monkeypatch):
    import model_result_view as view
    from supervision_store import TurnStore
    store = TurnStore(tmp_path / "ev")
    monkeypatch.setattr(view, "evidence_store", lambda: store)
    view._test_store = store
    return view


def _v2(value, **extra):
    return {"edition": 2, "success": True, "value": json.loads(json.dumps(value, default=float)),
            "value_wire": {"protocol": "ibl-value/1", "data": pack(value)}, **extra}


def _store(view, envelope):
    return view._test_store.evidence(json.dumps(envelope, ensure_ascii=False, default=str))


AREA = {"price": Decimal("19.9"), "items": [{"n": "A동", "v": Decimal("1.1")}, {"n": "B동", "v": Decimal("2.2")}]}


# B69-1 — path 를 준 참조도 손실 없는 wire 위를 걷는다
@pytest.mark.parametrize("path,expected", [
    (None, AREA),
    (["value"], AREA),
    (["value", "price"], Decimal("19.9")),
    (["value", "items"], AREA["items"]),
    (["value", "items", 1, "v"], Decimal("2.2")),
])
def test_value_paths_resolve_typed_wire_not_public_projection(view, path, expected):
    ref = _store(view, _v2(AREA))
    arg = {"$ref": ref["id"], **({"path": path} if path is not None else {})}
    resolved, notes = view.resolve_input_refs({"x": arg})
    assert resolved["x"] == expected
    assert type(json.dumps(resolved["x"], default=str)) is str
    if path is not None and path[1:]:
        leaf = resolved["x"]
        assert not isinstance(leaf, float)
    assert notes[0]["path"] == (["value_wire"] if path is None else path)


def test_typed_walk_does_not_reparse_json_looking_text(view):
    ref = _store(view, _v2({"memo": "[1, 2]"}))
    resolved, _ = view.resolve_input_refs({"x": {"$ref": ref["id"], "path": ["value", "memo"]}})
    assert resolved["x"] == "[1, 2]"


def test_read_result_page_input_args_are_lossless(view):
    ref = _store(view, _v2(AREA))
    page = view.read_result({"id": ref["id"], "path": ["value"]})
    resolved, _ = view.resolve_input_refs(page["input_args"])
    assert resolved["입력"]["price"] == Decimal("19.9")


# B69-4 — 실패 봉투의 기본 참조는 업무 값이 아니다
def test_failed_envelope_default_ref_rejected_but_explicit_diagnostic_allowed(view):
    failed = {"edition": 2, "success": False, "error": "없음", "diagnostic": {"code": "TOOL", "message": "없음"},
              "source_complete": False}
    ref = _store(view, failed)
    with pytest.raises(ValueError, match="실패"):
        view.resolve_input_refs({"x": {"$ref": ref["id"]}})
    resolved, _ = view.resolve_input_refs({"x": {"$ref": ref["id"], "path": ["diagnostic"]}})
    assert resolved["x"]["code"] == "TOOL"


def test_partial_paths_still_use_partial_wire(view):
    partial = ["가" * 3, "나"]
    failed = {"edition": 2, "success": False, "diagnostic": {"partial": partial, "has_partial": True},
              "partial_wire": {"protocol": "ibl-value/1", "data": pack(partial)}}
    ref = _store(view, failed)
    resolved, _ = view.resolve_input_refs({"x": {"$ref": ref["id"], "path": ["diagnostic", "partial", 1]}})
    assert resolved["x"] == "나"


# B69-2 — 목록·레코드 안의 참조도 같은 규칙으로 푼다
def test_nested_refs_in_lists_and_records_resolve(view):
    a = _store(view, _v2([{"n": "가"}, {"n": "나"}]))
    b = _store(view, _v2([{"n": "다"}], source_complete=False))
    resolved, notes = view.resolve_input_refs({
        "반": [{"$ref": a["id"]}, {"$ref": b["id"]}],
        "cfg": {"rows": {"$ref": a["id"], "path": ["value", 0]}, "title": "성적",
                "schema": {"$ref": "#/defs/x", "description": "JSON 스키마 조각"}}})
    assert resolved["반"] == [[{"n": "가"}, {"n": "나"}], [{"n": "다"}]]
    # 참조 모양($ref·path만)이 아닌 중첩 $ref 객체는 데이터다
    assert resolved["cfg"] == {"rows": {"n": "가"}, "title": "성적",
                               "schema": {"$ref": "#/defs/x", "description": "JSON 스키마 조각"}}
    assert [(n["name"], n.get("at")) for n in notes] == [("반", [0]), ("반", [1]), ("cfg", ["rows"])]
    merged = view.input_evidence_by_name(notes)
    assert merged["반"]["evidence"]["incomplete"] is True
    assert merged["cfg"]["evidence"]["incomplete"] is False
    assert len(merged["반"]["refs"]) == 2


def test_nested_missing_ref_is_an_honest_rejection(view):
    with pytest.raises(ValueError, match=r"inputs\.반\[1\]"):
        view.resolve_input_refs({"반": [1, {"$ref": "0" * 64}]})


# B69-5 — 저장 시 가린 자리는 값 통로가 업무 값으로 삼지 않는다
NOTE = "와이파이 비밀번호는 cafe2026guest 입니다"


def test_store_records_masked_paths_without_keeping_the_secret(view):
    envelope = _v2({"note": NOTE, "title": "공지"})
    ref = _store(view, envelope)
    saved = view._test_store.read_evidence(ref["id"], 0, None)
    assert "cafe2026guest" not in saved["text"]
    assert ["value", "note"] in saved["masked_paths"]
    assert any(p[:1] == ["value_wire"] for p in saved["masked_paths"])
    assert ref["masked_paths"] == saved["masked_paths"]


def test_masked_selection_rejected_unaffected_selection_resolves(view):
    envelope = _v2({"note": NOTE, "title": "공지"})
    ref = _store(view, envelope)
    with pytest.raises(ValueError, match=r"\*\*\*\*"):
        view.resolve_input_refs({"x": {"$ref": ref["id"]}})
    with pytest.raises(ValueError, match=r"\*\*\*\*"):
        view.resolve_input_refs({"x": {"$ref": ref["id"], "path": ["value", "title"]}})  # wire 안 대응 불가 → 전체
    # 값과 무관한 자리(실행 기록)만 가려졌으면 값은 그대로 넘어간다
    clean = _v2({"title": "공지"}, recordings=[{"args": {"password": "hunter2hunter2"}}])
    ref2 = _store(view, clean)
    resolved, _ = view.resolve_input_refs({"x": {"$ref": ref2["id"]}})
    assert resolved["x"] == {"title": "공지"}


def test_projection_and_read_result_do_not_offer_masked_input_args(view):
    envelope = _v2({"note": NOTE})
    ref = _store(view, envelope)
    reference = view._read_reference(ref, envelope)
    assert "input_args" not in reference and "****" in reference["input_unavailable"]
    page = view.read_result({"id": ref["id"], "path": ["value"]})
    assert "input_args" not in page and page["masked_paths"] and page["input_unavailable"]
    fine = _v2({"title": "공지"})
    ok = _store(view, fine)
    assert "input_args" in view._read_reference(ok, fine)


def test_nan_is_not_reported_as_masked(tmp_path):
    from supervision_store import masked_paths
    assert masked_paths({"x": float("nan")}, {"x": float("nan")}) == []


# F69-1 — 다른 대화의 참조는 범위를 알리고 내부 경로를 흘리지 않는다
def test_missing_evidence_error_is_scoped_and_catchable_both_ways(view):
    from supervision_store import EvidenceNotFound
    with pytest.raises(ValueError) as caught:
        view._test_store.read_evidence("a" * 64)
    message = str(caught.value)
    assert isinstance(caught.value, OSError) and isinstance(caught.value, EvidenceNotFound)
    assert "같은 대화" in message and "Errno" not in message and "/" not in message
    with pytest.raises(ValueError) as resolved:
        view.resolve_input_refs({"x": {"$ref": "a" * 64}})
    assert "Errno" not in str(resolved.value) and "tool_evidence" not in str(resolved.value)


# F69-2 — 문자열 경로는 원문 글자로 페이지한다
def test_string_path_pages_raw_text_with_preview_coordinates(view):
    text = "".join(f'{i:03d} "따옴표" \\ 탭\t끝\n' for i in range(400))
    ref = _store(view, _v2({"text": text}))
    buf, args, pages = "", {"id": ref["id"], "path": ["value", "text"], "limit": 1000}, 0
    while args:
        page = view.read_result(args)
        assert page["read_scope"]["total_chars"] == len(text) and page["read_scope"]["format"] == "text"
        buf += page["text"]
        args, pages = page["next_read"], pages + 1
    assert buf == text and pages == -(-len(text) // 1000)
    whole = view.read_result({"id": ref["id"], "path": ["value", "text"]})
    assert whole["read_scope"]["complete"] is True and whole["text"] == text
    # 구조 값은 종전처럼 JSON 페이지, paths.chars 는 read_scope 와 같은 좌표
    structured = view.read_result({"id": ref["id"], "path": ["value"]})
    assert structured["read_scope"]["format"] == "json" and json.loads(structured["text"]) == {"text": text}
    envelope = _v2({"text": text})
    assert view._read_reference(ref, envelope)["paths"][0] == {"path": ["value", "text"], "chars": len(text)}


# B69-3 — 수동 모드 검수 표면도 같은 해석기를 통과한다
def test_validate_surface_resolves_refs_like_execution(view, monkeypatch):
    from api_ibl import validate_request_code
    ref = _store(view, _v2([{"n": "가", "s": 90}]))
    report = validate_request_code("#!ibl edition=2\nreturn $입력[0].s + 1", edition=2,
                                   inputs={"입력": {"$ref": ref["id"]}})
    assert report["valid"] is True, report.get("issues")
    missing = validate_request_code("#!ibl edition=2\nreturn $입력", edition=2,
                                    inputs={"입력": {"$ref": "b" * 64}})
    assert missing["valid"] is False and missing["error"].startswith("inputs.입력")


# F69-3 — UNBOUND 안내가 실제 입력 이름을 알린다
def test_unbound_hint_lists_provided_input_names():
    from ibl_v2_entry import handle_request
    report = handle_request({"code": "#!ibl edition=2\nreturn len($목록)", "edition": 2,
                             "inputs": {"입력": ["a"]}, "check": True})
    unbound = [i for i in report["issues"] if i["code"] == "UNBOUND"]
    assert unbound and "$입력" in unbound[0]["hint"]
    plain = handle_request({"code": "#!ibl edition=2\nreturn $없음", "edition": 2, "check": True})
    assert "inputs" not in [i for i in plain["issues"] if i["code"] == "UNBOUND"][0]["hint"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
