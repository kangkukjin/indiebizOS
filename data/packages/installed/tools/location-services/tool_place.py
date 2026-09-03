"""
tool_place.py — [sense:place] 장소 검색·상세 (카카오 로컬 API, 전 업종)

handler.py 가 importlib 로 로드해 op 를 넘긴다(tool_stay.py 와 같은 관례).
  - search(기본): 키워드(query) 또는 카테고리(category) 로 장소를 찾는다. 좌표(lat/lng)를 주면
    그 주변(radius m) — 카테고리만 주면 카카오 category.json(좌표 필수), 키워드가 있으면 keyword.json.
  - detail: 한 곳의 상세 — 카카오 기본정보(이름·분류·주소·전화·place_url·좌표)에 네이버 지역검색
    설명·링크와 블로그 언급(blog_count·reason)을 덧붙인 1행 스냅샷(items 1행).

좌표 계약: 출력 항목은 항상 {lat,lng} float — 좌표 없는 항목은 드롭한다(cctv/restaurant 와 동일).
카테고리 코드는 카카오 API 명세(세계의 명사) — 한글 라벨·코드 어느 쪽으로 받아도 코드로 푼다.
"""
import os
import sys

_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.api_client import api_call          # noqa: E402
from common.auth_manager import check_api_key   # noqa: E402

# 카카오 로컬 카테고리 그룹 코드 (https://developers.kakao.com/docs/latest/ko/local/dev-guide#search-by-category)
CATEGORY_CODES = {
    "마트": "MT1", "대형마트": "MT1",
    "편의점": "CS2",
    "어린이집": "PS3", "유치원": "PS3",
    "학교": "SC4",
    "학원": "AC5",
    "주차장": "PK6",
    "주유소": "OL7", "충전소": "OL7",
    "지하철": "SW8", "지하철역": "SW8",
    "은행": "BK9",
    "문화시설": "CT1",
    "부동산": "AG2", "중개업소": "AG2",
    "공공기관": "PO3",
    "관광명소": "AT4", "관광지": "AT4",
    "숙박": "AD5",
    "음식점": "FD6", "식당": "FD6", "맛집": "FD6",
    "카페": "CE7",
    "병원": "HP8",
    "약국": "PM9",
}
_VALID_CODES = set(CATEGORY_CODES.values())
_PAGE = 15          # 카카오 페이지 크기 고정(페이지마다 size 가 바뀌면 오프셋이 어긋남)
_MAX = 45           # 3페이지 상한
_MAX_RADIUS = 20000


def _code(category):
    if not category:
        return None
    c = str(category).strip()
    if c.upper() in _VALID_CODES:
        return c.upper()
    return CATEGORY_CODES.get(c)


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v, default):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _simple_category(category_name: str) -> str:
    """'음식점 > 양식 > 이탈리안' → '양식' (둘째 단), 한 단이면 그대로."""
    parts = [p.strip() for p in (category_name or "").split(">") if p.strip()]
    if len(parts) >= 2:
        return parts[1]
    return parts[0] if parts else ""


def _doc_to_item(doc: dict) -> dict:
    lat, lng = _f(doc.get("y")), _f(doc.get("x"))
    name = doc.get("place_name", "")
    return {
        "id": str(doc.get("id", "")),
        "name": name,
        "title": name,                                   # 표준 제목 칸 병기(F1 규약)
        "category": doc.get("category_name", ""),
        "cat": _simple_category(doc.get("category_name", "")),
        "group": doc.get("category_group_name", ""),     # 카카오 대분류(음식점/카페/…)
        "group_code": doc.get("category_group_code", ""),
        "address": doc.get("road_address_name") or doc.get("address_name", ""),
        "jibun_address": doc.get("address_name", ""),
        "phone": doc.get("phone", ""),
        "url": doc.get("place_url", ""),
        "distance": _i(doc.get("distance"), None) if doc.get("distance") else None,   # m (좌표 준 검색만)
        "lat": lat,
        "lng": lng,
    }


def _paged(endpoint: str, params: dict, limit: int):
    """카카오 로컬 페이지네이션(15×최대 3) — (items, total, error)."""
    items, total, page = [], 0, 1
    while len(items) < limit and page <= 3:
        data = api_call("kakao", endpoint, params={**params, "size": _PAGE, "page": page}, timeout=10)
        if isinstance(data, dict) and "error" in data:
            return items, total, data if page == 1 else None
        total = (data.get("meta") or {}).get("total_count", total)
        for doc in data.get("documents", []):
            it = _doc_to_item(doc)
            if it["lat"] is None or it["lng"] is None:
                continue
            items.append(it)
        if (data.get("meta") or {}).get("is_end", True):
            break
        page += 1
    return items[:limit], total, None


