"""Execution-local observations. No planning, polling, or business-success inference."""
import copy
import hashlib
import json
import logging
import threading
import time
import uuid
from datetime import datetime
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps

_call = ContextVar('situation_call', default='')
logger = logging.getLogger(__name__)
_feedback = None


def set_feedback(callback):
    """Composition root supplies optional producer feedback without an upward import."""
    global _feedback
    _feedback = callback


def optional_observation(fn):
    """Observation failure must not change a completed producer operation's result."""
    @wraps(fn)
    def observe(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            logger.exception('Execution situation observation unavailable: %s', fn.__name__)
            return None
    return observe


def active_call_id():
    return _call.get()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     default=str).encode()).hexdigest()


def projection_kind(record):
    """Classify evidence by its contract, not by interpreting output text."""
    row = record['latest']
    value = row['value'] if isinstance(row['value'], dict) else {}
    if row['basis'] == 'user_request':
        return 'request'
    if record['availability'] in {'conflict', 'needs_recheck'}:
        return record['availability']
    if row['facet'] == 'diagnostics' and row['basis'] == 'observed':
        return 'diagnostics'
    if row['facet'] == 'recovery':
        from recovery_projection import requires_attention
        return 'unresolved' if requires_attention(value) else 'state'
    if row['facet'] == 'execution':
        return 'unresolved' if value.get('state') in {'running', 'result_missing'} else 'history'
    if row['basis'] == 'observed':
        if row['facet'] == 'receipt':
            from task_receipts import LIVE
            return 'pending' if value.get('state') in LIVE or value.get('state') == 'waiting' else 'receipt'
        return 'state'
    if row['facet'] == 'reported_effect':
        return 'state'  # attributed driver claim; basis remains tool_claim
    return 'evidence' if row['facet'] == 'reported_outcome' else 'interpretation'


def projection_priority(record):
    kind = projection_kind(record)
    row = record['latest']
    value = row['value'] if isinstance(row['value'], dict) else {}
    body = any(k in value for k in ('output', 'stdout', 'stderr', 'text'))
    failed = (any(value.get(k) is False for k in ('success', 'ok')) or
              any(value.get(k) for k in ('error', 'exception', 'unknown')) or
              any(value.get(k) not in (None, 0) for k in ('exit', 'exit_code', 'returncode')) or
              value.get('state', value.get('status')) in {'failed', 'blocked', 'error'})
    priority = {'request': 9, 'conflict': 8, 'needs_recheck': 8, 'diagnostics': 8, 'unresolved': 7,
                'pending': 7, 'receipt': 7, 'state': 6, 'evidence': 3,
                'interpretation': 2, 'history': 1}[kind]
    return priority, bool(body or failed) if kind == 'evidence' else False, record['revision']


def projection_groups(records):
    """Only a full result identity supplied by its adapter permits cross-call folding."""
    groups = {}
    for record in sorted(records, key=projection_priority, reverse=True):
        row = record['latest']
        identity = row.get('evidence_key')
        # Never fold conflicting, late, or restored evidence into a fresh result.
        if identity and not any(k in record for k in ('conflict', 'late', 'restored_from')):
            key = 'evidence:' + identity
            version = fingerprint([identity, record['availability']])
        else:
            key = fingerprint([row['subject'], row['facet'], row['source']])
            version = fingerprint([record['revision'], record['availability']])
        if key not in groups:
            groups[key] = {'key': key, 'version': version, 'record': record,
                           'kind': projection_kind(record), 'aliases': []}
        else:
            groups[key]['aliases'].append(row)
    return list(groups.values())


