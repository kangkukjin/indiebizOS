"""외부 클라이언트 담당 에이전트의 전송 독립 요청/전달 계약.

신원은 인증된 principal에서만 취득. 앱 선언 해소는 표면의 책임이며 실행은 MemberSessionManager.
재전송 원장은 유효 세션 동안 RAM에만 둔다. 프로세스 재시작은 새 epoch로 구별한다.
"""
import base64
import copy
import hashlib
import json
import re
import threading
import time
import uuid

VERSION = 1
EPOCH = uuid.uuid4().hex
LOCK = threading.RLock()
RECORDS = {}
TTL = 1800
MAX_RECORDS = 512
MAX_RESULT_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024


def _identity():
    import principal
    p = principal.current()
    if p.kind != principal.KIND_MEMBER:
        raise PermissionError('인증된 외부 클라이언트가 필요합니다')
    return p, (p.id, p.device_id)


def _key(request_id):
    p, identity = _identity()
    if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', request_id):
        raise ValueError('invalid_request_id')
    return p, (*identity, request_id)


def _sweep():
    now = time.monotonic()
    for key, row in list(RECORDS.items()):
        if row['state'] != 'running' and now - row['updated'] > TTL:
            del RECORDS[key]


def run(envelope, resolved, *, name='', body_session='', on_event=None, manager=None):
    """같은 request_id 재전송은 같은 결과. 다른 본문 충돌·진행 중 재실행은 거절한다."""
    from member_session import MemberSessionManager
    p, key = _key(envelope['request_id'])
    if envelope.get('version') != VERSION:
        return {'success': False, 'error': 'unsupported_client_version'}
    if envelope.get('epoch') and envelope['epoch'] != EPOCH:
        return {'success': False, 'error': 'server_restarted_result_unknown'}
    digest = hashlib.sha256(json.dumps(envelope, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    with LOCK:
        _sweep()
        old = RECORDS.get(key)
        if old:
            if old['digest'] != digest or old['body_session'] != body_session:
                return {'success': False, 'error': 'request_id_conflict'}
            if old['state'] == 'running':
                return {'success': False, 'error': 'request_in_progress'}
            return copy.deepcopy(old['result'])
        if len(RECORDS) >= MAX_RECORDS or sum(r.get('bytes', 0) for r in RECORDS.values()) >= MAX_TOTAL_BYTES - MAX_RESULT_BYTES:
            return {'success': False, 'error': 'client_request_capacity'}
        RECORDS[key] = {'digest': digest, 'state': 'running', 'bytes': MAX_RESULT_BYTES, 'updated': time.monotonic(), 'body_session': body_session}
    def emit(kind, **data):
        if on_event:
            on_event({'type': kind, 'version': VERSION, 'request_id': envelope['request_id'],
                      'conversation_id': envelope['conversation_id'], **data})
    emit('accepted')
    try:
        result = (manager or MemberSessionManager.instance()).turn(
            p.id, p.device_id, p.level, name, resolved.get('message') or '앱 실행',
            local_task_id=envelope['conversation_id'], code=resolved.get('code'),
            on_event=lambda event: emit(event['type'] if event.get('type') in {'client_action_required', 'delivered'} else 'progress', detail=event), body_session=body_session,
            client_context={'request_id': envelope['request_id'], 'capabilities': envelope.get('capabilities', {}),
                            'attachments': envelope.get('attachments', []), 'workflow': resolved.get('workflow')})
        result.update(agent_role='client_agent', output_owner='requester', version=VERSION, epoch=EPOCH, request_id=envelope['request_id'],
                      conversation_id=envelope['conversation_id'])
        if result.get('input_required'):
            result['delivery'] = 'input_required'
        elif result.get('success') and resolved.get('output'):
            content = str(result.get('response') or '').encode()
            if not content or len(content) > MAX_RESULT_BYTES // 2:
                result.update(success=False, error='산출물이 비었거나 크기 제한을 초과했습니다')
            else:
                artifact = {'id': uuid.uuid4().hex, 'name': 'report.md', 'mime': 'text/markdown',
                            'size': len(content), 'sha256': hashlib.sha256(content).hexdigest(),
                            'data': base64.b64encode(content).decode()}
                result.update(artifacts=[artifact], delivery='result_ready', saved=False)
        elif result.get('success'):
            result['delivery'] = 'delivered' if result.get('files') else 'response_ready'
        else:
            result['delivery'] = 'error'
        emit(result['delivery'], question=result.get('input_required'), artifacts=[{k: v for k, v in a.items() if k != 'data'} for a in result.get('artifacts', [])])
    except Exception:
        result = {'success': False, 'error': '클라이언트 요청을 완료하지 못했습니다',
                  'request_id': envelope['request_id'], 'epoch': EPOCH}
        emit('error')
    serialized = json.dumps(result, ensure_ascii=False, default=str).encode()
    if len(serialized) > MAX_RESULT_BYTES:
        result = {'success': False, 'error': 'client_result_too_large', 'request_id': envelope['request_id']}
        serialized = json.dumps(result).encode()
    with LOCK:
        RECORDS[key].update(state='finished', result=copy.deepcopy(result), bytes=len(serialized), updated=time.monotonic())
    return result


def receipt(request_id, artifact_id, sha256, size, *, body_session='', epoch=''):
    _, key = _key(request_id)
    with LOCK:
        _sweep()
        row = RECORDS.get(key)
        if epoch != EPOCH or not row or row['body_session'] != body_session:
            return {'success': False, 'error': 'delivery_unknown'}
        result = row.get('result', {})
        artifact = next((a for a in result.get('artifacts', []) if a['id'] == artifact_id), None)
        if not artifact or artifact['sha256'] != sha256 or artifact['size'] != size:
            return {'success': False, 'error': 'artifact_receipt_mismatch'}
        artifact['delivered'] = True
        delivered = all(a.get('delivered') for a in result['artifacts'])
        result.update(delivery='delivered' if delivered else 'result_ready', saved=delivered)
        row['updated'] = time.monotonic()
        return {'success': True, 'type': result['delivery'], 'request_id': request_id, 'artifact_id': artifact_id}
