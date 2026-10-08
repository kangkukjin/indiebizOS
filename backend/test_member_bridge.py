"""A member device must honor an explicitly requested content fingerprint."""
import boot_paths  # noqa: F401
import pytest
import member_bridge


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


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
