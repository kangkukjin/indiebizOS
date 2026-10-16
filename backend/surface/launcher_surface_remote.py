"""원격 런처 표면 조립 — React와 독립된 서버 생성 화면.

한국어 조각이 정본이다. frontend Vite의 uiCatalogPlugin이 같은 조각에서 UI 전용
번역 셸을 생성한다. 원문 지문이 다르면 낡은 실행 코드를 제공하지 않고 원문으로 돌아간다.
"""

import hashlib
import json

from surface_assets import asset_snapshot, read_asset



def launcher_html(*, display=True) -> str:
    """검증된 번역 셸 또는 한국어 원문. 네트워크·사용자 데이터 전송 없음."""
    with asset_snapshot():
        from launcher_web_shell import LAUNCHER_SHELL_HTML
        from launcher_web_app import LAUNCHER_APP_JS
        from launcher_web_render import LAUNCHER_RENDER_JS
        source = LAUNCHER_SHELL_HTML + LAUNCHER_APP_JS + LAUNCHER_RENDER_JS
        html = localized_html(source, "remote")
        if not display:
            return html
        from surface_display import launcher_display, display_bootstrap
        descriptor = launcher_display(html, 'remote', raw_html=source,
                                      rendered_code=localized_display(source), messages=display_messages(source))
        return html.replace('<!--INDIE_DISPLAY-->', '<script>' + display_bootstrap(descriptor, '/launcher/app') + '</script><!--INDIE_ACTIVE_DISPLAY-->', 1)


def localized_html(source: str, surface: str) -> str:
    """Serve a compiled UI only when it matches its source, including X-Ray."""
    try:
        bundle = json.loads(read_asset('i18n/' + surface + '.json'))
        if bundle.get('source_hash') == hashlib.sha256(source.encode()).hexdigest():
            return bundle['html']
    except (KeyError, OSError, ValueError, TypeError):
        pass
    return source


def localized_display(source):
    try:
        bundle = json.loads(read_asset('i18n/remote.json'))
        if bundle.get('source_hash') == hashlib.sha256(source.encode()).hexdigest():
            return bundle.get('display_code')
    except (KeyError, OSError, ValueError, TypeError):
        pass
    return None


def display_messages(source):
    try:
        bundle = json.loads(read_asset('i18n/remote.json'))
        if bundle.get('source_hash') == hashlib.sha256(source.encode()).hexdigest():
            return bundle.get('display_messages', {})
    except (KeyError, OSError, ValueError, TypeError):
        pass
    return {}


@asset_snapshot()
def remote_display():
    from launcher_web_shell import LAUNCHER_SHELL_HTML
    from launcher_web_app import LAUNCHER_APP_JS
    from launcher_web_render import LAUNCHER_RENDER_JS
    from surface_display import launcher_display
    with asset_snapshot():
        source = LAUNCHER_SHELL_HTML + LAUNCHER_APP_JS + LAUNCHER_RENDER_JS
        return launcher_display(localized_html(source, 'remote'), 'remote', raw_html=source,
                                rendered_code=localized_display(source), messages=display_messages(source))
