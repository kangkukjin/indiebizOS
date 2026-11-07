"""Reuse compiler receipts; prove a narrow missing-binding repair without replaying effects."""
import hashlib
import re

from execution_situation import active_call_id, current, fingerprint, optional_observation
from preflight_feedback import publish


def _exact(value):
    from ibl_v2_ir import Node, pack
    if isinstance(value, Node):
        return [value.kind, _exact(value.data)]
    if isinstance(value, dict):
        return {k: _exact(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_exact(v) for v in value]
    return pack(value)


def binding_repair(old, source):
    """Only literal definitions of exactly the unbound names may be inserted.

    Every original statement, operation argument, order and returned expression
    remains exact. A different program or a new side effect never matches.
    """
    from ibl_v2_parser import parse
    from ibl_v2_ir import Fault
    try:
        original = parse(old['source']).data['statements']
        updated = parse(source).data['statements']
        remaining, added = [], set()
        for statement in updated:
            if (statement.kind == 'bind' and statement.data['name'] in old['missing']
                    and statement.data['value'].kind == 'literal'):
                if statement.data['name'] in added:
                    return False
                added.add(statement.data['name'])
            else:
                remaining.append(statement)
        return added == set(old['missing']) and _exact(remaining) == _exact(original)
    except (Fault, ValueError, TypeError, KeyError, RecursionError):
        return False


@optional_observation
def observe(request, result, project_path):
    if not isinstance(result, dict):
        return
    source = request.get('code') or request.get('pipeline') or ''
    if not isinstance(source, str):
        return
    revision = hashlib.sha256(source.encode()).hexdigest()
    executed = result.get('executed')
    status = ('valid' if executed is True else result.get('status', 'failed'))
    items = list(result.get('issues') or []) if executed is False else []
    items += list(result.get('warnings') or result.get('precheck_warnings') or [])
    report = {'phase': 'preflight', 'language': 'ibl', 'source_hash': revision,
              'status': status, 'executed': executed, 'items': items, 'total': len(items),
              'coverage': {'syntax': 'checked' if status != 'failed' else 'unavailable',
                           'runtime_guards': result.get('runtime_checks', {}).get('total', 'preserved')}}
    subject = {'kind': 'ibl_program', 'source_hash': revision, 'project': str(project_path)}
    publish(report, subject)
    situation = current()
    if situation is None or not active_call_id() or len(source.encode()) > 65536:
        return
    context = fingerprint([str(project_path), {k: v for k, v in request.items()
                          if k not in {'code', 'pipeline', 'check', 'budget'}}])
    with situation.lock:
        if not hasattr(situation, 'ibl_preflight_pending'):
            situation.ibl_preflight_pending = {}
            situation.preflight_repairs = {}
        pending = situation.ibl_preflight_pending
        if status in ('valid', 'incomplete'):
            matched = []
            for call, old in list(pending.items()):
                if old['context'] == context and binding_repair(old, source):
                    matched.append(call)
                    publish({**report, 'status': 'resolved', 'executed': False, 'items': [], 'total': 0}, old['subject'])
                    del pending[call]
            if matched:
                situation.preflight_repairs[active_call_id()] = matched
                while len(situation.preflight_repairs) > 32:
                    del situation.preflight_repairs[next(iter(situation.preflight_repairs))]
        if status != 'invalid' or not items or any(i.get('code') != 'UNBOUND' for i in items):
            return
        missing = set()
        for item in items:
            span = item.get('source_span') or item.get('location') or {}
            token = source[span.get('start', 0):span.get('end', 0)]
            if not re.fullmatch(r'\$[\w]+', token):
                return
            missing.add(token[1:])
        pending[active_call_id()] = {'source': source, 'missing': sorted(missing),
                                     'context': context, 'subject': subject}
        while len(pending) > 32:
            del pending[next(iter(pending))]
