"""실제 Chromium에서 CDP snapshot → ref → 클릭의 신원 계약을 검증한다."""

import asyncio
import importlib
from pathlib import Path
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
from playwright.async_api import async_playwright


class Refs:
    def __init__(self, page):
        self.page = self.raw_page = page
        self._snapshot_url = None
        self.clear_refs()

    def clear_refs(self):
        self.refs = {}

    def add_ref(self, info):
        ref = f'e{len(self.refs) + 1}'
        self.refs[ref] = info
        return ref

    def get_ref(self, ref):
        return self.refs.get(ref)


def test_real_snapshot_disclosure_click_and_identity_guards(monkeypatch):
    folder = Path(__file__).resolve().parents[1] / 'data/packages/installed/tools/browser-action'
    monkeypatch.syspath_prepend(str(folder))
    snapshot = importlib.import_module('browser_snapshot')
    interact = importlib.import_module('browser_interact')

    async def run():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            try:
                page = await browser.new_page()
                refs = Refs(page)
                for module in (snapshot, interact):
                    monkeypatch.setattr(module, 'BrowserSession', SimpleNamespace(get_instance=lambda: refs))
                    monkeypatch.setattr(module, 'ensure_active', lambda: None)

                async def capture(html, name):
                    await page.set_content(html)
                    result = await snapshot.browser_snapshot({})
                    assert result['success'], result
                    return next(row for row in result['snapshot'] if row['name'] == name)

                # 본문·중첩 마크업·명시 접근성 이름, CSS 선택자 유무를 함께 확인한다.
                for markup, name in [
                    ('언어의 구성 보기', '언어의 구성 보기'),
                    ('<span>설정</span>   <b>더 보기</b>', '설정 더 보기'),
                    ('<span>설정 (A+B)?</span>', '설정 (A+B)?'),
                ]:
                    row = await capture(f'<details><summary>{markup}</summary>내용</details>', name)
                    assert row['role'] == 'disclosuretriangle'
                    assert refs.get_ref(row['ref'])['_interactive']
                    for expected in (True, False):
                        result = await interact.browser_click({'ref': row['ref']})
                        assert result['success'], result
                        assert await page.locator('details').evaluate('(el) => el.open') is expected

                for attr in ('aria-label="설정 열기"', 'aria-labelledby="label"'):
                    row = await capture(
                        '<span id="label">설정 열기</span><details>'
                        f'<summary id="toggle" {attr}>다른 본문</summary>내용</details>', '설정 열기')
                    # span도 같은 이름이므로 disclosure 참조를 명시 선택한다.
                    row = next({'ref': ref, **info} for ref, info in refs.refs.items()
                               if info['role'] == 'disclosuretriangle')
                    assert (await interact.browser_click({'ref': row['ref']}))['success']
                    assert await page.locator('details').evaluate('(el) => el.open')

                # 같은 이름 두 개를 임의 선택하지 않는다. 선택자가 있으면 그 신원만 클릭한다.
                row = await capture('<details><summary>더 보기</summary>A</details>'
                                    '<details><summary>더 보기</summary>B</details>', '더 보기')
                result = await interact.browser_click({'ref': row['ref']})
                assert result['error_code'] == 'REF_NOT_RESOLVED'
                assert await page.locator('details[open]').count() == 0
                row = await capture('<details><summary id="first">더 보기</summary>A</details>'
                                    '<details><summary id="second">더 보기</summary>B</details>', '더 보기')
                assert (await interact.browser_click({'ref': row['ref']}))['success']
                assert await page.locator('#first').evaluate('(el) => el.parentElement.open')
                assert not await page.locator('#second').evaluate('(el) => el.parentElement.open')

                # 접근성 이름이 바뀌면 옛 본문 이름, 같은 선택자만으로 클릭하면 안 된다.
                for mutation in [
                    "el.setAttribute('aria-label', '다른 작업')",
                    "el.textContent = '다른 작업'",
                    'el.remove()',
                ]:
                    row = await capture('<details><summary id="toggle">더 보기</summary>A</details>', '더 보기')
                    await page.locator('summary').evaluate(f'(el) => {{ {mutation} }}')
                    result = await interact.browser_click({'ref': row['ref']})
                    assert result['error_code'] == 'REF_NOT_RESOLVED', result
                    assert await page.locator('details[open]').count() == 0

                # CDP 고유 역할 처리가 보통 ARIA 버튼의 신원 검사를 바꾸지 않는다.
                row = await capture('<button onclick="this.textContent=\'완료\'">실행</button>', '실행')
                assert (await interact.browser_click({'ref': row['ref']}))['success']
                assert await page.get_by_role('button', name='완료').count() == 1
            finally:
                await browser.close()

    asyncio.run(run())


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
