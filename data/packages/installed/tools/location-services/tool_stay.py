# -*- coding: utf-8 -*-
"""
[sense:stay] 숙박·단기임대 검색 — source 분기 (2026-07-13)

- source=goodchoice(기본): 여기어때(yeogi.com) — 호텔·모텔·펜션·게스트하우스 실시간 할인가.
  레거시 goodchoice.kr URL은 리다이렉트 중 keyword를 떨어뜨림 → www.yeogi.com 직접 호출.
  데이터는 __NEXT_DATA__ SSR 임베드(당근 JSON-LD 선례). 날짜별 요금·페이지네이션 서버 반영 실측 확인.
- source=33m2: 삼삼엠투 한 달 살기 — api.33m2.co.kr/v1/rooms 공개 JSON(키·인증 불요).
  주간요금(usingFee)·관리비·평수·좌표. page는 1부터. 서버측 min/maxUsingFee 필터.
- source=tourapi: 한국관광공사 TourAPI 4.0 — 공식 숙박 디렉토리(contentTypeId=32).
  DATA_GO_KR_API_KEY 사용. 가격 없음 — 권위 목록·연락처·좌표.

세 소스 모두 통합 통화 items[{title, meta, summary, url, image, lat, lng, price}] 반환.
TLS 지문 봇탐지 대비 curl_cffi impersonate=chrome (naver부동산 선례) — 33m2·yeogi에 적용.
"""
import os
import re
import json
from urllib.parse import quote as _q

try:
    from curl_cffi import requests as _creq
except ImportError:
    _creq = None
import requests as _plain_requests


# ── 공통 ──────────────────────────────────────────────────────

def _to_int(v, default=None):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _fmt_won(n):
    n = _to_int(n)
    if n is None:
        return ""
    if n >= 10000 and n % 10000 == 0:
        return f"{n // 10000}만원"
    return f"{n:,}원"


def _build_map(items_out):
    """items → 채팅 자동 렌더용 location_map 봉투.
    ★프론트 parseMapData(chatUtils.ts)는 type=='location_map'|'route_map' 봉투만 지도로 렌더하고
    그 외 [MAP:]은 텍스트에서 지운다 → type/center/zoom 필수(없으면 지도 안 뜸). markers는 {name,lat,lng} 필수."""
    pts = [i for i in items_out if i.get("lat") and i.get("lng")]
    if not pts:
        return None
    clat = sum(p["lat"] for p in pts) / len(pts)
    clng = sum(p["lng"] for p in pts) / len(pts)
    return {
        "type": "location_map",
        "center": {"name": "검색 결과", "lat": clat, "lng": clng},
        "zoom": 12,
        "markers": [{"name": p.get("title") or "", "lat": p["lat"], "lng": p["lng"],
                     "meta": p.get("summary"), "url": p.get("url")} for p in pts],
    }


# ── source=goodchoice (여기어때 / yeogi.com) ──────────────────

_YEOGI_URL = "https://www.yeogi.com/domestic-accommodations"
# 실측 카테고리 코드(1~12 전수 스캔): 1=모텔 2=호텔·리조트 3=펜션 5=캠핑·글램핑 6=게스트하우스.
# ★4·7 이상은 서버가 무시하고 "전체"를 반환 — 잘못 매핑하면 타입 필터가 조용히 풀린다.
_YEOGI_CATEGORY = {
    "hotel": 2, "호텔": 2, "리조트": 2,
    "motel": 1, "모텔": 1,
    "pension": 3, "펜션": 3,
    "camping": 5, "캠핑": 5, "글램핑": 5, "풀빌라": 5,
    "guesthouse": 6, "게스트하우스": 6, "게하": 6,
}


