"""Preserve existing round evidence; no new research, model calls, or mutations to products."""
import collections
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

from transport import ROOT, DOC, OUT


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))


def fingerprint(path):
    return {str(f.relative_to(path)): {
        'sha256': hashlib.sha256(f.read_bytes()).hexdigest(),
        'mtime_ns': f.stat().st_mtime_ns, 'bytes': f.stat().st_size,
    } for f in path.rglob('*') if f.is_file()}


def decode(value):
    tag, *tail = value
    if tag == 'record':
        return {k: decode(v) for k, v in tail[0]}
    if tag == 'list':
        return [decode(v) for v in tail[0]]
    return tail[0] if tail else None


def preserve():
    con = sqlite3.connect(f'file:{ROOT}/data/world_pulse.db?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    metric = json.loads((OUT / 'evidence/ai_metrics.json').read_text())
    traces = json.loads((OUT / 'evidence/ai_trace.json').read_text())
    summaries, calls, crawl, evaluations, costs = {}, {}, [], [], []
    for stage, entry in metric.items():
        eid = entry['episode']['id']
        calls[stage] = traces[stage]['tools']
        summaries[stage] = []
        index = 0
        for row in con.execute('select kind,data from trajectory_event where episode_id=? order by event_seq', (eid,)):
            data = json.loads(row['data'])
            if row['kind'] in ('supervision.evaluation.finished', 'supervision.cost.summary'):
                clean = {k: v for k, v in data.items() if k not in ('store',)}
                (evaluations if row['kind'].endswith('evaluation.finished') else costs).append({'stage': stage, **clean})
            if row['kind'] != 'supervision.tool.finished':
                continue
            ref = data.get('evidence', {})
            p = Path(data['store']) / (ref.get('id', '') + '.txt')
            raw = p.read_text() if p.is_file() else ref.get('excerpt', '{}')
            try:
                result = json.loads(raw)
            except json.JSONDecodeError:
                result = {}
            if not isinstance(result, dict):
                result = {}
            summaries[stage].append({
                'index': index, 'name': data.get('name'),
                'elapsed_s': data.get('elapsed_s'), 'check_rejected': data.get('check_rejected'),
                'is_error': data.get('is_error'), 'success': result.get('success'),
                'error': result.get('error'), 'run_status': result.get('run_status'),
                'resume': result.get('resume'), 'diagnostic': result.get('diagnostic'),
                'read_scope': result.get('read_scope'),
            })
            fullref = result.get('result_ref', {})
            fullpath = Path(data['store']) / (fullref.get('id', '') + '.txt')
            full = json.loads(fullpath.read_text()) if fullpath.is_file() else result
            # read_result references can point to the same run; only actual execute calls count.
            request = calls[stage][index]['request']
            if not request.get('read_result'):
                for record in full.get('recordings', []):
                    if record.get('action') != 'sense:crawl':
                        continue
                    value = decode(record['value']) if 'value' in record else {}
                    if not isinstance(value, dict):
                        value = {}
                    crawl.append({'stage': stage, 'tool_index': index,
                                  'url': value.get('url'), 'cache': value.get('cache'),
                                  'title': value.get('title'), 'error': record.get('error')})
            index += 1
    dump(DOC / 'evidence/ai_calls.json', calls)
    dump(DOC / 'evidence/ai_results.json', summaries)
    dump(DOC / 'evidence/evaluations.json', evaluations)
    dump(DOC / 'evidence/cost_summaries.json', costs)
    dump(DOC / 'evidence/crawl_reuse.json', crawl)
    dump(DOC / 'evidence/ai_metrics.json', metric)
    runs = json.loads((OUT / 'evidence/trainer_runs.json').read_text())
    dump(DOC / 'evidence/trainer_runs.json', runs)
    preservation = {}
    for executor in ('trainer', 'ai'):
        before = json.loads((OUT / f'evidence/{executor}_base_before_variant.json').read_text())
        after = fingerprint(OUT / executor / 'base')
        dump(OUT / f'evidence/{executor}_base_after_variant.json', after)
        preservation[executor] = {'all_bytes_and_mtimes_unchanged': before == after,
                                 'files': len(before), 'before': before, 'after': after}
        for stage, filenames in (('base', ('research.md', 'evidence.json', 'source_notes.md')),
                                 ('variant', ('decision.md',))):
            dest = DOC / 'artifacts' / executor / stage
            dest.mkdir(parents=True, exist_ok=True)
            for filename in filenames:
                shutil.copy2(OUT / executor / stage / filename, dest / filename)
    dump(DOC / 'evidence/preservation.json', preservation)
    selected = ['search', 'collect', 'extract_v3', 'report_v1', 'variant']
    manifest = {}
    paths = {'search': 'search_v0.ibl', 'collect': 'collect_v0.ibl',
             'extract_v3': 'extract_v3.ibl', 'report_v1': 'report_v1.ibl',
             'variant': 'variant_v0.ibl'}
    for label in selected:
        payload = json.loads((OUT / 'payloads' / f'{label}.json').read_text())
        payload.pop('code')
        manifest[label] = {'program': f'drafts/{paths[label]}', 'payload': payload}
    dump(DOC / 'replay_manifest.json', manifest)
    scope = []
    for path in sorted((OUT / 'trainer/base/sources').glob('*.json')):
        d = json.loads(path.read_text())
        scope.append({'study': path.stem, 'total_pages': d.get('total_pages'),
                      'items': len(d['items']), 'first_item_type': d['items'][0]['type'],
                      'characters': len(d['text'])})
    dump(DOC / 'evidence/source_scope.json', scope)
    model = collections.Counter()
    for label in selected:
        usage = runs[label]['usage'].get('model') or {}
        model.update({k: usage.get(k, 0) for k in ('requests','input','output','cache_read','cache_create')})
    print(json.dumps({'preserved': {k: {'same': v['all_bytes_and_mtimes_unchanged'], 'files': v['files']} for k,v in preservation.items()},
                      'trainer_model_total': dict(model), 'trainer_calls': {k:runs[k]['wall_s'] for k in selected},
                      'ai_crawl_invocations':len(crawl), 'crawl_cache':collections.Counter(str(r['cache']) for r in crawl)}, ensure_ascii=False))


if __name__ == '__main__':
    preserve()
