"""직방(Zigbang) 현재 매물(호가) 조회 — [sense:realty]{source: "zigbang"}.

국토부 실거래가(molit)가 *체결된 과거 거래*만 주는 것과 달리, 직방은 *지금 시장에 나온 매물*
(호가·사진·링크)을 준다. 빌라/원룸/오피스텔 개별 호실에 강하다(아파트 단지·단독/다가구는 약함).

비공식 내부 API(apis.zigbang.com). 키 불필요. 한국 IP에서 차단 약함.
흐름: 지명→좌표(/v2/search, Nominatim 폴백) → geohash5 → 리스트(마커+itemId) →
거리 선필터 → 상세(/v3/items/{id}) 병렬조회 → records 통화.
"""
import json
import math
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124 Safari/537.36")
_API = "https://apis.zigbang.com"

# sense:realty 의 type → 직방 카테고리(엔드포인트·웹 URL 경로). 직방은 villa/oneroom/officetel만.
_TYPE_TO_CAT = {
    "villa": "villa", "빌라": "villa", "다세대": "villa", "연립": "villa", "house": "villa",
    "oneroom": "oneroom", "원룸": "oneroom", "one_room": "oneroom",
    "officetel": "officetel", "오피스텔": "officetel", "op": "officetel",
}
_CAT_DEFAULT = "villa"


