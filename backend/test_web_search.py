"""Search batches retain source estimates without confusing them with row counts."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import boot_paths  # noqa: F401


def test_batch_preserves_zero_estimate_missing_estimate_and_failure(monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'data/packages/installed/tools/web/handler.py'
    spec = importlib.util.spec_from_file_location('web_search_contract', path)
    handler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(handler)
    responses = {'many': {'success': True, 'items': [{'title': 'a'}], 'total_estimate': 59515},
                 'zero': {'success': True, 'items': [], 'total_estimate': 0},
                 'unknown': {'success': True, 'items': []},
                 'failed': {'success': False, 'error': 'offline', 'items': []}}
    monkeypatch.setattr(handler, 'execute', lambda args, ctx: json.dumps(responses[args['query']]))
    monkeypatch.setattr(handler, '_fetch_sections', lambda jobs: [job() for _, job in jobs])
    out = handler._batch_search({'queries': list(responses)}, 'naver_search', 'naver', '.')
    assert [s['count'] for s in out['sections']] == [1, 0, 0, 0]
    assert out['sections'][0]['total_estimate'] == 59515
    assert out['sections'][1]['total_estimate'] == 0
    assert all('total_estimate' not in s for s in out['sections'][2:])
    assert out['count'] == 1 and out['errors']


if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
