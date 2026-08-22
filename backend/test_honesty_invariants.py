"""정직성 불변식 판독기 회귀 — scripts/honesty_invariants_sweep.py (2026-08-23).

라이브 fixture 실행 없이 **판독 규칙**만 고정한다: 상상훈련에서 7자리 재발한 침묵/거짓 성공
부류(B21-1·V13-1·F16-2·F17)가 각각 어느 불변식에 걸리는지, 그리고 정직한 봉투가 과잉 거절되지
않는지. 실행: .venv/bin/python -m pytest backend/test_honesty_invariants.py
"""
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
_spec = importlib.util.spec_from_file_location(
    "honesty_invariants_sweep", os.path.join(ROOT, "scripts", "honesty_invariants_sweep.py"))
hs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hs)


def _invs(declared, env):
    return sorted({inv for inv, _ in hs.check_envelope("x", declared, env)})


# ── A. 거짓 성공 (B21-1 부류) ──────────────────────────────────────────────────
def test_a_error_text_in_success_message():
    assert _invs("scalar", {"success": True, "message": "오류: html은 필수입니다."}) == ["A"]
    assert _invs("scalar", {"message": "Error: nope"}) == ["A"]


def test_a_bare_string_error_is_flagged():
    assert _invs("scalar", "렌더링 중 오류 발생: boom") == ["A"]
    assert _invs("scalar", "Traceback (most recent call last):\n ...") == ["A"]


def test_a_honest_failure_not_flagged():
    # 실패를 error 채널로 말하면 정직 — A 아님
    assert _invs("scalar", {"success": False, "error": "오류: html 필요"}) == []
    assert _invs("scalar", {"error": "다운로드 실패: 403"}) == []


def test_a_success_prose_not_overrejected():
    assert _invs("scalar", "렌더링 완료: /tmp/a.png") == []
    assert _invs("scalar", {"success": True, "message": "실패 0건 / 성공 3건"}) == []   # 접두 아님


# ── B. 통화 부재 (V13-1·F16-2·B19-2 부류) ──────────────────────────────────────
def test_b_declared_items_but_missing():
    assert _invs("items", {"success": True, "goals": [{"a": 1}]}) == ["B"]
    assert _invs("items", {"success": True, "items": None}) == ["B"]


def test_b_table_shape_accepted():
    assert _invs("table", {"success": True, "rows": [[1]], "columns": ["a"]}) == []
    assert _invs("items", {"success": True, "table": {"rows": []}}) == []


def test_b_failed_envelope_exempt():
    # 실패 봉투는 오류 채널이 정본 — items 없어도 B 아님
    assert _invs("items", {"success": False, "error": "API 죽음"}) == []


def test_b_scalar_declared_free():
    assert _invs("scalar", {"success": True, "value": 3}) == []


# ── C. 0행 거짓 (F17·P14 빈손 계약) ────────────────────────────────────────────
def test_c_zero_rows_success_is_honest():
    assert _invs("items", {"success": True, "items": [], "count": 0, "message": "등록된 목표가 없습니다."}) == []


def test_c_zero_rows_with_error_prefixed_message():
    assert _invs("items", {"success": True, "items": [], "message": "Error: 결과 없음"}) == ["A", "C"]


def test_c_zero_rows_folded_into_failure_without_error():
    assert _invs("items", {"success": False, "items": []}) == ["C"]
    # error 채널이 있으면 정당한 실패(each 의 입력 거절 등)
    assert _invs("items", {"success": False, "items": [], "error": "each: do 가 필요합니다"}) == []


# ── final_of: 응답 → 최종 봉투 ─────────────────────────────────────────────────
def test_final_of_unwraps_pipeline_and_json_string():
    assert hs.final_of({"success": True, "final_result": '{"items": []}'}) == {"items": []}
    assert hs.final_of({"result": "2026-08-22"}) == "2026-08-22"
    assert hs.final_of({"success": True, "items": [1]}) == {"success": True, "items": [1]}


# ── D. 정적 부채 정규식 ────────────────────────────────────────────────────────
def test_d_static_regex_shape():
    r = hs.BARE_ERROR_RETURN_RE
    assert r.search('return f"Error: {e}"') and r.search("return '오류: 없음'")
    assert not r.search('return {"error": "x"}') and not r.search('return "완료: ok"')
