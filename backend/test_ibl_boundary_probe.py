"""독립 기대값이 있는 조합 문장 회귀. 네트워크·모델 없이 실제 파서/엔진/도구 실행."""
import sys
from pathlib import Path

import pytest
import boot_paths  # noqa: F401

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ibl_boundary_cases import cases, additional_cases
from ibl_boundary_cases_round2 import cases as round2_cases
from ibl_boundary_cases_round2 import additional_cases as round2_additional
from ibl_boundary_cases_round3 import cases as round3_cases
from ibl_boundary_cases_round4 import cases as round4_cases
from ibl_boundary_cases_round5 import cases as round5_cases
from ibl_boundary_probe import probe


@pytest.mark.parametrize('case', cases() + additional_cases() + round2_cases() + round2_additional() + round3_cases() + round4_cases() + round5_cases(), ids=lambda c: c['id'])
def test_boundary_sentences(case):
    result = probe(case)
    assert result['syntax_ok'], result.get('error_text')
    assert result['ok'], f"{case['id']}: actual={result.get('actual')!r}; error={result.get('error_text')}"


def test_counter_scope_does_not_escape_repeat():
    from ibl_exec_each import _each_foreign_vars
    text = '[repeat:2]{[table:take]{items:[{n:$i}],n:1}}; [table:take]{items:[{n:$i}],n:1}'
    assert _each_foreign_vars(text, 'it') == ['i']


def test_error_scope_does_not_escape_catch():
    from ibl_exec_each import _each_foreign_vars
    text = '[try]{[self:read]{path:"x"}} [catch]{[self:read]{path:"$error.summary"}}; [self:read]{path:"$error.summary"}'
    assert _each_foreign_vars(text, 'it') == ['error']


def test_recursive_parser_and_executor_share_definition_table():
    # ibl.ibl_parser와 ibl_parser를 동시에 import하면 재귀 파서의 정의 표만
    # 다른 모듈에 생긴다. 전체 수집 순서에서만 중첩 fn이 사라지던 회귀.
    import ibl_parser
    import ibl_parser_blocks
    assert ibl_parser_blocks._PARSE_VARS is ibl_parser.parse_with_vars


@pytest.mark.parametrize('bad', ['[table:take]{items:[{n:$i} {n:2}]}', '[table:take]{items:[{n:$i},,3]}'])
def test_dynamic_arrays_reject_bad_separators(bad):
    from ibl_parser import parse, IBLSyntaxError
    with pytest.raises(IBLSyntaxError):
        parse(bad)


@pytest.mark.parametrize('code,expected', [
    ('[repeat:2,as:"x"]{[table:take]{items:[{v:$x}],n:1}}\n$return=$x', ['x']),
    ('[repeat:while $x < 2,max:3,as:"x"]{[table:take]{items:[{v:$x}],n:1}}', []),
    ('[table:each]{items:[{}],do:["[repeat:2]{[table:take]{items:[{v:$i}],n:1}}"]}', []),
])
def test_repeat_signature_is_local(code, expected):
    from workflow_contract import call_signature
    assert call_signature(code) == expected


@pytest.mark.parametrize('mode', ['while $x < 2', 'until $x == 1'])
@pytest.mark.parametrize('wrapper', ['fn', 'each'])
def test_repeat_condition_uses_current_counter(mode, wrapper):
    from ibl_boundary_cases_round3 import each, take
    body = '[repeat:' + mode + ',max:3,as:"x"]{' + take('$x') + '}'
    code = ('[def:f]{$return=' + body + '}\n[fn:f]{x:9}' if wrapper == 'fn'
            else each([9], body, **{'as': 'x'}))
    row = probe(dict(id='counter_condition', code=code, expected=[{'v': '1'}], error=False, contains=None))
    assert row['ok'], row


@pytest.mark.parametrize('comment', ['# } $it.no\n', '# " $it.no\n'])
def test_repeat_ignores_comment_delimiters(comment):
    from ibl_boundary_cases_round3 import each, take
    code = each([{'v': 9}], '[repeat:2,as:"it"]{' + comment + take('$it') + '}')
    row = probe(dict(id='comment_delimiter', code=code, expected=[{'v': '1'}], error=False, contains=None))
    assert row['ok'], row


def test_unicode_data_and_real_missing_reference_stay_distinct():
    from ibl_exec_each import _each_foreign_vars
    assert _each_foreign_vars(r'[table:take]{items:[{v:"\u0024child.id"}],n:1}', 'it') == []
    assert _each_foreign_vars(r'[table:take]{items:[{v:"\u0024child.id",bad:"$child.id"}],n:1}', 'it') == ['child']


