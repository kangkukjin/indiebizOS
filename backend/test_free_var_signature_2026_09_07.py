"""함수 몸의 자유 변수는 자리를 가리지 않는다 — 언어 개정 2026-09-07 의 관문.

사용자 판정 "언어 한계가 있다면 그걸 극복해야지". 종전에 미할당 `$이름` 은 **파라미터 값 자리에서만**
시그니처였고 파이프 머리(`$x >> [액션]`)·병렬 분기(`$a & $b`)에서는 파싱 에러였다. 그래서 관용구는
통화를 하나(파이프로 흘러드는 앞 통화)만, 그것도 첫 문장에서만 받을 수 있었고 — 둘 이상의 통화를
받는 관용구(원장 누적·델타·join)는 아예 말할 수 없어, 몸에 도메인 머리(`[sense:search]{source:"naver"}`)를
박는 길밖에 없었다. 기존 이름 38건이 전부 도메인에 얼어붙은 구조적 이유가 이것이다.

★비대칭은 남긴다: **최상위 프로그램**의 미할당은 종전대로 정직한 파싱 에러다(오타를 잡는 자리).
"""
import json
import sys

import pytest

import boot_paths  # noqa: E402,F401
import ibl_engine  # noqa: E402
from ibl_parser import parse, parse_function_body, IBLSyntaxError  # noqa: E402
from workflow_contract import call_signature  # noqa: E402

PIPE_HEAD = '$추림 = $목록 >> [table:take]{n: 2}; $return = $추림'
PARALLEL = '$합 = $옛것 & $새것 >> [table:union] >> [table:dedup]{by: "k"}; $return = $합'


@pytest.mark.parametrize("body,want", [
    (PIPE_HEAD, ["목록"]),
    (PARALLEL, ["옛것", "새것"]),
    ('$합 = $옛것 & $새것 >> [table:union] >> [table:dedup]{by: "${키}"}; $return = $합',
     ["옛것", "새것", "키"]),                      # 파이프 머리·분기·파라미터 값이 한 서명에 섞인다
])
def test_free_vars_are_signature_everywhere(body, want):
    parse_function_body(body)                       # 함수 몸으로는 파싱된다
    assert call_signature(body) == want             # 서명 계산도 같은 눈으로 본다


@pytest.mark.parametrize("body", [PIPE_HEAD, PARALLEL])
def test_toplevel_still_rejects_unassigned(body):
    """최상위는 종전대로 거절 — 여기서 관대해지면 오타가 실행까지 간다(V49-1 규약)."""
    with pytest.raises(IBLSyntaxError) as e:
        parse(body)
    assert "할당되지" in str(e.value)


def test_def_block_signature_includes_pipe_head_slot():
    st = parse('[def: 합치기]{' + PARALLEL + '}\n$r = [fn:합치기]{옛것: [], 새것: []}')
    assert st[0]["signature"] == ["옛것", "새것"]


def test_two_currencies_flow_in_by_name():
    """실행 — 통화 둘이 이름으로 몸에 들어가 합쳐진다(중복 하나가 접힌다)."""
    st = parse('[def: 합치기]{' + PARALLEL + '}\n'
               '$r = [fn:합치기]{옛것: [{"k": 1}, {"k": 2}], 새것: [{"k": 2}, {"k": 3}]}')
    ibl_engine.execute_ibl(st[0], ".", None)
    out = ibl_engine.execute_ibl(st[1], ".", None)
    assert out["success"], out.get("error")
    fr = out.get("final_result")
    if isinstance(fr, str):
        fr = json.loads(fr)
    rows = fr["items"] if isinstance(fr, dict) else fr      # $return 은 값 그대로(리스트) 또는 통화 봉투
    assert [r["k"] for r in rows] == [1, 2, 3]


def test_missing_slot_points_at_the_call_not_the_body():
    """인자를 안 주면 '인자 누락' — '아직 값을 기록하지 않았습니다'로 말하면 몸을 고치러 간다."""
    st = parse('[def: 합치기]{' + PARALLEL + '}\n$r = [fn:합치기]{옛것: []}')
    ibl_engine.execute_ibl(st[0], ".", None)
    out = ibl_engine.execute_ibl(st[1], ".", None)
    assert not out.get("success")
    blob = json.dumps(out, ensure_ascii=False)
    assert "인자 누락" in blob and "새것" in blob


def test_return_type_of_reads_function_bodies():
    """서명의 반환 모양 계산도 함수 몸 모드 — 종전엔 파이프 머리 슬롯에서 '?'로 주저앉았다."""
    from ibl_typecheck import return_type_of
    assert return_type_of(PARALLEL) != "?"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
