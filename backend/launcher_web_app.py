"""원격 런처 웹앱 — 앱 셸 JS 조립(<script> 시작 포함).

2026-07-22 표면 분리 1단계(모듈화): 2026-07-18 에 api_launcher_web 에서 verbatim 이동했던
단일 문자열을 탭별 모듈(launcher_app_common/autopilot/manual/appmode/warehouse)로 분해.
이 파일은 조각들을 원래 순서 그대로 이어붙인 조립 지점 — LAUNCHER_APP_JS 이름·바이트 불변.
조각=기질(라이브러리). 어떤 탭이 존재하는가(정체)는 표면 조립(launcher_surface_*)이 정한다.
"""

from launcher_app_common import LAUNCHER_COMMON_JS, LAUNCHER_SETSURFACE_JS
from launcher_app_warehouse import LAUNCHER_WAREHOUSE_JS
from launcher_app_autopilot import LAUNCHER_AUTOPILOT_JS
from launcher_app_manual import LAUNCHER_MANUAL_JS
from launcher_app_appmode import (
    LAUNCHER_APPMODE_HEAD_JS,
    LAUNCHER_APPHOME_JS,
    LAUNCHER_APPMODE_REST_JS,
)

LAUNCHER_APP_JS = (
    LAUNCHER_COMMON_JS
    + LAUNCHER_SETSURFACE_JS
    + LAUNCHER_WAREHOUSE_JS
    + LAUNCHER_AUTOPILOT_JS
    + LAUNCHER_MANUAL_JS
    + LAUNCHER_APPMODE_HEAD_JS
    + LAUNCHER_APPHOME_JS
    + LAUNCHER_APPMODE_REST_JS
)
