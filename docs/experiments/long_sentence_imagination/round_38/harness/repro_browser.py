"""Read-only reproduction using synthetic public-document-shaped browser responses."""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
from common.pkg_utils import load_sibling  # noqa: E402

URL = 'https://fixture.test/research'
BODY = 'Verified research body. ' * 20
CODE = 'if ready:\n    save_backup()\n    check_values()'
HTML = f'<html><title>Research</title><body><nav>OUTSIDE MENU</nav><main><h1>Research</h1><p>{BODY}</p><pre>{CODE}</pre></main><footer>OUTSIDE FOOTER</footer></body></html>'
TEXT = f'OUTSIDE MENU\n\nResearch\n\n{BODY}\n\n{CODE}\n\nOUTSIDE FOOTER'


class Frame:
    url = URL
    async def content(self):
        return HTML
    async def inner_text(self, selector):
        return TEXT


class BrokenFrame:
    url = 'https://fixture.test/missing-evidence'
    async def content(self):
        raise RuntimeError('frame detached')
    async def inner_text(self, selector):
        raise RuntimeError('frame detached')


class Page:
    url = URL
    def __init__(self, broken=False):
        self.frames = [Frame()] + ([BrokenFrame()] if broken else [])
    async def goto(self, *a, **kw):
        return SimpleNamespace(status=200)
    async def wait_for_load_state(self, *a, **kw):
        pass
    async def title(self):
        return 'Research'


class Session:
    def __init__(self, broken=False):
        self.page = Page(broken)
    async def ensure_browser(self, **kw):
        pass
    async def new_tab(self):
        return 'owned'
    def get_tab_page(self, tab):
        return self.page
    async def close_tab(self, tab):
        pass


async def main():
    crawl = load_sibling(ROOT/'data/packages/installed/tools/web/tool_webcrawl.py', 'tool_webcrawl')
    results = {}
    for broken in (False, True):
        raw = await crawl._crawl_playwright_async(Session(broken), URL, None)
        result = crawl._structure().project(raw, 'content')
        results['playwright_broken' if broken else 'playwright'] = result
    calls = []
    async def call(tool, params):
        calls.append(tool)
        if tool == 'tabs_create_mcp':
            return {'tabId': 1}
        if tool == 'javascript_tool':
            return {'text': json.dumps({'html': HTML, 'frames': 0} if 'outerHTML' in params['text'] else {'title':'Research', 'url':URL, 'status':200})}
        if tool == 'get_page_text':
            return {'text': TEXT}
        return {}
    raw = await crawl._crawl_chrome_async(SimpleNamespace(call_tool=call), URL, None)
    results['chrome'] = crawl._structure().project(raw, 'content')
    results['chrome_calls'] = calls
    results['checks'] = {k: {'body_only': 'OUTSIDE MENU' not in v.get('text',''), 'code_preserved': CODE in v.get('text',''), 'missing_frame_reported': bool(v.get('partial') or v.get('structure_errors') or not v.get('success'))} for k,v in results.items() if isinstance(v,dict)}
    path = Path(sys.argv[1]); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results,ensure_ascii=False,indent=2))
    print(json.dumps(results['checks'],ensure_ascii=False)); print(calls)


if __name__ == '__main__':
    asyncio.run(main())
