"""Registered checkpoint/rewind adapter. Never accepts arbitrary database paths."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import boot_paths
from conversation_sessions import Binding, SessionStore
import conversation_rewind as rewind


def main(args):
    raw = json.loads(os.environ.get('INDIEBIZ_CONVERSATION_BINDING', 'null'))
    if not raw: raise ValueError('대화복구는 소속 대화가 있는 턴에서 실행하세요')
    binding = Binding(**raw)
    table = 'messages' if binding.owner.startswith('pair:') else 'conversations'
    store = SessionStore(binding.db_path, table, binding.owner, recover_turns=False)
    op = args.get('op', 'list')
    if op == 'list': return rewind.list_checkpoints(store, binding.session_id)
    if op == 'preview': return rewind.preview(store, binding.session_id, args['checkpoint'], args.get('mode', 'both'))
    if op == 'apply': return rewind.submit(store, binding.session_id, args['preview'])
    if op == 'status': return rewind.public(rewind.get(store, binding.session_id, args['rewind']))
    raise ValueError('op: list/preview/apply/status')


if __name__ == '__main__':
    try:
        print(json.dumps({'success': True, 'items': [], **main(json.load(sys.stdin))}, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'success': False, 'error': str(exc)}, ensure_ascii=False))
        sys.exit(1)
