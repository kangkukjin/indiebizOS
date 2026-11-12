"""공개 발주 표본을 수집한다. 표본의 범위와 금액 원문은 편집자에게 함께 넘긴다."""
import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401
from common.auth_manager import get_auth_query_params  # noqa: E402
from file_script import atomic_json  # noqa: E402

WISHKET = "https://www.wishket.com/project/"
# 위시켓이 검색 URL에 저장하는 필터(모집 마감 제외, 최신 등록순, 1~3쪽).
WISHKET_FILTERS = (
    "KYYwJgvAKgTgrsAZAZxgFwgO2Ad0QBwEMBzYCARiA===",
    "KYYwJgvAKgTgrsAZAZxgFwgO2Ad0QBwEMBzYCAJiA===",
    "KYYwJgvAKgTgrsAZAZxgFwgO2Ad0QBwEMBzYCAZiA===",
)
NIA = "https://www.nia.or.kr/site/nia_kor/ex/bbs/"
BIDS = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService02/getBidPblancListInfoServc02"
KST = ZoneInfo("Asia/Seoul")


def page(url, params=None):
    response = requests.get(url, params=params, timeout=12)
    response.raise_for_status()
    return BeautifulSoup(response.content, "html.parser")


def field(node, selector):
    element = node.select_one(selector)
    return element.get_text(" ", strip=True) if element else ""


def match(pattern, text):
    found = re.search(pattern, text)
    return found[1] if found else ""


def wishket():
    items = {}
    warnings = []
    for index, setting in enumerate(WISHKET_FILTERS):
        if index:
            time.sleep(5)  # 위시켓 robots.txt의 요청 간격
        try:
            doc = page(WISHKET, {"d": setting})
            cards = doc.select(".project-organic-info")
            if not cards:
                raise ValueError("공개 목록 구조 또는 검색 결과를 확인할 수 없음")
            for card in cards:
                link = card.select_one("a.project-link[href]")
                if not link or "모집 중" not in field(card, ".project-status-label"):
                    continue
                url = urljoin(WISHKET, link["href"])
                items[url] = {
                    "title": link.get_text(" ", strip=True), "url": url,
                    "posted": match(r"(\d{4}\.\d\d\.\d\d)", field(card, ".start-recruitment-data")),
                    "price_text": field(card, ".budget"), "period": field(card, ".term"),
                    "kind": field(card, ".project-type-mark"),
                    "summary": field(card, ".project-classification-info"),
                    "access": "등급 제한" if "프라이빗" in field(card, ".project-status-label") else "공개",
                }
        except (requests.RequestException, ValueError) as exc:
            warnings.append(f"{index + 1}쪽 조회 실패 ({type(exc).__name__})")
            break
    return {"source": "위시켓", "series": "wishket", "complete_sample": not warnings, "scope": "모집 중, 최신 등록순 3쪽(최대 30건)",
            "warnings": warnings, "items": list(items.values())}


def nia_notices():
    """전국 API 불가 시 원 발주기관 게시판. 나라장터 공고번호가 있는 본공고를 식별한다."""
    doc = page(NIA + "List.do", {"cbIdx": "78336"})
    links = doc.select('a[onclick*="doBbsFView"]')
    if not links:
        raise ValueError("NIA 발주기관 목록 구조를 확인할 수 없음")
    rows, warnings = [], []
    for link in links:
        title = field(link, ".subject").split("첨부파일")[0].removesuffix("new").strip()
        number = match(r"doBbsFView\('78336','(\d+)'", link.get("onclick", ""))
        if not number or "입찰공고]" not in title or "취소" in title:
            continue
        url = NIA + f"View.do?cbIdx=78336&bcIdx={number}"
        try:
            text = page(url).get_text(" ", strip=True)
        except requests.RequestException:
            warnings.append(f"NIA 게시물 {number} 상세 조회 실패")
            continue
        bid = match(r"입찰공고번호\s*[:：]?\s*(R\d+BK\d+(?:-\d+)?)", text)
        deadline = match(r"제출\s*마감일시\s*[:：]?\s*(\d{4}/\d\d/\d\d\s+\d\d:\d\d)", text)
        if deadline and datetime.strptime(deadline, "%Y/%m/%d %H:%M").replace(tzinfo=KST) <= datetime.now(KST):
            continue
        price = match(r"사업금액\s*[:：]?\s*([\d,]+\s*원(?:\s*\([^)]{1,30}\))?)", text)
        rows.append({"title": title, "url": url, "agency": "한국지능정보사회진흥원",
                     "bid_no": bid, "deadline": deadline, "price_text": price,
                     "posted": match(r"(\d{4}\.\d\d\.\d\d)", field(link, ".src"))})
    return rows, warnings


