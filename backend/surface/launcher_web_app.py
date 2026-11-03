"""선택된 화면 판본을 명시적으로 조립한다. 동적 이름은 외부 import 호환용이다."""
from surface_assets import read_asset


def load_app_js():
    from launcher_app_common import load_common_js
    from launcher_render_core import load_core_js
    from launcher_app_autopilot import load_autopilot_js
    return (load_common_js() + load_core_js() + read_asset('shared/launcher_setsurface_js.js')
            + read_asset('remote/launcher_warehouse_js.js') + load_autopilot_js()
            + read_asset('remote/launcher_manual_js.js')
            + read_asset('remote/launcher_appmode_head_js.js')
            + read_asset('remote/launcher_apphome_js.js')
            + read_asset('remote/launcher_appmode_rest_js.js'))


def __getattr__(name):
    if name == 'LAUNCHER_APP_JS':
        return load_app_js()
    raise AttributeError(name)
