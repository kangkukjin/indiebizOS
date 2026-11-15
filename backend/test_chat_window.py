"""Real chat windows keep reading position across polling and reserve native drag space."""
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

import pytest


@pytest.fixture(scope='module')
def chat_ui_url(tmp_path_factory):
    root = Path(__file__).resolve().parents[1]
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    with (tmp_path_factory.mktemp('chat-window') / 'vite.log').open('w') as log:
        server = subprocess.Popen(
            [str(root / 'frontend/node_modules/.bin/vite'), '--host', '127.0.0.1', '--port', str(port)],
            cwd=root / 'frontend', stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(100):
                try:
                    with urlopen(url, timeout=1):
                        break
                except OSError:
                    time.sleep(.1)
            else:
                pytest.fail('Vite did not start')
            yield url
        finally:
            server.terminate()
            server.wait(timeout=10)


@pytest.mark.parametrize('target', ['system_ai', 'agent'])
def test_chat_scroll_survives_poll_and_new_messages(chat_ui_url, target):
    from playwright.sync_api import sync_playwright, expect
    records = [{'id': str(i), 'role': 'user', 'content': f'대화 {i} ' + '본문 ' * 20,
                'timestamp': '2026-11-16T00:00:00Z', 'images': []} for i in range(50)]
    calls = []

    def api(route):
        path = urlparse(route.request.url).path
        payload = {}
        if path == '/chat-sessions':
            payload = {'sessions': [{'id': 'sample', 'title': '대화 시험', 'updated_at': '2026-11-16T00:00:00Z'}]}
        elif path == '/chat-sessions/sample':
            calls.append(route.request.url)
            payload = {'revision': 1, 'messages': records, 'has_older': False, 'turn': None, 'events': []}
        elif path == '/projects':
            payload = {'projects': [{'id': 'fixture', 'name': '검사 프로젝트', 'project_kind': 'general'}]}
        elif path == '/projects/fixture/agents':
            payload = {'agents': [{'id': 'a', 'name': '자료 정리', 'type': 'internal', 'active': True,
                                  'ai': {'provider': 'openai', 'model': 'test'}}]}
        elif path == '/projects/fixture/config':
            payload = {'config': {}}
        elif path == '/switches':
            payload = {'switches': []}
        route.fulfill(json=payload, headers={'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*'})

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={'width': 1000 if target == 'agent' else 700, 'height': 850})
            page.route('http://127.0.0.1:8765/**', api)
            page.goto(chat_ui_url + ('/#/project/fixture?agent=a' if target == 'agent' else '/#/system-ai'))
            expect(page.locator('.chat-header')).to_be_visible()
            header = page.locator('.chat-header:visible')
            scroller = header.locator('..').locator('div.overflow-y-auto').first
            expect(scroller.get_by_text('대화 49', exact=False)).to_be_visible()
            try:
                page.wait_for_function("""() => [...document.querySelectorAll('div.overflow-y-auto')]
                    .some(e => e.clientHeight && e.scrollTop > 1000 && e.scrollHeight-e.clientHeight-e.scrollTop <= 2)""", timeout=5000)
            except Exception:
                pytest.fail(str(scroller.evaluate('e => ({top:e.scrollTop,height:e.clientHeight,total:e.scrollHeight})')))
            # Layout changes must not be mistaken for the reader scrolling upward.
            page.set_viewport_size({'width': 1000 if target == 'agent' else 700, 'height': 750})
            page.wait_for_timeout(1500)
            assert scroller.evaluate('e => e.scrollHeight-e.clientHeight-e.scrollTop') <= 2
            page.set_viewport_size({'width': 1000 if target == 'agent' else 700, 'height': 850})
            page.wait_for_timeout(1500)
            get_top = lambda: scroller.evaluate('e => e.scrollTop')
            bottom = get_top()
            box = scroller.bounding_box()
            page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
            page.mouse.wheel(0, -60)
            page.wait_for_function('(bottom) => [...document.querySelectorAll("div.overflow-y-auto")].some(e => e.clientHeight && e.scrollTop < bottom-40 && e.scrollTop > 1000)', arg=bottom)
            reading = get_top()
            count = len(calls)
            page.wait_for_timeout(2700)
            assert len(calls) > count
            assert abs(get_top() - reading) <= 2, 'polling pulled the reader back to the bottom'
            records.append({**records[-1], 'id': '50', 'content': '새 답변 ' * 30})
            page.wait_for_timeout(1800)
            assert abs(get_top() - reading) <= 2, 'new content moved the reader'
            # Returning to the bottom resumes following; only the message viewport may scroll.
            scroller.evaluate('e => {e.scrollTop=e.scrollHeight;e.dispatchEvent(new Event("scroll",{bubbles:true}));}')
            before_header = header.bounding_box()['y']
            records.append({**records[-1], 'id': '51', 'content': '다음 답변 ' * 30})
            expect(scroller.get_by_text('다음 답변', exact=False)).to_be_visible(timeout=5000)
            assert scroller.evaluate('e => e.scrollHeight-e.clientHeight-e.scrollTop') <= 2
            assert header.bounding_box()['y'] == before_header
            assert page.evaluate('window.scrollY') == 0
            assert any(f'target={target}' in url for url in calls)
            if target == 'system_ai':
                for width in (700, 400):
                    page.set_viewport_size({'width': width, 'height': 850})
                    title = page.locator('.system-ai-titlebar')
                    rect = title.bounding_box()
                    assert rect['y'] <= 12 and rect['height'] >= 40
                    assert rect['width'] >= width - 24
                    assert title.evaluate('e => getComputedStyle(e).webkitAppRegion') == 'drag'
                    assert title.locator('button').count() == 0
                    assert page.get_by_role('button', name='음성대화 시작').bounding_box()['y'] >= rect['y'] + rect['height']
            else:
                title = page.locator('.project-header')
                assert title.evaluate('e => getComputedStyle(e).webkitAppRegion') == 'drag'
                assert title.get_by_text('검사 프로젝트', exact=True).evaluate(
                    "e => !e.closest('.no-drag')")
                assert title.locator('#project-actions').evaluate('e => getComputedStyle(e).webkitAppRegion') == 'no-drag'
        finally:
            browser.close()
