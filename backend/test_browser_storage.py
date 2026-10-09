"""Authentication storage application is distinct from verified login."""
import boot_paths  # noqa: F401
import asyncio
import json
from types import SimpleNamespace

import pytest
from test_browser_session import browser  # noqa: F401


@pytest.mark.parametrize('fault', ['', 'redirect', 'write', 'reload'])
def test_load_reports_applied_storage_and_partial_failures(browser, monkeypatch, tmp_path, fault):
    handler, module = browser
    storage = handler._load('browser_storage')
    monkeypatch.setattr(storage, 'get_cookies_dir', lambda: tmp_path)
    cookies = [{'name':'synthetic','value':'test'}]
    (tmp_path / 'example.json').write_text(json.dumps({
        'cookies':cookies, 'local_storage':{'one':'1','two':'2'},
        'url':'https://example.test/account',
    }))
    class Page:
        # Same host but different scheme still requires navigating to the saved origin.
        url = 'http://example.test/login'
        def __init__(self): self.context=self; self.applied=[]; self.keys=[]; self.visits=[]
        async def add_cookies(self, value): self.applied.extend(value)
        async def goto(self, url, **kwargs):
            self.visits.append(url)
            self.url = 'https://elsewhere.test/' if fault=='redirect' else url
        async def evaluate(self, expression, args):
            if fault=='write' and args['key']=='two': raise RuntimeError('unavailable')
            self.keys.append(args['key'])
        async def reload(self, **kwargs):
            if fault=='reload': raise RuntimeError('offline')
    page = Page()
    monkeypatch.setattr(storage, 'ensure_active', lambda: None)
    monkeypatch.setattr(module.BrowserSession, 'get_instance', lambda: SimpleNamespace(raw_page=page, clear_refs=lambda: None))
    result = asyncio.run(storage.browser_cookies_load({'name':'example'}))
    assert result['success'] == (not fault), result
    assert result['authentication_verified'] is False
    assert page.visits == ['https://example.test/account']
    assert page.applied==cookies and result['cookies_loaded']==1
    expected = 0 if fault=='redirect' else 1 if fault=='write' else 2
    assert len(page.keys)==result['local_storage_loaded']==expected
    if fault:
        assert result['error_code']=='STORAGE_RESTORE_INCOMPLETE' and result['warnings']
    assert '목적 화면' in result['snapshot_hint']


def test_closed_load_explains_navigation_sequence(browser, monkeypatch):
    handler, _ = browser
    storage = handler._load('browser_storage')
    monkeypatch.setattr(storage, 'ensure_active', lambda: {'success':False, 'error':'closed'})
    result = asyncio.run(storage.browser_cookies_load({'name':'example'}))
    assert not result['success'] and result['recovery']['op']=='navigate'
    assert 'cookies load' in result['hint']


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
