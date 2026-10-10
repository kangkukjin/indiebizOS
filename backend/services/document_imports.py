"""Pages source identity, durable conversion attempts and reusable DOCX copies."""
import json
import os
import time
from pathlib import Path

from document_pages import ImportFailure, snapshot
from office_sessions import owner, read_bytes
from office_store import digest, identifier, sync_directory

LEASE_SECONDS = 360


def _get(store, kind, key):
    try:
        return store.get(kind, key)
    except ValueError:
        return None


def describe(app, document):
    p = document.get('provenance', {})
    if p.get('source_format') != 'pages':
        return None
    source = app._doc(p['resource_id'])
    return {'state': 'ready', 'source_resource': source['id'],
            'source_revision': p['revision_id'], 'source_path': source['source_uri'],
            'source_format': 'pages', 'working_format': 'docx',
            'source_changed': (p['snapshot_sha256'] != source['source_sha256']
                               if source.get('source_checked_at') else None),
            'source_checked_at': source.get('source_checked_at'),
            'created_at': p.get('created_at'), 'engine_version': p.get('engine_version', 'unknown'),
            'original_preserved': True, 'fidelity': 'unverified'}


def _reuse(app, key):
    row = app._doc(key)
    try:
        matches = digest(read_bytes(Path(row['source_uri']))) == row['source_sha256']
    except (OSError, ValueError):
        matches = False
    if not matches:
        raise ImportFailure('working_copy_conflict',
                            'DOCX 작업 사본이 외부에서 변경되었거나 없습니다. 기존 초안·버전은 보존했습니다')
    result = app.detail(key)
    result['conversion']['reused'] = True
    return result