def _http_json(url, timeout=12):
    req = urllib.request.Request(url, headers={
        "User-Agent": _UA, "Accept": "application/json", "Referer": "https://www.zigbang.com/"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def _geohash(lat, lon, prec=5):
    base32 = "0123456789bcdefghjkmnpqrstuvwxyz"
    lat_i, lon_i = [-90.0, 90.0], [-180.0, 180.0]
    gh, bit, ch, even = [], 0, 0, True
    while len(gh) < prec:
        if even:
            mid = sum(lon_i) / 2
            if lon > mid:
                ch = (ch << 1) | 1; lon_i[0] = mid
            else:
                ch = ch << 1; lon_i[1] = mid
        else:
            mid = sum(lat_i) / 2
            if lat > mid:
                ch = (ch << 1) | 1; lat_i[0] = mid
            else:
                ch = ch << 1; lat_i[1] = mid
        even = not even
        if bit < 4:
            bit += 1
        else:
            gh.append(base32[ch]); bit = 0; ch = 0
    return "".join(gh)


def _haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _geocode(region):
    """지명 → {lat,lng,matched}. 직방 자체 검색 우선(동·지역명 강함), Nominatim 폴백(POI·건물명)."""
    q = str(region or "").strip()
    if not q:
        return None
    # 1) 직방 로컬 검색 (키 불필요)
    try:
        j = _http_json(f"{_API}/v2/search?q={urllib.parse.quote(q)}", timeout=10)
        items = j.get("items") or []
        # type=address(동·지역) 우선, 없으면 첫 결과
        pick = next((it for it in items if it.get("type") == "address"), items[0] if items else None)
        if pick and pick.get("lat") and pick.get("lng"):
            return {"lat": float(pick["lat"]), "lng": float(pick["lng"]),
                    "matched": pick.get("description") or pick.get("name") or q}
    except Exception:
        pass
    # 2) Nominatim 폴백 (도서관·건물 등 POI는 직방 검색에 없을 수 있음)
    try:
        url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
            {"q": q, "format": "json", "limit": 1, "countrycodes": "kr"})
        req = urllib.request.Request(url, headers={"User-Agent": "indiebizOS/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        if data:
            return {"lat": float(data[0]["lat"]), "lng": float(data[0]["lon"]),
                    "matched": data[0].get("display_name", q)}
    except Exception:
        pass
    return None


def _sales_types(deal, lease):
    """deal/lease → 직방 salesTypes 목록. deal=trade→매매, rent→전세+월세. lease가 있으면 그걸로 좁힘."""
    lease = (lease or "").strip()
    if lease in ("전세", "jeonse"):
        return ["전세"]
    if lease in ("월세", "wolse", "monthly"):
        return ["월세"]
    if (deal or "rent").strip() == "trade":
        return ["매매"]
    return ["전세", "월세"]


def _won_str(man):
    """만원 정수 → '1억 2,000만' 식 한국어. 0/None은 빈 문자열."""
    try:
        man = int(round(float(man)))
    except (TypeError, ValueError):
        return ""
    if man <= 0:
        return ""
    eok, rem = man // 10000, man % 10000
    if eok and rem:
        return f"{eok}억 {rem:,}만"
    if eok:
        return f"{eok}억"
    return f"{rem:,}만"


def _price_str(sales_type, price):
    p = price or {}
    dep = p.get("deposit")
    rent = p.get("rent")
    sales = p.get("sales") or p.get("salesPrice")
    if sales_type == "매매":
        return f"매매 {_won_str(sales if sales else dep)}".strip()
    if sales_type == "월세":
        r = ""
        try:
            r = f"{int(round(float(rent)))}" if rent else "0"
        except (TypeError, ValueError):
            r = "0"
        return f"월세 {_won_str(dep)}/{r}".strip()
    # 전세 (기본)
    return f"전세 {_won_str(dep)}".strip()


def _fetch_detail(item_id):
    try:
        j = _http_json(f"{_API}/v3/items/{item_id}", timeout=12)
        return j.get("item") if isinstance(j, dict) else None
    except Exception:
        return None


def _detail_to_row(item, cat, center, dist_m):
    if not isinstance(item, dict):
        return None
    iid = item.get("itemId")
    sales_type = item.get("salesType") or ""
    area = item.get("area") or {}
    m2 = area.get("전용면적M2") or area.get("계약면적M2") or area.get("공급면적M2")
    floor = item.get("floor") or {}
    fl, allfl = floor.get("floor"), floor.get("allFloors")
    addr = item.get("jibunAddress") or item.get("addressOrigin", {}).get("local3") or ""
    loc = item.get("location") or item.get("randomLocation") or {}
    price_str = _price_str(sales_type, item.get("price"))
    meta_parts = [price_str]
    if m2:
        try:
            meta_parts.append(f"{float(m2):g}㎡")
        except (TypeError, ValueError):
            meta_parts.append(f"{m2}㎡")
    if fl and allfl:
        meta_parts.append(f"{fl}/{allfl}층")
    if item.get("roomType"):
        meta_parts.append(item["roomType"])
    if addr:
        meta_parts.append(addr)
    if dist_m is not None:
        meta_parts.append(f"중심에서 {int(round(dist_m))}m")
    desc = (item.get("title") or "") + " — " + (item.get("description") or "")
    desc = " ".join(desc.split())[:90]
    url = f"https://www.zigbang.com/home/{cat}/items/{iid}"
    return {
        "itemId": iid,
        "salesType": sales_type,
        "title": item.get("title") or f"{item.get('serviceType','')} {sales_type}".strip(),
        "meta": " · ".join(p for p in meta_parts if p),
        "summary": desc,
        "deposit": (item.get("price") or {}).get("deposit"),
        "rent": (item.get("price") or {}).get("rent"),
        "area_m2": m2,
        "floor": fl,
        "address": addr,
        "lat": loc.get("lat"),
        "lng": loc.get("lng"),
        "distance_m": None if dist_m is None else int(round(dist_m)),
        "url": url,
        "image": item.get("imageThumbnail"),
        "thumbnail": item.get("imageThumbnail"),
    }


def get_zigbang_listings(tool_input: dict):
    """[sense:realty]{source: "zigbang"} — 직방 현재 매물(호가) 조회.

    입력: region(지명) 또는 lat/lng · type(villa/oneroom/officetel) · deal(trade/rent) ·
          lease(전세/월세, 좁힘) · deposit_max/rent_max/deposit_min(만원) · radius(m,기본3000) · limit(기본30)
    """
    region = tool_input.get("region") or tool_input.get("region_name") or tool_input.get("q")
    lat = tool_input.get("lat")
    lng = tool_input.get("lng")
    matched = None
    if lat is None or lng is None:
        if not region:
            return {"success": False,
                    "error": "직방 매물 조회에는 region(지명, 예: '평택 죽백동' 또는 '배다리도서관') 또는 lat/lng가 필요합니다."}
        geo = _geocode(region)
        if not geo:
            return {"success": False, "error": f"'{region}' 위치를 찾지 못했습니다. 더 구체적인 동·지역명으로 시도하세요."}
        lat, lng, matched = geo["lat"], geo["lng"], geo["matched"]
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return {"success": False, "error": "lat/lng 좌표가 올바르지 않습니다."}

    rtype = (tool_input.get("type") or _CAT_DEFAULT).strip().lower()
    cat = _TYPE_TO_CAT.get(rtype, _CAT_DEFAULT)
    if rtype in ("apt", "아파트", "apartment"):
        return {"success": False,
                "error": "source=zigbang는 빌라(villa)·원룸(oneroom)·오피스텔(officetel)만 지원합니다. "
                         "아파트 시세는 source=molit(실거래가) 또는 가이드(real_estate.md)의 네이버부동산 경로를 쓰세요."}
    sales_types = _sales_types(tool_input.get("deal"), tool_input.get("lease"))
    try:
        radius = int(tool_input.get("radius") or 3000)
    except (TypeError, ValueError):
        radius = 3000
    try:
        limit = max(1, min(50, int(tool_input.get("limit") or 30)))
    except (TypeError, ValueError):
        limit = 30

    # 리스트 호출 (geohash5 박스 — 약 4.9km). salesTypes 서버 필터.
    gh = _geohash(lat, lng, 5)
    qs = {"geohash": gh, "depositMin": tool_input.get("deposit_min") or 0,
          "rentMin": 0, "domain": "zigbang", "checkAnyItemWithoutFilter": "true"}
    params = urllib.parse.urlencode(qs)
    for i, st in enumerate(sales_types):
        params += f"&salesTypes[{i}]={urllib.parse.quote(st)}"
    try:
        listing = _http_json(f"{_API}/v2/items/{cat}?{params}", timeout=12)
    except Exception as e:
        return {"success": False, "error": f"직방 리스트 조회 실패: {e}"}
    markers = listing.get("items") or []
    if not markers:
        return {"success": True, "source": "zigbang", "count": 0, "items": [],
                "message": f"'{matched or region}' 반경에 직방 {cat} {'/'.join(sales_types)} 매물이 없습니다.",
                "조회지역": matched or region}

    # 거리 선필터 + 정렬 → 가까운 limit개만 상세 조회(상세 호출 비용 절약)
    scored = []
    for m in markers:
        mlat, mlng = m.get("lat"), m.get("lng")
        if mlat is None or mlng is None:
            continue
        d = _haversine_m(lat, lng, float(mlat), float(mlng))
        if d <= radius:
            scored.append((d, m.get("itemId")))
    scored.sort(key=lambda x: x[0])
    near = scored[:limit]
    if not near:
        return {"success": True, "source": "zigbang", "count": 0, "items": [],
                "message": f"'{matched or region}' 반경 {radius}m 내 직방 {cat} 매물이 없습니다(반경을 넓혀보세요).",
                "조회지역": matched or region}

    # 상세 병렬 조회
    dist_by_id = {iid: d for d, iid in near}
    with ThreadPoolExecutor(max_workers=8) as ex:
        details = list(ex.map(_fetch_detail, [iid for _, iid in near]))

    # 가격 후필터(deposit_max/rent_max) + 행 구성
    dep_max = tool_input.get("deposit_max")
    rent_max = tool_input.get("rent_max")
    rows = []
    for item in details:
        row = _detail_to_row(item, cat, (lat, lng), dist_by_id.get(item.get("itemId")) if item else None)
        if not row:
            continue
        if row["salesType"] not in sales_types:
            continue
        if dep_max is not None and row.get("deposit") is not None:
            try:
                if float(row["deposit"]) > float(dep_max):
                    continue
            except (TypeError, ValueError):
                pass
        if rent_max is not None and row.get("rent"):
            try:
                if float(row["rent"]) > float(rent_max):
                    continue
            except (TypeError, ValueError):
                pass
        rows.append(row)
    rows.sort(key=lambda r: (r["distance_m"] if r["distance_m"] is not None else 1e9))

    # 단일 통화 items — 열린 dict(title·meta·summary·url·image + lat·lng·distance_m).
    # 옛 records가 5칸으로 접던 lat/lng를 items는 그대로 노출 → 지도/차트 소비자가 직독.
    # map_data 봉투는 지도 위젯용으로 별도 유지(center 포함, items에서 유도 불가한 줌 기준점).
    items_out = [{"title": r["title"], "meta": r["meta"], "summary": r["summary"],
                  "url": r["url"], "image": r["image"],
                  "lat": r.get("lat"), "lng": r.get("lng"),
                  "distance_m": r.get("distance_m")} for r in rows]
    lease_label = "/".join(sales_types)
    msg_lines = [f"직방 '{matched or region}' 반경 {radius}m · {cat} {lease_label} — {len(rows)}건:"]
    for r in rows:
        msg_lines.append(f"- {r['meta']}\n  {r['url']}")
    return {
        "success": True,
        "source": "zigbang",
        "조회지역": matched or region,
        "center": {"lat": lat, "lng": lng},
        "count": len(rows),
        "message": "\n".join(msg_lines),
        "items": items_out,
        "map_data": {"center": {"lat": lat, "lng": lng},
                     "markers": [{"lat": r["lat"], "lng": r["lng"], "name": r["title"],
                                  "meta": r["meta"], "url": r["url"]} for r in rows if r["lat"]]},
    }
