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
                                                       'projection_revision': fields.get('projection_revision'),
            **({k: fields[k] for k in ('incident_ref', 'revision', 'resolution', 'signal', 'disposition', 'reason')
                if k in fields} if kind.startswith('recovery.') else {})})
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
    if getattr(binding, 'recovery_checkpoint', None):
        restore_parent(situation, binding.recovery_checkpoint)
    situation.observe({'kind': 'request', 'task': binding.task}, 'request_ref', evidence(binding.request),
                      source='user_request', basis='user_request', observed_at=time.time())


def checkpoint(binding):
    """Seal the current projection in its existing evidence store, before handing off effects."""
    situation = getattr(binding, 'situation', None)
    if not situation or not getattr(situation, 'store', None):
        return None
    snapshot = situation.snapshot()
    if not snapshot['recovery']['incidents']:
        return None
    try:
        ref = situation.store.evidence(snapshot)
    except (OSError, ValueError, TypeError):
        return {'availability': 'recovery_evidence_unavailable'}
    return {'store': str(situation.store.directory), 'id': ref['id'],
            'owner': situation.owner, 'task': situation.task,
            'projection_revision': snapshot['projection_revision']}


def restore_parent(situation, ref):
    from pathlib import Path
    from common.spill import spill_dir
    from member_runtime import is_member, private_path
    from supervision_store import TurnStore
    try:
        path = Path(ref['store']).resolve()
        roots = ([private_path(name) for name in ('supervision', 'tool_evidence')] if is_member()
                 else [Path(spill_dir()) / name for name in ('supervision', 'tool_evidence')])
        if (ref['owner'] != situation.owner
                or not any(path.is_relative_to(Path(root).resolve()) for root in roots) or not path.is_dir()):
            raise ValueError('recovery checkpoint scope mismatch')
        page = TurnStore(path).read_evidence(ref['id'], limit=None)
        if page['integrity'] != 'verified':
            raise ValueError('recovery checkpoint integrity unavailable')
        snapshot = json.loads(page['text'])
        if (snapshot.get('recovery', {}).get('task') != ref['task']
                or snapshot.get('projection_revision') != ref['projection_revision']):
            raise ValueError('recovery checkpoint version mismatch')
        situation.restore(snapshot, ref, resume_recovery=True)
    except (ValueError, OSError, KeyError, TypeError):
        situation.recovery.observe('parent-checkpoint', [{'signal': 'unobserved_range'}],
                                   {'availability': 'recovery_evidence_unavailable'})
        situation.persist('recovery.unavailable', reason='parent_checkpoint_unavailable')


def observe_result(situation, result, ref, call_id):
    """Retain result bodies as attributed claims, independently of transport success.

    Text excerpts are evidence for the model, never parsed into asserted effects.
    Complete JSON bodies may expose structured claims through the same adapter.
    """
    from logging_utils import mask_secret_data
    obj = mask_secret_data(result)
    visited = 0
    # Structural producer claims only: no stdout JSON promotion. Exact original paths survive.
    from operation_effects import collect, identity
    effects, omitted = collect(obj)
    for path, effect in effects:
        situation.observe({'kind': 'operation_effect', 'operation_ref': effect['operation_ref'],
                           'target': effect['target'], 'resource': effect['resource']},
                          'reported_effect', {**effect, 'observations_omitted': omitted},
                          source='tool_result', source_ref={**ref, 'path': path},
                          basis='tool_claim', call_id=call_id, evidence_key=identity(effect))

    def excerpt(text, limit=900):
        raw = text.encode('utf-8')
        if len(raw) <= limit:
            return {'text': text, 'truncated': False}
        return {'text': raw[:limit // 2].decode('utf-8', errors='ignore') + '\n…\n' +
                        raw[-limit // 2:].decode('utf-8', errors='ignore'), 'truncated': True}

    def publish(subject, facets, path, raw=None):
        from execution_situation import fingerprint
        context = subject.get('context') or {}
        task_ref = context.get('task_ref')
        # A full producer result + explicit task and host identity, never a clipped text hash.
        identity = None
        if raw is not None and task_ref and context.get('device'):
            identity = fingerprint([task_ref, context['device'], context.get('generation'), raw])
        situation.observe(subject, 'reported_outcome', facets, source='tool_result',
            source_ref={**ref, 'path': list(path)}, basis='tool_claim', call_id=call_id,
            evidence_key=identity)

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
                publish(subject, {'output': excerpt(value)}, path, raw=value)
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
            for key in ('limb', 'limb_name', 'device', 'generation', 'cwd', 'op'):
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
                publish(subject, facets, path, raw=value if any(k in facets for k in ('output', 'stdout', 'stderr', 'text')) else None)
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
    whole_version = complete or version.get('scope') == 'whole_source'
    revision = version.get('sha256') if whole_version and evidence.get('stable') else None
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
    current().feedback('file_committed', path=str(path), revision=revision)


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
