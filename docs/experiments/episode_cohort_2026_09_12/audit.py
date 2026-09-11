#!/usr/bin/env python3
"""Read-only historical cohort audit; standard library, no backend/model imports.

Run from any directory with Python 3. No raw tool arguments, prompts, responses,
credentials, or reasoning text are exported. Historical records stay untouched.
"""
import argparse
import ast
import collections
import hashlib
import json
from pathlib import Path
import sqlite3
import statistics
import subprocess
from types import SimpleNamespace
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[3]
PROBES = {2775, 2776, 2777, 2781, 2810, 2811, 2812, 2813, 2818, 2822}
REPORT_REQUESTS = {
    'AI 동향 보고서 써줘.', '부동산 발굴 보고서 써줘',
    '유튜브 AI 팁 보고서 써줘', 'AI 창업·응모 정보 보고서 써줘',
}


def command_probe():
    """Execute ONLY the parsed pure command builder, never initialize a provider."""
    path = ROOT / 'backend/providers/claude_code.py'
    tree = ast.parse(path.read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and any(
        isinstance(f, ast.FunctionDef) and f.name == '_build_command' for f in n.body))
    fn = next(f for f in cls.body if isinstance(f, ast.FunctionDef)
              and f.name == '_build_command')
    namespace = {'List': List, 'Optional': Optional, 'json': json}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(path), 'exec'), namespace)
    fake = SimpleNamespace(_binary_path='claude', agent_role='oneshot:execution',
                           model='opus', system_prompt='fixture', TOOL_POLICY='',
                           disable_thinking=False, reasoning_mode='default')
    before = namespace['_build_command'](fake, tools_mode='none')
    fake.disable_thinking, fake.reasoning_mode = True, 'off'
    after = namespace['_build_command'](fake, tools_mode='none')
    return {'source': str(path.relative_to(ROOT)), 'line': fn.lineno,
            'commands_identical': before == after, 'effort_flag_present': '--effort' in after,
            'scope': 'Pure command construction; inherited environment and server not tested',
            'network_calls': 0}


