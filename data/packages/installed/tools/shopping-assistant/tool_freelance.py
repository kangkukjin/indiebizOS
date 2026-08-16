# -*- coding: utf-8 -*-
"""
[sense:freelance] 프리랜서·외주 서비스 검색 — source 분기 (2026-08-04)

- source=kmong(기본): 크몽 비공식 내부 API (api.kmong.com/gig-app/*).
  봇 차단 없음, 인증 불요 — curl_cffi impersonate=chrome (직방·여기어때 선례).
  ★HTML 크롤링 불가: 페이지는 Next.js App Router 클라이언트 fetch 구조라
  첫 HTML 에 데이터가 없다(실측) — 반드시 이 내부 API 를 직접 호출.
  - type=gigs(기본): 서비스(긱) 검색 — /gig/v2/gigs/search
    제목·가격·판매자·평점·리뷰수·카테고리. 서비스 URL = kmong.com/gig/{gigId} (실측 200).
  - type=experts: 전문가(프리랜서) 검색 — /seller-profile/v2/seller-profiles/search
    닉네임·등급·자기소개·만족도·평균응답시간(분)·누적주문·포트폴리오수·전문분야·스킬·경력.
    프로필 URL = kmong.com/@{닉네임} (실측 200, /seller/{id} 는 404).
  - sortType 은 RANKING(인기)·SCORE(연관도)만 서버가 받는다(그 외 400 실측).
  - 가격 필터는 서버 파라미터 미발굴 → max_price 후필터(번개장터 region 후필터 선례).

숨고·위시켓 등은 후속 source 후보 (중고 sense:used 다중 source 선례).

통화 = items[{title, meta, summary, url, image, price}] (단일 통화 {items:[...]}. used/stay/realty 와 동일).
"""
import json
import os
import sys

_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "backend"))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# 크롬 TLS 위장 단일 소스 (감사 ⑥ — 옛 curl_cffi 가드 복붙을 수렴)
from common.http_fetch import chrome_get, has_curl_cffi

_API = "https://api.kmong.com/gig-app"
_HEADERS = {"Origin": "https://kmong.com", "Referer": "https://kmong.com/"}


def _to_int(v, default=None):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _fmt_won(n):
    n = _to_int(n)
    return f"{n:,}원" if n is not None else ""


def _get_json(path: str, params: dict):
    r = chrome_get(_API + path, params=params, timeout=20, headers=_HEADERS)
    if r.status_code != 200:
        raise RuntimeError(f"크몽 API HTTP {r.status_code} ({path})")
    return json.loads(r.text)


# ── type=gigs — 서비스(긱) 검색 ──────────────────────────────

def _search_gigs(query: str, limit: int, sort: str, max_price):
    """크몽 서비스 검색. perPage 최대 40 실측 — limit 초과분은 페이지 자동추적(최대 3p)."""
    sort_type = "SCORE" if sort == "score" else "RANKING"
    items_out = []
    total = None
    page = 1
    while len(items_out) < limit and page <= 3:
        data = _get_json("/gig/v2/gigs/search", {
            "keyword": query, "q": query,
            "isPrime": "false", "isFastReaction": "false", "isCompany": "false",
            "isNowContactable": "false", "hasPortfolios": "false",
            "includeAggregations": "false", "page": page,
            "perPage": min(max(limit, 20), 40), "sortType": sort_type,
            "service": "web",
            "rootCategoryId": "null", "subCategoryId": "null", "thirdCategoryId": "null",
        })
        total = data.get("totalItemCount", total)
        gigs = data.get("gigs") or []
        if not gigs:
            break
        for g in gigs:
            price = g.get("price")
            if max_price is not None and (_to_int(price) or 0) > max_price:
                continue
            seller = g.get("seller") or {}
            review = g.get("review") or {}
            cat = g.get("category") or {}
            meta_parts = [
                f"{_fmt_won(price)}~" if price else "",
                f"평점 {review['reviewAverage']}({review.get('reviewCount', 0)})"
                if review.get("reviewAverage") else "",
                seller.get("nickname", ""),
                seller.get("grade", "") if seller.get("grade") not in (None, "", "NEW") else "",
                "세금계산서" if seller.get("isAvailableTax") else "",
            ]
            item = {
                "title": g.get("title", ""),
                "meta": " · ".join(p for p in meta_parts if p),
                "summary": " > ".join(c for c in [cat.get("rootCategoryName"),
                                                  cat.get("subCategoryName")] if c),
                "url": f"https://kmong.com/gig/{g.get('gigId')}",
                "price": price,
                # 수치 칸 병기 (F1, 2026-08-16): 평점이 meta 텍스트에만 있으면
                # "평점순" sort 파이프가 원리적으로 막힌다.
                "rating": review.get("reviewAverage"),
                "reviews": review.get("reviewCount"),
            }
            images = g.get("images") or []
            if images:
                item["image"] = images[0]
            items_out.append(item)
            if len(items_out) >= limit:
                break
        if page >= data.get("lastPage", 1):
            break
        page += 1
    return {"source": "kmong", "type": "gigs", "total": total,
            "items": items_out}


