"""Export current-edition training inputs without executing or training a model."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
import hashlib
import json
import sqlite3

from corpus_policy import current_examples


def export(root, destination):
    destination.mkdir(parents=True, exist_ok=True)
    training = destination / 'training'
    training.mkdir(exist_ok=True)
    # Refuse mixing a new qualified export with stale files from an earlier run.
    if list(training.glob('*.json')) or (destination / 'ibl_examples_export.json').exists():
        raise ValueError('Use a fresh export directory')
    with sqlite3.connect((root / 'data/ibl_usage.db').as_uri() + '?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute(
            'SELECT id,intent,ibl_code,nodes,category,alias,provenance FROM ibl_examples ORDER BY id')]
    sources = [('data/ibl_usage.db:ibl_examples', rows, destination / 'ibl_examples_export.json')]
    for path in sorted((root / 'data/training').glob('*.json')):
        sources.append((str(path.relative_to(root)), json.loads(path.read_text()), training / path.name))
    report = {'policy': 'current-edition/1', 'semantic_verification_claimed': False, 'sources': []}
    for origin, rows, path in sources:
        if not isinstance(rows, list):
            raise ValueError(f'Expected row list: {origin}')
        accepted, rejected = current_examples(rows)
        content = json.dumps(accepted, ensure_ascii=False, indent=2) + '\n'
        path.write_text(content)
        report['sources'].append({'origin': origin, 'total': len(rows), 'accepted': len(accepted),
                                  'excluded': rejected, 'sha256': hashlib.sha256(content.encode()).hexdigest()})
    (destination / 'corpus_qualification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    print(json.dumps(export(ROOT, args.destination), ensure_ascii=False, indent=2))
