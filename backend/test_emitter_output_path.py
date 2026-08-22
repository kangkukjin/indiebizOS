"""emitter 산출 경로 규약의 단일성 회귀 (29회차 J29-1 판정, 2026-08-23)

29회차 상상훈련 F29-2 가 실측한 것: **같은 파이프 끝에 무엇을 놓느냐에 따라 파일이
어디 떨어질지가 달랐다.**

    [table:spreadsheet]{path: "/tmp/x/a.xlsx"}  → /tmp/x/a.xlsx        (경로 존중)
    [table:document]{filename: "/tmp/x/a.md"}   → <프로젝트>/outputs/a.md (경로 버림·고지)
    [table:chart]{path: "/tmp/x/a.png"}         → <프로젝트>/outputs/chart_<ts>.png (말없이 버림)

셋이 서로 다른 해소기를 들고 있었다. 판정(2026-08-23) = **주어진 경로는 지킨다** —
`[self:write]` 가 세운 몸의 오래된 규약에 맞춘다. 반대안(모두 프로젝트 outputs 로 강제)은
`/tmp`·NAS 로 쓰던 문장을 조용히 딴 데로 보내므로 침묵 이동 부류가 된다.

이 배터리가 지키는 것:
  ① 해소기는 하나다 — 세 emitter 가 같은 함수를 통과한다(25회차 원칙의 적용).
  ② bare 파일명은 여전히 outputs/ 로 간다 (가장 흔한 경우 = 무변화).
  ③ 준 경로(상대·절대)는 지킨다.
  ④ 범위 밖은 **거절**한다 — 있는 척하고 딴 데 쓰지 않는다(fail-closed).

실행: .venv/bin/python -m pytest backend/test_emitter_output_path.py -q
"""
import importlib.util
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401

from tool_context import ToolContext  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PKGS = os.path.join(_ROOT, "data", "packages", "installed", "tools")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def ctx(tmp_path):
    return ToolContext(project_path=str(tmp_path), tool_name="chart")


def _allow_all(path, project_path):
    return None


# ── ① 규약 자체 ──────────────────────────────────────────────────────────

def test_P1_bare_파일명은_outputs로(ctx, tmp_path):
    """가장 흔한 경우 — 규약을 바꿔도 여기는 변하지 않는다."""
    r = ctx.resolve_output_path("a.png", guard=_allow_all)
    assert r.get("error") is None
    assert r["path"] == str(tmp_path / "outputs" / "a.png")
    assert r["redirected"] is True


def test_P2_디렉토리를_적으면_지킨다(ctx, tmp_path):
    """옛 chart 는 여기서 basename() 으로 'reports/2026' 을 말없이 버렸다."""
    r = ctx.resolve_output_path("reports/2026/a.png", guard=_allow_all)
    assert r["path"] == str(tmp_path / "reports" / "2026" / "a.png")
    assert r["redirected"] is False


def test_P3_절대경로는_그대로(ctx, tmp_path):
    out = tmp_path.parent / "elsewhere" / "a.png"
    r = ctx.resolve_output_path(str(out), guard=_allow_all)
    assert r["path"] == str(out)


def test_P4_경로_생략시_기본이름은_outputs로(ctx, tmp_path):
    r = ctx.resolve_output_path(None, stem="chart", ext=".png", guard=_allow_all)
    assert r.get("error") is None
    assert os.path.dirname(r["path"]) == str(tmp_path / "outputs")
    assert os.path.basename(r["path"]).startswith("chart_")
    assert r["path"].endswith(".png")


def test_P5_게이트_거절은_그대로_올린다(ctx):
    def _refuse(path, project_path):
        return "Error: RED 구역입니다"
    r = ctx.resolve_output_path("a.png", guard=_refuse)
    assert r.get("error") == "Error: RED 구역입니다"
    assert "path" not in r


def test_P6_게이트를_못_빌리면_프로젝트_밖을_거절한다(ctx, tmp_path, monkeypatch):
    """fail-closed. 판정할 수 없을 때 '있는 척' 하고 딴 데 쓰지 않는다.

    guard=None 이면 해소기가 쓰기 게이트(system_essentials)를 빌린다. 그걸 못 빌리는
    상황을 만들어 놓고, 프로젝트 밖 절대경로가 **거절**되는지 본다.
    """
    import tool_loader
    monkeypatch.setattr(tool_loader, "load_tool_handler",
                        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("no gate")))
    outside = str(tmp_path.parent / "outside" / "a.png")
    r = ctx.resolve_output_path(outside)
    assert r.get("error"), "게이트 없이 프로젝트 밖에 썼다"
    assert "거절" in r["error"]
    # 프로젝트 안은 게이트 없이도 통과한다
    assert ctx.resolve_output_path("a.png").get("error") is None


