#!/usr/bin/env python3
"""Audit stored semantic interfaces; --apply publishes eligible new revisions."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import boot_paths  # noqa: E402,F401
import argparse
import json
from function_revalidation import revalidate


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='publish after CAS/source validation; never execute tools')
    args = parser.parse_args()
    print(json.dumps(revalidate(apply=args.apply), ensure_ascii=False, indent=2))
