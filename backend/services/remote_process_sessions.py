"""Resident PTY sessions: durable hub receipts and helper-owned process lifetime."""
import base64
import json
import time
import uuid

from coding_store import CodingStore, fingerprint
from file_changes import attribution
import resident_pcs


def _store():
    return CodingStore()


def _row(task_id):
    import principal
    if not principal.is_owner(): raise PermissionError('프로세스 제어는 소유자 전용입니다')
    row = _store().get('remote_process', task_id)
    rec = resident_pcs.resolve(row['device'])
    if row.get('installation_id') != rec['registration'].get('installation_id'):
        raise PermissionError('헬퍼 설치 세대가 변경됐습니다')
    return row


def start(target, command, cwd=None, request_id=None, io='pty', **kwargs):
    import principal
    if not principal.is_owner(): raise PermissionError('프로세스 세션은 소유자 전용입니다')
    if not isinstance(command, str) or not command.strip(): raise ValueError('cmd 필수')
    if io != 'pty': raise ValueError('resident process session은 PTY만 지원합니다')
    if any(kwargs.get(k) for k in ('elevate', 'stdin', 'reset')):
        raise ValueError('session은 elevate/stdin/reset을 지원하지 않습니다. 입력은 control로 전달하세요')
    rec = resident_pcs.resolve(target)
    if rec['registration'].get('capabilities', {}).get('process_session') != 1:
        raise ValueError('process_session/1을 지원하는 헬퍼로 갱신하세요')
    db = _store(); owner = attribution()
    from file_changes import validate_attribution
    validate_attribution({'attribution': owner})
    signature = fingerprint({'command': command, 'cwd': cwd, 'device': rec['device_id']})
    with db.lock('remote-process-start'):
        if request_id:
            for row in db.list('remote_process'):
                if row.get('request_id') == request_id and row['attribution'] == owner:
                    if row['signature'] != signature: raise ValueError('request_id 충돌')
                    if not row.get('job'):
                        _submit(db, row)
                    return receipt(row)
        sid = uuid.uuid4().hex
        row = {'id': 'remoteprocess_' + sid, 'device': rec['device_id'], 'generation': uuid.uuid4().hex,
               'command': command, 'cwd': cwd, 'request_id': request_id, 'signature': signature,
               'state': 'queued', 'created_at': time.time(), 'attribution': owner,
               'installation_id': rec['registration']['installation_id'],
               'output': '', 'offset': 0, 'end': 0, 'inputs': {}, 'lease': None}
        # Persist before submission: retry with the same helper request id never starts two shells.
        db.save('remote_process', row)
        _submit(db, row)
        return receipt(row)


def _submit(db, row):
    sid = row['id'].removeprefix('remoteprocess_')
    job = resident_pcs.submit(row['device'], {'op': 'terminal', 'terminal_id': sid,
        'process_session': True, 'cmd': row['command'], 'cwd': row['cwd'] or '',
        'cols': 100, 'rows': 30, 'timeout': 86400}, 'process-' + sid, allow_terminal=True)
    row['job'] = job['job_id']
    db.save('remote_process', row)


def receipt(row):
    import task_receipts as T
    return T.receipt('remote_process', row['id'], generation=row['generation'],
                     capabilities={'io': 'pty', 'input': True, 'resize': True, 'interrupt': True,
                                   'eof': True, 'cancel': True, 'restart_reconnect': True})


def attach(task_id, device):
    db = _store()
    with db.lock(task_id):
        row = _row(task_id)
        if row['device'] != device: raise PermissionError('다른 PC의 프로세스입니다')
        if row['state'] in ('succeeded', 'failed', 'cancelled'):
            return {'type': 'complete'}
        row['transport'] = uuid.uuid4().hex
        row['state'] = 'running'; row['heartbeat'] = time.time(); db.save('remote_process', row)
        return {'type': 'ready', 'cursor': row['end'], 'transport': row['transport']}


def receive(task_id, message, transport=None):
    db = _store()
    with db.lock(task_id):
        row = _row(task_id); row['heartbeat'] = time.time()
        if transport and row.get('transport') != transport:
            raise PermissionError('교체된 연결입니다')
        if message['type'] == 'output':
            data = base64.b64decode(message['data'], validate=True)
            if len(data) > 65536: raise ValueError('출력 프레임 초과')
            offset = int(message['offset'])
            if offset > row['end']:
                row['offset'] = offset; row['end'] = offset; row['output'] = ''
            skip = max(0, row['end'] - offset)
            output = base64.b64decode(row['output']) + data[skip:]
            row['end'] += len(data[skip:]); output = output[-1048576:]
            row['offset'] = row['end'] - len(output); row['output'] = base64.b64encode(output).decode()
        elif message['type'] == 'ack':
            item = row['inputs'].get(message.get('request_id'))
            if item:
                item['result'] = {'accepted': True, 'delivery': message.get('delivery', 'delivery_unknown'),
                                  'bytes_written': message.get('bytes_written', 0)}
                item.pop('message', None)
        elif message['type'] == 'exit':
            row.update(state='cancelled' if row.get('cancel_requested') else 'succeeded' if message['code'] == 0 else 'failed',
                       exit_code=message['code'], ended_at=time.time())
        db.save('remote_process', row)