def test_P7_게이트를_실제로_빌린다(tmp_path):
    """guard 를 안 주면 쓰기 게이트의 판정이 그대로 적용돼야 한다 —
    RED 구역(backend/)은 emitter 로도 못 쓴다."""
    ctx = ToolContext(project_path=_ROOT, tool_name="chart")
    r = ctx.resolve_output_path("backend/ibl/injected.html")
    assert r.get("error"), "emitter 가 RED 구역에 쓸 수 있었다"


# ── ② 세 emitter 가 같은 해소기를 통과한다 ───────────────────────────────

def test_P8_chart_가_해소기를_통과한다(tmp_path, monkeypatch):
    p = os.path.join(_PKGS, "visualization", "handler.py")
    if not os.path.exists(p):
        pytest.skip("visualization 패키지 없음")
    viz = _load("_it29b_viz", p)
    seen = {}
    ctx = ToolContext(project_path=str(tmp_path), tool_name="chart")
    real = ctx.resolve_output_path

    def _spy(raw, **kw):
        seen["raw"] = raw
        return real(raw, **kw)
    monkeypatch.setattr(ctx, "resolve_output_path", _spy, raising=False)
    # 렌더까지 가지 않게 데이터 없이 부른다 — 경로 해소는 그 전에 일어난다.
    viz.execute({"output_path": "reports/a.png"}, ctx)
    assert seen.get("raw") == "reports/a.png", "chart 가 해소기를 안 거쳤다"


def test_P9_document_가_준_경로를_지킨다(tmp_path):
    p = os.path.join(_PKGS, "data-ops", "doc_build.py")
    if not os.path.exists(p):
        pytest.skip("data-ops 패키지 없음")
    db = _load("_it29b_docbuild", p)
    ctx = ToolContext(project_path=str(tmp_path), tool_name="render_document")
    import json
    out = json.loads(db.render_document(
        {"blocks": [{"type": "paragraph", "text": "안녕"}],
         "format": "markdown", "filename": "reports/2026/a.md"},
        ctx.output_dir(), ctx))
    assert out["success"] is True
    assert out["path"] == str(tmp_path / "reports" / "2026" / "a.md"), out["path"]
    assert os.path.exists(out["path"])


def test_P10_document_bare_이름은_여전히_outputs(tmp_path):
    p = os.path.join(_PKGS, "data-ops", "doc_build.py")
    if not os.path.exists(p):
        pytest.skip("data-ops 패키지 없음")
    db = _load("_it29b_docbuild2", p)
    ctx = ToolContext(project_path=str(tmp_path), tool_name="render_document")
    import json
    out = json.loads(db.render_document(
        {"blocks": [{"type": "paragraph", "text": "안녕"}],
         "format": "markdown", "filename": "a.md"}, ctx.output_dir(), ctx))
    assert out["path"] == str(tmp_path / "outputs" / "a.md"), out["path"]


def test_P11_document_범위밖은_거절한다(tmp_path):
    """옛 동작은 경로를 버리고 **성공**했다 — 이제는 거절이 정직하다."""
    p = os.path.join(_PKGS, "data-ops", "doc_build.py")
    if not os.path.exists(p):
        pytest.skip("data-ops 패키지 없음")
    db = _load("_it29b_docbuild3", p)
    ctx = ToolContext(project_path=_ROOT, tool_name="render_document")
    import json
    out = json.loads(db.render_document(
        {"blocks": [{"type": "paragraph", "text": "안녕"}],
         "format": "html", "filename": "frontend/index.html"}, ctx.output_dir(), ctx))
    assert out["success"] is False, "emitter 가 RED 구역(frontend/)을 덮어쓸 수 있었다"


def test_P12_spreadsheet_규약이_해소기와_같다(tmp_path):
    """spreadsheet 는 원래 이 규약의 주인이었다 — 접은 뒤에도 결과가 같아야 한다."""
    p = os.path.join(_PKGS, "system_essentials", "office_ops.py")
    if not os.path.exists(p):
        pytest.skip("system_essentials 패키지 없음")
    off = _load("_it29b_office", p)
    ctx = ToolContext(project_path=str(tmp_path), tool_name="spreadsheet")
    import json
    out = json.loads(off.spreadsheet(
        {"rows": [[1, 2]], "path": "a"}, str(tmp_path), _allow_all, context=ctx))
    assert out["success"] is True
    assert out["path"] == str(tmp_path / "outputs" / "a.xlsx"), out["path"]
    # 디렉토리를 적으면 지킨다 (옛 동작과 동일 — 여긴 원래 정직했다)
    out2 = json.loads(off.spreadsheet(
        {"rows": [[1, 2]], "path": "sub/b.xlsx"}, str(tmp_path), _allow_all, context=ctx))
    assert out2["path"] == str(tmp_path / "sub" / "b.xlsx"), out2["path"]


if __name__ == "__main__":
    # 러너는 하나다 — 직접 실행도 pytest 에 위임한다(28회차: 두 번째 러너는 조용히 0건).
    raise SystemExit(pytest.main([__file__, "-q"]))
