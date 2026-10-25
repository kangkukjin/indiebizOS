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


def test_current_shape_is_checked_without_reinterpreting_business_status():
    assert _invs("items", {"success": False, "error": "業務", "items": [{}]}) == []
    assert _invs("items", {"items": []}) == []
    assert _invs("items", {"table": {"rows": []}}) == ["B"]
    assert _invs("items", {"items": [1]}) == ["B"]
    assert _invs("items", "text") == ["B"]
    assert _invs("scalar", {"message": "Error: quoted user text"}) == []


# ── final_of: 응답 → 최종 봉투 ─────────────────────────────────────────────────
def test_final_of_preserves_business_fields():
    from ibl_v2_ir import pack
    value = {"result": "업무 값", "success": False, "items": []}
    assert hs.final_of({"edition": 2, "success": True,
                       "value_wire": {"protocol": "ibl-value/1", "data": pack(value)}}) == value


def test_parallel_probes_use_actual_runtime_results():
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    for name, code, expected in hs.PARALLEL_PROBES:
        result = Runtime(compile_program(code, {})).run()
        assert hs.check_parallel_envelope(result, expected) == [], (name, result)
        assert hs.check_parallel_envelope({**result, "executed": False}, expected)
        assert hs.check_parallel_envelope({**result, "success": not result["success"]}, expected)


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
