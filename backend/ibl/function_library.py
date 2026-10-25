"""Compiler-owned mutation gate for the common function catalog."""
import copy
import uuid

import function_store as store


def definitions(view=None):
    from ibl_v2_store import Library
    view = store.snapshot() if view is None else view
    result = Library()
    result.references = {}
    result.generation = view['generation']
    for row in view['records'].values():
        if row.get('state') == 'retired':
            continue
        name = row['name']
        if row.get('state') != 'active' or row.get('problem'):
            result.conflicts[name] = [row.get('problem') or row.get('state')]
            continue
        result.add(name, row['source'], '관용구:' + row['function_id'])
        result.references[name] = store.reference(row)
    return result


def validate_changes(before, after, changed):
    with store.using(after):
        return _validate_changes(before, after, changed)


def _validate_changes(before, after, changed):
    """No execution during publication; unchanged broken callers are not blockers."""
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_store import definition_name
    from ibl_v2_ir import Fault
    try:
        registry = load_registry()
        with store.using(before):
            prior_registry = load_registry()
    except (Fault, ValueError):
        if any(r.get('state') == 'active'
               for view in (before, after) for r in view['records'].values()):
            raise
        registry = prior_registry = {}
    prior, following = definitions(before), definitions(after)

    def issues(source, library):
        try:
            return compile_program(source, prior_registry if library is prior else registry, definitions=library).issues
        except (Fault, ValueError) as exc:
            return [{'message': str(exc)}]

    for fid in changed:
        row = after['records'][fid]
        if row.get('state') != 'active':
            continue
        if definition_name(row['source']) != row['name']:
            raise ValueError('관용구 이름과 정의 머리가 다릅니다.')
        errors = issues(row['source'], following)
        if errors:
            raise ValueError('저장 전 검사 거절: ' + errors[0]['message'])
    broken = []
    for fid, old in before['records'].items():
        if fid in changed or old.get('state') != 'active':
            continue
        if not issues(old['source'], prior):
            errors = issues(old['source'], following)
            if errors:
                broken.append({'name': old['name'], 'origin': '관용구:' + fid,
                               'code': errors[0].get('code', 'FUNCTION'), 'message': errors[0]['message']})
    if broken:
        broken.sort(key=lambda row: row['name'])
        names = ', '.join(row['name'] for row in broken)
        error = ValueError(f'개정으로 호출자 {names}가 깨집니다: {broken[0]["message"]}. 새 이름 저장→호출자 전환→옛 정의 은퇴 순서로 이행하세요.')
        error.broken_callers = broken
        raise error
    # Persistent external consumers use their existing store, never a new registry.
    from function_consumers import validate_consumers
    validate_consumers(before, after, changed, registry, prior_registry)


