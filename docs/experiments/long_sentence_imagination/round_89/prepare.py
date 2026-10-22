"""Build complete IBL source/requests, without computing business results."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-22_89회차'
parser = argparse.ArgumentParser()
parser.add_argument('label')
parser.add_argument('--phase', type=int, default=1)
parser.add_argument('--sequential', action='store_true')
parser.add_argument('--previous', default='')
parser.add_argument('--execute', action='store_true')
parser.add_argument('--version', default='0')
args = parser.parse_args()
if args.execute:
    result = json.loads((OUT / 'runs' / f'{args.label}_check.json').read_text())['response']
    assert result.get('ok'), result
    body = result['execute_args']
    label = args.label
else:
    code = (HERE / f'functions_v{args.version}.ibl').read_text() + '\n' + (HERE / 'main_v0.ibl').read_text()
    (HERE / f'complete_v{args.version}.ibl').write_text(code)
    destination = OUT / 'trainer' / args.label
    destination.mkdir(exist_ok=True)
    source = OUT / 'reference/initial_inputs'
    if args.phase >= 3:
        source = OUT / 'staged' / f'T{args.phase}'
    body = {'code': code, 'check': True, 'budget': {'steps': 1000000, 'rows': 100000},
        'inputs': {'source': str(source), 'output': str(destination), 'phase': f'T{args.phase}',
            'parallel': not args.sequential, 'previous': args.previous,
            'reload_a': args.phase != 2, 'reload_policy': args.phase in (1, 2),
            'expected_ids': [f'D{i:04d}' for i in range(1, 1801)],
            'policy': {'budget': 6000000 if args.phase == 1 else 3200000, 'deadline': '2026-11-20',
                'cancel_optional': args.phase > 1, 'external_saas': args.phase == 1, 'face': args.phase == 1}}}
    label = args.label + '_check'
(OUT / 'runs' / f'{label}_request.json').write_text(json.dumps(body, ensure_ascii=False))
print(label)
