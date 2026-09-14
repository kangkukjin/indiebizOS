"""회원의 기본 진입점은 설치 없는 브라우저 작업 공간이다."""

def entry_html():
    from member_browser import browser_html
    return browser_html()
