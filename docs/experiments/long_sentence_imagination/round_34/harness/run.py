"""Reproduce one trainer run over generated inputs; HTTP transport only."""
import argparse
import json
import time
import urllib.request
from pathlib import Path

from prepare import OUT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('base', 'variant', 'new'))
    parser.add_argument('--draft', default='main_v1.ibl')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--project-id', default='수동모드')
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1] / 'drafts' / args.draft
    request = {'code': source.read_text(), 'origin': 'training',
               'project_id': args.project_id, 'check': args.check,
               'budget': {'steps': 1000000, 'rows': 100000},
               'inputs': {'source': str(OUT / 'source' / args.mode),
                          'out': str(OUT / 'trainer' / (args.mode + '_replay'))}}
    started = time.time()
    req = urllib.request.Request('http://127.0.0.1:8765/ibl/execute',
                                 data=json.dumps(request, ensure_ascii=False).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=300) as response:
        result = json.load(response)
    record = {'request': request, 'wall_s': time.time() - started, 'response': result}
    destination = OUT / 'runs' / (args.mode + '_' + source.stem + ('_check' if args.check else '_replay') + '.json')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(record, ensure_ascii=False))
    print(json.dumps({k: result.get(k) for k in ('success', 'ok', 'error', 'value', 'resume')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
