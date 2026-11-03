"""선택된 화면 판본을 명시적으로 조립한다. 동적 이름은 외부 import 호환용이다."""
from surface_assets import read_asset


def load_autopilot_js():
    return read_asset('remote/launcher_autopilot_js.js') + read_asset('remote/launcher_sessions_js.js')


def __getattr__(name):
    if name == 'LAUNCHER_AUTOPILOT_JS':
        return load_autopilot_js()
    raise AttributeError(name)