def place_search(tool_input: dict) -> dict:
    key_ok, key_error = check_api_key("kakao")
    if not key_ok:
        return {"success": False, "error": f"{key_error} https://developers.kakao.com 에서 발급받으세요."}

    query = (tool_input.get("query") or "").strip()
    code = _code(tool_input.get("category"))
    if tool_input.get("category") and not code:
        return {"success": False,
                "error": f"알 수 없는 카테고리 '{tool_input.get('category')}'. 가능: {', '.join(sorted(set(CATEGORY_CODES)))} 또는 카카오 코드(FD6·CE7…)"}
    if not query and not code:
        return {"success": False, "error": "query(검색어) 또는 category(카테고리) 중 하나는 필요합니다."}

    lat, lng = _f(tool_input.get("lat")), _f(tool_input.get("lng"))
    has_coord = lat is not None and lng is not None
    limit = max(1, min(_i(tool_input.get("limit"), 15), _MAX))
    sort = "distance" if str(tool_input.get("sort") or "").lower() == "distance" else "accuracy"
    radius = tool_input.get("radius")

    params = {"sort": sort}
    if has_coord:
        params.update({"x": f"{lng:.7f}", "y": f"{lat:.7f}"})
        if radius is not None:
            params["radius"] = max(0, min(_i(radius, 5000), _MAX_RADIUS))
    elif sort == "distance":
        return {"success": False, "error": "sort:distance 는 기준 좌표(lat·lng)가 필요합니다."}

    label = query or next((k for k, v in CATEGORY_CODES.items() if v == code), code)
    if query or not has_coord:
        # 키워드 검색 — 카테고리만 왔는데 좌표가 없으면 라벨('카페')을 검색어로 삼아 전국 정확도순(앱의 칩만 고른 첫 조회)
        params["query"] = query or label
        if code:
            params["category_group_code"] = code
        endpoint = "/v2/local/search/keyword.json"
    else:
        params["category_group_code"] = code
        params.setdefault("radius", 5000)
        endpoint = "/v2/local/search/category.json"

    items, total, err = _paged(endpoint, params, limit)
    if err:
        return err
    return {
        "items": items,
        "count": len(items),
        "total": total,
        "query": query,
        "category": code,
        "message": f"'{label}' 장소 {len(items)}곳 (전체 {total})" + (f" · 반경 {params['radius']}m" if "radius" in params else ""),
    }


def place_detail(tool_input: dict, *, naver_local=None, blog_evidence=None, norm_name=None) -> dict:
    """한 곳 상세 — name(필수, 검색 결과의 name) + 선택 id/lat/lng(동명 가게 판별)."""
    key_ok, key_error = check_api_key("kakao")
    if not key_ok:
        return {"success": False, "error": f"{key_error} https://developers.kakao.com 에서 발급받으세요."}
    name = (tool_input.get("name") or tool_input.get("query") or "").strip()
    if not name:
        return {"success": False, "error": "name(장소 이름)이 필요합니다 — [sense:place] 검색 결과의 name·lat·lng 을 그대로 넘기세요."}
    want_id = str(tool_input.get("id") or "").strip()
    lat, lng = _f(tool_input.get("lat")), _f(tool_input.get("lng"))

    params = {"query": name, "size": _PAGE}
    if lat is not None and lng is not None:
        params.update({"x": f"{lng:.7f}", "y": f"{lat:.7f}", "sort": "distance"})
    data = api_call("kakao", "/v2/local/search/keyword.json", params=params, timeout=10)
    if isinstance(data, dict) and "error" in data:
        return data
    docs = data.get("documents", []) if isinstance(data, dict) else []
    if not docs:
        return {"success": False, "error": f"'{name}' 에 해당하는 장소를 카카오에서 찾지 못했습니다.", "items": [], "count": 0}
    doc = next((d for d in docs if want_id and str(d.get("id")) == want_id), docs[0])
    item = _doc_to_item(doc)

    # 네이버 지역검색 — 같은 이름의 항목에서 설명·링크만 취한다(동음이의는 이름 정규화 일치로 거른다)
    sources = ["kakao"]
    if naver_local and check_api_key("naver")[0]:
        try:
            nv = naver_local(name, 5, "random")
            key = norm_name(item["name"]) if norm_name else item["name"]
            for r in (nv.get("restaurants") or []) if isinstance(nv, dict) else []:
                if (norm_name(r.get("name", "")) if norm_name else r.get("name")) == key:
                    if r.get("description"):
                        item["description"] = r["description"]
                    if r.get("url"):
                        item["naver_url"] = r["url"]
                    if not item.get("phone") and r.get("phone"):
                        item["phone"] = r["phone"]
                    sources.append("naver")
                    break
        except Exception:
            pass

    # 블로그 언급 — 인기 신호(blog_count)와 후기 제목(reason). 지역어는 주소의 구/군 단.
    if blog_evidence and check_api_key("naver")[0]:
        try:
            parts = (item.get("address") or "").split()
            region = parts[1] if len(parts) > 1 else (parts[0] if parts else "")
            ev = blog_evidence(region, item["name"])
            if ev:
                item["blog_count"] = ev.get("blog_count", 0)
                if ev.get("blog_titles"):
                    item["reason"] = " / ".join(ev["blog_titles"])[:120]
                if "naver_blog" not in sources:
                    sources.append("naver_blog")
        except Exception:
            pass

    item["sources"] = sources
    item["candidates"] = len(docs)
    return {"items": [item], "count": 1, "message": f"{item['name']} — {item.get('category') or item.get('group') or '장소'}"}
