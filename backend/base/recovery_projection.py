"""Execution-local failure facts and attributed decisions. No tools or model policy."""
import copy
import hashlib
import json
import logging
import threading

SCHEMA = 1
MAX_INCIDENTS = 1024
DISPOSITIONS = frozenset({'continue', 'satisfied', 'irrelevant', 'awaiting_user', 'blocked', 'unknown'})
SETTLED = frozenset({'satisfied', 'irrelevant', 'awaiting_user', 'blocked'})


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     default=str).encode()).hexdigest()


def requires_attention(row):
    if row.get('resolution') == 'needs_recheck':
        return True
    if row.get('resolution') == 'verified':
        return False
    assessment = row.get('assessment') or {}
    return assessment.get('disposition') not in SETTLED


class RecoveryProjection:
    """One projection per execution; callers supply normalized facts and verified references."""

    def __init__(self, owner, task, changed=None):
        self.owner, self.task = owner, task
        self.rows = {}
        self.receipts = {}
        self.call_receipts = {}
        self.changed = changed
        self.lock = threading.RLock()

    def _publish(self, rows):
        if self.changed:
            for row in rows:
                try:
                    self.changed(copy.deepcopy(row))
                except Exception:
                    logging.getLogger(__name__).exception('Recovery observation delivery unavailable')

    def observe(self, call_id, facts, ref, *, name='', repair_key=None):
        changed = []
        with self.lock:
            for fact in facts:
                ident = fingerprint([self.owner, self.task, call_id, fact.get('path', [])])
                if ident not in self.rows and len(self.rows) >= MAX_INCIDENTS:
                    ident = fingerprint([self.owner, self.task, 'overflow'])
                    fact = {'signal': 'unobserved_range', 'path': [], 'overflow': True}
                old = self.rows.get(ident)
                receipt = fact.get('receipt_subject', self.call_receipts.get(call_id))
                fact = copy.deepcopy(fact)
                signature = fingerprint([fact, ref, receipt, repair_key])
                if old and old.get('fact_signature') == signature:
                    continue
                row = {'incident_ref': ident, 'revision': (old or {}).get('revision', 0) + 1,
                       'origin': {'owner': self.owner, 'task': self.task, 'call_id': call_id,
                                  'name': name, 'path': fact.get('path', [])},
                       'signal': fact['signal'], 'effect': 'not_started' if fact.get('pre_execution') else 'unknown',
                       'resolution': 'unresolved', 'observation_refs': [copy.deepcopy(ref)],
                       'assessment': None, 'fact_signature': signature,
                       'pre_execution': bool(fact.get('pre_execution')),
                       'repair_key': repair_key, 'receipt_subject': receipt,
                       'detail': {k: v for k, v in fact.items() if k not in {'signal', 'path'}}}
                if old:
                    row['first_ref'] = old.get('first_ref', old['observation_refs'][0])
                self.rows[ident] = row
                changed.append(row)
        self._publish(changed)
        return copy.deepcopy(changed)

    def resolve_calls(self, calls, ref):
        """A producer proved a corrected program; resolve only its rejected calls."""
        changed = []
        with self.lock:
            for row in self.rows.values():
                if (row['origin']['call_id'] in calls and row.get('pre_execution')
                        and row['resolution'] != 'verified'):
                    row.update(resolution='verified', assessment=None, revision=row['revision'] + 1,
                               resolution_ref=copy.deepcopy(ref), resolution_scope='preflight_repair')
                    changed.append(copy.deepcopy(row))
        self._publish(changed)

    def resolve_pre_execution(self, repair_key, ref, *, operation=False):
        if not repair_key:
            return
        changed = []
        with self.lock:
            for row in self.rows.values():
                eligible = row.get('pre_execution') or (operation and row['origin']['path'] == []
                                                       and row['signal'] == 'failure')
                if (eligible and row.get('repair_key') == repair_key
                        and row['resolution'] != 'verified'):
                    row.update(resolution='verified', assessment=None, revision=row['revision'] + 1,
                               resolution_ref=copy.deepcopy(ref),
                               resolution_scope='matched_ibl_operation' if operation else 'pre_execution_only')
                    changed.append(copy.deepcopy(row))
        self._publish(changed)

    def receipt(self, subject, value, ref, *, call_id='', cursor=None, observed_at=None):
        """Only the task receipt producer calls this; tool claims cannot certify effects."""
        key = fingerprint(subject)
        receipt_call = call_id or 'receipt:' + key
        changed = []
        with self.lock:
            previous = self.receipts.get(key)
            order = cursor if cursor is not None else observed_at
            if previous and previous['order'] is not None and order is not None:
                if order < previous['order']:
                    return
                if order == previous['order'] and value == previous['value']:
                    return
                if order == previous['order'] and value != previous['value']:
                    value = {**value, 'state': 'unknown'}
            self.receipts[key] = {'order': order, 'value': copy.deepcopy(value)}
            if receipt_call not in self.call_receipts:
                self.call_receipts[receipt_call] = copy.deepcopy(subject)
            elif self.call_receipts[receipt_call] != subject:
                # A batch call is not the same operation as any one receipt inside it.
                self.call_receipts[receipt_call] = None
                for row in self.rows.values():
                    if row['origin']['call_id'] == receipt_call and row['origin']['path'] == []:
                        row.update(receipt_subject=None, resolution='needs_recheck', assessment=None,
                                   effect='unknown', revision=row['revision'] + 1)
                        changed.append(copy.deepcopy(row))
            for row in self.rows.values():
                if row.get('receipt_subject') != subject:
                    continue
                state = value.get('state')
                resolution = 'verified' if state == 'succeeded' else 'needs_recheck'
                if state in {'queued', 'running', 'waiting_children', 'cancel_requested'}:
                    resolution = 'unresolved'
                if row.get('receipt_state') == state and row['resolution'] == resolution:
                    continue
                row.update(receipt_state=state, resolution=resolution, assessment=None,
                           revision=row['revision'] + 1, resolution_ref=copy.deepcopy(ref),
                           resolution_scope='receipt_operation_only')
                if state == 'succeeded':
                    row['effect'] = 'observed'
                changed.append(copy.deepcopy(row))
        self._publish(changed)
        if value.get('state') in {'failed', 'cancelled', 'interrupted', 'unknown'}:
            self.observe(receipt_call,
                         [{'signal': 'failure', 'path': ['receipt', key], 'state': value['state'],
                           'receipt_subject': subject}], ref)

    def assess(self, decision, *, actor, valid_refs, subjects=()):
        """Reference validation is outside this lock. Compare the incident revision again."""
        if not isinstance(decision, dict):
            return False
        refs = decision.get('basis_refs')
        if (decision.get('disposition') not in DISPOSITIONS or not isinstance(refs, list) or not refs
                or any(not isinstance(r, str) or r not in valid_refs for r in refs)
                or not isinstance(decision.get('reason'), str) or not decision['reason'].strip()):
            return False
        with self.lock:
            row = self.rows.get(decision.get('incident_ref'))
            if not row or row['revision'] != decision.get('incident_revision'):
                return False
            # A model disposition never becomes an observed success or changes the original criteria.
            row['assessment'] = {k: copy.deepcopy(decision[k]) for k in
                                 ('disposition', 'basis_refs', 'reason', 'incident_revision')}
            row['assessment'].update(actor=actor, basis='model_judgment')
            row['assessment']['subjects'] = copy.deepcopy(list(subjects))
            if row['resolution'] == 'needs_recheck':
                row['resolution'] = 'unresolved'  # Fresh judgment, not observed success.
            row['revision'] += 1
            result = copy.deepcopy(row)
        self._publish([result])
        return True

    def invalidate_subject(self, subject, revision):
        """Snapshot evidence binds a judgment to the observed version of its subjects."""
        refs = set()
        with self.lock:
            for row in self.rows.values():
                assessment = row.get('assessment') or {}
                if any(dep['subject'] == subject and dep['revision'] != revision
                       for dep in assessment.get('subjects', [])):
                    refs.update(assessment['basis_refs'])
        self.invalidate(refs)

    def invalidate(self, refs):
        changed = []
        with self.lock:
            for row in self.rows.values():
                evidence = set((row.get('assessment') or {}).get('basis_refs', []))
                resolved = (row.get('resolution_ref') or {}).get('id')
                if evidence.intersection(refs) or resolved in refs:
                    if row['resolution'] == 'needs_recheck':
                        continue
                    row.update(resolution='needs_recheck', revision=row['revision'] + 1, assessment=None)
                    changed.append(copy.deepcopy(row))
        self._publish(changed)

    def view(self):
        with self.lock:
            return copy.deepcopy(list(self.rows.values()))

    def snapshot(self):
        with self.lock:
            subjects = {fingerprint(r['receipt_subject']) for r in self.rows.values() if r.get('receipt_subject')}
            return {'schema': SCHEMA, 'owner': self.owner, 'task': self.task, 'incidents': self.view(),
                    'receipts': copy.deepcopy({k: v for k, v in self.receipts.items() if k in subjects})}

    def restore(self, snapshot):
        if snapshot.get('owner') != self.owner:
            raise ValueError('recovery snapshot owner mismatch')
        if snapshot.get('schema') != SCHEMA:
            self.observe('snapshot', [{'signal': 'unobserved_range'}],
                         {'availability': 'unsupported_recovery_schema'})
            return
        changed = []
        with self.lock:
            for key, value in snapshot.get('receipts', {}).items():
                self.receipts.setdefault(key, copy.deepcopy(value))
            for source in snapshot.get('incidents', []):
                ident = source['incident_ref']
                if ident in self.rows:
                    continue
                row = copy.deepcopy(source)
                row['restored'] = True
                if row.get('assessment') or row.get('receipt_subject'):
                    row.update(resolution='needs_recheck', assessment=None, revision=row['revision'] + 1)
                self.rows[ident] = row
                changed.append(row)
        self._publish(changed)
