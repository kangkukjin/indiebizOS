"""46회차 상상훈련 — 텍스트 매칭·멤버십·관계 키 표현 동등성 회귀 시험.

축(4배=192칸): A 텍스트 연산자×정규화 모양 · B 비문자열/결측 좌변×텍스트 연산자 ·
C where vs api_transforms 표면 동형성 · D 관계 키 표면×값 표현 모양.
결함 7부류(B46-1~7)의 원 62칸과 경계를 지킨다. 판정의 정본은
common.value_semantics 한 벌(text_match/list_membership/regex_text/관계·그룹 식별자)이다.
"""

import importlib.util
import unicodedata
from pathlib import Path

import pytest

from common.value_semantics import (group_identity, list_membership,
                                    relation_identity, text_match, values_equal)
from ibl.api_transforms import _match_condition
from ibl.ibl_predicates import Evaluator, PredicateError

_HANDLER = (Path(__file__).resolve().parent.parent / "data" / "packages" /
            "installed" / "tools" / "data-ops" / "handler.py")


def _load_handler():
    spec = importlib.util.spec_from_file_location("round46_data_ops", _HANDLER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def data_ops():
    return _load_handler()


NFD = lambda s: unicodedata.normalize("NFD", s)  # noqa: E731


# ── B46-1 — 부분일치 연산자가 eq 의 텍스트 정규화(공백·casefold·NFC)를 승계한다 ──

_NORMALIZED_TRUE = [
    ("양끝공백", "  서울맛집  ", "서울맛집"),
    ("casefold_ß", "STRASSE", "straße"),
    ("NFD한글", NFD("가나다"), "가나다"),
    ("대소문자", "Seoul Food", "seoul food"),
]


@pytest.mark.parametrize("name,left,right", _NORMALIZED_TRUE)
def test_round46_partial_ops_inherit_eq_text_normalization(data_ops, name, left, right):
    for op in ("contains", "startswith", "endswith", "in"):
        assert data_ops._wdsl._apply_op(op, left, right) is True, (name, op)


def test_round46_fullwidth_stays_distinct_everywhere(data_ops):
    """전각은 침묵 수선하지 않는다(숫자 문법과 같은 판정) — 전 표면 일관 불일치."""
    for op in ("eq", "contains", "startswith", "endswith", "in"):
        assert data_ops._wdsl._apply_op(op, "ＡＢＣ", "ABC") is False, op
    assert relation_identity("ＡＢＣ") != relation_identity("ABC")
    assert group_identity("ＡＢＣ") != group_identity("ABC")


# ── B46-2 — NFC/NFD 정규형은 같은 실체다 (macOS 파일명 직격) ─────────────────

def test_round46_nfd_equals_nfc_across_value_surfaces(data_ops):
    left, right = NFD("가나"), "가나"
    assert values_equal(left, right) is True
    assert data_ops._wdsl._apply_op("matches", left, right) is True
    assert Evaluator.compare("matches", left, right) is True
    assert relation_identity(left) == relation_identity(right)
    assert group_identity(left) == group_identity(right)
    # 구조 안쪽까지 재귀 승계
    assert values_equal({"파일": left}, {"파일": right}) is True


def test_round46_group_identity_stays_strict_for_case_and_space():
    """group 은 엄격(JSON 값 보존) — NFC 만 접고 대소문자·공백은 다른 값."""
    assert group_identity("Seoul") != group_identity("seoul")
    assert group_identity("a  b") != group_identity("a b")


# ── B46-3 — 결측 좌변은 부분일치에서 아무것도 주장하지 않는다 ────────────────

def test_round46_null_left_asserts_nothing_in_partial_ops(data_ops):
    for op, needle in (("contains", "none"), ("startswith", "none"),
                       ("endswith", "one"), ("in", "none이 든 문장")):
        assert data_ops._wdsl._apply_op(op, None, needle) is False, op
    assert data_ops._wdsl._apply_op("matches", None, "가") is False


def test_round46_null_filter_contains_excludes_row_honestly(data_ops):
    result = data_ops._op_filter(
        {"items": [{"메모": None}, {"메모": "none 이라는 단어"}]},
        {"where": {"field": "메모", "op": "contains", "value": "none"}})
    assert result["success"] is True
    assert len(result["items"]) == 1
    assert result["items"][0]["메모"] == "none 이라는 단어"


# ── B46-4 — 구조 좌변의 repr 누출 금지 · list contains 는 원소 멤버십 ────────

def test_round46_structure_left_never_matches_by_repr(data_ops):
    apply_op = data_ops._wdsl._apply_op
    assert apply_op("contains", {"a": "가나"}, "가나") is False
    assert apply_op("contains", ["가나", "다라"], "'가나'") is False  # repr 따옴표 함정
    assert apply_op("matches", ["가나"], "가나") is False
    assert apply_op("matches", {"a": 1}, "a") is False
    assert apply_op("startswith", ["가나"], "가나") is False


def test_round46_list_contains_is_element_membership(data_ops):
    apply_op = data_ops._wdsl._apply_op
    assert apply_op("contains", ["가나", "다라"], "가나") is True
    assert apply_op("contains", ["가나", "다라"], "가") is False  # 부분 문자열 아님
    assert apply_op("contains", [1000, 2000], "1,000") is True   # 원소 동등성은 eq 계약


def test_round46_block_matches_rejects_structure_left_honestly():
    with pytest.raises(PredicateError):
        Evaluator.compare("matches", ["가나"], "가나")


# ── B46-5 — in 목록 멤버십의 동등성은 values_equal 한 벌 ─────────────────────

def test_round46_membership_uses_conditional_equality(data_ops):
    apply_op = data_ops._wdsl._apply_op
    assert apply_op("in", True, [1, 0]) is False          # bool 은 숫자와 절대 같지 않다
    assert apply_op("in", 1.5, ["1.5"]) is True           # 숫자 표기 동등
    assert apply_op("in", 1, ["1"]) is True
    assert apply_op("in", "true", [True]) is True         # bool==텍스트 기존 공개 계약
    assert apply_op("in", "Seoul", ["seoul"]) is True
    assert apply_op("in", " 서울 ", ["서울"]) is True
    assert apply_op("in", "1,000", [1000]) is True
    assert apply_op("in", None, [None, 1]) is True        # 결측 동등 검색 보존
    assert apply_op("in", None, [1, 2]) is False


# ── B46-6 — api_transforms 응답 필터는 where 와 같은 판결 ───────────────────

_CROSS_SURFACE = [
    ("숫자vs문자열", 1, "1"),
    ("truestr_vs_true", "true", True),
    ("대소문자", "Seoul", "seoul"),
    ("양끝공백", " 서울 ", "서울"),
    ("NFD", NFD("가나"), "가나"),
]


@pytest.mark.parametrize("name,left,right", _CROSS_SURFACE)
def test_round46_api_filter_agrees_with_where(data_ops, name, left, right):
    apply_op = data_ops._wdsl._apply_op
    item = {"f": left}
    assert (_match_condition(item, {"field": "f", "contains": right})
            == apply_op("contains", left, right)), name
    assert (_match_condition(item, {"field": "f", "in": [right]})
            == apply_op("in", left, [right])), name


def test_round46_api_contains_no_raw_typeerror():
    """비문자열 우변·좌변이 파이썬 TypeError 로 새지 않는다."""
    assert _match_condition({"f": "value true"}, {"field": "f", "contains": True}) is True
    assert _match_condition({"f": "1,000"}, {"field": "f", "contains": 1000}) is False
    assert _match_condition({"f": 100}, {"field": "f", "contains": "10"}) is True


def test_round46_api_negatives_assert_nothing_on_missing():
    """결측 좌변은 not_contains/not_in 도 주장하지 않는다(ne 결측 계약)."""
    assert _match_condition({}, {"field": "f", "not_contains": "가"}) is False
    assert _match_condition({}, {"field": "f", "not_in": [1, 2]}) is False
    assert _match_condition({"f": "다라"}, {"field": "f", "not_contains": "가"}) is True
    assert _match_condition({"f": 3}, {"field": "f", "not_in": [1, 2]}) is True
    assert _match_condition({"f": True}, {"field": "f", "not_in": [1, 2]}) is True


# ── B46-7 — 관계 키(join/dedup/merge)는 filter eq 의 숫자 표기 동등을 승계 ──

_NUMERIC_SAME_ENTITY = [
    ("int_float", 1, 1.0),
    ("쉼표숫자", "1,000", 1000),
    ("선행0", "02", 2),
    ("NFD", NFD("가나"), "가나"),
]


@pytest.mark.parametrize("name,v1,v2", _NUMERIC_SAME_ENTITY)
def test_round46_relation_keys_fold_numeric_and_nfc(data_ops, name, v1, v2):
    dedup = data_ops._op_dedup({"items": [{"k": v1}, {"k": v2}]}, {"by": "k"})
    assert len(dedup["items"]) == 1, ("dedup", name)
    merged = data_ops._op_merge(
        [{"items": [{"k": v1}]}, {"items": [{"k": v2}]}], {"by": "k"})
    assert len(merged["items"]) == 1, ("merge", name)
    joined = data_ops._op_join(
        [{"items": [{"k": v1, "l": 1}]}, {"items": [{"k": v2, "r": 2}]}], {"on": "k"})
    assert len(joined["items"]) == 1, ("join_items", name)
    tjoined = data_ops._op_join(
        [{"table": {"columns": ["k", "l"], "rows": [[v1, 1]]}},
         {"table": {"columns": ["k", "r"], "rows": [[v2, 2]]}}], {"on": "k"})
    rows = (tjoined.get("table") or {"rows": tjoined.get("rows", [])}).get("rows", [])
    assert len(rows) == 1, ("join_table", name)


def test_round46_relation_keys_keep_distinct_entities(data_ops):
    """접으면 안 되는 것 — 서로 다른 수·bool/숫자·전각·빈 키는 그대로 다르다."""
    assert relation_identity(1) != relation_identity(2)
    assert relation_identity(True) != relation_identity(1)      # "true" vs "1"
    assert relation_identity(2.5) == relation_identity("2.5")
    assert relation_identity(2.5) != relation_identity(2)
    assert relation_identity("") == relation_identity(None)     # 빈 키=키 없음 (B38-3)
    dedup = data_ops._op_dedup({"items": [{"k": 1}, {"k": 2}]}, {"by": "k"})
    assert len(dedup["items"]) == 2


# ── 한 벌 소유 관문 — 사설 부분일치 판정의 재발을 막는다 ────────────────────

def test_round46_single_owner_gate(data_ops):
    """where·api_transforms 의 텍스트 연산자가 common 한 벌을 쓰는지 동작으로 검증."""
    for op in ("contains", "startswith", "endswith"):
        assert data_ops._wdsl._apply_op(op, "  ＡB한글  ", NFD("한글")) == \
            text_match(op, "  ＡB한글  ", NFD("한글")), op
    assert data_ops._wdsl._apply_op("in", 1.5, ["1.5"]) == list_membership(1.5, ["1.5"])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
