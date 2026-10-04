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
    assert result["errors"][0]["reason"] == "제목 잘림" and result["errors"][0]["attempts"] == 1
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


def refused(candidate, error):
    return {"key": candidate["key"], "report_date": candidate["report_date"], "url": candidate["url"], "_error": error}


def test_refused_source_stops_retrying_after_repeated_evidence(news):
    """2026-10-01: 차단된 출처가 매시 재시도되며 트리거를 61회 연속 실패로 만들었다."""
    module, candidate = news
    row = refused(candidate, 'Step 1 에러: {"success": false, "reason": "bot_blocked", "error": "HTTP 403: 봇 차단"}')
    for attempt in range(1, module.MAX_BLOCKED + 1):
        assert module.prepare()["pending"] == 1
        error = module.normalize([row])["errors"][0]
        assert error["reason"] == "원문 제목 확인 실패" and error["attempts"] == attempt
    prepared = module.prepare()
    assert prepared["items"] == [] and prepared["pending"] == 0 and prepared["unreachable"] == 1
    status = module.main({"op": "status"})
    assert status["success"] is True and status["pending_count"] == 0
    assert status["unreachable"][0]["url"] == candidate["url"] and status["unreachable"][0]["attempts"] == module.MAX_BLOCKED
    module.main({"op": "retry", "keys": [candidate["key"]]})
    assert module.prepare()["pending"] == 1


def test_transient_failure_is_not_counted_as_refusal(news):
    module, candidate = news
    row = refused(candidate, "Step 1 에러: 시간 초과")
    for _ in range(module.MAX_BLOCKED + 2):
        error = module.normalize([row])["errors"][0]
        assert "attempts" not in error
    assert module.prepare()["pending"] == 1
    assert module.main({"op": "status"})["success"] is False


@pytest.mark.parametrize("rows,reason,evidence", [
    (lambda m, c: [metadata(c, "AI 새 소식…")], "제목 잘림", "AI 새 소식…"),
    (lambda m, c: [refused(c, "Step 1 에러: 이 수집 결과는 HTML 구조를 제공하지 않습니다(PDF 등). 본문은 op:content로 읽으세요.")],
     "원문 제목 확인 실패", "HTML 구조를 제공하지 않습니다"),
    (lambda m, c: [{**c, "field": "title", "value": "AI 새 소식", "source": "title",
                    "source_url": "https://news.google.com/rss/articles/abc"}], "원문 주소 미해소", "news.google.com"),
])
def test_repeated_non_refusal_failures_give_up_with_evidence(news, rows, reason, evidence):
    """2026-10-04: PDF 출처의 '구조 없음'은 거절 증거가 아니라 세지 않았고, 매시 재시도되며 32회 연속 실패로 남았다.
    실패 사유를 가리지 않고 세되, 증거 문구를 남겨 같은 사유가 쌓이는 것이 보이게 한다."""
    module, candidate = news
    for attempt in range(1, module.MAX_BLOCKED + 1):
        assert module.prepare()["pending"] == 1
        error = module.normalize(rows(module, candidate))["errors"][0]
        assert error["reason"] == reason and error["attempts"] == attempt and evidence in error["evidence"]
    prepared = module.prepare()
    assert prepared["pending"] == 0 and prepared["unreachable"] == 1
    status = module.main({"op": "status"})
    assert status["success"] is True and evidence in status["unreachable"][0]["evidence"]
    module.main({"op": "retry", "keys": [candidate["key"]]})
    assert module.prepare()["pending"] == 1


@pytest.mark.parametrize("error", ["Step 1 에러: 시간 초과", "Connection reset by peer", "원문 보관 실패: 디스크", "HTTP 429: 봇 차단"])
def test_transient_failures_of_any_reason_are_not_counted(news, error):
    module, candidate = news
    for _ in range(module.MAX_BLOCKED + 2):
        error_row = module.normalize([refused(candidate, error)])["errors"][0]
        assert "attempts" not in error_row
    assert module.prepare()["pending"] == 1


def test_pdf_first_page_heading_outranks_embedded_title_and_filename_is_never_a_title(news):
    """EADV 보도자료: 내장 제목이 비어 파일명이 제목으로 나왔다. 첫 쪽 최대 글꼴 줄이 근거 있는 제목이다."""
    module, candidate = news
    result = module.normalize([
        metadata(candidate, "Microsoft Word - Press release", "pdf.info.title"),
        metadata(candidate, "Autonomous AI could create capacity for thousands more dermatology appointments, real-world study finds",
                 "pdf.page[1].largest_font(16pt)"),
    ])
    assert result["errors"] == []
    assert result["items"][0]["original_title"].startswith("Autonomous AI could create capacity")


def test_success_after_refusals_clears_the_count(news):
    module, candidate = news
    module.normalize([refused(candidate, "HTTP 403")])
    assert module.load_state()["blocked"][candidate["key"]]["count"] == 1
    assert module.normalize([metadata(candidate, "AI 새 소식")])["errors"] == []
    assert candidate["key"] not in module.load_state()["blocked"]


def _report(module, name, body, urls):
    report = module.REPORTS / f"ai_trend_report_{name}.md"
    report.write_text(body)
    verified = module.REPORTS / f"_verified_rows_{name}.json"
    verified.write_text(json.dumps([{"verified": True, "label": "NEW", "url": u} for u in urls]))
    for file in (report, verified):
        os.utime(file, (1, 1))
    ledger = module.REPORTS / "_coverage_ledger.json"
    ledger.write_text(json.dumps(json.loads(ledger.read_text()) + [{"date": name, "file": report.name}]))


def test_source_cited_in_body_counts_without_a_sources_heading(news):
    """10-01 호: 출처를 본문에 인용했지만 절 제목이 '조사 범위와 검증 메모'라 통째로 막혔다."""
    module, _ = news
    _report(module, "2026-09-16", "# 보고서\n\n본문 [발표](https://example.com/a?utm_source=x).\n\n## 조사 범위와 검증 메모\n",
            ["https://example.com/a", "https://example.com/not-cited"])
    prepared = module.prepare()
    assert prepared["issues"] == []
    assert [c["url"] for c in prepared["items"] if c["report_date"] == "2026-09-16"] == ["https://example.com/a"]


def test_report_citing_none_of_its_verified_sources_is_an_issue(news):
    module, _ = news
    _report(module, "2026-09-17", "# 보고서\n\n## 출처\n[검증 원장](_verified_rows_2026-09-17.json)\n", ["https://example.com/b"])
    prepared = module.prepare()
    assert prepared["issues"] == [{"report_date": "2026-09-17", "reason": "보고서가 검증 출처를 인용하지 않음"}]
    assert all(c["report_date"] != "2026-09-17" for c in prepared["items"])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
