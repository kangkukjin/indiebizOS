"""
html_utils.py - HTML 파싱 유틸리티

여러 패키지에 중복 존재하던 clean_html 등의 함수를 통합합니다.

사용법:
    from common.html_utils import clean_html, extract_text
"""

import re
from html import unescape
from typing import Optional


def clean_html(text: Optional[str]) -> str:
    """
    HTML 태그 제거 및 엔티티 디코딩

    Args:
        text: HTML을 포함할 수 있는 문자열

    Returns:
        태그가 제거된 텍스트

    기존 중복:
        - location-services/handler.py: re.sub('<[^<]+?>', '', text)
        - shopping-assistant/handler.py: re.sub + replace(&quot; 등)
        - web/handler.py: re.sub + unescape
    """
    if not text:
        return ""
    # HTML 태그 제거
    clean = re.sub(r'<[^>]+>', '', text)
    # HTML 엔티티 디코딩 (&amp; → &, &lt; → < 등)
    clean = unescape(clean)
    # 연속 공백 정리
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean


def extract_text(html: Optional[str], max_length: int = 0) -> str:
    """
    HTML에서 텍스트만 추출 (clean_html + 길이 제한)

    Args:
        html: HTML 문자열
        max_length: 최대 길이 (0이면 제한 없음)

    Returns:
        추출된 텍스트
    """
    text = clean_html(html)
    if max_length > 0 and len(text) > max_length:
        return text[:max_length] + "..."
    return text
