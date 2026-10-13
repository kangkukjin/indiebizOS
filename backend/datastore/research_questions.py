"""대화별 연구 질문·잠정 답·근거·미확인 사항의 불변 판본. 자동 진리 판정은 없다."""
import hashlib
import json
import re
import unicodedata

from research_evidence import validate_reference
from research_store import ResearchConflict, identifier, now


SCHEMA = """
CREATE TABLE IF NOT EXISTS research_questions(
 question_id TEXT NOT NULL,thread_id TEXT NOT NULL REFERENCES research_threads(id),revision INTEGER NOT NULL,
 body TEXT NOT NULL,previous_digest TEXT,revision_digest TEXT NOT NULL,origin TEXT NOT NULL,
 run_id TEXT,event_sequence INTEGER NOT NULL REFERENCES research_events(sequence),created_at TEXT NOT NULL,
 PRIMARY KEY(question_id,revision));
CREATE INDEX IF NOT EXISTS research_questions_thread ON research_questions(thread_id,question_id,revision);
"""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def text(value, name, maximum=4000, required=False):
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        raise ValueError(f'{name}: {maximum}자 이내의 문자열을 지정하세요')
    return value.strip()


def strings(value, name):
    if not isinstance(value, list) or len(value) > 30:
        raise ValueError(f'{name}: 최대 30개 목록을 지정하세요')
    return [text(item, name, 1000, True) for item in value]


