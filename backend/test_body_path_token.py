"""몸 기준 경로 토큰 `~workspace/` 회귀 — 단일 해소점 + 관문 (2026-09-02 언어 개정 A안).

실측: 보고서 가이드·정기보고 계기의 폴더가 `/Users/<계정>/…` 로 박혀 있었고, 시스템 프로젝트
루트(projects/system)로는 <repo>/outputs/ 에 닿을 수 없어 계정명 없는 표기가 없었다. 경로 해소점이
IBL 표면에 30여 곳 산재해 토큰을 들일 자리가 없던 것이 뿌리 — 해소점을 하나로 모으고 관문이 지킨다.

실행: .venv/bin/python -m pytest backend/test_body_path_token.py -q
"""
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "check_body_path_expansion.py"


def test_token_expands_to_base_path(monkeypatch, tmp_path):
    import runtime_utils as ru
    monkeypatch.setenv("INDIEBIZ_BASE_PATH", str(tmp_path))
    assert ru.expand_body_path("~workspace/outputs/x.md") == str(tmp_path / "outputs" / "x.md")
    assert ru.expand_body_path("~workspace") == str(tmp_path)
    assert ru.expand_body_path("~workspace/") == str(tmp_path)


def test_home_absolute_relative_unchanged():
    import runtime_utils as ru
    assert ru.expand_body_path("~/a") == os.path.expanduser("~/a")
    assert ru.expand_body_path("/abs/p") == "/abs/p"
    assert ru.expand_body_path("outputs/rel") == "outputs/rel"
    assert ru.expand_body_path("") == ""
    # 비슷하지만 토큰이 아닌 것은 건드리지 않는다
    assert ru.expand_body_path("~workspaces/x") == os.path.expanduser("~workspaces/x")


def test_tool_context_resolve_path_honours_token(monkeypatch, tmp_path):
    monkeypatch.setenv("INDIEBIZ_BASE_PATH", str(tmp_path))
    from tool_context import ToolContext
    ctx = ToolContext(tool_name="t", project_path=str(tmp_path / "projects" / "p"))
    assert ctx.resolve_path("~workspace/outputs/a") == str(tmp_path / "outputs" / "a")
    assert ctx.resolve_path("rel") == str((tmp_path / "projects" / "p" / "rel").resolve())


def test_file_find_reaches_workspace_folder(monkeypatch, tmp_path):
    """시스템 프로젝트 안에서 `~workspace/outputs/<종류>` 로 보고서 폴더에 닿는다 — 이 결함의 재현."""
    monkeypatch.setenv("INDIEBIZ_BASE_PATH", str(tmp_path))
    rep = tmp_path / "outputs" / "ai_trend_reports"; rep.mkdir(parents=True)
    (rep / "ai_trend_report_2026-09-02.md").write_text("# r", encoding="utf-8")
    proj = tmp_path / "projects" / "system"; proj.mkdir(parents=True)
    import importlib.util, json
    se = ROOT / "data" / "packages" / "installed" / "tools" / "system_essentials"
    sys.path.insert(0, str(se))
    spec = importlib.util.spec_from_file_location("se_handler_t", se / "handler.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    ctx = SimpleNamespace(tool_name="glob_files", project_path=str(proj), agent_id="test", project_id="system", task_id=None)
    out = m.execute({"pattern": "*report_*.md", "path": "~workspace/outputs/ai_trend_reports", "max_results": 5}, ctx)
    d = json.loads(out) if isinstance(out, str) else out
    items = d.get("items") or d.get("files") or []
    assert any("ai_trend_report_2026-09-02.md" in str(i) for i in items), d


def test_gate_catches_direct_expanduser(tmp_path):
    bad = tmp_path / "bad.py"; bad.write_text("import os\np = os.path.expanduser(x)\n", encoding="utf-8")
    ok = tmp_path / "ok.py"; ok.write_text("import os\np = os.path.expanduser(x)  # path-ok: 홈 설정 파일\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(GATE), "--files", str(bad)], capture_output=True, text=True)
    assert r.returncode == 1 and "bad.py:2" in r.stdout
    r = subprocess.run([sys.executable, str(GATE), "--files", str(ok)], capture_output=True, text=True)
    assert r.returncode == 0


def test_gate_is_clean_on_live_tree():
    r = subprocess.run([sys.executable, str(GATE)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout


def test_hook_and_shell_export():
    hook = (ROOT / "scripts" / "git-hooks" / "pre-commit").read_text(encoding="utf-8")
    assert "check_body_path_expansion.py" in hook
    api = (ROOT / "backend" / "api.py").read_text(encoding="utf-8")
    assert 'os.environ.setdefault("INDIEBIZ_BASE_PATH"' in api


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
