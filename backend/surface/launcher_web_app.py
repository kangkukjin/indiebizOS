"""화면 자산의 호환 진입점. 원본은 frontend/surfaces, 본문은 판본별로 읽는다."""
from surface_assets import read_asset


def _parts():
    from launcher_app_common import LAUNCHER_COMMON_JS, LAUNCHER_SETSURFACE_JS
    from launcher_render_core import LAUNCHER_CORE_JS
    from launcher_app_warehouse import LAUNCHER_WAREHOUSE_JS
    from launcher_app_autopilot import LAUNCHER_AUTOPILOT_JS
    from launcher_app_manual import LAUNCHER_MANUAL_JS
    from launcher_app_appmode import LAUNCHER_APPMODE_HEAD_JS, LAUNCHER_APPHOME_JS, LAUNCHER_APPMODE_REST_JS
    LAUNCHER_APP_JS = LAUNCHER_COMMON_JS + LAUNCHER_CORE_JS + LAUNCHER_SETSURFACE_JS + LAUNCHER_WAREHOUSE_JS + LAUNCHER_AUTOPILOT_JS + LAUNCHER_MANUAL_JS + LAUNCHER_APPMODE_HEAD_JS + LAUNCHER_APPHOME_JS + LAUNCHER_APPMODE_REST_JS
    return {'LAUNCHER_APP_JS': LAUNCHER_APP_JS}


def __getattr__(name):
    if name not in ('LAUNCHER_APP_JS',):
        raise AttributeError(name)
    return _parts()[name]
