"""op 축 해소 규칙 회귀 (2026-08-05 감사 ③).

`returns`/`side_effect` 는 액션 단위인데 통화와 부작용을 가르는 건 op 다.
`ibl_ops` 가 그 해소의 단일 소스이고, 여기서 지키는 불변식은 하나다:

    **조이는 건 자동, 푸는 건 명시.**

op 가 effect 를 선언하면 액션이 뭐라 했든 위험해지고(자동), 보수적인 액션
`side_effect: true` 는 op 가 `false` 를 직접 말하기 전엔 안 풀린다(명시).
이 비대칭이 깨지면 무인 자가점검 루프가 부작용 op 를 매일 실행하게 된다.
"""
import os
import sys

_BACKEND = os.path.dirname(os.path.abspath(__file__))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
    import boot_paths  # noqa: F401 — 층 디렉토리 등재 (물리 이동 2026-08-05)
_SCRIPTS = os.path.join(os.path.dirname(_BACKEND), "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from ibl_ops import (  # noqa: E402
    any_op_side_effect,
    op_needs_fixture,
    op_returns,
    op_side_effect,
    resolve_op,
)
from ibl_safety import build_op_safety_map, build_safety_map, is_side_effect  # noqa: E402


def _action(**kw):
    base = {
        "returns": "items",
        "target_key": "op",
        "ops": {"default": "list", "values": {"list": "목록", "delete": "삭제"}},
    }
    ops_extra = kw.pop("ops_extra", None)
    base.update(kw)
    if ops_extra:
        base["ops"] = {**base["ops"], **ops_extra}
    return base


# ── 통화(returns) 상속·override ──

def test_returns_inherits_action_when_op_undeclared():
    a = _action()
    assert op_returns(a, "list") == "items"
    assert op_returns(a, "delete") == "items"  # 선언 안 하면 액션 말을 그대로 믿는다


def test_returns_per_op_override():
    a = _action(ops_extra={"returns": {"delete": "effect"}})
    assert op_returns(a, "list") == "items"
    assert op_returns(a, "delete") == "effect"


# ── 부작용: 조이기는 자동 ──

def test_effect_op_inside_items_action_is_unsafe_automatically():
    a = _action(ops_extra={"returns": {"delete": "effect"}})
    assert op_side_effect(a, "delete") is True
    assert op_side_effect(a, "list") is False
    # 액션 롤업은 보수적 — op 하나라도 쓰기면 액션은 쓰기
    assert any_op_side_effect(a) is True


# ── 부작용: 풀기는 명시 ──

def test_action_flag_is_sticky_until_op_speaks():
    a = _action(side_effect=True, ops_extra={"returns": {"list": "items"}})
    # op 가 items 를 선언해도 액션의 보수적 플래그는 안 풀린다
    # (카메라·마이크처럼 '통화는 읽기, 행위는 셔터'인 액션을 지키는 자리)
    assert op_side_effect(a, "list") is True


def test_explicit_false_unlocks_read_op():
    a = _action(side_effect=True, ops_extra={"side_effect": {"list": False}})
    assert op_side_effect(a, "list") is False
    assert op_side_effect(a, "delete") is True   # 말 안 한 op 는 여전히 잠김
    assert any_op_side_effect(a) is True


def test_unknown_op_falls_back_to_action_rollup():
    a = _action(side_effect=True, ops_extra={"side_effect": {"list": False}})
    assert op_side_effect(a, "유령") is True
    assert op_side_effect(a, None) is True


# ── op 해소 ──

def test_resolve_op_uses_default_and_rejects_ghost():
    a = _action()
    assert resolve_op(a, {}) == "list"
    assert resolve_op(a, {"op": "delete"}) == "delete"
    assert resolve_op(a, {"op": "없는op"}) is None      # 기본 op 인 척 삼키지 않는다
    assert resolve_op({"returns": "items"}, {}) is None  # op 축 없는 액션


# ── 지도 빌더 ──

def test_safety_maps():
    nodes = {"n": {"actions": {"a": _action(side_effect=True,
                                            ops_extra={"side_effect": {"list": False}})}}}
    assert build_safety_map(nodes) == {("n", "a"): False}          # 롤업=보수적
    assert build_op_safety_map(nodes) == {("n", "a", "list"): True,
                                          ("n", "a", "delete"): False}


def test_is_side_effect_backward_compatible():
    # op 없는 옛 액션: 선언 override → returns 파생 순서 유지
    assert is_side_effect({"returns": "effect"}) is True
    assert is_side_effect({"returns": "items"}) is False
    assert is_side_effect({"returns": "scalar", "side_effect": True}) is True
    assert is_side_effect("망가진 정의") is True  # 알 수 없으면 보수적


# ── 빌드 가드(드리프트 차단) ──

def test_build_guard_catches_ghost_op_and_bad_values():
    from iblbuild_validators import _check_op_axis
    a = _action(ops_extra={"returns": {"유령": "items", "delete": "transform"},
                           "side_effect": {"list": "아니오"}})
    issues = "\n".join(_check_op_axis("n:a", a, a["ops"], a["ops"]["values"]))
    assert "유령 op" in issues
    assert "delete" in issues        # transform 은 op 통화가 아니다
    assert "side_effect.list" in issues


def test_build_guard_catches_contradiction():
    from iblbuild_validators import _check_op_axis
    a = _action(ops_extra={"returns": {"delete": "effect"},
                           "side_effect": {"delete": False}})
    issues = "\n".join(_check_op_axis("n:a", a, a["ops"], a["ops"]["values"]))
    assert "모순" in issues


# ── 행위 검증 축 (감사 ⑤) ──

