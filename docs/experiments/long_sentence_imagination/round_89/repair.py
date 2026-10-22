"""Repair replay transport: preserve baseline, change only destination paths."""
import datetime
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

import live

BASE = live.OUT
OUT = BASE.with_name(BASE.name + '_repair')
SOURCES = ['data/common_prompts/base_prompt_v6.md',
           'data/common_prompts/consciousness_prompt.md',
           'backend/cognition/final_evaluator.py', 'data/guides/ibl_composition.md']


def fingerprints():
    return {p: hashlib.sha256((live.ROOT / p).read_bytes()).hexdigest() for p in SOURCES}


def main():
    action = sys.argv[1]
    live.OUT = OUT
    live.PROJECT = 'L89_repair'
    if action == 'prepare':
        OUT.mkdir(exist_ok=False)
        for name in ('runs', 'ai', 'snapshots', 'reference'):
            (OUT / name).mkdir()
        shutil.copytree(BASE / 'reference/initial_inputs', OUT / 'inputs')
        shutil.copytree(BASE / 'reference/initial_inputs', OUT / 'reference/initial_inputs')
        shutil.copytree(BASE / 'staged', OUT / 'staged')
        (OUT / 'reference/requests.json').write_text(
            (BASE / 'reference/requests.json').read_text().replace(str(BASE), str(OUT)))
        now = datetime.datetime.now().astimezone()
        (OUT / 'start.json').write_text(json.dumps({
            'start': now.isoformat(), 'deadline': (now + datetime.timedelta(minutes=60)).isoformat(),
            'sources': fingerprints(), 'baseline': str(BASE)}, ensure_ascii=False, indent=2))
        print(OUT)
    elif action == 'continue':
        for n in range(1, 5):
            assert fingerprints() == json.loads((OUT / 'start.json').read_text())['sources']
            if not (OUT / 'runs' / f'T{n}_accepted.json').exists():
                sys.argv = [__file__, 'submit', str(n)]
                live.main()
            while not (OUT / 'runs' / f'T{n}_result.json').exists():
                sys.argv = [__file__, 'poll', str(n)]
                live.main()
                time.sleep(2)
            result = json.loads((OUT / 'runs' / f'T{n}_result.json').read_text())
            assert result['state'] == 'succeeded' and result['pending_children'] == 0
            print(f'T{n} complete', flush=True)
        sys.argv = [__file__, 'stop']
        live.main()
        (OUT / 'end.json').write_text(json.dumps({
            'end': datetime.datetime.now().astimezone().isoformat(),
            'sources': fingerprints()}, ensure_ascii=False, indent=2))
    elif action == 'audit':
        import audit
        audit.OUT = OUT
        audit.main()
    else:
        live.main()


if __name__ == '__main__':
    main()
