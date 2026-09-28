"""상상훈련 70회차 수리 가드 — 지역 함수 분해·함수 계약·값 자리 호출의 검사 근거.

공통 뿌리: 검사가 값이 아니라 글자 모양(병렬 쓰기 자원)·저장소만(describe)·범용 문구(진단 안내)로 판정했다.
정본: docs/experiments/imagination_round70_2026_09_28/report.md
"""
import ast
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

from ibl_v2_adapters import Adapter
from ibl_v2_compile import compile_program
from ibl_v2_ir import Fault
from ibl_v2_types import TEXT, Type, join, static_text

ROOT = Path(__file__).resolve().parents[1]
GENERIC = '해당 위치의 계약과 호출 인자를 확인하세요.'


def writer():
    return Adapter({"version": 1, "params": {"path": "Text", "content": "Text"}, "required": ["path", "content"],
                    "pipe_input": "content", "result": "Record", "effects": ["write_external"],
                    "write_resources": {"file": "path"}}, lambda rt, a: {"ok": True})


REG = {"test:write": writer()}
W = 'test:write'


def codes(source, registry=REG):
    return [i["code"] for i in compile_program(source, registry).issues]


# B70-2 — 병렬 쓰기 자원은 글자 모양이 아니라 컴파일 시 값으로 식별한다
@pytest.mark.parametrize("source", [
    f'[{W}]{{path:"a",content:"1"}} & [{W}]{{path:"a",content:"2"}}',
    f'$p="a"\n[{W}]{{path:$p,content:"1"}} & [{W}]{{path:$p,content:"2"}}',
    f'[def:기록]($c,$p="a"){{ [{W}]{{path:$p,content:$c}} }}\n[fn:기록]{{c:"1"}} & [fn:기록]{{c:"2"}}',
    f'[def:기록]($c,$p){{ [{W}]{{path:$p,content:$c}} }}\n$경로="a"\n[fn:기록]{{c:"1",p:$경로}} & [fn:기록]{{c:"2",p:$경로}}',
    f'[def:양쪽]($p){{ [{W}]{{path:$p,content:"1"}} & [{W}]{{path:$p,content:"2"}} }}\n[fn:양쪽]{{p:"a"}}',
    f'[def:안]($c){{ $p="a"; [{W}]{{path:$p,content:$c}} }}\n[fn:안]{{c:"1"}} & [fn:안]{{c:"2"}}',
    f'$월="09"\n[{W}]{{path:f"r_${{$월}}.txt",content:"1"}} & [{W}]{{path:f"r_${{$월}}.txt",content:"2"}}',
    f'["A","B","C"] >> [table:each]{{parallel:3}}{{ [{W}]{{path:"a",content:$it}} }}',
    f'["A","A"] >> [table:each]{{parallel:2}}{{ [{W}]{{path:f"${{$it}}.txt",content:$it}} }}',
    f'return {{둘:([{W}]{{path:"a",content:"1"}} & [{W}]{{path:"a",content:"2"}})}}',
    f'([{W}]{{path:"a",content:"1"}} & [{W}]{{path:"b",content:"1"}}) & [{W}]{{path:"a",content:"2"}}',
])
def test_same_known_resource_in_parallel_is_a_conflict_whatever_its_spelling(source):
    assert "PARALLEL_WRITE_CONFLICT" in codes(source)


