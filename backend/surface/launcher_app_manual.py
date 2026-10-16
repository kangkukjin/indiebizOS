"""화면 자산의 호환 진입점. 원본은 frontend/surfaces, 본문은 판본별로 읽는다."""
from surface_assets import read_asset


def _parts():
    LAUNCHER_MANUAL_JS = read_asset('remote/launcher_manual_js.js')
    return {'LAUNCHER_MANUAL_JS': LAUNCHER_MANUAL_JS}


def __getattr__(name):
    if name not in ('LAUNCHER_MANUAL_JS',):
        raise AttributeError(name)
    return _parts()[name]
