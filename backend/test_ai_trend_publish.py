"""동향 보고서 발행: 최신 선택·원문 보존·공개 대기·실패 시 기존 판 보존."""
import importlib.util
from pathlib import Path

import boot_paths  # noqa: F401
import pytest
from bs4 import BeautifulSoup
from supervision_delivery import STAGING_ENV

ROOT = Path(__file__).resolve().parents[1]
SOURCE = """# 오늘의 보고서

> 조사일과 범위

## 한눈에
- **중요한 변화**와 설명

## 기술·연구
### NEW · 새 연구
내용과 [공식 출처](https://example.com/source).

| 대상 | 의미 |
|---|---|
| 모델 | 긴 설명을 보존한다 |

## 출처
1. [원문](https://example.com/source)
"""


@pytest.fixture
def publisher(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("test_trend_publisher", ROOT / "data/scripts/ai_trend_publish.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module.renderer, "_ROOT", tmp_path)
    monkeypatch.delenv(STAGING_ENV, raising=False)
    folder = tmp_path / "outputs/ai_trend_reports"
    folder.mkdir(parents=True)
    return module, folder, tmp_path / "공유창고/0/오늘의 AI 보고서.html"


def test_latest_source_is_filename_date_and_links_emphasis_survive(publisher):
    mod, folder, target = publisher
    (folder / "ai_trend_report_2026-10-06.md").write_text(SOURCE)
    (folder / "ai_trend_report_2026-10-05.md").write_text("# older but modified later")
    (folder / "ai_trend_report_draft.md").write_text("# draft")
    result = mod.publish({})
    assert result["published"] and result["source"].endswith("2026-10-06.md")
    soup = BeautifulSoup(target.read_text(), "html.parser")
    assert soup.select_one('meta[name="viewport"]')
    assert len(soup.select("h1")) == 1
    assert soup.select_one("strong").get_text() == "바로 읽기"
    assert soup.select_one(".brief-body strong").get_text() == "중요한 변화"
    assert len(soup.select('a[href="https://example.com/source"]')) == 2
    assert soup.select_one("td").get_text() == "모델"
    for link in soup.select("nav a"):
        assert soup.select_one(link["href"])


def test_explicit_saved_source_and_review_queue(publisher, tmp_path, monkeypatch):
    mod, folder, target = publisher
    source = folder / "ai_trend_report_2026-10-05.md"
    source.write_text(SOURCE)
    (folder / "ai_trend_report_2026-10-06.md").write_text("# later")
    target.parent.mkdir(parents=True)
    target.write_text("existing public bytes")
    monkeypatch.setenv(STAGING_ENV, str(tmp_path / "drafts"))
    out = mod.publish({"src": str(source)})
    assert out["publication_pending"] and not out["published"]
    assert target.read_text() == "existing public bytes"
    assert "오늘의 보고서" in Path(out["items"][0]["path"]).read_text()
    assert out["items"][0]["public_target"] == str(target)


def test_no_source_or_failed_replace_preserves_public_file(publisher, monkeypatch):
    mod, folder, target = publisher
    target.parent.mkdir(parents=True)
    target.write_text("existing public bytes")
    with pytest.raises(ValueError, match="없습니다"):
        mod.publish({})
    assert target.read_text() == "existing public bytes"
    (folder / "ai_trend_report_2026-10-06.md").write_text(SOURCE)

    def fail(*args):
        raise OSError("replace failed")

    monkeypatch.setattr(mod.renderer.os, "replace", fail)
    with pytest.raises(OSError, match="replace failed"):
        mod.publish({})
    assert target.read_text() == "existing public bytes"
    assert list(target.parent.glob("*.tmp")) == []


@pytest.mark.parametrize("width", [390, 1280])
def test_briefing_mobile_and_desktop_reading(publisher, width):
    from playwright.sync_api import sync_playwright
    from runtime_utils import setup_playwright_browsers_path
    mod, folder, target = publisher
    (folder / "ai_trend_report_2026-10-06.md").write_text(SOURCE)
    mod.publish({})
    setup_playwright_browsers_path()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 900})
        page.goto(target.as_uri())
        for scheme in ("light", "dark"):
            page.emulate_media(color_scheme=scheme)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert page.locator(".brief-story").is_visible()
            assert page.locator(".brief-body").evaluate("e => parseFloat(getComputedStyle(e).fontSize)") >= 17
            assert page.locator('a[href="https://example.com/source"]').count() == 2
        page.locator("nav a").last.click()
        assert page.url.endswith("#section-3")
        browser.close()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
