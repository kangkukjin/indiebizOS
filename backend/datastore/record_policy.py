"""인증 주체와 공간 역할. owner 기본값을 신원 증거로 사용하지 않는다."""
import json
from dataclasses import dataclass

from common.record_contract import fail, expression

_SEAL = object()


@dataclass(frozen=True)
class RecordAuthContext:
    subject: str
    principal_key: str
    executor: str
    space: str = ''
    command: str = ''
    human: bool = False
    seal: object = None


def from_principal(*, executor='ibl', human=False):
    import principal
    p = principal.export_for_snapshot()
    if p is None or p.kind == principal.KIND_ANONYMOUS:
        fail('forbidden', '명시적으로 인증된 실행 문맥이 필요합니다.')
    subject = 'owner' if p.is_owner else f'neighbor:{p.id}'
    if not p.is_owner and (not p.id or p.kind not in {'member', 'portal', 'body'}):
        fail('forbidden', '업무 주체를 확인할 수 없습니다.')
    return RecordAuthContext(subject, p.key(), executor, human=human, seal=_SEAL)


def delegated(subject, space, command):
    """영속 작업 원장만 호출하는 내부 이음매. 요청 JSON으로 공개하지 않는다."""
    return RecordAuthContext(subject, 'delegated', 'record_dispatch', space, command, seal=_SEAL)


def check_auth(auth, space='', command=''):
    if not isinstance(auth, RecordAuthContext) or auth.seal is not _SEAL:
        fail('forbidden', '인증 문맥이 없습니다.')
    if auth.space and auth.space != space or auth.command and auth.command != command:
        fail('forbidden', '위임된 공간·명령 범위 밖입니다.')


def require_owner(auth):
    check_auth(auth)
    if auth.subject != 'owner' or auth.principal_key != 'owner':
        fail('forbidden', '소유자 관리 기능입니다.')


def roles(conn, auth):
    row = conn.execute('SELECT roles FROM memberships WHERE subject=?', (auth.subject,)).fetchone()
    if not row:
        fail('not_found', '업무 공간을 찾을 수 없습니다.')
    return json.loads(row[0])


def allowed(rule, auth, member_roles, record=None, env=None):
    if not isinstance(rule, dict):
        return False
    if set(rule) - {'roles', 'subjects', 'where', 'fields', 'deny_self'}:
        fail('validation', '알 수 없는 접근 정책')
    role_ok = bool(set(rule.get('roles', [])) & set(member_roles))
    subject_ok = auth.subject in rule.get('subjects', [])
    if not role_ok and not subject_ok:
        return False
    context = {**(env or {}), 'actor': {'subject': auth.subject, 'roles': member_roles}, 'record': record or {}}
    if rule.get('where') and expression(rule['where'], context) is not True:
        return False
    for field in rule.get('deny_self', []):
        value = (record or {}).get(field)
        if value == auth.subject or isinstance(value, list) and auth.subject in value:
            return False
    return True


def can_read(definition, collection, record, auth, member_roles):
    spec = definition.get('collections', {}).get(collection)
    return bool(spec and allowed(spec.get('access', {}).get('read'), auth, member_roles, record))


def projection(definition, collection, record, auth, member_roles):
    if not can_read(definition, collection, record, auth, member_roles):
        fail('not_found', '기록을 찾을 수 없습니다.')
    rule = definition['collections'][collection]['access']['read']
    fields = rule.get('fields')
    system = {'_id', '_collection', '_revision', '_definition_revision', '_archived'}
    return {k: v for k, v in record.items() if fields is None or k in fields or k in system}


def artifact_ids(record, fields):
    result = set()
    def visit(value, spec):
        if value is None:
            return
        if spec['type'] == 'artifact_ref' and isinstance(value, str):
            result.add(value)
        elif spec['type'] == 'object' and isinstance(value, dict):
            for k, sub in spec.get('fields', {}).items():
                visit(value.get(k), sub)
        elif spec['type'] == 'array' and isinstance(value, list):
            for item in value:
                visit(item, spec['items'])
    for key, spec in fields.items():
        visit(record.get(key), spec)
    return result


def can_use_artifact(conn, ident, defn, auth, member_roles):
    row = conn.execute('SELECT subject FROM artifacts WHERE id=?', (ident,)).fetchone()
    if not row:
        return False
    if row[0] == auth.subject:
        return True
    from record_store import decode_record
    for stored in conn.execute('SELECT * FROM records WHERE archived=0'):
        record = decode_record(stored)
        collection = record['_collection']
        if can_read(defn, collection, record, auth, member_roles):
            visible = projection(defn, collection, record, auth, member_roles)
            if ident in artifact_ids(visible, defn['collections'][collection]['fields']):
                return True
    return False
