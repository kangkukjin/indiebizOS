#!/usr/bin/env python3
"""Read-only episode 5811 context audit; emit measurements, never source bodies.

Packing replay changes serialization only, restores every field, and adds the
complete already-read citation receipts. It does not run models or predict usage.
"""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
import collections
import hashlib
import json
import re
import sqlite3

STORE = BASE / 'data/spill/supervision/f49d5511f9604ef3b894eafda8db2484'
ROLLOUTS = {
    'execution': 'rollout-2026-11-04T11-51-21-01a1a477-dea0-7310-8074-7cba3fab3184.jsonl',
    'evaluation1': 'rollout-2026-11-04T12-04-15-01a1a483-abb7-7f21-9fae-54f3289ad0d0.jsonl',
    'evaluation2': 'rollout-2026-11-04T12-04-45-01a1a484-221d-7451-a8a1-8d6398470b24.jsonl',
}


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def user_text(items):
    return max((part.get('text', '') for row in items
                if row['type'] == 'response_item' and row['payload'].get('role') == 'user'
                for part in row['payload'].get('content', [])), key=len)


def evaluation_sections(text):
    found = []
    for match in re.finditer(r'^\{[^\n]+\}$', text, re.M):
        try:
            value = json.loads(match[0])
        except ValueError:
            continue
        if isinstance(value, dict) and 'completeness' in value and 'subject' in value:
            found.append((match, value))
    result = []
    for i, (match, meta) in enumerate(found):
        end = found[i + 1][0].start() if i + 1 < len(found) else len(text)
        result.append({'meta': meta, 'body': text[match.end():end].strip(),
                       'serialized_chars': end - match.start()})
    return result


def table_pack(records):
    """Column names once, cell values unchanged; missing and null are distinct."""
    columns = list(dict.fromkeys(key for row in records for key in row))
    return {'columns': columns,
            'rows': [[i for i, key in enumerate(columns) if key in row] for row in records],
            'values': [[row[key] for key in columns if key in row] for row in records]}


def table_unpack(table):
    return [{table['columns'][i]: value for i, value in zip(indices, values)}
            for indices, values in zip(table['rows'], table['values'])]


def intern_strings(value):
    """Readable aliases for repeated long strings; reversible collision-free codec."""
    counts = collections.Counter()

    def count(obj):
        if isinstance(obj, str):
            counts[obj] += 1
        elif isinstance(obj, list):
            for item in obj:
                count(item)
        elif isinstance(obj, dict):
            for item in obj.values():
                count(item)

    count(value)
    dictionary = [s for s, n in counts.items() if len(s) >= 32 and n > 1]
    aliases = {s: i for i, s in enumerate(dictionary)}

    def pack(obj):
        if isinstance(obj, str) and obj in aliases:
            return {'$audit_ref': aliases[obj]}
        if isinstance(obj, list):
            return [pack(item) for item in obj]
        if isinstance(obj, dict):
            assert '$audit_ref' not in obj
            return {key: pack(item) for key, item in obj.items()}
        return obj

    def unpack(obj):
        if isinstance(obj, dict) and '$audit_ref' in obj:
            return dictionary[obj['$audit_ref']]
        if isinstance(obj, list):
            return [unpack(item) for item in obj]
        if isinstance(obj, dict):
            return {key: unpack(item) for key, item in obj.items()}
        return obj

    packed = pack(value)
    assert unpack(packed) == value
    return {'dictionary': dictionary, 'data': packed}