class ResearchQuestions:
    def __init__(self, store, tid):
        self.store, self.tid = store, tid
        store.thread(tid)

    def _decode(self, row, db):
        # 원문 판본부터 현재까지 순서·내용·연결을 검사한다. 해시는 진위 인증이 아니라 손상 탐지다.
        previous = None
        ancestors = db.execute('SELECT * FROM research_questions WHERE question_id=? AND thread_id=? '
                               'AND revision<=? ORDER BY revision',
                               (row['question_id'], self.tid, row['revision'])).fetchall()
        for index, ancestor in enumerate(ancestors, 1):
            body = json.loads(ancestor['body'])
            commitment = [ancestor['question_id'], ancestor['thread_id'], ancestor['revision'],
                          ancestor['previous_digest'], body, ancestor['origin'], ancestor['run_id'], ancestor['created_at']]
            if (ancestor['revision'] != index or ancestor['previous_digest'] != previous
                    or digest(commitment) != ancestor['revision_digest']):
                raise ResearchConflict('연구 질문 판본 사슬이 일치하지 않습니다')
            previous = ancestor['revision_digest']
        if len(ancestors) != row['revision']:
            raise ResearchConflict('연구 질문의 이전 판본이 없습니다')
        body = json.loads(row['body'])
        return {**body, 'question_id': row['question_id'], 'revision': row['revision'],
                'revision_digest': row['revision_digest'], 'previous_revision_digest': row['previous_digest'],
                'origin': row['origin'], 'run_id': row['run_id'], 'created_at': row['created_at'],
                'event_sequence': row['event_sequence'], 'project_ref': self.store.uid, 'thread_ref': self.tid}

    def _head(self, db, qid):
        row = db.execute('SELECT * FROM research_questions WHERE question_id=? AND thread_id=? '
                         'ORDER BY revision DESC LIMIT 1', (qid, self.tid)).fetchone()
        return self._decode(row, db) if row else None

    def read(self, *, question_id=None, cursor=0, limit=30, query='', history=False):
        if type(cursor) is not int or cursor < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('질문 조회 범위를 확인하세요')
        with self.store.connect() as db:
            self.store.check_epoch(db)
            if history:
                if not question_id:
                    raise ValueError('질문 이력은 question_id를 지정하세요')
                rows = db.execute('SELECT * FROM research_questions WHERE thread_id=? AND question_id=? '
                                  'ORDER BY revision DESC LIMIT ? OFFSET ?',
                                  (self.tid, question_id, limit + 1, cursor)).fetchall()
            else:
                rows = db.execute('SELECT q.* FROM research_questions q WHERE thread_id=? '
                                  'AND revision=(SELECT MAX(revision) FROM research_questions h WHERE h.question_id=q.question_id) '
                                  'AND (? IS NULL OR question_id=?) AND body LIKE ? ORDER BY rowid DESC LIMIT ? OFFSET ?',
                                  (self.tid, question_id, question_id, '%' + query + '%', limit + 1, cursor)).fetchall()
            return {'items': [self._decode(row, db) for row in rows[:limit]],
                    'next_cursor': str(cursor + limit) if len(rows) > limit else None,
                    'questions_only': True, 'question_id': question_id, 'question_history': history}

    def context(self, budget=7500):
        """작은 목록만 전달한다. 원문/이력은 같은 도구에서 회수하고 기존 인용을 새 읽기로 승격하지 않는다."""
        items, used = [], 0
        with self.store.connect() as db:
            self.store.check_epoch(db)
            rows = db.execute('SELECT q.* FROM research_questions q WHERE thread_id=? '
                              'AND revision=(SELECT MAX(revision) FROM research_questions h WHERE h.question_id=q.question_id) '
                              "ORDER BY (json_extract(body,'$.status')='open') DESC,rowid DESC", (self.tid,)).fetchall()
            for row in rows:
                q = self._decode(row, db)
                item = {k: q[k] for k in ('question_id', 'revision', 'text', 'scope', 'status')}
                item.update(provisional_answer=q['provisional_answer'][:600],
                            gaps=q['gaps'][:3], next_probes=q['next_probes'][:3],
                            gaps_total=len(q['gaps']), next_probes_total=len(q['next_probes']),
                            supporting_count=len(q['supporting']), contradicting_count=len(q['contradicting']),
                            detail_required=True)
                size = len(canonical(item))
                if used + size > budget:
                    break
                items.append(item)
                used += size
        return {'items': items, 'total': len(rows), 'omitted': len(rows) - len(items),
                'hint': '잠정 연구 기록이며 사실 증명이 아닙니다. thread_messages+questions_only:true로 전체 질문·근거를 읽으세요.'}

    def apply(self, changes, *, origin='user', run=None):
        if not isinstance(changes, list) or not 1 <= len(changes) <= 20:
            raise ValueError('questions는 변경할 질문 1~20개의 목록입니다')
        if origin not in {'user', 'agent'} or (origin == 'agent' and not run):
            raise ValueError('질문 작성 주체와 실행 신원이 필요합니다')
        results, seen = [], set()
        with self.store.connect(True) as db:
            self.store.check_epoch(db)
            thread = self.store.thread(self.tid, db)
            if origin == 'agent' and thread['active_run'] != run:
                raise ResearchConflict('종료된 연구 실행은 질문을 수정할 수 없습니다')
            for change in changes:
                if not isinstance(change, dict):
                    raise ValueError('질문 변경은 객체여야 합니다')
                qid = change.get('question_id') or identifier()
                if not isinstance(qid, str) or not re.fullmatch('[a-f0-9]{32}', qid) or qid in seen:
                    raise ValueError('질문 ID는 중복되지 않는 32자리 UUID hex여야 합니다')
                seen.add(qid)
                current = self._head(db, qid)
                expected = change.get('expected_revision')
                if type(expected) is not int or expected != (current['revision'] if current else 0):
                    raise ResearchConflict('질문이 변경됐습니다. 최신 질문을 읽고 expected_revision으로 다시 저장하세요')
                if not current and db.execute('SELECT 1 FROM research_questions WHERE question_id=?', (qid,)).fetchone():
                    raise ValueError('다른 대화의 질문은 변경할 수 없습니다')
                body = self._body(db, change, current, run if origin == 'agent' else None)
                stamp = now()
                previous = current['revision_digest'] if current else None
                revision = expected + 1
                checksum = digest([qid, self.tid, revision, previous, body, origin, run, stamp])
                duplicates = [r[0] for r in db.execute(
                    'SELECT q.question_id FROM research_questions q WHERE thread_id=? AND question_id!=? '
                    'AND revision=(SELECT MAX(revision) FROM research_questions h WHERE h.question_id=q.question_id) '
                    "AND json_extract(body,'$.fingerprint')=? AND json_extract(body,'$.status')='open'",
                    (self.tid, qid, body['fingerprint']))]
                self.store.event(db, 'question.updated' if current else 'question.created',
                                 {'question_id': qid, 'revision': revision, 'revision_digest': checksum,
                                  'origin': origin, 'meaning': '판단 변경 기록이며 답의 증명이 아님'}, self.tid, run)
                event = db.execute('SELECT last_insert_rowid()').fetchone()[0]
                db.execute('INSERT INTO research_questions VALUES (?,?,?,?,?,?,?,?,?,?)',
                           (qid, self.tid, revision, canonical(body), previous, checksum, origin, run, event, stamp))
                results.append({**self._head(db, qid), 'duplicate_candidates': duplicates})
        return {'items': results}

    def _body(self, db, change, current, run):
        fields = {'text', 'scope', 'provisional_answer', 'supporting', 'contradicting', 'gaps', 'next_probes', 'resolution'}
        if set(change) - fields - {'question_id', 'expected_revision'}:
            raise ValueError('지원하지 않는 질문 변경 필드입니다')
        body = {k: current[k] for k in fields} if current else {
            'text': '', 'scope': '', 'provisional_answer': '', 'supporting': [], 'contradicting': [],
            'gaps': [], 'next_probes': [], 'resolution': None}
        body.update({k: v for k, v in change.items() if k in fields})
        body['text'] = text(body['text'], '질문', 1000, True)
        body['scope'] = text(body['scope'], '범위', 1000)
        body['provisional_answer'] = text(body['provisional_answer'], '잠정 답변')
        for name in ('gaps', 'next_probes'):
            body[name] = strings(body[name], name)
        retained = {ref['evidence_id']: ref for name in ('supporting', 'contradicting') for ref in (current or {}).get(name, [])}
        for name in ('supporting', 'contradicting'):
            if not isinstance(body[name], list) or len(body[name]) > 30:
                raise ValueError('근거는 역할별 최대 30개입니다')
            body[name] = [validate_reference(self.store, db, self.tid, ref, run=run, retained=retained) for ref in body[name]]
            keys = [ref['evidence_id'] for ref in body[name]]
            if len(keys) != len(set(keys)):
                raise ValueError('같은 근거가 중복됐습니다')
        if {r['evidence_id'] for r in body['supporting']} & {r['evidence_id'] for r in body['contradicting']}:
            raise ValueError('같은 인용을 지지와 반박에 동시에 연결할 수 없습니다')
        # 근거·주장·질문 변경은 이전 종결을 취소한다. 재종결은 새 판본에서 명시적으로 요청한다.
        if current and 'resolution' not in change and any(body[k] != current[k] for k in fields - {'resolution'}):
            body['resolution'] = None
        resolution = body['resolution']
        if resolution is not None:
            if not isinstance(resolution, dict) or set(resolution) - {'disposition', 'rationale', 'objections'}:
                raise ValueError('종결에는 disposition, rationale, objections만 지정하세요')
            disposition = resolution.get('disposition')
            if disposition not in {'answered', 'withdrawn', 'out_of_scope'}:
                raise ValueError('종결은 answered/withdrawn/out_of_scope이며 자동 verified는 지원하지 않습니다')
            rationale = text(resolution.get('rationale'), '종결 이유', 4000, True)
            objections = resolution.get('objections', [])
            if not isinstance(objections, list) or len(objections) > 30:
                raise ValueError('반박 검토 목록을 확인하세요')
            checked = []
            for item in objections:
                if not isinstance(item, dict) or set(item) != {'evidence_id', 'rationale'}:
                    raise ValueError('반박 검토에는 evidence_id와 rationale이 필요합니다')
                checked.append({'evidence_id': text(item['evidence_id'], '근거 ID', 64, True),
                                'rationale': text(item['rationale'], '반박 검토 이유', 2000, True)})
            if disposition == 'answered':
                if not body['provisional_answer'] or not body['supporting'] or body['gaps']:
                    raise ValueError('답변으로 종결하려면 잠정 답변·지지 근거가 있고 남은 확인사항이 없어야 합니다')
                if {r['evidence_id'] for r in body['contradicting']} != {r['evidence_id'] for r in checked}:
                    raise ValueError('각 반박 근거를 어떻게 판단했는지 남기세요')
            body['resolution'] = {'disposition': disposition, 'rationale': rationale, 'objections': checked}
        body['status'] = 'resolved' if resolution else 'open'
        normalize = lambda value: ' '.join(unicodedata.normalize('NFC', value).split())
        body['fingerprint'] = digest([normalize(body['text']), normalize(body['scope'])])
        return body
