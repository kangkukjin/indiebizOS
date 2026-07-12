"""네이버부동산 현재 매물(호가) 조회 — [sense:realty]{source: "naver"}.

직방(zigbang)이 빌라/원룸/오피스텔 개별 호실에 강한 것과 반대로, 네이버부동산은
*아파트 단지* 매물이 최다(중개사 등록 매물의 사실상 전국 표준 풀). 단독/다가구·상가주택도 잡힌다.

비공식 내부 API(new.land.naver.com/api). 공식 오픈API에는 부동산 카테고리가 없음(SE05, 종료됨)
— NAVER_CLIENT_ID 키와 무관하게 무키로 동작한다. 단 두 가지 요구:
  1) TLS 지문: 일반 curl/requests는 봇 탐지로 차단(무응답/404행) → curl_cffi impersonate="chrome" 필수.
  2) 익명 JWT: 아무 페이지 HTML에 심긴 Bearer 토큰을 Authorization 헤더로 전달(만료 시 재발급).
흐름: 지명→/api/search(keyword)로 cortarNo(동) 또는 complexNo(단지) 해소 →
      /api/articles(동) | /api/articles/complex/{no}(단지) → items 통화.
"""
import base64
import json
import re
import time
import urllib.parse

_BASE = "https://new.land.naver.com"
_BOOTSTRAP = _BASE + "/houses?ms=37.5,127.0,15"

# sense:realty 의 type → 네이버 realEstateType 코드. 직방과 달리 아파트가 주력.
_TYPE_TO_CODE = {
    "apt": "APT:ABYG:JGC", "아파트": "APT:ABYG:JGC", "apartment": "APT:ABYG:JGC",
    "officetel": "OPST", "오피스텔": "OPST", "op": "OPST",
    "villa": "VL", "빌라": "VL", "다세대": "VL", "연립": "VL",
    "house": "DDDGG", "단독": "DDDGG", "다가구": "DDDGG", "단독다가구": "DDDGG",
    "oneroom": "OR", "원룸": "OR", "one_room": "OR",
}
_TYPE_DEFAULT = "apt"

# 세션 + 익명 JWT 캐시 (프로세스 수명, 만료 60초 전 재발급)
_session = None
_token = None
_token_exp = 0


def _get_session():
    global _session
    if _session is None:
        from curl_cffi import requests as cr  # 지연 임포트 — 미설치 시 조회 시점에 안내
        _session = cr.Session(impersonate="chrome")
    return _session


def _jwt_exp(tok):
    try:
        payload = tok.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return int(json.loads(base64.urlsafe_b64decode(payload)).get("exp", 0))
    except Exception:
        return 0


def _get_token(force=False):
    """페이지 HTML에 심긴 익명 Bearer JWT. 만료 임박/강제 시 재발급."""
    global _token, _token_exp
    if not force and _token and time.time() < _token_exp - 60:
        return _token
    s = _get_session()
    r = s.get(_BOOTSTRAP, timeout=15)
    m = re.search(r"eyJ[A-Za-z0-9._-]{60,}", r.text)
    if not m:
        raise RuntimeError("네이버부동산 페이지에서 토큰을 찾지 못했습니다(차단 가능성).")
    _token = m.group(0)
    _token_exp = _jwt_exp(_token) or (time.time() + 1800)
    return _token


def _api_get(path, params=None, _retried=False):
    s = _get_session()
    url = _BASE + path
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    r = s.get(url, timeout=15, headers={
        "Accept": "application/json",
        "Referer": _BASE + "/",
        "Authorization": f"Bearer {_get_token()}",
    })
    if r.status_code in (401, 403, 429) and not _retried:
        _get_token(force=True)
        return _api_get(path, params, _retried=True)
    if r.status_code != 200:
        raise RuntimeError(f"네이버부동산 API {r.status_code}: {path}")
    return r.json()


