"""설치 없는 회원 웹앱. 공통 셸의 브라우저 어댑터를 선택한다."""
from member_shell import BROWSER_ASSETS as ASSETS, member_html


def browser_html():
    return member_html(browser=True)
