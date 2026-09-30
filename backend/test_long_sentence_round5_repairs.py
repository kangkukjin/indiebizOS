"""PDF honesty, model reuse/accounting, and ambiguous line diagnostics."""
import boot_paths  # noqa: F401
import importlib.util
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from ibl_v2_adapters import load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime
from ibl_v2_ir import Fault
from ibl_run_journal import Journal, reusable_receipts

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'docs/experiments/long_sentence_imagination/round_5'


def run(code, registry, inputs=None, **kwargs):
    plan = compile_program(code, registry, inputs)
    assert not plan.issues, plan.issues
    return Runtime(plan, inputs, **kwargs).run()


@pytest.fixture(scope='module')
def registry():
    return load_registry(str(ROOT))


@pytest.mark.parametrize('name', ['number', 'text', 'list'])
def test_leading_plus_is_not_silently_discarded(registry, name):
    with pytest.raises(Fault) as raised:
        compile_program((FIXTURE / f'repro/leading_plus_{name}.ibl').read_text(), registry)
    assert raised.value.code == 'SYNTAX'
    assert '앞줄 끝' in str(raised.value)


@pytest.mark.parametrize('operator', ['+', '-', '*', '/', '//', '%', '**'])
def test_arithmetic_line_diagnostic_and_fix(operator):
    with pytest.raises(Fault):
        compile_program(f'$x=4\n {operator} 2\nreturn $x', {})
    assert run(f'$x=4 {operator}\n 2\nreturn $x', {})['success']
    assert run('$x=1\nreturn -2', {})['value'] == -2
    assert run('$x=1; -2', {})['value'] == -2
    assert run('return [1,\n-2]', {})['value'] == [1, -2]


def test_format_type_explains_nullable_value(registry):
    plan = compile_program((FIXTURE / 'repro/format_type_detail.ibl').read_text(), registry,
                           {'r': [{'이유': None}, {'이유': 'x'}]})
    issue = next(i for i in plan.issues if i['code'] == 'FORMAT_TYPE')
    assert 'Null' in issue['actual'] and 'Text' in issue['actual']
    assert all(t in issue['expected'] for t in ['Text', 'Number', 'Bool'])


@pytest.mark.parametrize('name', ['R11', 'R12'])
def test_pdf_failure_is_preserved_after_catch(registry, name):
    result = run('[try]{return [self:read]{path:$p}}[catch]{return $error}', registry,
                 {'p': str(FIXTURE / f'input/receipts/{name}.pdf')})
    assert result['success'] and not result['source_complete']
    error = result['value']
    if name == 'R11':
        assert error['code'] == 'PARTIAL_SOURCE'
        partial = error['partial']
        assert partial['text'] == '' and partial['blocks'] == []
        assert partial['data']['no_text_pages'] == [1]
        assert partial['data']['page_text_chars'] == [{'page': 1, 'chars': 0}]
    else:
        assert error['code'] == 'TOOL' and error['details']['error_type'] == 'corrupt'


def test_pdf_mixed_pages_and_requested_selection(registry, tmp_path):
    import fitz
    path = tmp_path / 'mixed.pdf'
    with fitz.open() as doc:
        doc.new_page().insert_text((20, 30), 'visible text')
        doc.new_page()
        doc.save(path)
    result = run('[try]{return [self:read]{path:$p}}[catch]{return $error.partial}',
                 registry, {'p': str(path)})
    assert result['success'] and not result['source_complete']
    assert result['value']['data']['no_text_pages'] == [2]
    assert result['value']['blocks'][0]['page'] == 1
    assert '--- Page' not in result['value']['text']
    selected = run('return [self:read]{path:$p,pages:"1"}', registry, {'p': str(path)})
    assert selected['success'] and selected['source_complete']


@pytest.fixture
def judge_transport(monkeypatch):
    import requests
    import common.auth_manager
    calls = []
    monkeypatch.setattr(common.auth_manager, 'get_api_key', lambda _: 'fixture-only')

    def post(*args, **kwargs):
        payload = kwargs['json']
        calls.append(payload)
        answers = {key: {'type': 'noul', 'noul': 0.95} for key in payload['questions']}
        return SimpleNamespace(status_code=200, json=lambda: {
            'answers': answers, 'model': 'jev-latest',
            'usage': {'input_tokens': 20, 'output_tokens': 10}})

    monkeypatch.setattr(requests, 'post', post)
    return calls


def test_judge_keeps_read_reuse_and_records_own_call(registry, tmp_path, judge_transport):
    inputs = {'p': str(FIXTURE / 'input/policy.json')}
    with Journal(tmp_path, 'original') as journal:
        first = run((FIXTURE / 'repro/judge_reuse_a.ibl').read_text(), registry, inputs, journal=journal)
        original = journal.run_id
    second = run((FIXTURE / 'repro/judge_reuse_b.ibl').read_text(), registry, inputs,
                 reusable=reusable_receipts(tmp_path, original), reuse_run=original)
    assert first['success'] and second['success']
    assert second['reuse']['reused_calls'] == 1
    assert len(judge_transport) == 2  # Model outputs are not reuse candidates.
    usage = second['usage']['model']
    assert usage['requests'] == 1 and usage['input'] == 20
    call = usage['calls'][0]
    assert call['model'] == 'jev-latest' and call['source'] == 'fixed_provider'
    assert call['tier'] is None and call['call_id'] and call['role']


