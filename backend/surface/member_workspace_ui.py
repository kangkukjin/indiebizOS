"""회원 작업 공간 조립. 실행/표시 원본은 frontend/surfaces/member."""
import json
from member_app_frame import frame_html
from surface_assets import read_asset, render_template


def workspace_js(*, browser=False):
    frame = json.dumps(frame_html(), ensure_ascii=False).replace('</', '<\\/')
    return 'const MEMBER_FRAME_HTML=' + frame + ';\n' + render_template(
        'member/workspace.js', boot_name='workspaceBoot' if browser else 'memberBoot') + read_asset('member/display.js') + read_asset('member/frame-display-host.js')


def __getattr__(name):
    if name == 'WORKSPACE_STYLE':
        return read_asset('member/workspace_style.css')
    if name == 'SIDEBAR':
        return render_template('member/sidebar.html', artifacts='')
    if name == 'PANELS':
        return render_template('member/panels.html', export_tools=read_asset('member/native_export.html'), storage='', download='')
    raise AttributeError(name)