def _search_goodchoice(tool_input: dict) -> dict:
    if _creq is None:
        return {"success": False, "error": "curl_cffi 미설치 — 여기어때 소스는 curl_cffi가 필요합니다."}
    region = (tool_input.get("region") or tool_input.get("query") or "").strip()
    if not region:
        return {"success": False, "error": "region(지역/키워드)이 필요합니다. 예: {region: \"제주\"}"}
    stay_type = (tool_input.get("type") or "hotel").strip().lower()
    category = _YEOGI_CATEGORY.get(stay_type)
    if category is None:
        return {"success": False,
                "error": f"type '{stay_type}' 미지원 — hotel/motel/pension/camping/guesthouse 중 선택."}
    limit = _to_int(tool_input.get("limit"), 20)
    max_price = _to_int(tool_input.get("max_price"))

    params = {"searchType": "KEYWORD", "keyword": region, "category": category,
              "personal": _to_int(tool_input.get("personal"), 2)}
    if tool_input.get("checkin"):
        params["checkIn"] = tool_input["checkin"]
    if tool_input.get("checkout"):
        params["checkOut"] = tool_input["checkout"]

    items_out = []
    total = None
    page = 1
    while len(items_out) < limit and page <= 5:  # 최대 5페이지(100건) 안전상한
        params["page"] = page
        r = _creq.get(_YEOGI_URL, params=params, impersonate="chrome", timeout=20)
        if r.status_code != 200:
            return {"success": False, "error": f"여기어때 응답 {r.status_code}"}
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
        if not m:
            return {"success": False, "error": "여기어때 페이지 구조 변경 — __NEXT_DATA__ 없음 (가이드 stay.md 참조)"}
        d = json.loads(m.group(1))
        pp = d.get("props", {}).get("pageProps", {})
        page_info = pp.get("paginationInfo") or {}
        total = page_info.get("totalCount", total)
        rows = (pp.get("domesticList") or {}).get("body", {}).get("items", [])
        if not rows:
            break
        for it in rows:
            meta = it.get("meta") or {}
            stay = (it.get("room") or {}).get("stay") or {}
            price = stay.get("price") or {}
            pay = price.get("discountTotalPrice") or price.get("discountPrice")
            sold_out = pay is None  # 가격 없음 = 매진(soldOut "다른 날짜 확인") — 실측
            if max_price is not None and (sold_out or _to_int(pay) > max_price):
                continue  # 가격 조건이 있으면 매진(가격불명)도 제외
            review = meta.get("review") or {}
            addr = meta.get("address") or {}
            loc = meta.get("location") or {}
            strike = price.get("strikePrice")
            rate_txt = f"평점 {review['rate']}({review.get('count', 0)})" if review.get("rate") else ""
            price_txt = "매진 (다른 날짜 확인)" if sold_out else _fmt_won(pay)
            if not sold_out and strike and _to_int(strike) and _to_int(strike) > _to_int(pay):
                price_txt += f" (정가 {_fmt_won(strike)}, {price.get('discountRate') or ''}할인)".replace(", 할인", ")")
            images = meta.get("newImages") or meta.get("images") or []
            items_out.append({
                "title": meta.get("name"),
                "meta": " · ".join(x for x in [meta.get("grade"), addr.get("address"), rate_txt] if x),
                "summary": " · ".join(x for x in [price_txt, addr.get("traffic")] if x),
                "url": f"https://www.yeogi.com/domestic-accommodations/{meta.get('id')}",
                "image": images[0] if images else None,
                "lat": loc.get("latitude"),
                "lng": loc.get("longitude"),
                "price": _to_int(pay),
                "rating": review.get("rate"),
            })
            if len(items_out) >= limit:
                break
        if page >= page_info.get("totalPageCount", 1):
            break
        page += 1

    date_txt = f" {params.get('checkIn', '')}~{params.get('checkOut', '')}" if params.get("checkIn") else ""
    out = {
        "success": True, "source": "goodchoice", "count": len(items_out), "total": total,
        "message": f"여기어때 '{region}' {stay_type}{date_txt} — {len(items_out)}건 (전체 {total}건, 상세는 items)",
        "items": items_out,
    }
    _m = _build_map(items_out)
    if _m:
        out["map_data"] = _m
    return out


# ── source=33m2 (삼삼엠투 한 달 살기) ─────────────────────────

