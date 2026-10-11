"""직방(Zigbang) 현재 매물(호가) 조회 — [sense:realty]{source: "zigbang"}.

국토부 실거래가(molit)가 *체결된 과거 거래*만 주는 것과 달리, 직방은 *지금 시장에 나온 매물*
(호가·사진·링크)을 준다. 빌라/원룸/오피스텔 개별 호실에 강하다(아파트 단지·단독/다가구는 약함).

비공식 내부 API(apis.zigbang.com). 키 불필요. 한국 IP에서 차단 약함.
흐름: 지명→좌표(/v2/search, Nominatim 폴백) → geohash5 → 리스트(마커 id) →
반경의 격자들을 조회 → ID 중복 제거·거리 선필터 → 상세 병렬조회 → items 통화.

리스트 개편(2026-08-10 실측): 옛 `/v2/items/{cat}` 이 404 로 은퇴 →
`/house/property/v1/items/{villas|onerooms|officetels}` (경로가 복수형).
★웹사이트는 geohash 를 암호화 blob 으로 보내지만 **평문 geohash5 도 그대로 통한다**.
salesTypes[i] 서버필터 생존(실측 434→20건), 마커 필드 itemId→**id**.
상세 /v3/items/{id}·검색 /v2/search 는 불변. (벌크 상세 POST
/house/property/v1/items/list {itemIds, ≤15개} 도 존재 — 필요 시 왕복 절감 후보.)
"""
import json
import math
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from common.value_semantics import numeric_value

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
# 리스트 엔드포인트(/house/property/v1/items/…)는 경로가 복수형 — 웹 URL·상세는 단수형 유지.
_CAT_PLURAL = {"villa": "villas", "oneroom": "onerooms", "officetel": "officetels"}


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
    # 2) Nominatim 폴백 (도서관·건물 등 POI는 직방 검색에 없을 수 있음) — 단일 소스 (감사 ⑥)
    from common.geocode import nominatim_search
    return nominatim_search(q)


def _sales_types(deal, lease):
    """deal/lease → 직방 salesTypes 목록. deal=trade→매매, rent→전세+월세. lease가 있으면 그걸로 좁힘."""
    lease = (lease or "").strip()
    deal = (deal or "rent").strip()
    if deal == "lease":
        lease, deal = lease or "jeonse", "rent"
    if deal not in ("trade", "rent", "전세", "jeonse", "월세", "wolse", "monthly") or lease not in ("", "전세", "jeonse", "월세", "wolse", "monthly"):
        raise ValueError("deal은 trade/rent/lease(전세), lease는 전세/월세입니다.")
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
    j = _http_json(f"{_API}/v3/items/{item_id}", timeout=12)
    return j.get("item") if isinstance(j, dict) else None


def _radius_cells(lat, lng, radius):
    """Cover the spherical radius bounding box with geohash5 cells, including seams."""
    angle = radius / 6371000.0
    delta_lat = math.degrees(angle)
    south, north = max(-90, lat - delta_lat), min(90, lat + delta_lat)
    if south <= -90 or north >= 90:
        delta_lng = 180
    else:
        delta_lng = math.degrees(math.asin(min(1, math.sin(angle) / math.cos(math.radians(lat)))))
    step = 180 / 4096  # geohash5: 12 latitude bits, 13 longitude bits
    y0, y1 = max(0, math.floor((south + 90) / step)), min(4095, math.floor((north + 90) / step))
    x0, x1 = math.floor((lng - delta_lng + 180) / step), math.floor((lng + delta_lng + 180) / step)
    if (y1 - y0 + 1) * (x1 - x0 + 1) > 64:
        raise ValueError("검색 반경이 64개 지도 격자를 넘습니다. radius를 줄여 주세요.")
    return list(dict.fromkeys(_geohash(-90 + (y + .5) * step,
                                      -180 + ((x % 8192) + .5) * step)
                              for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)))