def test_needs_fixture_only_for_readable_ops():
    a = _action(ops_extra={"returns": {"delete": "effect"}})
    assert op_needs_fixture(a, "list") is True        # 읽기 + items
    assert op_needs_fixture(a, "delete") is False     # 쓰기
    # 읽기라고 선언했어도 통화가 effect 면 실행 대상이 아니다(측정할 계약이 없다)
    b = _action(returns="effect", ops_extra={"side_effect": {"list": False}})
    assert op_needs_fixture(b, "list") is False


def test_coverage_gate_demands_fixture_or_exempt_for_read_ops():
    from iblbuild_validators import _check_op_fixture_coverage
    a = _action(ops_extra={"returns": {"delete": "effect"}})
    assert "list" in "\n".join(_check_op_fixture_coverage("n:a", a))
    # ① op fixture / ② op exempt / ③ 액션 fixture 가 그 op 을 호출 — 셋 다 커버로 친다
    for extra_ops, extra in (({"fixture": {"list": '[n:a]{op: "list"}'}}, {}),
                             ({"exempt": {"list": "id 필요"}}, {}),
                             ({}, {"fixture": '[n:a]{op: "list"}'})):
        b = _action(ops_extra={"returns": {"delete": "effect"}, **extra_ops}, **extra)
        assert _check_op_fixture_coverage("n:a", b) == []
    # 액션 통째 면제도 커버
    c = _action(ops_extra={"returns": {"delete": "effect"}}, exempt="기기 의존")
    assert _check_op_fixture_coverage("n:a", c) == []


def test_fixture_on_write_op_is_rejected():
    """★부작용 op 의 fixture 는 무인 건강검진이 매일 그 부작용을 실행한다는 뜻."""
    from iblbuild_validators import _check_op_axis
    a = _action(ops_extra={"returns": {"delete": "effect"},
                           "fixture": {"delete": '[n:a]{op: "delete"}'}})
    issues = "\n".join(_check_op_axis("n:a", a, a["ops"], a["ops"]["values"]))
    assert "부작용 op 에는 fixture 를 달 수 없다" in issues


def test_fixture_code_must_call_its_own_op():
    from iblbuild_validators import _check_op_axis
    a = _action(ops_extra={"fixture": {"list": '[n:a]{op: "delete"}'}})
    issues = "\n".join(_check_op_axis("n:a", a, a["ops"], a["ops"]["values"]))
    assert "키와 불일치" in issues        # 다른 op 을 돌면서 '커버됨'으로 세지 못하게


def test_fixture_and_exempt_are_exclusive():
    from iblbuild_validators import _check_op_axis
    a = _action(ops_extra={"fixture": {"list": '[n:a]{op: "list"}'},
                           "exempt": {"list": "사유"}})
    issues = "\n".join(_check_op_axis("n:a", a, a["ops"], a["ops"]["values"]))
    assert "동시 선언" in issues


def test_inherited_contradiction_is_caught():
    """읽기라고 선언했는데 통화는 액션의 effect 상속 — 옛 검사가 못 보던 부류."""
    from iblbuild_validators import _check_op_axis
    a = _action(returns="effect", ops_extra={"side_effect": {"list": False}})
    issues = "\n".join(_check_op_axis("n:a", a, a["ops"], a["ops"]["values"]))
    assert "모순" in issues and "자기 통화를 선언" in issues


def test_live_registry_read_ops_are_all_covered():
    """라이브 레지스트리 전수 — 읽기 op 이 fixture/exempt 없이 남아 있지 않은가.

    빌드 --check 와 같은 판정을 CI 의 pytest 에서도 재확인한다(빌드를 안 돌리는
    경로에서도 커버리지 후퇴가 드러나게).
    """
    import yaml
    from iblbuild_validators import _check_op_fixture_coverage
    root = os.path.dirname(_BACKEND)
    data = yaml.safe_load(open(os.path.join(root, "data", "ibl_nodes.yaml"), encoding="utf-8"))
    problems = []
    for n, nd in (data.get("nodes") or {}).items():
        for a, ad in ((nd or {}).get("actions") or {}).items():
            problems += _check_op_fixture_coverage(f"{n}:{a}", ad)
    assert problems == [], problems


def test_derived_fixture_file_matches_declarations():
    """ibl_fixtures.json 의 op 항목(`node:action#op`)이 선언과 일치하는가."""
    import json
    import yaml
    root = os.path.dirname(_BACKEND)
    data = yaml.safe_load(open(os.path.join(root, "data", "ibl_nodes.yaml"), encoding="utf-8"))
    fx = json.load(open(os.path.join(root, "data", "ibl_fixtures.json"), encoding="utf-8"))
    for key, code in fx["fixtures"].items():
        if "#" not in key:
            continue
        qual, op = key.split("#", 1)
        node, action = qual.split(":", 1)
        declared = ((data["nodes"][node]["actions"][action].get("ops") or {}).get("fixture") or {})
        assert declared.get(op) == code, key


def test_live_registry_has_no_op_axis_drift():
    """라이브 레지스트리 전수 — 선언한 op 축이 전부 실재 op 를 가리키는가."""
    import yaml
    from iblbuild_validators import _check_op_axis
    root = os.path.dirname(_BACKEND)
    data = yaml.safe_load(open(os.path.join(root, "data", "ibl_nodes.yaml"), encoding="utf-8"))
    problems = []
    for n, nd in (data.get("nodes") or {}).items():
        for a, ad in ((nd or {}).get("actions") or {}).items():
            ops = (ad or {}).get("ops")
            if isinstance(ops, dict) and isinstance(ops.get("values"), dict):
                problems += _check_op_axis(f"{n}:{a}", ad, ops, ops["values"])
    assert problems == [], problems


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
