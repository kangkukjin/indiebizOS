"""Browser DOM collection boundaries, real Chromium and the IBL result adapter."""
import boot_paths  # noqa: F401
import asyncio
import json
import subprocess
from pathlib import Path

import pytest
from ibl_v2_adapters import decode_envelope
from ibl_v2_ir import Fault

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = {"protocol": "legacy-envelope", "value_path": ""}


@pytest.fixture(scope="module")
def operation_source():
    return subprocess.check_output([
        "node", "--input-type=module", "-e",
        "import {pageOperation} from './frontend/electron/embedded-browser-dom.js';"
        "process.stdout.write(pageOperation.toString())",
    ], cwd=ROOT, text=True)


def observe(operation_source, html, steps):
    from playwright.async_api import async_playwright
    from runtime_utils import setup_playwright_browsers_path
    setup_playwright_browsers_path()

    async def run():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.route("https://fixture.test/**", lambda route: route.fulfill(
                    body=html, content_type="text/html; charset=utf-8"))
                await page.goto("https://fixture.test/source")
                await page.evaluate("() => { window.operation = " + operation_source + "; }")
                return await steps(page)
            finally:
                await browser.close()
    return asyncio.run(run())


def test_short_rendered_scope_is_complete_and_ibl_composable(operation_source):
    async def steps(page):
        result = await page.evaluate("operation('content')")
        value, _ = decode_envelope({"success": True, **result}, ADAPTER)
        assert value["content"] == "전체 공개 본문"
        assert result["source_complete"] and not result["truncated"]
        assert "images_and_canvas" in result["coverage_limits"]
    observe(operation_source, "<main>전체 공개 본문</main>", steps)


def test_form_text_preserved_inputs_hidden_and_editors_excluded(operation_source):
    async def steps(page):
        result = await page.evaluate("operation('content')")
        assert "공개 제목" in result["content"] and "공개 설명" in result["content"]
        assert "PRIVATE_SENTINEL" not in json.dumps(result)
    observe(operation_source, '<form><h1>공개 제목</h1><p>공개 설명</p>'
            '<input value="PRIVATE_SENTINEL"><textarea>PRIVATE_SENTINEL</textarea>'
            '<select><option>PRIVATE_SENTINEL</option></select>'
            '<div contenteditable="true">PRIVATE_SENTINEL</div>'
            '<p hidden>PRIVATE_SENTINEL</p><p style="display:none">PRIVATE_SENTINEL</p>'
            '<script>"PRIVATE_SENTINEL"</script></form>', steps)


def test_explicit_pages_reassemble_without_partial_fault(operation_source):
    text = "가나다라" * 1300
    async def steps(page):
        part = await page.evaluate("operation('content', {limit:500})")
        chunks = []
        while True:
            decode_envelope({"success": True, **part}, ADAPTER)
            chunks.append(part["content"])
            if part["next_offset"] is None:
                break
            part = await page.evaluate("args => operation('content', args)", {
                "cursor": part["cursor"], "offset": part["next_offset"], "limit": 500})
        assert "".join(chunks) == text
    observe(operation_source, f"<main>{text}</main>", steps)


def test_default_limit_and_hard_capture_limit_remain_incomplete(operation_source):
    async def steps(page):
        default = await page.evaluate("operation('content')")
        with pytest.raises(Fault) as exc:
            decode_envelope({"success": True, **default}, ADAPTER)
        assert exc.value.code == "PARTIAL_SOURCE"
        result = await page.evaluate("operation('content', {limit:20000})")
        assert result["capture_truncated"] and result["total_chars"] <= 500000
        with pytest.raises(Fault):
            decode_envelope({"success": True, **result}, ADAPTER)
        assert any(t["reason"] == "capture_limit" for t in result["truncations"])
    observe(operation_source, "<main>" + "가" * 510000 + "</main>", steps)


