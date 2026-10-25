"""User-requested IBL helper updates use the cockpit's real staging and receipt path."""
import boot_paths  # noqa: F401
import hashlib
import json
import sys
from types import SimpleNamespace

import pytest

import limb_keys
import principal
import resident_pcs
import resident_store
import thread_context
from test_guestpc_resident_idioms import pc  # noqa: F401
from test_resident_pcs import registry, publish_test_mac_release  # noqa: F401


@pytest.fixture
def update_pc(pc, monkeypatch):
    import runtime_utils
    monkeypatch.setattr(runtime_utils, 'get_base_path', lambda: pc.path)
    dist = pc.path / 'helper/dist'
    dist.mkdir(parents=True)
    (dist / 'indiebiz-helper-win-resident.exe').write_bytes(b'published helper')
    pc.caps = {'os': 'windows', 'arch': 'amd64', 'helper_sha256': '0' * 64,
               'self_update': True, 'go': 'go1.26.5'}
    resident_pcs.sync(pc.rec['key'], 'a' * 32, capabilities=pc.caps)
    with thread_context.actor_context(origin='user'):
        yield pc


def call_update(pc, **extra):
    return pc.handler.execute({'op': 'update', 'target': pc.rec['device_id'], **extra},
                              SimpleNamespace(tool_name='limb_op'))


def test_ibl_and_cockpit_share_update_receipt_and_require_new_helper_report(update_pc):
    pc = update_pc
    receipt = pc('return [self:limb]{op:"update",target:"시험PC"}')
    assert receipt['state'] == 'updating'
    jid = receipt['task_ref']['task_id']
    assert receipt['task_ref']['kind'] == 'guestpc'
    command = json.loads(resident_pcs.sync(pc.rec['key'], 'a' * 32)['jobs'][0]['code'])
    assert command['op'] == 'update'
    assert command['sha256'] == hashlib.sha256(b'published helper').hexdigest()
    assert resident_pcs.transfer_path(command['transfer_id']).read_bytes() == b'published helper'
    # A cockpit click and repeated AI request recover the same running operation.
    assert resident_pcs.update_helper(pc.rec['device_id'])['task_ref'] == receipt['task_ref']
    assert call_update(pc)['task_ref'] == receipt['task_ref']
    assert len(resident_store.history(device=pc.rec['device_id'])['tasks']) == 1
    pc.complete(receipt, {'updated': True, 'restarting': True})
    assert call_update(pc)['state'] == 'updating'
    assert call_update(pc)['task_ref']['task_id'] == jid
    resident_pcs.sync(pc.rec['key'], 'a' * 32,
                      capabilities={**pc.caps, 'helper_sha256': receipt['sha256']})
    assert call_update(pc)['state'] == 'current'
    assert len(resident_store.history(device=pc.rec['device_id'])['tasks']) == 1


def test_ai_update_uses_signed_mac_release_not_caller_payload(update_pc):
    pc = update_pc
    publish_test_mac_release(pc.path, 'mac-amd64', b'signed helper')
    (pc.path / 'helper/dist/indiebiz-helper-mac-amd64').write_bytes(b'adhoc helper')
    resident_pcs.sync(pc.rec['key'], 'a' * 32,
                      capabilities={**pc.caps, 'os': 'darwin'})
    receipt = call_update(pc, sha256='f' * 64, transfer_id='arbitrary', path='/tmp/untrusted')
    assert receipt['sha256'] == hashlib.sha256(b'signed helper').hexdigest()
    command = json.loads(resident_pcs.sync(pc.rec['key'], 'a' * 32)['jobs'][0]['code'])
    assert resident_pcs.transfer_path(command['transfer_id']).read_bytes() == b'signed helper'
    with pytest.raises(ValueError, match='unsupported_resident_operation'):
        resident_pcs.submit(pc.rec['device_id'], {'op': 'update', 'transfer_id': 'arbitrary'})


def test_pending_receipt_keeps_original_release_when_new_release_is_published(update_pc):
    pc = update_pc
    first = call_update(pc)
    (pc.path / 'helper/dist/indiebiz-helper-win-resident.exe').write_bytes(b'next release')
    again = call_update(pc)
    assert again['task_ref'] == first['task_ref']
    assert again['sha256'] == first['sha256']
    assert len(pc.history()) == 1


@pytest.mark.parametrize('origin', [None, 'schedule', 'training', 'test', 'delegation'])
def test_non_user_origin_cannot_submit_update(update_pc, monkeypatch, origin):
    monkeypatch.setattr(thread_context, 'get_task_origin', lambda: origin)
    result = call_update(update_pc, origin='user', user_requested=True)
    assert result['error'] == 'helper_update_user_request_required'
    assert not update_pc.history()


@pytest.mark.parametrize('who', [principal.ANONYMOUS, principal.member('member'), principal.body('body')])
def test_non_owner_cannot_use_ai_or_central_update(update_pc, who):
    with principal.narrow(who):
        assert call_update(update_pc)['error'] == 'helper_update_owner_required'
        with pytest.raises(PermissionError, match='helper_update_owner_required'):
            resident_pcs.update_helper(update_pc.rec['device_id'])
    assert not update_pc.history()


def test_member_runtime_and_repair_copy_do_not_submit(update_pc, monkeypatch):
    import member_runtime
    import repair_context
    monkeypatch.setattr(member_runtime, 'is_member', lambda: True)
    assert call_update(update_pc)['error'] == 'helper_update_owner_required'
    monkeypatch.setattr(member_runtime, 'is_member', lambda: False)
    monkeypatch.setattr(repair_context, 'active', lambda: True)
    assert call_update(update_pc)['error'] == 'helper_update_has_no_repair_sandbox'
    assert not update_pc.history()


@pytest.mark.parametrize('state', ['paused', 'revoked', 'removed', 'manual', 'unknown'])
def test_unavailable_targets_are_not_updated(update_pc, state):
    pc = update_pc
    if state == 'paused':
        limb_keys.resident_update(pc.rec['device_id'], paused=True)
    elif state == 'revoked':
        limb_keys.revoke(pc.rec['device_id'])
    elif state == 'removed':
        limb_keys.resident_update(pc.rec['device_id'], state='removed')
    else:
        caps = {**pc.caps, 'self_update': False} if state == 'manual' else {}
        resident_pcs.sync(pc.rec['key'], 'a' * 32, capabilities=caps)
    assert call_update(pc)['success'] is False
    assert not pc.history()


def test_update_requires_explicit_target(update_pc):
    assert call_update(update_pc, target='')['success'] is False
    assert not update_pc.history()


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