def short_value(value, limit):
    """Bound excerpts only. Do not shorten resource identities or infer a verdict."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if isinstance(item, str) and key in {'text', 'output', 'stdout', 'stderr', 'error', 'reason', 'exception'}:
                raw = item.encode('utf-8')
                if len(raw) > limit:
                    item = (raw[:limit // 2].decode('utf-8', errors='ignore') + '\n…\n' +
                            raw[-limit // 2:].decode('utf-8', errors='ignore'))
                    result['projection_truncated'] = True
            result[key] = short_value(item, limit)
        return result
    if isinstance(value, list):
        return [short_value(item, limit) for item in value]
    return value


def projection_row(group, compact):
    record = group['record']
    latest = record['latest']
    fields = ('id', 'subject', 'facet', 'value', 'source', 'source_ref', 'subject_revision',
              'observed_at', 'basis', 'relation')
    row = {'latest': {k: copy.deepcopy(latest[k]) for k in fields
                      if latest.get(k) is not None and (k != 'relation' or latest[k])},
           'availability': record['availability']}
    limit = 120 if compact else 320
    row['latest']['value'] = short_value(row['latest']['value'], limit)
    # A cleared diagnostic must not carry the old errors back into the next input.
    # The complete before/after history remains in the snapshot evidence.
    if record['first']['id'] != latest['id'] and group['kind'] != 'diagnostics':
        row['first'] = {k: record['first'][k] for k in ('value', 'subject_revision', 'observed_at')}
        row['first']['value'] = short_value(row['first']['value'], limit)
    for key in ('late', 'conflict'):
        if key in record:
            row[key] = {k: record[key][k] for k in ('value', 'subject_revision', 'observed_at', 'source_ref')}
            row[key]['value'] = short_value(row[key]['value'], limit)
    if group['aliases']:
        # Full provenance is in read_result; bound the inline references during long waits.
        row['also_observed'] = [{'id': r['id'], 'source_ref': r['source_ref']}
                                for r in group['aliases'][:1]]
        row['additional_sources'] = len(group['aliases'])
    return row


def current(agent=None, task=None):
    from execution_turn import current as binding_current, resolve_session
    from thread_context import execution_key
    import principal
    agent, task = execution_key(agent, task)
    binding = binding_current()
    if not binding or binding.task != task or agent not in binding.aliases:
        try:
            binding = resolve_session(agent, task)
        except ValueError:
            return None
    situation = getattr(binding, 'situation', None)
    if (situation and not situation.closed and situation.owner == principal.current().key()):
        return situation
    return None


@contextmanager
def call_context(key):
    token = _call.set(key)
    try:
        yield
    finally:
        _call.reset(token)


def emit(subject, facet, value, *, source='harness', source_ref=None, source_cursor=None,
         subject_revision=None, observed_at=None, basis='observed', relation=None,
         event_id=None):
    """Producer seam: only known facts, never inferred target identity or effect."""
    situation = current()
    if situation:
        try:
            return situation.observe(subject, facet, value, source=source, source_ref=source_ref,
                source_cursor=source_cursor, subject_revision=subject_revision,
                observed_at=time.time() if observed_at is None and basis == 'observed' else observed_at,
                basis=basis, relation=relation, event_id=event_id,
                call_id=_call.get())
        except Exception:
            logger.exception('Execution situation observation unavailable')
    return None


@contextmanager
def tool_call(name, payload, *, call_id=None):
    situation = current()
    if not situation or _call.get():
        yield
        return
    key = call_id or uuid.uuid4().hex
    token = _call.set(key)
    try:
        situation.tool_started(key, name, payload)
        yield key
    except BaseException as exc:
        situation.tool_finished(key, {'exception': type(exc).__name__}, unknown=True)
        raise
    finally:
        _call.reset(token)


def run_tool(name, payload, execute):
    with tool_call(name, payload) as key:
        result = execute()
        situation = current()
        if situation and key:
            situation.tool_finished(key, result)
        return result


@contextmanager
def command_feedback(root):
    """A trusted command producer supplies its exact workspace, not shell text."""
    situation = current()
    observation = situation.feedback('command_started', root=str(root)) if situation else None
    try:
        yield
    finally:
        if situation and observation is not None:
            situation.feedback('command_finished', root=str(root), observation=observation)


class Situation:
    """First + ordered latest per source; concurrent sources remain separate evidence.

    The persistence callback owns masking and durable evidence. No disk or upper-layer
    import lives here. Delivery cursors move only after a transport acknowledgement.
    """

    def __init__(self, owner, task, persist, evidence, *, cancel_check=None):
        self.owner, self.task = owner, task
        self.persist, self.evidence = persist, evidence
        self.cancel_check = cancel_check
        self.lock = threading.RLock()
        self.revision = 0
        self.records = {}
        self.seen = set()
        self.cursors = {}
        self.pending = {}
        self.source_cursors = {}
        self.closed = False
        self.on_result = None
        self.on_recovery = None
        self.call_inputs = {}
        self.result_sources = {}
        from recovery_projection import RecoveryProjection
        self.recovery = RecoveryProjection(owner, task, self.publish_recovery)
        self.native_calls = {}
        self.native_sequences = {}
        self.refreshers = {}
        self.delivery_ids = set()
        self.snapshot_ref = None
        self.pending_versions = {}

    def watch(self, key, read):
        """Producer-owned local reads only. No network adapter or permanent polling thread."""
        with self.lock:
            if not self.closed:
                self.refreshers[key] = read

    @optional_observation
    def feedback(self, event, **data):
        if _feedback and not self.closed:
            return _feedback(self, event, **data)

    def refresh(self):
        with self.lock:
            callbacks = list(self.refreshers.values())
        for read in callbacks:
            if self.closed or (self.cancel_check and self.cancel_check()):
                break
            try:
                read()
            except Exception as exc:
                self.persist('situation.source_unavailable', error=type(exc).__name__)

    def restore(self, snapshot, source_ref, *, resume_recovery=False):
        """Only the owning conversation handoff may supply this data. No automatic task resumption."""
        if resume_recovery and snapshot.get('recovery'):
            self.recovery.restore(snapshot['recovery'])
        with self.lock:
            for record in snapshot.get('observations', []):
                row = record['latest']
                if row['basis'] == 'user_request':
                    continue
                key = fingerprint([row['subject'], row['facet'], row['source']])
                if key in self.records:
                    continue
                self.revision += 1
                self.records[key] = {**copy.deepcopy(record), 'revision': self.revision,
                                     'restored_from': source_ref}
                self.seen.update([record['first']['id'], row['id']])
            self.snapshot_ref = None
            self.persist('situation.restored', source_ref=source_ref, projection_revision=self.revision)

    def publish_recovery(self, row):
        self.observe({'kind': 'incident', 'id': row['incident_ref']}, 'recovery', row,
                     source='recovery_projection', source_cursor=row['revision'],
                     source_ref=(row.get('observation_refs') or [{}])[0], observed_at=time.time())
        self.persist('recovery.changed', incident_ref=row['incident_ref'], revision=row['revision'],
                     resolution=row['resolution'], signal=row['signal'],
                     disposition=(row.get('assessment') or {}).get('disposition'))

    def recovery_view(self):
        snapshot = self.snapshot()
        stale = {r['latest']['source_ref'].get('id') for r in snapshot['observations']
                 if r['availability'] in {'needs_recheck', 'conflict'}
                 and isinstance(r['latest'].get('source_ref'), dict)}
        self.recovery.invalidate(stale - {None})
        return self.recovery.view()

    def observe(self, subject, facet, value, *, source, source_ref=None, source_cursor=None,
                subject_revision=None, observed_at=None, basis='observed', relation=None,
                event_id=None, call_id='', evidence_key=None):
        from logging_utils import mask_secret_data
        if facet == 'receipt' and source == 'task_receipts' and basis == 'observed':
            self.recovery.receipt(subject, value, source_ref, call_id=call_id,
                                  cursor=source_cursor, observed_at=observed_at)
        with self.lock:
            if self.closed:
                return None
            subject = mask_secret_data(copy.deepcopy(subject))
            value = mask_secret_data(copy.deepcopy(value))
            source_ref = mask_secret_data(copy.deepcopy(source_ref))
            relation = mask_secret_data(copy.deepcopy(relation))
            key = fingerprint([subject, facet, source])
            old = self.records.get(key)
            stable = [subject, facet, value, subject_revision, relation, basis, evidence_key]
            signature = fingerprint(stable)
            event_id = event_id or fingerprint([source, source_cursor, observed_at, signature])
            reobserved = bool(old and old.get('restored_from') and observed_at
                              and observed_at != old['latest']['observed_at'])
            if event_id in self.seen and not reobserved:
                return old
            self.seen.add(event_id)
            # An unchanged poll is not progress. Its original observation time remains visible.
            if old and old['latest']['signature'] == signature and not reobserved:
                return old
            now = time.time()
            row = {'id': event_id, 'subject': subject, 'facet': facet, 'value': value,
                   'source': source, 'source_ref': source_ref, 'source_cursor': source_cursor,
                   'subject_revision': subject_revision, 'observed_at': observed_at,
                   'received_at': now, 'basis': basis, 'relation': relation or [],
                   'call_id': call_id, 'signature': signature, 'evidence_key': evidence_key}
            self.revision += 1
            self.snapshot_ref = None
            # Only source-owned sequence numbers establish ordering. Reception is not causality.
            previous_cursor = old['latest']['source_cursor'] if old else None
            ordered = isinstance(source_cursor, int) and isinstance(previous_cursor, int)
            late = ordered and source_cursor < previous_cursor
            conflict = bool(old and ((ordered and source_cursor == previous_cursor) or
                                    (source_cursor is None and previous_cursor is not None)))
            if old and not ordered:
                def epoch(value):
                    try:
                        return float(value) if isinstance(value, (int, float)) else datetime.fromisoformat(value).timestamp()
                    except (ValueError, TypeError):
                        return None
                before, after = epoch(old['latest']['observed_at']), epoch(observed_at)
                if before is not None and after is not None:
                    late, conflict = after < before, after == before
                elif basis == 'tool_claim':
                    conflict = True  # arrival order is not source order
            if old:
                record = {**old, 'revision': self.revision}
                if late:
                    record['late'] = row
                elif conflict:
                    record['conflict'] = row
                else:
                    record.update(latest=row)
                    record.pop('conflict', None)
                    record.pop('restored_from', None)
            else:
                record = {'first': row, 'latest': row, 'revision': self.revision}
            self.records[key] = record
            if basis == 'observed' and subject_revision is not None and not late:
                self.recovery.invalidate_subject(subject, subject_revision)
            if old and facet != 'recovery' and old['latest']['signature'] != row['signature']:
                prior_ref = old['latest'].get('source_ref') or {}
                if prior_ref.get('id'):
                    self.recovery.invalidate({prior_ref['id']})
            if isinstance(source_cursor, int):
                self.source_cursors[key] = max(source_cursor, self.source_cursors.get(key, 0))
            self.persist('situation.observed', projection_revision=self.revision, observation=row,
                         late=late, conflict=conflict)
            return copy.deepcopy(record)

    @optional_observation
    def tool_started(self, key, name, payload):
        self.feedback('tool_started', key=key, name=name, payload=payload)
        ref = self.evidence(payload)
        self.call_inputs[key] = (name, payload)
        self.observe({'kind': 'call', 'id': key}, 'execution',
                     {'name': name, 'state': 'running', 'effect': 'unknown', 'input_ref': ref},
                     source='tool', source_cursor=0, source_ref=ref, call_id=key, observed_at=time.time())

    @optional_observation
    def retain_result(self, key, result, ref, display=None):
        """Keep the producer value until this call finishes, before display projection.

        This is an in-flight handoff, not a cross-call cache or a truth judgment.
        Only the active producer can supply it; display fields cannot select it.
        """
        if key and key == active_call_id() and key in self.call_inputs:
            self.result_sources[key] = (copy.deepcopy(result), copy.deepcopy(ref),
                                        fingerprint(result if display is None else display))

    def result_source(self, key, result, ref):
        source = self.result_sources.get(key)
        display = result
        if source and isinstance(display, str):
            try:
                display = json.loads(display)
            except (ValueError, TypeError):
                return result, ref
        if source and source[2] == fingerprint(display):
            return source[:2]
        return result, ref

    @optional_observation
    def tool_finished(self, key, result, unknown=False, error=False):
        ref = self.evidence(result)
        if not unknown:
            result, ref = self.result_source(key, result, ref)
        self.result_sources.pop(key, None)
        name, payload = self.call_inputs.pop(key, ('', {}))
        self.feedback('tool_finished', key=key, name=name, payload=payload, unknown=unknown)
        if self.on_recovery:
            self.on_recovery(key, name, payload, result, ref, error, unknown)
        elif error or unknown:
            self.recovery.observe(key, [{'signal': 'result_missing' if unknown else 'failure'}], ref, name=name)
        self.observe({'kind': 'call', 'id': key}, 'execution',
                     {'state': 'result_missing' if unknown else 'returned',
                      'effect': 'unknown', 'result_ref': ref},
                     source='tool', source_cursor=1, source_ref=ref, call_id=key, observed_at=time.time())
        if self.on_result and not unknown:
            self.on_result(result, ref, key)

    def observe_native(self, event):
        name = event.get('name') or event.get('tool') or ''
        if name.startswith('mcp__indiebizos__') or name in {'execute_ibl', 'supervision'}:
            if event.get('type') == 'tool_result' and event.get('transport_error'):
                # A transport failure may never reach the backend producer.
                key = event.get('id') or name
                self.tool_started(key, name, {})
                self.tool_finished(key, event.get('result', ''), unknown=True, error=True)
            return  # the backend is the owner of bridge observations
        ident = event.get('id')
        if not ident:
            return
        if event.get('type') == 'tool_start':
            if ident in self.native_calls:
                return
            sequence = self.native_sequences.get(ident, 0)
            key = ident if sequence == 0 else f'{ident}:{sequence}'
            self.native_sequences[ident] = sequence + 1
            self.native_calls[ident] = key
            self.tool_started(key, name, event.get('input', {}))
        elif event.get('type') == 'tool_result' and ident in self.native_calls:
            key = self.native_calls.pop(ident)
            self.tool_finished(key, event.get('result', event.get('content', '')),
                               unknown=bool(event.get('transport_error')), error=bool(event.get('is_error')))

    def snapshot(self, since=0):
        with self.lock:
            rows = []
            for record in self.records.values():
                if record['revision'] <= since:
                    continue
                row = copy.deepcopy(record)
                latest = row['latest']
                row['availability'] = 'last_observed_before_resume' if row.get('restored_from') else 'last_observed'
                if 'conflict' in row:
                    row['availability'] = 'conflict'
                # Keep the tested version even after an input changes; never revoke unrelated checks.
                for dep in latest['relation']:
                    candidates = [v['latest'] for v in self.records.values()
                                  if v['latest']['subject'] == dep.get('subject')
                                  and v['latest']['facet'] == 'version'
                                  and v['latest']['basis'] == 'observed']
                    if candidates and any(v['subject_revision'] != dep.get('revision') for v in candidates):
                        row['availability'] = 'needs_recheck'
                peers = [v['latest'] for v in self.records.values()
                         if v['latest']['subject'] == latest['subject']
                         and v['latest']['facet'] == latest['facet']
                         and v['latest']['source'] != latest['source']]
                if any(v['value'] != latest['value'] or
                       v['subject_revision'] != latest['subject_revision'] for v in peers):
                    row['availability'] = 'conflict'
                rows.append(row)
            return {'projection_revision': self.revision, 'source_cursors': dict(self.source_cursors),
                    'observations': rows, 'recovery': self.recovery.snapshot()}

    def prepare(self, consumer, *, retained=(), baseline=False, budget=None, compact=False):
        """Reserve space for state AND results; acknowledge only facts actually included."""
        self.feedback('prepare')
        self.refresh()
        with self.lock:
            if self.closed or (self.cancel_check and self.cancel_check()):
                return None
            cursor = self.cursors.get(consumer, {})
            chain = cursor.get('chain', [])
            baseline = baseline or not chain or not set(chain).issubset(set(retained))
            since = 0 if baseline else cursor['revision']
            view = self.snapshot()
            all_groups = projection_groups(view['observations'])
            if not all_groups or all(g['kind'] == 'request' for g in all_groups):
                return None
            included = {} if baseline else cursor.get('included', {})
            # Unsent current facts survive a cursor advance. Old detailed history does not
            # become a drain queue: it remains accessible through the snapshot reference.
            states = {'request', 'conflict', 'needs_recheck', 'diagnostics', 'unresolved', 'pending', 'receipt', 'state'}
            groups = [g for g in all_groups if baseline or (
                included.get(g['key']) != g['version'] and
                (g['kind'] in states or g['record']['revision'] > since))]
            if not groups:
                return None
            delivery = {'delivery_id': uuid.uuid4().hex, 'projection_revision': self.revision,
                        'base_revision': since, 'mode': 'baseline' if baseline else 'delta',
                        'source_cursors': {}, 'observations': [],
                        'omitted': {'count': len(groups), 'by_kind': {}},
                        'projection': {'state_count': 0, 'evidence_count': 0,
                                       'history_count': 0, 'deduplicated':
                                       sum(len(g['aliases']) for g in groups)},
                        'size_method': 'utf8_bytes_limit_not_token_measurement',
                        'observed_at_note': 'null means unknown; last observation is not a fresh check'}
            limit = budget or (4000 if compact else (8000 if baseline else 2400))
            if self.snapshot_ref is None:
                self.snapshot_ref = self.evidence(view)
            if self.snapshot_ref.get('id'):
                delivery['read_result'] = {'id': self.snapshot_ref['id']}
            else:
                delivery['evidence_availability'] = 'unavailable'
            for g in groups:
                kind = g['kind']
                delivery['omitted']['by_kind'][kind] = delivery['omitted']['by_kind'].get(kind, 0) + 1
            selected = {}

            def size():
                return len(json.dumps(delivery, ensure_ascii=False).encode())

            def add(group, ceiling):
                kind = group['kind']
                lane = 'state' if kind in states else ('evidence' if kind == 'evidence' else 'history')
                row = projection_row(group, compact)
                delivery['observations'].append(row)
                delivery['projection'][lane + '_count'] += 1
                delivery['omitted']['count'] -= 1
                delivery['omitted']['by_kind'][kind] -= 1
                if size() <= ceiling:
                    selected[group['key']] = group['version']
                    return True
                delivery['observations'].pop()
                delivery['projection'][lane + '_count'] -= 1
                delivery['omitted']['count'] += 1
                delivery['omitted']['by_kind'][kind] += 1
                return False

            # Producer diagnostics are immediate edit feedback. Reserve their space before
            # old dependencies and tool bodies compete for the ordinary state/result lanes.
            # Overflow stays explicit in omitted.by_kind and unacknowledged in the cursor.
            for g in groups:
                if g['kind'] == 'diagnostics':
                    add(g, limit)
            state_rows = [g for g in groups if g['kind'] in states and g['key'] not in selected]
            evidence_rows = [g for g in groups if g['kind'] == 'evidence']
            base_size = size()
            # Each lane gets a protected share; unused space is shared afterward.
            state_ceiling = base_size + (limit - base_size) // 2 if evidence_rows else limit
            for g in state_rows:
                add(g, state_ceiling)
            evidence_ceiling = min(limit, size() + (limit - base_size) // 2) if state_rows else limit
            for g in evidence_rows:
                add(g, evidence_ceiling)
            for g in state_rows + evidence_rows:
                if g['key'] not in selected:
                    add(g, limit)
            if not compact:
                for g in groups:
                    if g['kind'] not in states | {'evidence'}:
                        add(g, limit)
            # A retained omission summary is sufficient when no new fact can fit.
            if not baseline and since == self.revision and not selected:
                return None
            if size() > limit:
                raise ValueError('situation budget cannot hold omission metadata')
            self.pending[consumer] = delivery
            self.pending_versions[consumer] = selected
            self.delivery_ids.add(delivery['delivery_id'])
            self.persist('situation.prepared', consumer=consumer, serialized_bytes=size(), **delivery)
            return copy.deepcopy(delivery)

    def acknowledge(self, consumer, delivery):
        with self.lock:
            pending = self.pending.get(consumer)
            if self.closed or not pending or pending['delivery_id'] != delivery['delivery_id']:
                return
            previous = self.cursors.get(consumer, {})
            chain = [] if delivery['mode'] == 'baseline' else previous.get('chain', [])
            included = {} if delivery['mode'] == 'baseline' else dict(previous.get('included', {}))
            included.update(self.pending_versions.pop(consumer, {}))
            self.cursors[consumer] = {'revision': delivery['projection_revision'],
                                     'included': included,
                                     'chain': [*chain, delivery['delivery_id']]}
            self.pending.pop(consumer, None)
            self.persist('situation.delivered', consumer=consumer, delivery_id=delivery['delivery_id'],
                         projection_revision=delivery['projection_revision'], at=time.time(),
                         meaning='transport_received_response_not_model_understanding')

    def close(self):
        self.feedback('close')
        with self.lock:
            if not self.closed:
                self.persist('situation.checkpoint', **self.snapshot())
                self.closed = True
                self.pending.clear()
                self.pending_versions.clear()
                self.refreshers.clear()
                self.result_sources.clear()
