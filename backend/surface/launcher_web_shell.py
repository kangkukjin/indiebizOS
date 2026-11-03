"""선택된 화면 판본을 명시적으로 조립한다. 동적 이름은 외부 import 호환용이다."""
from surface_assets import read_asset


SHELL_ASSETS = {
    "SHELL_HEAD_HTML": "remote/shell_head_html.html",
    "SHELL_SURFACES_HTML": "remote/shell_surfaces_html.html",
    "SHELL_PANEL_AUTOPILOT_HTML": "remote/shell_panel_autopilot_html.html",
    "SHELL_PANEL_MANUAL_HTML": "remote/shell_panel_manual_html.html",
    "SHELL_PANEL_APP_HTML": "remote/shell_panel_app_html.html",
    "SHELL_PANEL_FORAGE_HTML": "remote/shell_panel_forage_html.html",
    "SHELL_PANEL_WAREHOUSE_HTML": "remote/shell_panel_warehouse_html.html",
    "SHELL_TAIL_HTML": "remote/shell_tail_html.html",
}


def load_shell_html():
    return ''.join(read_asset(path) for path in SHELL_ASSETS.values())


def __getattr__(name):
    if name == 'LAUNCHER_SHELL_HTML':
        return load_shell_html()
    if name in SHELL_ASSETS:
        return read_asset(SHELL_ASSETS[name])
    raise AttributeError(name)
