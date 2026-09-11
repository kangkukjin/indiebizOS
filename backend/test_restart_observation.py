"""R0: 생존과 관측 실패를 빈 실행 목록으로 합치지 않는다."""
import json
from io import BytesIO

import pytest


@pytest.mark.parametrize("module", ["quiescent_reload", "red_apply"])
@pytest.mark.parametrize("payload,expected", [
    ({"live_turns": []}, (True, [])),
    ({"live_turns": [], "live_turns_observation": "unknown"}, (True, None)),
    ({"status": "healthy"}, (True, None)),
])
def test_probe_preserves_unknown(monkeypatch, module, payload, expected):
    import importlib
    import urllib.request
    response = BytesIO(json.dumps(payload).encode())
    response.status = 200
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: response)
    mod = importlib.import_module(module)
    probe = getattr(mod, "probe_live_turns", None) or mod._probe_live_turns
    assert probe("http://test") == expected


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
