"""TurnStore-backed execution observations; adapters consume existing producer receipts."""
import json
import logging
import time

from execution_situation import Situation, current, emit, optional_observation


@optional_observation
def attach(binding, store=None, handoff=None):
    if binding is None or binding.situation is not None:
        return
    import principal
    from supervision_store import current_evidence_store
    store = store or current_evidence_store()

    def persist(kind, **fields):
        try:
            store.log(kind, **fields)
        except Exception:
            logging.getLogger(__name__).exception('Situation journal unavailable')
            return
        from episode_logger import record_trajectory_event
        record_trajectory_event('supervision.' + kind, {'store': str(store.directory),
                                                       'seq': store.sequence,
                                                       'projection_revision': fields.get('projection_revision')})
        if kind == 'situation.checkpoint' and handoff and handoff.available:
            try:
                handoff.record('situation', {'snapshot': fields, 'availability': 'last_observed'})
            except Exception:
                logging.getLogger(__name__).exception('Situation handoff unavailable')

    def evidence(value):
        try:
            ref = store.evidence(value)
            return {'id': ref['id'], 'chars': ref['chars']}
        except Exception:
            return {'id': None, 'availability': 'evidence_store_unavailable'}

    situation = Situation(principal.current().key(), binding.task, persist, evidence,
                          cancel_check=binding.cancel_check)
    situation.on_result = lambda result, ref, key: observe_result(situation, result, ref, key)
    situation.store = store
    binding.situation = situation
    for snapshot, ref in getattr(handoff, 'situation_recovery', []):
        situation.restore(snapshot, ref)
    situation.observe({'kind': 'request', 'task': binding.task}, 'request_ref', evidence(binding.request),
                      source='user_request', basis='user_request', observed_at=time.time())


