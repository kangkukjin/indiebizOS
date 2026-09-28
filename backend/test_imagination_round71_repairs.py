"""상상훈련 71회차 수리 가드 — 저장 함수의 수명주기(저장·개정·이행·삭제)와 중첩 진단.

공통 뿌리: 저장소를 바꾸는 쓰기가 자기 항목만 보고(이름 겹침·호출자), 불변식 위반은 읽을 때 전역으로
터졌으며, 안쪽 판본 2 실패의 진단은 옛 도구 봉투의 허용 목록에서 버려졌다.
정본: docs/experiments/imagination_round71_2026_09_28/report.md
"""
import copy
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

import ibl_v2_store
import workflow_store

PROJECT = str(Path(__file__).resolve().parents[1] / "projects" / "컨텐츠")
GRADE = '[def:등급]($s){ [if:$s>=90]{ return "A" } [else] { return "B" } }'
GRADE_RENAMED = '[def:등급]($점수){ [if:$점수>=90]{ return "A" } [else] { return "B" } }'
SHEET = '[def:성적표]($목록){ $목록 >> [table:each]{ {점수:$it, 등급:[fn:등급]{s:$it}} } }'
SUMMARY = '[def:요약]($목록){ $t=[fn:성적표]{목록:$목록}; return len($t) }'


@pytest.fixture
def store(tmp_path, monkeypatch):
    """임시 저장소 + 관용구 별칭 하나(정렬해추리기) — 실제 원장·색인은 건드리지 않는다."""
    monkeypatch.setattr(workflow_store, "_get_workflows_path", lambda: tmp_path)
    real = ibl_v2_store.definitions

    def definitions():
        out = ibl_v2_store.Library()
        out.add("정렬해추리기", "#!ibl edition=2\n[def:정렬해추리기]($x){ return $x }", "관용구:정렬해추리기")
        for path in sorted(tmp_path.glob("*.yaml")):
            import yaml
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("edition") == 2:
                out.add(data.get("name"), data.get("code", ""), f"저장본:{path.stem}")
        return out

    assert real is not None
    monkeypatch.setattr(ibl_v2_store, "definitions", definitions)
    return tmp_path


def save(code, **extra):
    return ibl_v2_store.action("save", {"code": code, **extra}, PROJECT)


def run(code):
    from ibl_v2_entry import handle_request
    return handle_request({"edition": 2, "code": "#!ibl edition=2\n" + code}, PROJECT)


# B71-1 — 이름 하나에 정의 하나: 쓰는 자리에서 막고, 읽을 때는 겹친 이름만 국소화한다
def test_same_name_under_another_id_is_rejected_and_language_keeps_running(store):
    assert save('[def:배수]($x){ return $x * 2 }')["success"]
    r = save('[def:배수]($x){ return $x * 3 }', workflow_id="배수-v2")
    assert r["success"] is False and r["diagnostic"]["code"] == "DUPLICATE_LIBRARY"
    assert 'workflow_id:"배수"' in r["error"] and "[def:배수2]" in r["error"]
    assert not (store / "배수-v2.yaml").exists()
    assert run("return 1+1")["value"] == 2


def test_idiom_name_cannot_be_taken_by_a_saved_function(store):
    r = save('[def:정렬해추리기]($x){ return $x }')
    assert r["success"] is False and "관용구:정렬해추리기" in r["error"]
    assert "workflow_id" not in r["error"]  # 관용구는 저장 ID로 고칠 수 있는 대상이 아니다


def test_resave_same_id_and_name_only_resave_are_revisions(store):
    assert save('[def:할인]($p){ return $p * 0.9 }', workflow_id="it-discount")["success"]
    # 저장 ID를 안 주면 그 이름을 가진 저장본의 개정이다 — 새 파일을 만들어 겹치지 않는다
    assert save('[def:할인]($p){ return $p * 0.8 }')["success"]
    assert sorted(p.stem for p in store.glob("*.yaml")) == ["it-discount"]
    assert save('[def:할인]($p){ return $p * 0.7 }', workflow_id="it-discount")["success"]


