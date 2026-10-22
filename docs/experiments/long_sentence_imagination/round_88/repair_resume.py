"""Checkpoint replay of the observed T5 boundary; never a claimed fresh T1–T4 run."""
import argparse
import datetime
import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = ROOT / 'outputs/long_sentence_imagination/2026-10-22_88회차_repair2'
OUT = SOURCE.with_name('2026-10-22_88회차_repair3')


def prepare():
    assert not OUT.exists()
    for name in ('inputs', 'reference', 'staged', 'runs', 'snapshots', 'trainer'):
        (OUT / name).mkdir(parents=True)
    shutil.copytree(SOURCE / 'snapshots/T4', OUT / 'ai')
    shutil.copytree(SOURCE / 'reference/initial_inputs', OUT / 'reference/initial_inputs')
    for path in (SOURCE / 'reference/initial_inputs').iterdir():
        shutil.copyfile(path, OUT / 'inputs' / path.name)
    for source, target in [('receipts.json', 'receipts.json'), ('records_v2.json', 'records.json'), ('old_memo.txt', 'old_memo.txt')]:
        shutil.copyfile(SOURCE / 'staged' / source, OUT / 'inputs' / target)
    shutil.copytree(SOURCE / 'staged/repair_variant', OUT / 'staged/repair_variant')
    requests = json.loads((SOURCE / 'reference/requests.json').read_text())['turns']
    (OUT / 'reference/requests.json').write_text(json.dumps({
        'turns': [requests[n].replace(str(SOURCE), str(OUT)) for n in (4, 5, 8)],
        'mapping': {'T1': 'original T5 checkpoint replay', 'T2': 'original T6', 'T3': 'new T9 variant'},
    }, ensure_ascii=False, indent=2))
    (OUT / 'reference/variant_expected.json').write_bytes((SOURCE / 'reference/variant_expected.json').read_bytes())
    now = datetime.datetime.now().astimezone()
    deadline = json.loads((SOURCE / 'start.json').read_text())['deadline']
    (OUT / 'start.json').write_text(json.dumps({'start': now.isoformat(), 'deadline': deadline,
        'synthetic': True, 'checkpoint_replay': True, 'budget': 'remaining original second-attempt budget; not extended'}, indent=2))
    manifest = {str(p.relative_to(OUT / 'ai')): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (OUT / 'ai').rglob('*') if p.is_file()}
    (OUT / 'runs/seeded_artifacts.json').write_text(json.dumps(manifest, indent=2))


def seed():
    sys.path.insert(0, str(ROOT / 'backend'))
    import boot_paths  # noqa: F401
    from conversation_db import ConversationDB
    source_db = ROOT / 'projects/L88_repair2/conversations.db'
    conn = sqlite3.connect(f'file:{source_db}?mode=ro', uri=True)
    rows = conn.execute("SELECT id,from_agent_id,content,message_time FROM messages WHERE contact_type='rehearsal' ORDER BY id LIMIT 8").fetchall()
    assert len(rows) == 8
    db = ConversationDB(str(ROOT / 'projects/L88_repair3/conversations.db'))
    user = db.get_or_create_agent('user', 'human')
    agent = db.get_or_create_agent('long_project', 'ai_agent')
    with db.get_connection() as target:
        assert target.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 0
    evidence = []
    for source_id, sender, content, timestamp in rows:
        content = content.replace(str(SOURCE), str(OUT))
        role = 'user' if sender == 1 else 'assistant'
        mid = db.save_message(user if role == 'user' else agent, agent if role == 'user' else user,
                              content, contact_type='rehearsal')
        with db.get_connection() as target:
            target.execute('UPDATE messages SET message_time=? WHERE id=?', (timestamp, mid))
        evidence.append({'source_message': source_id, 'target_message': mid, 'role': role,
                         'sha256': hashlib.sha256(content.encode()).hexdigest()})
    (OUT / 'runs/seeded_history.json').write_text(json.dumps({'source': str(source_db),
        'target': db.db_path, 'rows': evidence, 'model_calls_for_seed': 0}, indent=2))
    history = db.get_history_for_ai(agent, user, rehearsal=True)
    (OUT / 'runs/history_at_resume.json').write_text(json.dumps(history, ensure_ascii=False, indent=2))
    print('Seeded 8 observed messages; source artifacts copied byte-for-byte; replay starts at original T5.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'seed'))
    args = parser.parse_args()
    {'prepare': prepare, 'seed': seed}[args.action]()
