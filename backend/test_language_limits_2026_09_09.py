"""언어 개정 2026-09-09 (사용자 판정 "남긴 언어 한계 셋도 다 고쳐") 관문.

① 값 구성 리터럴을 파이프 머리로: `[{…}] >> [self:write]{…}`
② 폴백 괄호 가지의 변수 머리: `($q >> [table:filter]{…}) ?? ($q >> [table:take]{n:1})` (변수 홀로는 종전대로 거절)
③ rename 의 같은 새 이름 옛 이름들 = 후보 집합(실물 정확히 하나)
격리 실행기(실 파서·실행기·data-ops·파일 핸들러)로 돈다.
"""
import json
import sys
from pathlib import Path

import pytest
import boot_paths  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from idiom_exposure_worker import run  # noqa: E402

REG = json.loads((ROOT / "docs/experiments/idiom_exposure_2026_09_09_v3/registry.json").read_text())


def execute(code):
    return run({"code": code, "case_id": "direct_context", "seed": 1, "registry": REG})["result"]


def final(r):
    return json.loads(r["final_result"]) if isinstance(r.get("final_result"), str) else r.get("final_result")


# ── ① 리터럴 파이프 머리 ────────────────────────────────────────────────────────




def test_literal_head_parses_as_nameless_assign_and_actions_are_untouched():
    from ibl_parser import parse_with_vars, _is_value_literal_head
    steps, _ = parse_with_vars('[{a: 1}] >> [table:take]{n: 1}')
    assert steps[0].get("_assign") and steps[0].get("_literal_head") and steps[0]["name"] is None
    assert steps[1]["_node"] == "table"
    for head in ('[self:read]{path:"x"}', '[if: 1 == 1]{[self:time]}', '[try]{[self:time]}', '[fn:이름]{}', '[def: 이름]{ todo }'):
        assert not _is_value_literal_head(head), head
    for lit in ('[{a: 1}]', '[1, 2]', '["a"]', '[]', '{a: 1}', '[$x]', '[true]'):
        assert _is_value_literal_head(lit), lit


def test_bare_literal_statement_without_pipe_is_still_rejected():
    from ibl_parser import parse_with_vars, IBLSyntaxError
    with pytest.raises(IBLSyntaxError):
        parse_with_vars('[{a: 1}]')


# ── ② 폴백 괄호 가지의 변수 머리 ───────────────────────────────────────────────


def test_fallback_bare_variable_is_still_not_an_attempt():
    from ibl_parser import parse_with_vars, IBLSyntaxError
    for code in ('$q = [self:time]\n$q ?? [self:time]', '$q = [self:time]\n($q) ?? [self:time]'):
        with pytest.raises(IBLSyntaxError, match="시도"):
            parse_with_vars(code)


def test_fallback_container_carries_branch_vars_like_parallel():
    from ibl_parser import parse_with_vars
    steps, _ = parse_with_vars('$q = [self:time]\n($q >> [table:take]{n: 1}) ?? [self:time]')
    fb = steps[-1]
    assert "_fallback_chain" in fb and fb["_vars"] == {"q": 0}
    assert fb["_fallback_chain"][0]["_branch_steps"][0]["_var_emit"]


# ── ③ rename 후보 집합 ─────────────────────────────────────────────────────────












if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
