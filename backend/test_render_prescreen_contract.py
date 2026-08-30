"""검수 비용 계층화 계약 배터리 — 0층 기계 관측 + critic 무비용 단락 (2026-08-27).

INSPECTION_COST_TIER_HANDOFF: render 행의 prescreen(관측 사실 문자열, ""=깨끗)과
critic 의 prescreen 단락(차 있으면 비전 호출 0회, tier=prescreen 실패 verdict)이 계약.
핵심 보증 둘: ① 깨끗한 화면에 오탐이 없다(빈 문자열) — 오탐은 유료 심사를 공짜 실패로
바꿔치기하는 침묵 ② 단락은 API 키 없이 돈다 — 키 검사 앞이 아니면 계층화가 아니라 장식.

★이 배터리는 backend/ 밖(data/packages)의 파일을 읽는다 — 라이브 트리에서 돌릴 것.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401 — 층 디렉토리 등재
from base.runtime_utils import setup_playwright_browsers_path

setup_playwright_browsers_path()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MP = os.path.join(ROOT, "data/packages/installed/tools/media_producer")


def _browser_ready() -> str:
    """실제로 한 장 구울 수 있는 몸인가 — 아니면 못 구는 **이유**를 돌려준다.

    ★모듈 유무로는 모자란다(2026-08-30): playwright 가 깔려도 브라우저 바이너리를 안 받은
      몸이 있다. 여기서 스킵되는 세 칸은 CI 의 playwright-render job(브라우저를 실제로 받는
      유일한 몸)에서 돈다 — 스킵이 침묵이 되지 않도록 배치를 그쪽에 걸어 두었다.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        return "playwright 미설치 — requirements-tools.txt 티어"
    try:
        with sync_playwright() as pw:
            pw.chromium.launch().close()
    except Exception as e:
        return f"chromium 미가용: {type(e).__name__}"
    return ""


_NO_BROWSER = _browser_ready()
needs_browser = pytest.mark.skipif(bool(_NO_BROWSER),
                                   reason=f"실 브라우저가 필요한 계약 — {_NO_BROWSER}")


def _load(fname, name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, os.path.join(MP, fname))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ra():
    return _load("render_artifact.py", "mp_ra_prescreen_test")


@pytest.fixture(scope="module")
def gv():
    return _load("vision_read.py", "mp_gv_prescreen_test")


# ── 0층 관측: render 행의 prescreen ───────────────────────────────


@needs_browser
def test_html_console_and_pageerror_and_reqfail_captured(ra, tmp_path):
    """콘솔 오류·페이지 예외·요청 실패가 관측 사실로 행에 실린다."""
    p = tmp_path / "broken.html"
    p.write_text(
        "<html><body><h1>제목</h1>"
        "<img src='없는파일.png'>"
        "<script>console.error('의도된 콘솔 오류'); throw new Error('의도된 예외');</script>"
        "</body></html>", encoding="utf-8")
    result = json.loads(ra.render_op_html({"path": str(p)}, output_base=str(tmp_path)))
    assert result.get("items"), f"렌더 실패: {result}"
    pre = result["items"][0]["prescreen"]
    assert "콘솔 오류 2건" in pre          # 이미지 로드 실패 + 의도된 console.error
    assert "페이지 예외" in pre and "의도된 예외" in pre
    assert "요청 실패" in pre
    assert result["prescreen_flagged"] == 1


@needs_browser
def test_html_clean_page_has_empty_prescreen(ra, tmp_path):
    """★오탐 금지: 깨끗한 페이지의 prescreen 은 빈 문자열 — 아니면 유료 심사가 통째로 우회된다."""
    p = tmp_path / "clean.html"
    p.write_text("<html><body style='font-size:40px;padding:60px'>"
                 "<h1>정상 페이지</h1><p>본문 내용이 충분히 그려진다.</p></body></html>",
                 encoding="utf-8")
    result = json.loads(ra.render_op_html({"path": str(p)}, output_base=str(tmp_path)))
    assert result["items"][0]["prescreen"] == ""
    assert result["prescreen_flagged"] == 0