def audit(session_dir):
    loaded = {k: rows(session_dir / v) for k, v in ROLLOUTS.items()}
    packet = json.loads((STORE / 'repair_review.json').read_text())['packet']
    result = {'episode_id': 5811, 'scope': 'stored evidence; no model replay',
              'source_hashes': {k: sha((session_dir / v).read_bytes()) for k, v in ROLLOUTS.items()}}
    with sqlite3.connect((BASE / 'data/world_pulse.db').as_uri() + '?mode=ro', uri=True) as db:
        summary = db.execute('SELECT steps,total_ms FROM episode_summary WHERE episode_id=5811').fetchone()
    usage = collections.defaultdict(collections.Counter)
    for step in json.loads(summary[0]):
        if step.get('event') == 'usage' and step.get('accounting') == 'billable_usage':
            for key in ('input', 'output', 'cache_read'):
                usage[step['role']][key] += step.get(key, 0)
    result['billed_usage_before_postprocess'] = dict(usage)
    result['wall_ms'] = summary[1]
    result['postprocess'] = json.loads((STORE / 'postprocess.json').read_text())
    execution = loaded['execution']
    usages = [r['payload']['usage'] for r in execution if r['type'] == 'token_usage_record']
    assert sum(u['input_tokens'] for u in usages) == usage['execution']['input']
    assert sum(u['cached_input_tokens'] for u in usages) == usage['execution']['cache_read']
    result['execution_rounds'] = usages
    result['execution_context'] = {'first_input': usages[0]['input_tokens'],
        'last_input': usages[-1]['input_tokens'],
        'compaction_events': sum(r['type'] == 'compacted' for r in execution),
        'mean_input': sum(u['input_tokens'] for u in usages) / len(usages)}
    calls, categories, situations = {}, collections.defaultdict(collections.Counter), []
    round_index = 0
    json_outputs = []
    for row in execution:
        p = row['payload']
        if row['type'] == 'token_usage_record':
            round_index += 1
        if row['type'] != 'response_item':
            continue
        if p.get('type') in {'function_call', 'custom_tool_call'}:
            calls[p['call_id']] = p.get('name')
        if p.get('type') not in {'function_call_output', 'custom_tool_call_output'}:
            continue
        output = p.get('output', '')
        blocks = output if isinstance(output, list) else [{'text': str(output)}]
        for block in blocks:
            text = block.get('text', '')
            group = 'other_tool_text'
            value = None
            if text.startswith('[Execution situation'):
                group = 'situation'
                value = json.loads(text.split('\n', 1)[1])
                situations.append(value)
            else:
                try:
                    value = json.loads(text)
                except ValueError:
                    pass
                if isinstance(value, dict) and calls.get(p.get('call_id')) == 'execute_ibl':
                    group = 'ibl_json'
                    json_outputs.append(value)
            categories[group]['chars'] += len(text)
            categories[group]['blocks'] += 1
            categories[group]['weighted_chars'] += len(text) * (len(usages) - round_index)
    result['tool_output_categories'] = dict(categories)
    result['tool_output_measurement_note'] = (
        'Unicode characters, not tokens. weighted_chars multiplies each recorded block '
        'by subsequent response records; this is a transcript exposure proxy, '
        'not measured token attribution or a latency estimate.')
    keys = collections.Counter()
    for output in json_outputs:
        for key, value in output.items():
            keys[key] += len(dumps(value))
    result['ibl_output_value_serializations'] = dict(keys.most_common())
    observations = [o['latest']['id'] for s in situations for o in s.get('observations', [])]
    result['situation'] = {'count': len(situations),
        'modes': dict(collections.Counter(s['mode'] for s in situations)),
        'observations': len(observations), 'unique_observations': len(set(observations))}
    evaluations = {}
    for label in ('evaluation1', 'evaluation2'):
        text = user_text(loaded[label])
        sections = evaluation_sections(text)
        groups = collections.Counter()
        for row in sections:
            group = re.sub(r'\[\d+\]', '[]', row['meta']['subject'])
            if row['meta']['role'] in {'submission', 'recovered'}:
                group = row['meta']['role']
            groups[group] += row['serialized_chars']
        begin = text.index('## 회수 가능한 원문 주소')
        start = text.index('\n', begin) + 1
        end = text.index('\n\n## 선택된 증거', start)
        refs = json.loads(text[start:end])
        evaluations[label] = {'actual_user_message_chars': len(text), 'reference_chars': end - start,
            'reference_count': len(refs), 'sections': dict(groups),
            'completeness': dict(collections.Counter(r['meta']['completeness'] for r in sections))}
        if label != 'evaluation1':
            continue
        # Faithful serialization prototype. Keep every section byte and reference
        # field, including all instructions/criteria. Table and dictionary indexes
        # replace repetition. No claim importance classifier or source summary.
        packed_refs = table_pack(refs)
        assert table_unpack(packed_refs) == refs
        meta = table_pack([s['meta'] for s in sections])
        assert table_unpack(meta) == [s['meta'] for s in sections]
        structured = []
        for section in sections:
            try:
                body = json.loads(section['body'])
                assert json.loads(dumps(body)) == body
            except ValueError:
                body = section['body']
            structured.append(body)
        replay = {'reference_index': packed_refs, 'section_index': meta, 'sections': structured}
        packed = intern_strings(replay)
        result['packing_replay'] = {
            'original_reference_and_section_chars': len(text) - start,
            'packed_chars': len(dumps(packed)),
            'unchanged_prefix_chars': start,
            'total_message_chars': start + len(dumps(packed)),
            'field_and_body_roundtrip_verified': True,
            'format': 'columnar metadata + repeated string aliases + JSON whitespace normalization',
            'not_measured': 'model tokens, latency, model understanding of new format, research quality',
        }
    result['evaluations'] = evaluations
    citations = packet['context']['research_citations']
    citation_rows = citations['valid']
    full_reads = []
    with sqlite3.connect((BASE / 'projects/투자/conversations.db').as_uri() + '?mode=ro', uri=True) as db:
        for citation in citation_rows:
            for ref in citation['read_refs']:
                row = db.execute('SELECT version_id,locator,revision,quote FROM research_access WHERE rowid=?',
                                 (ref['access_id'],)).fetchone()
                assert row[:3] == (citation['version_ref'], citation['locator'], ref['extraction_revision'])
                assert len(row[3]) == ref['chars']
                full_reads.append({'citation': citation['citation'], 'access_id': ref['access_id'],
                                   'revision': row[2], 'quote': row[3]})
    result['citation_coverage'] = {'citations': len(citation_rows),
        'claims': len(packet['context']['research_claims']),
        'selected_chars': citations['evidence_chars'],
        'full_already_read_chars': sum(len(r['quote']) for r in full_reads),
        'partial_citations': sum(c['truncated'] for c in citation_rows),
        'receipts_identity_and_length_verified': True,
        'micron': [{'locator': c['locator'], 'full_chars': c['full_chars'],
                    'selected_chars': sum(s['end'] - s['start'] for s in c['segments'])}
                   for c in citation_rows if c['version_ref'] == '8fee0b072a9e49e4b64f66862bdee1c8']}
    # Conservative expansion: add ALL full receipts alongside existing excerpts,
    # rather than claim a reduction by deleting partial receipts or metadata.
    result['packing_replay']['with_full_receipts_chars'] = (
        result['packing_replay']['total_message_chars'] + len(dumps(full_reads)))
    result['packing_replay']['full_receipts_added_chars'] = len(dumps(full_reads))
    events = rows(STORE / 'events.jsonl')
    result['timings'] = [{k: e[k] for k in ('kind', 'phase', 'elapsed_s') if k in e}
                        for e in events if e['kind'] in {'model.finished', 'evaluation.finished',
                                                         'evaluation.evidence_recovered'}]
    result['cost_summary'] = json.loads((STORE / 'cost.json').read_text())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sessions', type=Path,
                        default=Path.home() / '.codex/sessions/2026/11/04')
    parser.add_argument('--output', type=Path,
                        default=BASE / 'docs/experiments/episode5811_context_audit_2026_11_04.json')
    args = parser.parse_args()
    result = audit(args.sessions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('execution_context', 'tool_output_categories',
          'situation', 'evaluations', 'citation_coverage', 'packing_replay')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
