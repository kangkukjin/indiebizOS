"""_OP_DISPATCHERS 장식 스텁 가드 자체 회귀 (2026-08-05 감사 ①).

빌드 가드는 키만 AST 비교했어서 값이 전부 None 인 장식 테이블(15개 실재했음)이
"준수처럼 보이는 부재"로 통과했다 — 스텁 전환 후 _stub_ops 조항이 재발을 막는다.
이 테스트는 그 조항의 오탐/미탐 회귀: None=잡고, 함수 참조·문자열 디스패치=통과.
"""
import os
import sys

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from iblbuild_validators import _extract_op_dispatchers, _stub_ops  # noqa: E402


def _table(handler_text, tool="x_op"):
    dispatchers = _extract_op_dispatchers(handler_text)
    assert dispatchers is not None and tool in dispatchers, dispatchers
    _, node = dispatchers[tool]
    return node


def test_stub_none_values_detected():
    node = _table('_OP_DISPATCHERS = {"x_op": {"a": None, "b": None}}')
    assert _stub_ops(node) == ["a", "b"]


def test_function_refs_pass():
    node = _table(
        "def _a(ti, ctx): pass\n"
        "def _b(ti, ctx): pass\n"
        '_OP_DISPATCHERS = {"x_op": {"a": _a, "b": _b}}'
    )
    assert _stub_ops(node) == []


def test_string_dispatch_variant_passes():
    # browser-action / computer-use 변형: 값이 메서드명 문자열 — 실동작 디스패치라 통과
    node = _table('_OP_DISPATCHERS = {"x_op": {"a": "method_a", "b": "method_b"}}')
    assert _stub_ops(node) == []


def test_mixed_flags_only_none():
    node = _table(
        "def _a(ti, ctx): pass\n"
        '_OP_DISPATCHERS = {"x_op": {"a": _a, "b": None, "c": "m"}}'
    )
    assert _stub_ops(node) == ["b"]


def test_repo_has_no_stub_left():
    """실저장소 전수 — 42개 핸들러 어디에도 None 값 테이블이 없어야 한다."""
    import glob
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    left = []
    for path in glob.glob(os.path.join(root, "data/packages/installed/tools/*/handler.py")):
        dispatchers = _extract_op_dispatchers(open(path, encoding="utf-8").read())
        if not dispatchers:
            continue
        for tool, (_, node) in dispatchers.items():
            stubs = _stub_ops(node)
            if stubs:
                left.append((os.path.basename(os.path.dirname(path)), tool, stubs))
    assert not left, f"장식 스텁 잔존: {left}"


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
    raise SystemExit(_pytest.main([__file__, "-q"] + _sys.argv[1:]))
