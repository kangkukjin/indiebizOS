"""화면 자산의 호환 진입점. 원본은 frontend/surfaces, 본문은 판본별로 읽는다."""
from surface_assets import read_asset


def _parts():
    LAUNCHER_SESSIONS_JS = read_asset('remote/launcher_sessions_js.js')
    return {'LAUNCHER_SESSIONS_JS': LAUNCHER_SESSIONS_JS}


def __getattr__(name):
    if name not in ('LAUNCHER_SESSIONS_JS',):
        raise AttributeError(name)
    return _parts()[name]
