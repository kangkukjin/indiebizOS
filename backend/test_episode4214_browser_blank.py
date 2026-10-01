"""ep4214: about:blank 에 https:// 를 붙여 다섯 번 연속 실패한 주소 정규화의 회귀 시험."""
import importlib
import sys
from pathlib import Path

import boot_paths  # noqa: F401
import pytest


def _session(monkeypatch):
    folder = Path(__file__).resolve().parents[1] / 'data/packages/installed/tools/browser-action'
    monkeypatch.syspath_prepend(str(folder))
    return importlib.import_module('browser_session')


def test_blank_page_keeps_its_address(monkeypatch):
    session = _session(monkeypatch)
    assert session.normalize_url('about:blank') == 'about:blank'
    assert session.normalize_url(' About:Blank ') == 'About:Blank'


def test_bare_host_gets_https_and_explicit_scheme_is_kept(monkeypatch):
    session = _session(monkeypatch)
    assert session.normalize_url('example.com/a') == 'https://example.com/a'
    assert session.normalize_url('http://example.com') == 'http://example.com'
    assert session.normalize_url('HTTPS://example.com') == 'HTTPS://example.com'


def test_closed_browser_message_names_the_current_word(monkeypatch):
    session = _session(monkeypatch)
    monkeypatch.setattr(session.BrowserSession, 'is_active', property(lambda self: False))
    error = session.ensure_active()['error']
    assert '[limbs:browser]' in error and 'browser_navigate' not in error


def test_no_entry_point_keeps_its_own_prefix_rule():
    folder = Path(__file__).resolve().parents[1] / 'data/packages/installed/tools/browser-action'
    for name in ('browser_navigate.py', 'browser_session.py'):
        source = (folder / name).read_text(encoding='utf-8')
        assert source.count("'https://' + ") + source.count('"https://" + ') <= 1, name


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