def test_duplicate_on_disk_only_breaks_calls_to_that_name(store):
    for wid in ("a", "b"):
        (store / f"{wid}.yaml").write_text('edition: 2\nname: 겹침\ncode: "[def:겹침]($x){ return $x }"\n',
                                           encoding="utf-8")
    assert run("return 2+2")["value"] == 4
    issue = run("return [fn:겹침]{x:1}")["issues"][0]
    assert issue["code"] == "DUPLICATE_LIBRARY" and "저장본:a" in issue["message"]
    assert "op:" in issue["hint"] and "다른 함수는 영향이 없습니다" in issue["hint"]
    problems = [w["problem"] for w in workflow_store.list_workflows() if w["name"] == "겹침"]
    assert len(problems) == 2 and all("같은 이름의 저장 정의가 여럿" in p for p in problems)
    assert "고를 수 없습니다" in ibl_v2_store.describe("겹침")["error"]


def test_library_conflicts_survive_the_compilers_deepcopy():
    lib = ibl_v2_store.Library()
    lib.add("f", "[def:f]($x){ return $x }", "저장본:a")
    lib.add("f", "[def:f]($x){ return $x }", "저장본:b")
    copied = copy.deepcopy(lib)
    assert "f" not in copied and copied.conflicts == {"f": ["저장본:a", "저장본:b"]}


def test_plain_dict_definitions_are_wrapped(monkeypatch):
    monkeypatch.setattr(ibl_v2_store, "definitions", lambda: {"f": "[def:f]($x){ return $x }"})
    lib = ibl_v2_store.library()
    assert isinstance(lib, ibl_v2_store.Library) and lib.conflicts == {} and "f" in lib


# B71-2 — 개정·삭제는 저장 호출자를 확인한다 (workflow.md 의 약속)
def test_revision_that_breaks_callers_is_rejected_naming_them_transitively(store):
    for code in (GRADE, SHEET, SUMMARY):
        assert save(code)["success"]
    r = save(GRADE_RENAMED)
    assert r["success"] is False
    assert [b["name"] for b in r["broken_callers"]] == ["성적표", "요약"]
    assert r["broken_callers"][0]["code"] == "MISSING_ARGUMENT"
    assert "[def:등급2]" in r["error"] and "옛 정의를 지우세요" in r["error"]
    assert run("return [fn:성적표]{목록:[95]}")["value"] == [{"점수": 95, "등급": "A"}]


def test_compatible_revision_and_callerless_revision_are_allowed(store):
    save(GRADE)
    save(SHEET)
    assert save('[def:등급]($s){ [if:$s>=80]{ return "A" } [else] { return "B" } }')["success"]
    assert save('[def:홀로]($x){ return $x }')["success"]
    assert save('[def:홀로]($y){ return $y }')["success"]


def test_already_broken_caller_does_not_hold_other_revisions_hostage(store):
    save(GRADE)
    (store / "깨진.yaml").write_text(
        'edition: 2\nname: 깨진\ncode: "[def:깨진]($l){ return [fn:등급]{없는인자:1} }"\n', encoding="utf-8")
    assert save(GRADE_RENAMED)["success"]


def test_return_type_change_breaking_a_caller_is_caught(store):
    save('[def:합]($l){ return {합계:len($l)} }')
    save('[def:두배합]($l){ $r=[fn:합]{l:$l}; return $r.합계 * 2 }')
    r = save('[def:합]($l){ return len($l) }')
    assert r["success"] is False and [b["name"] for b in r["broken_callers"]] == ["두배합"]


def test_migration_path_new_name_switch_callers_then_delete(store):
    from workflow_engine import execute_workflow_action
    save(GRADE)
    save(SHEET)
    assert save(GRADE_RENAMED.replace("[def:등급]", "[def:등급2]"))["success"]
    assert save(SHEET.replace("[fn:등급]{s:$it}", "[fn:등급2]{점수:$it}"))["success"]
    assert execute_workflow_action("delete", {"workflow_id": "등급"}, PROJECT)["success"]
    assert run("return [fn:성적표]{목록:[70]}")["value"] == [{"점수": 70, "등급": "B"}]


def test_delete_of_a_called_function_is_refused_and_leaf_delete_works(store):
    from workflow_engine import execute_workflow_action
    for code in (GRADE, SHEET):
        save(code)
    r = execute_workflow_action("delete", {"workflow_id": "등급"}, PROJECT)
    assert r["success"] is False and "성적표" in r["error"] and (store / "등급.yaml").exists()
    assert execute_workflow_action("delete", {"workflow_id": "성적표"}, PROJECT)["success"]
    assert execute_workflow_action("delete", {"workflow_id": "등급"}, PROJECT)["success"]