@pytest.mark.parametrize("source", [
    f'[{W}]{{path:"a",content:"1"}} & [{W}]{{path:"b",content:"2"}}',
    f'["A","B"] >> [table:each]{{parallel:2}}{{ [{W}]{{path:f"${{$it}}.txt",content:$it}} }}',
    f'["A","B"] >> [table:each]{{ [{W}]{{path:"a",content:$it}} }}',
    f'["A"] >> [table:each]{{parallel:4}}{{ [{W}]{{path:"a",content:$it}} }}',
    f'$p="a"\n[{W}]{{path:$p,content:"1"}}; [{W}]{{path:$p,content:"2"}}',
    # 흐름이 합류하면 값이 둘일 수 있다 — 알 수 없는 자원은 충돌로 증명하지 않는다(설계 경계 유지)
    f'$x=1\n[if:$x>0]{{ $p="a" }}[else]{{ $p="b" }}\n[{W}]{{path:$p,content:"1"}} & [{W}]{{path:"a",content:"2"}}',
    f'$p="a"\n[repeat:2]{{ $p=f"b${{$i}}" }}\n[{W}]{{path:$p,content:"1"}} & [{W}]{{path:"a",content:"2"}}',
    f'[def:기록]($c,$p){{ [{W}]{{path:$p,content:$c}} }}\n[fn:기록]{{c:"1",p:"a"}} & [fn:기록]{{c:"2",p:"b"}}',
])
def test_distinct_or_unknown_resources_are_not_conflicts(source):
    assert "PARALLEL_WRITE_CONFLICT" not in codes(source)


def test_known_text_is_a_refinement_not_a_type():
    known = Type("Text", literal="a")
    assert str(known) == "Text" and static_text(known) == "a"
    assert join(known, Type("Text", literal="b")) == TEXT
    assert static_text(join(known, Type("Text", literal="a"))) == "a"
    rows = [Type("Record", (("url", Type("Text", literal=u)), ("t", TEXT)), open=False) for u in ("x", "y")]
    assert str(join(*rows)) == "{url: Text, t: Text}"  # 필드 순서는 값이 없을 때와 같다


def test_contract_strings_do_not_carry_known_values():
    plan = compile_program('[def:f]($p){ return $p }\nreturn [fn:f]{p:"비밀아님"}')
    contract = next(iter(plan.function_contracts.values()))
    assert contract["params"] == {"p": "Text"} and contract["result"] == "Text"


# F70-2 — 값 경로와 떨어지는 경로가 섞인 함수
def test_function_mixing_value_and_fallthrough_paths_warns_once():
    plan = compile_program('[def:등급]($s){ [if:$s>=90]{ return "A" } }\n'
                           'return [[fn:등급]{s:95},[fn:등급]{s:50}]')
    warned = [w for w in plan.preflight["warnings"] if w["code"] == "UNIT_RETURN_PATH"]
    assert len(warned) == 1 and not plan.issues
    assert warned[0]["hint"] != GENERIC


@pytest.mark.parametrize("source", [
    '[def:등급]($s){ [if:$s>=90]{ return "A" } [else]{ return "B" } }\nreturn [fn:등급]{s:1}',
    f'[def:기록]($c){{ [{W}]{{path:"a",content:$c}}; $x=1 }}\n[fn:기록]{{c:"1"}}',
    '[def:끝]($s){ [if:$s>0]{ return } }\n[fn:끝]{s:1}',
    '[def:값]($s){ $s * 2 }\nreturn [fn:값]{s:1}',
])
def test_consistent_functions_do_not_warn(source):
    plan = compile_program(source, REG)
    assert "UNIT_RETURN_PATH" not in [w["code"] for w in plan.preflight["warnings"]]


# F70-1 — 컴파일 진단은 코드마다 고치는 법을 말한다
def _diagnostic_codes():
    found = set()
    for path in (ROOT / "backend").rglob("*.py"):
        if path.name.startswith("test_"):
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("issue", "warn") and len(node.args) >= 2
                    and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str)
                    and node.args[1].value.isupper()):
                found.add(node.args[1].value)
    return found


def test_every_compile_diagnostic_code_has_its_own_hint():
    from ibl_v2_analysis import HINTS
    found = _diagnostic_codes()
    assert len(found) > 25
    assert sorted(found - set(HINTS)) == []
    assert all(HINTS[c] != GENERIC for c in found)


