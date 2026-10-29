"""주제 대화의 현재 계획과 판본 연결. 계획 본문 작성·저장은 기존 인지 경로가 맡는다."""
import json
from pathlib import Path

from research_store import ResearchConflict, json_text, now


class ResearchPlans:
    def __init__(self, store, root):
        self.store = store
        self.root = Path(root).resolve()
        with store.connect(True) as db:
            store.check_epoch(db)
            db.execute("""CREATE TABLE IF NOT EXISTS research_plans(
                thread_id TEXT NOT NULL REFERENCES research_threads(id),
                revision INTEGER NOT NULL, receipt TEXT NOT NULL,
                run_id TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(thread_id, revision))""")

    def current(self, tid):
        with self.store.connect() as db:
            self.store.check_epoch(db)
            self.store.thread(tid, db)
            row = db.execute('SELECT * FROM research_plans WHERE thread_id=? '
                             'ORDER BY revision DESC LIMIT 1', (tid,)).fetchone()
        if not row:
            return None
        receipt = json.loads(row['receipt'])
        for key in ('path', 'previous_path'):
            if receipt.get(key):
                path = (self.root / receipt[key]).resolve()
                if not path.is_relative_to(self.root):
                    raise ValueError('현재 연구계획의 경로가 저장소 밖에 있습니다')
                receipt[key] = str(path)
        # 이름 변경·복제 후에도 현재 프로젝트 신원을 사용한다. 옛 본문은 역사적 기록이다.
        return {**receipt, 'project_uid': self.store.uid, 'thread_id': tid,
                'revision': row['revision']}

    def bind(self, tid, run, receipt, expected_revision):
        stored = dict(receipt)
        for key in ('path', 'previous_path'):
            if stored.get(key):
                path = Path(stored[key]).resolve()
                if not path.is_relative_to(self.root):
                    raise ValueError('연구계획을 현재 저장소 안에 저장해야 합니다')
                stored[key] = path.relative_to(self.root).as_posix()
        # 본문은 파일과 저장 영수증이 소유한다. DB에는 판본 연결만 보존한다.
        for key in ('body', 'project_uid', 'thread_id', 'revision'):
            stored.pop(key, None)
        with self.store.connect(True) as db:
            self.store.check_epoch(db)
            thread = self.store.thread(tid, db)
            if thread['active_run'] != run or thread['archived'] or thread['trashed']:
                raise ResearchConflict('종료되었거나 변경된 연구 대화에는 계획을 연결할 수 없습니다')
            revision = db.execute('SELECT COALESCE(MAX(revision),0) FROM research_plans '
                                  'WHERE thread_id=?', (tid,)).fetchone()[0]
            if revision != expected_revision:
                raise ResearchConflict('연구계획이 변경됐습니다. 최신 판본으로 다시 판단하세요')
            revision += 1
            db.execute('INSERT INTO research_plans VALUES (?,?,?,?,?)',
                       (tid, revision, json_text(stored), run, now()))
            self.store.event(db, 'research.plan_bound',
                             {'revision': revision, 'path': stored['path']}, tid, run)
        return {**receipt, 'project_uid': self.store.uid, 'thread_id': tid,
                'revision': revision}
