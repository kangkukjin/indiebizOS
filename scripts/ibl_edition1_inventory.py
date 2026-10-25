#!/usr/bin/env python3
"""Read-only inventory of edition retirement inputs; never boots live stores."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
import ast
from collections import Counter
import hashlib
import json
import sqlite3

import yaml
from ibl_edition import source_edition

SOURCE_KEYS = {'code', 'pipeline', 'do', 'steps', 'load', 'action', 'options_action', 'ibl_code'}
LEGACY_MODULES = {
    'ibl_parser', 'ibl_parser_blocks', 'ibl_parser_values', 'ibl_parser_scope',
    'ibl_control_blocks', 'ibl_exec_each', 'ibl_executors', 'workflow_engine',
    'workflow_binding', 'workflow_contract', 'workflow_parallel', 'workflow_fallback',
    'ibl_v2_compat', 'pipeline_state',
}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    default=str).encode()).hexdigest()


def walk(value, location='$', inherited=None, active=True):
    """Preserve parent edition. Ambiguous strings are candidates, never proof."""
    if isinstance(value, dict):
        edition = value.get('edition', inherited)
        active = active and value.get('enabled', True) is not False and value.get('state') not in ('retired','hold','quarantine')
        for key, item in value.items():
            at = location + '.' + str(key)
            if key in SOURCE_KEYS and isinstance(item, str) and (
                    '[' in item or item.lstrip().startswith(('#!ibl', 'return ', '$'))):
                try:
                    ed, problem = source_edition(item, edition), None
                except (ValueError, TypeError) as exc:
                    ed, problem = None, str(exc).split(':')[0]
                yield {'location': at, 'edition': ed, 'hash': fingerprint(item),
                       'problem': problem, 'kind': 'source', 'active': active}
            elif key in ('steps','pipeline','code','do') and isinstance(item, list) and any(isinstance(v, dict) or (isinstance(v,str) and ':' in v) for v in item):
                yield {'location': at, 'edition': 1, 'hash': fingerprint(item), 'kind': 'steps', 'active': active}
            elif key in ('function_ref', 'function_refs', 'workflow_id'):
                refs = item if isinstance(item, list) else [item]
                for ref in refs:
                    public = ({k: ref[k] for k in ('function_id', 'revision', 'edition', 'name') if k in ref}
                              if isinstance(ref, dict) else {'workflow_id': ref})
                    yield {'location': at, 'kind': 'reference', 'reference': public}
            else:
                yield from walk(item, at, edition, active)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from walk(item, f'{location}[{i}]', inherited, active)


def inventory(root):
    root = Path(root).resolve()
    out = {'schema': 1, 'read_only': True, 'functions': [], 'surfaces': [],
           'imports': [], 'corpus': {}, 'errors': [], 'unresolved': []}
    catalog_path = root / 'data/workflows/catalog.json'
    if catalog_path.exists():
        catalog = json.loads(catalog_path.read_text())
        out['catalog_generation'] = catalog['generation']
        out['catalog_hash'] = fingerprint(catalog)
        for fid, entry in catalog['functions'].items():
            p = root / 'data/workflows/revisions' / fid / (entry['revision'] + '.yaml')
            record = yaml.safe_load(p.read_text())
            out['functions'].append({'function_id': fid, **entry,
                                     'source_hash': fingerprint(record.get('source', '')),
                                     'origin': record.get('origin'),
                                     'legacy_body': bool(record.get('legacy'))})
    paths = set()
    for pattern in ('data/calendar_events.json', 'data/event_triggers.json',
                    'projects/*/schedules.json', 'data/instruments/*.yaml',
                    'data/idioms/*.json', 'data/idioms/*.yaml',
                    'data/ibl_nodes_src/*.yaml', 'data/switches.json', 'data/member_apps.yaml',
                    'data/packages/installed/tools/*/ibl_actions.yaml'):
        paths.update(root.glob(pattern))
    for p in sorted(paths):
        if p.is_symlink():
            out['unresolved'].append({'owner': str(p.relative_to(root)), 'reason': 'symlink'})
            continue
        try:
            value = json.loads(p.read_text()) if p.suffix == '.json' else yaml.safe_load(p.read_text())
            out['surfaces'].append({'owner': str(p.relative_to(root)),
                                    'hash': fingerprint(value), 'programs': list(walk(value))})
        except (ValueError, OSError, yaml.YAMLError) as exc:
            out['errors'].append({'owner': str(p.relative_to(root)), 'error': type(exc).__name__})
    for p in sorted((root / 'backend').rglob('*.py')):
        if p.name.startswith('test_') or 'tests' in p.parts:
            continue
        try:
            tree = ast.parse(p.read_text())
        except (SyntaxError, UnicodeError) as exc:
            out['errors'].append({'owner': str(p.relative_to(root)), 'error': type(exc).__name__})
            continue
        for node in ast.walk(tree):
            modules = ([node.module] if isinstance(node, ast.ImportFrom) else
                       [a.name for a in node.names] if isinstance(node, ast.Import) else [])
            for module in modules:
                if module in LEGACY_MODULES:
                    out['imports'].append({'owner': str(p.relative_to(root)), 'module': module,
                                           'line': node.lineno,
                                           'names': [a.name for a in node.names]})
    db_path = root / 'data/ibl_usage.db'
    if db_path.exists():
        with sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True) as db:
            counts = Counter()
            for (source,) in db.execute('SELECT ibl_code FROM ibl_examples'):
                try:
                    counts[str(source_edition(source))] += 1
                except (ValueError, TypeError):
                    counts['invalid'] += 1
            out['corpus']['examples_by_edition'] = dict(counts)
    out['inspection'] = {
        'switch': {'disposition':'natural_language', 'evidence':'backend/cognition/switch_runner.py:run'},
        'channel': {'disposition':'current_entry', 'evidence':'backend/services/channel_poller.py:_fire_channel_pipeline'},
        'member': {'disposition':'reject_legacy_library', 'evidence':'backend/ibl/ibl_member_library.py:definitions'},
        'remote': {'disposition':'explicit_current_source_or_negotiated_leaf_protocol', 'evidence':'backend/ibl/ibl_engine.py'},
        'apps': {'disposition':'edition2_source_and_inputs', 'evidence':'frontend/src/lib/instrument.ts; source app-block build validation'},
        'seed_history': {'disposition':'excluded_from_executable_recall', 'evidence':'backend/base/corpus_policy.py; backend/boot_paths.py'},
    }
    for surface in out['surfaces']:
        owner = surface['owner']
        for program in surface['programs']:
            if program.get('edition') != 1:
                continue
            if '.limb_op.' in program['location']:
                disposition = 'handler_argument_mapping_not_program'
            elif not program.get('active', True):
                disposition = 'inactive_history_execution_rejected'
            elif owner.startswith('data/idioms/'):
                disposition = 'historical_seed_registration_and_recall_excluded'
            else:
                disposition = 'requires_individual_review'
                out['unresolved'].append({'owner': owner, 'location': program['location'],
                                          'reason': 'active_legacy_source'})
            program['disposition'] = disposition
    jobs = root / 'data/phone_jobs.db'
    if jobs.exists():
        with sqlite3.connect(jobs.as_uri()+'?mode=ro', uri=True) as db:
            out['phone_jobs'] = dict(db.execute('SELECT state,count(*) FROM jobs GROUP BY state'))
    out['automatic_wakes'] = len(list((root / 'data/ibl_runs').glob('*/*.wake')))
    out['external_deployment'] = 'External device installations were not updated or certified by this local migration.'
    out['summary'] = {
        'functions': dict(Counter(f"{r['edition']}:{r['state']}" for r in out['functions'])),
        'surface_sources': dict(Counter(str(p.get('edition')) for s in out['surfaces']
                                       for p in s['programs'] if p['kind'] in ('source', 'steps'))),
        'import_edges': len(out['imports']), 'unresolved': len(out['unresolved']),
    }
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = inventory(args.root)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result['summary'], ensure_ascii=False, indent=2))
    return bool(result['errors'])


if __name__ == '__main__':
    raise SystemExit(main())
