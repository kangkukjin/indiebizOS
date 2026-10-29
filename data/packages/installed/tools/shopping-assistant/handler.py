"""
쇼핑 검색 도구 — 새 상품 가격비교(다나와·에누리) + 중고 C2C([sense:used]) + 외주([sense:freelance])

★2026-08-04: [sense:search_shopping] 의 중고 축(site=used/all)은 은퇴했다.
  중고 매물은 [sense:used](tool_used.py — 내부 API, 소스 4종, 폰 동작)가 정본.

Phase 0 마이그레이션: common 유틸리티 사용
"""
import sys
import os
import json
import asyncio
# playwright 는 다나와 스크래핑(브라우저 자동화) 폴백에만 필요 — 모듈 레벨이면 폰서 import 실패해
# 순수 HTTP 인 다나와·중고·외주 검색까지 통째로 막힌다(study:arxiv 와 동일 함정).
# → 지연 import 로 내려, 폰선 HTTP 경로가 로컬 작동하고 폴백만 graceful 미지원.

# backend/common 모듈 경로 추가
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.api_client import api_call
from common.auth_manager import check_api_key
from common.html_utils import clean_html
from common.response_formatter import format_json


def _products_to_records(items):
    """상품 목록 → 레코드 통화(records). 비파괴 부착용.
    title=상품명 · meta=가격·쇼핑몰 · url=링크 · image=상품이미지(있을 때만)."""
    records = []
    for it in items:
        if not isinstance(it, dict):
            continue
        price = it.get("price")
        price_str = ""
        if price not in (None, "", "0", 0):
            try:
                price_str = f"{int(str(price)):,}원"
            except (ValueError, TypeError):
                price_str = str(price)
        meta_parts = [price_str, it.get("mall")]
        try:
            price_num = int(str(price).replace(",", "").replace("원", "").strip())
        except (ValueError, TypeError):
            price_num = None
        rec = {
            "title": it.get("name", ""),
            "meta": " · ".join(p for p in meta_parts if p),
            "summary": "",
            "url": it.get("link", ""),
            # R7 칸 규약 — meta 에 접힌 가격(정수 원)·쇼핑몰의 구조 칸
            "price": price_num,
            "mall": it.get("mall"),
        }
        image = it.get("image")
        if image:
            rec["image"] = image
        records.append(rec)
    return records


def search_naver_shopping(query: str, display: int = 5):
    """종료된 공식 API: https://developers.naver.com/notice/article/32564 (2026-07-31)."""
    return {"success": False, "error_type": "source_retired", "items": [],
            "error": "네이버 쇼핑 API는 2026-07-31 종료됐습니다. site=danawa 또는 enuri를 사용하세요."}


