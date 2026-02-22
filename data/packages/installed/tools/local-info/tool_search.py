"""
tool_search.py - 사이트 검색 디스패처
=======================================
site 파라미터에 따라 적절한 사이트 모듈을 호출.
"""

import asyncio
import logging
import os
import sys
from typing import Dict, Any

logger = logging.getLogger(__name__)

# 현재 디렉토리를 path에 추가 (sites 모듈 임포트용)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)


def search(query: str, site: str = "naver_cafe",
           cafe_id: str = "osong1", display: int = 5) -> Dict[str, Any]:
    """
    사이트 검색 디스패처.

    Args:
        query: 검색 키워드
        site: 검색 사이트 (naver_cafe, naver_map)
        cafe_id: 네이버 카페 ID (naver_cafe 전용, 기본: osong1)
        display: 결과 수

    Returns:
        검색 결과 딕셔너리
    """
    if not query or not query.strip():
        return {"success": False, "error": "검색어를 입력해주세요."}

    query = query.strip()
    display = max(1, min(display, 10))

    if site == "naver_cafe":
        try:
            from sites.naver_cafe import search_cafe_async

            # 이벤트 루프가 이미 실행 중인지 확인
            try:
                loop = asyncio.get_running_loop()
                # 이미 실행 중이면 새 스레드에서 실행
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        search_cafe_async(query, cafe_id, display)
                    )
                    return future.result(timeout=30)
            except RuntimeError:
                # 실행 중인 루프 없음 → asyncio.run 사용
                return asyncio.run(
                    search_cafe_async(query, cafe_id, display)
                )
        except Exception as e:
            logger.error(f"[LocalInfo] 카페 검색 디스패치 실패: {e}")
            return {"success": False, "error": str(e), "site": "naver_cafe"}

    elif site == "naver_map":
        try:
            from sites.naver_map import search_local
            return search_local(query, display)
        except Exception as e:
            logger.error(f"[LocalInfo] 지도 검색 디스패치 실패: {e}")
            return {"success": False, "error": str(e), "site": "naver_map"}

    else:
        return {
            "success": False,
            "error": f"지원하지 않는 사이트입니다: {site}. "
                     f"사용 가능: naver_cafe, naver_map",
            "site": site
        }
