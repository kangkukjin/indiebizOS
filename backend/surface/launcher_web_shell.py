"""화면 자산의 호환 진입점. 원본은 frontend/surfaces, 본문은 판본별로 읽는다."""
from surface_assets import read_asset


def _parts():
    SHELL_HEAD_HTML = read_asset('remote/shell_head_html.html')
    SHELL_SURFACES_HTML = read_asset('remote/shell_surfaces_html.html')
    SHELL_PANEL_AUTOPILOT_HTML = read_asset('remote/shell_panel_autopilot_html.html')
    SHELL_PANEL_MANUAL_HTML = read_asset('remote/shell_panel_manual_html.html')
    SHELL_PANEL_APP_HTML = read_asset('remote/shell_panel_app_html.html')
    SHELL_PANEL_FORAGE_HTML = read_asset('remote/shell_panel_forage_html.html')
    SHELL_PANEL_WAREHOUSE_HTML = read_asset('remote/shell_panel_warehouse_html.html')
    SHELL_TAIL_HTML = read_asset('remote/shell_tail_html.html')
    LAUNCHER_SHELL_HTML = SHELL_HEAD_HTML + SHELL_SURFACES_HTML + SHELL_PANEL_AUTOPILOT_HTML + SHELL_PANEL_MANUAL_HTML + SHELL_PANEL_APP_HTML + SHELL_PANEL_FORAGE_HTML + SHELL_PANEL_WAREHOUSE_HTML + SHELL_TAIL_HTML
    return {'SHELL_HEAD_HTML': SHELL_HEAD_HTML, 'SHELL_SURFACES_HTML': SHELL_SURFACES_HTML, 'SHELL_PANEL_AUTOPILOT_HTML': SHELL_PANEL_AUTOPILOT_HTML, 'SHELL_PANEL_MANUAL_HTML': SHELL_PANEL_MANUAL_HTML, 'SHELL_PANEL_APP_HTML': SHELL_PANEL_APP_HTML, 'SHELL_PANEL_FORAGE_HTML': SHELL_PANEL_FORAGE_HTML, 'SHELL_PANEL_WAREHOUSE_HTML': SHELL_PANEL_WAREHOUSE_HTML, 'SHELL_TAIL_HTML': SHELL_TAIL_HTML, 'LAUNCHER_SHELL_HTML': LAUNCHER_SHELL_HTML}


def __getattr__(name):
    if name not in ('SHELL_HEAD_HTML', 'SHELL_SURFACES_HTML', 'SHELL_PANEL_AUTOPILOT_HTML', 'SHELL_PANEL_MANUAL_HTML', 'SHELL_PANEL_APP_HTML', 'SHELL_PANEL_FORAGE_HTML', 'SHELL_PANEL_WAREHOUSE_HTML', 'SHELL_TAIL_HTML', 'LAUNCHER_SHELL_HTML'):
        raise AttributeError(name)
    return _parts()[name]
