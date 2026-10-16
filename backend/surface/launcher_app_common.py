"""화면 자산의 호환 진입점. 원본은 frontend/surfaces, 본문은 판본별로 읽는다."""
from surface_assets import read_asset


def _parts():
    from launcher_render_core import load_conversation_js
    LAUNCHER_COMMON_JS = '<script>\n' + load_conversation_js() + read_asset('shared/launcher_common_js.js')
    LAUNCHER_SETSURFACE_JS = read_asset('shared/launcher_setsurface_js.js')
    return {'LAUNCHER_COMMON_JS': LAUNCHER_COMMON_JS, 'LAUNCHER_SETSURFACE_JS': LAUNCHER_SETSURFACE_JS}


def __getattr__(name):
    if name not in ('LAUNCHER_COMMON_JS', 'LAUNCHER_SETSURFACE_JS'):
        raise AttributeError(name)
    return _parts()[name]