def _load_shopping_source(filename):
    # 패키지 reload 뒤에도 새 파일의 파서를 사용한다. 외부 입력은 파일명으로 받지 않는다.
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename + ".py")
    spec = importlib.util.spec_from_file_location(filename, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def search_danawa_shopping_async(query: str, display: int = 5, page: int = 1,
                                       sort: str = "default"):
    """HTTP·구조 확인 실패를 브라우저로 보완한다. 두 경로의 페이지·정렬·파서는 동일하다."""
    from datetime import datetime, timezone
    from urllib.parse import urlencode
    module = _load_shopping_source("tool_danawa")
    try:
        result = await asyncio.to_thread(module.search_danawa, query, display, page, sort)
        if result.get("success") is not False or result.get("error_type") in ("invalid_argument", "unsupported_option"):
            return result
        failure = result
    except Exception as exc:
        failure = {"success": False, "items": [], "error_type": "http_error", "error": str(exc)}
    params = module.search_params(query, page, sort)
    url = module._SEARCH + "?" + urlencode(params)
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                tab = await browser.new_page()
                response = await tab.goto(url, wait_until="domcontentloaded", timeout=25000)
                if response is None or response.status != 200:
                    raise RuntimeError(f"브라우저 HTTP {response.status if response else '미확인'}")
                # 서버가 이미 완성한 검색 상태는 옛 카드 셀렉터를 기다리지 않는다.
                deadline = asyncio.get_running_loop().time() + 12
                while True:
                    result = module.parse_danawa(await tab.content(), display, query=query, page=page)
                    remaining = deadline - asyncio.get_running_loop().time()
                    if result.get('error_type') != 'source_changed' or remaining <= 0:
                        break
                    await asyncio.sleep(min(.25, remaining))
                result.update(source="danawa", query=query, page=page,
                              page_size=module.PAGE_SIZE, sort=sort, source_url=url,
                              observed_at=datetime.now(timezone.utc).isoformat(),
                              transport="browser", http_failure=failure)
                return result
            finally:
                await browser.close()
    except Exception as exc:
        failure["browser_failure"] = str(exc)
        return failure


# ★중고 축(site=used/all)은 2026-08-04 은퇴 — `search_used_items_async`·`search_all_async` 삭제.
#
# 있던 것: 중고나라(web.joongna.com)·번개장터(m.bunjang.co.kr)를 Playwright 로 긁던 함수.
# 죽은 이유: 두 사이트 개편으로 셀렉터(`ul.grid > li`, `div[class*='ProductItem']`)가 낡아
#   **라이브 0건**(실측 2026-08-04, 11.6초 걸려 빈 목록). 게다가 두 블록 다 `except: pass`
#   라 실패가 침묵했다 — "중고가 없다"와 "긁기가 깨졌다"를 호출자가 구별할 수 없었다.
# 고치지 않은 이유: **같은 두 소스를 [sense:used] 가 이미 내부 API 로 준다**(tool_used.py —
#   실측 번개장터 0.1초·중고나라 0.3초에 각 5건, 제목·가격·위치·링크). 소스도 넷
#   (bunjang/danggeun/joongna/naver)이고 동네 스코프까지 되며, 브라우저 자동화가 아니라
#   폰에서도 돈다. 스크래퍼를 고쳐 봐야 더 느리고 더 약한 두 번째 창구가 될 뿐이다.
# → 중고는 [sense:used]. 되살리지 말 것.
#
# 옛 site=all(새 상품+중고)은 은퇴 상태다. 여러 원천은 IBL의 &로 명시 조합한다.


def _search_naver_used(query: str, limit: int = 15):
    """[sense:used] source=naver — 네이버 카페 통합검색(중고나라 카페 등 게시글)."""
    ok, err = check_api_key("naver")
    if not ok:
        return {"success": False, "source": "naver", "error": err, "items": []}
    # ★침묵 클램프 청산(2026-08-24 #repair B6)
    _display = min(limit, 20)
    data = api_call("naver", "/v1/search/cafearticle.json",
                    params={"query": query, "display": _display, "sort": "date"})
    if isinstance(data, dict) and "error" in data:
        return {"success": False, "source": "naver", "error": data["error"], "items": []}
    records = []
    for it in data.get("items", []):
        records.append({
            "title": clean_html(it.get("title", "")),
            "meta": clean_html(it.get("cafename", "")),
            "summary": clean_html(it.get("description", ""))[:200],
            "url": it.get("link", ""),
            "image": "",
        })
    return {"source": "naver", "total": len(records), "items": records,
            **({"clamped": True, "requested": limit,
                "message": f"네이버 카페 검색은 {_display}건까지 — 요청 {limit}건을 깎았습니다."}
               if limit > _display else {}),
            "note": "네이버 카페 통합검색(중고나라 등) — 게시글 기준"}


def _handle_used(tool_input: dict) -> str:
    """[sense:used] — 중고 C2C 매물 검색(source 분기). items 통화(단일 통화 {items:[...]})."""
    # sys.path+import는 sys.modules에 캐시돼 /packages/reload로 안 갈림 —
    # real-estate(tool_zigbang) 선례대로 파일에서 매번 fresh 로드.
    import importlib.util as _ilu
    _path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tool_used.py")
    _spec = _ilu.spec_from_file_location("tool_used", _path)
    _tu = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_tu)

    query = tool_input.get("query") or tool_input.get("q")
    if not query:
        return format_json({"success": False, "error": "검색어(query)를 입력해주세요.", "items": []})
    source = (tool_input.get("source") or "bunjang").lower()
    limit = int(tool_input.get("limit", 15))
    region = tool_input.get("region")

    if source == "bunjang":
        res = _tu.search_bunjang(query, limit=limit, region=region)
    elif source == "joongna":
        res = _tu.search_joongna(query, limit=limit)
    elif source == "naver":
        res = _search_naver_used(query, limit)
    elif source == "danggeun":
        res = _tu.search_danggeun(query, limit=limit, region=region,
                                  requested_limit=tool_input.get("limit"))
    else:
        return format_json({
            "success": False,
            "error": f"알 수 없는 source: {source} (bunjang/joongna/naver/danggeun)",
            "items": [],
        })
    return format_json(res)