@needs_browser
def test_html_blank_page_flagged(ra, tmp_path):
    """아무것도 안 그려진 렌더 = 빈 화면 사실 (잉크율 관측)."""
    p = tmp_path / "blank.html"
    p.write_text("<html><body></body></html>", encoding="utf-8")
    result = json.loads(ra.render_op_html({"path": str(p)}, output_base=str(tmp_path)))
    assert "빈 화면" in result["items"][0]["prescreen"]


def test_xlsx_formula_error_marker_flagged(ra, tmp_path):
    """xlsx 0층: 재계산 PDF 텍스트의 #DIV/0! 표식 — sheet.yaml forbidden 의 무비용 선행판."""
    if not ra._find_soffice():
        pytest.skip("LibreOffice(soffice) 없음")
    import openpyxl
    src = tmp_path / "err.xlsx"
    wb = openpyxl.Workbook()
    wb.active["A1"] = "=1/0"
    wb.save(str(src))
    result = json.loads(ra.render_op_xlsx({"path": str(src)}, output_base=str(tmp_path)))
    assert result.get("items"), f"변환 실패: {result}"
    assert "#DIV/0!" in result["items"][0]["prescreen"]
    assert result["prescreen_flagged"] >= 1


# ── 1층 단락: critic 의 prescreen param ───────────────────────────


def test_critic_prescreen_shortcircuit_calls_no_model(gv, tmp_path, monkeypatch):
    """★단락은 모델 호출 앞: 기어 상태와 무관하게 즉시 tier=prescreen 실패 verdict."""
    def _boom(*a, **k):
        raise AssertionError("0층 단락인데 모델이 호출됐다 — 비용 계층화 위반")
    monkeypatch.setattr(gv, "_ai_call", _boom)
    img = tmp_path / "x.png"
    img.write_bytes(b"png-stub")            # 단락 경로는 이미지를 읽지 않는다
    out = gv.critique_image(
        {"image_path": str(img), "intent": "웹 페이지 품질",
         "prescreen": "콘솔 오류 2건: TypeError…; 빈 화면(잉크 0.00%)"}, ".")
    assert "verdict_json:" in out
    verdict = json.loads(out.split("verdict_json:", 1)[1].strip())
    assert verdict["passed"] is False
    assert verdict["tier"] == "prescreen"
    assert any("콘솔 오류" in i for i in verdict["issues"])
    assert any("빈 화면" in i for i in verdict["issues"])


def test_critic_without_prescreen_keeps_normal_path(gv, tmp_path, monkeypatch):
    """단락이 정상 경로를 삼키지 않는다 — prescreen 없으면(빈 문자열 포함) 기어 호출로 간다."""
    calls = []
    monkeypatch.setattr(gv, "_ai_call", lambda *a, **k: calls.append(k) or None)
    img = tmp_path / "x.png"
    img.write_bytes(b"png-stub")
    for tin in ({"image_path": str(img), "intent": "t"},
                {"image_path": str(img), "intent": "t", "prescreen": ""}):
        out = json.loads(gv.critique_image(tin, "."))
        assert out["success"] is False and "기어" in out["error"]
    assert len(calls) == 2                  # 두 경우 모두 실제로 기어 호출까지 갔다


# ── 배선: 화면검수 워크플로우가 0층을 실제로 통과시키는가 ─────────


def test_inspection_workflow_passes_prescreen():
    import yaml
    w = yaml.safe_load(open(os.path.join(ROOT, "data/workflows/화면검수.yaml"), encoding="utf-8"))
    for k in ("do", "steps"):
        assert "prescreen: '$it.prescreen'" in w[k], f"화면검수 {k} 에 0층 통과 배선 없음"


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__] + sys.argv[1:]))
