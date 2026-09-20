"""관리 기록 계약: 동시 쓰기·영수증·권한·승인·원자 rollback·복구."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
import principal
from common.record_contract import RecordError, validate_definition
from record_policy import from_principal
from record_store import create_space, transaction, get_record
from record_commands import apply
from record_queries import query
from record_admin import administer


def definition_data():
    access = {'read': {'roles': ['clerk', 'reviewer', 'admin']}}
    return {'contract_version': 1, 'name': '공동 장부', 'collections': {
        'stocks': {'fields': {'sku': {'type': 'string', 'required': True},
                             'available': {'type': 'integer', 'required': True, 'min': 0}},
                   'unique': [['sku']], 'access': access},
        'orders': {'fields': {'stock_id': {'type': 'record_ref', 'collection': 'stocks', 'required': True},
                             'quantity': {'type': 'integer', 'required': True, 'min': 1},
                             'status': {'type': 'string', 'required': True, 'default': 'draft'}},
                   'access': access, 'process': 'ordering'}},
        'processes': {'ordering': {'field': 'status', 'initial': 'draft',
                                  'transitions': {'confirm': {'from': 'draft', 'to': 'confirmed'}}}},
        'commands': {
            'stock': {'input': {'sku': {'type': 'string', 'required': True}, 'available': {'type': 'integer', 'required': True}},
                      'allow': {'roles': ['admin']}, 'change': [{'create': {'collection': 'stocks', 'as': 'stock', 'values': '$input'}}]},
            'order': {'input': {'stock_id': {'type': 'record_ref', 'collection': 'stocks', 'required': True}, 'quantity': {'type': 'integer', 'required': True}},
                      'allow': {'roles': ['clerk', 'admin']}, 'change': [{'create': {'collection': 'orders', 'as': 'order', 'values': '$input'}}]},
            'confirm': {'input': {'order_id': {'type': 'string', 'required': True}}, 'allow': {'roles': ['clerk', 'admin']},
                        'read': {'order': {'collection': 'orders', 'id': '$input.order_id', 'version': 'observed'},
                                 'stock': {'collection': 'stocks', 'id': '$order.stock_id', 'version': 'current'}},
                        'require': [{'expr': '$order.status == "draft"'}, {'expr': '$stock.available >= $order.quantity'}],
                        'change': [{'patch': {'record': 'stock', 'set': {'available': {'expr': '$stock.available - $order.quantity'}}}},
                                   {'transition': {'record': 'order', 'from': 'draft', 'to': 'confirmed'}}]}}}


@pytest.fixture
def owner():
    token = principal.set_transport(principal.OWNER)
    auth = from_principal()
    yield auth
    principal.reset_transport(token)


@pytest.fixture
def space(tmp_path, owner):
    create_space('shop', definition_data(), owner, tmp_path)
    return tmp_path


def command(root, owner, name, values, request_id, expected=None):
    return apply('shop', {'command': name, 'definition_revision': 1, 'input': values,
                         'request_id': request_id, 'expected': expected or []}, owner, root)


def seed(root, auth):
    stock = command(root, auth, 'stock', {'sku': 'a', 'available': 1}, 's')['changed'][0]['id']
    orders = [command(root, auth, 'order', {'stock_id': stock, 'quantity': 1}, f'o{i}')['changed'][0]['id'] for i in range(2)]
    return stock, orders


def test_no_implicit_owner():
    token = principal.set_transport(None)
    try:
        with pytest.raises(RecordError, match='인증'):
            from_principal()
    finally:
        principal.reset_transport(token)


def test_atomic_race_and_replay(space, owner):
    stock, orders = seed(space, owner)
    def confirm(index):
        try:
            return command(space, owner, 'confirm', {'order_id': orders[index]}, f'c{index}',
                           [{'collection': 'orders', 'id': orders[index], 'revision': 1}])
        except RecordError as exc:
            return exc.result()
    with ThreadPoolExecutor(2) as pool:
        result = list(pool.map(confirm, [0, 1]))
    assert sum(r['success'] for r in result) == 1
    winner = next(i for i, r in enumerate(result) if r['success'])
    assert confirm(winner)['replayed']
    with transaction('shop', space) as conn:
        assert get_record(conn, 'stocks', stock)['available'] == 0
        assert conn.execute("SELECT COUNT(*) FROM commits WHERE command='confirm'").fetchone()[0] == 1


def test_duplicate_key_and_unique(space, owner):
    command(space, owner, 'stock', {'sku': 'A', 'available': 1}, 'one')
    with pytest.raises(RecordError) as exc:
        command(space, owner, 'stock', {'sku': 'B', 'available': 1}, 'one')
    assert exc.value.kind == 'duplicate_key'
    with pytest.raises(RecordError):
        command(space, owner, 'stock', {'sku': 'a', 'available': 9}, 'two')
    with transaction('shop', space) as conn:
        assert conn.execute('SELECT COUNT(*) FROM records').fetchone()[0] == 1
        assert conn.execute('SELECT COUNT(*) FROM requests').fetchone()[0] == 1


def test_reference_and_version(space, owner):
    with pytest.raises(RecordError):
        command(space, owner, 'order', {'stock_id': 'absent', 'quantity': 1}, 'bad')
    stock, orders = seed(space, owner)
    with pytest.raises(RecordError) as exc:
        command(space, owner, 'confirm', {'order_id': orders[0]}, 'stale', [{'collection': 'orders', 'id': orders[0], 'revision': 0}])
    assert exc.value.kind == 'conflict'
    with transaction('shop', space) as conn:
        assert get_record(conn, 'stocks', stock)['available'] == 1


def test_member_revocation(space, owner):
    administer('shop', 'membership', {'request_id': 'grant', 'reason': '테스트', 'expected_revision': 1,
                                     'subject': 'neighbor:7', 'roles': ['clerk']}, owner, space)
    token = principal.set_transport(principal.member('7'))
    try:
        member = from_principal()
    finally:
        principal.reset_transport(token)
    assert query('shop', {'op': 'describe'}, member, space)['commands']
    administer('shop', 'membership', {'request_id': 'revoke', 'reason': '테스트', 'expected_revision': 2,
                                     'subject': 'neighbor:7', 'roles': []}, owner, space)
    with pytest.raises(RecordError):
        query('shop', {'op': 'describe'}, member, space)


def test_row_and_field_privacy(tmp_path, owner):
    d = definition_data()
    d['collections']['stocks']['access']['read'] = {'roles': ['admin'], 'fields': ['sku']}
    create_space('shop', d, owner, tmp_path)
    command(tmp_path, owner, 'stock', {'sku': 'A', 'available': 9}, 'one')
    r = query('shop', {'op': 'query', 'collection': 'stocks'}, owner, tmp_path)
    assert 'available' not in r['items'][0]
    with pytest.raises(RecordError):
        query('shop', {'op': 'query', 'collection': 'stocks', 'where': {'available': 9}}, owner, tmp_path)


def test_export_restore(space, owner):
    from record_assets import export_space, import_space
    seed(space, owner)
    exported = export_space('shop', owner, space)
    assert import_space('restored', exported, owner, space)['recovery_required']
    with pytest.raises(RecordError):
        apply('restored', {'command': 'stock', 'definition_revision': 1, 'input': {'sku': 'z', 'available': 9}, 'expected': [], 'request_id': 'new'}, owner, space)


def test_unknown_remote_lease(space, owner):
    from record_tasks import enqueue
    from record_dispatch import tick, register_adapter
    sent = []
    register_adapter('unsafe_test', lambda *a: sent.append(a), idempotent=False)
    with transaction('shop', space, write=True) as conn:
        enqueue(conn, 'effect_test', 'effect', {'config': {'adapter': 'unsafe_test'}, 'payload': {}}, owner.subject, 1)
        conn.execute("UPDATE deliveries SET state='leased',lease_until=0")
    tick('shop', space)
    assert not sent
    with transaction('shop', space) as conn:
        assert conn.execute('SELECT state FROM deliveries').fetchone()[0] == 'unknown'


def approval_definition():
    d = definition_data()
    d['processes']['ordering']['transitions'].update({
        'submit': {'from': 'draft', 'to': 'reviewing',
                   'task': {'roles': ['reviewer'], 'command': 'approve', 'quorum': 2}},
        'approve': {'from': 'reviewing', 'to': 'approved'}})
    read = {'order': {'collection': 'orders', 'id': '$input.order_id', 'version': 'observed'}}
    d['commands']['submit'] = {'input': {'order_id': {'type': 'string', 'required': True}},
                               'allow': {'roles': ['admin']}, 'read': read,
                               'change': [{'transition': {'record': 'order', 'from': 'draft', 'to': 'reviewing'}}]}
    d['commands']['approve'] = {'input': {'order_id': {'type': 'string', 'required': True},
                                        'task_id': {'type': 'string', 'required': True},
                                        'task_revision': {'type': 'integer', 'required': True}},
                                'allow': {'roles': ['reviewer', 'admin']}, 'read': read,
                                'change': [{'task': {'op': 'complete', 'id': '$input.task_id', 'revision': '$input.task_revision'}},
                                           {'transition': {'record': 'order', 'from': 'reviewing', 'to': 'approved'}}]}
    return d


def member_auth(n):
    token = principal.set_transport(principal.member(str(n)))
    try:
        return from_principal()
    finally:
        principal.reset_transport(token)


def test_quorum_and_same_person_different_login(tmp_path, owner):
    create_space('shop', approval_definition(), owner, tmp_path)
    stock, orders = seed(tmp_path, owner)
    expected = [{'collection': 'orders', 'id': orders[0], 'revision': 1}]
    command(tmp_path, owner, 'submit', {'order_id': orders[0]}, 'submit', expected)
    for i, n in enumerate([2, 3]):
        administer('shop', 'membership', {'request_id': f'grant{n}', 'reason': '검토자', 'expected_revision': i + 1,
                                         'subject': f'neighbor:{n}', 'roles': ['reviewer']}, owner, tmp_path)
    one, two = member_auth(2), member_auth(3)
    task = query('shop', {'op': 'inbox'}, one, tmp_path)['items'][0]
    expected[0]['revision'] = 2
    inputs = {'order_id': orders[0], 'task_id': task['id'], 'task_revision': 1}
    command(tmp_path, one, 'approve', inputs, 'vote1', expected)
    assert query('shop', {'op': 'detail', 'collection': 'orders', 'id': orders[0]}, one, tmp_path)['items'][0]['status'] == 'reviewing'
    token = principal.set_transport(principal.portal('2'))
    try:
        same_person = from_principal()
    finally:
        principal.reset_transport(token)
    with pytest.raises(RecordError, match='이미 처리'):
        command(tmp_path, same_person, 'approve', {**inputs, 'task_revision': 2}, 'again', expected)
    command(tmp_path, two, 'approve', {**inputs, 'task_revision': 2}, 'vote2', expected)
    assert query('shop', {'op': 'detail', 'collection': 'orders', 'id': orders[0]}, two, tmp_path)['items'][0]['status'] == 'approved'


def test_old_definition_pinned_current_permissions(space, owner):
    _, orders = seed(space, owner)
    d = definition_data()
    d['commands']['confirm']['require'].append({'expr': 'false'})
    administer('shop', 'publish', {'request_id': 'publish', 'reason': '새 규칙', 'expected_revision': 1,
                                  'definition': d}, owner, space)
    # 이미 시작된 인스턴스에는 옛 절차를 적용하지만 최신 권한을 적용한다.
    command(space, owner, 'confirm', {'order_id': orders[0]}, 'old', [{'collection': 'orders', 'id': orders[0], 'revision': 1}])
    with pytest.raises(RecordError) as exc:
        command(space, owner, 'stock', {'sku': 'new', 'available': 2}, 'new')
    assert exc.value.kind == 'definition_changed'


def _process_confirm(root, order, queue):
    token = principal.set_transport(principal.OWNER)
    try:
        result = command(root, from_principal(), 'confirm', {'order_id': order}, 'p_' + order,
                         [{'collection': 'orders', 'id': order, 'revision': 1}])
        queue.put(result['success'])
    except RecordError:
        queue.put(False)
    finally:
        principal.reset_transport(token)


def test_separate_processes_cannot_oversell(space, owner):
    import multiprocessing
    _, orders = seed(space, owner)
    context = multiprocessing.get_context('spawn')
    queue = context.Queue()
    processes = [context.Process(target=_process_confirm, args=(space, order, queue)) for order in orders]
    for process in processes:
        process.start()
    for process in processes:
        process.join(15)
        assert process.exitcode == 0
    assert sum(queue.get(timeout=2) for _ in processes) == 1


def test_partial_mutation_rolls_back_everything(tmp_path, owner):
    d = definition_data()
    d['commands']['confirm']['change'].append({'patch': {'record': 'stock', 'set': {'available': -1}}})
    create_space('shop', d, owner, tmp_path)
    stock, orders = seed(tmp_path, owner)
    with pytest.raises(RecordError):
        command(tmp_path, owner, 'confirm', {'order_id': orders[0]}, 'broken', [{'collection': 'orders', 'id': orders[0], 'revision': 1}])
    with transaction('shop', tmp_path) as conn:
        assert get_record(conn, 'stocks', stock)['available'] == 1
        assert get_record(conn, 'orders', orders[0])['status'] == 'draft'
        assert conn.execute("SELECT COUNT(*) FROM commits WHERE command='confirm'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM requests WHERE request_id='broken'").fetchone()[0] == 0


def test_invalid_contract_fails_before_publication():
    d = definition_data()
    d['commands']['stock']['change'] = [{'sql': 'delete'}]
    with pytest.raises(RecordError):
        validate_definition(d)
    d = definition_data()
    d['commands']['stock']['emit'] = [{'event': 'again'}]
    d['subscriptions'] = {'again': [{'command': 'stock'}]}
    with pytest.raises(RecordError, match='순환'):
        validate_definition(d)


def test_stale_cursor_rejected_after_write(space, owner):
    seed(space, owner)
    first = query('shop', {'op': 'query', 'collection': 'orders', 'limit': 1}, owner, space)
    command(space, owner, 'stock', {'sku': 'new', 'available': 1}, 'change')
    with pytest.raises(RecordError):
        query('shop', {'op': 'query', 'collection': 'orders', 'limit': 1, 'cursor': first['cursor']}, owner, space)


def test_task_cannot_approve_another_record(tmp_path, owner):
    create_space('shop', approval_definition(), owner, tmp_path)
    _, orders = seed(tmp_path, owner)
    for index, ident in enumerate(orders):
        command(tmp_path, owner, 'submit', {'order_id': ident}, f'submit{index}',
                [{'collection': 'orders', 'id': ident, 'revision': 1}])
    administer('shop', 'membership', {'request_id': 'grant', 'reason': '검토자', 'expected_revision': 1,
                                     'subject': 'neighbor:2', 'roles': ['reviewer']}, owner, tmp_path)
    reviewer = member_auth(2)
    task = next(t for t in query('shop', {'op': 'inbox'}, reviewer, tmp_path)['items'] if t['record_id'] == orders[0])
    with pytest.raises(RecordError, match='검토 대상이 다릅니다'):
        command(tmp_path, reviewer, 'approve', {'order_id': orders[1], 'task_id': task['id'], 'task_revision': 1}, 'wrong',
                [{'collection': 'orders', 'id': orders[1], 'revision': 2}])
    assert query('shop', {'op': 'inbox'}, reviewer, tmp_path)['items'][0]['revision'] == 1


def test_artifact_id_is_not_permission(tmp_path, owner):
    from record_assets import upload, download
    d = definition_data()
    d['collections']['stocks']['fields']['attachment'] = {'type': 'artifact_ref'}
    d['collections']['stocks']['fields']['note'] = {'type': 'string'}
    d['commands']['stock']['input'] = copy.deepcopy(d['collections']['stocks']['fields'])
    d['commands']['stock']['allow'] = {'roles': ['admin', 'clerk']}
    create_space('shop', d, owner, tmp_path)
    asset = upload('shop', b'private', 'file.txt', owner, tmp_path)['items'][0]['id']
    administer('shop', 'membership', {'request_id': 'grant', 'reason': '회원', 'expected_revision': 1,
                                     'subject': 'neighbor:2', 'roles': ['clerk']}, owner, tmp_path)
    clerk = member_auth(2)
    command(tmp_path, clerk, 'stock', {'sku': 'text', 'available': 1, 'note': asset}, 'text')
    with pytest.raises(RecordError):
        download('shop', asset, clerk, tmp_path)
    with pytest.raises(RecordError):
        command(tmp_path, clerk, 'stock', {'sku': 'private', 'available': 1, 'attachment': asset}, 'theft')
    command(tmp_path, owner, 'stock', {'sku': 'shared', 'available': 1, 'attachment': asset}, 'share')
    assert download('shop', asset, clerk, tmp_path)[0] == b'private'


def test_schema_migration_atomic_with_history(space, owner):
    stock, _ = seed(space, owner)
    administer('shop', 'pause', {'request_id': 'pause', 'reason': '이전', 'expected_revision': 1, 'paused': True}, owner, space)
    d = definition_data()
    d['collections']['stocks']['fields']['category'] = {'type': 'string', 'required': True}
    args = {'request_id': 'migration', 'reason': '필드 추가', 'expected_revision': 2, 'definition': d, 'transforms': {}}
    with pytest.raises(RecordError):
        administer('shop', 'migrate', args, owner, space)
    with transaction('shop', space) as conn:
        assert get_record(conn, 'stocks', stock)['_revision'] == 1
        assert conn.execute('SELECT COUNT(*) FROM definitions').fetchone()[0] == 1
    args['transforms'] = {'stocks': {'set': {'category': 'general'}}}
    assert administer('shop', 'migrate', args, owner, space)['definition_revision'] == 2
    assert administer('shop', 'migrate', args, owner, space)['definition_revision'] == 2
    history = query('shop', {'op': 'history', 'collection': 'stocks', 'id': stock}, owner, space)['items']
    assert history[0]['command'] == 'admin:migrate'
    assert history[0]['after']['category'] == 'general'
    assert 'category' not in history[0]['before']


def _crash_command(root, before_commit):
    import os
    import record_tasks
    token = principal.set_transport(principal.OWNER)
    auth = from_principal()
    if before_commit:
        record_tasks.persist_tasks = lambda *a: os._exit(17)
    command(root, auth, 'stock', {'sku': 'crash', 'available': 1}, 'crash')
    os._exit(18)


@pytest.mark.parametrize('before_commit', [True, False])
def test_process_crash_before_and_after_commit(space, owner, before_commit):
    import multiprocessing
    child = multiprocessing.get_context('spawn').Process(target=_crash_command, args=(space, before_commit))
    child.start()
    child.join(timeout=10)
    assert child.exitcode == (17 if before_commit else 18)
    with transaction('shop', space) as conn:
        assert conn.execute('SELECT COUNT(*) FROM records').fetchone()[0] == (0 if before_commit else 1)
        assert conn.execute('SELECT COUNT(*) FROM requests').fetchone()[0] == (0 if before_commit else 1)
    result = command(space, owner, 'stock', {'sku': 'crash', 'available': 1}, 'crash')
    assert result['replayed'] is (not before_commit)


def test_revoked_effect_role_blocks_send(tmp_path, owner):
    from record_dispatch import tick, register_adapter
    d = definition_data()
    d['commands']['stock']['allow'] = {'roles': ['admin', 'clerk']}
    d['commands']['stock']['emit'] = [{'effect': 'send', 'payload': {'sku': '$input.sku'}}]
    d['effects'] = {'send': {'adapter': 'revoke_test'}}
    create_space('shop', d, owner, tmp_path)
    administer('shop', 'membership', {'request_id': 'grant', 'reason': '담당', 'expected_revision': 1,
                                     'subject': 'neighbor:2', 'roles': ['clerk']}, owner, tmp_path)
    command(tmp_path, member_auth(2), 'stock', {'sku': 'a', 'available': 1}, 'new')
    administer('shop', 'membership', {'request_id': 'revoke', 'reason': '담당 해제', 'expected_revision': 2,
                                     'subject': 'neighbor:2', 'roles': ['reviewer']}, owner, tmp_path)
    sent = []
    register_adapter('revoke_test', lambda *args: sent.append(args))
    tick('shop', tmp_path)
    assert sent == []
    with transaction('shop', tmp_path) as conn:
        assert conn.execute('SELECT state FROM deliveries').fetchone()[0] == 'blocked'


def test_injected_runtime_metadata_and_explicit_principal(space, owner, monkeypatch):
    import importlib.util
    from pathlib import Path
    import record_store
    import vocabulary_state
    path = Path(__file__).parents[1] / 'data/packages/installed/tools/record-ops/handler.py'
    spec = importlib.util.spec_from_file_location('record_handler_test', path)
    handler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(handler)
    monkeypatch.setattr(record_store, 'root_path', lambda: space)
    monkeypatch.setattr(vocabulary_state, 'is_active', lambda *a, **k: True)
    assert handler.execute({'op': 'describe', 'space': 'shop', '_prev_result': {}, '_wf_stack': []}, None)['success']
    assert not handler.execute({'op': 'describe', 'space': 'shop', 'actor': 'owner'}, None)['success']
    from ibl_engine import execute_ibl
    from ibl_parser import parse
    import ibl_registry
    # 활성 선택을 테스트에서 바꿨으므로 같은 revision의 과거 사전을 재사용하지 않는다.
    monkeypatch.setattr(ibl_registry, '_nodes', None)
    monkeypatch.setattr(ibl_registry, '_nodes_revision', None)
    result = execute_ibl(parse('[self:record]{op:"describe",space:"shop"}')[0], '')
    assert result.get('success'), result
    assert result['items']


def test_shared_capability_closes_when_dependency_changes(tmp_path, monkeypatch):
    import hashlib
    import member_profile
    pkg = tmp_path / 'package'
    pkg.mkdir()
    (pkg / 'handler.py').write_text('pass\n')
    dependency = tmp_path / 'permission.py'
    dependency.write_text('allowed = False\n')
    monkeypatch.setattr(member_profile, '_package_dir', lambda *a: pkg)
    entry = {'resource_scope': 'app_shared', 'package': 'test', 'path_audited': {
        'impl': member_profile.handler_fingerprint(pkg),
        'dependencies': {'permission.py': hashlib.sha256(dependency.read_bytes()).hexdigest()}}}
    assert member_profile.fingerprint_ok(entry, tmp_path)
    dependency.write_text('allowed = True\n')
    assert not member_profile.fingerprint_ok(entry, tmp_path)


def test_timeout_survives_partial_vote_and_cancels_task(tmp_path, owner):
    from record_dispatch import tick
    d = approval_definition()
    d['processes']['ordering']['transitions']['submit']['task'].update(
        due_seconds=0, timeout_command='expire', timeout_input={'order_id': '$order._id', 'task_id': '$task.id', 'task_revision': '$task.revision'})
    d['processes']['ordering']['transitions']['expire'] = {'from': 'reviewing', 'to': 'expired'}
    d['commands']['expire'] = copy.deepcopy(d['commands']['approve'])
    d['commands']['expire']['allow'] = {'roles': ['admin']}
    d['commands']['expire']['change'][0]['task']['op'] = 'cancel'
    d['commands']['expire']['change'][1]['transition']['to'] = 'expired'
    create_space('shop', d, owner, tmp_path)
    _, orders = seed(tmp_path, owner)
    command(tmp_path, owner, 'submit', {'order_id': orders[0]}, 'submit', [{'collection': 'orders', 'id': orders[0], 'revision': 1}])
    administer('shop', 'membership', {'request_id': 'grant', 'reason': '검토자', 'expected_revision': 1,
                                     'subject': 'neighbor:2', 'roles': ['reviewer']}, owner, tmp_path)
    reviewer = member_auth(2)
    task = query('shop', {'op': 'inbox'}, reviewer, tmp_path)['items'][0]
    command(tmp_path, reviewer, 'approve', {'order_id': orders[0], 'task_id': task['id'], 'task_revision': 1}, 'vote',
            [{'collection': 'orders', 'id': orders[0], 'revision': 2}])
    tick('shop', tmp_path)
    detail = query('shop', {'op': 'detail', 'collection': 'orders', 'id': orders[0]}, owner, tmp_path)['items'][0]
    assert detail['status'] == 'expired'
    assert query('shop', {'op': 'inbox'}, reviewer, tmp_path)['items'] == []
    history = query('shop', {'op': 'history', 'collection': 'orders', 'id': orders[0]}, owner, tmp_path)['items']
    assert any(h.get('kind') == 'task' and h['subject'] == 'neighbor:2' and h['after']['approvals'] == 1 for h in history)


def test_remote_success_survives_invalid_followup(tmp_path, owner):
    from record_dispatch import tick, register_adapter
    d = definition_data()
    d['commands']['stock']['emit'] = [{'effect': 'send', 'payload': {}}]
    d['commands']['after_send'] = {'allow': {'roles': ['admin']}, 'change': []}
    d['effects'] = {'send': {'adapter': 'followup_test', 'success_command': 'after_send', 'success_input': {'missing': '$result.absent'}}}
    create_space('shop', d, owner, tmp_path)
    result = command(tmp_path, owner, 'stock', {'sku': 'a', 'available': 1}, 'send')
    register_adapter('followup_test', lambda *a: {'status': 'succeeded'})
    tick('shop', tmp_path)
    with transaction('shop', tmp_path) as conn:
        states = dict(conn.execute('SELECT id,state FROM deliveries').fetchall())
    effect_id = result['effects'][0]['id']
    assert states[effect_id] == 'succeeded'
    assert states[effect_id + '_result'] == 'blocked'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