def _resolve_keyword(keyword):
    """지명/단지명 → {'mode': 'region'|'complex', ...}. 동(regions) 우선, 없으면 단지(complexes)."""
    d = _api_get("/api/search", {"keyword": keyword})
    regions = d.get("regions") or []
    if regions:
        r0 = regions[0]
        return {"mode": "region", "cortarNo": r0["cortarNo"],
                "matched": r0.get("cortarName") or keyword,
                "lat": r0.get("centerLat"), "lng": r0.get("centerLon")}
    complexes = d.get("complexes") or []
    if complexes:
        c0 = complexes[0]
        return {"mode": "complex", "complexNo": c0["complexNo"],
                "matched": f"{c0.get('complexName', keyword)} (단지)",
                "cortarNo": c0.get("cortarNo"),
                "lat": c0.get("latitude"), "lng": c0.get("longitude")}
    return None


def _trade_types(deal, lease):
    """deal/lease → 네이버 tradeType. A1=매매, B1=전세, B2=월세.

    모델이 전세/월세를 deal 에 넣는 경향이 있어(예 deal="lease"/"전세"), lease 가 비면 deal 값을 흡수.
    """
    deal = (deal or "").strip()
    lease = (lease or "").strip()
    if not lease and deal in ("전세", "jeonse", "월세", "wolse", "monthly"):
        lease, deal = deal, "rent"  # deal 에 잘못 실린 임대유형을 lease 로 이관
    if lease in ("전세", "jeonse"):
        return "B1", "전세"
    if lease in ("월세", "wolse", "monthly"):
        return "B2", "월세"
    if deal == "trade":
        return "A1", "매매"
    return "B1:B2", "전세/월세"


def _prc_to_man(prc):
    """'2억 9,000' / '5,000' 식 가격 문자열 → 만원 정수. 실패 시 None."""
    if not prc:
        return None
    txt = str(prc).replace(",", "").strip()
    m = re.match(r"(?:(\d+)억)?\s*(\d+)?", txt)
    if not m or (m.group(1) is None and m.group(2) is None):
        return None
    return int(m.group(1) or 0) * 10000 + int(m.group(2) or 0)


def _article_to_item(a):
    name = a.get("articleName") or a.get("articleRealEstateTypeName") or "매물"
    bld = a.get("buildingName") or ""
    title = f"{name} {bld}".strip() if bld and bld != name else name
    prc = a.get("dealOrWarrantPrc") or ""
    if a.get("rentPrc"):  # 월세는 rentPrc 별도 필드 → '보증금/월세' 표기
        prc = f"{prc}/{a['rentPrc']}"
    meta_parts = [f"{a.get('tradeTypeName', '')} {prc}".strip()]
    if a.get("area1") or a.get("area2"):
        meta_parts.append(f"{a.get('area1', '?')}/{a.get('area2', '?')}㎡")
    if a.get("floorInfo"):
        meta_parts.append(f"{a['floorInfo']}층")
    if a.get("direction"):
        meta_parts.append(a["direction"])
    if a.get("articleConfirmYmd"):
        meta_parts.append(f"확인 {a['articleConfirmYmd']}")
    if a.get("realtorName"):
        meta_parts.append(a["realtorName"])
    same = a.get("sameAddrCnt")
    if same and int(same) > 1:
        meta_parts.append(f"동일매물 {same}건")
    summary = a.get("articleFeatureDesc") or ""
    tags = a.get("tagList") or []
    if tags:
        summary = (summary + " · " if summary else "") + " ".join(tags[:4])
    img = a.get("representativeImgUrl")
    if img and img.startswith("/"):
        img = "https://landthumb-phinf.pstatic.net" + img
    return {
        "title": title,
        "meta": " · ".join(p for p in meta_parts if p),
        "summary": summary[:120],
        "url": f"https://m.land.naver.com/article/info/{a.get('articleNo')}",
        "image": img,
        "lat": a.get("latitude"),
        "lng": a.get("longitude"),
        "_deposit_man": _prc_to_man(a.get("dealOrWarrantPrc")),
        "_rent_man": _prc_to_man(a.get("rentPrc")),
        "_trade": a.get("tradeTypeName"),
    }


