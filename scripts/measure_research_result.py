#!/usr/bin/env python3
"""저장된 연구 결과의 같은 판본에 비용과 선택적 사람 검토를 연결한다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
import json
from research_measurement import measure


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--episode', type=int, required=True)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--task', required=True)
    parser.add_argument('--variant', required=True)
    parser.add_argument('--review', type=Path)
    parser.add_argument('--conditions', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    read = lambda path: json.loads(path.read_text()) if path else None
    result = measure(args.database, args.episode, args.artifact, task=args.task, variant=args.variant,
                     review=read(args.review), conditions=read(args.conditions))
    with args.out.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'artifact': result['artifact'], 'missing': result['missing']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
