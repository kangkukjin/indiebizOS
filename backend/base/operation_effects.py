"""Versioned, bounded driver claims about effects; never a goal evaluator.

Only structural observations are collected. Text/stdout is never decoded here.
Transport binding proves which job returned a claim, not that the claim is true.
"""
import copy
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import sys
from pathlib import Path
import uuid

CONTRACT = 'operation-effect/1'
STATUSES = {'confirmed', 'mismatch', 'pending', 'unknown', 'unsupported'}
MAX_BYTES = 12000


@lru_cache(maxsize=64)
def revision(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make(*, driver, implementation, resource, scope, requested, actual, checks,
         status=None, reason=None, request_id=None, step_id=None, target=None,
         method='state_readback'):
    situation = sys.modules.get('execution_situation')
    call = situation.active_call_id() if situation is not None else None
    matches = [c.get('matched') for c in checks]
    derived = ('unknown' if not matches or any(v is None for v in matches) else
               'mismatch' if any(v is False for v in matches) else 'confirmed')
    if status == 'confirmed' and derived != 'confirmed':
        raise ValueError('confirmation_requires_all_checks')
    return {
        'contract': CONTRACT,
        'operation_ref': {'request_id': request_id or call or uuid.uuid4().hex,
                          'step_id': step_id or call or uuid.uuid4().hex},
        'target': target or {'device_id': None, 'generation': None},
        'resource': resource, 'status': status or derived, 'scope': scope,
        'requested': requested, 'actual': actual, 'checks': checks,
        'source': {'driver': driver, 'revision': revision(implementation), 'method': method},
        'observed_at': datetime.now(timezone.utc).isoformat(), 'sequence': 1,
        'reason': reason,
    }


def valid(value):
    if not isinstance(value, dict) or value.get('contract') != CONTRACT:
        return False
    if not isinstance(value.get('status'), str) or value['status'] not in STATUSES:
        return False
    if not all(isinstance(value.get(k), dict) for k in
               ('operation_ref', 'target', 'resource', 'requested', 'actual', 'source')):
        return False
    if not all(isinstance(value.get(k), str) and value[k] for k in ('scope', 'observed_at')):
        return False
    if not all(isinstance(value['operation_ref'].get(k), str) and value['operation_ref'][k]
               for k in ('request_id', 'step_id')):
        return False
    if not all(isinstance(value['source'].get(k), str) and value['source'][k]
               for k in ('driver', 'revision', 'method')):
        return False
    if not isinstance(value['resource'].get('kind'), str) or not value['resource']['kind']:
        return False
    if type(value.get('sequence')) is not int or value['sequence'] < 1:
        return False
    checks = value.get('checks')
    if not isinstance(checks, list) or len(checks) > 32:
        return False
    if any(not isinstance(c, dict) or not isinstance(c.get('name'), str)
           or c.get('matched') is not None and type(c['matched']) is not bool for c in checks):
        return False
    if value['status'] == 'confirmed' and (not checks or any(c.get('matched') is not True for c in checks)):
        return False
    try:
        return len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode()) <= MAX_BYTES
    except (TypeError, ValueError):
        return False


def collect(value, limit=16, *, deduplicate=True):
    """Find structured claims including partial/failure bodies, preserving exact paths."""
    found, visited = [], 0
    excluded = {'value_wire', 'partial_wire', 'source_map', 'evidence', 'recordings',
                'output', 'stdout', 'stderr', 'text', 'content', 'source', 'requested', 'actual'}

    def walk(obj, path):
        nonlocal visited
        visited += 1
        if visited > 1000 or len(path) > 16:
            return
        if isinstance(obj, dict):
            if valid(obj):
                found.append((path, obj))
                return
            for key, child in obj.items():
                if key not in excluded and isinstance(child, (dict, list)):
                    walk(child, path + [key])
        elif isinstance(obj, list):
            for index, child in enumerate(obj[:100]):
                walk(child, path + [index])
    walk(value, [])
    if not deduplicate:
        return found[:limit], max(0, len(found) - limit)
    unique = {}
    for path, obs in found:
        key = json.dumps(obs, sort_keys=True, ensure_ascii=False)
        if key not in unique:
            unique[key] = (path, obs)
    rows = list(unique.values())
    return rows[:limit], max(0, len(rows) - limit)


def bind(value, *, device, generation, job_id, request_id, received_at):
    """Bind once at authenticated result ingestion; keep the original event unchanged."""
    out = copy.deepcopy(value)
    rows, _ = collect(out, limit=1000, deduplicate=False)
    for _, obs in rows:
        expected = {'device_id': device, 'generation': generation}
        conflict = any(obs['target'].get(k) not in (None, v) for k, v in expected.items())
        obs['transport_ref'] = {'device_id': device, 'generation': generation,
                                'job_id': job_id, 'request_id': request_id,
                                'received_at': received_at, 'basis': 'authenticated_job_report'}
        if conflict:
            obs['status'] = 'unknown'
            obs['reason'] = 'observation_target_conflict'
        else:
            obs['target'] = expected
    return out


