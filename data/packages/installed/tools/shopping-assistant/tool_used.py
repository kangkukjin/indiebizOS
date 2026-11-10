"""
tool_used.py — 중고 C2C 매물 검색 어댑터 ([sense:used] 결정화)

빈도 높은 중고물건 검색을 어휘로 승격. 명명 헌법대로 소스마다 액션이 아니라
[sense:used]{source} 한 액션 + source 파라미터(직방 sense:realty{source} 선례).

통화 = items[{title, meta, summary, url, image}] (단일 통화 {items:[...]}. realty/stay와 동일).

소스별 접근(2026-07-12 실측 확정):
- bunjang : /api/search/v8/web/search → mainGrid 매물과 커서(2026-11-10 확인).
            외부·유료 광고 및 추천 목록 제외. 위치 미제공은 미확인으로 보존.
- joongna : web.joongna.com/search RSC 스트림(self.__next_f)에 seq/title/price/url. best-effort.
- danggeun: 2단 — ①지역 해소 /kr/api/v1/regions/keyword ②검색 /kr/search/buy-sell/?in=x-{id}&q=
            의 Remix 로더 JSON(`_data=routes/kr.search.buy-sell._index`) → buySellArticles.
            (2026-09-29 재실측: 옛 /kr/buy-sell/?search= 는 301 로 새 주소에 가고 JSON-LD 가 사라졌다.
             SSR HTML 의 __remixContext 에도 같은 키가 있으나 목록이 비어 오고 클라이언트가 로더를 다시 부른다.)
- naver   : 핸들러에서 api_call cafearticle(중고나라 카페) — 이 파일 밖(키 필요).
"""

import re
import json
import time

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


def _num_or_none(v):
    """수치 칸 병기용 — 정수 원 단위, 실패 시 None (F1 규약: 표시=meta, 수치=price)."""
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


# ============ bunjang — 내부 API (★깨끗) ============

# 번개장터 API 에는 지역 이름 인자가 없다(응답 flags 의 "내근처"는 기기 좌표 기반) — region 은 후필터뿐이다.
# 전국 최신순 한 쪽(40행)만 보고 걸렀더니 "그 지역 매물 0건"이 사실처럼 나왔다(79회차 B79-4). region 이 있으면
# 목표 수를 채울 때까지 쪽을 넘기되 상한을 두고, 상한에 닿으면 표본이었음을 truncations 로 말한다.
BUNJANG_PAGE_SIZE = 40
BUNJANG_REGION_SCAN_PAGES = 5          # 최신순 커서 최대 쪽 수; 매물 수도 별도로 200건 제한


def _bunjang_page(query, cursor, n):
    url = "https://api.bunjang.co.kr/api/search/v8/web/search"
    params = {"q": query, "policyKey": "pw.product.keyword", "sort": "latest", "size": n}
    if cursor is not None:
        params["cursor"] = cursor
    text, code = _get(url, params=params)
    if code != 200:
        raise RuntimeError(f"번개장터 API HTTP {code}")
    try:
        grid = json.loads(text)["data"]["responses"]["mainGrid"]["searchResponse"]
        rows = grid["data"]
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("invalid rows")
        cursor = grid.get("cursor")
        if cursor is not None and not isinstance(cursor, str):
            raise ValueError("invalid cursor")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("번개장터 mainGrid 매물 구조를 확인할 수 없습니다(원천 구조 변경)") from exc
    return {"list": rows, "num_found": grid.get("totalCount"), "cursor": cursor or None}


def _bunjang_record(it, loc):
    pid = it.get("pid")
    status = {"SELLING": "판매중", "RESERVED": "예약중", "SOLD_OUT": "판매완료"}.get(it.get("status"))
    meta_bits = [_man(it.get("price"))]
    if loc:
        meta_bits.append(loc)
    if status in {"판매완료", "예약중"}:
        meta_bits.append(status)
    return {
        "title": (it.get("name") or "").strip(),
        "meta": " · ".join(meta_bits),
        "summary": "",
        "url": f"https://m.bunjang.co.kr/products/{pid}" if pid else "",
        "image": (it.get("productImage") or "").replace("{res}", "320"),
        # 수치 칸 병기 (F1, 2026-08-16 상상훈련): 가격이 meta 텍스트("80만원")에만 있으면
        # sort/filter/비교 파이프가 원리적으로 막힌다 — 표시용 meta 와 별개로 수치를 나른다.
        "price": _num_or_none(it.get("price")),
        # R7 — meta 에 접힌 거래 지역·거래완료 여부의 구조 칸
        "location": loc or None,
        "sold": status == "판매완료" if status else None,
    }


