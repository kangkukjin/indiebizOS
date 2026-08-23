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


# ── E. 병렬 봉투 (B24-1, 24회차 상상훈련) ──────────────────────────────────────
def _pinvs(env, expect):
    return [i for i, _ in hs.check_parallel_envelope(env, expect)]


def test_e_parallel_branch_failure_must_be_reported():
    # 한 가지 실패 — 신고 있고 부분 성공
    ok = {"success": True, "branches_failed": [{"step": 1, "of": 2,
          "failed": [{"branch": 2, "node": "sense", "action": "feed", "error": "…"}]}]}
    assert _pinvs(ok, {"success": True, "failed": 1}) == []
    # 옛 동작(신고 0) 은 위반이어야 한다 — 이게 B24-1 그 자체다
    old = {"success": True}
    assert _pinvs(old, {"success": True, "failed": 1}) == ["E"]


def test_e_all_branches_failed_is_not_success():
    old = {"success": True, "branches_failed": [{"step": 1, "of": 2,
           "failed": [{"branch": 1}, {"branch": 2}]}]}
    # 전 가지 실패인데 success:true → 위반(아무것도 못 가져온 것은 성공이 아니다)
    assert _pinvs(old, {"success": False, "failed": 2}) == ["E"]
    new = {**old, "success": False}
    assert _pinvs(new, {"success": False, "failed": 2}) == []


def test_e_healthy_parallel_is_untouched():
    assert _pinvs({"success": True}, {"success": True, "failed": 0}) == []


def test_e_probe_universe_is_network_free():
    # 프로브가 외부 API 를 타면 블립이 판정을 흔든다 — 우주는 결정론이어야 한다.
    for _n, code, _e in hs.PARALLEL_PROBES:
        assert "http" not in code, code
        assert " & " in code, code


# ── D. 정적 부채 정규식 ────────────────────────────────────────────────────────
def test_d_static_regex_shape():
    r = hs.BARE_ERROR_RETURN_RE
    assert r.search('return f"Error: {e}"') and r.search("return '오류: 없음'")
    assert not r.search('return {"error": "x"}') and not r.search('return "완료: ok"')


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    # ★두 번째 러너를 두지 않는다. 손으로 적은 러너는 반드시 드리프트한다 — 새 시험 함수를
    # 러너에 안 적으면 직접 실행이 **그 시험만 조용히 건너뛰고 종료코드 0** 을 낸다.
    # 실측(2026-08-23): 배터리 44개·시험 303건 중 **147건**이 직접 실행에서 한 번도 안 돌았고,
    # 27·28회차 상상훈련이 그 초록을 "전부 통과"로 보고서에 적었다(거짓 초록).
    # 위임하면 직접 실행도 살고(순찰·손버릇) 수집은 pytest 가 하므로 드리프트가 불가능하다.
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__] + _sys.argv[1:]))
