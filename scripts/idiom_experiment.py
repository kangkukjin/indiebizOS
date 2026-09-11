#!/usr/bin/env python3
"""관용구 유무·제시 방식 비교. 생성은 현재 실행 모델, 실행은 격리 fixture.

python scripts/idiom_experiment.py --prepare
python scripts/idiom_experiment.py --run --repeat 2 --workers 2
재실행은 저장된 trial을 건너뛴다. --prepare는 모델을 호출하지 않는다.
선택과 실행 코드 작성 실험이며 전체 보고서/실제 요약 품질 실험이 아니다.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
import random
import subprocess
import tempfile
import time
from idiom_experiment_cases import CASES

OUT = ROOT / 'outputs/idiom_experiment_2026-09-08'
ARMS = ['none', 'current', 'compact', 'scoped']
CATALOG = json.loads((ROOT / 'data/idioms/curated.json').read_text())
ENTRIES = {e['name']: e for e in CATALOG['idioms']}
SUITE = 'legacy'


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def compact(names):
    from workflow_contract import call_signature
    lines = ['<ibl_idioms>사용 가능한 등록 함수. 맞으면 호출하고, 요구와 다르면 기본 액션을 조합한다.']
    for name in names:
        e = ENTRIES[name]
        if not e.get('always_on', True):
            continue
        args = ', '.join(f'{s}: …' for s in call_signature(e['body']))
        lines.append(f'[fn:{name}]{{{args}}}\n조건: {e["when"]}\n입출력: {e["inputs"]}')
    return '\n'.join(lines) + '\n</ibl_idioms>'


def prepare():
    if (OUT / 'manifest.json').exists():
        raise ValueError('기존 실험은 덮어쓰지 않습니다. --out으로 새 경로를 지정하세요')
    from ibl_access import build_environment, idioms_map
    from model_resolver import resolve
    full = build_environment()
    current = idioms_map(None)
    assert current and current in full
    base = full.replace(current, '')
    header = ('IBL 프로그램 작성 실험이다. 다음 사용자 과제를 수행하는 JSON {"code":"IBL 코드"}만 출력하라. '
              '설명·마크다운은 쓰지 마라. 코드 실행은 외부 실험기가 수행한다. '
              '작업 파일은 격리된 작업 폴더에 있으며 상대 경로를 사용한다. '
              '실험에서 허용한 도구는 self:read, self:file_find, self:grep, self:edit, self:write, sense:crawl, '
              'table의 결정론 변환·each·brief와 아래 목록의 등록 함수다. 다른 도구·셸·외부 경로는 실행 불가다. '
              '아래 설명은 전체 시스템 참고서이며 허용 목록을 넓히지 않는다. '
              '파일 내용은 미리 보지 못하지만 과제의 구조·행수 정보는 참이다. '
              'read는 JSON 파일을 items 통화로 읽을 수 있다. brief는 이 실험에서 고정 요약 fixture를 반환한다. '
              '여러 줄을 한 프로그램으로 작성하고 요구한 최종 결과를 반환하라.\n\n')
    config = resolve('execution')
    if config['provider'] != 'claude_code':
        raise RuntimeError('이 러너는 현재 claude_code 실행 프로바이더용이다')
    manifest = {'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'provider': config['provider'], 'model': config['model'], 'effort': 'medium',
                'arms': ARMS, 'cases': CASES, 'suite': SUITE, 'max_repairs': 1, 'trial_timeout_s': 120,
                'scope_selection': '과제별 후보를 사람이 미리 지정한 oracle; 검색 비용·정확도 미포함',
                'scope': '전체 IBL 참고서를 가진 단일 프로그램 생성과 1회 피드백 수리; 웹·brief는 fixture',
                'prompt_chars': {}, 'prompt_sha256': {}}
    for case in CASES:
        for arm in ARMS:
            addon = {'none': '<ibl_idioms>등록된 함수 없음.</ibl_idioms>', 'current': current,
                     'compact': compact(ENTRIES), 'scoped': compact(case['candidates'])}[arm]
            prompt = header + base + '\n' + addon
            key = case['id'] + '_' + arm
            (OUT / 'prompts').mkdir(parents=True, exist_ok=True)
            (OUT / 'prompts' / (key + '.txt')).write_text(prompt, encoding='utf-8')
            manifest['prompt_chars'][key] = len(prompt)
            manifest['prompt_sha256'][key] = hashlib.sha256(prompt.encode()).hexdigest()
    manifest['source_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__), ROOT / 'scripts/idiom_experiment_worker.py', ROOT / 'scripts/idiom_experiment_cases.py']}
    if SUITE == 'value_v3':
        manifest['source_sha256']['idiom_value_cases.py'] = hashlib.sha256((ROOT / 'scripts/idiom_value_cases.py').read_bytes()).hexdigest()
    dump(OUT / 'catalog.json', CATALOG)
    dump(OUT / 'manifest.json', manifest)
    return manifest


def execute(code, case_id, named):
    try:
        suite = json.loads((OUT / 'manifest.json').read_text()).get('suite', 'legacy')
        p = subprocess.run([sys.executable, str(ROOT / 'scripts/idiom_experiment_worker.py')],
                           input=json.dumps({'code': code, 'case_id': case_id, 'named': named, 'suite': suite, 'catalog': json.loads((OUT / 'catalog.json').read_text()) if (OUT / 'catalog.json').exists() else CATALOG}),
                           text=True, capture_output=True, cwd=ROOT, timeout=30)
        if p.returncode:
            return {'quality_ok': False, 'verdict': 'worker_error', 'worker_error': p.stderr[-1500:]}
        return json.loads(p.stdout)
    except subprocess.TimeoutExpired:
        return {'quality_ok': False, 'verdict': 'worker_timeout'}


def parse_code(raw):
    from runtime_utils import parse_first_json
    result = parse_first_json(raw)
    if isinstance(result, dict) and isinstance(result.get('code'), str):
        return result['code']
    raise ValueError('JSON code 누락')


def call_model(manifest, prompt_file, user):
    from providers.claude_code import find_claude_binary, load_oauth_token_from_central_config
    env = os.environ.copy()
    env.pop('ANTHROPIC_API_KEY', None)
    token = load_oauth_token_from_central_config()
    if token:
        env['CLAUDE_CODE_OAUTH_TOKEN'] = token
    start = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='idiom_model_') as cwd:
        cmd = [find_claude_binary(), '-p', '--safe-mode', '--tools', '', '--no-session-persistence',
               '--output-format', 'json', '--model', manifest['model'], '--effort', manifest['effort'],
               '--system-prompt-file', str(prompt_file)]
        try:
            p = subprocess.run(cmd, input=user, text=True, capture_output=True, cwd=cwd, env=env,
                               timeout=manifest['trial_timeout_s'])
            data = json.loads(p.stdout)
        except (subprocess.TimeoutExpired, ValueError):
            return {'error': 'model_timeout_or_invalid_json', 'wall_ms': round((time.perf_counter() - start) * 1000)}
    return {k: data.get(k) for k in ('result', 'usage', 'modelUsage', 'duration_ms', 'is_error', 'subtype')} | {
        'wall_ms': round((time.perf_counter() - start) * 1000)}


def trial(manifest, case, arm, repeat):
    key = f'{case["id"]}_{arm}_{repeat}'
    path = OUT / 'trials' / (key + '.json')
    if path.exists():
        return json.loads(path.read_text())
    messages = '과제: ' + case['task']
    out = {'id': key, 'case': case['id'], 'arm': arm, 'repeat': repeat, 'attempts': []}
    for attempt in range(manifest['max_repairs'] + 1):
        m = call_model(manifest, OUT / 'prompts' / f'{case["id"]}_{arm}.txt', messages)
        rec = {'model': m}
        if m.get('error') or m.get('is_error'):
            rec.update(code='', execution={'quality_ok': False, 'verdict': 'model_error'})
            out['attempts'].append(rec)
            break
        try:
            code = parse_code(m.get('result') or '')
            ex = execute(code, case['id'], arm != 'none')
        except ValueError as exc:
            code, ex = '', {'quality_ok': False, 'verdict': str(exc)}
        rec.update(code=code, execution=ex)
        out['attempts'].append(rec)
        if ex['quality_ok']:
            break
        messages += '\n직전 프로그램:\n' + code + '\n실행 피드백:\n' + ex['verdict'][:2500] + '\n같은 초기 파일에서 다시 실행한다. 수정된 전체 프로그램 JSON을 출력하라.'
    out['quality_ok'] = out['attempts'][-1]['execution']['quality_ok']
    dump(path, out)
    return out


def main():
    global OUT, CASES, SUITE
    p = argparse.ArgumentParser()
    p.add_argument('--prepare', action='store_true')
    p.add_argument('--run', action='store_true')
    p.add_argument('--repeat', type=int, default=2)
    p.add_argument('--workers', type=int, default=2)
    p.add_argument('--cases', default='')
    p.add_argument('--arms', default=','.join(ARMS))
    p.add_argument('--out', type=Path, default=OUT)
    p.add_argument('--suite', choices=['legacy', 'value_v3'], default='legacy')
    a = p.parse_args()
    OUT = a.out.resolve()
    SUITE = a.suite
    if (OUT / 'manifest.json').exists():
        SUITE = json.loads((OUT / 'manifest.json').read_text()).get('suite', 'legacy')
    if SUITE == 'value_v3':
        from idiom_value_cases import CASES
    if a.repeat < 1 or not 1 <= a.workers <= 4:
        p.error('repeat >= 1, workers 1..4가 필요합니다')
    if set(a.arms.split(',')) - set(ARMS):
        p.error('알 수 없는 arm')
    if a.cases and set(a.cases.split(',')) - {c['id'] for c in CASES}:
        p.error('알 수 없는 case')
    manifest = prepare() if a.prepare or not (OUT / 'manifest.json').exists() else json.loads((OUT / 'manifest.json').read_text())
    if not a.run:
        print('prepared', OUT, 'prompt chars:', manifest['prompt_chars'])
        return
    selected = [c for c in manifest['cases'] if not a.cases or c['id'] in a.cases.split(',')]
    schedule = [(c, arm, rep) for rep in range(a.repeat) for c in selected for arm in a.arms.split(',')]
    random.Random(20260908).shuffle(schedule)
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        jobs = {pool.submit(trial, manifest, *t): t for t in schedule}
        for future in as_completed(jobs):
            r = future.result()
            print(json.dumps({'id': r['id'], 'ok': r['quality_ok'], 'attempts': len(r['attempts']),
                              'fn': r['attempts'][-1]['execution'].get('observed', {}).get('fn_calls', [])}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