def search_bunjang(query, limit=20, region=None):
    """최신순 매물 커서 조회. 최대 5쪽·200매물, region은 위치 후필터이며 미표기는 제외한다."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        return {"success": False, "source": "bunjang", "error": "limit은 양의 정수여야 합니다", "items": []}
    n, pages = BUNJANG_PAGE_SIZE, BUNJANG_REGION_SCAN_PAGES
    scan_limit = n * pages
    records, scanned, unlocated, num_found, exhausted = [], 0, 0, None, False
    cursor, cursors, product_ids = None, set(), set()
    try:
        for _ in range(pages):
            data = _bunjang_page(query, cursor, n)
            rows = data["list"]
            if num_found is None and isinstance(data.get("num_found"), int):
                num_found = data["num_found"]
            for it in rows:
                if it.get("type") == "EXT_AD":
                    continue
                if it.get("type") != "PRODUCT":
                    raise ValueError("번개장터 매물 type을 확인할 수 없습니다(원천 구조 변경)")
                if it.get("ad"):
                    continue
                pid = it.get("pid")
                if not pid or not isinstance(it.get("name"), str) or not it["name"].strip():
                    raise ValueError("번개장터 매물의 pid/name이 없습니다(원천 구조 변경)")
                if pid in product_ids:
                    continue
                if scanned >= scan_limit:
                    break
                product_ids.add(pid)
                scanned += 1
                loc = (it.get("location") or "").strip()
                if region:
                    if not loc:
                        unlocated += 1
                        continue
                    if region not in loc:
                        continue
                records.append(_bunjang_record(it, loc))
                if len(records) >= limit:
                    break
            else:
                # A response can exceed size or mix ads. Only its cursor proves
                # exhaustion; a short page/totalCount must not skip the next page.
                if not data["cursor"]:
                    exhausted = True
            if len(records) >= limit or exhausted or scanned >= scan_limit:
                break
            cursor = data["cursor"]
            if cursor in cursors:
                raise ValueError("번개장터 페이지 커서가 반복됩니다")
            cursors.add(cursor)
    except Exception as e:
        if not records:
            return {"success": False, "source": "bunjang", "error": f"번개장터 조회 실패: {e}", "items": []}
        # 앞 쪽에서 모은 행은 보존하고 나머지 쪽의 실패를 원천 절단으로 신고한다.
        return {"source": "bunjang", "total": len(records), "items": records,
                # truncation-scope: source — 뒤 쪽 조회 실패로 훑기가 끊겼다
                "scanned": scanned, "unlocated": unlocated, "truncated": True,
                "truncations": [{"scope": "source", "reason": "fetch_error", "scanned": scanned,
                                 "retained": len(records), "error": str(e)[:200]}]}

    res = {"source": "bunjang", "total": len(records), "items": records}
    if num_found is not None:
        res["total_estimate"] = num_found          # 원천이 말한 검색 모집단(전국, 추정치)
    if region or (len(records) < limit and not exhausted):
        if region:
            res["region"] = region
        res["scanned"] = scanned                  # 훑은 원천 행 수(전국 최신순)
        res["unlocated"] = unlocated              # 위치 미표기라 region 판정 불가로 뺀 행
        if len(records) < limit and not exhausted:
            # truncation-scope: source — 지역 인자가 없는 원천을 상한 쪽수까지만 훑은 표본
            res["truncated"] = True
            res["truncations"] = [{"scope": "source", "reason": "scan_limit",
                                   "limit": scan_limit, "scanned": scanned,
                                   "retained": len(records), "unlocated": unlocated}]
            res["note"] = f"최대 {pages}쪽·{scan_limit}매물 조회 상한에 닿아 나머지는 확인하지 못했습니다."
        if region:
            res["note"] = (res.get("note", "") + f" 전국 최신 {scanned}건 중 위치에 '{region}' 이 든 매물만 "
                           f"남겼습니다(위치 미표기 {unlocated}건은 판정 불가로 제외). "
                           "0건으로 지역 매물 부재를 단정할 수 없습니다. 동네 검색은 source=danggeun을 쓰세요.").strip()
    return res


# ============ joongna — RSC 스트림 파싱 (best-effort) ============

def search_joongna(query, limit=20):
    """중고나라 web 검색. Next.js RSC 스트림에서 상품 필드 추출(best-effort)."""
    url = f"https://web.joongna.com/search/{query}"
    try:
        text, code = _get(url)
        if code != 200:
            return {"success": False, "error": f"중고나라 HTTP {code}", "items": []}
    except Exception as e:
        return {"success": False, "error": f"중고나라 조회 실패: {e}", "items": []}

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
            "price": _num_or_none(pm.group(1)) if pm else None,
        })
        if len(records) >= limit:
            break
    return {"source": "joongna", "total": len(records), "items": records,
            "note": "RSC 파싱(best-effort) — 제목/가격 일부 누락 가능"}


# ============ danggeun — 검색 로더 JSON (2026-09-29 복구) ============
#
# 옛 경로 /kr/buy-sell/?in=x-{id}&search= 는 301 로 /kr/search/buy-sell/?in=x-{id}&q= 에 간다.
# 새 페이지는 Remix 앱이라 JSON-LD ItemList 가 없고, SSR HTML 의 window.__remixContext 안
# `routes/kr.search.buy-sell._index` 로더 데이터에 buySellArticles 가 있다 — 다만 그 목록은
# 비어 오고 브라우저가 같은 로더를 `_data=` JSON 으로 다시 부른다(실측). 그래서 로더 JSON 을 직접 읽는다.
# ★함정 1: in= 슬러그의 한글 이름은 장식이고 숫자 ID만 유효 — 반드시 regions/keyword 로 해소할 것.
# ★함정 2(2026-09-29 실측): 같은 로더 요청이 간헐적으로 빈 목록을 준다(광고 목록도 0). 연속 10회 중 1회만
#   282건, 나머지 0건 — UA 판본·쿠키 세션·TLS 위장으로 가려 봤지만 규칙이 없었다(원인 미상, 원천 쪽).
#   구조는 멀쩡하므로 source_changed 가 아니지만 "매물 없음"으로 단정할 수도 없다 → 0건이면 간격을 두고
#   몇 번 다시 묻고, 그래도 0건이면 empty_notes 로 미확인임을 말한다(0행=성공 계약은 지키되 해석을 싣는다).
DANGGEUN_LOADER = "routes/kr.search.buy-sell._index"
DANGGEUN_EMPTY_RETRIES = 3        # 0건일 때 더 묻는 횟수(원천 간헐 빈 목록 대응 — 호출 상한)
DANGGEUN_RETRY_GAP_S = 1.0
DANGGEUN_STATUS = {"Ongoing": "판매중", "Reserved": "예약중", "Closed": "거래완료", "Completed": "거래완료"}


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


def _danggeun_loader(query, region_id):
    """검색 로더 JSON 한 번. (data, None) 또는 (None, 실패 봉투)."""
    url = "https://www.daangn.com/kr/search/buy-sell/"
    params = {"q": query, "_data": DANGGEUN_LOADER}
    if region_id:
        params["in"] = f"x-{region_id}"  # 이름 부분은 장식 — ID만 유효
    try:
        text, code = _get(url, params=params, timeout=20)
    except Exception as e:
        return None, {"success": False, "source": "danggeun", "error": f"당근 검색 실패: {e}", "items": []}
    if code != 200:
        return None, {"success": False, "source": "danggeun", "error": f"당근 검색 HTTP {code}", "items": []}
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("buySellArticles"), list):
        return None, {"success": False, "source": "danggeun", "error_type": "source_changed",
                      "error": "당근 검색 구조를 확인할 수 없습니다(검색 로더 JSON 의 buySellArticles 미발견). "
                               "매물 0건으로 해석하지 마세요.",
                      "items": []}
    return data, None


def _danggeun_price(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def search_danggeun(query, limit=20, region=None, requested_limit=None):
    """당근 web 검색. region(동 이름) = 그 동네+인근 동 스코프(당근의 '내동네'). region 은 필수다."""
    if not region:
        # 지역 없는 요청은 당근이 접속 IP 로 동네를 추정해 조용히 스코프한다(실측: 분평동) — 사용자가
        # 고르지 않은 동네의 결과를 '전체'처럼 줄 수 없다.
        return {"success": False, "source": "danggeun", "error_type": "missing_param",
                "error": "당근 검색은 동네 단위입니다 — region 에 동/읍/면 이름(예 \"역삼동\")을 주세요.",
                "items": []}
    region_id, resolved = _resolve_danggeun_region(region)
    if region_id is None:
        return {"success": False, "source": "danggeun", "error": resolved, "items": []}
    region_full = resolved

    data, fail = _danggeun_loader(query, region_id)
    if fail:
        return fail
    retried = 0
    while not data["buySellArticles"] and retried < DANGGEUN_EMPTY_RETRIES:
        retried += 1
        time.sleep(DANGGEUN_RETRY_GAP_S)
        data2, fail2 = _danggeun_loader(query, region_id)
        if fail2:
            return fail2
        data = data2
    got_region = str(((data.get("currentFilters") or {}).get("regionId")) or "")
    if got_region and got_region != str(region_id):
        return {"success": False, "source": "danggeun", "error_type": "source_changed",
                "error": f"당근이 요청한 동네(ID {region_id})가 아닌 동네(ID {got_region})로 검색했습니다.",
                "items": []}

    articles = [a for a in data["buySellArticles"] if isinstance(a, dict)]
    records = []
    for it in articles[:limit]:
        price = _danggeun_price(it.get("price"))
        status = DANGGEUN_STATUS.get(it.get("status"), it.get("status") or "")
        sold = status == "거래완료"
        art_region = ((it.get("region") or {}).get("name")) or None
        meta_bits = [_man(price) if price is not None else ""]
        if art_region:
            meta_bits.append(art_region)
        if status and status != "판매중":
            meta_bits.append(status)
        href = it.get("href") or it.get("id") or ""
        records.append({
            "title": (it.get("title") or "").strip(),
            "meta": " · ".join(b for b in meta_bits if b),
            "summary": (it.get("content") or "").strip()[:200],
            "url": ("https://www.daangn.com" + href) if href.startswith("/") else href,
            "image": it.get("thumbnail") or "",
            "price": price,
            # R7 — meta 에 접힌 매물 동네·상태의 구조 칸. region 은 이제 매물의 실제 동(옛 판은 검색 동네)
            "region": art_region,
            "search_region": region_full,
            "status": status or None,
            "sold": sold,
            "created_at": it.get("createdAt"),
        })

    truncated = len(articles) > len(records)
    from common.currency import bounded_selection
    res = {"source": "danggeun", "total": len(articles), "items": records,
           "region": region_full,
           "note": "해당 동 + 인근 동 매물(당근 '내동네' 스코프). 행의 region 이 매물의 동이다.",
           # truncation-scope: bounded — 명시 limit 과 실효 상한이 같고 충족한 선택만 selection
           **({"truncated": True} if truncated else {}),
           **bounded_selection(requested_limit, limit, len(records), truncated)}
    if not articles:
        res["empty_notes"] = [
            f"당근 검색이 0건을 돌려줬습니다(재시도 {retried}회 포함). 당근 검색이 같은 요청에 간헐적으로 빈 목록을 "
            "주는 현상이 실측돼 '매물 없음'으로 단정할 수 없습니다 — 잠시 뒤 다시 확인하세요."]
    elif retried:
        res["retried"] = retried
    return res
