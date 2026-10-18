"""Provider failures preserve actionable evidence without rewriting the query."""
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
from test_ibl_rank41_50_repairs import load


@pytest.mark.parametrize('data,body,expected', [
    ({'error': 'invalid_search', 'message': 'Search cannot contain wildcard'}, '', 'Search cannot contain wildcard'),
    ({'error': 'bad filter'}, '', 'bad filter'),
    (None, 'Bad request body', 'Bad request body'),
    ({}, '', '원천 사유 미제공'),
])
def test_openalex_bad_request_preserves_reason_without_retry(monkeypatch, data, body, expected):
    mod = load('study')
    calls = []
    def response_json():
        if data is None:
            raise ValueError('not JSON')
        return data
    response = SimpleNamespace(status_code=400, text=body, json=response_json,
                               raise_for_status=lambda: pytest.fail('lost server error detail'))
    monkeypatch.setattr(mod, '_polite_get', lambda *a, **kw: calls.append(kw) or response)
    result = mod._search_openalex({'query': 'Who is AI replacing?'})
    assert result['success'] is False and result['items'] == []
    assert result['status_code'] == 400 and expected in result['error']
    assert len(calls) == 1 and calls[0]['params']['search'] == 'Who is AI replacing?'


def test_openalex_error_detail_is_bounded(monkeypatch):
    mod = load('study')
    monkeypatch.setattr(mod, '_polite_get', lambda *a, **kw: SimpleNamespace(
        status_code=400, json=lambda: {'message': 'bad ' * 10000}, text=''))
    result = mod._search_openalex({'query': 'test'})
    assert len(result['error']) < 700


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
