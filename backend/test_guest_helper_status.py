"""AI discovery uses the same signed release comparison as the owner cockpit."""
import boot_paths  # noqa: F401
import hashlib
import importlib.util
from pathlib import Path
import sys
import pytest
from test_resident_pcs import registry, publish_test_mac_release  # noqa: F401
import resident_pcs


def test_limb_list_exposes_signed_release_status_without_update(registry, tmp_path, monkeypatch):
    import runtime_utils, device_registry
    monkeypatch.setattr(runtime_utils, 'get_base_path', lambda: tmp_path)
    monkeypatch.setattr(device_registry, 'live_with_capability', lambda cls: [])
    spec = importlib.util.spec_from_file_location('guest_status_handler', Path(__file__).resolve().parents[1] /
                                                 'data/packages/installed/tools/guest-helper/handler.py')
    handler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(handler)
    row = registry('mac-test')
    binary = publish_test_mac_release(tmp_path, 'mac-amd64', b'signed release')
    dist = tmp_path / 'helper/dist'
    dist.mkdir()
    (dist / 'indiebiz-helper-mac-amd64').write_bytes(b'newer unapproved development build')
    sha = hashlib.sha256(binary.read_bytes()).hexdigest()
    caps = {'os': 'darwin', 'arch': 'amd64', 'go': 'go1.26.5', 'helper_sha256': sha, 'self_update': True}
    resident_pcs.sync(row['key'], 'a' * 32, capabilities=caps)
    monkeypatch.setattr(resident_pcs, 'update_helper', lambda *a: pytest.fail('lookup submitted update'))
    found = handler._limb_list({'limb': row['device_id']})['items'][0]
    assert found['helper'] == resident_pcs.helper_status(resident_pcs.resolve(row['device_id']))
    assert found['helper']['state'] == 'current' and not found['connected']
    publish_test_mac_release(tmp_path, 'mac-amd64', b'next signed release')
    assert handler._limb_list({'limb': row['device_id']})['items'][0]['helper']['state'] == 'available'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
