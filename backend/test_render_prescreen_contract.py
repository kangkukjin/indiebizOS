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
    return _load("gemini_vision.py", "mp_gv_prescreen_test")


# ── 0층 관측: render 행의 prescreen ───────────────────────────────


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


def test_html_clean_page_has_empty_prescreen(ra, tmp_path):
    """★오탐 금지: 깨끗한 페이지의 prescreen 은 빈 문자열 — 아니면 유료 심사가 통째로 우회된다."""
    p = tmp_path / "clean.html"
    p.write_text("<html><body style='font-size:40px;padding:60px'>"
                 "<h1>정상 페이지</h1><p>본문 내용이 충분히 그려진다.</p></body></html>",
                 encoding="utf-8")
    result = json.loads(ra.render_op_html({"path": str(p)}, output_base=str(tmp_path)))
    assert result["items"][0]["prescreen"] == ""
    assert result["prescreen_flagged"] == 0


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


def test_critic_prescreen_shortcircuit_needs_no_api_key(gv, tmp_path, monkeypatch):
    """★단락은 키 검사 앞: 비전 호출·키 없이 즉시 tier=prescreen 실패 verdict."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    img = tmp_path / "x.png"
    img.write_bytes(b"png-stub")            # 단락 경로는 이미지를 읽지 않는다
    out = gv.critique_gemini_image(
        {"image_path": str(img), "intent": "웹 페이지 품질",
         "prescreen": "콘솔 오류 2건: TypeError…; 빈 화면(잉크 0.00%)"}, ".")
    assert "verdict_json:" in out
    verdict = json.loads(out.split("verdict_json:", 1)[1].strip())
    assert verdict["passed"] is False
    assert verdict["tier"] == "prescreen"
    assert any("콘솔 오류" in i for i in verdict["issues"])
    assert any("빈 화면" in i for i in verdict["issues"])


def test_critic_without_prescreen_keeps_normal_path(gv, tmp_path, monkeypatch):
    """단락이 정상 경로를 삼키지 않는다 — prescreen 없으면(빈 문자열 포함) 기존 키 요구 그대로."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    img = tmp_path / "x.png"
    img.write_bytes(b"png-stub")
    for tin in ({"image_path": str(img), "intent": "t"},
                {"image_path": str(img), "intent": "t", "prescreen": ""}):
        out = json.loads(gv.critique_gemini_image(tin, "."))
        assert out["success"] is False and "GEMINI_API_KEY" in out["error"]


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
