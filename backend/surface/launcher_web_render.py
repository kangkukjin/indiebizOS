"""선택된 화면 판본을 명시적으로 조립한다. 동적 이름은 외부 import 호환용이다."""
from surface_assets import read_asset


def load_render_js():
    from surface_assets import render_template
    return render_template('remote/launcher_render_js.js',
                           display_js=read_asset('remote/conversation-display.js') + read_asset('remote/display.js'))


def __getattr__(name):
    if name == 'LAUNCHER_RENDER_JS':
        return load_render_js()
    raise AttributeError(name)
