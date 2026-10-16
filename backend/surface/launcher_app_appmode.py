"""화면 자산의 호환 진입점. 원본은 frontend/surfaces, 본문은 판본별로 읽는다."""
from surface_assets import read_asset


def _parts():
    LAUNCHER_APPMODE_HEAD_JS = read_asset('remote/launcher_appmode_head_js.js')
    LAUNCHER_APPHOME_JS = read_asset('remote/launcher_apphome_js.js')
    LAUNCHER_APPMODE_REST_JS = read_asset('remote/launcher_appmode_rest_js.js')
    return {'LAUNCHER_APPMODE_HEAD_JS': LAUNCHER_APPMODE_HEAD_JS, 'LAUNCHER_APPHOME_JS': LAUNCHER_APPHOME_JS, 'LAUNCHER_APPMODE_REST_JS': LAUNCHER_APPMODE_REST_JS}


def __getattr__(name):
    if name not in ('LAUNCHER_APPMODE_HEAD_JS', 'LAUNCHER_APPHOME_JS', 'LAUNCHER_APPMODE_REST_JS'):
        raise AttributeError(name)
    return _parts()[name]
