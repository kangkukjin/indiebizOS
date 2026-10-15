#!/usr/bin/env python3
"""회원 설치 앱의 공통 화면을 번들한다. 허브와 주인 UI를 배포에 싣지 않는다."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import boot_paths  # noqa: E402,F401
from member_shell import member_html

root = Path(__file__).resolve().parents[1]
html = member_html()
# Static CSP. All API access goes through the narrow preload adapter.
html = html.replace('<meta charset="utf-8">', '<meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'self\' \'unsafe-inline\'; style-src \'unsafe-inline\'; img-src data: blob:; media-src https: http:; frame-src about: blob:; connect-src \'none\'">', 1)
html = html.replace('</html>', '<script src="workspace.cjs"></script></html>')
(root / 'member-desktop/workspace.html').write_text(html)
print('회원 데스크톱 공통 화면 생성')
