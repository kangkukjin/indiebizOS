"""보존 문서만 검사하며 훈련이나 모델 호출을 시작하지 않는다."""

import boot_paths  # noqa: F401

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = (Path(__file__).resolve().parents[1] / "docs/experiments/"
          "long_sentence_imagination/round_101/verify_coords.py")
SPEC = importlib.util.spec_from_file_location("round101_verify_coords", SCRIPT)
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


def test_one_matching_quote_does_not_hide_another_wrong_quote():
    result = CHECKER.verify_text('"정확한 인용문"과 "존재하지 않는 인용문" (D1 L1)',
                                {"D1": ["정확한 인용문"]})
    assert [q["status"] for q in result["quotes"]] == ["matched_candidate", "unmatched"]
    assert result["needs_review"]


def test_quotes_may_match_different_sources_without_sibling_promotion():
    result = CHECKER.verify_text('"첫째 원문" "둘째 원문" "가짜 원문" D1 L1 R2 L1',
                                {"D1": ["첫째 원문"], "R2": ["둘째 원문"]})
    assert result["quote_status"] == {"matched_candidate": 2, "unmatched": 1}
    assert result["quotes"][0]["matches"][0]["coord"] == "D1 L1"
    assert result["quotes"][1]["matches"][0]["coord"] == "R2 L1"
    assert not result["quotes"][2]["matches"]


@pytest.mark.parametrize("coordinate,status", [
    ("D9 L1", "unknown_doc"), ("D1 L0", "out_of_range"),
    ("D1 L2", "out_of_range"), ("D1 L2-1", "invalid_range"),
])
def test_invalid_coordinate_is_not_rescued_by_valid_sibling(coordinate, status):
    result = CHECKER.verify_text(f'"원문" D1 L1 {coordinate}', {"D1": ["원문"]})
    assert result["coordinate_status"][status] == 1
    assert result["needs_review"]


def test_short_long_and_unattributed_quotes_are_not_silently_dropped():
    long_quote = "긴" * 150
    result = CHECKER.verify_text(f'"짧음" “{long_quote}” 「없는말」\n『무좌표』 D1 L1',
                                {"D1": ["무좌표"]})
    assert result["quote_count"] == 4
    assert result["quote_status"] == {"no_valid_coordinate": 3, "matched_candidate": 1}


def test_nearby_quote_is_review_not_exact_citation():
    result = CHECKER.verify_text('"맞는말" D1 L1', {"D1": ["다른말", "맞는말"]})
    assert result["quotes"][0]["status"] == "nearby_only"
    assert result["needs_review"]
    assert result["semantic_validated"] is False


def test_multiple_coordinates_and_quotes_keep_occurrence_identity():
    result = CHECKER.verify_text('"같음" "같음" D1 L1 D1 L1', {"D1": ["같음"]})
    assert result["coords"] == result["quote_count"] == 2
    assert result["quotes"][0]["column"] != result["quotes"][1]["column"]
    assert len(result["quotes"][0]["matches"]) == 2
    assert not result["needs_review"]


def test_shorthand_and_section_coordinates_keep_the_document_identity():
    result = CHECKER.verify_text('"둘째" D1 §5(L1, L2); "다른" R2 L1',
                                {"D1": ["첫째", "둘째"], "R2": ["다른"]})
    assert result["coords"] == 3
    assert result["quote_status"] == {"matched_candidate": 2}
    assert result["quotes"][0]["matches"][1]["coord"] == "D1 L2"


def test_document_identity_does_not_leak_to_next_output_line():
    result = CHECKER.verify_text('D1 L1\n"원문" L1', {"D1": ["원문"]})
    assert result["coordinates"][1]["status"] == "unknown_doc"
    assert result["quotes"][0]["status"] == "no_valid_coordinate"


def test_empty_and_duplicate_source_sets_fail(tmp_path):
    with pytest.raises(ValueError, match="입력 사본"):
        CHECKER.load_docs(tmp_path)
    (tmp_path / "D1_a.md").write_text("첫 자료")
    (tmp_path / "D1_b.md").write_text("둘째 자료")
    with pytest.raises(ValueError, match="중복"):
        CHECKER.load_docs(tmp_path)


def test_cli_reports_unmatched_quote_without_invoking_any_model(tmp_path, capsys):
    (tmp_path / "D1_source.md").write_text("실제 원문", encoding="utf-8")
    artifact = tmp_path / "output.md"
    artifact.write_text('"실제 원문" "틀린 인용" D1 L1', encoding="utf-8")
    assert CHECKER.main([str(tmp_path), str(artifact)]) == 1
    result = json.loads(capsys.readouterr().out)[str(artifact)]
    assert result["quote_status"] == {"matched_candidate": 1, "unmatched": 1}


def test_saved_cost_aggregation_keeps_all_fields_for_filtered_roles(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("round101_audit", SCRIPT.with_name("audit_saved.py"))
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    rows = [dict(calls=1, input=100, cache_read=60, cache_create=30, output=5),
            dict(calls=2, input=200, cache_read=120, cache_create=50, output=15)]
    result = audit.sum_usage(row for row in rows)
    assert result == dict(calls=3, input=300, cache_read=180, cache_create=80,
                          output=20, input_less_reported_caches=40)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
