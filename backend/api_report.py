"""api_report.py — 정기보고 발행 면 (공개 서빙, 요청 시 렌더).

공개 Worker(public-files 와 공유)가 /r/<slug>/ 요청을 이 엔드포인트로 끌어온다.
  · GET /report/page/{slug} — 그 보고서 폴더의 **최신 .md 하나**를 골라 HTML 로 렌더해 서빙.

발행 대상은 data/report_publish.json 의 reports[] (slug·title·folder·pattern·enabled). 정기보고 앱이
outputs/ai_trend_reports/*.md 로 쌓은 마크다운을, 클릭하면 항상 최신본이 보이도록 그때그때 렌더한다
(정기보고 도메인에 속한 얇은 발행 면 — 새 IBL 어휘 없음, 순수 콘텐츠 링크).

보안: X-Showcase-Secret(Worker 만 보유) + slug 일치 + 폴더가 프로젝트 안(경로 이탈 방어).
파일명이 ..._YYYY-MM-DD.md 라 사전순 정렬 = 시간순 → 맨 뒤가 최신.
"""

import os
import re
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import HTMLResponse

import report_html

router = APIRouter(prefix="/report", tags=["report"])

_ROOT = Path(__file__).resolve().parent.parent
_CONFIG = _ROOT / "data" / "report_publish.json"


def _read_env(name: str) -> str:
    v = os.environ.get(name, "")
    if v:
        return v
    envp = _ROOT / ".env"
    if envp.exists():
        try:
            for line in envp.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith(name + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass
    return ""


def _check_secret(secret_header: str) -> None:
    secret = _read_env("SHOWCASE_ORIGIN_SECRET")
    if not secret or secret_header != secret:
        raise HTTPException(status_code=403, detail="forbidden")


def _reports() -> list:
    try:
        return json.loads(_CONFIG.read_text(encoding="utf-8")).get("reports", [])
    except Exception:
        return []


def _report_by_slug(slug: str) -> dict:
    for r in _reports():
        if r.get("slug") == slug and r.get("enabled", True):
            return r
    return None


def _safe_folder(folder: str) -> Path:
    """설정의 folder 를 프로젝트 안 절대경로로 — 이탈 방어."""
    base = _ROOT.resolve()
    target = (base / folder).resolve()
    if target != base and base not in target.parents:
        raise HTTPException(status_code=404, detail="bad folder")
    return target


def _date_label(fname: str) -> str:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", fname)
    return m.group(1) if m else ""


@router.get("/page/{slug}")
async def page(slug: str, x_showcase_secret: str = Header(default="")):
    _check_secret(x_showcase_secret)
    rep = _report_by_slug(slug)
    if not rep:
        raise HTTPException(status_code=404, detail="no such report")
    folder = _safe_folder(rep.get("folder", ""))
    pattern = rep.get("pattern", "*.md")
    files = sorted(folder.glob(pattern)) if folder.is_dir() else []
    if not files:
        html = report_html.render_report(rep.get("title", "정기보고"),
                                         "아직 발행된 보고서가 없습니다.", "", 0)
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"})
    latest = files[-1]   # 파일명 사전순 = 시간순 → 최신
    md = latest.read_text(encoding="utf-8")
    html = report_html.render_report(rep.get("title", "정기보고"), md,
                                     _date_label(latest.name), len(files))
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})
