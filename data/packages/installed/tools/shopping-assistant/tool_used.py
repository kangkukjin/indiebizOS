"""
tool_used.py — 중고 C2C 매물 검색 어댑터 ([sense:used] 결정화)

빈도 높은 중고물건 검색을 어휘로 승격. 명명 헌법대로 소스마다 액션이 아니라
[sense:used]{source} 한 액션 + source 파라미터(직방 sense:realty{source} 선례).

통화 = records[{title, meta, summary, url, image}] (realty/nanet과 동일 봉투).

소스별 접근(2026-07-12 실측 확정):
- bunjang : 내부 API api.bunjang.co.kr/api/1/find_v2.json → 깨끗한 JSON(위치 포함). ★
            (옛 Playwright SPA 셀렉터는 빈 껍데기라 실패 → API로 대체가 결정화의 핵심.)
- joongna : web.joongna.com/search RSC 스트림(self.__next_f)에 seq/title/price/url. best-effort.
- danggeun: 2단 — ①지역 해소 /kr/api/v1/regions/keyword ②검색 /kr/buy-sell/?in=x-{id}&search=
            → JSON-LD ItemList에 전체 결과 통째(키·쿠키 불요). 지역 스코프(해당 동+인근 동). ★
- naver   : 핸들러에서 api_call cafearticle(중고나라 카페) — 이 파일 밖(키 필요).
"""

import re
import json

try:
    import requests
    _HTTP = "requests"
except ImportError:
    requests = None
    import httpx
    _HTTP = "httpx"

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def _get(url, params=None, timeout=12):
    """소스 독립 GET — requests 우선, 없으면 httpx. (text, status) 반환."""
    headers = {"User-Agent": _UA, "Accept-Language": "ko-KR,ko;q=0.9"}
    if _HTTP == "requests":
        r = requests.get(url, params=params, headers=headers, timeout=timeout)
        # 당근 등 HTML 응답에 charset 헤더가 없으면 requests가 ISO-8859-1로
        # 잘못 디코딩(한글 모지바케) — 한국 서비스는 전부 UTF-8이라 강제 보정.
        if not r.encoding or r.encoding.lower() in ("iso-8859-1", "latin-1"):
            r.encoding = "utf-8"
        return r.text, r.status_code
    else:
        r = httpx.get(url, params=params, headers=headers, timeout=timeout,
                      follow_redirects=True)
        if not r.charset_encoding:
            r.encoding = "utf-8"
        return r.text, r.status_code


def _man(won):
    """원 단위 정수 → '230만원' 표기(만원 미만은 원)."""
    try:
        w = int(won)
    except (ValueError, TypeError):
        return str(won)
    if w >= 10000:
        man = w / 10000
        return (f"{man:.0f}만원" if man == int(man) else f"{man:.1f}만원")
    return f"{w:,}원"


# ============ bunjang — 내부 API (★깨끗) ============

def search_bunjang(query, limit=20, region=None):
    """번개장터 내부 API. region 주면 location substring 후필터(반경 아님)."""
    url = "https://api.bunjang.co.kr/api/1/find_v2.json"
    params = {"q": query, "order": "date", "n": max(limit * 2, 40),
              "page": 0, "req_ref": "search", "stat_uid": ""}
    try:
        text, code = _get(url, params=params)
        if code != 200:
            return {"error": f"번개장터 API HTTP {code}", "records": []}
        data = json.loads(text)
    except Exception as e:
        return {"error": f"번개장터 조회 실패: {e}", "records": []}

    records = []
    for it in data.get("list", []):
        loc = (it.get("location") or "").strip()
        if region and region not in loc:
            continue
        pid = it.get("pid")
        status = "판매완료" if it.get("status") in ("2", 2, "sold") else "판매중"
        meta_bits = [_man(it.get("price"))]
        if loc:
            meta_bits.append(loc)
        if status == "판매완료":
            meta_bits.append("거래완료")
        records.append({
            "title": (it.get("name") or "").strip(),
            "meta": " · ".join(meta_bits),
            "summary": "",
            "url": f"https://m.bunjang.co.kr/products/{pid}" if pid else "",
            "image": it.get("product_image") or "",
        })
        if len(records) >= limit:
            break
    return {"source": "bunjang", "total": len(records), "records": records}


# ============ joongna — RSC 스트림 파싱 (best-effort) ============

