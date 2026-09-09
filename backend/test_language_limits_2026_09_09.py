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
def test_literal_list_head_flows_as_items_currency():
    r = execute('[{a: 1, b: "x >> y"}, {a: 2, b: "z"}] >> [table:select]{columns: ["a"]}')
    assert r["success"], r.get("error")
    assert final(r)["items"] == [{"a": 1}, {"a": 2}]        # 문자열 속 `>>` 는 구조가 아니다


def test_literal_head_with_variable_reference_writes_json():
    r = execute('$최신 = [self:file_find]{path:"drafts",pattern:"*.md"} >> [table:sort]{by:"mtime",desc:true} >> [table:take]{n:1}\n'
                '[{path: "${최신.items.0.path}", start_line: 11}] >> [self:write]{path:"outputs/result.json", format:"json"}')
    assert r["success"], r.get("error")
    assert "1행" in final(r)["message"]


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
def test_fallback_branch_may_start_with_a_variable_pipe():
    r = execute('$q = [self:read]{path:"locations.json"}\n'
                '($q >> [table:filter]{where: "줄번호 > 100"}) ?? ($q >> [table:take]{n: 1})')
    assert r["success"], r.get("error")
    out = final(r)
    assert out["items"] == [{"파일": "notes/01.txt", "줄번호": 4}] and out.get("_fallback_used") == 2


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
def test_rename_candidate_set_keeps_the_one_present_column():
    r = execute('[self:read]{path:"locations.json"} >> [table:rename]{map: {파일: "file", path: "file", 줄번호: "line", lineno: "line"}}')
    assert r["success"], r.get("error")
    assert final(r)["items"][0] == {"file": "notes/01.txt", "line": 4}


def test_rename_candidate_set_with_no_present_column_is_an_honest_error():
    r = execute('[self:read]{path:"locations.json"} >> [table:rename]{map: {p: "file", path: "file"}}')
    assert not r["success"] and "후보" in r["error"] and "하나도 없습니다" in r["error"]


def test_rename_two_present_columns_to_one_name_still_refused_and_single_absent_still_refused():
    r = execute('[self:read]{path:"locations.json"} >> [table:rename]{map: {파일: "k", 줄번호: "k"}}')
    assert not r["success"] and "함께 접힙니다" in r["error"]
    r = execute('[self:read]{path:"locations.json"} >> [table:rename]{map: {없는열: "file"}}')
    assert not r["success"] and "없는열" in r["error"]


@pytest.mark.parametrize('code', [
    '[{파일:"a.txt"}] >> [table:rename]{map:{파일:"file",path:"file"}}',
    '[table:rename]{items:[{파일:"a.txt"}],map:{파일:"file",path:"file"}}',
    '[{파일:"a.txt",extra:1}] >> [table:select]{columns:["파일"]} '
    '>> [table:rename]{columns:{파일:"file",path:"file"}}',
    '$q=[{path:"a.txt"}]; ($q >> [table:filter]{where:"path eq missing"} '
    '>> [table:rename]{map:{파일:"file",path:"file"}}) '
    '?? ($q >> [table:rename]{map:{파일:"file",path:"file"}})',
])
def test_rename_candidate_compositions_validate_and_execute(code):
    from api_ibl import validate_code
    code += ' >> [table:select]{columns:["file"]}'
    checked = validate_code(code)
    assert checked['valid'] and checked['typecheck']['ok'], checked
    assert not checked['typecheck']['issues'], checked
    r = execute(code)
    assert r['success'], r
    assert final(r)['items'] == [{'file': 'a.txt'}]


@pytest.mark.parametrize('head', ['[] >> ', '[{}] >> '])
def test_rename_unobserved_candidate_columns_do_not_reject_empty_input(head):
    r = execute(head + '[table:rename]{map:{파일:"file",path:"file"}}')
    assert r['success'], r
    assert final(r)['items'] == ([] if head.startswith('[]') else [{}])


def test_rename_atomic_swap_keeps_both_values():
    r = execute('[{a:1,b:2}] >> [table:rename]{map:{a:"b",b:"a"}}')
    assert r['success'], r
    assert final(r)['items'] == [{'b': 1, 'a': 2}]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
