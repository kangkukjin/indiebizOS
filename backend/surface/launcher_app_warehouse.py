"""선택된 화면 판본을 명시적으로 조립한다. 동적 이름은 외부 import 호환용이다."""
from surface_assets import read_asset


ASSETS = {'LAUNCHER_WAREHOUSE_JS': 'remote/launcher_warehouse_js.js'}


def __getattr__(name):
    if name in ASSETS:
        return read_asset(ASSETS[name])
    raise AttributeError(name)
