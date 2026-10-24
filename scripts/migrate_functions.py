#!/usr/bin/env python3
"""Audit or explicitly migrate workflow/idiom definitions to the common catalog."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import boot_paths

import argparse
import json
from function_migration import migrate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--resolve', action='append', default=[], metavar='EDITION:NAME=SOURCE_KEY')
    args = parser.parse_args()
    import os
    os.environ["INDIEBIZ_BASE_PATH"] = str(args.root.resolve())
    resolutions = dict(item.split('=', 1) for item in args.resolve)
    result = migrate(args.root, apply=args.apply, resolutions=resolutions)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get('conflicts') else 0


if __name__ == '__main__':
    raise SystemExit(main())
