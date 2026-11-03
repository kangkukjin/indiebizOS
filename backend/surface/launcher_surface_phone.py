"""폰네이티브 표면 조립 — 독립된 몸의 자기 UI (자율주행·조종실·앱 3탭).

표면 정의(어떤 탭이 존재하는가=정체)의 거처 — 원격런처(launcher_surface_remote)와 짝.
원격런처는 PC 몸의 얼굴·리모컨이고, 이 표면은 폰 몸 자신의 것 — 라이브러리
(launcher_web_shell/app 조각·launcher_web_render = 기질)는 공유하되 정체는 여기서 조립한다.
2026-07-22 표면 분리 2단계 — docs/SURFACE_SPLIT_HANDOFF.md.

빠진 것(의도):
- 공유창고: 창고=숙주(맥) 몸의 살림+네트워크 얼굴 — 폰에서 창고를 만지려면 원격런처(기능 완비).
- 포식(검색브라우저): 맥 디스크 중심 — 패널도, 홈 그리드 타일도 없다(PHONE_APPHOME_JS).
  launcher_web_render 의 fg* 함수들은 공유 기질에 실려 오지만 진입점이 없어 잠든 코드다.
남은 IS_PHONE 런타임 분기(공통 조각의 부트·클립보드 경로·자율주행 스위치 숨김)는 폰 config
(host=phone-local)로 스스로 참이 되어 그대로 작동한다 — 정적 흡수는 후속 후보.
"""

from surface_assets import read_asset, asset_snapshot

@asset_snapshot()
def phone_html(*, display=True) -> str:
    from launcher_app_common import load_common_js
    from launcher_render_core import load_core_js
    from launcher_app_autopilot import load_autopilot_js
    from launcher_web_render import load_render_js
    PHONE_SURFACES_HTML = read_asset('phone/phone_surfaces_html.html')
    PHONE_SETSURFACE_JS = read_asset('phone/phone_setsurface_js.js')
    PHONE_APPHOME_JS = read_asset('phone/phone_apphome_js.js')
    """폰네이티브 표면 HTML — 3탭 마크업 + 3탭 JS 조립."""
    html = (
        read_asset('remote/shell_head_html.html')
        + PHONE_SURFACES_HTML
        + read_asset('remote/shell_panel_autopilot_html.html')
        + read_asset('remote/shell_panel_manual_html.html')
        + read_asset('remote/shell_panel_app_html.html')
        + read_asset('remote/shell_tail_html.html')
        + load_common_js()
        + load_core_js()   # 공용 렌더 코어 — 원격런처와 같은 자리(load_common_js() 바로 뒤)
        + PHONE_SETSURFACE_JS
        + load_autopilot_js()
        + read_asset('remote/launcher_manual_js.js')
        + read_asset('remote/launcher_appmode_head_js.js')
        + PHONE_APPHOME_JS
        + read_asset('remote/launcher_appmode_rest_js.js')
        + load_render_js()
    )
    if not display:
        return html
    from surface_display import launcher_display, display_bootstrap
    descriptor = launcher_display(html, 'phone')
    return html.replace('<!--INDIE_DISPLAY-->', '<script>' + display_bootstrap(descriptor) + '</script><!--INDIE_ACTIVE_DISPLAY-->', 1)


def __getattr__(name):
    if name not in ('PHONE_SURFACES_HTML', 'PHONE_SETSURFACE_JS', 'PHONE_APPHOME_JS'):
        raise AttributeError(name)
    PHONE_SURFACES_HTML = read_asset('phone/phone_surfaces_html.html')
    PHONE_SETSURFACE_JS = read_asset('phone/phone_setsurface_js.js')
    PHONE_APPHOME_JS = read_asset('phone/phone_apphome_js.js')
    return {'PHONE_SURFACES_HTML': PHONE_SURFACES_HTML, 'PHONE_SETSURFACE_JS': PHONE_SETSURFACE_JS, 'PHONE_APPHOME_JS': PHONE_APPHOME_JS}[name]
