"""
쇼핑 검색 도구 — 새 상품 가격비교(다나와) + 중고 C2C([sense:used]) + 외주([sense:freelance])

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
        rec = {
            "title": it.get("name", ""),
            "meta": " · ".join(p for p in meta_parts if p),
            "summary": "",
            "url": it.get("link", ""),
        }
        image = it.get("image")
        if image:
            rec["image"] = image
        records.append(rec)
    return records


def search_naver_shopping(query: str, display: int = 5):
    """네이버 쇼핑 검색 — ★은퇴. 공식 API 도 내부 API 도 막혔다(2026-08-04 실측 종결).

    ① 공식 오픈API `/v1/search/shop.json` = 404 SE05 "존재하지 않는 검색 api"(네이버가 은퇴).
    ② 내부 API 발굴 시도(직방 tool_zigbang·크몽 tool_freelance 선례) — **전부 차단**:
       · `search.shopping.naver.com/api/search/all` → **418**(I'm a teapot = WAF 봇 차단).
         ★없는 경로는 404 text/plain 9바이트로 답한다 → 418 은 "경로는 살아있고 WAF 가 막는다"는 뜻.
         `/ns/v1/search/paged-composite-cards` 도 동일하게 418(존재+차단).
       · 검색 페이지 HTML(웹·모바일·msearch) 전부 418 — SSR 데이터 추출 경로도 없음.
       · 쿠키 부트스트랩(naver.com→shopping.naver.com 방문 후 재시도)도 418 그대로.
       · curl_cffi impersonate="chrome" 무효 — TLS 지문 위장으로 뚫리는 층이 아니다.
       · **실제 창을 띄운 Chromium(headed, non-headless)조차 캡차**로 착지:
         `ncpt.naver.com/v1/wcpt/*` 영수증 이미지 문제 + 쿠키 `sus_val`·`X-Wtm-Cpt-Tk`
         (네이버 WTM 봇탐지 플랫폼). 즉 headless 탐지가 아니라 **자동화 전면 게이트**.
       · robots.txt = `User-agent: * / Disallow: /` (정책상으로도 금지).
       → 캡차를 푸는 것 외에 경로가 없고, 그건 하지 않는다(우회 금지 + 애초에 불안정한 토대).
    ③ 대체 후보 실측: 통합검색(search.naver.com)은 200 이지만 고유 상품 **3개**뿐이고
       대부분 광고 블록이라 상품 검색 소스로 부적합(robots 도 Disallow: /).
    → 결론: **네이버 축은 죽었다.** 쇼핑 검색의 몸은 다나와(순수 HTTP, 폰 포함)로 옮겼다
      (tool_danawa.py). 되살릴 여지가 생기면 418→200 전환 여부부터 재실측할 것.

    호출부(search_all_async·site:naver)가 items 부재를 우아하게 건너뛰도록 즉시 반환."""
    return {"success": False, "error": "네이버 쇼핑 검색 은퇴(2026-08) — 공식 API SE05 + 내부 API 418/캡차. 다나와 검색을 사용하세요.",
            "items": []}


async def search_danawa_shopping_async(query: str, display: int = 5):
    """다나와 검색 — **순수 HTTP 우선**(2026-08-04), Playwright 는 폴백.

    네이버 축이 죽어(search_naver_shopping 주석) 폰 쇼핑 검색이 완전히 비었던 것을,
    다나와가 봇 차단·TLS 지문 검사 없이 stdlib urllib 만으로 상품을 준다는 실측으로 메움.
    → tool_danawa.py 가 폰(curl_cffi 없는 Chaquopy)에서도 그대로 동작한다.
    HTTP 가 실패할 때만 옛 Playwright 경로(PC 전용)로 내려간다."""
    try:
        # tool_used/tool_freelance 와 동일 — /packages/reload 는 handler 만 갈고
        # 서브모듈은 sys.modules 캐시에 남으므로 파일에서 매번 fresh 로드.
        import importlib.util as _ilu
        _path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tool_danawa.py")
        _spec = _ilu.spec_from_file_location("tool_danawa", _path)
        _td = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_td)
        res = _td.search_danawa(query, display)
        if res.get("items"):
            return res
    except Exception:
        pass  # 아래 Playwright 폴백으로

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"success": False, "total": 0, "items": [], "error": "다나와 검색 실패(HTTP 파싱 결과 없음, 이 기기엔 브라우저 폴백 미지원)"}
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            url = f"https://search.danawa.com/dsearch.php?query={query}"
            await page.goto(url, wait_until="domcontentloaded")

            try:
                await page.wait_for_selector(".product_list .prod_main_info", timeout=5000)
            except:
                await browser.close()
                return {"total": 0, "items": []}

            items_els = await page.query_selector_all(".product_list .prod_main_info")
            items = []
            for el in items_els[:display]:
                name_el = await el.query_selector(".prod_name a")
                name = (await name_el.inner_text()).strip() if name_el else "N/A"

                price_el = await el.query_selector(".rank_one .price_sect strong")
                price = (await price_el.inner_text()).replace(",", "").strip() if price_el else "0"

                link = await name_el.get_attribute("href") if name_el else ""

                img_el = await el.query_selector(".thumb_image img")
                image = (await img_el.get_attribute("data-original")) or (await img_el.get_attribute("src")) or ""
                if image and image.startswith("//"):
                    image = "https:" + image

                items.append({
                    "name": name,
                    "price": price,
                    "mall": "다나와",
                    "link": link,
                    "image": image,
                    "category": "가전/디지털",
                    "site": "danawa"
                })

            await browser.close()
            return {"total": len(items), "items": items}
        except Exception as e:
            return {"success": False, "error": f"다나와 검색 중 오류: {str(e)}"}


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
# `site=all`(다나와+중고 합침)도 함께 은퇴 — 중고가 빠지면 다나와 하나라 별칭일 뿐이다.


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
        res = _tu.search_danggeun(query, limit=limit, region=region)
    else:
        return format_json({
            "success": False,
            "error": f"알 수 없는 source: {source} (bunjang/joongna/naver/danggeun)",
            "items": [],
        })
    return format_json(res)


def _handle_freelance(tool_input: dict) -> str:
    """[sense:freelance] — 프리랜서·외주 서비스 검색(source 분기). items 통화."""
    # tool_used 와 동일 — /packages/reload 가 handler 만 갈고 서브모듈은 sys.modules
    # 캐시에 남으므로 파일에서 매번 fresh 로드.
    import importlib.util as _ilu
    _path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tool_freelance.py")
    _spec = _ilu.spec_from_file_location("tool_freelance", _path)
    _tf = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_tf)
    return format_json(_tf.search_freelance(tool_input))


def execute(tool_input: dict, context) -> str:
    """도구 실행 메인 핸들러 (ToolContext 기반 신규 시그니처)."""
    tool_name = context.tool_name
    if tool_name == "freelance_search":
        return _handle_freelance(tool_input)
    if tool_name == "used_search":
        return _handle_used(tool_input)
    if tool_name == "search_shopping":
        query = tool_input.get("query")
        # site 는 이제 danawa(실동작) + naver(은퇴 안내) 둘뿐이다 — 중고 축은 2026-08-04 은퇴.
        site = tool_input.get("site", "danawa")
        display = tool_input.get("limit", tool_input.get("display", 5))

        if not query:
            return format_json({"success": False, "error": "검색어를 입력해주세요.", "items": []})

        try:
            if site == "naver":
                result = search_naver_shopping(query, display)
            else:
                result = asyncio.run(search_danawa_shopping_async(query, display))
                if site not in ("danawa", "naver"):
                    # 어휘 밖 값(옛 used/all 포함) — 빈손으로 돌려보내는 대신 가격비교 결과를
                    # 주고 중고 정본으로 안내한다(옛 스크래퍼는 조용히 0건이라 이보다 나빴다).
                    # ★enum 리터럴로만 분기한다 — 은퇴한 값을 코드에 박으면 enum-가드가
                    #   어휘 드리프트로 잡는다(그게 맞다: 죽은 축은 코드에도 남기지 않는다).
                    result["note"] = (
                        f"알 수 없는 site='{site}' — 다나와 가격비교 결과를 반환했습니다. "
                        "중고 매물은 [sense:used]{source: \"bunjang\"|\"danggeun\"|\"joongna\"|\"naver\"} 를 "
                        "쓰세요(옛 site=used/all 축은 2026-08-04 은퇴)."
                    )

            return format_json(result)
        except Exception as e:
            return format_json({"success": False, "error": f"오류 발생: {e}", "items": []})

    return format_json({"success": False, "error": f"알 수 없는 도구: {tool_name}"})
