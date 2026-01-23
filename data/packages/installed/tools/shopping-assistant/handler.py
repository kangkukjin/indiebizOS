import os
import json
import requests
import re
import asyncio
from playwright.async_api import async_playwright

# 네이버 API 키 환경변수 로드
NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")

def clean_html(text):
    """HTML 태그 제거 및 특수 문자 처리"""
    if not text:
        return ""
    clean = re.sub('<[^<]+?>', '', text)
    return clean.replace('&quot;', '"').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')

def search_naver_shopping(query: str, display: int = 5):
    """네이버 쇼핑 검색 API 호출"""
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return {"error": "네이버 API 키가 설정되지 않았습니다."}

    url = "https://openapi.naver.com/v1/search/shop.json"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }
    params = {
        "query": query,
        "display": min(display, 10),
        "sort": "sim"
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code != 200:
            return {"error": f"네이버 API 오류: {response.status_code}"}

        data = response.json()
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

        return {
            "total": data.get("total", 0),
            "items": items
        }
    except Exception as e:
        return {"error": f"네이버 검색 중 오류: {str(e)}"}

async def search_danawa_shopping_async(query: str, display: int = 5):
    """다나와 검색 (Playwright 사용)"""
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            url = f"https://search.danawa.com/dsearch.php?query={query}"
            await page.goto(url, wait_until="domcontentloaded")

            # 상품 목록 대기
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

async def search_all_async(query: str, display: int = 5):
    """모든 사이트 검색 (네이버 + 다나와)"""
    naver_res = search_naver_shopping(query, display)
    danawa_res = await search_danawa_shopping_async(query, display)

    combined_items = []
    if "items" in naver_res: combined_items.extend(naver_res["items"])
    if "items" in danawa_res: combined_items.extend(danawa_res["items"])

    return {
        "total": len(combined_items),
        "items": combined_items
    }

def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    """도구 실행 메인 핸들러"""
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
            else:  # all
                result = asyncio.run(search_all_async(query, display))

            return json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"오류 발생: {str(e)}"

    return f"알 수 없는 도구: {tool_name}"
