"""파이프 정적 타입 검사(T1) 관문 — returns 선언의 소비자 (ibl_pipe_types).

P1. 홀로/머리에 선 변환자(통화·items 없음) = 실행 전 정직 거절 (안내 동반).
P2. items 를 직접 실은 머리 변환자 = 통과 (언어 개정 2026-08-28 ③).
P3. 생산자 >> 변환자 = 통과 (정상 파이프).
P4. has_incoming(블록 몸·each 하위) = 통과 — 직전 통화가 들어온다.
P5. `$변수 >>` 머리·병렬 머리·블록 머리 = 검사 밖 (각자 규약 보유).
P6. 미지 액션·사전 불능 = 통과 (보수적 — 검사기가 실행을 죽이면 안 된다).
P7. 통합: execute_pipeline 이 T1 위반을 실행 전에 error_type=binding 으로 거절.
음성 대조(2026-08-29 출하 시 실측): 해마 코퍼스 3,661건 중 거절 3건 — 전부
생산자 없는 미완성 조각(정탐). do 하위 파이프 90건 거절 0.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401

from ibl_parser import parse  # noqa: E402
from ibl_pipe_types import head_transform_error  # noqa: E402


def test_p1_lone_or_head_transform_rejected():
    err = head_transform_error(parse('[table:take]{n: 3}'))
    assert err and "변환자" in err and "items" in err
    err2 = head_transform_error(parse('[table:sort]{by: "a"} >> [table:take]{n: 3}'))
    assert err2 and "table:sort" in err2


def test_p2_head_transform_with_items_passes():
    assert head_transform_error(
        parse('[table:sort]{items: [{"a": 2}, {"a": 1}], by: "a"}')) is None


def test_p3_producer_then_transform_passes():
    assert head_transform_error(
        parse('[sense:search]{query: "x"} >> [table:take]{n: 3}')) is None


def test_p4_incoming_currency_passes():
    assert head_transform_error(parse('[table:take]{n: 3}'),
                                has_incoming=True) is None


def test_p5_special_heads_out_of_scope():
    # `$변수 >>` 머리 — 파서는 할당 선행을 요구하므로(V49-1) _var_emit step 을 직접 구성
    assert head_transform_error(
        [{"_var_emit": True, "name": "saved"},
         {"_node": "table", "action": "take", "params": {"n": 3}}]) is None
    assert head_transform_error(
        parse('[sense:search]{query:"a"} & [sense:search]{query:"b"} '
              '>> [table:merge]{by: "t"}')) is None
    assert head_transform_error(
        parse('[if: count($items) > 0]{[table:take]{n: 1}}')) is None


def test_p6_unknown_action_is_conservative():
    assert head_transform_error(
        [{"_node": "table", "action": "없는액션", "params": {}}]) is None
    assert head_transform_error([]) is None


def test_p7_pipeline_rejects_before_execution():
    from workflow_engine import execute_pipeline
    res = execute_pipeline(parse('[table:dedup]{by: "a"} >> [table:take]{n: 3}'),
                           project_path=".")
    assert res.get("success") is False
    assert res.get("steps_completed") == 0, "실행 전에 거절돼야 한다"
    assert "변환자" in (res.get("error") or "")
    assert (res.get("traceback") or {}).get("error_type") == "binding"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