def _finish(app, job):
    """Caller holds writer lock. File publication can be replayed, never overwritten."""
    store = app.store
    source = app._doc(job['source_id'])
    if source.get('conversion_attempt') != job['attempt']:
        raise ImportFailure('conversion_superseded', '더 새로운 문서 열기 작업이 있습니다')
    row = job['output_document']
    data = store.bytes(row['source_sha256'])
    path = Path(row['source_uri'])
    path.parent.mkdir(parents=True, exist_ok=True)
    # Publish the complete file exclusively; a crash cannot leave a partial target.
    temporary = path.parent / ('.' + job['attempt'] + '.tmp')
    if not path.exists():
        with temporary.open('wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            pass
        finally:
            temporary.unlink(missing_ok=True)
        sync_directory(path.parent)
    if path.is_symlink() or digest(read_bytes(path)) != row['source_sha256']:
        raise ImportFailure('working_copy_conflict', '변환 사본 위치에 다른 파일이 있습니다. 덮어쓰지 않았습니다')
    source['working_resource'] = row['id']
    source.pop('conversion_attempt', None)
    job.update(state='ready', output_id=row['id'], completed_at=time.time())
    revision = {'id': row['revision_id'], 'document_id': row['id'],
                'parent_revision_id': None, 'blob': row['source_sha256'], 'created_at': row['created_at']}
    with store.connect() as conn:
        store.put('document', row, conn)
        store.put('revision', revision, conn)
        store.put('document', source, conn)
        store.put('document_import', job, conn)
        store.event(source['id'], {'type': 'conversion_ready', 'resource': row['id'],
                                  'source_revision': job['source_revision']}, conn)
    return row['id']


def open_pages(app, path, conversion='auto', request_id=None, working_resource=None):
    owner()
    if conversion not in ('auto', 'source', 'refresh'):
        raise ValueError('conversion은 auto/source/refresh 중 하나입니다')
    if conversion == 'refresh' and (not isinstance(request_id, str) or not 1 <= len(request_id) <= 128):
        raise ValueError('새 변환 사본에는 request_id(1~128자)가 필요합니다')
    store = app.store
    data = snapshot(path)
    blob = store.blob(data)
    with store.lock():
        source = app.resources.register(path, data)
        if source['source_sha256'] != blob:
            previous = source['revision_id']
            source.update(source_sha256=blob, revision_id=identifier())
            with store.connect() as conn:
                store.put('revision', {'id': source['revision_id'], 'document_id': source['id'],
                    'parent_revision_id': previous, 'blob': blob, 'created_at': time.time()}, conn)
                store.put('document', source, conn)
        source['source_checked_at'] = time.time()
        store.put('document', source)
        if conversion == 'source':
            return app.detail(source['id'])
        if working_resource:
            candidate = app._doc(working_resource)
            if (candidate.get('provenance', {}).get('resource_id') != source['id']
                    or candidate['source_format'] != 'docx'):
                raise ValueError('이 Pages에서 변환한 DOCX 사본을 선택하세요')
            _reuse(app, working_resource)
            source['working_resource'] = working_resource
            source.pop('conversion_attempt', None)
            store.put('document', source)
        if conversion == 'auto' and source.get('working_resource'):
            return _reuse(app, source['working_resource'])
        if conversion == 'auto':
            candidates = [d for d in app.list() if d['source_format'] == 'docx'
                          and d.get('provenance', {}).get('resource_id') == source['id']
                          and d['provenance'].get('source_format') == 'pages'
                          and _get(store, 'revision', d['provenance'].get('revision_id', ''))]
            if len(candidates) == 1:
                _reuse(app, candidates[0]['id'])
                source['working_resource'] = candidates[0]['id']
                store.put('document', source)
                return _reuse(app, candidates[0]['id'])
            if len(candidates) > 1:
                raise ImportFailure('working_copy_choice', '이 Pages의 작업 사본이 여러 개입니다. 원본 정보에서 이어 쓸 사본을 선택하세요')
        identity = [source['owner'], source['id'], request_id if conversion == 'refresh' else source['revision_id'],
                    'docx', 1, conversion]
        key = 'pages_' + digest(json.dumps(identity).encode())
        job = _get(store, 'document_import', key)
        if job and job['state'] == 'ready':
            return _reuse(app, job['output_id'])
        if job and job.get('output_document') and source.get('conversion_attempt') == job['attempt']:
            return _reuse(app, _finish(app, job))
        # Serialize all refreshes of one source too, without holding a network lock.
        active = next((j for j in store.list('document_import') if j['source_id'] == source['id']
                       and j['attempt'] == source.get('conversion_attempt')), None)
        if active and active.get('output_document'):
            return _reuse(app, _finish(app, active))
        if active and active['state'] in ('converting', 'validating') and active['expires'] > time.time():
            raise ImportFailure('conversion_in_progress', 'Pages 변환 중입니다. 잠시 후 다시 시도하세요')
        if active and active['state'] in ('converting', 'validating'):
            active['state'] = 'interrupted'
            with store.connect() as conn:
                store.put('document_import', active, conn)
                store.event(source['id'], {'type': 'conversion_interrupted', 'attempt': active['attempt']}, conn)
        attempt = identifier()
        job = {'id': key, 'attempt': attempt, 'state': 'converting', 'source_id': source['id'],
               'source_revision': source['revision_id'], 'input_blob': blob,
               'created_at': time.time(), 'expires': time.time() + LEASE_SECONDS,
               'engine_version': 'unknown'}
        source['conversion_attempt'] = attempt
        with store.connect() as conn:
            store.put('document', source, conn)
            store.put('document_import', job, conn)
    try:
        from document_formats import convert_bytes
        from document_office import validate
        engine = {}
        output = convert_bytes(app, source['id'], data, 'pages', 'docx', source['title'], engine)
        job['engine_version'] = engine.get('engine_version', 'unknown')
        try:
            validate(output, 'docx')
            from docx import Document
            import io
            Document(io.BytesIO(output))
        except Exception as exc:
            raise ImportFailure('invalid_conversion_output', '변환 결과가 올바른 DOCX 문서가 아닙니다') from exc
        # Reobserve the source; conversion always uses the captured immutable bytes.
        try:
            current_blob = store.blob(snapshot(path))
        except (OSError, ValueError):
            current_blob = None
        with store.lock():
            current = app._doc(source['id'])
            if current.get('conversion_attempt') != attempt:
                raise ImportFailure('conversion_superseded', '더 새로운 문서 열기 작업이 있습니다')
            if current_blob is None:
                current['source_checked_at'] = None
            elif current_blob != current['source_sha256']:
                prior = current['revision_id']
                current.update(source_sha256=current_blob, revision_id=identifier(), source_checked_at=time.time())
                store.put('revision', {'id': current['revision_id'], 'document_id': current['id'],
                    'parent_revision_id': prior, 'blob': current_blob, 'created_at': time.time()})
            store.put('document', current)
            output_id, rev = identifier(), identifier()
            filename = Path(source['title']).stem + '_converted.docx'
            row = {'id': output_id, 'owner': source['owner'], 'title': filename,
                   'source_uri': str(store.root / 'files' / output_id / filename),
                   'source_format': 'docx', 'source_sha256': store.blob(output),
                   'revision_id': rev, 'encoding': None, 'session_id': None, 'created_at': time.time(),
                   'provenance': {'resource_id': source['id'], 'revision_id': job['source_revision'],
                                  'snapshot_sha256': blob, 'source_format': 'pages', 'output_format': 'docx',
                                  'original_preserved': True, 'created_at': time.time(),
                                  'engine_version': job['engine_version'], 'fidelity': 'unverified'}}
            job.update(state='validating', output_document=row)
            store.put('document_import', job)
            result = app.detail(_finish(app, job))
            result['conversion']['reused'] = False
            return result
    except Exception as exc:
        with store.lock():
            latest = store.get('document_import', key)
            if latest['attempt'] == attempt and latest['state'] != 'ready':
                latest.update(state='failed', error_code=getattr(exc, 'code', 'conversion_failed'))
                with store.connect() as conn:
                    store.put('document_import', latest, conn)
                    store.event(source['id'], {'type': 'conversion_failed', 'attempt': attempt,
                                              'error_code': latest['error_code']}, conn)
        raise


def candidates(app, source_id):
    app._doc(source_id)
    return [{'resource': d['id'], 'title': d['title'], 'path': d['source_uri']}
            for d in app.list() if d.get('provenance', {}).get('resource_id') == source_id
            and d['source_format'] == 'docx']
