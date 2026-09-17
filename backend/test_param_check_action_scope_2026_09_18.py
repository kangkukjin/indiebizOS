"""인자 검사는 액션의 선언으로 판정한다 (2026-09-18) — 같은 패키지 다른 액션의 키를 빌려주지 않고, 없는 op 을 말한다."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__)); import boot_paths  # noqa
from ibl_param_vocab import check_code_params, unknown_op_message


def _unknown(code):
    return [k for i in check_code_params(code) for k in i["unknown"]]


def test_sibling_action_key_no_longer_passes():
    # script 는 id 로 부른다 — name 은 같은 패키지 다른 액션들이 읽는 키라 옛 판에서 통과했다
    assert _unknown('[self:script]{name: "정리"}') == ["name"]


def test_declared_keys_and_aliases_pass():
    assert not check_code_params('[self:read]{path: "장부.xlsx", format: "xlsx", sheet: "매출"}')
    assert not check_code_params('[sense:researcher]{op: "find", query: "홍길동"}')
    assert not check_code_params('[limbs:browser]{op: "type", ref: "e1", text: "검색어", submit: true}')


def test_unknown_op_is_reported_everywhere_check_params_runs():
    issues = check_code_params('[sense:stock]{op: "nope", ticker: "005930"}')
    assert issues and issues[0]["unknown_op"] == "nope" and "사용 가능" in issues[0]["message"]


def test_dynamic_or_placeholder_op_abstains():
    cfg = {"ops": {"values": {"quote": "시세"}}}
    assert unknown_op_message(cfg, {"op": "$op"}) is None
    assert unknown_op_message(cfg, {"op": "<동작>"}) is None
    assert unknown_op_message({}, {"op": "anything"}) is None      # op 선언이 없는 액션은 판정하지 않는다
    assert unknown_op_message(cfg, {"op": "quote"}) is None


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__] + sys.argv[1:]))
