#!/usr/bin/env python3
"""미리 선언한 분야 골격과 실제 어휘의 일치·빈 가지·분포를 검사한다. 품질 점수는 아니다."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
import argparse  # noqa: E402
from collections import Counter  # noqa: E402
import json  # noqa: E402
import yaml  # noqa: E402
from knowledge_catalog import load_snapshot  # noqa: E402


def audit(root=ROOT):
    root = Path(root)
    snapshot = load_snapshot(root)
    outline = yaml.safe_load((root / 'data/knowledge_catalog/outline.yaml').read_text())
    dictionary = yaml.safe_load((root / 'data/knowledge_catalog/branches.yaml').read_text())
    declared = []
    domains = []
    errors = []
    for domain in outline['domains']:
        name = domain['name']
        if not domain.get('scope', '').strip():
            errors.append(f'분야 범위 없음: {name}')
        domains.append(name)
        declared.extend((name, b) for b in domain['branches'])
    for label, paths in [('분야', domains), ('가지', declared),
                         ('가지 사전', [tuple(b['path']) for b in dictionary['branches']])]:
        errors.extend(f'{label} 중복: {p}' for p, n in Counter(paths).items() if n > 1)
    actual = Counter(tuple(e.path[:2]) for e in snapshot.entries)
    planned = set(declared)
    defined = {tuple(b['path']) for b in dictionary['branches']}
    for label, extra in [('골격 밖 항목', set(actual) - planned),
                         ('비어 있는 계획 가지', planned - set(actual)),
                         ('골격 밖 가지 사전', defined - planned),
                         ('사전 없는 계획 가지', planned - defined)]:
        errors.extend(f'{label}: {"/".join(p)}' for p in sorted(extra))
    rows = []
    for domain in outline['domains']:
        name = domain['name']
        entries = [e for e in snapshot.entries if e.path[0] == name]
        rows.append({'domain': name, 'scope': domain['scope'], 'entries': len(entries),
                     'foundation_entries': sum(e.id.startswith('foundation.') for e in entries),
                     'kinds': dict(Counter(e.kind for e in entries)),
                     'branches': {b: actual[(name, b)] for b in domain['branches']}})
    return {'revision': snapshot.revision, 'kind': 'editorial_coverage_inventory',
            'quality_measured': False, 'entries': len(snapshot.entries),
            'domains': len(domains), 'branches': len(planned), 'errors': errors,
            'thin_branches': {'/'.join(p): n for p, n in actual.items() if n < 3}, 'results': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = audit()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(bool(report['errors']))


if __name__ == '__main__':
    raise SystemExit(main())
