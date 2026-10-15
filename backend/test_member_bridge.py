"""A member device must honor an explicitly requested content fingerprint."""
import boot_paths  # noqa: F401
import pytest
import member_bridge
import member_runtime
import threading


@pytest.mark.parametrize('items', [[{'name': 'a'}], [{'sha256': None}],
                                  [{'sha256': 'not-a-digest'}], None])
def test_missing_or_invalid_requested_fingerprint_fails(monkeypatch, items):
    monkeypatch.setattr(member_bridge, 'request', lambda command: {'items': items})
    result = member_bridge.execute({'limb_op': {'op': 'list', 'hash': '$hash'}}, {'hash': True})
    assert result['success'] is False and result['error_type'] == 'unsupported'


def test_fingerprint_option_reaches_body_and_plain_list_stays_compatible(monkeypatch):
    calls = []
    rows = [{'name': 'a', 'sha256': 'a' * 64}, {'name': 'folder', 'is_dir': True, 'sha256': None}]
    def request(command):
        calls.append(command)
        return {'files': rows if command.get('hash') else [{'name': 'a'}]}
    monkeypatch.setattr(member_bridge, 'request', request)
    entry = {'limb_op': {'op': 'list', 'path': '$path', 'hash': '$hash'}}
    assert member_bridge.execute(entry, {'path': '.', 'hash': True}) == {'items': rows}
    assert calls[-1]['hash'] is True
    assert member_bridge.execute(entry, {'path': '.'}) == {'items': [{'name': 'a'}]}
    assert 'hash' not in calls[-1]


def test_ibl_conditional_write_uses_observed_version_not_a_fresh_read(monkeypatch, tmp_path):
    calls = []
    current = ['a' * 64]

    def request(command):
        calls.append(command)
        if command['op'] == 'read':
            return {'success': True, 'sha256': current[0], 'content': 'old'}
        return {'success': command.get('expected_hash') == current[0]}

    monkeypatch.setattr(member_bridge, 'request', request)
    with member_runtime.turn_scope(tmp_path, 'device', 'turn', threading.Event(), {}) as state:
        state.update(local_task_id='task', body_session='body')
        member_bridge._ibl_exchange({'op': 'read', 'path': 'a.txt'})
        current[0] = 'b' * 64  # A human edited the file after the read.
        assert not member_bridge._ibl_exchange({'op': 'write', 'path': 'a.txt'})['success']
        assert calls[-1]['expected_hash'] == 'a' * 64
        assert len(calls) == 2  # No implicit read that bypasses conflict detection.
        member_bridge._ibl_exchange({'op': 'read', 'path': 'a.txt'})
        assert member_bridge._ibl_exchange({'op': 'write', 'path': 'a.txt'})['success']
        explicit = {'op': 'write', 'path': 'a.txt', 'expected_hash': 'missing'}
        member_bridge._ibl_exchange(explicit)
        assert calls[-1] == explicit
        for field in ('local_task_id', 'body_session'):
            old = state[field]
            state[field] = 'other'
            member_bridge._ibl_exchange({'op': 'write', 'path': 'a.txt'})
            assert 'expected_hash' not in calls[-1]
            state[field] = old
    with member_runtime.turn_scope(tmp_path, 'device', 'next', threading.Event(), {}):
        member_bridge._ibl_exchange({'op': 'write', 'path': 'a.txt'})
        assert 'expected_hash' not in calls[-1]


@pytest.mark.parametrize('reply', [{'success': False, 'sha256': 'a' * 64},
                                  {'success': True, 'sha256': 'broken'},
                                  {'success': True}])
def test_unconfirmed_read_never_authorizes_ibl_overwrite(monkeypatch, tmp_path, reply):
    calls = []
    monkeypatch.setattr(member_bridge, 'request', lambda c: calls.append(c) or reply)
    with member_runtime.turn_scope(tmp_path, 'device', 'turn', threading.Event(), {}):
        member_bridge._ibl_exchange({'op': 'read', 'path': 'a.txt'})
        member_bridge._ibl_exchange({'op': 'write', 'path': 'a.txt'})
        assert 'expected_hash' not in calls[-1]


def test_document_transform_uses_the_same_version_exchange(monkeypatch, tmp_path):
    import member_files
    calls = []
    def request(command):
        calls.append(command)
        return {'success': True, 'sha256': 'a' * 64}
    def transform(entry, params, command, exchange):
        return exchange(command)
    monkeypatch.setattr(member_bridge, 'request', request)
    monkeypatch.setattr(member_files, 'transform', transform)
    with member_runtime.turn_scope(tmp_path, 'device', 'turn', threading.Event(), {}):
        for op in ('read', 'write'):
            member_bridge.execute({'limb_op': {'op': op, 'path': '$path'},
                                   'member_transform': 'test'}, {'path': 'doc.json'})
        assert calls[-1]['expected_hash'] == 'a' * 64


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
