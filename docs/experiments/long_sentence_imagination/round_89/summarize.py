"""Compact, non-secret evidence for the tracked training report."""
import collections
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-22_89회차'


def read(path):
    return json.loads(path.read_text())


def main():
    audit = read(OUT / 'runs/audit_summary.json')
    trainer = read(HERE / 'trainer_verification.json')
    ai = read(HERE / 'ai_verification.json')
    turns = []
    for turn in audit['turns']:
        label = turn['turn']
        result_path = OUT / 'runs' / f'{label}_result.json'
        result = read(result_path) if result_path.exists() else {}
        totals = collections.Counter()
        for usage in turn['usage'].values():
            totals.update(usage)
        tools = read(OUT / 'runs' / f'{label}_tool_inputs.json')
        planning = read(OUT / 'runs' / f'{label}_planning_tool_inputs.json')
        # These are lexical indicators for manual audit, not an access-control claim.
        suspect = []
        for tool in tools + planning:
            body = json.dumps(tool['input'], ensure_ascii=False)
            hits = [word for word in ['/trainer', '/reference', '/staged', '/snapshots', '/runs/', '/tmp/', '/private/tmp/', 'round_89'] if word in body]
            if hits:
                suspect.append({'seq': tool['seq'], 'indicators': hits})
        log_path = OUT / 'ai' / label / 'run_log.json'
        log = read(log_path) if log_path.exists() else {}
        turns.append({**{k: turn[k] for k in ('turn', 'task_id', 'episodes', 'usage', 'tool_count', 'full_tool_inputs',
            'planning_tool_count', 'full_planning_inputs', 'models', 'context_compacted', 'evaluations')},
            'totals': dict(totals), 'state': result.get('state'), 'pending_children': result.get('pending_children'),
            'access_indicators_for_manual_review': suspect,
            'artifact_run_started': log.get('run_started_at'), 'artifact_run_ended': log.get('run_ended_at'),
            'reused': log.get('reused', log.get('preserved')), 'recomputed': log.get('recomputed', log.get('reprocessed', log.get('updated')))})
    runs = []
    for file in sorted((OUT / 'runs').glob('*.json')):
        obj = read(file)
        response = obj.get('response', {}) if isinstance(obj, dict) else {}
        if 'executed' not in response or response.get('executed') is not True:
            continue
        runs.append({'label': file.stem, 'success': response.get('success'), 'run_status': response.get('run_status'),
            'run_id': response.get('resume', {}).get('run_id'), 'seconds': obj.get('seconds'),
            'elapsed_ms': response.get('usage', {}).get('elapsed_ms'), 'steps': response.get('usage', {}).get('steps'),
            'source_complete': response.get('source_complete'), 'error': response.get('error'),
            'reuse': response.get('reuse'), 'response_sha256': hashlib.sha256(file.read_bytes()).hexdigest()})
    evidence = {'start': read(OUT / 'start.json'), 'head_at_capture': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'closure': read(OUT / 'end.json') if (OUT / 'end.json').exists() else None,
        'trainer_checks': {k: trainer[k] for k in ('passed', 'failed')}, 'ai_checks': {k: ai[k] for k in ('passed', 'failed')},
        'benchmark': trainer['benchmark'], 'turns': turns, 'trainer_runs': runs,
        'preservation': audit['preservation'], 'seed_reconstruction': read(HERE / 'seed_verification.json'),
        'limits': ['CPU 동시 수행은 구간 겹침만으로 입증하지 않는다', '훈련자 작성 토큰 미측정',
            'AI 전체 시간·토큰 개선율 미측정', '접근 감사는 수집된 도구 인자와 보존 스크립트 범위']}
    (HERE / 'evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'turns': [{'turn': t['turn'], 'state': t['state'], 'totals': t['totals']} for t in turns],
        'trainer_runs': len(runs), 'trainer_checks': evidence['trainer_checks'], 'ai_checks': evidence['ai_checks']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
