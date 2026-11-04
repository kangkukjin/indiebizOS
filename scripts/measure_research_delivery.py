#!/usr/bin/env python3
"""Frozen episode and controlled model A/B. No live research writes or external tools.

--prepare freezes originals in the required backup directory. --live explicitly
authorizes configured model calls. Public reports contain metrics/hashes, not bodies.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
import copy
import hashlib
import importlib.util
import json
import shutil
import sqlite3
import time
from types import SimpleNamespace

import research_episode5811_context as audit
from evaluation_input import EvaluationPrompt, record, evidence_requests, new_evidence_requests, recover
from evaluation_evidence import freeze_receipts, receipt_sections, structured_sections
from supervision_store import TurnStore

WORK = ROOT / 'data/_backups/2026-11-04_research_delivery_r0'
PUBLIC = ROOT / 'docs/experiments/research_delivery_repair_2026_11_04.json'


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def legacy(name):
    spec = importlib.util.spec_from_file_location('baseline_' + name, WORK / 'backend' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def freeze():
    import subprocess
    WORK.mkdir(parents=True, exist_ok=True)
    baseline = '32a5c289350bc0b7e530d518e609e63a62d6783c'
    for name in ('evaluation_input', 'model_result_view', 'model_value_preview', 'cognitive_eval', 'final_evaluator'):
        path = WORK / 'backend' / (name + '.py')
        path.parent.mkdir(exist_ok=True)
        original = subprocess.check_output(['git', 'show', f'{baseline}:backend/cognition/{name}.py'], cwd=ROOT)
        if path.exists():
            assert path.read_bytes() == original
        else:
            path.write_bytes(original)
    source = audit.STORE
    shutil.copytree(source, WORK / 'store', dirs_exist_ok=True)
    text = audit.user_text(audit.rows(Path.home() / '.codex/sessions/2026/11/04' / audit.ROLLOUTS['evaluation1']))
    sections = audit.evaluation_sections(text)
    store = TurnStore(WORK / 'store')
    packet = json.loads((source / 'repair_review.json').read_text())['packet']
    receipts = copy.deepcopy(packet['context']['research_citations'])
    with sqlite3.connect((ROOT / 'projects/투자/conversations.db').as_uri() + '?mode=ro', uri=True) as db:
        for citation in receipts['valid']:
            reads = []
            for ref in citation['read_refs']:
                row = db.execute('SELECT version_id,locator,revision,quote FROM research_access WHERE rowid=?',
                                 (ref['access_id'],)).fetchone()
                assert row[:3] == (citation['version_ref'], citation['locator'], ref['extraction_revision'])
                assert len(row[3]) == ref['chars']
                reads.append({'access_id': ref['access_id'], 'extraction_revision': row[2], 'quote': row[3]})
            for key in ('quote', 'segments', 'quote_layout', 'quote_start', 'quote_end', 'truncated',
                        'read_refs', 'evidence_state'):
                citation.pop(key, None)
            citation['receipts'] = reads
            citation['candidate_state'] = 'complete'
    receipts['evidence_chars'] = sum(len(r['quote']) for c in receipts['valid'] for r in c['receipts'])
    receipts['unreviewed'] = []
    freeze_receipts(receipts, store)
    old_rows = []
    for section in sections:
        meta = section['meta']
        page = store.read_evidence(meta['source_ref'], 0, None)
        assert page['integrity'] == 'verified'
        body = page['text']
        old_rows.append(record(body, subject=meta['subject'], role=meta['role'], source_ref=meta['source_ref'],
                               revision=meta['revision'], criterion_ids=meta['criterion_ids']))
    new_rows = []
    from research_review import claims
    all_claims = packet['context']['research_claims']
    for row in old_rows:
        subject = row['subject']
        if subject.startswith('research_claims[') or subject.startswith('research_citations['):
            continue
        if subject.startswith(('evidence_index[', 'assertion_evidence[')):
            row = {**row, 'structured': json.loads(row['text']), 'structure_kind': subject.split('[')[0]}
        new_rows.append(row)
    # Derive exact document coordinates, retaining every historical claim occurrence.
    updated = []
    for claim in all_claims:
        doc = next((r for r in old_rows if r['subject'] == claim['path']), None)
        matches = claims(doc['text'], path=claim['path'], digest=claim['hash']) if doc else []
        updated.append(next((c for c in matches if c['offset'] == claim['offset'] and
                             c['claim_context'] == claim['claim_context']), claim))
    new_rows.extend(structured_sections('research_claims', updated))
    new_rows.extend(structured_sections('research_citations', receipts))
    new_rows.extend(receipt_sections(receipts, store))
    for row in new_rows:
        if row['source_ref'] is None:
            ref = store.evidence(row['text'])
            row.update(source_ref=ref['id'], revision=ref['id'], total=ref['chars'])
    required = text[:text.index('## 회수 가능한 원문 주소')].rstrip()
    old_required = text[:text.index('\n\n## 선택된 증거')]
    frozen = {'old_text': text, 'required': required, 'old_required': old_required,
              'old_rows': old_rows, 'new_rows': new_rows, 'criteria': packet['context']['criteria_contract'],
              'references_context': {'evidence_index': packet['context']['evidence_index']}}
    write(WORK / 'fixture.json', frozen)
    manifest = {'episode': 5811, 'baseline_chars': len(text), 'citation_count': len(receipts['valid']),
                'receipt_chars': receipts['evidence_chars'],
                'hashes': {k: hashlib.sha256(json.dumps(v, ensure_ascii=False).encode()).hexdigest()
                           for k, v in frozen.items()},
                'baseline_modules': {p.name: audit.sha(p.read_bytes()) for p in (WORK / 'backend').glob('*.py')}}
    write(WORK / 'manifest.json', manifest)
    return frozen, store, manifest


def episode_prompts(frozen, provider):
    from evaluation_input import evidence_references
    from final_evaluator import RESEARCH_POLICY
    refs = evidence_references({'selection_sources': frozen['new_rows'], 'context': frozen['references_context']})
    required = frozen['required'].replace(legacy('final_evaluator').RESEARCH_POLICY, RESEARCH_POLICY)
    prompt = EvaluationPrompt(required, frozen['new_rows'], json.dumps(frozen['criteria']), references=refs)
    rendered = prompt.prepare_request(provider)
    assert all(r['completeness'] == 'complete' for r in prompt.metrics['sections'] if r['role'] in ('citation', 'submission'))
    assert len(rendered) < len(frozen['old_text'])
    return frozen['old_text'], rendered, prompt.metrics


def replay_situations():
    from situation_delivery import compact_delivery, expand_delivery
    snapshots = []
    for row in audit.rows(Path.home() / '.codex/sessions/2026/11/04' / audit.ROLLOUTS['execution']):
        output = row.get('payload', {}).get('output', [])
        for block in output if isinstance(output, list) else []:
            text = block.get('text', '')
            if text.startswith('[Execution situation'):
                value = json.loads(text.split('\n', 1)[1])
                packed = compact_delivery(value)
                assert expand_delivery(packed) == value
                snapshots.append({'old_bytes': len(audit.dumps(value).encode()),
                                  'new_bytes': len(audit.dumps(packed).encode()),
                                  'observations': len(value['observations']),
                                  'mode': value['mode'], 'roundtrip_verified': True})
    return snapshots


def call(provider, prompt, system=''):
    from consciousness_agent import call_oneshot_provider, oneshot_failure_details
    from cognitive_eval import parse_eval_verdict
    usage, start = {}, time.monotonic()
    answer = call_oneshot_provider(provider, prompt, system_prompt=system, role='evaluate', usage_sink=usage)
    failure = oneshot_failure_details()
    verdict = parse_eval_verdict(answer or '')[0] if not failure else None
    return {'answer': answer, 'failure': failure, 'usage': usage, 'elapsed_s': time.monotonic()-start,
            'status': 'ACHIEVED' if verdict is True else 'NOT_ACHIEVED' if verdict is False else 'UNKNOWN'}


def evaluate(provider, frozen, store, arm, initial):
    start = time.monotonic()
    rows = copy.deepcopy(frozen[arm + '_rows'])
    packet = {'attachments': rows, 'context': {**frozen['references_context'], 'criteria_contract': frozen['criteria']}}
    rounds = []
    prompt = initial
    for attempt in range(3):
        result = call(provider, prompt)
        rounds.append(result)
        if result['status'] != 'UNKNOWN' or result['failure']:
            break
        parsed = evidence_requests(result['answer'] or '', packet)
        if parsed['status'] not in ('valid', 'normalized'):
            result['recovery_protocol'] = parsed
            break
        requests = new_evidence_requests(parsed['requests'], rows)
        if not requests or attempt == 2:
            break
        recovered = recover(SimpleNamespace(store=store, cancelled=lambda: False), requests)
        rows.extend(recovered)
        result['recovered_chars'] = sum(len(r['text']) for r in recovered)
        cls = legacy('evaluation_input').EvaluationPrompt if arm == 'old' else EvaluationPrompt
        prompt = cls(frozen['old_required' if arm == 'old' else 'required'], rows, json.dumps(frozen['criteria']))
    return {'rounds': rounds, 'elapsed_s': time.monotonic()-start, 'status': rounds[-1]['status']}


def public_result(result):
    measured = all(r['usage'].get('total_requests') for r in result['rounds'])
    return {'status': result['status'], 'elapsed_s': round(result['elapsed_s'], 3), 'rounds': len(result['rounds']),
            'tokens': {k: sum(r['usage'].get(k, 0) for r in result['rounds']) if measured else None
                       for k in ('total_input_tokens', 'total_output_tokens', 'total_cache_read_tokens')},
            'failures': [r['failure'] for r in result['rounds'] if r['failure']],
            'response_hashes': [audit.sha((r['answer'] or '').encode()) for r in result['rounds']]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--only-new', action='store_true', help='Refresh new arm after a policy clarification; retain old measured arms')
    args = parser.parse_args()
    previous = json.loads(PUBLIC.read_text()) if args.only_new else None
    if args.prepare:
        frozen, store, manifest = freeze()
    else:
        frozen = json.loads((WORK / 'fixture.json').read_text())
        store, manifest = TurnStore(WORK / 'store'), json.loads((WORK / 'manifest.json').read_text())
    from consciousness_agent import _resolve_oneshot_provider
    provider = _resolve_oneshot_provider('evaluate')
    if provider is None or not provider.is_ready:
        raise RuntimeError('Configured evaluator unavailable; no model substitution')
    provider.no_tools = True
    provider.tools = []
    provider.system_prompt = ''
    old, new, selection = episode_prompts(frozen, provider)
    report = {'manifest': manifest, 'model': provider.model, 'provider': type(provider).__name__,
              'structural': {'old_chars': len(old), 'new_chars': len(new),
                             'new_request_sha256': audit.sha(new.encode()),
                             'citation_chars_delivered': sum(r['shown_chars'] for r in selection['sections'] if r['role'] == 'citation'),
                             'submission_chars_delivered': sum(r['shown_chars'] for r in selection['sections'] if r['role'] == 'submission')},
              'situation_replay': replay_situations(),
              'cases': [], 'limits': ['Fixed-input replay; not a new live research task.',
                                      'Three repetitions are exploratory, not statistical proof.',
                                      'Cache/load/order affect wall time; cache counted within input, never added again.']}
    if previous:
        report['cases'] = [r for r in previous['cases'] if r['arm'] == 'old']
        report['limits'].append('Old arm retained from alternating run; new arm remeasured after format-policy clarification.')
    write(PUBLIC, report)
    print(json.dumps(report['structural']), flush=True)
    if not args.live:
        return
    for repeat in range(args.repetitions):
        for arm in (('new',) if args.only_new else ('old', 'new') if repeat % 2 == 0 else ('new', 'old')):
            print(f'episode5811 {repeat} {arm}', flush=True)
            result = evaluate(provider, frozen, store, arm, old if arm == 'old' else new)
            write(WORK / f'episode-{repeat}-{arm}.json', result)
            report['cases'].append({'case': 'episode5811', 'repeat': repeat, 'arm': arm, **public_result(result)})
            write(PUBLIC, report)
            print(json.dumps(report['cases'][-1]), flush=True)


if __name__ == '__main__':
    main()
