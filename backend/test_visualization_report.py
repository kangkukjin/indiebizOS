"""Round 41's full program: real files/charts/statistics; only prose AI is a double."""
import boot_paths  # noqa: F401
from dataclasses import replace
import importlib.util
import json
import shutil
from pathlib import Path

import pytest
from ibl_run_journal import Journal, reusable_receipts
from ibl_v2_adapters import load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Budget, Runtime

ROOT = Path(__file__).resolve().parents[1]
ROUND = ROOT / 'docs/experiments/long_sentence_imagination/round_41'


def load_prepare():
    spec = importlib.util.spec_from_file_location('round41_prepare', ROUND / 'harness/prepare.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.system
def test_full_report_correction_and_new_survey_variant(tmp_path):
    prepare = load_prepare()
    prepare.OUT = tmp_path / 'fixture'
    prepare.generate()
    src = prepare.OUT / 'trainer/base'
    registry = load_registry(str(ROOT))
    registry['table:brief'] = replace(registry['table:brief'], run=lambda *_: {'message': '유의한 차이를 찾지 못한 가설은 차이 없음의 증거가 아니다.'})
    code = (ROUND / 'drafts/main_v3.ibl').read_text()
    journal_root = tmp_path / 'journal'
    results = []

    def run(out, prev=None, reuse=None):
        out.mkdir(exist_ok=True)
        inputs = {'src': str(src), 'out': str(out), 'prev': str(prev) if prev else None}
        plan = compile_program(code, registry, inputs)
        assert not plan.issues, plan.report()
        with Journal(journal_root, plan.fingerprint) as journal:
            result = Runtime(plan, inputs, budget=Budget(steps=1_000_000, rows=100_000), journal=journal,
                reusable=reusable_receipts(journal_root, reuse) if reuse else None, reuse_run=reuse).run()
        assert result['success'], result
        expected = prepare.analyze(src)
        quality = json.loads((out / 'quality.json').read_text())
        stats = json.loads((out / 'stats.json').read_text())
        assert quality['excluded_count'] == expected['quality']['excluded_count']
        assert quality['duplicate_count'] == expected['quality']['duplicate_count']
        assert quality['low_n_conditions'] == expected['quality']['low_n_conditions']
        for condition in stats['conditions']:
            exp = expected['conditions'][condition['group'] + '-' + condition['task']]
            for key in ('n', 'mean', 'sd', 'ci_low', 'ci_high'):
                assert condition[key] == exp[key], (key, condition, exp)
        assert stats['satisfaction'] == expected['satisfaction']
        for actual, exp in zip(stats['hypotheses'], expected['hypotheses']):
            for key in ('n_a', 'n_b', 't', 'df', 'cohen_d'):
                assert actual.get(key) == exp.get(key)
        manifest = json.loads((out / 'manifest.json').read_text())
        assert manifest['inputs_sha256'] == expected['input_sha256']
        for fig in manifest['figures']:
            assert Path(fig['file']).read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
        results.append({'value': result['value'], 'continuation': result['continuation'], 'reuse': result.get('reuse')})
        return result['resume']['run_id']

    out = tmp_path / 'base'
    first = run(out)
    assert results[-1]['continuation']['read_calls'] == 64
    # The original seven-file correction, at the same resource paths.
    changed = []
    for path in (prepare.OUT / 'trainer/v1/trials').glob('*.json'):
        target = src / 'trials' / path.name
        if path.read_bytes() != target.read_bytes():
            shutil.copyfile(path, target)
            changed.append(path.name)
    assert len(changed) == 7
    correction = tmp_path / 'correction'
    second = run(correction, out, first)
    assert results[-1]['reuse']['reused_calls'] >= 57
    assert results[-1]['value']['fig1'] is True and results[-1]['value']['fig2'] is False
    stale = [x for x in results[-1]['reuse']['skipped'] if x['reason'] == 'resource_changed']
    assert len(stale) == 7
    # New boundary: only survey changes, so duration remains reusable/unchanged.
    path = src / 'survey.csv'
    lines = path.read_text().splitlines()
    cells = lines[1].split(',')
    cells[1] = '1' if cells[1] != '1' else '5'
    lines[1] = ','.join(cells)
    path.write_text('\n'.join(lines) + '\n')
    run(tmp_path / 'survey-change', correction, second)
    assert results[-1]['reuse']['reused_calls'] >= 63
    assert results[-1]['value']['fig1'] is False and results[-1]['value']['fig2'] is True
    print('ROUND41_REPAIR=' + json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