def get_naver_listings(tool_input: dict):
    """[sense:realty]{source: "naver"} — 네이버부동산 현재 매물(호가) 조회.

    입력: region(동·지명 또는 아파트 단지명) · type(apt/officetel/villa/house/oneroom) ·
          deal(trade/rent) · lease(전세/월세, 좁힘) · deposit_max/deposit_min(만원) ·
          rent_max(만원, 월세 후필터) · limit(기본 30, 최대 60)
    """
    region = tool_input.get("region") or tool_input.get("region_name") or tool_input.get("q")
    if not region:
        return {"success": False,
                "error": "네이버부동산 조회에는 region(동·지명 또는 단지명, 예: '평택 비전동', '우미린센트럴파크')이 필요합니다."}
    try:
        import curl_cffi  # noqa: F401
    except ImportError:
        return {"success": False,
                "error": "curl_cffi 미설치 — 네이버부동산은 TLS 위장이 필요합니다. pip install curl_cffi 후 재시도하세요."}

    rtype = (tool_input.get("type") or _TYPE_DEFAULT).strip().lower()
    re_code = _TYPE_TO_CODE.get(rtype) or (rtype.upper() if re.fullmatch(r"[A-Z:]{2,}", rtype.upper()) else None)
    if not re_code:
        return {"success": False,
                "error": f"type '{rtype}' 미지원 — apt/officetel/villa/house/oneroom 중 하나를 쓰세요."}
    trade_code, trade_label = _trade_types(tool_input.get("deal"), tool_input.get("lease"))
    try:
        limit = max(1, min(60, int(tool_input.get("limit") or 30)))
    except (TypeError, ValueError):
        limit = 30

    try:
        loc = _resolve_keyword(str(region).strip())
    except Exception as e:
        return {"success": False, "error": f"네이버부동산 지역 해소 실패: {e}"}
    if not loc:
        return {"success": False,
                "error": f"'{region}'을(를) 네이버부동산에서 찾지 못했습니다. 동 이름(예 '평택 비전동')이나 정확한 단지명으로 시도하세요."}

    params = {"order": "rank", "realEstateType": re_code, "tradeType": trade_code,
              "priceType": "RETAIL", "sameAddressGroup": "true", "articleState": ""}
    dep_min, dep_max = tool_input.get("deposit_min"), tool_input.get("deposit_max")
    if dep_min is not None:
        params["priceMin"] = int(float(dep_min))
    if dep_max is not None:
        params["priceMax"] = int(float(dep_max))

    if loc["mode"] == "complex":
        path = f"/api/articles/complex/{loc['complexNo']}"
        params["complexNo"] = loc["complexNo"]
    else:
        path = "/api/articles"
        params["cortarNo"] = loc["cortarNo"]

    rows, page = [], 1
    try:
        while len(rows) < limit and page <= 3:
            d = _api_get(path, {**params, "page": page})
            arts = d.get("articleList") or []
            rows.extend(_article_to_item(a) for a in arts)
            if not d.get("isMoreData") or not arts:
                break
            page += 1
    except Exception as e:
        return {"success": False, "error": f"네이버부동산 매물 조회 실패: {e}"}

    # 월세 rent_max 후필터 (rentPrc는 서버필터 파라미터가 없어 클라이언트 필터)
    rent_max = tool_input.get("rent_max")
    if rent_max is not None:
        try:
            _rmax = float(rent_max)
            rows = [r for r in rows
                    if r["_trade"] != "월세" or r["_rent_man"] is None or r["_rent_man"] <= _rmax]
        except (TypeError, ValueError):
            pass
    rows = rows[:limit]

    items_out = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    if not rows:
        return {"success": True, "source": "naver", "count": 0, "items": [],
                "message": f"네이버부동산 '{loc['matched']}' {rtype} {trade_label} 매물이 없습니다.",
                "조회지역": loc["matched"]}
    message = f"네이버부동산 '{loc['matched']}' · {rtype} {trade_label} — {len(rows)}건 (동일매물 묶음, 상세는 items)"
    out = {
        "success": True,
        "source": "naver",
        "조회지역": loc["matched"],
        "count": len(rows),
        "message": message,
        "items": items_out,
    }
    if loc.get("lat") and loc.get("lng"):
        out["center"] = {"lat": loc["lat"], "lng": loc["lng"]}
        out["map_data"] = {"center": out["center"],
                           "markers": [{"lat": r["lat"], "lng": r["lng"], "name": r["title"],
                                        "meta": r["meta"], "url": r["url"]} for r in rows if r.get("lat")]}
    return out