_33M2_API = "https://api.33m2.co.kr/v1/rooms"
_33M2_CDN = "https://d1pviohoskiraj.cloudfront.net/"


def _search_33m2(tool_input: dict) -> dict:
    if _creq is None:
        return {"success": False, "error": "curl_cffi 미설치 — 삼삼엠투 소스는 curl_cffi가 필요합니다."}
    region = (tool_input.get("region") or tool_input.get("query") or "").strip()
    if not region:
        return {"success": False, "error": "region(지역/키워드)이 필요합니다. 예: {region: \"평택\"}"}
    limit = _to_int(tool_input.get("limit"), 20)

    params = {"keyword": region, "size": min(limit, 50), "page": 1, "sortBy": "POPULAR"}
    if tool_input.get("max_week_fee") is not None:
        params["maxUsingFee"] = _to_int(tool_input["max_week_fee"])
    if tool_input.get("min_week_fee") is not None:
        params["minUsingFee"] = _to_int(tool_input["min_week_fee"])
    if tool_input.get("checkin"):
        params["startDate"] = tool_input["checkin"]
    if tool_input.get("checkout"):
        params["endDate"] = tool_input["checkout"]

    headers = {"Referer": "https://33m2.co.kr/", "Origin": "https://33m2.co.kr"}
    r = _creq.get(_33M2_API, params=params, impersonate="chrome", timeout=20, headers=headers)
    if r.status_code != 200:
        return {"success": False, "error": f"삼삼엠투 응답 {r.status_code}: {r.text[:200]}"}
    rooms = (r.json().get("data") or {}).get("rooms", {})
    content = rooms.get("content", [])

    items_out = []
    for rm in content[:limit]:
        fee = rm.get("usingFee")
        mgmt = rm.get("mgmtFee")
        fee_txt = f"주 {_fmt_won(fee)}" + (f" +관리비 {_fmt_won(mgmt)}" if mgmt else "")
        disc = rm.get("longtermDiscountPer")
        if disc:
            fee_txt += f" · 장기 {disc}%↓"
        items_out.append({
            "title": rm.get("roomName"),
            "meta": " · ".join(x for x in [rm.get("propertyType"),
                                           f"{rm.get('province', '')} {rm.get('town', '')}".strip(),
                                           f"{rm.get('pyeongSize')}평" if rm.get("pyeongSize") else "",
                                           "슈퍼호스트" if rm.get("isSuperHost") else ""] if x),
            "summary": fee_txt,
            "url": f"https://33m2.co.kr/room/detail/{rm.get('rid')}",
            "image": (_33M2_CDN + rm["picMain"]) if rm.get("picMain") else None,
            "lat": rm.get("lat"),
            "lng": rm.get("lng"),
            "week_fee": _to_int(fee),
        })

    # 전체 건수 (별도 count 엔드포인트)
    total = None
    try:
        rc = _creq.get(_33M2_API + "/count", params={"keyword": region}, impersonate="chrome",
                       timeout=10, headers=headers)
        total = (rc.json().get("data") or {}).get("roomCount")
    except Exception:
        pass

    out = {
        "success": True, "source": "33m2", "count": len(items_out), "total": total,
        "message": f"삼삼엠투 '{region}' 한 달 살기 — {len(items_out)}건 (전체 {total}건, 주간요금 기준, 상세는 items)",
        "items": items_out,
    }
    _m = _build_map(items_out)
    if _m:
        out["map_data"] = _m
    return out


# ── source=tourapi (한국관광공사 공식 숙박 디렉토리) ──────────

_TOURAPI_SEARCH = "https://apis.data.go.kr/B551011/KorService2/searchKeyword2"
_TOURAPI_AREA = "https://apis.data.go.kr/B551011/KorService2/areaBasedList2"
# 광역 지역명 → TourAPI areaCode (키워드 검색보다 목록이 알찬 광역 단위)
_TOURAPI_AREACODE = {
    "서울": 1, "인천": 2, "대전": 3, "대구": 4, "광주": 5, "부산": 6, "울산": 7, "세종": 8,
    "경기": 31, "강원": 32, "충북": 33, "충남": 34, "경북": 35, "경남": 36,
    "전북": 37, "전남": 38, "제주": 39,
}