def national_bids(now):
    auth = get_auth_query_params("data_go_kr")
    if not auth:
        raise ValueError("공공데이터포털 키 미설정")
    response = requests.get(BIDS, params={
        **auth, "inqryDiv": 1, "inqryBgnDt": (now - timedelta(hours=24)).strftime("%Y%m%d%H%M"),
        "inqryEndDt": now.strftime("%Y%m%d%H%M"), "type": "json", "numOfRows": 100, "pageNo": 1,
    }, timeout=15)
    # 인증 파라미터가 든 요청 URL을 오류·보고서에 출력하지 않는다.
    if response.status_code != 200:
        raise ValueError(f"나라장터 API HTTP {response.status_code}")
    envelope = response.json().get("response", {})
    if str(envelope.get("header", {}).get("resultCode")) not in {"00", "0"}:
        raise ValueError("나라장터 API 서비스 오류")
    body = envelope["body"]
    total = int(body["totalCount"])
    items = body["items"] or []
    if isinstance(items, dict):
        items = items.get("item", [])
    if total and not items:
        raise ValueError("나라장터 API 목록 구조 확인 필요")
    rows = []
    for bid in items:
        if "취소" in str(bid.get("ntceKindNm", "")) or "취소공고" in str(bid["bidNtceNm"]):
            continue
        deadline = bid.get("bidClseDt") or ""
        if deadline and deadline <= now.strftime("%Y-%m-%d %H:%M:%S"):
            continue
        amount = bid.get("presmptPrce")
        rows.append({"title": bid["bidNtceNm"], "bid_no": f"{bid['bidNtceNo']}-{bid['bidNtceOrd']}",
                     "agency": bid.get("dminsttNm") or bid.get("ntceInsttNm"),
                     "posted": bid.get("bidNtceDt"), "deadline": deadline,
                     "url": bid.get("bidNtceDtlUrl") or bid.get("bidNtceUrl"),
                     "price_text": f"추정가격 {amount}원" if amount else ""})
    return {"source": "나라장터", "series": "g2b", "complete_sample": True,
            "scope": f"최근 24시간 용역 공고 {total}건 중 첫 100건 이내, 취소·마감 제외",
            "warnings": [], "items": rows}


def procurement():
    try:
        return national_bids(datetime.now(KST))
    except (requests.RequestException, ValueError, KeyError) as exc:
        reason = str(exc) if type(exc) is ValueError else type(exc).__name__
    rows, warnings = nia_notices()
    return {"source": "나라장터·발주기관", "series": "nia", "complete_sample": not warnings,
            "scope": "대체 표본 · 한국지능정보사회진흥원 입찰 게시판 첫 쪽",
            "warnings": [reason, *warnings], "items": rows}


def compare_sample(scan, folder, today):
    """같은 출처의 직전 날짜와만 비교한다. 같은 날 재실행은 기준선을 바꾸지 않는다."""
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{today}.json"
    previous = max((p for p in folder.glob("????-??-??.json") if p.name < target.name), default=None)
    prior = json.loads(previous.read_text(encoding="utf-8")) if previous else []
    seen = {r.get("bid_no") or r.get("url") for r in prior}
    for row in scan["items"]:
        row["new_to_sample"] = ((row.get("bid_no") or row.get("url")) not in seen
                                if previous else None)
    atomic_json(target, scan["items"])
    scan["previous_date"] = previous.stem if previous else None


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    try:
        args = json.loads(sys.stdin.read() or "{}")
        source = args["source"]
        scan = {"wishket": wishket, "g2b": procurement}[source]()
        if args.get("track") and scan["complete_sample"]:
            folder = ROOT / "outputs" / "money_reports" / "samples" / scan["series"]
            compare_sample(scan, folder, datetime.now(KST).date().isoformat())
        print(json.dumps({"success": bool(scan["items"]) or scan["complete_sample"],
                          "observed_at": datetime.now(KST).isoformat(), **scan}, ensure_ascii=False))
    except (KeyError, ValueError, requests.RequestException) as exc:
        print(json.dumps({"success": False, "error": type(exc).__name__,
                          "message": "source(wishket/g2b) 또는 원천 응답을 확인하세요.", "items": []},
                         ensure_ascii=False))
        sys.exit(1)
