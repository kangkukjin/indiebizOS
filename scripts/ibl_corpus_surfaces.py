"""Inventory linked teaching/execution surfaces without treating snippets as programs."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
import ast
import json
import re
from collections import Counter

import yaml
from ibl_corpus_snapshot import connect, dump, sha
from ibl_scanner import source_heads


def contains_ibl(value):
    return '#!ibl' in value or bool(source_heads(value))


def structured_strings(value, pointer='$', inherited_edition=None):
    if isinstance(value, dict):
        edition = value.get('edition', inherited_edition)
        for key, child in value.items():
            yield from structured_strings(child, pointer + '/' + str(key), edition)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from structured_strings(child, pointer + '/' + str(i), inherited_edition)
    elif isinstance(value, str) and contains_ibl(value):
        yield {'location': pointer, 'code': value, 'edition_context': inherited_edition,
               'kind': 'structured_string', 'review': 'program_or_example_context_required'}


def snippets(path):
    if path.suffix not in {'.json', '.yaml', '.yml', '.py', '.ibl', '.md'}:
        return
    text = path.read_text()
    if path.suffix in {'.json', '.yaml', '.yml'}:
        data = json.loads(text) if path.suffix == '.json' else yaml.safe_load(text)
        yield from structured_strings(data)
    elif path.suffix == '.py':
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and contains_ibl(node.value):
                yield {'location': f'line:{node.lineno}:col:{node.col_offset}', 'code': node.value,
                       'kind': 'python_string', 'review': 'dynamic_construction_or_literal_context_required'}
    elif path.suffix == '.ibl':
        yield {'location': 'file', 'code': text, 'kind': 'ibl_file', 'review': 'program'}
    elif path.suffix == '.md':
        # Preserve source offsets. Fenced examples and prose snippets are not equivalent.
        spans = []
        for m in re.finditer(r'(?m)^```([^\n]*)\n([\s\S]*?)^```\s*$', text):
            spans.append(m.span())
            if contains_ibl(m[2]):
                yield {'location': f'offset:{m.start(2)}', 'code': m[2], 'kind': 'markdown_fence',
                       'language': m[1], 'review': 'example_or_fragment_context_required'}
        for m in re.finditer(r'`([^`\n]+)`', text):
            if not any(start <= m.start() < end for start, end in spans) and contains_ibl(m[1]):
                yield {'location': f'offset:{m.start(1)}', 'code': m[1], 'kind': 'markdown_inline',
                       'review': 'fragment_not_standalone'}


def inventory(base):
    manifest = json.loads((base / 'manifest.json').read_text())
    rows, files, errors = [], [], []
    for entry in manifest['files']:
        name = entry['path']
        if not name.startswith('data/') or name.startswith(('data/training/', 'data/models/')):
            continue
        p = base / name
        if sha(p.read_bytes()) != entry['sha256']:
            raise ValueError('Snapshot changed: ' + name)
        try:
            found = list(snippets(p))
            files.append({'path': name, 'sha256': entry['sha256'], 'candidates': len(found),
                          'status': 'extracted' if p.suffix in {'.json', '.yaml', '.yml', '.py', '.ibl', '.md'} else 'non_text_asset'})
            rows.extend({'origin': name, 'code_sha256': sha(r['code']), **r} for r in found)
        except Exception as exc:
            errors.append({'path': name, 'kind': type(exc).__name__, 'message': str(exc)})
    out = base / 'audit'
    out.mkdir(exist_ok=True)
    with (out / 'surface_candidates.jsonl').open('w') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    report = {'files': files, 'errors': errors, 'candidates': len(rows),
              'kinds': dict(Counter(r['kind'] for r in rows)),
              'status': 'inventory_only; candidate extraction does not establish executable context',
              'scope': 'files in snapshot manifest; imports, external project apps and runtime exports not recursively resolved'}
    dump(out / 'surfaces.json', report)
    return report


def drift(base, live=ROOT):
    """Compare identities, not mutable success statistics; no source writes."""
    from audit_ibl_corpus_v2 import rows_from_snapshot
    def index(root):
        return {(r['origin'], str(r['row_id'])):
                sha(json.dumps([r.get('intent'), r.get('ibl_code'), r.get('edition'), r.get('alias')], ensure_ascii=False))
                for r in rows_from_snapshot(root)}
    before, after = index(base), index(live)
    changes = {kind: [] for kind in ('added', 'removed', 'changed')}
    for key in sorted(before.keys() | after.keys()):
        kind = 'added' if key not in before else 'removed' if key not in after else 'changed' if before[key] != after[key] else None
        if kind:
            changes[kind].append({'origin': key[0], 'row_id': key[1]})
    manifest = json.loads((base / 'manifest.json').read_text())
    changes['surface_files_changed'] = [e['path'] for e in manifest['files']
                                        if not (live / e['path']).exists() or sha((live / e['path']).read_bytes()) != e['sha256']]
    changes['surface_candidate_changes'] = []
    for name in changes['surface_files_changed']:
        if not name.startswith('data/'):
            continue
        try:
            left = Counter((r['kind'], sha(r['code'])) for r in snippets(base / name))
            right = Counter((r['kind'], sha(r['code'])) for r in snippets(live / name)) if (live / name).exists() else Counter()
            changes['surface_candidate_changes'].append({'path': name,
                                                        'removed': sum((left - right).values()),
                                                        'added': sum((right - left).values()),
                                                        'context_review': 'required_even_when_code_unchanged'})
        except Exception as exc:
            changes['surface_candidate_changes'].append({'path': name, 'error': type(exc).__name__})
    dump(base / 'audit/drift.json', changes)
    return {k: len(v) for k, v in changes.items()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--drift', action='store_true')
    args = parser.parse_args()
    if args.drift:
        print(json.dumps(drift(args.snapshot.resolve())))
    else:
        result = inventory(args.snapshot.resolve())
        print(json.dumps({k: result[k] for k in ('candidates', 'kinds', 'errors')}, ensure_ascii=False))