def audit(end, count, events_through):
    db = ROOT / 'data/world_pulse.db'
    conn = sqlite3.connect(db.resolve().as_uri() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA query_only=ON')
    conn.execute('BEGIN')
    rows = list(conn.execute('''
        SELECT e.*,s.unconscious_decision,s.evaluation_result,s.execution_rounds
        FROM episode_log e LEFT JOIN episode_summary s ON s.episode_id=e.id
        WHERE e.source='usage' AND e.id<=? ORDER BY e.id DESC LIMIT ?
    ''', (end, count)))[::-1]
    if len(rows) != count or len({r['id'] for r in rows}) != count:
        raise ValueError('Cohort size or summary join cardinality mismatch')
    episodes, all_oneshots = [], []
    for row in rows:
        events, malformed = [], []
        for event in conn.execute('SELECT * FROM trajectory_event WHERE episode_id=? '
                                  'AND ts<=? ORDER BY ts,event_seq',
                                  (row['id'], events_through)):
            try:
                data = json.loads(event['data'])
                if not isinstance(data, dict):
                    raise ValueError('not an object')
            except (ValueError, TypeError):
                malformed.append({'run_id': event['run_id'], 'seq': event['event_seq'],
                                  'kind': event['kind']})
                continue
            events.append((event['kind'], data))
        usage = [d for k, d in events if k == 'model.usage']
        roles = {}
        for data in usage:
            role = data.get('role', 'unknown')
            dst = roles.setdefault(role, {'events': 0, 'input': 0, 'output': 0,
                                         'cache_read': 0, 'cache_create': 0,
                                         'latency_ms_sum': 0, 'reasoning_known_events': 0,
                                         'reasoning_known_output': 0, 'reasoning': 0})
            dst['events'] += 1
            for key in ('input', 'output', 'cache_read', 'cache_create'):
                dst[key] += data.get(key, 0) or 0
            dst['latency_ms_sum'] += data.get('latency_ms', 0) or 0
            if 'reasoning' in data:
                dst['reasoning_known_events'] += 1
                dst['reasoning_known_output'] += data.get('output', 0)
                dst['reasoning'] += data['reasoning']
                if role == 'oneshot:execution':
                    all_oneshots.append((row['id'], data['output'], data['reasoning']))
        started = [d for k, d in events if k == 'ibl.started']
        request, log = row['user_message'] or '', row['log'] or ''
        episodes.append({
            'id': row['id'], 'date': row['started_at'][:10], 'agent': row['agent'],
            'total_ms': row['total_ms'], 'route': row['unconscious_decision'],
            'evaluation': row['evaluation_result'], 'log_chars': len(log),
            'log_sha256': hashlib.sha256(log.encode()).hexdigest(),
            'probe': row['id'] in PROBES,
            'survey': request.startswith(('폴더 조사:', '노트북 조사:')),
            'recurring_report': request.strip() in REPORT_REQUESTS,
            'event_count': len(events), 'malformed_events': malformed,
            'ibl_started': len(started),
            'ibl_top_level_started': sum(d.get('nested') is False for d in started),
            'ibl_top_level_multi': sum(d.get('nested') is False and
                                       d.get('action_count', 0) > 1 for d in started),
            'ibl_finished_failure_signals': sum(k == 'ibl.finished' and
                                                d.get('success') is False for k, d in events),
            'ibl_resumed': sum(k == 'ibl.resumed' for k, d in events),
            'actions': dict(collections.Counter(a for d in started for a in d.get('actions', []))),
            'usage_roles': roles,
        })
    conn.close()
    durations = sorted(e['total_ms'] for e in episodes if e['total_ms'] is not None)
    nonreports = sorted(e['total_ms'] for e in episodes
                        if not e['recurring_report'] and e['total_ms'] is not None)
    summary = {
        'count': len(episodes), 'first_id': episodes[0]['id'], 'last_id': episodes[-1]['id'],
        'first_date': episodes[0]['date'], 'last_date': episodes[-1]['date'],
        'agents': dict(collections.Counter(e['agent'] for e in episodes)),
        'known_duration_count': len(durations), 'recorded_duration_hours': sum(durations) / 3600000,
        'median_seconds': statistics.median(durations) / 1000,
        'p90_nearest_lower_seconds': durations[int(.9 * (len(durations) - 1))] / 1000,
        'top20_duration_share': sum(durations[-20:]) / sum(durations),
        'nonreport_top20_duration_share': sum(nonreports[-20:]) / sum(nonreports),
        'usage_present_episodes': sum(bool(e['usage_roles']) for e in episodes),
        'usage_without_main_execution': [e['id'] for e in episodes if e['usage_roles'] and
                                        not any(k in e['usage_roles'] for k in ('execution', 'system_repair'))],
        'evaluation_counts': dict(collections.Counter(e['evaluation'] or 'NULL' for e in episodes)),
        'log_chars': sum(e['log_chars'] for e in episodes),
        'parsed_events': sum(e['event_count'] for e in episodes),
        'malformed_events': sum(len(e['malformed_events']) for e in episodes),
        'recurring_reports': sum(e['recurring_report'] for e in episodes),
        'explicit_probes': sum(e['probe'] for e in episodes),
        'surveys': sum(e['survey'] for e in episodes),
        'reasoning_observed_internal_calls': len(all_oneshots),
        'reasoning_observed_internal_episodes': len({a[0] for a in all_oneshots}),
        'reasoning_observed_internal_output': sum(a[1] for a in all_oneshots),
        'reasoning_observed_internal_reasoning': sum(a[2] for a in all_oneshots),
    }
    return {'schema': 1, 'code_commit_at_run': subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'selection': {'source': 'usage', 'id_lte': end, 'latest_count': count,
                      'events_through_db_timestamp': events_through},
        'limitations': [
            'Recorded durations include useful work; sum is episode-hours, not user wait or waste.',
            'Usage absent or incomplete is unknown, not zero; no historical dollar estimate.',
            'model.usage only. Snapshots excluded. Reasoning is a subset of output.',
            'Model latency sums overlap tool waits and parallel calls; not additive wall time.',
            'IBL event counts include checks, recovery, nesting; not model calls or action success rate.',
            'Automatic evaluation is not independent artifact quality; old round counts omitted.',
            'Probe/survey/report flags are descriptive, may overlap, not all test traffic is identifiable.',
        ], 'summary': summary, 'command_probe': command_probe(), 'episodes': episodes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--end', type=int, default=3546)
    parser.add_argument('--count', type=int, default=180)
    parser.add_argument('--events-through', default='2026-09-12T02:52:52.296566',
                        help='Inclusive event timestamp in DB format; defaults to cohort snapshot')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.end, args.count, args.events_through)
    with args.out.open('x', encoding='utf-8') as output:
        # One episode per line keeps the artifact bounded; cohort.md is the reading view.
        metadata = {k: v for k, v in result.items() if k != 'episodes'}
        output.write(json.dumps(metadata, ensure_ascii=False, indent=2)[:-2])
        output.write(',\n  "episodes": [\n')
        output.write(',\n'.join('    ' + json.dumps(e, ensure_ascii=False)
                                for e in result['episodes']))
        output.write('\n  ]\n}\n')
    print(json.dumps(result['summary'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