def _listing_cell(gh, cat, sales_types, deposit_min):
    qs = {"geohash": gh, "salesPriceMin": 0, "depositMin": deposit_min or 0, "rentMin": 0}
    params = urllib.parse.urlencode(qs)
    for i, st in enumerate(sales_types):
        params += f"&salesTypes[{i}]={urllib.parse.quote(st)}"
    try:
        listing = _http_json(f"{_API}/house/property/v1/items/{_CAT_PLURAL[cat]}?{params}", timeout=12)
        if not isinstance(listing, dict) or not isinstance(listing.get("items"), list):
            raise ValueError("매물 목록 items가 없습니다.")
        return listing["items"], None
    except Exception as exc:
        return [], {"stage": "list", "geohash": gh, "error": str(exc)}


def _detail_result(iid):
    try:
        item = _fetch_detail(iid)
        if not isinstance(item, dict) or str(item.get("itemId")) != str(iid):
            raise ValueError("요청한 매물의 상세 응답이 없습니다.")
        return item, None
    except Exception as exc:
        return None, {"stage": "detail", "item_id": iid, "error": str(exc)}


def _detail_to_row(item, cat, center, dist_m):
    if not isinstance(item, dict):
        return None
    iid = item.get("itemId")
    sales_type = item.get("salesType") or ""
    area = item.get("area") or {}
    m2 = numeric_value(area.get("전용면적M2"))
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
        "supply_area_m2": numeric_value(area.get("공급면적M2")),
        "contract_area_m2": numeric_value(area.get("계약면적M2")),
        "floor": fl,
        # R7 칸 규약 — meta·summary 에 접힌 나머지 값의 구조 칸
        "total_floors": int(allfl) if str(allfl).isdigit() else allfl,  # 건물 전체 층수(meta 의 "층/전체층")
        "sales_price": (item.get("price") or {}).get("sales") or (item.get("price") or {}).get("salesPrice"),  # 매매가(만원, deposit 과 같은 단위)
        "room_type": item.get("roomType"),
        "description": item.get("description"),    # 원문 설명(summary 는 제목+설명 90자 표시본)
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
          lease(전세/월세, 좁힘) · deposit_max/rent_max/deposit_min(만원) · radius(m,기본3000) · limit(1~50, 기본30)
    """
    # ★침묵 클램프 청산(2026-08-24 #repair B6)
    try:
        _requested = int(tool_input.get("limit") or 30)
    except (TypeError, ValueError):
        _requested = 30
    if _requested > 50:
        return {"success": False, "requested": _requested,
                "error": f"직방은 한 번에 50건까지입니다(요청 {_requested}). limit 을 50 이하로 주세요."}
    limit = max(1, _requested)


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
    lat, lng = numeric_value(lat), numeric_value(lng)
    if lat is None or lng is None or not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return {"success": False, "error": "lat/lng 좌표가 올바르지 않습니다."}

    rtype = (tool_input.get("type") or _CAT_DEFAULT).strip().lower()
    cat = _TYPE_TO_CAT.get(rtype, _CAT_DEFAULT)
    if rtype in ("apt", "아파트", "apartment"):
        return {"success": False,
                "error": "source=zigbang는 빌라(villa)·원룸(oneroom)·오피스텔(officetel)만 지원합니다. "
                         "아파트 시세는 source=molit(실거래가) 또는 가이드(real_estate.md)의 네이버부동산 경로를 쓰세요."}
    sales_types = _sales_types(tool_input.get("deal"), tool_input.get("lease"))
    radius = numeric_value(tool_input.get("radius", 3000))
    if radius is None or radius <= 0 or radius > 20000000:
        return {"success": False, "error": "radius는 유한한 양수 거리(m)여야 합니다."}
    try:
        cells = _radius_cells(lat, lng, radius)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    # One cell does not cover the requested circle. Fetch its bounding cells once.
    with ThreadPoolExecutor(max_workers=4) as ex:
        listings = list(ex.map(lambda gh: _listing_cell(
            gh, cat, sales_types, tool_input.get("deposit_min")), cells))
    errors = [error for _, error in listings if error]
    distances = {}
    for markers, _ in listings:
        for marker in markers:
            iid = marker.get("id") or marker.get("itemId")
            mlat, mlng = numeric_value(marker.get("lat")), numeric_value(marker.get("lng"))
            if iid is None or mlat is None or mlng is None or not (-90 <= mlat <= 90 and -180 <= mlng <= 180):
                errors.append({"stage": "marker", "item_id": iid, "error": "매물 ID 또는 좌표가 올바르지 않습니다."})
                continue
            distance = _haversine_m(lat, lng, mlat, mlng)
            if distance <= radius:
                key = str(iid)
                if key not in distances or distance < distances[key][0]:
                    distances[key] = (distance, iid)
    scored = sorted(distances.values(), key=lambda pair: pair[0])
    dep_max = numeric_value(tool_input.get("deposit_max"))
    rent_max = numeric_value(tool_input.get("rent_max"))
    rows, checked = [], 0
    # Limit applies to accepted results. Stop once filled; never repeat an ID.
    with ThreadPoolExecutor(max_workers=8) as ex:
        while checked < len(scored) and len(rows) < limit:
            batch = scored[checked:checked + min(8, limit - len(rows))]
            details = list(ex.map(_detail_result, [iid for _, iid in batch]))
            checked += len(batch)
            for (distance, iid), (item, error) in zip(batch, details):
                if error:
                    errors.append(error)
                    continue
                row = _detail_to_row(item, cat, (lat, lng), distance)
                if row["salesType"] not in sales_types:
                    continue
                deposit, rent = numeric_value(row.get("deposit")), numeric_value(row.get("rent"))
                if dep_max is not None and deposit is not None and deposit > dep_max:
                    continue
                if rent_max is not None and rent is not None and rent > rent_max:
                    continue
                rows.append(row)
    rows.sort(key=lambda r: (r["distance_m"] if r["distance_m"] is not None else 1e9))

    # 상세에서 읽은 숫자·식별자도 통화에 보존한다. 화면용 필드만 고르면
    # 보증금·면적·층이 meta 산문에 갇혀 filter·sort·재방문 대조가 불가능해진다.
    # deposit/rent는 API 원단위인 만원(네이버의 price/rent는 원)이다.
    # map_data 봉투는 지도 위젯용으로 별도 유지(center 포함, items에서 유도 불가한 줌 기준점).
    items_out = [dict(r) for r in rows]
    for row in items_out:
        row.update(currency="KRW", deal_type=row.get("salesType"))
        for original, canonical in (("deposit", "deposit_won"), ("rent", "rent_won")):
            raw = row.get(original)
            if raw is not None:
                try:
                    row[canonical] = int(float(str(raw).replace(",", "")) * 10000)
                except (ValueError, TypeError):
                    pass
        # 칸 규약 2(원 단위 price) — 매매는 매매가, 임대는 보증금. 옛 코드는 매매에도 보증금을 넣어
        # 매매가가 sales 에만 있는 매물의 price 가 비거나 보증금이 됐다(표시는 sales 우선이라 둘이 어긋남).
        if row.get("salesType") == "매매":
            sale = row.get("sales_price") or row.get("deposit")
            try:
                row["price"] = int(float(str(sale).replace(",", "")) * 10000) if sale not in (None, "") else None
            except (TypeError, ValueError):
                row["price"] = None
        elif "deposit_won" in row:
            row["price"] = row["deposit_won"]
    lease_label = "/".join(sales_types)
    message = f"직방 '{matched or region}' 반경 {radius}m · {cat} {lease_label} — {len(rows)}건 (상세는 items)"
    out = {
        "success": True,
        "source": "zigbang",
        "source_complete": not errors,
        "errors": errors,
        "search_scope": {"radius_m": radius, "geohashes": cells,
                         "candidate_count": len(scored), "details_checked": checked},
        "조회지역": matched or region,
        "center": {"lat": lat, "lng": lng},
        "count": len(rows),
        "message": message,
        "items": items_out,
        "map_data": {"center": {"lat": lat, "lng": lng},
                     "markers": [{"lat": r["lat"], "lng": r["lng"], "name": r["title"],
                                  "meta": r["meta"], "url": r["url"]} for r in rows if r["lat"]]},
    }
    if errors:
        out["warning"] = f"직방 검색 일부 실패 {len(errors)}건. 성공한 매물은 items에 보존했습니다."
        out["message"] += " · 일부 조회 실패(매물 없음으로 해석하지 마세요)"
    if checked < len(scored):
        out["truncations"] = [{"scope": "selection", "reason": "limit", "limit": limit,
                               "remaining_candidates": len(scored) - checked}]
    return out
