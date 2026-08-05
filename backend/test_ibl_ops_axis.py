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
_SCRIPTS = os.path.join(os.path.dirname(_BACKEND), "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from ibl_ops import (  # noqa: E402
    any_op_side_effect,
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
