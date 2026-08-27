"""where 부정 멤버십(not_in/not_contains) 가드 — N1~N8.

2026-08-28 팁 보고서 완성 프로그램 실측이 적발한 표면 비대칭의 이빨:
`api_transforms` 는 not_in/not_contains 를 팔면서 `where` 구조형은
"지원하지 않는 연산자 'not_in'" 으로 거절했다 — 원장 제외(안티조인)를
문장 안 술어로 쓸 수 없었다. 수리 = where_dsl._OPS 에 두 연산자를
api_transforms 와 **같은 의미론**(common.value_semantics 한 벌)으로 추가.

수리 전 코드에서 N1·N2·N4·N5·N7 이 빨강(_WhereError)이어야 한다.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: F401,E402

from ibl.api_transforms import _match_condition  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent
_WHERE = _ROOT / "data/packages/installed/tools/data-ops/where_dsl.py"


@pytest.fixture(scope="module")
def wd():
    spec = importlib.util.spec_from_file_location("negation_where_dsl", _WHERE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_N1_not_in_structured_keeps_and_drops(wd):
    """구조형 {field, op:"not_in", value:[...]} — 목록에 없는 행만 참."""
    cond = {"field": "video_id", "op": "not_in", "value": ["aaa", "bbb"]}
    assert wd._match({"video_id": "ccc"}, cond) is True
    assert wd._match({"video_id": "aaa"}, cond) is False


def test_N2_not_in_null_left_claims_nothing(wd):
    """결측 좌변은 부정도 주장하지 않는다 — api_transforms 와 같은 가드."""
    cond = {"field": "video_id", "op": "not_in", "value": ["aaa"]}
    assert wd._match({"video_id": None}, cond) is False
    assert wd._match({}, cond) is False


def test_N3_not_in_isomorphic_with_api_transforms(wd):
    """where 구조형과 api_transforms 조건이 같은 판정을 낸다(표면 동형성)."""
    for left in ("ccc", "aaa", None, 3):
        row = {"v": left}
        got_where = wd._match(row, {"field": "v", "op": "not_in", "value": ["aaa", 3]})
        got_api = _match_condition(row, {"field": "v", "not_in": ["aaa", 3]})
        assert got_where == got_api, f"left={left!r}: where={got_where} api={got_api}"


def test_N4_not_contains_structured(wd):
    cond = {"field": "title", "op": "not_contains", "value": "광고"}
    assert wd._match({"title": "정직한 리뷰"}, cond) is True
    assert wd._match({"title": "[광고] 협찬 영상"}, cond) is False
    # 결측 좌변은 부정도 주장하지 않는다
    assert wd._match({"title": None}, cond) is False


def test_N5_word_op_string_form_parses(wd):
    """문자열 "필드 not_in 값" 이 전-필드 substring 으로 내려앉지 않는다."""
    parsed = wd._parse_where_str("video_id not_in abc")
    assert parsed == ("video_id", "not_in", "abc")
    parsed2 = wd._parse_where_str("title not_contains 광고")
    assert parsed2 == ("title", "not_contains", "광고")


def test_N6_string_form_membership_semantics(wd):
    """문자열 우변 not_in = 긍정 in 의 substring 의미론의 부정(대칭)."""
    assert wd._match({"v": "xyz"}, "v not_in abc,def") is True
    assert wd._match({"v": "abc"}, "v not_in abc,def") is False


def test_N7_error_message_lists_negation_ops(wd):
    """모르는 op 거절문이 새 연산자를 안내 목록에 싣는다."""
    with pytest.raises(wd._WhereError) as ei:
        wd._apply_op("bogus_op", 1, 2)
    assert "not_in" in str(ei.value)
    assert "not_contains" in str(ei.value)


def test_N8_positive_ops_unchanged(wd):
    """무회귀 — 기존 in/contains 판정 불변."""
    assert wd._match({"v": "aaa"}, {"field": "v", "op": "in", "value": ["aaa"]}) is True
    assert wd._match({"v": "ccc"}, {"field": "v", "op": "in", "value": ["aaa"]}) is False
    assert wd._match({"t": "복층 테라스"}, {"field": "t", "op": "contains", "value": "복층"}) is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