# ── type=experts — 전문가(프리랜서) 검색 ─────────────────────

def _search_experts(query: str, limit: int, sort: str):
    """크몽 전문가 검색. 응답이 긱보다 풍부 — 응답시간·주문수·전문분야·경력까지."""
    sort_type = "SCORE" if sort == "score" else "RANKING"
    items_out = []
    total = None
    page = 1
    while len(items_out) < limit and page <= 3:
        data = _get_json("/seller-profile/v2/seller-profiles/search", {
            "keyword": query, "isFastReaction": "false", "isCompany": "false",
            "isResident": "false", "hasPortfolios": "false",
            "sortType": sort_type, "page": page,
            "perPage": min(max(limit, 20), 40), "includeAggregations": "false",
        })
        pg = data.get("sellerProfilePage") or {}
        total = pg.get("totalItemCount", total)
        rows = pg.get("items") or []
        if not rows:
            break
        for row in rows:
            s = row.get("seller") or {}
            review = s.get("review") or {}
            career = s.get("careerInfo") or {}
            gig = row.get("gig") or {}
            specialties = [sp.get("specialtyName") for sp in (s.get("specialties") or [])
                           if sp.get("specialtyName")]
            resp_min = s.get("averageResponseTimesInMinutes")
            meta_parts = [
                s.get("grade", "") if s.get("grade") not in (None, "", "NEW") else "",
                f"평점 {round(review['reviewAverage'], 1)}({review.get('reviewCount', 0)})"
                if review.get("reviewAverage") else "",
                f"경력 {career['totalCareerYear']}년" if career.get("totalCareerYear") else "",
                f"주문 {s['ordersCount']}건" if s.get("ordersCount") else "",
                f"응답 {resp_min}분" if resp_min else "",
                f"만족도 {s['satisfactionPoint']}%" if s.get("satisfactionPoint") else "",
            ]
            desc = (s.get("description") or "").replace("\n", " ").strip()
            summary_parts = [", ".join(specialties[:4]), desc[:120]]
            item = {
                "title": s.get("nickname", ""),
                "meta": " · ".join(p for p in meta_parts if p),
                "summary": " — ".join(p for p in summary_parts if p),
                "url": f"https://kmong.com/@{s.get('nickname', '')}",
                "price": gig.get("price"),
                "rating": (round(review["reviewAverage"], 2)
                           if review.get("reviewAverage") else None),
                "reviews": review.get("reviewCount"),
            }
            if s.get("thumbnail"):
                item["image"] = s["thumbnail"]
            if gig.get("gigId"):
                item["gig_url"] = f"https://kmong.com/gig/{gig['gigId']}"
                item["gig_title"] = gig.get("title", "")
            items_out.append(item)
            if len(items_out) >= limit:
                break
        if page >= pg.get("lastPage", 1):
            break
        page += 1
    return {"source": "kmong", "type": "experts", "total": total,
            "items": items_out}


# ── 엔트리 ───────────────────────────────────────────────────

def search_freelance(tool_input: dict) -> dict:
    if not has_curl_cffi():
        return {"success": False, "error": "curl_cffi 미설치 — 크몽 소스는 curl_cffi 가 필요합니다.", "items": []}
    query = (tool_input.get("query") or tool_input.get("q") or "").strip()
    if not query:
        return {"success": False, "error": "검색어(query)를 입력해주세요. 예: {query: \"로고디자인\"}", "items": []}
    source = (tool_input.get("source") or "kmong").lower()
    if source != "kmong":
        return {"success": False, "error": f"알 수 없는 source: {source} (현재 kmong 만 지원)", "items": []}
    search_type = (tool_input.get("type") or "gigs").lower()
    limit = _to_int(tool_input.get("limit"), 20)
    sort = (tool_input.get("sort") or "ranking").lower()
    max_price = _to_int(tool_input.get("max_price"))

    try:
        if search_type in ("experts", "expert", "sellers", "seller", "전문가"):
            return _search_experts(query, limit, sort)
        if search_type in ("gigs", "gig", "services", "service", "서비스"):
            return _search_gigs(query, limit, sort, max_price)
        return {"success": False, "error": f"type '{search_type}' 미지원 — gigs(서비스)/experts(전문가) 중 선택.",
                "items": []}
    except Exception as e:
        return {"success": False, "error": f"크몽 조회 실패: {e}", "items": []}
