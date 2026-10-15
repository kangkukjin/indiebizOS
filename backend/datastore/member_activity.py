"""회원 관리자 전용 작업 원장. 개인 기억/증류/주인 대화 원장과 공유하지 않는다."""
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def database(base):
    path = Path(base) / 'data/member_activity.sqlite3'
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    try:
        db.executescript('''
          CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY, member_id TEXT, device_id TEXT, name TEXT,
            local_task_id TEXT, request TEXT, started REAL, finished REAL,
            status TEXT, tokens INTEGER, models TEXT);
          CREATE INDEX IF NOT EXISTS member_tasks ON tasks(member_id, started DESC);
          CREATE TABLE IF NOT EXISTS actions (
            id INTEGER PRIMARY KEY, task_id TEXT, tool TEXT, started REAL,
            finished REAL, status TEXT);
          CREATE INDEX IF NOT EXISTS task_actions ON actions(task_id, id);
        ''')
        yield db
        db.commit()
    finally:
        db.close()


def begin(base, task_id, member_id, device_id, name, local_task_id, message):
    with database(base) as db:
        db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?,NULL,?,NULL,?)',
                   (task_id, member_id, device_id, name, local_task_id, message, time.time(), 'running', '[]'))


def finish(base, task_id, status, tokens, models):
    with database(base) as db:
        db.execute('UPDATE tasks SET finished=?,status=?,tokens=?,models=? WHERE id=?',
                   (time.time(), status, tokens, json.dumps(models, ensure_ascii=False), task_id))


def start_action(base, task_id, tool):
    with database(base) as db:
        return db.execute('INSERT INTO actions(task_id,tool,started,status) VALUES (?,?,?,?)',
                          (task_id, tool, time.time(), 'running')).lastrowid


def finish_action(base, action_id, status):
    with database(base) as db:
        db.execute('UPDATE actions SET finished=?,status=? WHERE id=?', (time.time(), status, action_id))


def recent(base, member_id, limit=50):
    with database(base) as db:
        rows = [dict(row) for row in db.execute(
            'SELECT * FROM tasks WHERE member_id=? ORDER BY started DESC LIMIT ?', (member_id, limit))]
        for row in rows:
            row['models'] = json.loads(row['models'])
            row['actions'] = [dict(a) for a in db.execute(
                'SELECT tool,started,finished,status FROM actions WHERE task_id=? ORDER BY id', (row['id'],))]
        return rows
