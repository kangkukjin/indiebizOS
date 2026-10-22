"""Replay the fixed T9 variant from observed T6, excluding the failed T9 output."""
import argparse
import datetime
import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / 'outputs/long_sentence_imagination/2026-10-22_88회차_repair3'
OUT = SOURCE.with_name('2026-10-22_88회차_repair4')


def prepare():
    assert not OUT.exists()
    for name in ('runs', 'reference', 'snapshots', 'staged', 'trainer'):
        (OUT / name).mkdir(parents=True)
    shutil.copytree(SOURCE / 'snapshots/T2', OUT / 'ai')
    shutil.copytree(SOURCE / 'inputs', OUT / 'inputs')
    req = json.loads((SOURCE / 'reference/requests.json').read_text())['turns'][2]
    (OUT / 'reference/requests.json').write_text(json.dumps({'turns': [req.replace(str(SOURCE), str(OUT))]}, ensure_ascii=False))
    shutil.copyfile(SOURCE / 'reference/variant_expected.json', OUT / 'reference/variant_expected.json')
    start = json.loads((SOURCE / 'start.json').read_text())
    start.update(start=datetime.datetime.now().astimezone().isoformat(), checkpoint='observed T6 before T9')
    (OUT / 'start.json').write_text(json.dumps(start, indent=2))
    sources = json.loads((SOURCE / 'runs/repair_source_hashes.json').read_text())
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources}
    (OUT / 'runs/repair_source_hashes.json').write_text(json.dumps(hashes, indent=2))
    hashes = {str(p.relative_to(OUT / 'ai')): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (OUT / 'ai').rglob('*') if p.is_file()}
    (OUT / 'runs/seeded_artifacts.json').write_text(json.dumps(hashes, indent=2))


def seed():
    sys.path.insert(0, str(ROOT / 'backend'))
    import boot_paths  # noqa: F401
    from conversation_db import ConversationDB
    source_db = ROOT / 'projects/L88_repair3/conversations.db'
    source = sqlite3.connect(f'file:{source_db}?mode=ro', uri=True)
    rows = source.execute("SELECT id,from_agent_id,content,message_time FROM messages WHERE contact_type='rehearsal' ORDER BY id LIMIT 12").fetchall()
    assert len(rows) == 12
    db = ConversationDB(str(ROOT / 'projects/L88_repair4/conversations.db'))
    user = db.get_or_create_agent('user', 'human')
    agent = db.get_or_create_agent('long_project', 'ai_agent')
    with db.get_connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 0
    evidence = []
    for sid, sender, content, timestamp in rows:
        role = 'user' if sender == 1 else 'assistant'
        content = content.replace(str(SOURCE), str(OUT))
        mid = db.save_message(user if role == 'user' else agent, agent if role == 'user' else user,
                              content, contact_type='rehearsal')
        with db.get_connection() as conn:
            conn.execute('UPDATE messages SET message_time=? WHERE id=?', (timestamp, mid))
        evidence.append({'source_message': sid, 'target_message': mid, 'role': role,
                         'sha256': hashlib.sha256(content.encode()).hexdigest()})
    (OUT / 'runs/seeded_history.json').write_text(json.dumps({'source': str(source_db), 'rows': evidence, 'model_calls_for_seed': 0}, indent=2))
    (OUT / 'runs/history_at_resume.json').write_text(json.dumps(db.get_history_for_ai(agent, user, rehearsal=True), ensure_ascii=False, indent=2))
    print('Seeded 12 observed messages and 54 artifacts; failed T9 excluded.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'seed'))
    {'prepare': prepare, 'seed': seed}[parser.parse_args().action]()