def test_saving_another_name_over_an_id_checks_the_vanishing_name(store):
    save(GRADE)
    save(SHEET)
    r = save('[def:등급X]($s){ return "A" }', workflow_id="등급")
    assert r["success"] is False and "사라지면" in r["error"] and "성적표" in r["error"]


# B71-3 — 거절 봉투는 스스로 설명하고, 안쪽 진단이 경계를 넘는다
def test_rejection_messages_carry_the_first_issue():
    from ibl_v2_analysis import rejection_message
    issues = [{"code": "MISSING_ARGUMENT", "message": "필수 인자 누락: 금액"}, {"code": "TYPE", "message": "x"}]
    assert rejection_message("실행 전 검사에서 거절했습니다", issues) == \
        "실행 전 검사에서 거절했습니다: 필수 인자 누락: 금액 (MISSING_ARGUMENT) 외 1건"
    assert rejection_message("저장 전 검사 거절", []) == "저장 전 검사 거절"


def test_stored_run_and_save_failures_name_their_cause(store):
    save('[def:세금]($금액,$세율=0.1){ return $금액 * $세율 }')
    r = ibl_v2_store.action("run", {"workflow_id": "세금", "params": {"세율": 0.2}}, PROJECT)
    assert "필수 인자 누락: 금액" in r["error"]
    r = save('[def:합계]($목록){ $v = $목록 >> [table:each]{ [fn:행금액]{r:$it} }; return sum($v) }')
    assert "행금액" in r["error"] and r["error"].startswith("저장 전 검사 거절:")


def test_save_syntax_error_keeps_code_and_position_in_the_saved_source(store):
    r = save('[def:q]($s){ [if:$s>=90]{ return "A" } else { return "B" } }')
    assert r["diagnostic"]["code"] == "SYNTAX"
    assert r["diagnostic"]["source_span"]["column"] > 1


def test_inner_diagnostics_cross_the_tool_boundary_bounded():
    from ibl_v2_adapters import decode_envelope, inner_diagnostics
    from ibl_v2_ir import Fault
    raw = {"edition": 2, "success": False, "error": "실행 전 검사에서 거절했습니다: …",
           "issues": [{"code": "MISSING_ARGUMENT", "message": "m" * 900, "hint": "h",
                       "location": {"line": 3, "column": 7, "source": "세금"}}] * 8}
    rows = inner_diagnostics(raw)
    assert len(rows) == 5 and len(rows[0]["message"]) == 500
    assert rows[0]["line"] == 3 and rows[0]["source"] == "세금"
    with pytest.raises(Fault) as exc:
        decode_envelope(raw, {})
    assert exc.value.details["inner_diagnostics"][0]["code"] == "MISSING_ARGUMENT"
    # 판본 2 봉투가 아니면 옛 허용 목록 그대로
    assert inner_diagnostics({"success": False, "error": "x", "issues": [{"code": "A"}]}) == []


# F71-1·F71-2·F71-3
def test_resave_without_description_keeps_it(store):
    save('[def:메모]($x){ return $x }', description="부동산 메모 정리")
    save('[def:메모]($x){ return strip($x) }')
    assert workflow_store.get_workflow("메모")["description"] == "부동산 메모 정리"
    save('[def:메모]($x){ return $x }', description="")
    assert workflow_store.get_workflow("메모")["description"] == ""


def test_saving_a_decomposed_program_explains_how(store):
    r = save('[def:행]($r){ return $r.a }\n[def:합]($l){ return sum($l >> [table:each]{ [fn:행]{r:$it} }) }')
    assert r["success"] is False and "보조 함수(행)부터 먼저" in r["error"] and "받은 정의 2개" in r["error"]


@pytest.mark.parametrize("word,fix", [("else", "[else] {"), ("catch", "[catch] {"), ("elif", "[else] { [if:")])
def test_bare_branch_words_are_told_the_bracket_form(word, fix):
    from ibl_v2_ir import Fault
    from ibl_v2_parser import parse
    with pytest.raises(Fault) as exc:
        parse('[if:1>0]{ return 1 } ' + word + ' { return 2 }')
    assert exc.value.code == "SYNTAX" and fix in str(exc.value)


def test_unknown_op_warning_does_not_predict_rejection():
    from ibl_param_vocab import unknown_op_message
    msg = unknown_op_message({"ops": {"values": {"detail": "", "list": ""}}}, {"op": "get"})
    assert "선언된 op 가 아닙니다" in msg and "거절됩니다" not in msg


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