def register(name, source, description='', provenance=None, *, expected_revision=None,
             function_id=None, legacy=None, workflow_id=None, origin='user', request_id=None,
             edition=None, reason='', state=None, request_payload=None):
    store.storage_root(for_write=True)
    if request_payload is None:
        request_payload = dict(name=name, source=source, description=description, provenance=provenance,
                               expected_revision=expected_revision, function_id=function_id, legacy=legacy,
                               workflow_id=workflow_id, origin=origin, edition=edition, reason=reason, state=state)
    if request_id:
        prior = store.catalog().get('requests', {}).get(request_id)
        if prior:
            if prior['hash'] != store.digest(request_payload):
                raise ValueError('동일 변경 요청 ID의 내용이 다릅니다.')
            return prior['result']['functions'][0]
    from ibl_edition import require_current
    require_current(source, edition)
    edition = 2
    view = store.snapshot()
    old = store.resolve(name, function_id=function_id, view=view, include_inactive=True)
    if old:
        if workflow_id and old.get('legacy_ids') and workflow_id not in old['legacy_ids'] and workflow_id != old['name']:
            raise ValueError('같은 이름은 다른 저장 ID로 등록할 수 없습니다. 현재 관용구 ID로 개정하세요.')
        # Repeated seeding is a reference attachment, never a blind overwrite.
        if expected_revision is None:
            from ibl_edition import pin_source
            same_source = pin_source(old.get('source', ''), 2) == pin_source(source, 2)
            if same_source and old.get('legacy') == legacy:
                return store.reference(old)
            raise ValueError('관용구가 이미 있습니다. 현재 revision을 읽고 명시적으로 개정하세요.')
    elif expected_revision is not None:
        raise ValueError('개정할 관용구가 없습니다.')
    fid = old['function_id'] if old else (function_id or uuid.uuid4().hex)
    record = {'schema': 1, 'scope_id': store.catalog()['scope_id'], 'function_id': fid, 'name': name, 'edition': edition,
              'source': source, 'source_hash': store.digest(source),
              'description': description, 'origin': (old or {}).get('origin', origin),
              'provenance': copy.deepcopy(provenance or (old or {}).get('provenance') or {})}
    if old and old.get('installation_source_hash'):
        record['installation_source_hash'] = old['installation_source_hash']
    if legacy is not None:
        record['legacy'] = legacy
    if reason:
        record['reason'] = reason
    ids = list((old or {}).get('legacy_ids') or [])
    if workflow_id and workflow_id not in ids:
        ids.append(workflow_id)
    change = {'record': record, 'expected_revision': expected_revision, 'legacy_ids': ids}
    if state:
        change['state'] = state
    return store.publish([change], expected_generation=view['generation'], request_id=request_id, request_payload=request_payload)['functions'][0]


def retire(identifier, expected_revision=None):
    store.storage_root(for_write=True)
    view = store.snapshot()
    row = store.resolve(identifier, view=view, include_inactive=True)
    if row is None:
        row = store.resolve(function_id=identifier, view=view, include_inactive=True)
    if row is None or row.get('state') == 'retired':
        return False
    record = store.revision(row['function_id'], row['revision'])
    record.pop('revision')
    store.publish([{'record': record, 'expected_revision': expected_revision or row['revision'],
                    'state': 'retired', 'legacy_ids': row.get('legacy_ids', [])}],
                  expected_generation=view['generation'])
    return True


def reference_library(refs):
    """Resolve a closed, pinned library; do not fill missing entries from current."""
    from ibl_v2_store import Library
    from ibl_v2_ir import Fault
    from member_runtime import is_member
    if is_member():
        raise ValueError('회원 호출은 동봉한 관용구 정의만 사용할 수 있습니다.')
    if not isinstance(refs, list):
        raise ValueError('function_refs는 관용구 참조 목록이어야 합니다.')
    view, result = store.snapshot(), Library()
    result.references = {}
    result.pinned_view = {'generation': view['generation'], 'records': {}}
    for ref in refs:
        if not isinstance(ref, dict):
            raise ValueError('잘못된 관용구 참조입니다.')
        if ref.get('scope_id') != store.catalog()['scope_id']:
            raise ValueError('다른 소유 범위의 관용구 참조를 찾을 수 없습니다.')
        active = store.resolve(function_id=ref.get('function_id'), view=view)
        if active is None:
            raise ValueError('관용구 참조를 찾을 수 없습니다.')
        row = store.revision(active['function_id'], ref.get('revision'))
        if ref.get('name') != row['name'] or ref.get('edition', 2) != row['edition']:
            raise ValueError('관용구 참조의 이름 또는 판본이 다릅니다.')
        row['state'] = 'active'
        row['legacy_ids'] = active.get('legacy_ids', [])
        result.pinned_view['records'][row['function_id']] = row
        result.add(row['name'], row['source'], '관용구:' + row['function_id'])
        result.references[row['name']] = store.reference(row)
    return result


def compile_current(source, project_path='.', agent_id=None, inputs=None, **kwargs):
    """Registry adapters and native definitions share one immutable read view."""
    from contextlib import nullcontext
    from member_runtime import is_member
    from ibl_v2_store import definitions
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    with nullcontext() if is_member() else store.using(store.snapshot()):
        return compile_program(source, load_registry(project_path, agent_id), inputs or {}, definitions(), **kwargs)