def execute(tool_input: dict, context) -> str:
    """도구 실행 메인 핸들러 (ToolContext 기반 신규 시그니처)."""
    tool_name = context.tool_name
    if tool_name == "used_search":
        return _handle_used(tool_input)
    if tool_name == "search_shopping":
        query = tool_input.get("query")
        site = tool_input.get("site", "danawa")
        display = tool_input.get("limit", tool_input.get("display", 5))
        page = tool_input.get("page", 1)
        sort = tool_input.get("sort", "default")

        if not isinstance(query, str) or not query.strip():
            return format_json({"success": False, "error": "검색어를 입력해주세요.", "items": []})

        try:
            if site == "naver":
                result = search_naver_shopping(query, display)
            elif site == "enuri":
                module = _load_shopping_source("tool_enuri")
                result = module.search_enuri(query, display, page, sort)
            else:
                result = asyncio.run(search_danawa_shopping_async(query, display, page, sort))
                if site not in ("danawa", "enuri", "naver"):
                    # 어휘 밖 값(옛 used/all 포함) — 빈손으로 돌려보내는 대신 가격비교 결과를
                    # 주고 중고 정본으로 안내한다(옛 스크래퍼는 조용히 0건이라 이보다 나빴다).
                    # ★enum 리터럴로만 분기한다 — 은퇴한 값을 코드에 박으면 enum-가드가
                    #   어휘 드리프트로 잡는다(그게 맞다: 죽은 축은 코드에도 남기지 않는다).
                    result["note"] = (
                        f"알 수 없는 site='{site}' — 다나와 가격비교 결과를 반환했습니다. "
                        "중고 매물은 [sense:used]{source: \"bunjang\"|\"danggeun\"|\"joongna\"|\"naver\"} 를 "
                        "쓰세요(옛 site=used/all 축은 2026-08-04 은퇴)."
                    )

            result.setdefault("source", "enuri" if site == "enuri" else "naver" if site == "naver" else "danawa")
            result.setdefault("query", query)
            result.setdefault("page", page)
            result.setdefault("sort", sort)
            if result.get("empty_reason") == "no_results" and result["source"] == "danawa":
                from datetime import datetime, timezone
                from urllib.parse import urlencode
                module = _load_shopping_source("tool_danawa")
                result.update(source_url=module._SEARCH + "?" + urlencode(module.search_params(query, page, sort)),
                              observed_at=datetime.now(timezone.utc).isoformat(), page_size=module.PAGE_SIZE)
            result["price_note"] = "원천 표시 가격입니다. 옵션·배송·쿠폰·렌탈 조건은 판매처 원문에서 확인하세요. total은 반환 건수입니다."
            return format_json(result)
        except Exception as e:
            return format_json({"success": False, "error": f"오류 발생: {e}", "error_type": "http_error", "items": []})

    return format_json({"success": False, "error": f"알 수 없는 도구: {tool_name}"})