def identity(obs):
    """Same stored report from sync/wait/watcher folds; conflicting values stay visible."""
    return hashlib.sha256(json.dumps(obs, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def summaries(value, ref):
    from logging_utils import mask_secret_data
    rows, omitted = collect(mask_secret_data(value), limit=8)
    shown = []
    for path, obs in rows:
        summary = {k: obs[k] for k in ('contract', 'operation_ref', 'target', 'resource',
            'status', 'scope', 'requested', 'actual', 'checks', 'source', 'observed_at',
            'sequence', 'reason', 'transport_ref') if k in obs}
        for key in ('requested', 'actual'):
            if len(json.dumps(summary[key], ensure_ascii=False)) > 1600:
                summary[key] = {'omitted': True, 'reason': 'read_original_observation'}
        if len(summary['checks']) > 8:
            summary['checks_omitted'] = len(summary['checks']) - 8
            summary['checks'] = summary['checks'][:8]
        summary.update(basis='driver_report', source_ref={**ref, 'path': path})
        shown.append(summary)
    return shown, omitted


def carried(accepted, observed=None):
    """Carriage evidence for an effect the hub verified from an accepted job.

    accepted is the original submission receipt and observed the ledger view the hub
    read back by that receipt's task_ref; both come from the receipt-owning APIs, not
    from a caller-supplied result. The generation is the job's own, never the device
    registration at lookup time. bind() says which job returned a device's report;
    this says which job a hub-side verification read, and its basis keeps them apart.
    Returns (transport_ref, conflict): mixed jobs, devices or generations conflict.
    A receipt older than these fields yields the limited basis 'accepted_receipt'."""
    accepted = accepted if isinstance(accepted, dict) else {}
    task_ref = accepted.get('task_ref') if isinstance(accepted.get('task_ref'), dict) else {}
    ref = {'device_id': accepted.get('limb'), 'generation': accepted.get('generation'),
           'job_id': task_ref.get('task_id'), 'request_id': accepted.get('request_id'),
           'received_at': None, 'basis': 'accepted_receipt', 'result_ref': {'task_ref': task_ref or None}}
    if not isinstance(observed, dict):
        return ref, None
    seen = {'device_id': observed.get('limb'), 'generation': observed.get('generation'),
            'job_id': (observed.get('task_ref') or {}).get('task_id'), 'request_id': observed.get('request_id')}
    for key, value in seen.items():
        if value is None:
            continue
        if ref[key] is None:
            ref[key] = value
        elif ref[key] != value:
            return ref, 'transport_' + key + '_conflict'
    ref.update(received_at=observed.get('result_received_at'), basis='hub_task_ledger')
    return ref, None


def verified_result(value, *, driver, implementation, requested, request_id, target, scope,
                    transport=None, resource=None):
    """Called only after a producer's existing receipt and readback checks.

    transport (from carried) keeps the original job with the verified effect. resource is
    the producer's own instance reference; without one the action is recorded as the kind
    of control only, and no identity is derived from output text, PIDs or file names."""
    # Avoid screenshots, native dumps and stream URLs in the compact observation.
    actual = {k: v for k, v in value.items() if isinstance(v, (str, int, float, bool, type(None)))
              and k not in {'url', 'stream_url', 'output', 'text', 'protocol', 'source_sha256'}}
    if len(json.dumps(actual, ensure_ascii=False)) > 3000:
        actual = {'verified': value.get('verified'), 'details': 'see_original_result'}
    matched = True if value.get('verified') is True else None
    if not (isinstance(resource, dict) and isinstance(resource.get('kind'), str) and resource['kind']):
        resource = {'kind': 'device_control', 'id': None, 'action': requested.get('action'),
                    'identity': 'not_reported_by_driver'}
    generation = transport.get('generation') if isinstance(transport, dict) else None
    observation = make(driver=driver, implementation=implementation,
        resource=resource, scope=scope,
        requested=requested, actual=actual,
        checks=[{'name': 'existing_driver_postcondition', 'matched': matched}],
        request_id=request_id, step_id=request_id + ':verification',
        target={'device_id': target, 'generation': generation}, method='existing_driver_verification',
        reason=None if matched else 'driver_did_not_verify_postcondition')
    if isinstance(value.get('observed_at'), str) and value['observed_at']:
        observation['observed_at'] = value['observed_at']
    if isinstance(transport, dict):
        observation['transport_ref'] = dict(transport)
    return {**value, 'observation': observation}