def test_cursor_keeps_text_links_title_and_capture_time_together(operation_source):
    async def steps(page):
        first = await page.evaluate("operation('content', {limit:500})")
        await page.evaluate("document.title='Changed'; document.querySelector('a').href='/new';"
                            "document.querySelector('main').firstChild.textContent='Different'")
        second = await page.evaluate("args => operation('content', args)", {
            "cursor": first["cursor"], "offset": first["next_offset"], "limit": 500})
        assert second["title"] == first["title"]
        assert second["links"] == first["links"]
        assert second["captured_at"] == first["captured_at"]
        assert second["content"] == "a" * 500
    observe(operation_source, "<title>Original</title><main>" + "a" * 1500 +
            '<a href="/old?token=secret">Old link</a></main>', steps)


def test_scope_includes_sibling_articles_and_link_omission_is_disclosed(operation_source):
    async def steps(page):
        result = await page.evaluate("operation('content', {limit:20000})")
        assert "둘째 문서" in result["content"]
        assert result["links_total"] == 90 and result["links_omitted"] == 10
        assert any(t["reason"] == "links_limit" for t in result["truncations"])
        with pytest.raises(Fault):
            decode_envelope({"success": True, **result}, ADAPTER)
    observe(operation_source, '<article>첫째 문서</article><article>둘째 문서</article>' +
            ''.join(f'<a href="/{i}">link {i}</a>' for i in range(90)), steps)


def test_inline_text_preserves_visible_words_and_blocks(operation_source):
    async def steps(page):
        result = await page.evaluate("operation('content')")
        assert "금액: 2200원" in result["content"]
        assert "연구 자료 D02 전체 제목" in result["content"]
        assert "\n" in result["content"]
    observe(operation_source, '<h1>연구 자료 <span>D02</span> 전체 제목</h1>'
            '<p>금액: <strong>2200</strong>원</p>', steps)


def test_unicode_cursor_scope_and_stale_capture(operation_source):
    text = '🙂한글' * 500
    async def steps(page):
        snap = await page.evaluate("operation('snapshot')")
        ref = next(e['ref'] for e in snap['elements'] if e['role'] == 'region')
        first = await page.evaluate("ref => operation('content', {ref,limit:500})", ref)
        second = await page.evaluate("args => operation('content', args)", {
            'cursor': first['cursor'], 'offset': first['next_offset'], 'limit': 20000})
        assert first['content'] + second['content'] == text
        assert first['total_chars'] == len(text)
        assert first['links'] == []
        assert second['source_complete']
        await page.evaluate("operation('content')")
        with pytest.raises(Exception, match='STALE_CURSOR'):
            await page.evaluate("cursor => operation('content', {cursor})", first['cursor'])
        for args in ({'offset': -1}, {'offset': .5}, {'limit': 0}, {'limit': '500'}):
            with pytest.raises(Exception, match='INVALID_CONTENT_RANGE'):
                await page.evaluate("args => operation('content', args)", args)
    observe(operation_source, f'<div role="region">{text}</div><a href="/outside">밖</a>', steps)


def test_default_page_limit_is_partial_but_explicit_selection_is_not(operation_source):
    async def steps(page):
        default = await page.evaluate("operation('content')")
        with pytest.raises(Fault) as exc:
            decode_envelope({'success': True, **default}, ADAPTER)
        assert exc.value.code == 'PARTIAL_SOURCE'
        assert default['truncations'][0]['reason'] == 'limit'
        assert not default['capture_truncated']
        explicit = await page.evaluate("operation('content', {limit:12000})")
        decode_envelope({'success': True, **explicit}, ADAPTER)
        assert explicit['source_complete'] and explicit['next_offset'] == 12000
    observe(operation_source, '<main>' + '가' * 15000 + '</main>', steps)


def test_frame_metadata_uses_the_captured_content_url():
    source = """
import {EmbeddedTabs} from './frontend/electron/embedded-browser-tabs.js';
const tabs = new EmbeddedTabs({show(){},changed(){}});
tabs.frames=async()=>[{id:'frame',url:'https://fixture.test/new'}];
tabs.cdp=async(_record,method)=>method==='Page.createIsolatedWorld'
  ? {executionContextId:1}
  : {result:{value:{document_id:'doc',url:'https://fixture.test/old',content:'captured'}}};
console.log(JSON.stringify(await tabs.page({},'content',{cursor:'saved'})));
"""
    result = json.loads(subprocess.check_output(
        ['node', '--input-type=module', '-e', source], cwd=ROOT, text=True))
    assert result['frame'] == {'id': 'frame', 'url': result['url']}


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
