"""선택된 화면 판본을 명시적으로 조립한다. 동적 이름은 외부 import 호환용이다."""
from surface_assets import read_asset


def load_common_js():
    from launcher_render_core import load_conversation_js
    return '<script>\n' + load_conversation_js() + read_asset('shared/launcher_common_js.js')


def __getattr__(name):
    if name == 'LAUNCHER_COMMON_JS':
        return load_common_js()
    if name == 'LAUNCHER_SETSURFACE_JS':
        return read_asset('shared/launcher_setsurface_js.js')
    raise AttributeError(name)
