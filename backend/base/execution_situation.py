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


def projection_priority(record):
    """Keep request, uncertainty and substantive evidence ahead of transport receipts.

    This orders reported evidence; a failed check is not a diagnosis of its target,
    and a successful command cannot resolve another subject's earlier failure.
    """
    row = record['latest']
    value = row['value'] if isinstance(row['value'], dict) else {}
    body = any(k in value for k in ('output', 'stdout', 'stderr', 'text'))
    context = row['subject'].get('context') or {}
    failed = (any(value.get(k) is False for k in ('success', 'ok')) or
              any(value.get(k) for k in ('error', 'exception', 'timed_out', 'unknown')) or
              any(isinstance(value.get(k), (int, float)) and value[k] != 0
                  for k in ('exit', 'exit_code', 'returncode')) or
              any(str(value.get(k, '')).lower() in {'failed', 'blocked', 'error', 'recovering'}
                  for k in ('state', 'status', 'phase', 'readiness')))
    if row['basis'] == 'user_request':
        priority = 8
    elif record['availability'] in {'conflict', 'needs_recheck'}:
        priority = 7
    elif body and any(k in context for k in ('task_ref', 'device', 'limb')):
        priority = 6
    elif body:
        priority = 5
    elif failed:
        priority = 4
    elif row['facet'] not in {'execution', 'reported_outcome', 'receipt'}:
        priority = 3
    elif row['basis'] == 'observed' and value.get('state') in {'running', 'queued', 'waiting'}:
        priority = 2
    else:
        priority = 1
    return priority, record['revision']


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
        self.native_calls = {}
        self.refreshers = {}
        self.delivery_ids = set()
        self.snapshot_ref = None

    def watch(self, key, read):
        """Producer-owned local reads only. No network adapter or permanent polling thread."""
        with self.lock:
            if not self.closed:
                self.refreshers[key] = read

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

    def restore(self, snapshot, source_ref):
        """Only the owning conversation handoff may supply this data. No automatic task resumption."""
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

    def observe(self, subject, facet, value, *, source, source_ref=None, source_cursor=None,
                subject_revision=None, observed_at=None, basis='observed', relation=None,
                event_id=None, call_id=''):
        from logging_utils import mask_secret_data
        with self.lock:
            if self.closed:
                return None
            subject = mask_secret_data(copy.deepcopy(subject))
            value = mask_secret_data(copy.deepcopy(value))
            source_ref = mask_secret_data(copy.deepcopy(source_ref))
            relation = mask_secret_data(copy.deepcopy(relation))
            key = fingerprint([subject, facet, source])
            old = self.records.get(key)
            stable = [subject, facet, value, subject_revision, relation, basis]
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
                   'call_id': call_id, 'signature': signature}
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
            if isinstance(source_cursor, int):
                self.source_cursors[key] = max(source_cursor, self.source_cursors.get(key, 0))
            self.persist('situation.observed', projection_revision=self.revision, observation=row,
                         late=late, conflict=conflict)
            return copy.deepcopy(record)

    @optional_observation
    def tool_started(self, key, name, payload):
        ref = self.evidence(payload)
        self.observe({'kind': 'call', 'id': key}, 'execution',
                     {'name': name, 'state': 'running', 'effect': 'unknown', 'input_ref': ref},
                     source='tool', source_cursor=0, source_ref=ref, call_id=key, observed_at=time.time())

    @optional_observation
    def tool_finished(self, key, result, unknown=False):
        ref = self.evidence(result)
        self.observe({'kind': 'call', 'id': key}, 'execution',
                     {'state': 'result_missing' if unknown else 'returned',
                      'effect': 'unknown', 'result_ref': ref},
                     source='tool', source_cursor=1, source_ref=ref, call_id=key, observed_at=time.time())
        if self.on_result and not unknown:
            self.on_result(result, ref, key)

    def observe_native(self, event):
        name = event.get('name') or event.get('tool') or ''
        if name.startswith('mcp__indiebizos__') or name in {'execute_ibl', 'supervision'}:
            return  # the backend is the owner of bridge observations
        ident = event.get('id')
        if not ident:
            return
        if event.get('type') == 'tool_start':
            self.native_calls[ident] = name
            self.tool_started(ident, name, event.get('input', {}))
        elif event.get('type') == 'tool_result' and ident in self.native_calls:
            self.native_calls.pop(ident)
            self.tool_finished(ident, event.get('result', event.get('content', '')),
                               unknown=bool(event.get('transport_error')))

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
                    'observations': rows}

    def prepare(self, consumer, *, retained=(), baseline=False, budget=None):
        """Bound bytes when the provider tokenizer is unavailable; never report measured tokens."""
        self.refresh()
        with self.lock:
            if self.closed or (self.cancel_check and self.cancel_check()):
                return None
            cursor = self.cursors.get(consumer, {})
            chain = cursor.get('chain', [])
            baseline = baseline or not chain or not set(chain).issubset(set(retained))
            since = 0 if baseline else cursor['revision']
            if not baseline and since == self.revision:
                return None
            view = self.snapshot(since)
            if not view['observations'] or all(r['latest']['basis'] == 'user_request' for r in view['observations']):
                return None
            # A dependency change also needs its existing validation in a delta.
            if not baseline:
                all_rows = self.snapshot()['observations']
                existing = {r['latest']['id'] for r in view['observations']}
                view['observations'] += [r for r in all_rows if r['availability'] == 'needs_recheck'
                                         and r['latest']['id'] not in existing]
            delivery = {'delivery_id': uuid.uuid4().hex, 'projection_revision': self.revision,
                        'base_revision': since, 'mode': 'baseline' if baseline else 'delta',
                        'source_cursors': {}, 'observations': [],
                        'omitted': {'count': 0},
                        'size_method': 'utf8_bytes_limit_not_token_measurement', 'observed_at_note':
                        'null means source observation time unknown; received_at is arrival only'}
            limit = budget or (8000 if baseline else 2400)
            if self.snapshot_ref is None:
                self.snapshot_ref = self.evidence(self.snapshot())
            if self.snapshot_ref.get('id'):
                delivery['read_result'] = {'id': self.snapshot_ref['id']}
            else:
                delivery['evidence_availability'] = 'unavailable'
            rows = sorted(view['observations'], key=projection_priority, reverse=True)
            for record in rows:
                row = {'latest': {k: v for k, v in record['latest'].items()
                                  if k not in {'signature', 'relation', 'call_id'} and v is not None},
                       'availability': record['availability']}
                if record['latest']['relation']:
                    row['latest']['relation'] = record['latest']['relation']
                if record['first']['id'] != record['latest']['id']:
                    row['first'] = {k: record['first'][k] for k in ('value', 'subject_revision', 'observed_at')}
                for k in ('late', 'conflict'):
                    if k in record:
                        row[k] = {f: record[k][f] for f in ('value', 'subject_revision',
                                  'observed_at', 'source_cursor', 'source_ref')}
                candidate = {**delivery, 'observations': [*delivery['observations'], row]}
                source_key = fingerprint([record['latest']['subject'], record['latest']['facet'],
                                          record['latest']['source']])
                if source_key in view['source_cursors']:
                    candidate['source_cursors'] = {**delivery['source_cursors'],
                                                   source_key: view['source_cursors'][source_key]}
                if len(json.dumps(candidate, ensure_ascii=False).encode()) <= limit:
                    delivery['observations'].append(row)
                    delivery['source_cursors'] = candidate['source_cursors']
                else:
                    delivery['omitted']['count'] += 1
            # Pending does not replace an acknowledged cursor. A failed request is retried as a baseline.
            self.pending[consumer] = delivery
            self.delivery_ids.add(delivery['delivery_id'])
            self.persist('situation.prepared', consumer=consumer, **delivery)
            return copy.deepcopy(delivery)

    def acknowledge(self, consumer, delivery):
        with self.lock:
            pending = self.pending.get(consumer)
            if self.closed or not pending or pending['delivery_id'] != delivery['delivery_id']:
                return
            previous = self.cursors.get(consumer, {})
            chain = [] if delivery['mode'] == 'baseline' else previous.get('chain', [])
            self.cursors[consumer] = {'revision': delivery['projection_revision'],
                                     'chain': [*chain, delivery['delivery_id']]}
            self.pending.pop(consumer, None)
            self.persist('situation.delivered', consumer=consumer, delivery_id=delivery['delivery_id'],
                         projection_revision=delivery['projection_revision'], at=time.time(),
                         meaning='transport_received_response_not_model_understanding')

    def close(self):
        with self.lock:
            if not self.closed:
                self.persist('situation.checkpoint', **self.snapshot())
                self.closed = True
                self.pending.clear()
                self.refreshers.clear()