def search_joongna(query, limit=20):
    """중고나라 web 검색. Next.js RSC 스트림에서 상품 필드 추출(best-effort)."""
    url = f"https://web.joongna.com/search/{query}"
    try:
        text, code = _get(url)
        if code != 200:
            return {"error": f"중고나라 HTTP {code}", "records": []}
    except Exception as e:
        return {"error": f"중고나라 조회 실패: {e}", "records": []}

    # RSC 스트림은 키가 이스케이프돼 있다(\\"seq\\"). 언이스케이프 후 근접 파싱.
    text = text.replace('\\"', '"')
    # 상품 객체 조각을 seq 기준으로 근접 필드와 함께 추출(best-effort).
    records = []
    seen = set()
    # seq 와 그 주변(±600자) 창에서 title/price 를 찾는다.
    for m in re.finditer(r'"seq"\s*:\s*(\d{6,})', text):
        seq = m.group(1)
        if seq in seen:
            continue
        seen.add(seq)
        win = text[m.start(): m.start() + 700]
        tm = re.search(r'"title"\s*:\s*"((?:[^"\\]|\\.)*)"', win)
        pm = re.search(r'"price"\s*:\s*"?(\d+)"?', win)
        title = tm.group(1) if tm else ""
        try:
            title = json.loads('"' + title + '"')  # 이스케이프 해제
        except Exception:
            pass
        records.append({
            "title": title.strip(),
            "meta": _man(pm.group(1)) if pm else "",
            "summary": "",
            "url": f"https://web.joongna.com/product/{seq}",
            "image": "",
        })
        if len(records) >= limit:
            break
    return {"source": "joongna", "total": len(records), "records": records,
            "note": "RSC 파싱(best-effort) — 제목/가격 일부 누락 가능"}


# ============ danggeun — JSON-LD ItemList (★깨끗) ============
#
# 옛 "클라이언트 렌더라 안 됨" 진단은 URL이 틀렸던 것(2026-07-12 재실측으로 뒤집힘).
# /kr/buy-sell/?in=x-{지역ID}&search={쿼리} 는 SSR이고, JSON-LD ItemList에 전체
# 결과가 통째로 담긴다(282건도 한 응답, 페이지네이션 불요). 결과 = 해당 동 + 인근 동.
# ★함정: in= 슬러그의 한글 이름은 장식이고 숫자 ID만 유효 — 이름이 틀려도 에러 없이
#   ID의 지역이 조용히 나온다(1372=의정부 녹양동). 반드시 regions/keyword로 해소할 것.

def _resolve_danggeun_region(region):
    """지역 이름 → 당근 지역 ID. (id, 전체이름) 또는 (None, 에러문자열)."""
    url = "https://www.daangn.com/kr/api/v1/regions/keyword"
    try:
        text, code = _get(url, params={"keyword": region})
        if code != 200:
            return None, f"당근 지역 검색 HTTP {code}"
        locs = json.loads(text).get("locations", [])
    except Exception as e:
        return None, f"당근 지역 검색 실패: {e}"
    if not locs:
        return None, f"당근에서 지역 '{region}'을 찾지 못함 — 동/읍/면 이름으로 시도(예 \"죽백동\")"
    loc = locs[0]
    full = " ".join(p for p in (loc.get("name1"), loc.get("name2"), loc.get("name3")) if p)
    return loc.get("id"), full


def search_danggeun(query, limit=20, region=None):
    """당근 web 검색. region(동 이름) 주면 그 동네+인근 동으로 스코프(당근의 '내동네')."""
    region_id, region_full = None, None
    if region:
        region_id, resolved = _resolve_danggeun_region(region)
        if region_id is None:
            return {"error": resolved, "records": []}
        region_full = resolved

    url = "https://www.daangn.com/kr/buy-sell/"
    params = {"search": query}
    if region_id:
        params["in"] = f"x-{region_id}"  # 이름 부분은 장식 — ID만 유효
    try:
        text, code = _get(url, params=params, timeout=20)
        if code != 200:
            return {"error": f"당근 검색 HTTP {code}", "records": []}
    except Exception as e:
        return {"error": f"당근 검색 실패: {e}", "records": []}

    # JSON-LD ItemList 추출 (스크립트가 여럿일 수 있어 ItemList인 것만)
    products = []
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', text, re.S):
        try:
            data = json.loads(m.group(1))
        except Exception:
            continue
        if isinstance(data, dict) and data.get("@type") == "ItemList":
            products = [e.get("item", {}) for e in data.get("itemListElement", [])]
            break
    if not products:
        return {"source": "danggeun", "total": 0, "records": [],
                "note": "결과 없음 또는 페이지 구조 변경(JSON-LD ItemList 미발견)"}

    records = []
    for it in products:
        offers = it.get("offers") or {}
        sold = "SoldOut" in (offers.get("availability") or "")
        meta_bits = []
        price = offers.get("price")
        if price not in (None, ""):
            try:
                meta_bits.append(_man(int(float(price))))
            except (ValueError, TypeError):
                meta_bits.append(str(price))
        if region_full:
            meta_bits.append(region_full + " 인근")
        if sold:
            meta_bits.append("거래완료")
        records.append({
            "title": (it.get("name") or "").strip(),
            "meta": " · ".join(meta_bits),
            "summary": (it.get("description") or "").strip()[:200],
            "url": it.get("url") or "",
            "image": it.get("image") or "",
        })
        if len(records) >= limit:
            break
    res = {"source": "danggeun", "total": len(records), "records": records}
    if region_full:
        res["region"] = region_full
        res["note"] = "해당 동 + 인근 동 매물(당근 '내동네' 스코프). 매물별 정확한 동은 링크에서 확인."
    else:
        res["note"] = "region 미지정 — 지역 스코프 없는 기본 결과. 동네 매물은 region=\"동이름\" 권장."
    return res
