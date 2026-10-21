"""표 어댑터의 입력 계약은 외부 효과 전에 알려진 오류를 거절한다."""
import boot_paths  # noqa: F401
import pytest

from ibl_v2_adapters import Adapter, load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime


@pytest.mark.parametrize("count", ["-4", "-1.0", "+-4"])
def test_negative_take_is_rejected_before_external_reads(tmp_path, count):
    calls = []
    registry = load_registry(str(tmp_path))
    registry["fixture:rows"] = Adapter(
        {"version": 1, "params": {}, "result": "List", "effects": ["read_external"]},
        lambda rt, args: calls.append(1) or [{"n": 1}])
    plan = compile_program('$rows=[fixture:rows]{}\nreturn $rows >> [table:take]{n:' + count + '}',
                           registry, {"count": -4})
    assert any(issue["code"] == "ARGUMENT_CONTRACT" for issue in plan.issues), plan.report()
    assert not Runtime(plan).run()["executed"]
    assert not calls


def test_dynamic_take_uses_same_minimum_contract(tmp_path):
    registry = load_registry(str(tmp_path))
    registry["fixture:count"] = Adapter(
        {"version": 1, "params": {}, "result": "Number", "effects": ["pure"]},
        lambda rt, args: -4)
    plan = compile_program('$count=[fixture:count]{}\nreturn [1,2] >> [table:take]{n:$count}', registry)
    assert not plan.issues, plan.report()
    out = Runtime(plan).run()
    assert not out["success"] and out["diagnostic"]["code"] == "ARGUMENT_CONTRACT", out


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
