"""Validate the deployable TURN configuration without creating a server or writing secrets."""
import boot_paths  # noqa: F401
import importlib.util
from pathlib import Path

import pytest


def test_turn_config_requires_pinned_image_and_produces_all_routes():
    path = Path(__file__).resolve().parents[1] / 'scripts/media_turn_setup.py'
    spec = importlib.util.spec_from_file_location('media_turn_setup_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    image = 'coturn/coturn@sha256:' + 'a' * 64
    config, compose, ice = module.deployment('turn.example.com', '203.0.113.7', image, 'test-only')
    assert 'use-auth-secret' in config and 'static-auth-secret=test-only' in config
    assert compose['services']['turn']['image'] == image
    assert compose['services']['turn']['network_mode'] == 'host'
    assert len(ice['urls']) == 3 and ice['urls'][-1].startswith('turns:')
    assert 'test-only' not in str(ice) and 'test-only' not in str(compose)
    with pytest.raises(ValueError):
        module.deployment('turn.example.com', '203.0.113.7', 'coturn/coturn:latest', 'test-only')
    with pytest.raises(ValueError):
        module.deployment('bad\nrealm=other', '203.0.113.7', image, 'test-only')


if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
