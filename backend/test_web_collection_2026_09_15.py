"""실제 조사 재발명: 메타·링크 관측, 모드 캐시, 출처별 문맥 선택과 fn 실행."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest

from common.pkg_utils import load_sibling
from tool_context import ToolContext

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "data/packages/installed/tools/web/handler.py"
OPS = ROOT / "data/packages/installed/tools/data-ops/handler.py"
URL = "https://fixture.test/article"
HTML = '''<html><head><title>검증 자료</title><base href="/docs/">
<link rel="canonical" href="../canonical">
<meta property="article:published_time" content="2026-09-14T12:00:00+09:00">
<script type="application/ld+json">{"@type":"NewsArticle","datePublished":"2026-09-13",
"dateModified":"not-a-date","author":{"name":"기자"}}</script></head><body>
<time datetime="2020-01-01">다른 날짜</time><article><p>''' + "긴 본문입니다. " * 40 + '''</p>
<a href="next?q=1#part">다음 문서</a><a href="javascript:alert(1)">실행</a>
<a href="mailto:abc@example.com">메일</a><a href="/original">원문</a>
</article></body></html>'''


@pytest.fixture
def crawler(monkeypatch, tmp_path):
    from common import spill
    monkeypatch.setattr(spill, "_root", lambda: str(tmp_path / "spill"))
    c = load_sibling(WEB, "tool_webcrawl")
    calls = []
    def fetch(url):
        calls.append(url)
        return SimpleNamespace(status_code=200, url=URL, content=HTML.encode(),
                               headers={"Content-Type": "text/html; charset=utf-8"})
    monkeypatch.setattr(c, "_http_get", fetch)
    monkeypatch.setattr(c, "_resolve_google_news", lambda url: None)
    monkeypatch.setattr(c, "_get_browser_session", lambda: None)
    monkeypatch.setattr(c, "_get_chrome_driver", lambda: None)
    return c, calls


def test_observations_keep_conflicting_dates_and_do_not_infer_publication(crawler):
    c, _ = crawler
    out = c.crawl_website(URL, op="metadata")
    rows = out["items"]
    dates = [r for r in rows if r["field"] == "published_at"]
    assert {r["value"] for r in dates} == {"2026-09-14T12:00:00+09:00", "2026-09-13"}
    assert all(r["source"] and r["raw"] and r["source_url"] == URL for r in rows)
    assert next(r for r in rows if r["field"] == "modified_at")["normalized"] is None
    assert next(r for r in rows if r["field"] == "date")["value"] == "2020-01-01"
    assert next(r for r in rows if r["field"] == "canonical_url")["value"] == "https://fixture.test/canonical"
    assert "text" not in out


@pytest.mark.parametrize("order", [("content", "links", "metadata"), ("metadata", "content", "links")])
def test_modes_share_snapshot_without_leaking_structure_into_content(crawler, order):
    c, calls = crawler
    views = {op: c.crawl_website(URL, op=op) for op in order}
    assert calls == [URL]
    assert len({v["source_ref"]["path"] for v in views.values()}) == 1
    assert all("_page_structure" not in v for v in views.values())
    assert [(r["text"], r["url"]) for r in views["links"]["items"]] == [
        ("다음 문서", "https://fixture.test/docs/next?q=1#part"), ("원문", "https://fixture.test/original")]
    assert views["content"]["items"][0]["paragraph_index"] == 1
    assert all(r["url"] == URL for r in views["content"]["items"])
    snapshot = json.loads(Path(views["content"]["source_ref"]["path"]).read_text())
    assert snapshot["_page_structure"]["metadata"] == views["metadata"]["items"]
    fresh = c.crawl_website(URL, op="links", refresh=True)
    assert calls == [URL, URL] and fresh["source_ref"] != views["links"]["source_ref"]


def test_empty_structure_is_success_and_malformed_jsonld_is_explicit(crawler, monkeypatch):
    c, _ = crawler
    monkeypatch.setattr(c, "_http_get", lambda u: SimpleNamespace(
        status_code=200, url=u, headers={}, content=b'<html><script type="application/ld+json">oops</script></html>'))
    result = c.crawl_website(URL, op="links")
    assert result["success"] and result["items"] == []
    assert result["partial"] and result["structure_errors"]


@pytest.mark.parametrize("status,html", [(403, HTML), (200, '<title>Just a moment</title>')])
def test_structure_modes_do_not_turn_blocked_pages_into_success(crawler, monkeypatch, status, html):
    c, _ = crawler
    monkeypatch.setattr(c, "_http_get", lambda u: SimpleNamespace(
        status_code=status, url=u, headers={}, content=html.encode()))
    assert not c.crawl_website(URL, op="metadata")["success"]


def test_pdf_structure_is_unsupported_and_invalid_op_does_not_fetch(crawler, monkeypatch):
    c, calls = crawler
    assert not c.crawl_website(URL, op="unknown")["success"] and not calls
    monkeypatch.setattr(c, "_crawl_website_impl", lambda *a, **kw:
                        {"success": True, "text": "PDF 본문", "title": "PDF"})
    assert c.crawl_website(URL, op="links")["reason"] == "structure_unavailable"


def filtered(rows, **over):
    h = load_sibling(OPS, "handler")
    context = {"before": 1, "after": 1, "by": "url", "limit": 2, **over}
    return h.execute({"_prev_result": {"items": rows, "errors": [{"error": "원천 실패"}],
                                                  "truncated": True},
                                 "where": {"field": "text", "op": "matches", "value": "hit"},
                                 "context": context}, ToolContext(str(ROOT), "data_filter"))


ROWS = [{"url": "a", "text": "앞", "paragraph_index": 1},
        {"url": "a", "text": "hit 하나", "paragraph_index": 2},
        {"url": "a", "text": "hit 둘", "paragraph_index": 3},
        {"url": "b", "text": "다른 문서", "paragraph_index": 1},
        {"url": "b", "_error": "수집 실패"},
        {"url": "c", "text": "hit 셋", "paragraph_index": 1}]


def test_context_keeps_sources_failures_overlap_and_exact_counts():
    out = filtered(ROWS)
    assert out["items"] == [ROWS[i] for i in (0, 1, 2, 4)]
    assert out["match_info"] == {"total_matches": 3, "selected_matches": 2, "omitted_matches": 1,
                                 "match_indices": [2, 3, 6], "selected_indices": [2, 3],
                                 "input_indices": [1, 2, 3, 5], "failure_count": 1}
    assert out["errors"] and out["truncated"]
    assert any(t["scope"] == "selection" and t["total"] == 3 for t in out["truncations"])
    assert filtered(ROWS, limit=0)["items"] == [ROWS[4]]
    assert filtered([])["items"] == []
    assert filtered([ROWS[4]])["items"] == [ROWS[4]]


def test_unknown_source_does_not_join_unrelated_context():
    rows = [{"text": "앞"}, {"text": "hit"}, {"text": "뒤"}]
    assert filtered(rows)["items"] == [rows[1]]


@pytest.mark.parametrize("options", [{"before": -1}, {"limit": True}, {"after": "1"}, {"typo": 1}])
def test_context_options_reject_misuse(options):
    assert filtered(ROWS, **options)["success"] is False


def test_named_idiom_runs_real_parser_filter_and_preserves_diagnostics():
    sys.path.insert(0, str(ROOT / "scripts"))
    from idiom_experiment_worker import run_trial
    from idiom_experiment_cases import decoded
    code = '$문단=' + json.dumps(ROWS, ensure_ascii=False) + '; '
    code += '[fn:본문에서찾기]{목록:$문단,패턴:"hit",문맥:1,개수:2}'
    out = run_trial(code, "dedup")
    assert out["result"]["success"], out
    final = decoded(out["result"]["final_result"])
    assert final["items"] == [ROWS[i] for i in (0, 1, 2, 4)]
    assert final["match_info"]["omitted_matches"] == 1
    assert out["observed"]["brief"] == 0


def test_handler_and_ibl_declared_modes(crawler, monkeypatch):
    c, _ = crawler
    h = load_sibling(WEB, "handler")
    original = h.load_module
    monkeypatch.setattr(h, "load_module", lambda n: c if n == "tool_webcrawl" else original(n))
    result = json.loads(h.execute({"url": URL, "op": "links"}, ToolContext(str(ROOT), "crawl_website")))
    assert len(result["items"]) == 2 and result["items"][0]["source_url"] == URL


def test_cache_isolated_by_project_for_all_modes(crawler, tmp_path):
    c, calls = crawler
    first = c.crawl_website(URL, op="metadata", project_path=str(tmp_path / "a"))
    other = c.crawl_website(URL, op="links", project_path=str(tmp_path / "b"))
    again = c.crawl_website(URL, op="links", project_path=str(tmp_path / "a"))
    assert len(calls) == 2
    assert first["source_ref"] == again["source_ref"] != other["source_ref"]


def test_playwright_structure_keeps_frame_source_and_reports_missing_frame(crawler):
    import asyncio
    c, _ = crawler

    class Frame:
        def __init__(self, url, html):
            self.url, self.html = url, html

        async def content(self):
            if self.html is None:
                raise RuntimeError("frame detached")
            return self.html

        async def inner_text(self, selector):
            return "프레임 본문 " * 40

    class Page:
        url = URL
        frames = [Frame(URL, HTML), Frame("https://frame.test/a", '<a href="next">자식</a>'),
                  Frame("https://failed.test", None)]

        async def goto(self, *args, **kwargs):
            return SimpleNamespace(status=200)

        async def wait_for_load_state(self, *args, **kwargs):
            pass

        async def title(self):
            return "제목"

    class Session:
        closed = []

        async def ensure_browser(self, **kwargs):
            pass

        async def new_tab(self):
            return "owned"

        def get_tab_page(self, tab):
            return Page()

        async def close_tab(self, tab):
            self.closed.append(tab)

    session = Session()
    raw = asyncio.run(c._crawl_playwright_async(session, URL, None, op="links"))
    result = c._structure().project(raw, "links")
    assert result["success"] and result["partial"] and session.closed == ["owned"]
    assert any(r["url"] == "https://frame.test/next" and r["source_url"] == "https://frame.test/a"
               for r in result["items"])
    assert result["structure_errors"][0]["source_url"] == "https://failed.test"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
