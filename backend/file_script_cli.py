"""Explicit local reproduction: python backend/file_script_cli.py RECORD_DIR.

Ordinary files are the inspection interface. This command never edits an old
receipt and never falls back to a masked input or stdout business value.
"""
import boot_paths  # noqa: F401
import argparse
import json

from file_script import reproduce, ScriptError
from script_workspace import authorize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record', help='private file-script execution directory')
    args = parser.parse_args()
    authorize()
    try:
        result = reproduce(args.record)
        print(json.dumps({'ok': result['ok'], 'record': result['record'],
                          'error': result['error']}, ensure_ascii=False))
        return 0 if result['ok'] else 1
    except ScriptError as exc:
        print(json.dumps({'ok': False, 'code': exc.code, 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
