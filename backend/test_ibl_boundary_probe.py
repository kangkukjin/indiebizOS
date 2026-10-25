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
from ibl_boundary_cases_round6 import cases as round6_cases
from ibl_boundary_probe import probe


@pytest.mark.parametrize('case', cases() + additional_cases() + round2_cases() + round2_additional() + round3_cases() + round4_cases() + round5_cases() + round6_cases(), ids=lambda c: c['id'])
def test_historical_boundary_sentences_are_refused_without_effects(case, monkeypatch):
    from ibl_v2_entry import handle_request
    import ibl_v2_adapters
    monkeypatch.setattr(ibl_v2_adapters, 'load_registry', lambda *a, **k: pytest.fail('구판 도구 로드'))
    result = handle_request({'edition':1,'code':case['code']})
    assert not result['executed'] and not result['success']
    assert 'EDITION_RETIRED' in str(result)



def test_counter_scope_does_not_escape_repeat():
    from test_ibl_v2_core import run
    out = run('[repeat:2]{return $i}; return $i')
    assert not out['success'] and not out['executed']


def test_error_scope_does_not_escape_catch():
    from test_ibl_v2_core import run
    out = run('[try]{1/0}[catch]{return $error}; return $error')
    assert not out['success'] and not out['executed']


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


@pytest.mark.parametrize('mode', ['while $x < 2', 'until $x == 2'])
@pytest.mark.parametrize('wrapper', ['fn', 'each'])
def test_repeat_condition_uses_current_counter(mode, wrapper):
    from test_ibl_v2_core import value
    body = '$x=0;[repeat:' + mode + ']{$x=$x+1};return $x'
    code = ('[def:f](){'+body+'};[fn:f]{}' if wrapper=='fn' else
            '([0] >> [table:each]{'+body+'})[0]')
    assert value(code) == 2


@pytest.mark.parametrize('comment', ['# } $it.no\n', '# " $it.no\n'])
def test_repeat_ignores_comment_delimiters(comment):
    from test_ibl_v2_core import value
    assert value('$x=0;[repeat:2]{'+comment+'$x=$x+1};return $x') == 2


def test_unicode_data_and_real_missing_reference_stay_distinct():
    from test_ibl_v2_core import value, run
    assert value(r'return "\u0024child.id"') == '$child.id'
    assert not run(r'return {v:"\u0024child.id",bad:$child.id}')['success']


def test_catch_binding_failure_still_runs_finally():
    from test_ibl_v2_core import run, adapter
    calls = []
    registry = {'test:cleanup':adapter(lambda *a: calls.append('cleanup'), effects=['write'])}
    out = run('[try]{1/0}[catch]{1/0}[finally]{[test:cleanup]{}}', registry=registry)
    assert not out['success'] and calls == ['cleanup']


def test_finally_failure_does_not_claim_success():
    from test_ibl_v2_core import run
    out = run('[try]{return "unchanged"}[finally]{1/0}')
    assert not out['success']


def test_repeat_invalid_binding_is_checked_before_effects():
    from test_ibl_v2_core import run
    out = run('[repeat:2]{return $i.absent}')
    assert not out['success']


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


@pytest.mark.parametrize('count', [0,1,2,10])
@pytest.mark.parametrize('budget', [1,3,100])
def test_repeat_budget_controls_calls(count, budget):
    from test_ibl_v2_core import run, adapter
    from ibl_v2_runtime import Budget
    calls = []
    registry = {'test:work':adapter(lambda *a: calls.append('work'), effects=['write'])}
    out = run('[repeat:'+str(count)+']{[test:work]{}}', registry=registry, budget=Budget(steps=budget))
    assert len(calls) <= count
    if not out['success']:
        assert out['diagnostic']['kind']=='budget'
    else:
        assert len(calls)==count


def test_zero_repeat_preserves_state_and_runs_finally():
    from test_ibl_v2_core import value
    assert value('$x=4;[try]{[repeat:0]{$x=9}}[finally]{$x=$x+1};return $x') == 5


@pytest.mark.parametrize('params,span,message', [
    ('tail:1', (2, 2), '초안\n'), ('tail:3', (1, 2), '제목\n초안\n'),
    ('limit:0', (None, None), ''), ('offset:8,limit:2', (None, None), ''),
])
def test_blocks_read_range_metadata_matches_contents(params, span, message, tmp_path):
    from ibl_v2_entry import handle_request
    (tmp_path/'note.txt').write_text('제목\n초안\n')
    source = '[self:read]{path:"note.txt",'+params+'}'
    result = handle_request({'edition':2,'code':source}, str(tmp_path))
    assert result['success'] and result['value']['text']==message, result
    if message:
        assert result['value']['blocks']


@pytest.mark.parametrize('separator', ['\u2028', '\u2029', '\x85', '\v', '\f'])
def test_blocks_and_plain_read_share_physical_line_numbers(separator, tmp_path):
    from ibl_v2_entry import handle_request
    (tmp_path/'lines.txt').write_text('a'+separator+'b\nc\n')
    out = handle_request({'edition':2,'code':'[self:read]{path:"lines.txt",start_line:2,limit:1}'},str(tmp_path))
    assert out['success'] and out['value']['text']=='c\n', out


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
