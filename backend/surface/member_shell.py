"""회원 셸의 명시적 조립. HTML 본문·문구를 검색해서 바꾸지 않는다."""
from surface_assets import asset_snapshot, read_asset, render_template

BROWSER_ASSETS = ('member_browser_store.js', 'member_browser_files.js',
                  'member_browser_runtime.js', 'member_browser_boot.js')
DESKTOP_CSP = ("default-src 'none'; script-src 'self' 'unsafe-inline'; "
               "style-src 'unsafe-inline'; img-src data: blob:; media-src https: http:; "
               "frame-src about: blob:; connect-src 'none'")


def member_html(*, browser=False, desktop=False, display=True):
    if browser and desktop:
        raise ValueError('회원 표면 어댑터는 하나만 선택해야 합니다')
    with asset_snapshot():
        from launcher_app_common import LAUNCHER_COMMON_JS
        from member_workspace_ui import workspace_js
        browser_js = ('\n'.join(read_asset('static/' + name) for name in BROWSER_ASSETS)
                      .replace('</script', '<\\/script') if browser else '')
        sidebar = render_template('member/sidebar.html', artifacts=read_asset('member/browser_artifacts.html') if browser else '')
        panels = render_template('member/panels.html',
            export_tools=read_asset('member/browser_tools.html' if browser else 'member/native_export.html'),
            storage=read_asset('member/browser_storage.html') if browser else '',
            download=read_asset('member/browser_download.html') if browser else '')
        host_js = render_template('member/host.js',
            approval_hidden=",'body_session'" if browser else '',
            approval_ops="javascript:'브라우저 계산'," if browser else '')
        def compose(display_script):
            return render_template('member/shell.html',
                meta=f'<meta http-equiv="Content-Security-Policy" content="{DESKTOP_CSP}">' if desktop else '',
                workspace_style=read_asset('member/workspace_style.css'),
                browser_style=read_asset('member/browser.css') if browser else '',
                login=read_asset('member/browser_login.html') if browser else '',
                main_attrs=' id="memberWorkspace" hidden' if browser else '',
                sidebar=sidebar, panels=panels, common_js=LAUNCHER_COMMON_JS,
                host_js=host_js, workspace_js=workspace_js(browser=browser), browser_js=browser_js,
                desktop_script='<script src="workspace.cjs"></script>' if desktop else '', display_script=display_script)

        html = compose('')
        if not display:
            return html
        from surface_display import member_display, display_bootstrap
        descriptor = member_display(html, 'browser' if browser else 'desktop' if desktop else 'member')
        return compose('<script>' + display_bootstrap(descriptor, '/m/app' if browser else None) + '</script><!--INDIE_ACTIVE_DISPLAY-->')
