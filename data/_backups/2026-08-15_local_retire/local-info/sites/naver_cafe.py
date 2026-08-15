"""
naver_cafe.py - 네이버 카페 검색 (Playwright)
=============================================
카페 홈 접속 → 검색 버튼 클릭 → 검색어 입력 → Enter → 결과 파싱.
로그인 불필요 (공개 검색 결과만 사용).
"""

import asyncio
import re
import logging
from urllib.parse import quote_plus
from typing import Dict, Any

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Mobile Safari/537.36"
)


async def search_cafe_async(query: str, cafe_id: str = "osong1",
                            display: int = 5) -> Dict[str, Any]:
    """
    네이버 카페에서 검색어로 게시글 검색.

    Args:
        query: 검색 키워드
        cafe_id: 네이버 카페 URL ID (기본: osong1 = 아이러브오송)
        display: 결과 수 (최대 10)
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {
            "success": False,
            "error": "Playwright가 설치되지 않았습니다. "
                     "pip install playwright && playwright install chromium",
            "site": "naver_cafe"
        }

    display = min(display, 10)
    browser = None

    try:
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=USER_AGENT,
            locale="ko-KR",
            viewport={"width": 412, "height": 915}
        )
        page = await context.new_page()

        # 1. 카페 홈 접속
        cafe_url = f"https://m.cafe.naver.com/{cafe_id}"
        await page.goto(cafe_url, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(2)

        # 2. 숫자 카페 ID 추출 (검색 URL에 필요)
        html = await page.content()
        numeric_ids = re.findall(r'/cafes/(\d+)', html)
        if not numeric_ids:
            return {
                "success": False,
                "error": f"카페 '{cafe_id}'의 숫자 ID를 찾을 수 없습니다. 카페 ID를 확인해주세요.",
                "site": "naver_cafe"
            }
        numeric_cafe_id = numeric_ids[0]

        # 3. 검색 버튼 클릭
        search_btn = await page.query_selector('[id=search], a[href*="search"]')
        if not search_btn:
            return {
                "success": False,
                "error": "카페 검색 버튼을 찾을 수 없습니다.",
                "site": "naver_cafe"
            }
        await search_btn.click()
        await asyncio.sleep(1)

        # 4. 검색어 입력 + Enter
        search_input = await page.query_selector('input[type="text"], input.input_box')
        if not search_input:
            return {
                "success": False,
                "error": "검색 입력창을 찾을 수 없습니다.",
                "site": "naver_cafe"
            }
        await search_input.fill(query)
        await search_input.press("Enter")
        await asyncio.sleep(3)

        # 5. 결과 파싱
        items = await page.query_selector_all(".article_box")

        if not items:
            body_text = await page.inner_text("body")
            if "검색결과가 없습니다" in body_text or "검색 결과가 없습니다" in body_text or "검색결과 0건" in body_text:
                return {
                    "success": True,
                    "query": query,
                    "site": "naver_cafe",
                    "cafe_id": cafe_id,
                    "count": 0,
                    "results": [],
                    "message": "검색 결과가 없습니다."
                }
            return {
                "success": False,
                "error": "검색 결과 구조를 인식할 수 없습니다.",
                "site": "naver_cafe",
                "debug_url": page.url
            }

        results = []
        for item in items[:display]:
            try:
                # 제목
                title_el = await item.query_selector("strong.title")
                title = (await title_el.inner_text()).strip() if title_el else ""

                # 미리보기
                txt_el = await item.query_selector("p.txt")
                snippet = (await txt_el.inner_text()).strip() if txt_el else ""
                snippet = snippet[:200]

                # 날짜
                date_el = await item.query_selector("span.date")
                date = (await date_el.inner_text()).strip() if date_el else ""

                # 작성자
                name_el = await item.query_selector("span.name")
                author = (await name_el.inner_text()).strip() if name_el else ""

                # 조회수
                views_el = await item.query_selector("span.no")
                views = (await views_el.inner_text()).strip() if views_el else ""

                # URL 구성 (카페 검색 결과는 SPA라 href 없음, 고유 식별은 제목+날짜로)
                url = f"https://m.cafe.naver.com/{cafe_id}"

                if title:
                    results.append({
                        "title": title,
                        "snippet": snippet,
                        "date": date,
                        "author": author,
                        "views": views,
                        "url": url,
                        "source": "naver_cafe",
                        "cafe_id": cafe_id
                    })
            except Exception as e:
                logger.debug(f"[LocalInfo] 항목 추출 실패: {e}")
                continue

        return {
            "success": True,
            "query": query,
            "site": "naver_cafe",
            "cafe_id": cafe_id,
            "count": len(results),
            "results": results
        }

    except Exception as e:
        logger.error(f"[LocalInfo] 네이버 카페 검색 실패: {e}")
        return {
            "success": False,
            "error": f"카페 검색 중 오류: {str(e)}",
            "site": "naver_cafe"
        }
    finally:
        if browser:
            try:
                await browser.close()
            except Exception:
                pass


def search_cafe(query: str, cafe_id: str = "osong1",
                display: int = 5) -> Dict[str, Any]:
    """동기 래퍼"""
    return asyncio.run(search_cafe_async(query, cafe_id, display))
