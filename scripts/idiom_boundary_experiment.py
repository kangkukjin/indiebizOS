#!/usr/bin/env python3
"""저장된 동일 결과의 모델 경계 반환량 비교 + 첫 생성 코드 재생. 모델 호출 없음."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import re
import subprocess
import types

import ibl_envelope
from common.value_semantics import dumps_public_result
from ibl_retyping import load_policy_block
from idiom_experiment import dump


def envelope(value):
    obj = value
    if isinstance(obj, str) and obj.lstrip().startswith('{'):
        try:
            obj = json.loads(obj)
        except ValueError:
            return None
    if (isinstance(obj, dict) and isinstance(obj.get('results'), list)
            and isinstance(obj.get('steps_total'), int)):
        return obj
    return None


def contract(value, root=False):
    """실행 기록만 제외한 값·오류·표지 비교. 업무 items 안으로 내려가지 않는다."""
    obj = envelope(value)
    if obj is None or (not root and obj.get('fn_source') not in ('idiom', 'def', 'workflow')):
        return value
    return {k: contract(v) if k == 'final_result' else v for k, v in obj.items()
            if k not in ('results', '_results_summarized', '_hint')}


def current_execution(trial, catalog):
    request = {'code': trial['attempts'][0]['code'], 'case_id': trial['case'],
               'named': trial['arm'] != 'none', 'catalog': catalog}
    proc = subprocess.run(
        [sys.executable, str(ROOT / 'scripts/idiom_experiment_worker.py')],
        input=json.dumps(request), text=True, capture_output=True, timeout=30, cwd=ROOT)
    if proc.returncode:
        raise RuntimeError(proc.stderr[-1500:])
    ex = json.loads(proc.stdout)
    return {'id': trial['id'], 'arm': trial['arm'],
            'before': trial['attempts'][0]['execution']['quality_ok'],
            'after': ex['quality_ok'], 'execution': ex}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--replay', action='store_true')
    args = parser.parse_args()
    manifest = json.loads((args.out / 'manifest.json').read_text())
    ref = manifest['base_commit']
    if not re.fullmatch('[0-9a-f]{40}', ref):
        parser.error('base_commit은 git 해시여야 합니다')
    source = subprocess.check_output(
        ['git', 'show', f'{ref}:backend/ibl/ibl_envelope.py'], cwd=ROOT, text=True)
    before = types.ModuleType('_baseline_ibl_envelope')
    exec(compile(source, f'{ref}:ibl_envelope.py', 'exec'), before.__dict__)
    trials = [json.loads(p.read_text()) for p in sorted((args.out / 'trials').glob('*.json'))]
    policy = load_policy_block('envelope_preview', ibl_envelope.PREVIEW_DEFAULT)
    data = {'baseline_ref': ref, 'policy': policy,
            'before_source_sha256': hashlib.sha256(source.encode()).hexdigest(),
            'after_source_sha256': hashlib.sha256(Path(ibl_envelope.__file__).read_bytes()).hexdigest(),
            'unit': 'dumps_public_result(indent=2) chars; diet+preview; task metadata excluded',
            'arms': {}, 'attempts': []}
    for trial in trials:
        arm = data['arms'].setdefault(trial['arm'], {'before_chars': 0, 'after_chars': 0, 'attempts': 0})
        for index, attempt in enumerate(trial['attempts']):
            raw = attempt['execution'].get('result', {})
            old = before.diet_envelope(raw)
            new = ibl_envelope.diet_envelope(raw)
            assert contract(old, root=True) == contract(new, root=True), trial['id']
            sizes = {}
            for label, module, value in [('before', before, old), ('after', ibl_envelope, new)]:
                text = dumps_public_result(module.preview_envelope(value, policy=policy), indent=2)
                sizes[label + '_chars'] = len(text)
                arm[label + '_chars'] += len(text)
            arm['attempts'] += 1
            data['attempts'].append({'id': trial['id'], 'attempt': index, **sizes, 'same_contract': True})
    if args.replay:
        catalog = json.loads((args.out / 'catalog.json').read_text())
        with ThreadPoolExecutor(max_workers=2) as pool:
            data['replay'] = list(pool.map(lambda t: current_execution(t, catalog), trials))
        for arm in data['arms']:
            rows = [r for r in data['replay'] if r['arm'] == arm]
            data['arms'][arm]['first_pass_before'] = sum(r['before'] for r in rows)
            data['arms'][arm]['first_pass_after'] = sum(r['after'] for r in rows)
    dump(args.out / 'boundary_comparison.json', data)
    print(json.dumps(data['arms'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