def _search_tourapi(tool_input: dict) -> dict:
    key = os.environ.get("DATA_GO_KR_API_KEY", "")
    if not key:
        return {"success": False, "error": "DATA_GO_KR_API_KEY 미설정 (.env)"}
    region = (tool_input.get("region") or tool_input.get("query") or "").strip()
    if not region:
        return {"success": False, "error": "region(지역/키워드)이 필요합니다. 예: {region: \"경주 한옥\"}"}
    limit = _to_int(tool_input.get("limit"), 20)

    base = {"serviceKey": key, "MobileOS": "ETC", "MobileApp": "indiebiz", "_type": "json",
            "contentTypeId": 32, "numOfRows": min(limit, 100), "pageNo": 1, "arrange": "C"}
    area_code = _TOURAPI_AREACODE.get(region)
    if area_code:
        url, params = _TOURAPI_AREA, {**base, "areaCode": area_code}
    else:
        url, params = _TOURAPI_SEARCH, {**base, "keyword": region}

    r = _plain_requests.get(url, params=params, timeout=20)
    if r.status_code != 200:
        return {"success": False, "error": f"TourAPI 응답 {r.status_code} — 공공데이터포털 활용신청/트래픽 확인"}
    try:
        body = r.json().get("response", {}).get("body", {})
    except ValueError:
        return {"success": False, "error": f"TourAPI 비정상 응답: {r.text[:200]}"}
    total = body.get("totalCount", 0)
    rows = (body.get("items") or {}).get("item", []) if body.get("items") else []

    items_out = []
    for it in rows[:limit]:
        title = it.get("title") or ""
        # ★visitkorea 상세 URL(ms_detail.do?cotid=)의 cotid는 별도 GUID라 TourAPI contentid로 못 만듦(실측)
        #  → 업소명 검색 링크로 안내 (제목 노출 검증됨)
        url = f"https://korean.visitkorea.or.kr/search/search_list.do?keyword={_q(title)}" if title else None
        items_out.append({
            "title": title,
            "meta": " · ".join(x for x in [it.get("addr1"), it.get("tel")] if x),
            "summary": "관광공사 등록 숙박업소 (가격은 예약처 확인)",
            "url": url,
            "image": it.get("firstimage") or None,
            "lat": float(it["mapy"]) if it.get("mapy") else None,
            "lng": float(it["mapx"]) if it.get("mapx") else None,
        })

    out = {
        "success": True, "source": "tourapi", "count": len(items_out), "total": total,
        "message": f"관광공사 숙박 디렉토리 '{region}' — {len(items_out)}건 (전체 {total}건, 가격 없음·공식 목록, 상세는 items)",
        "items": items_out,
    }
    _m = _build_map(items_out)
    if _m:
        out["map_data"] = _m
    return out


# ── 진입점 ────────────────────────────────────────────────────

_SOURCE_DISPATCH = {
    "goodchoice": _search_goodchoice, "여기어때": _search_goodchoice, "yeogi": _search_goodchoice,
    "33m2": _search_33m2, "삼삼엠투": _search_33m2, "samsam": _search_33m2,
    "tourapi": _search_tourapi, "관광공사": _search_tourapi, "tour": _search_tourapi,
}


def search_stay(tool_input: dict) -> dict:
    source = str(tool_input.get("source") or "goodchoice").strip().lower()
    fn = _SOURCE_DISPATCH.get(source)
    if fn is None:
        return {"success": False,
                "error": f"source '{source}' 미지원 — goodchoice(호텔·모텔·펜션 실시간가) / 33m2(한 달 살기) / tourapi(공식 디렉토리)"}
    try:
        return fn(tool_input)
    except Exception as e:
        return {"success": False, "error": f"숙박 검색 실패({source}): {type(e).__name__}: {e}"}
