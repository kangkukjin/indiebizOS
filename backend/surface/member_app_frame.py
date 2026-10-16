"""회원 앱은 원격 런처 렌더러 그대로, 로컬 승인 토큰이 없는 별도 프레임에서 그린다."""

from surface_assets import read_asset, asset_snapshot


@asset_snapshot()
def frame_html(display=True):
    from surface_assets import render_template
    LAUNCHER_COMMON_JS = '<script>\n' + read_asset('shared/launcher_common_js.js')
    from launcher_render_core import LAUNCHER_CORE_JS
    from launcher_app_appmode import LAUNCHER_APPMODE_HEAD_JS, LAUNCHER_APPMODE_REST_JS
    LAUNCHER_RENDER_JS = render_template('remote/launcher_render_js.js', display_js=read_asset('remote/display.js'))
    head = read_asset('member/head.html')
    bridge = read_asset('member/bridge.js')
    bridge += read_asset('static/member_app_requests.js')
    html = head + LAUNCHER_COMMON_JS + LAUNCHER_CORE_JS + LAUNCHER_APPMODE_HEAD_JS + LAUNCHER_APPMODE_REST_JS + LAUNCHER_RENDER_JS.split('</script>')[0] + bridge + '</script><!--INDIE_DISPLAY--></html>'

    if not display:
        return html
    import json
    descriptor = frame_display(html)
    script = (read_asset('shared/display-host.js') + '\nIndieDisplay.start('
              + json.dumps(descriptor, ensure_ascii=False).replace('<', '\\u003c')
              + ',function(){if(!CUR.inst)renderAppHome()});' + read_asset('member/frame-display-bridge.js'))
    return html.replace('<!--INDIE_DISPLAY-->', '<script>' + script + '</script>')


def frame_display(html=None):
    from surface_display import describe
    return describe(html if html is not None else frame_html(False), 'frame',
                    read_asset('remote/display.js'), '')
