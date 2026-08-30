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


# ── T2. 이음매 기아 (2026-08-30) ─────────────────────────────────────────────
# effect >> 변환자 = 실행 전 정직 거절. A 통화는 op·param 조건부까지 해소한다 —
# 액션 단위로만 읽으면 오거절(코퍼스 3,676건 실측 26건: self:script op:run 4 ·
# self:write spill:true 2 등). 음성 대조(출하 시 실측): 사전 정정 후 T2 거절 0.
from ibl_pipe_types import seam_starvation_error  # noqa: E402


def test_t2_effect_into_transform_rejected():
    # 동기 실례: 통화 없는 effect op 뒤에 변환자 — 런타임 "items 통화를 찾지
    # 못했습니다" 를 실행 전으로 앞당긴다.
    hit = seam_starvation_error(
        parse('[limbs:browser]{op: "click", ref: "b1"} >> [table:filter]{where: "a > 1"}'))
    assert hit and hit[0] == 1 and "effect" in hit[1] and "table:filter" in hit[1]


def test_t2_op_override_resolved_not_action_level():
    # others:feed 는 액션=items 이지만 op:post 는 effect 오버라이드 — op 로 판정해야 거절
    hit = seam_starvation_error(
        parse('[others:feed]{op: "post", content: "x"} >> [table:take]{n: 1}'))
    assert hit and "others:feed" in hit[1]
    # 반대 방향: 액션 단위로 effect 로 읽힐 자리가 op 해소로 통과해야 한다
    assert seam_starvation_error(
        parse('[self:script]{op: "run", id: "x"} >> [table:take]{n: 1}')) is None


def test_t2_returns_variants_param_conditional():
    # self:write 는 effect 지만 spill:true 는 {items:[], ref:…} 통과자(B36-3 변형 선언)
    assert seam_starvation_error(
        parse('[self:write]{path: "a.json", spill: true} >> [table:take]{n: 1}')) is None
    hit = seam_starvation_error(
        parse('[self:write]{path: "a.json"} >> [table:take]{n: 1}'))
    assert hit and "self:write" in hit[1]


def test_t2_abstains_are_conservative():
    # 동적 op — 실행 시점에야 정해진다 (파서 우회, step 직접 구성)
    assert seam_starvation_error(
        [{"_node": "others", "action": "feed", "params": {"op": "$mode"}},
         {"_node": "table", "action": "take", "params": {"n": 1}}]) is None
    # scalar = 데이터 의존 승격(파일 읽기 등) 가능 — 기권 (코퍼스 실측으로 기각된 부류)
    assert seam_starvation_error(
        parse('[self:read]{path: "a.json"} >> [table:take]{n: 1}')) is None
    # B 가 items 를 직접 실었다(언어 개정 ③) — 이음매 통화 불요
    assert seam_starvation_error(
        parse('[limbs:os_open]{path: "x"} >> [table:take]{items: [{"a": 1}], n: 1}')) is None
    # 문장 경계 — 통화가 안 넘는 자리라 이음매가 아니다 (그 머리는 T1 관할)
    assert seam_starvation_error(
        [{"_node": "limbs", "action": "os_open", "params": {"path": "x"}},
         {"_seq_boundary": True, "_node": "table", "action": "take",
          "params": {"n": 1}}]) is None
    # 미지 액션 — 사전 불능은 통과
    assert seam_starvation_error(
        [{"_node": "limbs", "action": "없는액션", "params": {}},
         {"_node": "table", "action": "take", "params": {"n": 1}}]) is None


def test_t2_pipeline_rejects_before_execution():
    from workflow_engine import execute_pipeline
    res = execute_pipeline(
        parse('[limbs:browser]{op: "click", ref: "b1"} >> [table:filter]{where: "a > 1"}'),
        project_path=".")
    assert res.get("success") is False
    assert res.get("steps_completed") == 0, "실행 전에 거절돼야 한다"
    assert "굶습니다" in (res.get("error") or "")
    tb = res.get("traceback") or {}
    assert tb.get("error_type") == "binding"
    frames = tb.get("frames") or []
    assert frames and frames[-1].get("step") == 2, "프레임은 굶는 변환자 자리"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
