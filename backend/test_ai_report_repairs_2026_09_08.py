"""AI 동향보고서 현장 신호: 원장 오염, 괄호 변수 분기, 산문 수집 회귀."""
import importlib.util
import json
from pathlib import Path

import pytest
import boot_paths  # noqa: F401
from ibl_parser import parse, parse_with_vars, format_step, IBLSyntaxError
from ibl_typecheck import typecheck_code

ROOT = Path(__file__).resolve().parents[1]
PROGRAM = '''
$기술 = [table:compute]{items:[{id:1},{id:2},{id:3}],set:{x:1}};
$사례 = [table:compute]{items:[{id:4}],set:{x:2}};
($기술 >> [table:take]{n:-2}) & $사례 >> [table:union]
'''


def test_parenthesized_variable_pipeline_runs_and_keeps_source():
    from workflow_engine import execute_pipeline
    steps = parse(PROGRAM)
    assert steps[-2]['_vars'] == {'기술': 0, '사례': 1}
    before = json.dumps(steps)
    result = execute_pipeline(steps, str(ROOT))
    assert result['success'], result
    final = result['final_result']
    final = json.loads(final) if isinstance(final, str) else final
    assert [r['id'] for r in final['items']] == [2, 3, 4]
    assert json.dumps(steps) == before
    assert typecheck_code(PROGRAM)['ok']


@pytest.mark.parametrize('ref', ['$기술', '${기술}', '${기술.items}'])
def test_parenthesized_reference_forms(ref):
    code = PROGRAM.replace('($기술 >>', '(' + ref + ' >>')
    assert parse(code)[-2]['branches'][0]['_branch_steps'][0]['_var_emit']
    # pretty-printer가 뜻 있는 괄호·참조를 보존한다.
    formatted = format_step(parse(code)[-2])
    assert parse_with_vars(formatted, preset_vars={'기술': 100, '사례': 101})[0]


def test_parenthesized_free_slot_in_function_and_missing_variable():
    assert parse('[def:끝둘]{($목록 >> [table:take]{n:-2}) & $다른 >> [table:union]}')
    with pytest.raises(IBLSyntaxError, match='할당되지'):
        parse('($미할당 >> [table:take]{n:1}) & [self:time]')
    # 폴백은 시도를 받는 자리 — 언어 개정 2026-09-09 로 괄호 가지의 **변수 머리 파이프**는 시도다(허용),
    # 변수 홀로는 종전대로 시도가 아니다(거절). 정본 test_language_limits_2026_09_09.
    assert parse('$x = [self:time]; [self:time] ?? ($x >> [table:take]{n:1})')
    with pytest.raises(IBLSyntaxError):
        parse('$x = [self:time]; [self:time] ?? ($x)')


@pytest.mark.parametrize('code', [
    '[self:ledger]{op:"append",path:"x.json",item:{date:"2026-09-07",tags:["a"],max_items:10}',
    '[self:ledger]{op:"append",path:"x.json",items:[{date:"2026-09-07"}]',
])
def test_unclosed_container_never_becomes_string(code):
    with pytest.raises(IBLSyntaxError, match='닫히지 않은'):
        parse(code)
    assert parse('[self:ledger]{op:"append",path:"x.json",item:{date:"2026-09-07",tags:["a"]},max_items:10}')


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('report_ledger_probe', ROOT / 'data/packages/installed/tools/system_essentials/ledger_ops.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, '_ROOT', tmp_path)
    return module


@pytest.mark.parametrize('bad', ['{date:"2026-09-07",tags:["a"]}', 1, False, ['a']])
def test_ledger_rejects_nonobject_input_atomically(ledger, tmp_path, bad):
    path = tmp_path / 'ledger.json'
    path.write_text('[{"date":"2026-09-08","tags":["정상"]}]')
    before = path.read_bytes()
    result = ledger.op_append({'path': str(path), 'items': [{'date': 'new'}, bad]})
    assert not result['success'] and '객체' in result['error']
    assert path.read_bytes() == before
    path2 = tmp_path / 'new.json'
    assert not ledger.op_append({'path': str(path2), 'item': bad})['success']
    assert not path2.exists()


def test_ledger_reports_corrupt_rows_even_when_filter_would_hide_them(ledger, tmp_path):
    path = tmp_path / 'ledger.json'
    path.write_text('[{"date":"2026-09-08"},"broken"]')
    before = path.read_bytes()
    for call in (ledger.op_select, ledger.op_append):
        out = call({'path': str(path), 'where': {'date': '2026-09-08'}, 'item': {'date': 'new'}})
        assert not out['success'] and '첫 위치 2' in out['error']
        assert path.read_bytes() == before


@pytest.mark.parametrize('parallel', [1, 2])
def test_collect_preserves_four_summaries_and_warns_before_work(monkeypatch, parallel):
    import ibl_engine
    from ibl_exec_each import _execute_table_each
    def fake(ti, *args, **kwargs):
        if ti.get('action') == 'crawl':
            return {'success': True, 'items': [{'text': '원문'}]}
        return '보존할 요약'
    monkeypatch.setattr(ibl_engine, 'execute_ibl', fake)
    params = {'items': [{'url': f'https://example.com/{i}'} for i in range(4)],
              'do': '[sense:crawl]{url:"$it.url"} >> [table:brief]{instruction:"요약"}',
              'parallel': parallel}
    code = '[table:each]' + json.dumps(params, ensure_ascii=False)
    check = typecheck_code(code)
    assert check['ok'] and any('collect:true' in i.get('hint', '') for i in check['issues'])
    old = _execute_table_each(params, str(ROOT))
    assert old['passthrough_rows'] == 4 and 'collect:true' in old['message']
    params['collect'] = True
    out = _execute_table_each(params, str(ROOT))
    assert out['success'] and out['collected_rows'] == 4
    assert [r['value'] for r in out['items']] == ['보존할 요약'] * 4
    assert 'passthrough_rows' not in out
    check = typecheck_code('[table:each]' + json.dumps(params, ensure_ascii=False))
    assert not any('collect:true' in i.get('hint', '') for i in check['issues'])


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
