#!/usr/bin/env python3
"""Audit a frozen corpus with real parsers/compiler and inert tool adapters.

Never executes programs, imports the live usage DB, or edits corpus rows.
Private row/code outputs stay under the supplied backup directory.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
import json
import re
from collections import Counter, defaultdict

import yaml
from ibl_corpus_snapshot import connect, dump, now, sha
from ibl_edition import source_edition
from ibl_parser import parse, parse_function_body
from ibl_scanner import source_heads, QuoteState
from ibl_v2_adapters import Adapter, validate_contract
from ibl_v2_compile import compile_program
from ibl_v2_contracts import handler_contract
from ibl_v2_ir import Fault
from workflow_contract import call_signature, _signature_of


def forbidden(*args, **kwargs):
    raise AssertionError('Audit must never execute a tool')


def rows_from_snapshot(base):
    rows = []
    with connect(base / 'data/ibl_usage.db') as conn:
        conn.row_factory = __import__('sqlite3').Row
        for r in conn.execute('SELECT * FROM ibl_examples ORDER BY id'):
            rows.append({**dict(r), 'origin': 'data/ibl_usage.db:ibl_examples',
                         'row_id': r['id'], 'role': 'learning'})
    for path in sorted((base / 'data/training').glob('*.json')):
        data = json.loads(path.read_text())
        if not isinstance(data, list):
            raise ValueError(f'Training source is not a list: {path}')
        for i, row in enumerate(data):
            if not isinstance(row, dict):
                row = {'invalid_row_type': type(row).__name__}
            rows.append({**row, 'origin': str(path.relative_to(base)), 'row_id': i, 'role': 'learning'})
    with connect(base / 'data/world_pulse.db') as conn:
        conn.row_factory = __import__('sqlite3').Row
        for r in conn.execute('SELECT * FROM ibl_code_corpus ORDER BY code_sha256'):
            rows.append({**dict(r), 'ibl_code': r['code'],
                         'origin': 'data/world_pulse.db:ibl_code_corpus',
                         'row_id': r['code_sha256'], 'role': 'history'})
    return rows


def frozen_registry(base, rows):
    catalog = yaml.safe_load((base / 'data/ibl_nodes.yaml').read_text())
    # Share the runtime's merge rule, but only supply the backed-up API registry.
    from unittest.mock import patch
    import ibl_registry
    api_path = base / 'data/api_registry.yaml'
    api = yaml.safe_load(api_path.read_text()) if api_path.exists() else {}
    with patch.object(ibl_registry, '_registry', api or {}):
        ibl_registry._merge_api_registry_actions(catalog.get('nodes', {}))
    schemas, providers = {}, {}
    for path in sorted((base / 'data/packages/installed/tools').glob('*/tool.json')):
        data = json.loads(path.read_text())
        for tool in data.get('tools', [data]):
            name = tool.get('name')
            schemas[name] = set((tool.get('input_schema') or {}).get('properties', {}))
            providers[name] = path.parent.name
    contracts, definitions, problems, availability = {}, {}, [], {}
    activation = json.loads((base / 'data/vocabulary/activation.json').read_text()).get('active', {})
    # This is a full declared-catalog audit. Availability is separate from type correctness.
    for node, cfg in catalog.get('nodes', {}).items():
        for action, config in cfg.get('actions', {}).items():
            key = node + ':' + action
            c = config.get('callable_contract') or handler_contract(node, action, config, schemas.get(config.get('tool'), set()))
            validate_contract(c)
            contracts[key] = c
            provider = providers.get(config.get('tool'))
            availability[key] = {'provider': provider,
                                 'active': activation.get(provider, True) if provider else None}
    for row in sorted((r for r in rows if r['role'] == 'learning' and r.get('alias')
                       and r['origin'].endswith(':ibl_examples')), key=lambda r: r.get('updated_at', '')):
        name, code = row['alias'], row['ibl_code']
        try:
            if source_edition(code) == 2:
                definitions[name] = code
                continue
            params = call_signature(code)
            if any(not p.isidentifier() or p.startswith('_') for p in params):
                raise ValueError('Invalid legacy parameter name')
            contracts['fn:' + name] = legacy_contract(params, {})
        except Exception as exc:
            problems.append({'origin': row['origin'], 'row_id': row['row_id'], 'kind': type(exc).__name__})
    for path in sorted((base / 'data/workflows').glob('*.yaml')):
        try:
            wf = yaml.safe_load(path.read_text())
            if wf.get('edition', 1) == 2:
                if wf['name'] in definitions:
                    raise ValueError('Duplicate current function definition')
                definitions[wf['name']] = wf['code']
            else:
                params = _signature_of(wf.get('steps') or wf.get('do') or wf.get('pipeline'))
                contracts['fn:' + path.stem] = legacy_contract(params, wf.get('params_default') or {})
        except Exception as exc:
            problems.append({'origin': str(path.relative_to(base)), 'kind': type(exc).__name__})
    return contracts, definitions, availability, problems


def legacy_contract(params, defaults):
    return {'version': 1, 'params': {p: 'Unknown' for p in [*params, *defaults]},
            'required': [p for p in params if p not in defaults], 'result': 'Record',
            'effects': ['unknown'], 'compatibility': 'legacy-function/1',
            'adapter': {'protocol': 'legacy-envelope', 'value_path': ''}}


def risks(code):
    visible = [' '] * len(code)
    for pos, char in QuoteState().outside(code, hash_comments=True):
        visible[pos] = char
    text = ''.join(visible)
    out = []
    patterns = {'pipeline': r'>>', 'parallel': r'(?<!&)&(?!&)', 'fallback': r'\?\?',
                'each': r'\[table:each\]', 'function': r'\[(fn|def):',
                'table_callback': r'\[table:(filter|compute|select)\]',
                'legacy_return': r'\$return\s*=', 'envelope_field': r'\.items\b',
                'control': r'\[(if|case|repeat|try)\b', 'variables': r'\$[\w{]',
                'nested_source_boundary': r'\[(self:workflow|self:schedule|self:script)\]'}
    for tag, pattern in patterns.items():
        if re.search(pattern, text):
            out.append(tag)
    # Lexical suspicion only. Literal $ in a prompt is not automatically a defect.
    if re.search(r'\$\{|\$[\w]+', code) and code != text:
        out.append('interpolation_review')
    return out


def static_check(code, registry, definitions, alias='', edition=None):
    try:
        edition = source_edition(code, edition)
        if alias and edition == 2:
            from ibl_v2_store import definition_name
            if definition_name(code) != alias:
                raise Fault('LIBRARY_NAME', 'Stored alias and definition name differ', kind='compile')
        # Old function bodies require an explicit test wrapper; never publish this wrapper.
        if alias and edition == 1:
            params = call_signature(code)
            candidate = '[def:AuditBody](' + ','.join('$' + p for p in params) + '){\n' + code + '\n}'
            context = 'legacy_function_body_with_declared_free_inputs'
        else:
            candidate, context = code, 'stored_program'
        plan = compile_program(candidate, registry, definitions=definitions)
        report = plan.report()
        return {k: report[k] for k in ('status', 'issues', 'guards', 'result_type', 'effects')} | {'context': context}
    except Fault as exc:
        return {'status': 'invalid' if exc.kind == 'compile' else 'failed',
                'issues': [exc.view(code)], 'guards': [], 'context': 'parse_or_compile'}
    except Exception as exc:
        return {'status': 'failed', 'issues': [{'code': type(exc).__name__, 'message': str(exc)}], 'guards': []}


def legacy_check(code, alias=False):
    try:
        (parse_function_body if alias else parse)(code)
        return {'status': 'parsed'}
    except Exception as exc:
        return {'status': 'invalid', 'kind': type(exc).__name__, 'message': str(exc)}


def dependency_closure(deps, graph):
    seen, pending = set(), list(deps)
    while pending:
        key = pending.pop()
        if key in seen:
            continue
        seen.add(key)
        pending.extend(graph.get(key, []))
    return sorted(seen)


def audit(base):
    out = base / 'audit'
    out.mkdir(exist_ok=True)
    manifest = json.loads((base / 'manifest.json').read_text())
    for entry in manifest['files']:
        if sha((base / entry['path']).read_bytes()) != entry['sha256']:
            raise ValueError('Snapshot changed: ' + entry['path'])
    for entry in manifest['databases']:
        if sha((base / entry['path']).read_bytes()) != entry['sha256']:
            raise ValueError('Database snapshot changed: ' + entry['path'])
    # Compiler implementation is part of the evidence, not an unpinned moving target.
    for entry in manifest['files']:
        if entry['path'].startswith('backend/') and sha((ROOT / entry['path']).read_bytes()) != entry['sha256']:
            raise ValueError('Compiler changed since snapshot: ' + entry['path'])
    rows = rows_from_snapshot(base)
    contracts, definitions, availability, problems = frozen_registry(base, rows)
    registry = {key: Adapter(c, forbidden) for key, c in contracts.items()}
    dump(out / 'contracts.json', {'contracts': contracts, 'definitions': definitions,
                                'availability': availability, 'problems': problems,
                                'scope': 'full declared catalog; availability separate; no agent-specific permissions'})
    graphs = {1: {}, 2: {}}
    for row in rows:
        if row.get('alias') and row['origin'].endswith(':ibl_examples'):
            try:
                edition = source_edition(row['ibl_code'])
                graphs[edition]['fn:' + row['alias']] = [':'.join(h) for h in source_heads(row['ibl_code']) if h[0] != 'def']
            except ValueError:
                pass  # The row's edition diagnostic below remains authoritative.
    graphs[2] = {**graphs[1], **graphs[2]}
    for name, code in definitions.items():
        graphs[2]['fn:' + name] = [':'.join(h) for h in source_heads(code) if h[0] != 'def']
    cache, groups, summary = {}, {}, {'started_at': now(), 'sources': {}, 'registry_problems': problems,
                                     'semantic_review': 'not_started', 'applied': 0,
                                     'limitations': ['Static checks are not intent or runtime verification.',
                                                    'Nested strings and linked surfaces require separate review.',
                                                    'Full catalog; no live actor permissions or dynamic script-contract refinement.']}
    counts = defaultdict(lambda: {'total': 0, 'editions': Counter(), 'static_current': Counter(),
                                  'legacy_parse': Counter(), 'risks': Counter(), 'issues': Counter()})
    with (out / 'rows.jsonl').open('w') as stream:
        for index, row in enumerate(rows):
            code = row.get('ibl_code')
            valid_source = isinstance(code, str) and bool(code.strip())
            try:
                edition = source_edition(code, row.get('edition')) if valid_source else None
                edition_error = None if edition else 'missing_code'
            except Exception as exc:
                edition, edition_error = None, str(exc)
            context = 'function_body' if row.get('alias') and edition == 1 else 'program'
            group = sha(json.dumps([code, edition, context], ensure_ascii=False))
            if group not in cache:
                if not valid_source or edition_error:
                    check = {'status': 'failed', 'issues': [{'code': 'SOURCE_EDITION', 'message': edition_error}], 'guards': []}
                else:
                    check = static_check(code, registry, definitions, row.get('alias', ''), edition)
                old = legacy_check(code, context == 'function_body') if edition == 1 else {'status': 'not_applicable'}
                tags = risks(code) if valid_source else []
                deps = sorted({':'.join(h) for h in source_heads(code) if h[0] not in {'def', 'if', 'case', 'repeat', 'when'}}) if valid_source else []
                closure = dependency_closure(deps, graphs.get(edition, {}))
                local_functions = {'fn:' + h[1] for h in source_heads(code if valid_source else '') if h[0] == 'def'}
                cache[group] = {'edition': edition, 'edition_error': edition_error,
                                'current_check': check, 'legacy_parse': old, 'risk_tags': tags,
                                'direct_dependencies': deps, 'dependency_closure': closure,
                                'missing_functions': [d for d in closure if d.startswith('fn:') and d not in registry and d[3:] not in definitions and d not in local_functions],
                                'inactive_actions': [d for d in closure if availability.get(d, {}).get('active') is False]}
                groups[group] = {'group_id': group, 'code': code, 'context': context, **cache[group], 'targets': []}
            data = cache[group]
            target = {'origin': row['origin'], 'row_id': row['row_id'], 'intent': row.get('intent', ''),
                      'alias': row.get('alias', ''), 'always_on': row.get('always_on', 0)}
            groups[group]['targets'].append(target)
            record = {**target, 'role': row['role'], 'group_id': group,
                      'intent_sha256': sha(row.get('intent') or ''),
                      'code_sha256': sha(code if isinstance(code, str) else json.dumps(code)),
                      **data, 'decision': 'preserve_history' if row['role'] == 'history' else 'pending_semantic_review',
                      'semantic_review': 'not_started', 'execution_test': 'not_run', 'applied': False,
                      'masked': bool(row.get('masked'))}
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')
            c = counts[row['origin']]
            c['total'] += 1
            c['editions'][str(edition)] += 1
            c['static_current'][data['current_check']['status']] += 1
            c['legacy_parse'][data['legacy_parse']['status']] += 1
            c['risks'].update(data['risk_tags'])
            c['issues'].update({issue['code'] for issue in data['current_check']['issues']})
            if (index + 1) % 500 == 0:
                print(json.dumps({'processed': index + 1, 'total': len(rows), 'unique_contexts': len(cache)}), flush=True)
    with (out / 'groups.jsonl').open('w') as stream:
        for group in groups.values():
            stream.write(json.dumps(group, ensure_ascii=False) + '\n')
    summary.update({'ended_at': now(), 'total': len(rows), 'groups': len(groups), 'sources': dict(counts),
                    'manifest_sha256': sha((base / 'manifest.json').read_bytes()),
                    'ledger_sha256': sha((out / 'rows.jsonl').read_bytes()),
                    'auditor_sha256': sha(Path(__file__).read_bytes())})
    dump(out / 'summary.json', summary)
    print(json.dumps({'total': len(rows), 'groups': len(groups), 'summary': str(out / 'summary.json')}, ensure_ascii=False))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    args = parser.parse_args()
    audit(args.snapshot.resolve())
