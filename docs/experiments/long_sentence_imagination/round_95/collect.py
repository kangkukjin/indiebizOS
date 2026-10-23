"""Compact, non-sensitive evidence from this rehearsal's immutable records."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
import hashlib
import json
import subprocess
from collections import Counter
from prepare import OUT, HERE


def read(path):
    return json.loads(path.read_text())


def collect():
    runs = OUT / 'runs'
    evidence = {'baseline': read(OUT / 'start.json'),
                'end_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'trainer': [], 'ai': [], 'probes': []}
    for probe in read(runs / 'probes.json'):
        diagnostic = probe.get('diagnostic')
        evidence['probes'].append({**probe, 'diagnostic': None if diagnostic is None else
            {k: diagnostic[k] for k in ('code', 'kind', 'message') if k in diagnostic}})
    for tag in ('trainer_T1_v1', 'trainer_T1_v2', 'trainer_T2_v2'):
        result = read(runs / f'{tag}_result.json')
        reuse = result.get('reuse', {})
        evidence['trainer'].append({'tag': tag, 'success': result['success'],
            'resume': result.get('resume'), 'usage': {k: result.get('usage', {}).get(k)
                for k in ('steps', 'rows', 'elapsed_ms', 'limits')},
            'http': read(runs / f'{tag}_timing.json'), 'source_complete': result.get('source_complete'),
            'diagnostic': result.get('diagnostic'), 'reused_calls': reuse.get('reused_calls', 0),
            'changed_resources': sorted({p for s in reuse.get('skipped', [])
                                         for p in s.get('changed_resources', [])})})
    evidence['verification'] = []
    for lane in ('trainer', 'ai'):
        for turn in (1, 2):
            value = read(runs / f'{lane}_T{turn}_verification.json')
            evidence['verification'].append({k: v for k, v in value.items() if k != 'checks'})
    tool_inputs = []
    for row in read(runs / 'episodes.json'):
        turn = row['turn']
        terminal = read(runs / f'ai_T{turn}_result.json')
        assert terminal['state'] in ('succeeded', 'failed', 'cancelled', 'interrupted')
        events = read(runs / f'ai_T{turn}_events.json')
        row['terminal'] = {k: terminal.get(k) for k in ('state', 'pending_children', 'created_at', 'completed_at')}
        row['tool_calls'] = dict(Counter(e['data'].get('name') for e in events if e['kind'] == 'supervision.tool.started'))
        row['model_rounds'] = dict(Counter(e['data'].get('role') for e in events if e['kind'] == 'model.round'))
        row['evaluations'] = [e['data'].get('decision') for e in events if e['kind'] == 'supervision.evaluation.finished']
        row['compactions'] = sum(e['kind'] == 'context.compacted' for e in events)
        row['recall_events'] = dict(Counter(e['kind'] for e in events if e['kind'] in ('recall.presented', 'recall.used')))
        row['total_usage'] = {k: sum(v.get(k, 0) for v in row['usage'].values())
                              for k in ('input', 'output', 'cache_read', 'cache_create')}
        evidence['ai'].append(row)
        for event in events:
            if event['kind'] != 'supervision.tool.started':
                continue
            data = event['data']
            ref = data.get('input', {})
            path = Path(data['store']) / (ref['id'] + '.txt')
            raw = path.read_text()
            tool_inputs.append({'turn': turn, 'seq': event['seq'], 'name': data['name'],
                                'id': data['id'], 'input': json.loads(raw)})
    # Full tool requests remain local; no model response/thought snapshots are published.
    (runs / 'ai_tool_inputs.json').write_text(json.dumps(tool_inputs, ensure_ascii=False, indent=2))
    evidence['artifacts'] = {str(p.relative_to(OUT)): hashlib.sha256(p.read_bytes()).hexdigest()
                             for lane in ('trainer', 'ai') for p in (OUT / lane / 'artifacts').rglob('*') if p.is_file()}
    evidence['health'] = read(runs / 'final_health.json')
    evidence['cleanup'] = read(sorted(runs.glob('stop_*.json'))[-1])
    (HERE / 'evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'verification': evidence['verification'],
                      'ai': [{'turn': r['turn'], 'tool_calls': r['tool_calls'], 'total_usage': r['total_usage'],
                              'evaluations': r['evaluations'], 'compactions': r['compactions']} for r in evidence['ai']]},
                     ensure_ascii=False)[:4500])


if __name__ == '__main__':
    collect()
