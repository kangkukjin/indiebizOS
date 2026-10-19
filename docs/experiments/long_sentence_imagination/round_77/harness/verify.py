"""Verify frozen inputs and excerpt provenance without calling a model."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-19_77회차'
EVIDENCE = Path(__file__).resolve().parent.parent / 'evidence'


def main():
    checks = []

    def check(label, ok):
        checks.append({'check': label, 'ok': bool(ok)})

    for role in ('trainer', 'ai'):
        rows = json.loads((OUT / 'inputs' / role / 'sources.json').read_text())
        for row in rows:
            p = OUT / 'inputs' / role / row['file']
            check(f'input hash {role}/{row["id"]}',
                  hashlib.sha256(p.read_bytes()).hexdigest() == row['sha256'])
    old = json.loads((OUT / 'evidence/training_closed.json').read_text())['hashes']
    check('original training outputs unchanged', all(
        hashlib.sha256((OUT / p).read_bytes()).hexdigest() == h
        for p, h in old.items()))
    for phase in ('repair_base', 'repair_variant'):
        rows = json.loads((OUT / 'trainer' / phase / 'evidence.json').read_text())
        for row in rows:
            lines = (OUT / 'inputs/trainer' / row['file']).read_text().split('\n')
            selected = {int(n): v for n, v in
                        (line.split('\t', 1) for line in row['text'].splitlines())}
            label = f'{phase}/{row["id"]}'
            check(label + ' source lines exact',
                  all(lines[n - 1] == v for n, v in selected.items()))
            check(label + ' headings retained', all(
                i + 1 in selected for i, line in enumerate(lines)
                if line.startswith('#')))
            check(label + ' coverage counted',
                  len(selected) == row['selected_lines'] and
                  len(lines) == row['total_lines'] ==
                  row['selected_lines'] + row['omitted_lines'])
    check('variant reuses repaired base evidence',
          (OUT / 'trainer/repair_base/evidence.json').read_bytes() ==
          (OUT / 'trainer/repair_variant/evidence.json').read_bytes())
    (EVIDENCE / 'deterministic_checks.json').write_text(
        json.dumps(checks, ensure_ascii=False, indent=2))
    print(f'{sum(c["ok"] for c in checks)}/{len(checks)} checks passed')
    assert all(c['ok'] for c in checks)


if __name__ == '__main__':
    main()
