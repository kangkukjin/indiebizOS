"""Desktop capture file sink preserves bytes and the legacy image result."""
import boot_paths  # noqa: F401
import base64
import importlib.util
import json
from pathlib import Path

from tool_context import ToolContext

ROOT = Path(__file__).resolve().parents[1]


def test_screenshot_path_is_guarded_and_writes_exact_bytes(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location('screen_contract_handler', ROOT / 'data/packages/installed/tools/computer-use/handler.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    raw = b'\x89PNG\r\n\x1a\nsynthetic screenshot'
    captures = []
    def capture(region=None):
        captures.append(region)
        return {'base64': base64.b64encode(raw).decode(), 'media_type': 'image/png'}
    monkeypatch.setattr(module, '_capture_screenshot', capture)
    monkeypatch.setattr(module, '_get_screen_size', lambda: (1280, 800))
    context = ToolContext(str(tmp_path), 'computer_op')
    monkeypatch.setattr(context, '_scope_refusal', lambda path, guard=None: None)
    legacy = module.execute({'op': 'screenshot'}, context)
    assert legacy['images'][0]['base64'] == base64.b64encode(raw).decode()
    result = module.execute({'op': 'screenshot', 'path': 'proof.png'}, context)
    assert Path(result['file_path']) == tmp_path / 'outputs/proof.png'
    assert Path(result['file_path']).read_bytes() == raw and 'images' not in result
    monkeypatch.setattr(context, '_scope_refusal', lambda path, guard=None: 'denied')
    denied = json.loads(module.execute({'op': 'screenshot', 'path': '/outside.png'}, context))
    assert not denied['success'] and len(captures) == 2


if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
