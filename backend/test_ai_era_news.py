"""뉴스 동기화: 정상 말줄임표·대체 메타 제목·게시 영수증 회귀."""
import boot_paths  # noqa: F401
import importlib.util
import io
import json
import os
from pathlib import Path

import pytest


@pytest.fixture
def news(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "data/scripts/ai_era_news.py"
    spec = importlib.util.spec_from_file_location("ai_era_news_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    reports = tmp_path / "reports"
    reports.mkdir()
    monkeypatch.setattr(module, "REPORTS", reports)
    monkeypatch.setattr(module, "STATE", tmp_path / "state" / "state.json")
    report = reports / "ai_trend_report_2026-09-15.md"
    report.write_text("# 보고서\n\n## 출처\nhttps://example.com/news\n")
    verified = reports / "_verified_rows_2026-09-15.json"
    verified.write_text(json.dumps([{
        "verified": True, "label": "NEW", "url": "https://example.com/news",
    }]))
    for file in (report, verified):
        os.utime(file, (1, 1))
    (reports / "_coverage_ledger.json").write_text(json.dumps([
        {"date": "2026-09-15", "file": report.name},
    ]))
    candidate = module.main({"op": "prepare"})["items"][0]
    return module, candidate


def metadata(candidate, title, source="meta[1][og:title]@content"):
    return {**candidate, "field": "title", "value": title,
            "source": source, "source_url": candidate["url"]}


@pytest.mark.parametrize("title", [
    "中 딥시크, IPO 앞두고 첫 CFO 내정…저가 AI 공세 강화",
    "AI 투자...기업 도입 확대",
    "AI 코딩 스타트업, 기업가치 상승",
])
def test_complete_headline_preserved(news, title):
    module, candidate = news
    result = module.main({"op": "normalize", "data": {
        "items": [metadata(candidate, title)],
    }})
    assert result["errors"] == []
    assert result["items"][0]["original_title"] == title
    assert module.main({"op": "status"})["pending_count"] == 1


@pytest.mark.parametrize("title", ["AI 새 소식…", "AI 새 소식...  ", "가", "가" * 501])
def test_incomplete_headline_stays_pending(news, title):
    module, candidate = news
    result = module.normalize([metadata(candidate, title)])
    assert result["items"] == []
    assert result["errors"] == [{"key": candidate["key"], "reason": "제목 잘림"}]
    assert module.load_state()["done"] == {}


def test_complete_alternative_is_used(news):
    module, candidate = news
    result = module.normalize([
        metadata(candidate, "새 모델 발표…", "jsonld[1].headline"),
        metadata(candidate, "새 모델 발표…지원 언어 확대"),
    ])
    assert result["items"][0]["original_title"] == "새 모델 발표…지원 언어 확대"
    assert result["errors"] == []


@pytest.mark.parametrize("title", ["", "404 Not Found", "Access Denied", "Just a moment..."])
def test_unavailable_original_is_not_published(news, title):
    module, candidate = news
    result = module.normalize([metadata(candidate, title)])
    assert result["items"] == []
    assert result["errors"][0]["reason"] == "원문 제목 확인 실패"
    assert module.main({"op": "status"})["success"] is False


@pytest.mark.parametrize("accepted", [True, False])
def test_only_matching_receipt_marks_done(news, monkeypatch, accepted):
    module, candidate = news
    row = module.normalize([metadata(candidate, "AI 발표…도입 확대")])["items"][0]
    row["title_ko"] = row["original_title"]
    monkeypatch.setattr(module.subprocess, "check_output", lambda *a, **k: "test-token")

    def post(request, timeout):
        sent = json.loads(request.data)["items"]
        assert set(sent[0]) == module.FIELDS
        assert sent[0]["title_ko"] == "AI 발표…도입 확대"
        assert timeout == 45
        return io.StringIO(json.dumps({
            "ok": True, "accepted": [candidate["key"]] if accepted else [],
            "inserted": 1, "updated": 0, "unchanged": 0,
        }))

    monkeypatch.setattr(module, "urlopen", post)
    if accepted:
        assert module.publish([row])["sent"] == 1
        assert module.prepare()["pending"] == 0
    else:
        with pytest.raises(ValueError, match="영수증 불일치"):
            module.publish([row])
        assert module.prepare()["pending"] == 1


def test_report_change_blocks_stale_translation(news):
    module, candidate = news
    row = module.normalize([metadata(candidate, "AI 새 소식")])["items"][0]
    row["title_ko"] = row["original_title"]
    report = module.REPORTS / "ai_trend_report_2026-09-15.md"
    report.write_text(report.read_text() + "\n수정됨\n")
    with pytest.raises(ValueError, match="보고서가 처리 중 변경됨"):
        module.publish([row])
    assert module.load_state()["done"] == {}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
