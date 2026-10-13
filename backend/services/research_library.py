"""불변 자료 보존과 노트북 색인의 연결. 모든 자료 접근은 프로젝트 범위 안이다."""
import hashlib
import json
import mimetypes
import re
from pathlib import Path

from notebook_store import NotebookStore, build_chunks, extract_file, _paragraphs_with_loc
from research_store import ResearchStore, ResearchConflict, identifier, json_text, now


COVERAGE_LABELS = {'full': '확보한 본문', 'partial': '일부 본문', 'snippet': '검색 발췌', 'unknown': '확보 범위 미확인'}
INDEX_LABELS = {'pending': '검색 준비 중', 'ready': '검색 가능', 'failed': '검색 준비 실패', 'unsupported': '텍스트 추출 불가'}


class ResearchLibrary:
    def __init__(self, store, thread=None):
        from research_context import current
        context = current() or {}
        active = context.get('thread_id') if context.get('project_uid') == store.uid else None
        if active and thread and active != thread:
            raise PermissionError('다른 대화의 자료실에는 접근할 수 없습니다')
        self.thread = thread or active
        if self.thread:
            store.thread(self.thread)
        self.store = store
        self.index = NotebookStore(store.root / 'index.db')

    def capture(self, data, *, title, origin='', kind='text', mime='text/plain', coverage='full',
                thread=None, run=None, call=None, item='0', paragraphs=None, acquired_result=None):
        if coverage not in {'full', 'partial', 'snippet', 'unknown'}:
            raise ValueError('잘못된 확보 범위')
        if isinstance(data, str):
            data = data.encode('utf-8')
        if self.thread and thread and thread != self.thread:
            raise PermissionError('다른 대화에 자료를 저장할 수 없습니다')
        thread = self.thread or thread
        if run is None:
            from research_context import current
            context = current() or {}
            run = (context.get('run_id') if context.get('project_uid') == self.store.uid
                   and context.get('thread_id') == thread else None) or 'manual'
        blob = self.store.put_blob(data)
        result_blob = self.store.put_blob(json_text(acquired_result)) if acquired_result is not None else None
        call = call or identifier()
        origin = origin or 'text:' + blob
        extraction = self.store.put_blob(json_text(paragraphs)) if paragraphs is not None else None
        with self.store.connect(True) as db:
            self.store.check_epoch(db)
            if thread:
                self.store.thread(thread, db)
            old = db.execute('SELECT v.* FROM research_captures c JOIN research_versions v ON v.id=c.version_id '
                             'WHERE c.run_id=? AND c.call_id=? AND c.item_key=?', (run, call, item)).fetchone()
            if old:
                if old['blob'] != blob:
                    raise ResearchConflict('같은 획득 신원의 내용이 달라졌습니다')
                return self._receipt(dict(old))
            source = db.execute('SELECT id FROM research_sources WHERE origin=? AND kind=?', (origin, kind)).fetchone()
            sid = source['id'] if source else identifier()
            if not source:
                db.execute('INSERT INTO research_sources(id,origin,kind,title,created_at) VALUES (?,?,?,?,?)',
                           (sid, origin, kind, title or origin, now()))
            row = db.execute('SELECT * FROM research_versions WHERE source_id=? AND blob=?', (sid, blob)).fetchone()
            if row:
                version = dict(row)
            else:
                version = {'id': identifier(), 'source_id': sid, 'blob': blob, 'mime': mime,
                           'coverage': coverage, 'created_at': now()}
                db.execute('INSERT INTO research_versions(id,source_id,blob,mime,coverage,created_at) VALUES (?,?,?,?,?,?)',
                           tuple(version.values()))
                if extraction:
                    db.execute('INSERT INTO research_extractions(id,version_id,revision,blob,created_at) VALUES (?,?,1,?,?)',
                               (identifier(), version['id'], extraction, now()))
                db.execute('INSERT INTO research_jobs(version_id,updated_at) VALUES (?,?)', (version['id'], now()))
            db.execute('INSERT INTO research_captures(id,version_id,thread_id,run_id,call_id,item_key,created_at,result_blob) VALUES (?,?,?,?,?,?,?,?)',
                       (identifier(), version['id'], thread, run, call, item, now(), result_blob))
            self.store.event(db, 'material.stored', self._receipt(version), thread, run)
        return self._receipt(version)

    def _receipt(self, version):
        return {'source_ref': version['source_id'], 'version_ref': version['id'],
                'project_ref': self.store.uid, 'preservation': 'stored', 'coverage': version['coverage'], 'coverage_label': COVERAGE_LABELS[version['coverage']]}

    def add_file(self, path, *, title=None, **context):
        path = Path(path).resolve(strict=True)
        raw = path.read_bytes()
        mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        # 바이트를 먼저 보존한다. 파서 실패가 원문 보존을 취소하지 않는다.
        receipt = self.capture(raw, title=title or path.name, origin=str(path), kind='file', mime=mime, **context)
        suffix = path.suffix.lower()
        snapshot = self.store.root / 'staging' / (identifier() + suffix)
        snapshot.parent.mkdir(exist_ok=True)
        try:
            snapshot.write_bytes(raw)
            paras, error = _extract_file(snapshot)
            if error:
                self._job_state(receipt['version_ref'], 'unsupported', error)
            else:
                self._extraction(receipt['version_ref'], paras)
        except Exception as exc:
            self._job_state(receipt['version_ref'], 'failed', str(exc))
        finally:
            snapshot.unlink(missing_ok=True)
        return receipt

    def _extraction(self, version, paras):
        blob = self.store.put_blob(json_text(paras))
        with self.store.connect(True) as db:
            self.store.check_epoch(db)
            old = db.execute('SELECT id FROM research_extractions WHERE version_id=? AND blob=?', (version, blob)).fetchone()
            if not old:
                revision = db.execute('SELECT COALESCE(MAX(revision),0)+1 FROM research_extractions WHERE version_id=?', (version,)).fetchone()[0]
                db.execute('INSERT INTO research_extractions(id,version_id,revision,blob,created_at) VALUES (?,?,?,?,?)',
                           (identifier(), version, revision, blob, now()))
            db.execute("UPDATE research_jobs SET state='pending',error='',updated_at=? WHERE version_id=?", (now(), version))

    def _job_state(self, version, state, error='', index_source=None):
        with self.store.connect(True) as db:
            self.store.check_epoch(db)
            db.execute('UPDATE research_jobs SET state=?,error=?,index_source=COALESCE(?,index_source),updated_at=? WHERE version_id=?',
                       (state, error, index_source, now(), version))

    def version(self, version):
        with self.store.connect() as db:
            row = db.execute('SELECT v.*,s.title,s.origin,s.kind,s.excluded,j.state AS index_state,j.error '
                             'FROM research_versions v JOIN research_sources s ON s.id=v.source_id '
                             'LEFT JOIN research_jobs j ON j.version_id=v.id WHERE v.id=?', (version,)).fetchone()
        if not row or not self._visible(version):
            raise ValueError('이 대화에 자료 버전이 없습니다')
        result = dict(row)
        if self.thread:
            with self.store.connect() as db:
                flag = db.execute('SELECT excluded FROM research_thread_sources WHERE thread_id=? AND source_id=?', (self.thread, result['source_id'])).fetchone()
            if flag:
                result['excluded'] = flag[0]
        return result

    def _visible(self, version):
        if not self.thread:
            return True  # 내부 색인 작업만 프로젝트 전체를 사용한다.
        with self.store.connect() as db:
            return bool(db.execute('SELECT 1 FROM research_captures WHERE thread_id=? AND version_id=?',
                                   (self.thread, version)).fetchone())

    def _scope_sql(self, alias='v'):
        if not self.thread:
            return '1', []
        return (f'EXISTS (SELECT 1 FROM research_captures c WHERE c.version_id={alias}.id AND c.thread_id=?)',
                [self.thread])

    def _excluded_sql(self):
        if not self.thread:
            return 's.excluded', []
        return ('COALESCE((SELECT x.excluded FROM research_thread_sources x WHERE x.source_id=s.id AND x.thread_id=?),s.excluded)',
                [self.thread])

    def paragraphs(self, version, revision=None):
        self.version(version)
        with self.store.connect() as db:
            row = db.execute('SELECT * FROM research_extractions WHERE version_id=? AND (? IS NULL OR revision=?) '
                             'ORDER BY revision DESC LIMIT 1', (version, revision, revision)).fetchone()
        if row:
            return json.loads(self.store.blob(row['blob'])), row['revision']
        if revision is not None:
            raise ValueError('요청한 추출 판본이 없습니다')
        v = self.version(version)
        if v['mime'].startswith('text/') or v['mime'] == 'application/json':
            paras = _paragraphs_with_loc(self.store.blob(v['blob']).decode('utf-8'))
            self._extraction(version, paras)
            return paras, 1
        raise ValueError('원본은 보존됐지만 텍스트를 추출하지 못했습니다')

    def prepare_index(self):
        self._upgrade_web_snapshots()
        if not self.index.db_path.exists():
            with self.store.connect(True) as db:
                self.store.check_epoch(db)
                db.execute("UPDATE research_jobs SET state='pending',index_source=NULL WHERE state='ready'")

    def _upgrade_web_snapshots(self):
        """옛 웹 원본 JSON의 검색 추출본만 새 판본으로 교체한다. 원문·옛 인용은 보존한다."""
        migration = 'web-snapshot-body-v1'
        with self.store.connect() as db:
            if db.execute('SELECT 1 FROM research_migrations WHERE name=?', (migration,)).fetchone():
                return
            versions = db.execute("SELECT v.id,v.blob FROM research_versions v JOIN research_sources s ON s.id=v.source_id "
                                  "WHERE s.kind='file' AND v.mime='application/json'").fetchall()
        for row in versions:
            body = _web_snapshot_body(self.store.blob(row['blob']))
            if body is not None:
                self._extraction(row['id'], _paragraphs_with_loc(body))
        with self.store.connect(True) as db:
            self.store.check_epoch(db)
            db.execute('INSERT OR IGNORE INTO research_migrations(name) VALUES (?)', (migration,))

    def retry(self, version):
        v = self.version(version)
        try:
            self.paragraphs(version)
        except ValueError:
            suffix = mimetypes.guess_extension(v['mime']) or '.bin'
            snapshot = self.store.root / 'staging' / (identifier() + suffix)
            snapshot.parent.mkdir(exist_ok=True)
            try:
                snapshot.write_bytes(self.store.blob(v['blob']))
                paras, error = _extract_file(snapshot)
                if error:
                    self._job_state(version, 'unsupported', error)
                    return {**self._receipt(v), 'message': error}
                self._extraction(version, paras)
            finally:
                snapshot.unlink(missing_ok=True)
        self._job_state(version, 'pending')
        return self._receipt(v)

    def index_pending(self, limit=8):
        self.prepare_index()
        self.index.call('create_notebook', self.store.uid, '연구 자료실')
        with self.store.connect() as db:
            versions = [r[0] for r in db.execute("SELECT version_id FROM research_jobs WHERE state='pending' ORDER BY updated_at LIMIT ?", (limit,))]
        for vid in versions:
            try:
                paras, revision = self.paragraphs(vid)
                chunks = build_chunks(paras)
                v = self.version(vid)
                # 버전마다 안정적인 가상 path. 재시도는 같은 소스에 다시 색인한다.
                with self.index.scope():
                    import notebook_store as core
                    nb = core.get_notebook(self.store.uid)
                    conn = core._connect()
                    try:
                        old = conn.execute('SELECT id FROM sources WHERE notebook_id=? AND path=?', (nb['id'], vid)).fetchone()
                    finally:
                        conn.close()
                    if old:
                        core.remove_source(self.store.uid, old['id'])
                    conn = core._connect()
                    try:
                        sid = conn.execute("INSERT INTO sources(notebook_id,title,kind,path,char_count,chunk_count,status,added_at) VALUES (?,?,'text',?,?,?,'indexing',?)",
                                           (nb['id'], v['title'], vid, sum(len(t) for _, t in chunks), len(chunks), now())).lastrowid
                        conn.commit()
                    finally:
                        conn.close()
                    core._index_chunks_job(nb['id'], sid, v['title'], chunks)
                    status = core._source_status(sid)
                if status['status'] != 'ready':
                    raise RuntimeError(status['error'] or '색인 미완료')
                self._job_state(vid, 'ready', index_source=sid)
            except Exception as exc:
                self._job_state(vid, 'failed', str(exc))

    def sources(self, query='', offset=0, limit=100, include_excluded=False):
        visible, args = self._scope_sql()
        latest, latest_args = self._scope_sql('x')
        excluded, excluded_args = self._excluded_sql()
        with self.store.connect() as db:
            rows = db.execute(f'SELECT s.*,v.id AS version_ref,v.coverage,v.created_at AS fetched_at,j.state AS index_state,j.error '
                              'FROM research_sources s JOIN research_versions v ON v.source_id=s.id '
                              'LEFT JOIN research_jobs j ON j.version_id=v.id '
                              f'WHERE {visible} AND (? OR {excluded}=0) AND s.title LIKE ? '
                              f'AND v.rowid=(SELECT MAX(x.rowid) FROM research_versions x WHERE x.source_id=s.id AND {latest}) '
                              'ORDER BY v.rowid DESC LIMIT ? OFFSET ?',
                              (*args, int(include_excluded), *excluded_args, '%' + query + '%', *latest_args, limit + 1, offset)).fetchall()
        return {'items': [{**dict(r), 'source_ref': r['id'], 'project_ref': self.store.uid,
                           'coverage_label': COVERAGE_LABELS[r['coverage']], 'index_label': INDEX_LABELS.get(r['index_state'], r['index_state'])} for r in rows[:limit]],
                'next_cursor': str(offset + limit) if len(rows) > limit else None,
                'pages': [{'title': '다음 자료 보기', 'cursor': str(offset + limit), 'query': query}] if len(rows) > limit else []}

    def versions(self, source):
        visible, args = self._scope_sql()
        with self.store.connect() as db:
            rows = db.execute(f'SELECT v.* FROM research_versions v WHERE source_id=? AND {visible} ORDER BY rowid DESC', (source, *args)).fetchall()
        return {'items': [self._receipt(dict(r)) | {'created_at': r['created_at']} for r in rows]}

    def read(self, version, offset=0, limit=12000, revision=None):
        """고정 추출 판본을 문자 단위로 읽고 실제 반환한 본문만 근거로 남긴다."""
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 12000:
            raise ValueError('max_chars는 1~12000 사이의 정수여야 합니다')
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError('cursor는 0 이상의 문자 위치여야 합니다')
        v = self.version(version)
        try:
            paras, revision = self.paragraphs(version, revision)
        except ValueError:
            if revision is not None:
                raise
            return {**self._receipt(v), 'title': v['title'], 'origin': v['origin'], 'blocks': [{'type': 'paragraph', 'text': v['error'] or '텍스트 추출을 지원하지 않는 형식입니다. 원문 파일은 보존되어 있습니다.'}], 'raw_path': self.store.material_path(v['blob'], v['mime'])}
        text = '\n\n'.join(f'[자료:{version}:{loc}] {body}' for loc, body in paras)
        visible = text[offset:offset + limit]
        # 실제 반환한 문장만 근거 원장에 남긴다. 전체 문서를 읽었다고 승격하지 않는다.
        position = 0
        for loc, body in paras:
            body_start = position + len(f'[자료:{version}:{loc}] ')
            start = max(offset, body_start) - body_start
            end = min(offset + limit, body_start + len(body)) - body_start
            if start < end:
                self.access(version, revision, loc, body[start:end])
            position = body_start + len(body) + 2
        return {**self._receipt(v), 'title': v['title'], 'origin': v['origin'], 'excluded': bool(v['excluded']), 'extraction_revision': revision,
                'text': visible, 'next_cursor': str(offset + limit) if len(text) > offset + limit else None,
                'total_chars': len(text), 'offset': offset, 'max_chars': limit,
                'controls': [{**self._receipt(v), 'title': '자료 관리'}],
                'pages': [{'title': '다음 부분 읽기', 'version_ref': version, 'cursor': str(offset + limit), 'extraction_revision': revision, 'max_chars': limit}] if len(text) > offset + limit else [],
                'blocks': [{'type': 'paragraph', 'text': visible}]}

    def search(self, query, limit=12):
        visible, args = self._scope_sql()
        latest, latest_args = self._scope_sql('x')
        excluded, excluded_args = self._excluded_sql()
        with self.store.connect() as db:
            mapping = {r['index_source']: dict(r) for r in db.execute(
                'SELECT j.index_source,v.id AS version_id,v.source_id,s.title,(SELECT MAX(revision) FROM research_extractions e WHERE e.version_id=v.id) AS extraction_revision FROM research_jobs j '
                'JOIN research_versions v ON v.id=j.version_id JOIN research_sources s ON s.id=v.source_id '
                f'WHERE {visible} AND {excluded}=0 AND v.rowid=(SELECT MAX(x.rowid) FROM research_versions x WHERE x.source_id=s.id AND {latest})',
                (*args, *excluded_args, *latest_args))}
            pending = db.execute(f"SELECT COUNT(*) FROM research_jobs j JOIN research_versions v ON v.id=j.version_id WHERE state!='ready' AND {visible}", args).fetchone()[0]
        # 후보 선정 전에 제한한다. 다른 대화의 상위 결과가 현재 대화 자료를 밀어내지 않는다.
        out = self.index.call('search_chunks', self.store.uid, query, top_k=limit,
                              source_ids=[sid for sid in mapping if sid is not None])
        if not out.get('success'):
            return {'items': [], 'search_state': 'not_ready', 'error_detail': out.get('error')}
        items = []
        for hit in out.get('results', []):
            v = mapping.get(hit['source_id'])
            if v:
                self.access(v['version_id'], v['extraction_revision'], hit['loc'], hit['text'])
                items.append({**hit, **v, 'version_ref': v['version_id'], 'source_ref': v['source_id'],
                              'citation': f"[자료:{v['version_id']}:{hit['loc']}]"})
        return {'items': items, 'search_type': out.get('search_type'), 'pending': pending}

    def exclude(self, source, excluded=True):
        if not self.versions(source)['items']:
            raise ValueError('이 대화에 자료가 없습니다')
        with self.store.connect(True) as db:
            self.store.check_epoch(db)
            if self.thread:
                db.execute('INSERT INTO research_thread_sources(thread_id,source_id,excluded) VALUES (?,?,?) '
                           'ON CONFLICT(thread_id,source_id) DO UPDATE SET excluded=excluded.excluded',
                           (self.thread, source, int(excluded)))
            else:
                db.execute('UPDATE research_sources SET excluded=? WHERE id=?', (int(excluded), source))
        return {'source_ref': source, 'excluded': excluded}

    def access(self, version, revision, loc, quote):
        from research_context import current
        context = current()
        if not context or context.get('project_uid') != self.store.uid:
            return
        with self.store.connect(True) as db:
            self.store.check_epoch(db)
            db.execute('INSERT OR IGNORE INTO research_access(run_id,version_id,revision,locator,quote) VALUES (?,?,?,?,?)',
                       (context['run_id'], version, revision, loc, quote))

    def citations(self, text, run):
        result = []
        with self.store.connect() as db:
            for version, loc in re.findall(r'\[자료:([a-f0-9]{32}):([^\]]+)\]', text):
                row = db.execute('SELECT version_id,revision AS extraction_revision,locator,quote FROM research_access '
                                 'WHERE run_id=? AND version_id=? AND locator=? ORDER BY rowid DESC LIMIT 1',
                                 (run, version, loc)).fetchone()
                if row:
                    result.append(dict(row))
        return result

    def add_url(self, url, **context):
        import requests
        import notebook_store as core
        from research_capture import clean_url
        origin = clean_url(url)
        if core._youtube_id(url):
            paras, title, error = core._extract_youtube(url)
            if error:
                raise ValueError(error)
            return self.capture(json_text(paras), title=title, origin=origin, kind='transcript',
                                mime='application/json', paragraphs=paras, **context)
        response = requests.get(url, timeout=25, headers={'User-Agent': 'IndieBiz Research/1.0'})
        response.raise_for_status()
        mime = response.headers.get('content-type', 'application/octet-stream').split(';')[0]
        raw = response.content
        receipt = self.capture(raw, title=origin, origin=origin, kind='web', mime=mime, **context)
        try:
            if mime == 'application/pdf':
                snapshot = self.store.root / 'staging' / (identifier() + '.pdf')
                try:
                    snapshot.write_bytes(raw)
                    paras, error = _extract_file(snapshot)
                    if error:
                        raise ValueError(error)
                finally:
                    snapshot.unlink(missing_ok=True)
            elif mime.startswith('text/') or mime == 'application/json':
                body = response.text
                if 'html' in mime:
                    body = core._strip_html(body)
                paras = core._paragraphs_with_loc(body)
            else:
                raise ValueError('원문은 저장했습니다. 이 형식의 텍스트 추출은 지원하지 않습니다')
            self._extraction(receipt['version_ref'], paras)
        except Exception as exc:
            self._job_state(receipt['version_ref'], 'unsupported', str(exc))
        return receipt


def _web_snapshot_body(raw):
    """수집기의 구조화된 웹 스냅샷을 알아본다. 일반 JSON 첨부의 필드는 버리지 않는다."""
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
    if (isinstance(obj, dict) and isinstance(obj.get('text'), str) and obj['text'].strip()
            and ('_page_structure' in obj or ('resolved_url' in obj and 'method' in obj))):
        return obj['text']
    return None


def _extract_file(path):
    if path.suffix.lower() == '.json':
        body = _web_snapshot_body(path.read_bytes())
        if body is not None:
            return _paragraphs_with_loc(body), ''
    return extract_file(str(path))
