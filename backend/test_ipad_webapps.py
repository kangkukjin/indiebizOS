"""실패한 iPad 경로 회귀: 팝업 금지·느린 본문·취소 및 쿠키 없는 로그인 성공."""
from pathlib import Path

import boot_paths  # noqa: F401
import pytest


@pytest.fixture
def page():
    playwright = pytest.importorskip('playwright.sync_api')
    with playwright.sync_playwright() as p:
        if not Path(p.chromium.executable_path).exists():
            pytest.skip('Playwright Chromium 미설치')
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1024, 'height': 768})
        yield page
        browser.close()


def test_nas_reader_never_opens_popup_and_preserves_text_and_list(page):
    html = (Path(__file__).parent / 'static/nas/index.html').read_text()
    pending = []
    body = '<script>window.injected=true</script>\n한글 원문\n' * 300

    def route(r):
        path = r.request.url.split('test.invalid')[-1]
        if path == '/nas/app':
            r.fulfill(body=html, content_type='text/html')
        elif path.startswith('/nas/text?'):
            pending.append(r)
        elif path == '/nas/auth/check':
            r.fulfill(json={'enabled': True, 'authenticated': True})
        else:
            r.fulfill(json={'path': '/', 'items': []})

    page.route('**/*', route)
    page.goto('https://test.invalid/nas/app')
    page.wait_for_function("document.getElementById('app').style.display==='flex'")
    page.evaluate("window.open=()=>{throw new Error('popup forbidden')}; document.getElementById('fileList').innerHTML='<div style=\"height:5000px\">files</div>';document.getElementById('fileList').scrollTop=700")
    scroll = page.locator('#fileList').evaluate('(e)=>e.scrollTop')
    page.evaluate("void viewText('/한글.txt')")
    page.wait_for_function("document.getElementById('textBody').getAttribute('aria-busy')==='true'")
    page.wait_for_timeout(50)
    assert pending
    pending.pop(0).fulfill(json={'content': body, 'encoding': 'cp949'})
    page.wait_for_function("document.getElementById('textBody').getAttribute('aria-busy')==='false'")
    assert page.locator('#textContent').text_content() == body
    assert page.evaluate('window.injected') is None
    assert len(page.context.pages) == 1
    page.evaluate('jumpText(500)')
    assert page.locator('#textPercent').inner_text() == '50%'
    page.click('#textClose')
    assert not page.locator('#textReader').is_visible()
    assert page.locator('#fileList').evaluate('(e)=>e.scrollTop') == scroll
    assert not page.locator('#app').evaluate('(e)=>e.inert')
    # 닫은 요청의 늦은 응답이 다음 문서를 덮지 않는다.
    page.evaluate("void viewText('/old.txt')")
    page.wait_for_timeout(50)
    page.click('#textClose')
    page.evaluate("void viewText('/new.txt')")
    page.wait_for_timeout(50)
    old, new = pending
    new.fulfill(json={'content': '새 문서'})
    old.fulfill(json={'content': '이전 문서'})
    page.wait_for_function("document.getElementById('textContent').textContent==='새 문서'")
    assert page.locator('#textTitle').inner_text() == 'new.txt'
    page.click('#textClose')
    page.evaluate("void viewText('/expired.txt')")
    page.wait_for_timeout(50)
    pending[-1].fulfill(status=401, json={'detail': 'login required'})
    page.wait_for_function("document.getElementById('loginScreen').style.display==='flex'")
    assert not page.locator('#textReader').is_visible()


def test_launcher_refuses_false_login_and_reports_project_failure(page):
    from api_launcher_web import get_launcher_webapp_html
    html = get_launcher_webapp_html()
    state = {'status': 401}

    def route(r):
        path = r.request.url.split('test.invalid')[-1]
        if path == '/launcher/app':
            r.fulfill(body=html, content_type='text/html')
        elif path == '/launcher/config':
            r.fulfill(json={'has_password': True})
        elif path == '/projects':
            r.fulfill(status=state['status'], json={'projects': [{'id': 'test', 'name': '진단 프로젝트'}]})
        else:
            r.fulfill(json={})

    page.route('**/*', route)
    page.goto('https://test.invalid/launcher/app')
    page.wait_for_function("document.getElementById('loginErr').textContent.includes('로그인')")
    page.evaluate("document.getElementById('pw').value='test';void doLogin()")
    page.wait_for_function("document.getElementById('loginErr').textContent.includes('HTTPS')")
    assert page.locator('#login').is_visible()
    assert not page.locator('#app').is_visible()
    state['status'] = 200
    page.evaluate('void doLogin()')
    page.wait_for_function("document.getElementById('apBrowse').textContent.includes('진단 프로젝트')")
    assert page.locator('#app').is_visible()
    state['status'] = 503
    page.evaluate('void apLoad()')
    page.wait_for_function("document.getElementById('apBrowse').textContent.includes('HTTP 503')")
    assert '프로젝트 0' not in page.locator('#apBrowse').inner_text()
    state['status'] = 401
    page.evaluate("void jfetch('/projects')")
    page.wait_for_function("!document.getElementById('app').classList.contains('on')")
    assert page.locator('#login').is_visible()


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