@pytest.mark.parametrize("source,code,needle", [
    ('[def:팩]($n){ $r=[fn:팩]{n:$n}; return $r }\nreturn [fn:팩]{n:1}', "RECURSION", "repeat"),
    ('[def:f]($x){ return 1 }\n[def:f]($x){ return 2 }\nreturn [fn:f]{x:0}', "DUPLICATE_FUNCTION", "이름"),
    (f'[{W}]{{path:"a",content:"1"}} & [{W}]{{path:"a",content:"2"}}', "PARALLEL_WRITE_CONFLICT", "순차"),
    ('[def:할인]($가격,$최종=$가격*0.9){ return $최종 }\nreturn [fn:할인]{가격:1}', "UNBOUND", "기본값"),
])
def test_hints_name_the_repair(source, code, needle):
    plan = compile_program(source, REG)
    from ibl_v2_analysis import finish_diagnostics  # noqa: F401 — compile_program 이 이미 적용
    issue = next(i for i in plan.issues if i["code"] == code)
    assert needle in issue["hint"], issue
    assert "첫 판본" not in issue["message"]


def test_outer_variable_unbound_keeps_argument_hint():
    plan = compile_program('$세율=0.1\n[def:세금]($x){ return $x*$세율 }\nreturn [fn:세금]{x:1}')
    issue = next(i for i in plan.issues if i["code"] == "UNBOUND")
    assert "인자" in issue["hint"] and "기본값" not in issue["hint"]


# F70-3 — 숫자로 시작하는 레코드 키
@pytest.mark.parametrize("source,shown", [('return {3월:1}', '"3월"'), ('return {1:2}', '"1"')])
def test_numeric_record_key_names_the_quoted_form(source, shown):
    with pytest.raises(Fault) as exc:
        compile_program(source)
    assert "따옴표" in str(exc.value) and shown in str(exc.value)


def test_quoted_numeric_keys_still_work():
    plan = compile_program('return {"3월":1, "1면":"a"}')
    assert not plan.issues


# B70-1 — 코드와 함께 준 describe 는 제출 원문의 지역 정의를 먼저 해소한다
def test_describe_with_code_resolves_program_definition_first(monkeypatch):
    import ibl_v2_store
    from model_result_view import describe_actions
    monkeypatch.setattr(ibl_v2_store, "definitions", lambda: {})
    code = '#!ibl edition=2\n[def:주간보고]($목록,$k=2){ return len($목록)*$k }\nreturn [fn:주간보고]{목록:[1]}'
    rows = describe_actions(["fn:주간보고"], None, edition=2, program=code)["actions"]
    contract = rows[0]["definition"]["callable_contract"]
    assert rows[0]["definition"]["source"] == "program"
    assert contract["pipe_input"] == "목록" and contract["default_expressions"] == {"k": "2"}
    # 코드 없이 부르면 종전대로 저장소만 본다
    assert describe_actions(["fn:주간보고"], None, edition=2)["actions"][0].get("error")


def test_program_definition_shadows_stored_one_like_the_executor(monkeypatch):
    import ibl_v2_store
    from model_result_view import describe_actions
    monkeypatch.setattr(ibl_v2_store, "definitions", lambda: {"요약": "#!ibl edition=2\n[def:요약]($a,$b){ return $a }"})
    code = '#!ibl edition=2\n[def:요약]($목록){ return len($목록) }\nreturn [fn:요약]{목록:[1]}'
    contract = describe_actions(["fn:요약"], None, edition=2, program=code)["actions"][0]["definition"]["callable_contract"]
    assert list(contract["params"]) == ["목록"]


def test_describe_with_invalid_program_still_reports_program_signature(monkeypatch):
    import ibl_v2_store
    monkeypatch.setattr(ibl_v2_store, "definitions", lambda: {})
    found = ibl_v2_store.program_functions('#!ibl edition=2\n[def:f]($x){ return $x }\nreturn $없음')
    assert found["f"]["status"] == "invalid" and found["f"]["callable_contract"]["pipe_input"] == "x"
    assert ibl_v2_store.program_functions('#!ibl edition=2\n[def:f]($x){') == {}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
