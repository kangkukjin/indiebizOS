# -*- coding: utf-8 -*-
"""다나와 공개 검색의 상태 데이터와 상품 카드를 읽는다. 두 전송 경로가 같은 파서를 쓴다.

page는 원천의 40개 단위 페이지, limit는 해당 페이지에서 선택할 개수다.
원천 기본 정렬만 지원한다. 표시 가격은 배송·옵션·렌탈을 확정한 구매 총액이 아니다.
"""
import os
import json
import re
import sys
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlencode

_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "backend"))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# 크롬 위장 GET 단일 소스 (감사 ⑥) — fallback="urllib" 이 폰(curl_cffi 없음) 경로
from common.http_fetch import CHROME_UA, chrome_get

_SEARCH = "https://search.danawa.com/dsearch.php"
_HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Referer": "https://www.danawa.com/",
}


def _fetch(params: dict) -> str:
    """다나와 검색 HTML. curl_cffi 우선(있으면), 없으면 stdlib urllib(폰 경로)."""
    r = chrome_get(_SEARCH, params=params, timeout=25, headers=_HEADERS,
                   fallback="urllib")
    if r.status_code != 200:
        raise RuntimeError(f"다나와 HTTP {r.status_code}")
    return r.text


def _strip(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def _first(pattern: str, text: str, group: int = 1):
    m = re.search(pattern, text, re.S)
    return m.group(group) if m else None


PAGE_SIZE = 40


class _SearchData(HTMLParser):
    """Next Flight의 문자열만 JSON으로 읽는다. 페이지 JavaScript는 실행하지 않는다."""
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.active = False
        self.parts = []
        self.chunks = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            self.active = 'src' not in dict(attrs)
            self.parts = []

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag != 'script' or not self.active:
            return
        self.active = False
        match = re.fullmatch(r'\s*self\.__next_f\.push\((.*)\)\s*;?\s*', ''.join(self.parts), re.S)
        if not match:
            return
        try:
            value = json.loads(match[1])
        except ValueError:
            return
        if isinstance(value, list) and len(value) == 2 and value[0] == 1 and isinstance(value[1], str):
            self.chunks.append(value[1])


def _state_result(html, query, page, limit):
    parser = _SearchData()
    parser.feed(html)
    stream = ''.join(parser.chunks)
    matches = []
    for hit in re.finditer(r'"queries"\s*:\s*', stream):
        try:
            queries, _ = json.JSONDecoder().raw_decode(stream, hit.end())
        except ValueError:
            continue
        if not isinstance(queries, list):
            continue
        for entry in queries:
            if not isinstance(entry, dict):
                continue
            key = entry.get('queryKey')
            if not isinstance(key, list) or len(key) != 3 or key[:2] != ['search', 'productList']:
                continue
            scope = key[2]
            if not isinstance(scope, dict) or (query is not None and scope.get('keyword') != query):
                continue
            if str(scope.get('page')) != str(page):
                continue
            state = entry.get('state', {})
            if not isinstance(state, dict) or state.get('status') != 'success':
                continue
            envelope = state.get('data')
            if isinstance(envelope, dict) and envelope.get('kind') == 'fetched':
                matches.append(envelope.get('data'))
    if len(matches) != 1 or not isinstance(matches[0], dict):
        return None
    data = matches[0]
    rows, paging = data.get('products'), data.get('page')
    if not isinstance(rows, list) or not isinstance(paging, dict) or str(paging.get('current')) != str(page):
        return None
    count = data.get('count')
    if not rows and (not isinstance(count, dict) or type(count.get('total')) is not int or count['total'] != 0):
        return None  # 검색 건수는 있는데 아직 목록이 없는 셸을 정상 0건으로 만들지 않는다.
    items, invalid = [], 0
    for row in rows:
        if not isinstance(row, dict):
            invalid += 1
            continue
        name, link = row.get('productName'), row.get('linkUrl')
        if not isinstance(name, str) or not _strip(name) or not isinstance(link, str) or not link.startswith(('https://', 'http://')):
            invalid += 1
            continue
        name = unescape(_strip(name))
        raw_price = row.get('minPrice')
        price = str(raw_price).replace(',', '') if type(raw_price) in (int, str) else ''
        price = price if re.fullmatch(r'[0-9]+', price) and price.strip('0') else None
        summary = row.get('summary')
        desc = summary.get('desc', []) if isinstance(summary, dict) else []
        spec = ' / '.join(unescape(_strip(part)) for part in desc if isinstance(part, str)) if isinstance(desc, list) else ''
        items.append({'name': name, 'price': price, 'mall': '다나와', 'link': unescape(link),
                      'image': row.get('imageUrl', ''), 'category': '가격비교', 'site': 'danawa',
                      'spec': spec, 'currency': 'KRW', 'product_id': row.get('productSeq'),
                      'price_status': 'observed' if price is not None else 'unknown',
                      'price_basis': 'listed', 'shipping_included': None,
                      'rental_hint': '렌탈' in name or '렌트' in name})
    result = {'total': len(items[:limit]), 'items': items[:limit], 'page_items': len(items)}
    if not rows:
        result['empty_reason'] = 'no_results'
    if invalid:
        result['truncations'] = [{'scope': 'source', 'reason': 'invalid_product', 'count': invalid}]
    return result


class _Cards(HTMLParser):
    """상품의 중첩 li를 세어 다음 카드·푸터 가격이 앞 상품에 붙지 않게 한다."""
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.depth = 0
        self.parts = []
        self.cards = []

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            if self.depth:
                self.depth += 1
            elif dict(attrs).get("id", "").startswith("productItem"):
                self.depth = 1
                self.parts = []
        if self.depth:
            self.parts.append(self.get_starttag_text())

    def handle_startendtag(self, tag, attrs):
        if self.depth:
            self.parts.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if self.depth:
            self.parts.append(f"</{tag}>")
            if tag == "li":
                self.depth -= 1
                if not self.depth:
                    self.cards.append("".join(self.parts))

    def handle_data(self, data):
        if self.depth:
            self.parts.append(data)

    def handle_entityref(self, name):
        self.handle_data(f"&{name};")

    def handle_charref(self, name):
        self.handle_data(f"&#{name};")


def search_params(query, page=1, sort="default"):
    # sort/list/tab 등 옛 UI 인자를 붙이면 일부 검색어는 빈 셸만 반환한다.
    return {"query": query, **({"page": page} if page != 1 else {})}


def parse_danawa(html, limit=5, *, query=None, page=1):
    """요청한 검색 상태를 우선 읽고 구형 상품 카드도 지원한다. 광고·추천 상태는 제외한다."""
    current = _state_result(html, query, page, limit)
    if current is not None:
        return current
    parser = _Cards()
    parser.feed(html)
    blocks = parser.cards
    items = []
    invalid = 1 if parser.depth else 0
    for b in blocks:
        name = _first(r'<p\b[^>]*class=["\'][^"\']*\bprod_name\b[^"\']*["\'][^>]*>\s*<a\b[^>]*>(.*?)</a>', b)
        link = _first(r'<p\b[^>]*class=["\'][^"\']*\bprod_name\b[^"\']*["\'][^>]*>\s*<a\b[^>]*href=["\']([^"\']+)', b)
        name = unescape(_strip(name)) if name else ""
        link = unescape(link or "")
        if link.startswith("//"):
            link = "https:" + link
        if not name or not link.startswith(("https://", "http://")):
            invalid += 1
            continue
        section = _first(r'<p\b[^>]*class=["\'][^"\']*\bprice_sect\b[^"\']*["\'][^>]*>(.*?)</p>', b)
        raw_price = _first(r'<strong\b[^>]*>(.*?)</strong>', section or "")
        price = unescape(_strip(raw_price)).replace(",", "") if raw_price else ""
        # 0/비숫자/가격 없음은 무료 상품으로 바꾸지 않는다. 숫자 변환·비교는 하지 않는다.
        price = price if re.fullmatch(r"[0-9]+", price) and price.strip("0") else None
        image = _first(r'<img[^>]+(?:data-original|src)=["\']([^"\']+)', b) or ""
        if image.startswith("//"):
            image = "https:" + image
        spec = _first(r'<div\b[^>]*class=["\'][^"\']*\bspec_list\b[^"\']*["\'][^>]*>(.*?)</div>', b)
        items.append({"name": name, "price": price, "mall": "다나와", "link": link,
                      "image": unescape(image), "category": "가격비교", "site": "danawa",
                      "spec": unescape(_strip(spec or "")), "currency": "KRW",
                      "price_status": "observed" if price is not None else "unknown",
                      "price_basis": "listed", "shipping_included": None,
                      "rental_hint": "렌탈" in name or "렌트" in name})
    if not blocks:
        if not parser.depth and re.search(r'id=["\']nosearchArea["\']', html):
            return {"total": 0, "items": [], "empty_reason": "no_results"}
        return {"success": False, "error_type": "source_changed", "total": 0, "items": [],
                "error": "다나와 상품 목록·결과 없음 표지를 확인하지 못했습니다. 0건으로 해석하지 마세요."}
    result = {"total": len(items[:limit]), "items": items[:limit], "page_items": len(items)}
    if invalid:
        result["truncations"] = [{"scope": "source", "reason": "invalid_product",
                                  "count": invalid}]
    return result


def search_danawa(query: str, limit: int = 5, page: int = 1, sort: str = "default") -> dict:
    """원천 정렬·페이지를 유지하며 한 페이지에서 limit개를 선택한다."""
    if not isinstance(query, str) or not query.strip():
        return {"success": False, "total": 0, "items": [], "error": "검색어(query)를 입력해주세요."}
    if type(limit) is not int or not 1 <= limit <= PAGE_SIZE or type(page) is not int or not 1 <= page <= 100:
        return {"success": False, "items": [], "error_type": "invalid_argument",
                "error": "limit=1..40, page=1..100을 사용하세요."}
    if sort != "default":
        return {"success": False, "items": [], "error_type": "unsupported_option",
                "error": "다나와는 기본 정렬만 지원합니다. sort=default를 사용하세요."}
    query = query.strip()
    params = search_params(query, page, sort)
    result = parse_danawa(_fetch(params), limit, query=query, page=page)
    # 기본 진입점과 명시적 첫 페이지의 서버 렌더링 응답이 다를 때가 있다.
    # 실패에 한해 같은 범위를 한 번 재조회한다. 다른 페이지로 대체하지 않는다.
    if result.get("error_type") == "source_changed" and page == 1:
        params = {"query": query, "page": 1}
        result = parse_danawa(_fetch(params), limit, query=query, page=page)
    # 기존 정상 빈 결과의 모양을 유지한다. handler는 공통 조회 범위를 부착한다.
    if result.get("empty_reason") == "no_results":
        return result
    result.update(source="danawa", query=query, page=page, page_size=PAGE_SIZE, sort=sort,
                  source_url=_SEARCH + "?" + urlencode(params),
                  observed_at=datetime.now(timezone.utc).isoformat())
    return result
