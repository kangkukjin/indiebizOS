"""실행 시점의 중첩 문장 검사도 컴파일 때와 같은 저장 함수 목록을 본다.

2026-10-01 실측: 트리거 문장에 저장 함수 호출(`[fn:이름]{…}`)을 입력 변수로 넘기면 컴파일 검사는 값을 몰라
지나가고, 실행 검사는 저장 함수 목록 없이 다시 컴파일해 "등록된 함수가 없습니다"로 거절했다 — 저장 함수를
부르는 예약 문장을 등록할 수 없었다.
"""
import boot_paths  # noqa: F401
import pytest

from ibl_v2_adapters import Adapter
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime

DEFS = {"twice": '[def:twice]($n){return $n*2}'}


def _registry(seen):
    return {"test:keep": Adapter({"version": 1, "params": {"pipeline": "Text"}, "result": "Text",
                                  "effects": ["write_external"], "code_params": ["pipeline"]},
                                 lambda rt, a: seen.append(a["pipeline"]) or a["pipeline"])}


def test_runtime_code_param_check_sees_saved_functions():
    seen = []
    code = '[fn:twice]{n:2}'
    plan = compile_program('return [test:keep]{pipeline:$p}', _registry(seen), {"p": code}, DEFS)
    assert not plan.issues, plan.report()
    out = Runtime(plan, {"p": code}).run()
    assert out["success"], out
    assert seen == [code]


def test_runtime_code_param_check_still_rejects_unknown_function():
    seen = []
    code = '[fn:nowhere]{n:2}'
    plan = compile_program('return [test:keep]{pipeline:$p}', _registry(seen), {"p": code}, DEFS)
    out = Runtime(plan, {"p": code}).run()
    assert not out["success"] and "nowhere" in str(out.get("error")), out
    assert seen == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
