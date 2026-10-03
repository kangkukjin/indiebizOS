"""원격 런처 표면 조립 — React와 독립된 서버 생성 화면.

한국어 조각이 정본이다. frontend Vite의 uiCatalogPlugin이 같은 조각에서 UI 전용
번역 셸을 생성한다. 원문 지문이 다르면 낡은 실행 코드를 제공하지 않고 원문으로 돌아간다.
"""

import hashlib
import json
import logging
from pathlib import Path

from launcher_web_shell import LAUNCHER_SHELL_HTML
from launcher_web_app import LAUNCHER_APP_JS
from launcher_web_render import LAUNCHER_RENDER_JS

_LOG = logging.getLogger(__name__)


def launcher_html() -> str:
    """검증된 번역 셸 또는 한국어 원문. 네트워크·사용자 데이터 전송 없음."""
    source = LAUNCHER_SHELL_HTML + LAUNCHER_APP_JS + LAUNCHER_RENDER_JS
    return localized_html(source, "remote")


def localized_html(source: str, surface: str) -> str:
    """Serve a compiled UI only when it matches its source, including X-Ray."""
    root = Path(__file__).resolve().parents[2]
    candidates = (
        root / "frontend/i18n" / f"{surface}.json",
        root / "backend/static/ui_i18n" / f"{surface}.json",
    )
    for path in candidates:
        if not path.is_file():
            continue
        try:
            bundle = json.loads(path.read_text(encoding="utf-8"))
            expected = hashlib.sha256(source.encode("utf-8")).hexdigest()
            if isinstance(bundle, dict) and bundle.get("source_hash") == expected and isinstance(bundle.get("html"), str):
                return bundle["html"]
            _LOG.warning("UI catalog is stale: run the frontend dev server or build (%s)", path)
        except (OSError, ValueError, TypeError):
            _LOG.warning("UI catalog unavailable; using Korean UI (%s)", path)
    return source
