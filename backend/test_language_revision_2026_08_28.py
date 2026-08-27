"""언어 개정 4건 가드 (2026-08-28, 사용자 판정 "언어의 한계 부분은 다 고쳐") — L1~L12.

세 일간 보고서 완성 프로그램 실측(docs/IBL_REPORT_PROGRAMS_HANDOFF.md 완료 절)이
드러낸 표현 공백 4건의 집행:
  ① each 실패 행 통화화 — `on_error: "keep"` (실패 행이 `_error` 표식과 함께 흐름)
  ② 빈 통화 폴백 — 파이프 세그먼트 if 블록의 불일치 = 직전 통화 통과(_if_skipped 표식)
  ③ 문서 blocks 조건부 절 — `when` (빈 값이면 블록 생략, blocks_omitted 신고)
  ④ 열 벡터·옵셔널 경로 — 괄호형 `${x.items.*.f}`(벡터) · `${x.y?}`(결측=빈 값)

수리 전 코드에서 L1·L2·L4·L5·L7·L8·L9·L11 이 빨강이어야 한다.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: F401,E402

from common.field_path import MISSING, walk_path  # noqa: E402
from common.ibl_vars import find_refs  # noqa: E402
from ibl.workflow_binding import _extract_result_field_obj  # noqa: E402


# ── ④ 열 벡터 `*` ──────────────────────────────────────────────

def test_L1_star_vector_projection():
    obj = {"items": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}
    assert walk_path(obj, "items.*.id") == ["a", "b", "c"]


def test_L2_star_partial_and_all_missing():
    obj = {"items": [{"id": "a"}, {"other": 1}]}
    # 부분 결측 = None 자리 유지($items.field 바인딩 선례 — 위치 보존)
    assert walk_path(obj, "items.*.id") == ["a", None]
    # 전 원소 결측 = 정직 결측(오타가 침묵 [] 로 새지 않게)
    assert walk_path({"items": [{"x": 1}]}, "items.*.id") is MISSING


def test_L3_star_dict_key_precedence():
    """dict 에 문자열 키 '*' 가 실존하면 그 키가 우선 — 기존 판정 순서 보존."""
    assert walk_path({"*": {"v": 7}}, "*.v") == 7


def test_L4_optional_path_suffix():
    raw = json.dumps({"a": 1})
    assert _extract_result_field_obj(raw, "b?") is None
    assert _extract_result_field_obj("평문 텍스트", "b?") is None
    with pytest.raises(ValueError):
        _extract_result_field_obj(raw, "b")   # 물음표 없으면 종전대로 정직 오류
    # 벡터+옵셔널 조합
    raw2 = json.dumps({"items": [{"id": "a"}]})
    assert _extract_result_field_obj(raw2, "items.*.id") == ["a"]
    assert _extract_result_field_obj(raw2, "items.*.없는필드?") is None


def test_L5_braced_extended_refs_parse():
    refs = find_refs("x ${성공.items.*.video_id} y ${사례문.message?} z")
    assert ("성공", ".items.*.video_id") in refs
    assert ("사례문", ".message?") in refs


def test_L6_bare_form_stays_narrow():
    """맨몸형은 확장 문법 밖 — `$x.*` 의 `*` 는 경로에 안 먹힌다(산문·강조 충돌 방지)."""
    refs = find_refs("$x.*.id")
    assert refs and refs[0] == ("x", "")


# ── ① each on_error: keep ─────────────────────────────────────

def _each(rows, do, on_error):
    from ibl.ibl_exec_each import _execute_table_each
    out = _execute_table_each({"items": rows, "do": do, "on_error": on_error}, ".")
    return out if isinstance(out, dict) else json.loads(out)


def test_L7_keep_flows_failed_rows_marked():
    rows = [{"a": 1}, {"a": 2}]
    out = _each(rows, "[self:time]{x: '$it.없는필드'}", "keep")
    assert out.get("success", True) is True
    marked = [r for r in out["items"] if isinstance(r, dict) and r.get("_error")]
    assert len(marked) == 2 and marked[0]["a"] == 1
    assert out["error_count"] == 2
    assert out.get("errors")          # 진단층은 keep 이어도 그대로(경계 규약 예외 없음)


def test_L8_continue_keeps_old_contract():
    rows = [{"a": 1}]
    out = _each(rows, "[self:time]{x: '$it.없는필드'}", "continue")
    # 전량 실패 = 종전대로 문장 실패(keep 만 전량 실패도 통화로 흘린다)
    assert out.get("success") is False
    assert not out.get("items")


# ── ② if 블록 파이프 불일치 = 통과 ─────────────────────────────

def test_L9_if_no_match_passes_prev_currency():
    from ibl.ibl_executors import _execute_condition
    prev = json.dumps({"success": True, "items": [{"a": 1}], "count": 1}, ensure_ascii=False)
    out = _execute_condition({"branches": [{"condition": "1 == 2", "action": None}],
                              "params": {"_prev_result": prev}}, ".", None)
    assert isinstance(out, dict)
    assert out.get("items") == [{"a": 1}]
    assert out.get("_if_skipped") == ["1 == 2"]


def test_L10_if_no_match_standalone_unchanged():
    from ibl.ibl_executors import _execute_condition
    out = _execute_condition({"branches": [{"condition": "1 == 2", "action": None}]}, ".", None)
    assert out.get("message") == "모든 조건 불일치, 실행할 분기 없음"


# ── ③ blocks 조건부 절 when ───────────────────────────────────

def test_L11_when_drops_empty_and_strips_key():
    import importlib.util
    _ROOT = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "when_doc_build", _ROOT / "data/packages/installed/tools/data-ops/doc_build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    blocks = [
        {"type": "heading", "level": 2, "text": "함의", "when": ""},
        {"type": "paragraph", "text": "본문", "when": "산문 있음"},
        {"type": "paragraph", "text": "무조건"},
        {"type": "cards", "items": [], "when": []},
        {"type": "paragraph", "text": "널", "when": None},
    ]
    kept, omitted = mod._apply_when(blocks)
    assert omitted == 3
    assert [b["text"] for b in kept] == ["본문", "무조건"]
    assert all("when" not in b for b in kept)


def test_L12_when_absent_untouched():
    import importlib.util
    _ROOT = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "when_doc_build2", _ROOT / "data/packages/installed/tools/data-ops/doc_build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    blocks = [{"type": "paragraph", "text": "a"}]
    kept, omitted = mod._apply_when(blocks)
    assert kept == blocks and omitted == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
