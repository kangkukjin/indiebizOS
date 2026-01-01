"""
ai/imports.py - 동적 도구 임포트
"""

# 동적 도구 선택 시스템
try:
    from tool_selector import (
        select_my_tools,
        list_available_tools,
        get_base_tools,
        get_extended_tools
    )
    DYNAMIC_TOOL_SELECTOR_AVAILABLE = True
    print("✓ 동적 도구 선택 시스템 로드됨")
except ImportError as e:
    DYNAMIC_TOOL_SELECTOR_AVAILABLE = False
    select_my_tools = None
    list_available_tools = None
    get_base_tools = None
    get_extended_tools = None
    print(f"⚠️  동적 도구 선택 시스템 로드 실패: {e}")

# YouTube 도구
try:
    from tool_youtube import (
        download_youtube_music,
        get_youtube_info,
        get_youtube_transcript,
        list_available_transcripts,
        summarize_youtube
    )
except ImportError:
    download_youtube_music = None
    get_youtube_info = None
    get_youtube_transcript = None
    list_available_transcripts = None
    summarize_youtube = None

# 블로그 RAG 도구
try:
    from tool_blog_rag import search_blog, get_post_content, search_semantic
except ImportError:
    search_blog = None
    get_post_content = None
    search_semantic = None

# 신문 생성 도구
try:
    from tool_newspaper import generate_newspaper
except ImportError:
    generate_newspaper = None

# 잡지 생성 도구
try:
    from tool_magazine import generate_magazine
except ImportError:
    generate_magazine = None

# 웹 크롤링 도구
try:
    from tool_webcrawl import use_tool as use_webcrawl_tool
except ImportError:
    use_webcrawl_tool = None

# 웹 검색 도구
try:
    from tool_ddgs_search import use_tool as use_websearch_tool
except ImportError:
    use_websearch_tool = None

# Google News 검색 도구
try:
    from tool_google_news import use_tool as use_googlenews_tool
except ImportError:
    use_googlenews_tool = None
