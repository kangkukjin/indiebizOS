# -*- coding: utf-8 -*-
"""다나와 상품 검색 — 순수 HTTP (2026-08-04 신설)

★왜 순수 HTTP 인가: 네이버 쇼핑 API 은퇴(2026-08, SE05)로 폰에서 쇼핑 검색이 완전히
비었다. 다나와는 Playwright(브라우저 자동화)로만 긁고 있어 PC 전용이었는데, 실측 결과
**TLS 지문 검사도 봇 차단도 없어 stdlib urllib 만으로 200 + 상품 40개**가 나온다
(curl_cffi 크롬위장조차 불필요 — 직방·크몽과 달리 위장이 필요 없는 순한 소스).
→ 폰(Chaquopy, curl_cffi 없음)에서도 그대로 동작. Playwright 는 폴백으로만 남긴다.

HTTP 계층: curl_cffi 있으면 사용, 없으면 stdlib urllib 폴백(폰 경로).
파싱: 상품 목록이 첫 HTML 에 SSR 로 박혀 있어 정규식으로 충분(크몽처럼 클라이언트
fetch 구조가 아니다 — 실측).

통화 = {total, items:[{name, price, mall, link, image, category, site, spec}]}
(handler 의 기존 다나와 통화와 동일 — 호출부 무변경.)
"""
import gzip
import re
import urllib.parse
import urllib.request

_SEARCH = "https://search.danawa.com/dsearch.php"
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
_HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Referer": "https://www.danawa.com/",
}


def _fetch(params: dict) -> str:
    """다나와 검색 HTML. curl_cffi 우선(있으면), 없으면 stdlib urllib(폰 경로)."""
    try:
        from curl_cffi import requests as _creq
    except ImportError:
        _creq = None

    if _creq is not None:
        r = _creq.get(_SEARCH, params=params, impersonate="chrome",
                      timeout=25, headers=_HEADERS)
        if r.status_code != 200:
            raise RuntimeError(f"다나와 HTTP {r.status_code}")
        return r.text

    url = _SEARCH + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=25) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return raw.decode("utf-8", "replace")


def _strip(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def _first(pattern: str, text: str, group: int = 1):
    m = re.search(pattern, text, re.S)
    return m.group(group) if m else None


def search_danawa(query: str, limit: int = 5) -> dict:
    """다나와 상품 검색. 인기(저장)순 상위 limit 개."""
    if not query:
        return {"total": 0, "items": [], "error": "검색어(query)를 입력해주세요."}

    # limit 는 다나와가 30/60/90 만 받는다 — 넉넉히 받아 클라이언트에서 자름.
    html = _fetch({
        "query": query, "originalQuery": query, "volumeType": "allvs",
        "page": 1, "limit": 30, "sort": "saveDESC", "list": "list",
        "boost": "true", "tab": "main",
    })

    # 상품 카드 = <li id="productItem12345"> — SSR 로 첫 HTML 에 박혀 있다(실측).
    blocks = re.split(r'<li[^>]+id="productItem\d+"', html)[1:]
    items = []
    for b in blocks:
        if len(items) >= limit:
            break
        name = _first(r'<p class="prod_name">\s*<a[^>]*>(.*?)</a>', b)
        if not name:
            continue
        name = _strip(name)
        if not name:
            continue

        link = _first(r'<p class="prod_name">\s*<a[^>]*href="([^"]+)"', b) or ""
        if link.startswith("//"):
            link = "https:" + link

        price = _first(r'<p class="price_sect">\s*<a[^>]*>\s*<strong>(.*?)</strong>', b)
        if price is None:
            price = _first(r"<strong>([\d,]{3,12})</strong>", b)
        price = _strip(price).replace(",", "") if price else "0"
        if not price.isdigit():
            price = "0"

        image = _first(r'<img[^>]+(?:data-original|src)="([^"]+)"', b) or ""
        if image.startswith("//"):
            image = "https:" + image

        spec = _first(r'<div class="spec_list">(.*?)</div>', b)
        spec = _strip(spec)[:200] if spec else ""

        items.append({
            "name": name,
            "price": price,
            "mall": "다나와",
            "link": link,
            "image": image,
            "category": "가격비교",
            "site": "danawa",
            "spec": spec,
        })

    return {"total": len(items), "items": items}