def test_catch_binding_failure_keeps_original_error_and_runs_finally():
    from test_ibl_program_grade_m3m5 import _run, _final
    calls = []
    out = _run('[try]{[sense:bad]{why:"original"}}'
               '[catch]{[self:ok]{v:"$error.absent"}}[finally]{[self:cleanup]{}}', calls)
    assert out['success'] is False
    assert [c['action'] for c in calls] == ['bad', 'cleanup']
    final = _final(out)
    assert final['try_error']['summary'] == '고장: original'
    assert '$error.absent' in final['catch_error']['error']
    assert final['catch_error']['traceback']['error_type'] == 'binding'


def test_finally_binding_failure_keeps_scalar_result(monkeypatch):
    import ibl_control_blocks as cb
    monkeypatch.setattr(cb, '_run_body', lambda *a, **kw: ('unchanged', False, {}, {}))
    out = cb._execute_try({'body': {}, 'finally': {'params': {'v': '$error.absent'}}}, '.', 'test')
    assert out['result'] == 'unchanged'
    assert '$error.absent' in out['finally_error']['error']


def test_repeat_binding_failure_reports_iteration():
    from test_ibl_program_grade_m3m5 import _run, _final
    calls = []
    out = _run('[repeat:2]{[self:ok]{v:"$i.absent"}}', calls)
    assert out['success'] is False and calls == []
    error = _final(out)['repeat_error']
    assert error['iteration'] == 1
    assert '$i.absent' in error['error']
    assert error['traceback']['error_type'] == 'binding'


@pytest.mark.parametrize('code,expected', [
    ('[self:write]{content:"# 제목\n  들여쓰기\n\n끝"} # } [self:read]{}', '# 제목\n  들여쓰기\n\n끝'),
    ('[self:write]{content:"https://example.test/a#part"} # "', 'https://example.test/a#part'),
    ('[self:write]{content:"첫줄\n# 제목\n끝"}', '첫줄\n# 제목\n끝'),
])
def test_comment_preprocessing_preserves_string_content(code, expected):
    from ibl_parser import parse
    steps = parse(code)
    assert len(steps) == 1
    assert steps[0]['params']['content'] == expected


@pytest.mark.parametrize('header,iterations,halted', [
    ('0', 0, None), ('0,max:6', 0, None), ('3,max:0', 0, 'max'),
    ('2,max:6', 2, None), ('3,max:1', 1, 'max'),
    ('while true,max:0', 0, 'max'), ('until false,max:0', 0, 'max'),
    ('while false,max:3', 0, None),
])
@pytest.mark.parametrize('collect', ['false', 'true'])
def test_repeat_budget_controls_calls_and_reports_incomplete(header, iterations, halted, collect):
    from test_ibl_program_grade_m3m5 import _run, _final
    calls = []
    out = _run('[repeat:' + header + ',collect:' + collect + ']{[self:work]{}}', calls)
    final = _final(out)
    assert out['success'] and len(calls) == iterations
    assert final['iterations'] == iterations and final.get('halted') == halted
    if not iterations:
        assert final['items'] == [] and final['count'] == 0
    if halted:
        assert 'max=' in final['note']


def test_zero_repeat_preserves_state_and_still_runs_outer_finally():
    from idiom_experiment_worker import run_trial
    from ibl_boundary_cases import payload
    trial = run_trial('$n=7\n[try]{[repeat:0]{$n=$n+1\n[self:read]{path:"absent"}}}'
                      '[finally]{[self:read]{path:"note.txt"}}\n$return=$n', 'dedup')
    assert trial['result']['success'] and trial['observed']['leaf_calls'] == ['self:read']
    assert payload(trial['result']) == 7


@pytest.mark.parametrize('params,span,message', [
    ('tail:1', (2, 2), '초안\n'), ('tail:3', (1, 2), '제목\n초안\n'),
    ('limit:0', (None, None), ''), ('offset:8,limit:2', (None, None), ''),
])
def test_blocks_read_range_metadata_matches_contents(params, span, message):
    from idiom_experiment_worker import run_trial
    from idiom_value_cases import final_value
    result = run_trial('[self:read]{path:"note.txt",blocks:true,' + params + '}', 'dedup')['result']
    final = final_value(result)
    assert result['success'] and final['message'] == message
    assert (final['start_line'], final['end_line']) == span
    assert final['total_lines'] == 2


@pytest.mark.parametrize('separator', ['\u2028', '\u2029', '\x85', '\v', '\f'])
def test_blocks_and_plain_read_share_physical_line_numbers(separator):
    from ibl_boundary_cases import literal as q
    from idiom_experiment_worker import run_trial
    from idiom_value_cases import final_value
    code = '[self:write]{path:"outputs/lines.txt",content:' + q('a' + separator + 'b\nc\n') + '}'
    code += '\n[self:read]{path:"outputs/lines.txt",blocks:true,start_line:2,limit:1}'
    result = run_trial(code, 'dedup')['result']
    final = final_value(result)
    assert result['success'] and final['message'] == 'c\n'
    assert final['total_lines'] == 2


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
