"""경로 해석 한 벌(common/field_path) — 표면 동형성·관문 다리 시험 (2026-08-27).

같은 경로 "items.0.title" 이 표면(블록 술어·응답 변환 추출/중첩·$변수 추출·flatten)
마다 다른 답을 내던 5개 방언을 한 벌로 접었다. 이 시험이 그 동형성을 지킨다.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from common.field_path import MISSING, parse_path, walk_path
from ibl.api_transforms import _extract_path, _get_nested
from ibl.ibl_predicates import _MISSING as PRED_MISSING
from ibl.ibl_predicates import walk_path as pred_walk
from ibl.workflow_binding import _extract_result_field

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts" / "check_field_path.py"


@pytest.fixture(scope="module")
def data_ops():
    handler = ROOT / "data/packages/installed/tools/data-ops/handler.py"
    spec = importlib.util.spec_from_file_location("fp_data_ops", handler)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_DOC = {"items": [{"title": "가"}, {"title": "나"}], "meta": {"0": "영키", "n": None}}


def test_same_path_same_answer_across_surfaces():
    """리스트 숫자 인덱스 경로가 전 표면에서 같은 값을 낸다 (옛 방언은 3표면이 실패)."""
    path = "items.0.title"
    assert walk_path(_DOC, path) == "가"
    assert pred_walk(_DOC, path) == "가"
    assert _extract_path(_DOC, path) == "가"
    assert _get_nested(_DOC, path) == "가"
    import json
    assert _extract_result_field(json.dumps(_DOC, ensure_ascii=False), path) == "가"


def test_dict_digit_key_takes_precedence_over_index():
    """dict 의 "0" 은 문자열 키다 — 블록 술어의 문서화된 계약이 전 표면의 정본."""
    assert walk_path(_DOC, "meta.0") == "영키"
    assert pred_walk(_DOC, "meta.0") == "영키"
    assert _get_nested(_DOC, "meta.0") == "영키"


def test_missing_vs_null_distinction_preserved():
    """결측(MISSING)과 값 null 은 다르다 — 술어의 exists() 계약이 산다."""
    assert walk_path(_DOC, "meta.n") is None
    assert walk_path(_DOC, "meta.x") is MISSING
    assert pred_walk(_DOC, "meta.n") is None
    assert pred_walk(_DOC, "meta.x") is PRED_MISSING
    assert PRED_MISSING is MISSING  # 표지도 한 벌 — 두 표지는 두 방언의 씨앗


def test_bracket_grammar_stays_surface_local():
    """대괄호는 응답 변환 전용 확장 — 다른 표면 문법을 조용히 넓히지 않는다."""
    assert _extract_path({"data": [{"name": "가"}]}, "data[0].name") == "가"
    assert parse_path("data[0].name") == ["data[0]", "name"]          # 기본은 문자 그대로
    assert parse_path("data[0].name", brackets=True) == ["data", 0, "name"]
    assert pred_walk({"data[0]": {"name": "나"}}, "data[0].name") == "나"  # 술어는 리터럴 키


def test_flatten_field_accepts_index_path(data_ops):
    """flatten 의 field 경로도 같은 문법 — 옛 _dig 는 dict 전용이라 행을 침묵 스킵했다."""
    rows = {"items": [{"wrap": [{"items": [{"v": 1}, {"v": 2}]}]}]}
    res = data_ops._op_flatten(rows, {"field": "wrap.0.items"})
    assert res["success"] is True
    assert [r["v"] for r in res["items"]] == [1, 2]


def test_binding_missing_still_reports_honestly():
    with pytest.raises(ValueError) as err:
        _extract_result_field('{"a": {"b": 1}}', "a.x")
    assert "'x'" in str(err.value) and "사용 가능" in str(err.value)


def test_extract_xml_fallback_preserved():
    """XML 중첩 태그 폴백은 추출 표면의 정책으로 남는다 — 문법이 아니라."""
    data = {"response": {"body": {"row": [1, 2]}}}
    assert _extract_path(data, "row") == [1, 2]


def test_gate_passes_and_has_teeth(tmp_path):
    proc = subprocess.run([sys.executable, str(CHECKER)],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    spec = importlib.util.spec_from_file_location("fp_checker", CHECKER)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    planted = tmp_path / "p.py"
    planted.write_text('def f(p, d):\n    for k in p.split("."):\n        d = d.get(k)\n    return d\n')
    assert len(checker._scan_file(planted, "p.py")) == 1
    ok = tmp_path / "q.py"
    ok.write_text('h = host.split(".")  # path-ok: 호스트명 분해\n')
    assert checker._scan_file(ok, "q.py") == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
