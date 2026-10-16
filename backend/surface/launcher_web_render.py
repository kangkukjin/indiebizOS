"""화면 자산의 호환 진입점. 원본은 frontend/surfaces, 본문은 판본별로 읽는다."""
from surface_assets import read_asset, render_template


def _parts():
    LAUNCHER_RENDER_JS = render_template('remote/launcher_render_js.js', display_js=read_asset('remote/conversation-display.js') + read_asset('remote/display.js'))
    return {'LAUNCHER_RENDER_JS': LAUNCHER_RENDER_JS}


def __getattr__(name):
    if name not in ('LAUNCHER_RENDER_JS',):
        raise AttributeError(name)
    return _parts()[name]
