"""Registered process start adapter; stdin is a JSON input object."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import boot_paths
from conversation_sessions import Binding, scope, effect_scope
from process_sessions import start


def main(args):
    binding = json.loads(os.environ.get('INDIEBIZ_CONVERSATION_BINDING', 'null'))
    origin = json.loads(os.environ.get('INDIEBIZ_EFFECT_BINDING', 'null'))
    with scope(Binding(**binding) if binding else None), effect_scope(Binding(**origin) if origin else None):
        return {**start(args['command'], args.get('cwd') or os.getcwd(),
                        io=args.get('io', 'pipe'), request_id=args.get('request_id'),
                        yield_ms=args.get('yield_ms', 1000), lifetime=args.get('lifetime', 'task')), 'items': []}


if __name__ == '__main__':
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'success': False, 'error': str(exc)}, ensure_ascii=False))
        sys.exit(1)
