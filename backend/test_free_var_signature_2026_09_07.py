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

PIPE_HEAD = '$추림 = $목록 >> [table:take]{n: 2}; $return = $추림'
PARALLEL = '$합 = $옛것 & $새것 >> [table:union] >> [table:dedup]{by: "k"}; $return = $합'








def test_two_currencies_flow_in_by_name():
    from ibl_v2_entry import handle_request
    code='[def:합치기]($옛것,$새것){return $옛것 + $새것 >> [table:dedup]{by:"k"}}\n[fn:합치기]{옛것:[{k:1},{k:2}],새것:[{k:2},{k:3}]}'
    out=handle_request({'code':code,'edition':2})
    assert out['success'],out
    assert [r['k'] for r in out['value']['items']]==[1,2,3]



def test_missing_slot_points_at_the_call_not_the_body():
    from ibl_v2_entry import handle_request
    code='[def:합치기]($옛것,$새것){return $옛것 + $새것}\n[fn:합치기]{옛것:[]}'
    out=handle_request({'code':code,'edition':2})
    assert not out['success'] and '새것' in str(out['issues'])
    assert 'MISSING_ARGUMENT' in str(out['issues'])





if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