def take(task_id, transport=None):
    db = _store()
    with db.lock(task_id):
        row = _row(task_id); messages = []
        if transport and row.get('transport') != transport:
            raise PermissionError('교체된 연결입니다')
        row['heartbeat'] = time.time()
        for rid, item in row['inputs'].items():
            if item['result']['delivery'] == 'queued':
                # Mark ambiguous before transport, never replay an unacknowledged write.
                item['result']['delivery'] = 'delivery_unknown'
                messages.append({**item['message'], 'request_id': rid})
        db.save('remote_process', row)
        return messages


def control(ref, params):
    db = _store(); tid = ref['task_id']
    with db.lock(tid):
        row = _row(tid)
        if params.get('generation') != row['generation']: raise ValueError('generation 불일치')
        rid = params.get('request_id')
        if not rid: raise ValueError('request_id 필수')
        signature = fingerprint(params)
        prior = row['inputs'].get(rid)
        if prior:
            if prior['signature'] != signature: raise ValueError('request_id 충돌')
            return {'success': True, **prior['result'], 'cached': True}
        if row['state'] not in ('queued', 'running'): raise ValueError('종료한 프로세스입니다')
        if len(row['inputs']) >= 10000: raise ValueError('이 세션의 입력 접수 한도에 도달했습니다')
        queued = [v for v in row['inputs'].values() if v['result']['delivery'] == 'queued']
        if len(queued) >= 128 or sum(len(v.get('message', {}).get('data', '')) for v in queued) > 87384:
            raise ValueError('입력 대기열 backpressure')
        actor = params.get('actor', 'ai')
        lease = row.get('lease')
        if params.get('action') != 'cancel' and lease and lease['actor'] != actor and lease['until'] > time.time():
            raise ValueError('다른 작성자가 입력을 제어 중입니다')
        row['lease'] = {'actor': actor, 'until': time.time() + 30}
        action = params.get('action'); message = {'type': action}
        if action == 'input':
            if ('text' in params) == ('base64' in params): raise ValueError('text 또는 base64 하나가 필요합니다')
            data = base64.b64decode(params['base64'], validate=True) if 'base64' in params else params['text'].encode()
            if params.get('newline'): data += b'\r'
            if len(data) > 65536: raise ValueError('입력은 64KiB 이하입니다')
            if sum(len(v.get('message', {}).get('data', '')) for v in queued) + len(base64.b64encode(data)) > 87384:
                raise ValueError('입력 대기열 backpressure')
            message['data'] = base64.b64encode(data).decode()
        elif action == 'resize':
            from resident_terminal import dimensions
            message['cols'], message['rows'] = dimensions(params.get('cols'), params.get('rows'))
        elif action not in ('eof', 'interrupt', 'cancel'): raise ValueError('미지원 control')
        row['inputs'][rid] = {'signature': signature, 'message': message,
                              'result': {'accepted': True, 'delivery': 'queued'}}
        if action == 'cancel': row['cancel_requested'] = True
        db.save('remote_process', row)
        return {'success': True, 'accepted': True, 'delivery': 'queued', 'request_id': rid}


def status(ref):
    import task_receipts as T
    row = _row(ref['task_id'])
    if row['state'] in ('queued', 'running') and row.get('job'):
        import resident_store
        tasks = resident_store.history(job=row['job'])['tasks']
        if tasks and tasks[0]['state'] in ('cancelled', 'failed', 'unknown', 'expired'):
            row['state'] = {'unknown': 'interrupted', 'expired': 'failed'}.get(tasks[0]['state'], tasks[0]['state'])
    cursor = int(ref.get('_history_cursor') or 0)
    limit = max(1, min(int(ref.get('_limit_bytes') or 65536), 262144))
    start = max(cursor, row['offset']); data = base64.b64decode(row['output'])[start-row['offset']:start-row['offset']+limit]
    value = {'output': [{'stream': 'combined', 'text': data.decode(errors='replace'), 'base64': base64.b64encode(data).decode()}],
             'generation': row['generation'], 'history_cursor': start + len(data), 'gap': cursor < row['offset'],
             'connected': time.time() - row.get('heartbeat', 0) < 15,
             'capabilities': receipt(row)['capabilities']}
    return T.view(ref, row['state'], progress=value, result=value, **value, accepted_at=row['created_at'], ended_at=row.get('ended_at'))


def cancel(ref):
    row = _row(ref['task_id'])
    if row['state'] not in ('queued', 'running'):
        return status(ref)
    control(ref, {'action': 'cancel', 'generation': row['generation'], 'request_id': 'cancel'})
    import resident_store
    resident_store.cancel(row['job'], row['device'])
    import task_receipts as T
    return T.view(ref, T.CANCEL_REQUESTED)
