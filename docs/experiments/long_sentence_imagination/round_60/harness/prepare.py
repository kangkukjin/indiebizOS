"""Recreate requests from preserved IBL; no solver logic or live submission."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
DOC = ROOT / 'docs/experiments/long_sentence_imagination/round_60'
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-12_60회차'


def main():
    (OUT / 'runs').mkdir(parents=True, exist_ok=True)
    for version, stage, variants in (
        ('main_v2.ibl', 'repaired', ('base', 'flaky')),
        ('main_v5.ibl', 'final', ('base', 'flaky', 'inline', 'empty')),
    ):
        for variant in variants:
            request = {'code': (DOC / 'drafts' / version).read_text(),
                       'origin': 'training', 'project_id': '컨텐츠',
                       'inputs': {'base': f'http://127.0.0.1:8874/{stage}/{variant}/list',
                                  'out': str(OUT / stage / variant)}}
            target = OUT / 'runs' / f'{variant}_{stage}_request.json'
            target.write_text(json.dumps(request, ensure_ascii=False, indent=2))
    print(OUT / 'runs')


if __name__ == '__main__':
    main()
