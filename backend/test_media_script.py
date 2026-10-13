"""The AI control surface must not expose engine authentication material."""
import boot_paths  # noqa: F401
import importlib.util
import io
import json
import sys
from pathlib import Path


def test_script_returns_state_without_engine_secrets(monkeypatch, capsys):
    path = Path(__file__).resolve().parents[1] / 'data/scripts/미디어세션.py'
    spec = importlib.util.spec_from_file_location('media_script_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    raw = {'success': True, 'session': {'session_id': 'test', 'state': 'active',
        'pending_offer': {'sdp': 'private-sdp'}, 'ice_servers': [{'credential': 'private-turn'}],
        'content': {'ref': 'safe-reference', 'url': 'https://media.example/song?token=private-token'},
        'quality': {'fps': 24}}}
    monkeypatch.setattr(module, '_http', lambda *args: raw)
    monkeypatch.setattr(sys, 'stdin', io.StringIO('{"op":"status","session_id":"test"}'))
    module.main()
    output = capsys.readouterr().out
    assert 'private-' not in output and 'pending_offer' not in output and 'ice_servers' not in output
    result = json.loads(output)['items'][0]
    assert result['state'] == 'active' and result['quality']['fps'] == 24
    assert result['content']['ref'] == 'safe-reference'


if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
