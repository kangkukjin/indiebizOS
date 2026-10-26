"""Verify remote renderer uses a matching compiled catalog and fails back safely."""
import sys
from pathlib import Path
from unittest.mock import patch

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'backend'))
import boot_paths  # noqa: E402,F401
import launcher_surface_remote as remote  # noqa: E402
from surface_assets import source_build  # noqa: E402

with source_build():
    from launcher_web_shell import LAUNCHER_SHELL_HTML
    from launcher_web_app import LAUNCHER_APP_JS
    from launcher_web_render import LAUNCHER_RENDER_JS

    raw = LAUNCHER_SHELL_HTML + LAUNCHER_APP_JS + LAUNCHER_RENDER_JS
    rendered = remote.launcher_html(display=False)
    assert 'window.__ui=' in rendered, 'built remote catalog was not consumed'
    assert 'data-ui-text=' in rendered
    with patch.object(remote, 'read_asset', return_value='{"source_hash":"obsolete","html":"UNSAFE STALE HTML"}'):
        assert remote.localized_html(raw, 'remote') == raw
    with patch.object(remote, 'read_asset', return_value='{corrupt'):
        assert remote.localized_html(raw, 'remote') == raw
print('remote renderer: matching bundle, stale source and corrupt bundle fallback passed')
