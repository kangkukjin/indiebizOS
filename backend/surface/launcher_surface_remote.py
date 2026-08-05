"""원격 런처 표면 조립 — PC(허브) 몸의 얼굴·리모컨. 5탭 전부.

표면 정의(어떤 탭이 존재하는가=정체)의 거처 — 폰네이티브(launcher_surface_phone)와 짝.
원격런처는 PC 의 일부(맥/윈도우 허브의 얼굴)라 창고·포식을 포함한 전판이고,
폰네이티브는 독립된 다른 시스템이라 자기 표면을 따로 조립한다.
라이브러리(launcher_web_shell/app/render = 기질)는 공유, 정체는 몸별 파일.
2026-07-22 표면 분리 2단계 — docs/SURFACE_SPLIT_HANDOFF.md.
"""

from launcher_web_shell import LAUNCHER_SHELL_HTML
from launcher_web_app import LAUNCHER_APP_JS
from launcher_web_render import LAUNCHER_RENDER_JS


def launcher_html() -> str:
    """원격런처 HTML — 5탭 전판 (바이트: 종전 get_launcher_webapp_html 과 동일)."""
    return LAUNCHER_SHELL_HTML + LAUNCHER_APP_JS + LAUNCHER_RENDER_JS
