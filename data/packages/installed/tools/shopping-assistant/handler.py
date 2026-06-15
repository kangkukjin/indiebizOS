"""
쇼핑 비교 검색 도구 (네이버 쇼핑 + 다나와 + 중고)

Phase 0 마이그레이션: common 유틸리티 사용
"""
import sys
import os
import json
import asyncio
# playwright 는 다나와·중고 스크래핑(브라우저 자동화)에만 필요 — 모듈 레벨이면 폰서 import 실패해
# 순수 API 인 네이버 쇼핑 검색(search_naver_shopping)까지 막힌다(study:arxiv 와 동일 함정).
# → 지연 import 로 내려, 폰선 네이버 검색이 로컬 작동하고 다나와/중고만 graceful 미지원.

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
    """네이버 쇼핑 검색 API 호출"""
    ok, err = check_api_key("naver")
    if not ok:
        return {"error": err}

    data = api_call(
        "naver", "/v1/search/shop.json",
        params={"query": query, "display": min(display, 10), "sort": "sim"},
    )

    if isinstance(data, dict) and "error" in data:
        return data

    raw_items = data.get("items", [])
    items = []
    for item in raw_items:
        items.append({
            "name": clean_html(item.get("title", "")),
            "price": item.get("lprice", "0"),
            "mall": item.get("mallName", "네이버"),
            "link": item.get("link", ""),
            "image": item.get("image", ""),
            "category": f"{item.get('category1', '')} > {item.get('category2', '')}",
            "site": "naver"
        })

    return {"total": data.get("total", 0), "items": items}


async def search_danawa_shopping_async(query: str, display: int = 5):
    """다나와 검색 (Playwright 사용)"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"total": 0, "items": [], "error": "다나와 검색은 이 기기에서 미지원(브라우저 자동화 — 맥 전용)"}
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
            return {"error": f"다나와 검색 중 오류: {str(e)}"}


async def search_used_items_async(query: str, display: int = 5):
    """중고 거래 사이트 검색 (중고나라, 번개장터)"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"total": 0, "items": [], "error": "중고 검색은 이 기기에서 미지원(브라우저 자동화 — 맥 전용)"}
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )

            items = []

            # 1. 중고나라
            try:
                page = await context.new_page()
                await page.goto(f"https://web.joongna.com/search?keyword={query}", wait_until="domcontentloaded", timeout=10000)
                await page.wait_for_selector("ul.grid", timeout=5000)
                jn_items = await page.query_selector_all("ul.grid > li")
                for el in jn_items[:display]:
                    name_el = await el.query_selector("span.title")
                    price_el = await el.query_selector("span.price")
                    link_el = await el.query_selector("a")
                    img_el = await el.query_selector("img")

                    if name_el and price_el:
                        items.append({
                            "name": (await name_el.inner_text()).strip(),
                            "price": (await price_el.inner_text()).replace("원", "").replace(",", "").strip(),
                            "mall": "중고나라",
                            "link": "https://web.joongna.com" + (await link_el.get_attribute("href") if link_el else ""),
                            "image": await img_el.get_attribute("src") if img_el else "",
                            "category": "중고",
                            "site": "joongna"
                        })
                await page.close()
            except:
                pass

            # 2. 번개장터
            try:
                page = await context.new_page()
                await page.goto(f"https://m.bunjang.co.kr/search/products?q={query}", wait_until="domcontentloaded", timeout=10000)
                await page.wait_for_selector("div[class*='sc-']", timeout=5000)
                bj_items = await page.query_selector_all("div[class*='ProductItem']")
                for el in bj_items[:display]:
                    name_el = await el.query_selector("div[class*='Name']")
                    price_el = await el.query_selector("div[class*='Price']")
                    link_el = await el.query_selector("a")
                    img_el = await el.query_selector("img")

                    if name_el and price_el:
                        items.append({
                            "name": (await name_el.inner_text()).strip(),
                            "price": (await price_el.inner_text()).replace(",", "").strip(),
                            "mall": "번개장터",
                            "link": "https://m.bunjang.co.kr" + (await link_el.get_attribute("href") if link_el else ""),
                            "image": await img_el.get_attribute("src") if img_el else "",
                            "category": "중고",
                            "site": "bunjang"
                        })
                await page.close()
            except:
                pass

            await browser.close()
            return {"total": len(items), "items": items[:display * 2]}
        except Exception as e:
            return {"error": f"중고 검색 중 오류: {str(e)}"}


async def search_all_async(query: str, display: int = 5):
    """모든 사이트 검색 (네이버 + 다나와 + 중고)"""
    naver_res = search_naver_shopping(query, display)
    danawa_res = await search_danawa_shopping_async(query, display)
    used_res = await search_used_items_async(query, display)

    combined_items = []
    if "items" in naver_res:
        combined_items.extend(naver_res["items"])
    if "items" in danawa_res:
        combined_items.extend(danawa_res["items"])
    if "items" in used_res:
        combined_items.extend(used_res["items"])

    return {"total": len(combined_items), "items": combined_items}


def execute(tool_input: dict, context) -> str:
    """도구 실행 메인 핸들러 (ToolContext 기반 신규 시그니처)."""
    tool_name = context.tool_name
    if tool_name == "search_shopping":
        query = tool_input.get("query")
        site = tool_input.get("site", "all")
        display = tool_input.get("display", 5)

        if not query:
            return "검색어를 입력해주세요."

        try:
            if site == "naver":
                result = search_naver_shopping(query, display)
            elif site == "danawa":
                result = asyncio.run(search_danawa_shopping_async(query, display))
            elif site == "used":
                result = asyncio.run(search_used_items_async(query, display))
            else:
                result = asyncio.run(search_all_async(query, display))

            # 레코드 통화 부착(비파괴) — items 목록을 records로. >> 파이프가 자동으로 흐름.
            if isinstance(result, dict) and isinstance(result.get("items"), list):
                result["records"] = _products_to_records(result["items"])

            return format_json(result)
        except Exception as e:
            return f"오류 발생: {str(e)}"

    return f"알 수 없는 도구: {tool_name}"
