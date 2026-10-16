#!/usr/bin/env python3
"""회원 설치 앱의 공통 화면을 번들한다. 허브와 주인 UI를 배포에 싣지 않는다."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import boot_paths  # noqa: E402,F401
from member_shell import member_html
from surface_assets import source_build
from surface_display import member_display
import json

root = Path(__file__).resolve().parents[1]
with source_build():
    html = member_html(desktop=True)
    display = member_display(member_html(desktop=True, display=False), 'desktop')
(root / 'member-desktop/workspace.html').write_text(html)
print('회원 데스크톱 공통 화면 생성')
(root / 'member-desktop/display.json').write_text(json.dumps(display, ensure_ascii=False))
