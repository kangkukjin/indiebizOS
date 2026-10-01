"""Verify remote renderer uses a matching compiled catalog and fails back safely."""
import sys
from pathlib import Path
from unittest.mock import patch

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'backend'))
import boot_paths  # noqa: E402,F401
import launcher_surface_remote as remote  # noqa: E402

raw = remote.LAUNCHER_SHELL_HTML + remote.LAUNCHER_APP_JS + remote.LAUNCHER_RENDER_JS
rendered = remote.launcher_html()
assert 'window.__ui=' in rendered, 'built remote catalog was not consumed'
assert 'data-ui-text=' in rendered
with patch.object(remote.json, 'loads', return_value={'source_hash': 'obsolete', 'html': 'UNSAFE STALE HTML'}):
    assert remote.launcher_html() == raw
with patch.object(remote.json, 'loads', side_effect=ValueError('corrupt')):
    assert remote.launcher_html() == raw
print('remote renderer: matching bundle, stale source and corrupt bundle fallback passed')
