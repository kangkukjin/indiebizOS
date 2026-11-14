"""일감공고수집(data/scripts/work_market_scan.py) — 나라장터 전국 표본의 계약.

2026-11-14 실측이 남긴 세 가지를 고정한다.
  W1. 직전 24시간은 평일 670~1,000건이다. 첫 쪽만 읽으면 전날 오전 몇 시간치만 표본이 된다 →
      전체 건수에 닿을 때까지 다음 쪽을 읽고, 못 읽으면 완전한 표본이라고 말하지 않는다.
  W2. 변경·취소는 차수를 올린 새 행으로 온다 → 같은 공고번호는 마지막 차수만 남고,
      마지막이 취소면 앞 차수도 열린 공고로 남지 않는다.
  W3. 표본 비교의 단위는 공고다 → 차수만 오른 변경공고는 새 공고가 아니다.
네트워크는 타지 않는다(쪽 조회를 가짜로 바꾼다).
"""
import importlib.util
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 13, 3, 0, tzinfo=ZoneInfo("Asia/Seoul"))


@pytest.fixture(scope="module")
def scan():
    spec = importlib.util.spec_from_file_location(
        "work_market_scan_under_test", ROOT / "data" / "scripts" / "work_market_scan.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bid(number, order="000", kind="등록공고", close="2026-11-20 10:00:00", price="1000000", title=None):
    return {"bidNtceNo": number, "bidNtceOrd": order, "ntceKindNm": kind,
            "bidNtceNm": title or f"용역 {number}", "bidClseDt": close, "presmptPrce": price,
            "dminsttNm": "수요기관", "bidNtceDt": "2026-11-12 09:00:00",
            "bidNtceDtlUrl": f"https://example.invalid/{number}/{order}",
            "pubPrcrmntLrgClsfcNm": "ICT 서비스 ", "pubPrcrmntClsfcNm": "정보시스템개발서비스"}


def test_w2_last_order_is_the_current_state(scan):
    rows = scan.open_notices([
        bid("A"), bid("A", "001", "변경공고", price="2000000"),      # 변경 → 001 만
        bid("B"), bid("B", "001", "취소공고"),                        # 취소 → 000 도 빠진다
        bid("C", close="2026-11-13 02:00:00"),                        # 이미 마감
        bid("D", price=""),                                           # 금액 없음
    ], NOW)
    by_no = {r["bid_no"]: r for r in rows}
    assert set(by_no) == {"A-001", "D-000"}
    assert by_no["A-001"]["price"] == 2000000 and by_no["A-001"]["kind"] == "변경공고"
    assert by_no["A-001"]["price_text"] == "추정가격 2,000,000원"
    assert by_no["A-001"]["category"] == "ICT 서비스", "분류 이름의 끝 공백은 거르기 조건을 어긋나게 한다"
    assert by_no["D-000"]["price"] is None and by_no["D-000"]["price_text"] == ""


def test_w1_reads_every_page_until_total(scan, monkeypatch):
    pages = {1: [bid(f"P1-{i}") for i in range(3)], 2: [bid(f"P2-{i}") for i in range(2)]}
    asked = []

    def fake_page(auth, now, page_no):
        asked.append(page_no)
        return 5, list(pages.get(page_no, []))

    monkeypatch.setattr(scan, "bid_page", fake_page)
    monkeypatch.setattr(scan, "get_auth_query_params", lambda name: {"serviceKey": "x"})
    result = scan.national_bids(NOW)
    assert asked == [1, 2] and len(result["items"]) == 5
    assert result["complete_sample"] is True and result["warnings"] == []
    assert "5건 전체" in result["scope"]


def test_w1_partial_read_is_not_a_complete_sample(scan, monkeypatch):
    def fake_page(auth, now, page_no):
        if page_no == 1:
            return 5, [bid(f"P1-{i}") for i in range(3)]
        raise ValueError("나라장터 API HTTP 500")

    monkeypatch.setattr(scan, "bid_page", fake_page)
    monkeypatch.setattr(scan, "get_auth_query_params", lambda name: {"serviceKey": "x"})
    result = scan.national_bids(NOW)
    assert len(result["items"]) == 3
    assert result["complete_sample"] is False, "못 읽은 쪽이 있으면 표본 저장·비교 기준이 되면 안 된다"
    assert any("2쪽" in w for w in result["warnings"]) and "중 3건" in result["scope"]


def test_w3_sample_comparison_ignores_order_suffix(scan, tmp_path):
    (tmp_path / "2026-11-12.json").write_text(json.dumps(
        [{"bid_no": "A-000", "url": "u1"}, {"bid_no": "", "url": "u-nia"}]), encoding="utf-8")
    result = {"items": [{"bid_no": "A-001", "url": "u1b"}, {"bid_no": "Z-000", "url": "u2"},
                        {"bid_no": "", "url": "u-nia"}]}
    scan.compare_sample(result, tmp_path, "2026-11-13")
    assert [r["new_to_sample"] for r in result["items"]] == [False, True, False]
    assert result["previous_date"] == "2026-11-12"
    assert (tmp_path / "2026-11-13.json").exists()


def test_permission_failure_names_the_dataset_to_apply_for(scan, monkeypatch):
    class Response:
        status_code = 403

    monkeypatch.setattr(scan.requests, "get", lambda *a, **k: Response())
    with pytest.raises(ValueError) as failure:
        scan.bid_page({"serviceKey": "x"}, NOW, 1)
    message = str(failure.value)
    assert "입찰공고정보서비스" in message and "data.go.kr/data/15129394" in message
    assert "serviceKey" not in message
