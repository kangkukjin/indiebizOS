"""Touch screen control must not focus an editable field; text entry is explicit."""
import boot_paths  # noqa: F401
import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect, sync_playwright

from launcher_react import react_shell


@pytest.mark.parametrize('kind', ['pc', 'phone'])
def test_touch_focus_and_explicit_text_delivery(kind, tmp_path):
    root = Path(__file__).resolve().parents[1] / 'frontend/dist'
    html = react_shell()
    assert html, 'Build the frontend before running viewer acceptance tests'
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 390, 'height': 844},
                                is_mobile=True, has_touch=True)
        errors, creates = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.add_init_script('''
          window.sent=[];window.sockets=[];
          window.WebSocket=class {static OPEN=1;readyState=1;bufferedAmount=0;
            constructor(url){window.sockets.push(this);setTimeout(()=>{
              if(this.readyState!==1)return;
              this.onmessage?.({data:JSON.stringify({type:'status',state:'running'})});
              const c=document.createElement('canvas');c.width=800;c.height=600;
              c.getContext('2d').fillRect(0,0,800,600);
              c.toBlob(b=>this.onmessage?.({data:b}),'image/jpeg');},30);}
            send(s){window.sent.push(JSON.parse(s));}
            close(){this.readyState=3;this.onclose?.();}};
        ''')

        def respond(route):
            path = urlsplit(route.request.url).path
            if path == '/launcher/ui/':
                route.fulfill(content_type='text/html', body=html)
                return
            if path.startswith('/launcher/ui/'):
                asset = root / path.removeprefix('/launcher/ui/')
                if asset.is_file():
                    route.fulfill(path=str(asset))
                    return
            result = {}
            if path == '/launcher/auth/session':
                result = {'authenticated': True, 'external': True}
            elif path == '/remote-pcs/screens' and route.request.method == 'POST':
                creates.append(route.request.post_data_json)
                result = {'device_kind': kind}
            route.fulfill(content_type='application/json', body=json.dumps(result))

        page.route('**/*', respond)
        page.goto('https://screen.test/launcher/ui/#/remote-screen/guestpc-abc')
        canvas = page.get_by_label('원격 기기 화면')
        hidden_keyboard = page.get_by_label('원격 키보드 입력')
        expect(canvas).to_have_attribute('width', '800')
        for _ in range(3):
            canvas.tap()
            expect(canvas).to_be_focused()
            expect(hidden_keyboard).not_to_be_focused()
        assert any(v['type'] == 'pointer' and v['buttons'] == 1
                   for v in page.evaluate('window.sent'))
        assert not any(v['type'] == 'text' for v in page.evaluate('window.sent'))

        page.get_by_role('button', name='문자 입력', exact=True).tap()
        entry = page.get_by_role('textbox', name='보낼 글', exact=True)
        entry.tap()
        expect(entry).to_be_focused()
        entry.fill('한글 English 😀\n두 번째 줄')
        assert not any(v['type'] == 'text' for v in page.evaluate('window.sent'))
        page.get_by_role('button', name='보내기', exact=True).tap()
        expect(entry).to_have_value('')
        texts = [v['text'] for v in page.evaluate('window.sent') if v['type'] == 'text']
        assert texts == ['한글 English 😀\n두 번째 줄']
        canvas.tap()
        expect(canvas).to_be_focused()
        expect(entry).not_to_be_focused()

        # Failed sends retain the draft, and a retry delivers it once.
        entry.fill('재시도할 글')
        page.evaluate('window.sockets.at(-1).bufferedAmount=65536')
        page.get_by_role('button', name='보내기', exact=True).tap()
        expect(entry).to_have_value('재시도할 글')
        expect(page.get_by_role('alert')).to_be_visible()
        page.evaluate('window.sockets.at(-1).bufferedAmount=0')
        page.get_by_role('button', name='보내기', exact=True).tap()
        expect(entry).to_have_value('')
        assert [v['text'] for v in page.evaluate('window.sent') if v['type'] == 'text'].count('재시도할 글') == 1
        page.screenshot(path=str(tmp_path / 'text-entry-portrait.png'))

        for width, height in [(320, 700), (844, 390)]:
            page.set_viewport_size({'width': width, 'height': height})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            expect(page.get_by_role('button', name='문자 입력', exact=True)).to_be_visible()
        page.screenshot(path=str(tmp_path / 'text-entry-landscape.png'))
        assert len(creates) == 1, 'Changing focus or layout must not recreate the session'
        assert not errors, errors
        browser.close()


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