def observe_result(situation, result, ref, call_id):
    """Retain result bodies as attributed claims, independently of transport success.

    Text excerpts are evidence for the model, never parsed into asserted effects.
    Complete JSON bodies may expose structured claims through the same adapter.
    """
    from logging_utils import mask_secret_data
    obj = mask_secret_data(result)
    visited = 0

    def excerpt(text, limit=900):
        raw = text.encode('utf-8')
        if len(raw) <= limit:
            return {'text': text, 'truncated': False}
        return {'text': raw[:limit // 2].decode('utf-8', errors='ignore') + '\n…\n' +
                        raw[-limit // 2:].decode('utf-8', errors='ignore'), 'truncated': True}

    def publish(subject, facets, path):
        situation.observe(subject, 'reported_outcome', facets, source='tool_result',
            source_ref={**ref, 'path': list(path)}, basis='tool_claim', call_id=call_id)

    def walk(value, path=(), context=None):
        nonlocal visited
        visited += 1
        if visited > 100 or len(path) > 8:
            return
        subject = {'kind': 'call', 'id': call_id, 'path': list(path)}
        if context:
            subject['context'] = context
        if isinstance(value, str):
            if not value.strip():
                return
            try:
                decoded = json.loads(value)
            except (ValueError, TypeError):
                decoded = None
            if isinstance(decoded, (dict, list)):
                walk(decoded, (*path, 'json'), context)
            else:
                publish(subject, {'output': excerpt(value)}, path)
        elif isinstance(value, list):
            for i, item in enumerate(value[:40]):
                walk(item, (*path, i), context)
        elif isinstance(value, dict):
            facets = {k: value[k] for k in ('success', 'ok', 'error', 'exit_code', 'returncode', 'exit',
                                           'state', 'status', 'terminal', 'timed_out', 'accepted',
                                           'timeout', 'cancelled', 'unknown', 'phase', 'readiness',
                                           'reason', 'recovery_reason', 'exception')
                      if k in value and not isinstance(value[k], (dict, list))}
            task_ref = value.get('task_ref')
            context = dict(context or {})
            for key in ('limb', 'limb_name', 'device', 'cwd', 'op'):
                if isinstance(value.get(key), str):
                    context[key] = value[key][:240]
            if isinstance(task_ref, dict) and task_ref.get('kind') and task_ref.get('task_id'):
                context['task_ref'] = task_ref
            if context:
                subject['context'] = context
            for key in ('output', 'stdout', 'stderr', 'text'):
                if isinstance(value.get(key), str) and value[key].strip():
                    facets[key] = excerpt(value[key])
            if facets:
                publish(subject, facets, path)
            # Known transport/result containers only. External source bodies are not evidence adapters.
            for key in ('value', 'result', 'items', 'results', 'failure', 'details',
                        'observation', 'execution_result', 'content'):
                if key in value and isinstance(value[key], (dict, list, str)):
                    walk(value[key], (*path, key), context)
    walk(obj)


@optional_observation
def source_published(evidence, ref):
    if not current():
        return
    source = evidence['source']
    version = evidence.get('version') or {}
    complete = bool((evidence.get('scope') or {}).get('complete'))
    revision = version.get('sha256') if complete and evidence.get('stable') else None
    from runtime_utils import file_resource_identity
    emit({'kind': source['kind'], 'device': source.get('device_id'), 'address': file_resource_identity(source['address'])},
         'version' if revision else 'partial_read',
         {'stable': evidence.get('stable'), 'scope': evidence.get('scope'),
          'method': version.get('method')}, source='file_io',
         source_ref={'source_observation_ref': ref}, subject_revision=revision,
         observed_at=evidence.get('observed_at'), event_id=ref)


@optional_observation
def file_written(path, data):
    """Called with the exact bytes just atomically committed, under the producer lock."""
    if not current():
        return
    import hashlib
    file_committed(path, hashlib.sha256(data).hexdigest(), len(data))


@optional_observation
def file_committed(path, revision, size=None):
    """Existing publication receipt; no filesystem read is added after the write."""
    if not current():
        return
    from source_observation import device_identity
    from runtime_utils import file_resource_identity
    emit({'kind': 'file', 'device': device_identity(), 'address': file_resource_identity(path)},
         'version', {'write': 'committed', 'size': size}, source='file_io',
         subject_revision=revision, observed_at=time.time())


@optional_observation
def office_read(store, kind, row):
    """Committed store reads only; never observe a transaction before its commit."""
    if not current() or kind not in {'document', 'session', 'revision', 'operation', 'snapshot'}:
        return
    from source_observation import device_identity
    subject = {'kind': 'office_' + kind, 'device': device_identity(),
               'store': str(store.root), 'id': row['id']}
    version = row.get('blob') or row.get('source_sha256') or row.get('revision_id')
    known = {k: row[k] for k in ('revision_id', 'session_revision', 'status', 'state',
                                'document_id', 'session_id', 'source_uri') if k in row}
    emit(subject, 'version', known, source='office_store', subject_revision=version,
         observed_at=time.time())


@optional_observation
def file_validation(path, data, *, check, outcome):
    if not current():
        return
    from source_observation import device_identity
    from runtime_utils import file_resource_identity
    import hashlib
    subject = {'kind': 'file', 'device': device_identity(), 'address': file_resource_identity(path)}
    revision = hashlib.sha256(data).hexdigest()
    emit(subject, 'validation:' + check, {'outcome': outcome, 'coverage': check},
         source='validator', subject_revision=revision, observed_at=time.time(),
         relation=[{'subject': subject, 'revision': revision}])


@optional_observation
def document_validation(store, document, data):
    """An in-memory draft is checked; this does not certify the original file on disk."""
    if not current():
        return
    import hashlib
    from source_observation import device_identity
    revision = hashlib.sha256(data).hexdigest()
    emit({'kind': 'office_blob', 'device': device_identity(), 'store': str(store.root),
          'document_id': document['id'], 'sha256': revision},
         'validation:document_format', {'outcome': 'passed', 'coverage': 'document_format',
                                        'publication': 'not_established_by_validation'},
         source='validator', subject_revision=revision)
