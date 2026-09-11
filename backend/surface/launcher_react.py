"""데스크톱과 같은 React 빌드를 원격 셸로 서빙한다. 폰/포털 HTML은 별도 계약이다."""
from pathlib import Path
import re

from fastapi import HTTPException
from fastapi.responses import FileResponse


def bundle_root() -> Path | None:
    """개발 저장소 또는 asar:false 배포의 읽기 전용 앱 자산. userData는 실행 코드가 아니다."""
    resources = Path(__file__).resolve().parents[2]
    for candidate in (resources / "frontend" / "dist", resources / "app" / "dist"):
        if (candidate / "index.html").is_file():
            return candidate.resolve()
    return None


def react_shell() -> str | None:
    root = bundle_root()
    if root is None:
        return None
    try:
        html = (root / "index.html").read_text(encoding="utf-8")
    except OSError:
        return None
    # 오래된 데스크톱 번들을 인증 셸인 것처럼 서빙하지 않는다.
    if '<meta name="indiebiz-remote-shell" content="1"' not in html:
        return None
    scripts = re.findall(r'<script\b[^>]*\bsrc="([^"]+)"', html)
    if not scripts or any(not (root / src.removeprefix("./")).is_file() for src in scripts):
        return None
    html = html.replace('<html ', '<html data-indiebiz-surface="remote" ', 1)
    return html.replace('<head>', '<head>\n'
                        '<base href="/launcher/ui/">\n'
                        '<link rel="manifest" href="/launcher/manifest.webmanifest">\n'
                        '<link rel="icon" href="/launcher/icon-192.png">\n'
                        '<link rel="apple-touch-icon" href="/launcher/apple-touch-icon.png">\n'
                        '<meta name="theme-color" content="#D97706">', 1)


def serve_asset(path: str) -> FileResponse:
    """정적 번들 안의 허용 형식만. 경로 탈출·심볼릭 링크·소스맵/설정 노출을 차단한다."""
    root = bundle_root()
    allowed = {".js", ".css", ".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif", ".woff", ".woff2", ".ico"}
    if root is None:
        raise HTTPException(404, "정적 번들이 없습니다")
    target = (root / path).resolve()
    if not target.is_relative_to(root) or target.suffix.lower() not in allowed or not target.is_file():  # vj-ok: 정적 파일 확장자
        raise HTTPException(404, "자산이 없습니다")
    return FileResponse(target, headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"})
