"""에누리 검색의 공개 JSON-LD ItemList. 표준 라이브러리 파싱으로 폰에서도 사용.

현재 검증 범위는 기본 정렬 첫 페이지다. 다른 페이지·정렬을 조용히 무시하지 않는다.
추천 상품과 빈 검색 결과를 구별하기 위해 검색어가 붙은 목록만 사용한다.
"""
import json
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urlsplit, parse_qs

_backend_dir = str(Path(__file__).resolve().parents[5] / "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from common.http_fetch import chrome_get

_SEARCH = "https://price.enuri.com/search"


class _JsonLd(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.active = False
        self.parts = []
        self.documents = []
        self.invalid = 0

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.active = dict(attrs).get("type", "").lower() == "application/ld+json"
            self.parts = []

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.active:
            try:
                self.documents.append(json.loads("".join(self.parts)))
            except ValueError:
                self.invalid += 1
            self.active = False


def _lists(value):
    if isinstance(value, list):
        for item in value:
            yield from _lists(item)
    elif isinstance(value, dict):
        if value.get("@type") == "ItemList":
            yield value
        if "@graph" in value:
            yield from _lists(value["@graph"])


def parse_enuri(html, query, limit=5):
    parser = _JsonLd()
    parser.feed(html)
    matching = [d for d in _lists(parser.documents)
                if d.get("name") == query + " 검색결과"]
    if len(matching) != 1 or not isinstance(matching[0].get("itemListElement"), list):
        return {"success": False, "error_type": "source_changed", "items": [],
                "error": "에누리 검색 목록 구조를 확인하지 못했습니다. 0건으로 해석하지 마세요."}
    rows = matching[0]["itemListElement"]
    items = []
    invalid = 0
    for row in rows:
        product = row.get("item") if isinstance(row, dict) else None
        if not isinstance(product, dict) or product.get("@type") != "Product":
            invalid += 1
            continue
        name, link = product.get("name"), product.get("url")
        if not isinstance(name, str) or not name.strip() or not isinstance(link, str):
            invalid += 1
            continue
        parsed = urlsplit(link)
        catalog = parsed.hostname == 'price.enuri.com' and parsed.path.startswith('/catalog/')
        model = parse_qs(parsed.query).get('modelno', [])
        detail = (parsed.hostname == 'www.enuri.com' and parsed.path == '/detail.jsp'
                  and len(model) == 1 and re.fullmatch(r'[0-9]+', model[0]) and model[0].strip('0'))
        if parsed.scheme != "https" or parsed.username or parsed.password or not (catalog or detail):
            invalid += 1
            continue
        offers = product.get("offers")
        offers = offers if isinstance(offers, dict) else {}
        raw_price = offers.get("lowPrice") if offers.get("@type") == "AggregateOffer" else offers.get("price")
        price = str(raw_price).replace(",", "") if isinstance(raw_price, (int, str)) and not isinstance(raw_price, bool) else ""
        price = price if re.fullmatch(r"[0-9]+", price) and price.strip("0") else None
        rating = product.get("aggregateRating")
        rating = rating if isinstance(rating, dict) else {}
        items.append({"name": name.strip(), "price": price, "mall": "에누리", "link": link,
                      "image": product.get("image"), "category": "가격비교", "site": "enuri",
                      "spec": "", "product_id": product.get("sku"),
                      "currency": offers.get("priceCurrency"),
                      "price_status": "observed" if price is not None else "unknown",
                      "price_basis": "aggregate_low" if offers.get("@type") == "AggregateOffer" else "listed",
                      "shipping_included": None, "offer_count": offers.get("offerCount"),
                      "rating": rating.get("ratingValue"), "review_count": rating.get("reviewCount"),
                      "rental_hint": "렌탈" in name or "렌트" in name})
    result = {"items": items[:limit], "total": len(items[:limit]), "page_items": len(items)}
    if not rows:
        result["empty_reason"] = "no_results"
    if invalid:
        result["truncations"] = [{"scope": "source", "reason": "invalid_product", "count": invalid}]
    return result


def search_enuri(query, limit=5, page=1, sort="default"):
    if not isinstance(query, str) or not query.strip() or type(limit) is not int or not 1 <= limit <= 40:
        return {"success": False, "items": [], "error_type": "invalid_argument",
                "error": "query와 limit=1..40을 지정하세요."}
    if type(page) is not int or page != 1 or sort != "default":
        return {"success": False, "items": [], "error_type": "unsupported_option",
                "error": "에누리는 기본 정렬 첫 페이지를 지원합니다. page=1, sort=default를 사용하세요."}
    query = query.strip()
    response = chrome_get(_SEARCH, params={"keyword": query}, timeout=25, fallback="urllib")
    if response.status_code != 200:
        return {"success": False, "items": [], "error_type": "http_error",
                "error": f"에누리 HTTP {response.status_code}"}
    result = parse_enuri(response.text, query, limit)
    result.update(source="enuri", query=query, page=1, sort="default",
                  source_url=_SEARCH + "?" + urlencode({"keyword": query}),
                  observed_at=datetime.now(timezone.utc).isoformat())
    return result