@pytest.mark.parametrize('response_kind', ['network', 'bad_json', 'unmeasured'])
def test_judge_unmeasured_failures_have_model_identity(monkeypatch, response_kind):
    import requests
    from model_call_context import capture_usage
    path = ROOT / 'data/packages/installed/tools/ai-ops/ai_ops_judge.py'
    spec = importlib.util.spec_from_file_location('round5_judge', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, '_key', lambda: 'fixture-only')

    def post(*a, **kw):
        if response_kind == 'network':
            raise requests.Timeout('fixture')
        def body():
            if response_kind == 'bad_json':
                raise ValueError('fixture')
            return {'answers': {}}
        return SimpleNamespace(status_code=200, json=body)

    monkeypatch.setattr(requests, 'post', post)
    with capture_usage() as captured:
        module._request({})
    assert len(captured) == 1 and not captured[0]['measured']
    assert captured[0]['model'] == 'jev-latest'


@pytest.mark.parametrize('variant,unknown', [(False, False), (True, False), (False, True)])
def test_full_original_task_and_copy_variant(tmp_path, monkeypatch, judge_transport, variant, unknown):
    import oneshot_facade
    model_calls = []

    def model(prompt, system):
        rows = json.loads(prompt.split('[items]\n', 1)[1].split('\n\n[지시]', 1)[0])
        model_calls.append(rows)
        return ([{'_i': row['_i'], '가맹점': row['원문'].splitlines()[0],
                  '날짜': re.search(r'\d{4}-\d{2}-\d{2}', row['원문'])[0],
                  '합계': re.search(r'합계 금액 ([\d,]+)', row['원문'])[1]}
                 for row in rows], None)

    monkeypatch.setattr(oneshot_facade, 'oneshot_json', model)
    reg = load_registry(str(tmp_path))
    folder = FIXTURE / ('input_variant' if variant else 'input')
    p1 = run((FIXTURE / 'drafts/p1_repaired.ibl').read_text(), reg,
             {'폴더': str(folder / 'receipts')})
    assert p1['success'] and not p1['source_complete'], p1
    states = {row['id']: row['상태'] for row in p1['value']['영수증']}
    assert states['R11'] == '글자 없음' and states['R12'] == '읽기 실패'
    assert len(model_calls) == 1 and len(model_calls[0]) == (12 if variant else 10)
    inputs = {'추출': p1['value'], '카드': str(folder / 'card_statement.csv'),
              '정책': str(folder / 'policy.json'), '보고서': str(tmp_path / 'report.md'),
              '목록': str(tmp_path / 'anomalies.json')}
    if unknown:
        import requests
        normal_post = requests.post
        def uncertain_post(*args, **kwargs):
            response = normal_post(*args, **kwargs)
            body = response.json()
            for i, row in enumerate(kwargs['json']['state']['items']):
                if row['영수증'] in ('R01', 'R03'):
                    body['answers'][f'r{i}q0']['noul'] = 0.71
            return SimpleNamespace(status_code=200, json=lambda: body)
        monkeypatch.setattr(requests, 'post', uncertain_post)
    # Original successful P2, then corrected pending-judgment variant.
    for draft in (['p2_repaired'] if unknown else ['p2_v2', 'p2_repaired']):
        p2 = run((FIXTURE / f'drafts/{draft}.ibl').read_text(), reg, inputs)
        assert p2['success'], p2
        assert p2['value']['보고일치'] and p2['value']['목록일치']
        assert p2['value']['카드합'] == (515000 if variant else 506000)
        assert p2['value']['영합'] == (444400 if variant else 435400)
        rows = json.loads(Path(inputs['목록']).read_text())['이상']
        assert any(r['종류'] == '중복 청구 의심' and r['승인번호'] == 'A1009' for r in rows)
        if unknown:
            pending = [r for r in rows if r['종류'] == '가맹점 확인 필요']
            assert {r['영수증'] for r in pending} == {'R01', 'R03'}
            assert all('미결정' in r['설명'] for r in pending)
            assert not any(r['종류'] in ('금액 불일치', '카드 내역 없음')
                           and r['영수증'] == 'R03' for r in rows)
            assert not any(r['종류'] == '영수증 없음' and r['승인번호'] == 'A1002' for r in rows)
            normal = Path(inputs['보고서']).read_text().split('## 정상 짝')[1]
            assert 'R01' not in normal
        else:
            assert any(r['종류'] == '금액 불일치' and r['영수증'] == 'R03' for r in rows)
    assert len(model_calls) == 1


def test_brief_keeps_read_reuse_but_runs_model_again(tmp_path, monkeypatch):
    import oneshot_facade
    calls = []
    monkeypatch.setattr(oneshot_facade, 'execution_oneshot',
                        lambda *a, **kw: calls.append(1) or 'summary')
    registry = load_registry(str(tmp_path))
    code = ('$d=[self:read]{path:$p};'
            '$s=[{a:1}] >> [table:brief]{instruction:"요약"};return len($d.text)')
    inputs = {'p': str(FIXTURE / 'input/policy.json')}
    with Journal(tmp_path / 'runs', 'brief') as journal:
        first = run(code, registry, inputs, journal=journal)
        original = journal.run_id
    second = run(code + '+1', registry, inputs,
                 reusable=reusable_receipts(tmp_path / 'runs', original), reuse_run=original)
    assert first['success'] and second['success']
    assert second['reuse']['reused_calls'] == 1 and calls == [1, 1]
    assert second['value'] == first['value'] + 1


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
