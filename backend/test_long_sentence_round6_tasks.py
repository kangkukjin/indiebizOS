"""Full ledger pipelines with real local tools and deterministic model transports."""
import boot_paths  # noqa: F401
import ast
import csv
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from ibl_v2_adapters import load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Budget, Runtime
from ibl_run_journal import Journal, reusable_receipts
from ibl_v2_ir import unpack

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'docs/experiments/long_sentence_imagination/round_6'


def execute(name, registry, inputs, **kwargs):
    source = (FIXTURE / f'drafts/{name}.ibl').read_text()
    plan = compile_program(source, registry, inputs)
    assert not plan.issues, plan.issues
    result = Runtime(plan, inputs, budget=Budget(steps=1000000, rows=100000), **kwargs).run()
    assert result['success'], {k: v for k, v in result.items() if k in ('error', 'diagnostic', 'usage')}
    return result


@pytest.fixture
def model_transports(monkeypatch):
    import oneshot_facade
    import requests
    import common.auth_manager
    tree = ast.parse((FIXTURE / 'input/gen.py').read_text())
    categories = dict(next(ast.literal_eval(node.value) for node in tree.body
                           if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'UNCAT' for t in node.targets)))
    calls = {'ai': [], 'judge': []}

    def model(prompt, system):
        rows = json.loads(prompt.split('[items]\n', 1)[1].split('\n\n[지시]', 1)[0])
        calls['ai'].append(rows)
        return ([{'_i': row['_i'], '분류': categories[row['설명']]} for row in rows], None)

    def post(*args, **kwargs):
        payload = kwargs['json']
        calls['judge'].append(payload)
        answers = {}
        for i, row in enumerate(payload['state']['items']):
            pair = {row['서비스1'], row['서비스2']}
            probability = 0.95 if pair in ({'멜론', '스포티파이'}, {'넷플릭스', '왓챠'}) else 0.5 if 'APPLE.COM/BILL' in pair else 0.05
            answers[f'r{i}q0'] = {'type': 'noul', 'noul': probability}
        return SimpleNamespace(status_code=200, json=lambda: {'answers': answers, 'model': 'jev-latest',
                                                               'usage': {'input_tokens': 10, 'output_tokens': 10}})

    monkeypatch.setattr(oneshot_facade, 'oneshot_json', model)
    monkeypatch.setattr(common.auth_manager, 'get_api_key', lambda _: 'fixture-only')
    monkeypatch.setattr(requests, 'post', post)
    return calls


@pytest.mark.system  # 2026-10-04: 전체 재생·전수 스캔은 system 묶음(docs/REGRESSION_TESTING.md 표)
@pytest.mark.parametrize('variant', ['original', 'missing', 'triple'])
def test_full_ledger_and_render_change(tmp_path, model_transports, variant):
    folder = tmp_path / 'input'
    shutil.copytree(FIXTURE / ('input_variant' if variant == 'missing' else 'input'), folder)
    if variant == 'triple':
        for path in (folder / 'ledger').glob('*.csv'):
            with path.open(newline='') as stream:
                reader = csv.DictReader(stream)
                fields, rows = reader.fieldnames, list(reader)
            with path.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows * 3)
    raw = []
    for path in (folder / 'ledger').glob('*.csv'):
        with path.open(newline='') as stream:
            raw.extend(csv.DictReader(stream))
    valid = [int(r['금액']) for r in raw if re.fullmatch(r'-?\d+', r['금액'])]
    registry = load_registry(str(tmp_path))
    p1 = execute('p1_v2', registry, {'폴더': str(folder / 'ledger'), '규칙': str(folder / 'rules.json')})
    data = unpack(p1['value_wire']['data'])
    assert data['행수'] == len(raw)
    assert len(data['금액오류행']) == (1 if variant == 'missing' else 0)
    if variant == 'triple':
        assert data['행수'] == 8094 and p1['usage']['steps'] > 100000
    inputs = {'자료': data, '고정': str(folder / 'fixed.json'), '기대월': [f'{m:02d}' for m in range(1, 13)]}
    with Journal(tmp_path / 'journal', 'p2') as journal:
        p2 = execute('p2_v4', registry, inputs, journal=journal)
        rid = journal.run_id
    analysis = unpack(p2['value_wire']['data'])
    assert analysis['총지출'] == sum(x for x in valid if x >= 0)
    assert analysis['환불합'] == sum(x for x in valid if x < 0)
    assert len([r for r in analysis['이상'] if r['종류'] == '구독 겹침']) == 2
    assert any(r['종류'] == '구독 겹침 확인 필요' for r in analysis['이상'])
    if variant == 'missing':
        assert any(r['종류'] == '월 파일 없음' and r['월'] == '07' for r in analysis['이상'])
    judge_count = len(model_transports['judge'])
    reused = execute('p2_v4', registry, inputs, reusable=reusable_receipts(tmp_path / 'journal', rid), reuse_run=rid)
    assert reused['reuse']['model_calls'] == 1 and len(model_transports['judge']) == judge_count
    outputs = {'분석': analysis, '파일상태': data['파일상태'], 'AI분류': data['AI분류'],
               '행수': data['행수'], '가게수': data['가게수'], '보고서': str(tmp_path / 'report.md'),
               '목록': str(tmp_path / 'anomalies.json'), 'CSV': str(tmp_path / 'anomalies.csv')}
    p3 = execute('p3_repaired', registry, outputs)
    assert p3['value']['보고일치'] and p3['value']['목록일치'] and p3['value']['CSV일치']
    assert str(analysis['총지출']) in Path(outputs['보고서']).read_text()
    with Path(outputs['CSV']).open(newline='') as stream:
        exported = list(csv.DictReader(stream))
    assert exported == [{'종류': row['종류'], '설명': row['설명문']} for row in analysis['이상']]
    assert len(model_transports['ai']) == 1


@pytest.mark.system  # 2026-10-04: 전체 재생·전수 스캔은 system 묶음(docs/REGRESSION_TESTING.md 표)
def test_real_read_reuse_survives_process_restart(tmp_path):
    source = tmp_path / 'source.txt'
    source.write_text('restart preserved')
    script = '''import sys,json
sys.path.insert(0, 'backend')
import boot_paths
from ibl_v2_entry import handle_request
request=json.loads(sys.argv[1])
result=handle_request(request,sys.argv[2])
print(json.dumps({k:result[k] for k in ('success','value','reuse','resume') if k in result}))
'''
    request = {'code': '#!ibl edition=2\nreturn [self:read]{path:$p}.text', 'inputs': {'p': str(source)}}
    def child(payload):
        result = subprocess.run([sys.executable, '-c', script, json.dumps(payload), str(tmp_path)],
                                cwd=ROOT, text=True, capture_output=True, check=True, timeout=45)
        return json.loads(result.stdout.splitlines()[-1])
    first = child(request)
    second = child({**request, 'reuse': first['resume']})
    assert second['success'] and second['value'] == 'restart preserved'
    assert second['reuse']['reused_calls'] == 1


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
