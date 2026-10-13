"""연구 프로젝트 정본: 대화·자료 판본·획득 원장. 색인은 정본이 아니다."""
import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from conversation_db import ConversationDB
from research_lifecycle import project_lock


def identifier():
    return uuid.uuid4().hex


def now():
    return datetime.now(timezone.utc).isoformat()


def json_text(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class ResearchConflict(ValueError):
    pass


class ResearchStore:
    def __init__(self, project_path, project_uid=None):
        self.path = Path(project_path).resolve()
        self.root = self.path / 'research'
        self.db_path = self.path / 'conversations.db'
        if project_uid is None and not self.root.is_dir():
            raise ValueError('연구 프로젝트가 아닙니다')
        self.conversations = ConversationDB(str(self.db_path))
        self.root.mkdir(exist_ok=True)
        with self.connect() as db:
            from research_questions import SCHEMA as QUESTIONS_SCHEMA
            db.executescript(SCHEMA + QUESTIONS_SCHEMA)
            if project_uid:
                db.execute('INSERT OR IGNORE INTO research_project(uid) VALUES (?)', (project_uid,))
            row = db.execute('SELECT * FROM research_project').fetchone()
            if not row or (project_uid and row['uid'] != project_uid):
                raise ValueError('연구 프로젝트 신원이 일치하지 않습니다')
            self.uid = row['uid']
            self.epoch = row['epoch']
            if 'enabled' not in {r[1] for r in db.execute('PRAGMA table_info(research_project)')}:
                db.execute('ALTER TABLE research_project ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1')
            columns = {r[1] for r in db.execute('PRAGMA table_info(messages)')}
            for name, declaration in [('thread_id', 'TEXT'), ('research_run', 'TEXT'),
                                      ('research_role', 'TEXT'), ('research_status', "TEXT DEFAULT 'complete'"),
                                      ('research_attachments', "TEXT NOT NULL DEFAULT '[]'")]:
                if name not in columns:
                    db.execute(f'ALTER TABLE messages ADD COLUMN {name} {declaration}')
            if 'extraction_revision' not in {r[1] for r in db.execute('PRAGMA table_info(research_citations)')}:
                db.execute('ALTER TABLE research_citations ADD COLUMN extraction_revision INTEGER NOT NULL DEFAULT 1')
            if 'result_blob' not in {r[1] for r in db.execute('PRAGMA table_info(research_captures)')}:
                db.execute("ALTER TABLE research_captures ADD COLUMN result_blob TEXT")
            # 옛 공용 수동 자료는 버리지 않고 별도 대화에 보존한다. 자동 수집 자료는 원래 thread_id 유지.
            if not db.execute("SELECT 1 FROM research_migrations WHERE name='thread-libraries'").fetchone():
                if db.execute('SELECT 1 FROM research_captures WHERE thread_id IS NULL').fetchone():
                    legacy = identifier()
                    db.execute('INSERT INTO research_threads(id,title,created_at,updated_at) VALUES (?,?,?,?)',
                               (legacy, '이전 공용 자료', now(), now()))
                    db.execute('UPDATE research_captures SET thread_id=? WHERE thread_id IS NULL', (legacy,))
                db.execute("INSERT INTO research_migrations(name) VALUES ('thread-libraries')")
            db.execute('CREATE INDEX IF NOT EXISTS messages_thread ON messages(thread_id,id)')
            db.commit()

    @contextmanager
    def connect(self, write=False):
        with project_lock(self.path):
            if not self.root.is_dir():
                raise ResearchConflict('연구 프로젝트가 이동되거나 삭제됐습니다')
            with self._connection(write) as db:
                yield db

    @contextmanager
    def _connection(self, write=False):
        db = sqlite3.connect(str(self.db_path), timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA foreign_keys=ON')
        try:
            if write:
                db.execute('BEGIN IMMEDIATE')
            yield db
            if write:
                db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def check_epoch(self, db):
        row = db.execute('SELECT uid,epoch,enabled FROM research_project').fetchone()
        if not row or row['uid'] != self.uid or row['epoch'] != self.epoch or not row['enabled']:
            raise ResearchConflict('프로젝트가 이동·삭제되어 실행 문맥이 만료됐습니다')

    def event(self, db, kind, payload, thread=None, run=None):
        db.execute('INSERT INTO research_events(kind,payload,thread_id,run_id,created_at) VALUES (?,?,?,?,?)',
                   (kind, json_text(payload), thread, run, now()))

    def put_blob(self, data):
        with project_lock(self.path), self.connect() as db:
            self.check_epoch(db)
            return self._put_blob(data)

    def _put_blob(self, data):
        if isinstance(data, str):
            data = data.encode('utf-8')
        digest = hashlib.sha256(data).hexdigest()
        dest = self.root / 'objects' / digest[:2] / digest
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            if hashlib.sha256(dest.read_bytes()).hexdigest() != digest:
                raise IOError('저장 원문의 지문이 일치하지 않습니다')
            return digest
        staging = self.root / 'staging'
        staging.mkdir(exist_ok=True)
        tmp = staging / identifier()
        try:
            with tmp.open('xb') as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, dest)
            if hasattr(os, "O_DIRECTORY"):
                fd = os.open(dest.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        finally:
            tmp.unlink(missing_ok=True)
        return digest

    def blob(self, digest):
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('잘못된 원문 참조')
        data = (self.root / 'objects' / digest[:2] / digest).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise IOError('저장 원문 손상')
        return data

    def material_path(self, digest, mime):
        """확장자를 요구하는 기존 이미지/문서 도구용 사본. 정본 blob에서 재생성 가능하다."""
        import mimetypes
        suffix = mimetypes.guess_extension(mime) or '.bin'
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('잘못된 원문 참조')
        path = self.root / 'files' / (digest + suffix)
        with project_lock(self.path):
            if not path.exists():
                data = self.blob(digest)
                path.parent.mkdir(exist_ok=True)
                tmp = path.with_name(identifier())
                try:
                    tmp.write_bytes(data)
                    os.replace(tmp, path)
                finally:
                    tmp.unlink(missing_ok=True)
        return str(path)

    def create_thread(self, title, agent='', mode='research'):
        if not str(title).strip() or mode not in {'research', 'library'}:
            raise ValueError('대화 제목과 조사 모드를 확인하세요')
        tid = identifier()
        with self.connect(True) as db:
            self.check_epoch(db)
            db.execute('INSERT INTO research_threads(id,title,agent,mode,created_at,updated_at) VALUES (?,?,?,?,?,?)',
                       (tid, str(title).strip(), agent, mode, now(), now()))
            self.event(db, 'thread.created', {'thread_ref': tid}, tid)
        return self.thread(tid)

    def thread(self, tid, db=None):
        if db is None:
            with self.connect() as conn:
                return self.thread(tid, conn)
        row = db.execute('SELECT * FROM research_threads WHERE id=?', (tid,)).fetchone()
        if not row:
            raise ValueError('이 프로젝트에 대화가 없습니다')
        return {**dict(row), 'thread_ref': row['id'], 'project_ref': self.uid}

    def threads(self, archived=False, query='', offset=0, limit=100):
        with self.connect() as db:
            rows = db.execute('SELECT * FROM research_threads WHERE archived=? AND trashed=0 AND title LIKE ? '
                              'ORDER BY updated_at DESC,id LIMIT ? OFFSET ?',
                              (int(archived), '%' + query + '%', limit + 1, offset)).fetchall()
        return {'items': [{**dict(r), 'thread_ref': r['id'], 'project_ref': self.uid,
                           'mode_label': '자료 + 추가 조사' if r['mode'] == 'research' else '저장 자료만',
                           'updated_label': r['updated_at'][:16].replace('T', ' ')} for r in rows[:limit]],
                'next_cursor': str(offset + limit) if len(rows) > limit else None,
                'pages': [{'title': '다음 대화 목록', 'cursor': str(offset + limit), 'query': query, 'archived': archived}] if len(rows) > limit else []}

    def update_thread(self, tid, expected=None, *, notes_origin='user', **changes):
        allowed = {'title', 'agent', 'mode', 'notes', 'archived', 'trashed'}
        if not changes or set(changes) - allowed:
            raise ValueError('변경할 대화 필드를 확인하세요')
        if 'mode' in changes and changes['mode'] not in {'research', 'library'}:
            raise ValueError('지원하지 않는 조사 모드')
        if 'title' in changes and not str(changes['title']).strip():
            raise ValueError('대화 제목이 필요합니다')
        with self.connect(True) as db:
            self.check_epoch(db)
            row = self.thread(tid, db)
            if expected is not None and row['revision'] != expected:
                raise ResearchConflict('다른 창에서 변경했습니다. 다시 읽어 주세요')
            if row['active_run'] and any(k in changes for k in ('mode', 'agent', 'trashed')):
                raise ResearchConflict('진행 중인 대화를 먼저 중단하세요')
            if 'notes' in changes:
                if notes_origin not in {'user', 'agent'}:
                    raise ValueError('잘못된 문서 작성자')
                db.execute('INSERT INTO research_notes(thread_id,body,origin,created_at) VALUES (?,?,?,?)',
                           (tid, str(changes['notes']), notes_origin, now()))
            fields = ','.join(k + '=?' for k in changes)
            db.execute(f'UPDATE research_threads SET {fields},revision=revision+1,updated_at=? WHERE id=?',
                       (*changes.values(), now(), tid))
        return self.thread(tid)

    def messages(self, tid, before=None, limit=50, query=''):
        self.thread(tid)
        with self.connect() as db:
            rows = db.execute('SELECT id,content,message_time,research_role AS role,research_status AS status,'
                              'research_run AS run_id,research_attachments FROM messages WHERE thread_id=? AND id<? AND content LIKE ? '
                              'ORDER BY id DESC LIMIT ?', (tid, before or 9223372036854775807,
                                                         '%' + query + '%', limit + 1)).fetchall()
            result = []
            for row in reversed(rows[:limit]):
                item = dict(row)
                # message_time 은 SQLite CURRENT_TIMESTAMP(UTC, 표식 없음). 일반 대화와 같은
                # 계약으로 읽기 경계에서 시간대를 명시한다 — 그대로 보내면 브라우저가 현지 시각으로 오해.
                item['message_time'] = ConversationDB.message_timestamp(item['message_time'])
                item['attachments'] = json.loads(item.pop('research_attachments') or '[]')
                # 실행 중 추가 지시는 assistant 초안보다 나중 ID로 저장된다.
                # 최종 응답을 그 실행의 마지막 사용자 입력 뒤에 배치한다.
                last_input = db.execute("SELECT MAX(id) FROM messages WHERE thread_id=? AND research_run=? AND research_role='user'",
                                        (tid, row['run_id'])).fetchone()[0]
                item['display_order'] = max(row['id'], (last_input or 0) + 0.5) if row['role'] == 'assistant' else row['id']
                item['mine'] = row['role'] == 'user'
                item['citations'] = [dict(r) for r in db.execute(
                    'SELECT * FROM research_citations WHERE message_id=?', (row['id'],))]
                result.append(item)
        result.sort(key=lambda item: item['display_order'])
        return {'items': result, 'next_cursor': str(rows[limit - 1]['id']) if len(rows) > limit else None,
                'pages': [{'title': '이전 대화 읽기', 'thread_ref': tid, 'cursor': str(rows[limit - 1]['id'])}] if len(rows) > limit else []}

    def begin_run(self, tid, message, request_id, attachments=()):
        if (not message.strip() and not attachments) or not request_id:
            raise ValueError('메시지와 요청 신원이 필요합니다')
        with self.connect(True) as db:
            self.check_epoch(db)
            db.execute("INSERT OR IGNORE INTO agents(name,type) VALUES ('user','human'),('연구 도우미','ai_agent')")
            user = db.execute("SELECT id FROM agents WHERE name='user'").fetchone()[0]
            agent = db.execute("SELECT id FROM agents WHERE name='연구 도우미'").fetchone()[0]
            row = self.thread(tid, db)
            old = db.execute('SELECT task_id,original_request FROM tasks WHERE requester_channel=?',
                             ('research:' + tid + ':' + request_id,)).fetchone()
            if old:
                prior = db.execute("SELECT research_attachments FROM messages WHERE research_run=? AND research_role='user'", (old['task_id'],)).fetchone()
                if old['original_request'] != message or json.loads(prior[0] or '[]') != list(attachments):
                    raise ResearchConflict('같은 요청 신원으로 다른 메시지를 보낼 수 없습니다')
                return old['task_id'], False
            if row['active_run'] or row['trashed'] or row['archived']:
                raise ResearchConflict('진행 중이거나 보관한 대화입니다. 중단 또는 보관 해제 후 보내세요')
            run = 'research_' + identifier()
            db.execute('INSERT INTO tasks(task_id,requester,requester_channel,original_request,delegated_to,status) '
                       'VALUES (?,?,?,?,?,?)', (run, 'user@gui', 'research:' + tid + ':' + request_id,
                                               message, row['agent'], 'running'))
            db.execute("INSERT INTO messages(from_agent_id,to_agent_id,content,contact_type,thread_id,research_run,research_role,research_attachments) "
                       "VALUES (?,?,?,'research',?,?,'user',?)", (user, agent, message, tid, run, json_text(list(attachments))))
            db.execute("INSERT INTO messages(from_agent_id,to_agent_id,content,contact_type,thread_id,research_run,research_role,research_status) "
                       "VALUES (?,?,'','research',?,?,'assistant','running')", (agent, user, tid, run))
            db.execute('UPDATE research_threads SET active_run=?,updated_at=? WHERE id=?', (run, now(), tid))
            self.event(db, 'run.started', {}, tid, run)
        return run, True

    def write_response(self, tid, run, text, state='running', citations=()):
        with self.connect(True) as db:
            self.check_epoch(db)
            row = self.thread(tid, db)
            if row['active_run'] != run:
                raise ResearchConflict('실행 신원이 만료됐습니다')
            db.execute("UPDATE messages SET content=?,research_status=? WHERE thread_id=? AND research_run=? AND research_role='assistant'",
                       (text, state, tid, run))
            if state != 'running':
                mid = db.execute("SELECT id FROM messages WHERE research_run=? AND research_role='assistant'", (run,)).fetchone()[0]
                for citation in citations:
                    db.execute('INSERT OR IGNORE INTO research_citations(message_id,version_id,locator,quote,extraction_revision) VALUES (?,?,?,?,?)',
                               (mid, citation['version_id'], citation['locator'], citation.get('quote', ''), citation.get('extraction_revision', 1)))
                db.execute('UPDATE tasks SET status=?,result=?,completed_at=? WHERE task_id=?', (state, text, now(), run))
                db.execute('UPDATE research_threads SET active_run=NULL,updated_at=? WHERE id=?', (now(), tid))
            self.event(db, 'response.' + state, {'chars': len(text)}, tid, run)

    def recover_runs(self, live):
        with self.connect(True) as db:
            rows = db.execute('SELECT id,active_run FROM research_threads WHERE active_run IS NOT NULL').fetchall()
            for row in rows:
                if row['active_run'] in live:
                    continue
                db.execute("UPDATE tasks SET status='interrupted',completed_at=? WHERE task_id=?", (now(), row['active_run']))
                db.execute("UPDATE messages SET research_status='interrupted' WHERE research_run=? AND research_status='running'", (row['active_run'],))
                db.execute('UPDATE research_threads SET active_run=NULL WHERE id=?', (row['id'],))


SCHEMA = """
CREATE TABLE IF NOT EXISTS research_migrations(name TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS research_thread_sources(
 thread_id TEXT NOT NULL REFERENCES research_threads(id),source_id TEXT NOT NULL REFERENCES research_sources(id),
 excluded INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(thread_id,source_id));
CREATE TABLE IF NOT EXISTS research_project(uid TEXT PRIMARY KEY,epoch INTEGER NOT NULL DEFAULT 1,enabled INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS research_threads(
 id TEXT PRIMARY KEY,title TEXT NOT NULL,agent TEXT NOT NULL DEFAULT '',mode TEXT NOT NULL DEFAULT 'research',
 notes TEXT NOT NULL DEFAULT '',summary TEXT NOT NULL DEFAULT '',summary_until INTEGER NOT NULL DEFAULT 0,
 archived INTEGER NOT NULL DEFAULT 0,trashed INTEGER NOT NULL DEFAULT 0,revision INTEGER NOT NULL DEFAULT 1,
 active_run TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS research_sources(
 id TEXT PRIMARY KEY,origin TEXT NOT NULL,kind TEXT NOT NULL,title TEXT NOT NULL,excluded INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL,UNIQUE(origin,kind));
CREATE TABLE IF NOT EXISTS research_versions(
 id TEXT PRIMARY KEY,source_id TEXT NOT NULL REFERENCES research_sources(id),blob TEXT NOT NULL,
 mime TEXT NOT NULL,coverage TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(source_id,blob));
CREATE TABLE IF NOT EXISTS research_extractions(
 id TEXT PRIMARY KEY,version_id TEXT NOT NULL REFERENCES research_versions(id),revision INTEGER NOT NULL,
 blob TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(version_id,revision));
CREATE TABLE IF NOT EXISTS research_captures(
 id TEXT PRIMARY KEY,version_id TEXT NOT NULL REFERENCES research_versions(id),thread_id TEXT,
 run_id TEXT,call_id TEXT NOT NULL,item_key TEXT NOT NULL,created_at TEXT NOT NULL,result_blob TEXT,
 UNIQUE(run_id,call_id,item_key));
CREATE INDEX IF NOT EXISTS research_capture_scope ON research_captures(thread_id,version_id);
CREATE TABLE IF NOT EXISTS research_jobs(
 version_id TEXT PRIMARY KEY REFERENCES research_versions(id),state TEXT NOT NULL DEFAULT 'pending',
 error TEXT NOT NULL DEFAULT '',index_source INTEGER,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS research_citations(
 message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
 version_id TEXT NOT NULL,locator TEXT NOT NULL,quote TEXT NOT NULL DEFAULT '',extraction_revision INTEGER NOT NULL DEFAULT 1,
 UNIQUE(message_id,version_id,locator));
CREATE TABLE IF NOT EXISTS research_access(
 run_id TEXT NOT NULL,version_id TEXT NOT NULL,revision INTEGER NOT NULL,locator TEXT NOT NULL,quote TEXT NOT NULL,
 UNIQUE(run_id,version_id,revision,locator,quote));
CREATE TABLE IF NOT EXISTS research_notes(
 id INTEGER PRIMARY KEY,thread_id TEXT NOT NULL REFERENCES research_threads(id),body TEXT NOT NULL,
 origin TEXT NOT NULL,covered_until INTEGER,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS research_events(
 sequence INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT NOT NULL,payload TEXT NOT NULL,
 thread_id TEXT,run_id TEXT,created_at TEXT NOT NULL);
"""
