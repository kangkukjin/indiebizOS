"""설정된 비전 모델과 수리 사본의 실제 조사·빌드·UI 검사 능력."""
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest

from test_repair_workspace_completion import setup, module  # noqa: F401
from test_hippo_tree import env, _add  # noqa: F401


@pytest.mark.parametrize("provider", ["codex", "codex_cli", "codex-cli"])
@pytest.mark.parametrize("effort", ["high", "max", "ultra"])
def test_configured_image_evaluator_uses_same_selector_as_execution(monkeypatch, provider, effort):
    import model_resolver as mr
    from providers.codex import CodexProvider
    descriptor = {"provider": provider, "model": "gpt-6-astra:" + effort, "api_key": ""}
    monkeypatch.setattr("providers.codex.list_available_models", lambda: [])
    monkeypatch.setattr(mr, "resolve", lambda *a: descriptor)
    monkeypatch.setattr(mr, "resolve_vision", lambda: {"provider": "missing", "model": "opus"})
    selected = []
    ready = object()
    monkeypatch.setattr(mr, "_provider_from_desc", lambda d, **kw: selected.append((d, kw)) or ready)
    assert mr.image_input_support(descriptor) is True
    assert mr.get_image_evaluation_provider() == (ready, descriptor)
    assert selected == [(descriptor, {"oneshot": True})]
    assert CodexProvider(api_key="", model=descriptor["model"], system_prompt="")._model_and_effort() == ("gpt-6-astra", effort)


def test_image_support_does_not_strip_other_provider_ids_or_unknown_effort(monkeypatch):
    import model_resolver as mr
    monkeypatch.setattr("providers.codex.list_available_models", lambda: [])
    for provider, model in [("openai", "gpt-6-astra:high"), ("codex", "gpt-6-astra:typo"),
                            ("codex", "unknown:high")]:
        assert mr.image_input_support({"provider": provider, "model": model}) is None


@pytest.mark.parametrize("name,payload", [
    ("grep_files", {"pattern": "candidate", "path": "."}),
    ("glob_files", {"pattern": "*.txt", "root_path": "."}),
])
def test_repair_search_reads_candidate_not_live(setup, monkeypatch, name, payload):
    from test_repair_staging import _load_handler
    from repair_context import guard_tool
    root, wt, st, sess = setup
    (wt / "a.txt").write_text("candidate only")
    handler = _load_handler()
    monkeypatch.setattr("repair_context.active", lambda: True)
    monkeypatch.setattr(handler, "_red_grant_active", lambda: True)
    monkeypatch.setattr(handler, "_REPO_ROOT", root)
    monkeypatch.setattr(handler, "_staging_mod", lambda: st)
    monkeypatch.setattr(handler, "_staging_key", lambda: "task")
    context = SimpleNamespace(tool_name=name, project_path=str(root), agent_id="owner")
    guard_tool(handler, name, payload)
    result = json.loads(handler.execute(payload, context))
    assert result.get("success", True), result
    assert result["items"]
    if name == "grep_files":
        assert "candidate only" in json.dumps(result)
    else:
        assert str(wt) in json.dumps(result)
    assert (root / "a.txt").read_text() == "before"


@pytest.mark.parametrize("payload", [{"root_path": "/outside", "pattern": "*.py"},
    {"path": ".", "pattern": "../*.py"}, {"path": ".", "pattern": "/tmp/*.py"}])
def test_search_cannot_escape_candidate(setup, payload):
    root, wt, st, sess = setup
    handler = SimpleNamespace(_staging_mod=lambda: st, _REPO_ROOT=root, _staging_key=lambda: "task")
    with pytest.raises((ValueError, PermissionError)):
        module("repair_tool_scope").prepare(handler, "glob_files", payload, str(root))


@pytest.mark.parametrize("node", ["", "개발"])
def test_repair_recall_keeps_live_schema_and_documents_unchanged(env, tmp_path, monkeypatch, node):
    ht, db = env
    _add(db, "read files", '[self:read]{path:"a.txt"}', "개발")
    original = Path(db).read_bytes()
    package = Path(__file__).resolve().parents[1] / "data/packages/installed/tools/memory/handler.py"
    spec = importlib.util.spec_from_file_location("memory_repair_test", package)
    handler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(handler)
    payload = {"op": "recall", "store": "실행", "node": node}
    monkeypatch.setattr("repair_context.active", lambda: True)
    monkeypatch.setattr(ht, "sync_all", lambda *a: pytest.fail("live sync"))
    monkeypatch.setattr(ht, "sync_topic", lambda *a: pytest.fail("live sync"))
    assert handler.repair_safe_call("memory_op", payload)
    result = json.loads(handler.execute(payload, SimpleNamespace(tool_name="memory_op")))
    assert result["success"] and result["sync_deferred"], result
    assert "개발" in json.dumps(result, ensure_ascii=False)
    assert Path(db).read_bytes() == original
    assert not Path(ht.DOC_DIR).exists()
    assert not handler.repair_safe_call("memory_op", {"op": "move", "store": "실행"})


def test_dependency_cache_writable_while_shared_package_is_protected(setup):
    from repair_runtime import prepare_dependencies
    from repair_process import run
    root, wt, st, sess = setup
    live = root / "frontend/node_modules"
    (live / "pkg").mkdir(parents=True)
    (live / "pkg/index.js").write_text("original")
    (live / ".tmp").mkdir()
    (live / ".tmp/previous").write_text("live cache")
    (wt / "frontend").mkdir()
    (wt / "frontend/node_modules").symlink_to(live, target_is_directory=True)
    prepare_dependencies(root, wt)
    prepare_dependencies(root, wt)
    code = "from pathlib import Path; Path('frontend/node_modules/.tmp/new').write_text('local'); print('ok')"
    result = run([sys.executable, "-c", code], wt)
    assert result.returncode == 0, result.stderr
    assert not (live / ".tmp/new").exists()
    assert not (wt / "frontend/node_modules/.tmp/previous").exists()
    result = run([sys.executable, "-c", "from pathlib import Path; Path('frontend/node_modules/pkg/index.js').write_text('bad')"], wt)
    assert result.returncode != 0
    assert (live / "pkg/index.js").read_text() == "original"


def test_runtime_selects_compatible_installed_node(monkeypatch, tmp_path):
    import repair_runtime as runtime
    (tmp_path / "package.json").write_text('{}')
    monkeypatch.setattr("runtime_utils.get_runtime_paths", lambda: {"node": "/old/node"})
    monkeypatch.setattr(runtime.shutil, "which", lambda value, **kw:
                        str(Path(kw["path"]) / value) if value == "node" else value)
    calls = []
    def check(argv, **kw):
        assert argv[0] == "/usr/bin/sandbox-exec"
        calls.append(argv[-4])
        return SimpleNamespace(returncode=0 if argv[-4] == "/compatible/node" else 1)
    monkeypatch.setattr(runtime.subprocess, "run", check)
    assert runtime.node_runtime(tmp_path, {"PATH": "/old:/compatible"}) == "/compatible/node"
    assert calls == ["/old/node", "/compatible/node"]


def test_dependency_preparation_rejects_parent_link_outside_candidate(tmp_path):
    from repair_runtime import prepare_dependencies
    repo, root = tmp_path / "repo", tmp_path / "candidate"
    (repo / "frontend/node_modules").mkdir(parents=True)
    root.mkdir()
    (root / "frontend").symlink_to(repo / "frontend", target_is_directory=True)
    with pytest.raises(ValueError, match="사본 밖"):
        prepare_dependencies(repo, root)
    assert not (repo / "frontend/node_modules/.tmp").exists()


def test_timeout_preserves_child_diagnostics(monkeypatch, setup):
    from repair_process import run
    root, wt, st, sess = setup
    monkeypatch.setattr("script_process.run_process", lambda *a, **kw:
                        {"timed_out": True, "stdout": "started", "stderr": "failure before timeout"})
    with pytest.raises(subprocess.TimeoutExpired) as error:
        run(["fixture"], wt)
    assert error.value.stderr == "failure before timeout"
    handler = SimpleNamespace(_staging_mod=lambda: st, _REPO_ROOT=root, _staging_key=lambda: "task")
    result = module("repair_tool_scope").run_shell(handler, "fixture", 5)
    assert result["exit_code"] == 124 and result["success"] is False
    assert "started" in result["output"] and "failure before timeout" in result["output"]


def test_runtime_probe_cannot_write_outside_sandbox(tmp_path):
    from repair_runtime import node_runtime
    if not shutil.which("node"):
        pytest.skip("Node unavailable")
    root = tmp_path / "candidate"
    package = root / "node_modules/semver"
    package.mkdir(parents=True)
    (root / "package.json").write_text('{}')
    outside = tmp_path / "outside.txt"
    outside.write_text("original")
    (package / "index.js").write_text(
        "require('fs').writeFileSync(" + json.dumps(str(outside)) + ", 'bad');"
        "module.exports={satisfies:()=>true};")
    assert node_runtime(root, dict(os.environ, TMPDIR=str(root))) is None
    assert outside.read_text() == "original"


def test_typescript_and_vite_build_in_candidate(tmp_path):
    from repair_runtime import prepare_dependencies
    from repair_process import run
    repo = Path(__file__).resolve().parents[1]
    if not (repo / "frontend/node_modules/vite").is_dir():
        pytest.skip("frontend dependencies unavailable")
    root = tmp_path / "candidate"
    frontend = root / "frontend"
    frontend.mkdir(parents=True)
    (frontend / "package.json").write_text(json.dumps({
        "type": "module", "scripts": {"build": "tsc --noEmit && vite build"},
        "devDependencies": {"typescript": "*", "vite": "*"},
    }))
    (frontend / "tsconfig.json").write_text(json.dumps({"compilerOptions": {
        "target": "ES2022", "module": "ESNext", "moduleResolution": "bundler", "types": [],
        "incremental": True, "tsBuildInfoFile": "./node_modules/.tmp/check.tsbuildinfo",
    }}))
    (frontend / "index.html").write_text('<h1>Ready</h1><script type="module" src="/main.ts"></script>')
    (frontend / "main.ts").write_text('document.title = "Candidate"; export {};')
    prepare_dependencies(repo, root)
    result = run(["/bin/sh", "-c", "cd frontend && npm run build"], root, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (frontend / "dist/index.html").is_file()
    assert (frontend / "node_modules/.tmp/check.tsbuildinfo").is_file()


@pytest.mark.system
def test_electron_captures_persistent_image_and_preserves_outer_boundary(tmp_path):
    from repair_process import run
    package = Path(__file__).resolve().parents[1] / "frontend/node_modules/electron"
    if not (package / "path.txt").is_file():
        pytest.skip("Electron unavailable")
    binary = package / "dist" / (package / "path.txt").read_text().strip()
    root = tmp_path / "candidate"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("original")
    main = root / "main.cjs"
    main.write_text('''const {app, BrowserWindow}=require('electron');
const fs=require('fs'), path=require('path');
app.setPath('userData', path.join(__dirname, 'profile'));
app.whenReady().then(async()=>{
  const win=new BrowserWindow({show:false});
  await win.loadURL('data:text/html,<title>English UI</title><h1>Ready</h1>');
  const title=await win.webContents.executeJavaScript('document.title');
  const image=await win.webContents.capturePage();
  fs.writeFileSync(path.join(__dirname, 'capture.png'), image.toPNG());
  let protectedOutside=false;
  try {fs.writeFileSync(process.argv[2], 'bad')} catch(e) {protectedOutside=true;}
  console.log(JSON.stringify({title, protectedOutside}));
  app.exit(title==='English UI' && protectedOutside && !image.isEmpty() ? 0 : 2);
}).catch(e=>{console.error(e); app.exit(3)});
setTimeout(()=>app.exit(4), 15000);
''')
    result = run([str(binary), str(main), str(outside)], root, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"title":"English UI"' in result.stdout
    assert (root / "capture.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert outside.read_text() == "original"


@pytest.mark.parametrize("engine", ["rg", "python"])
def test_search_root_hidden_ancestor_does_not_hide_contents(tmp_path, engine):
    from test_grep_glob_dialect import fs_grep
    root = tmp_path / ".worktrees/candidate"
    (root / "node_modules").mkdir(parents=True)
    (root / "visible.txt").write_text("needle\nneedle\n")
    (root / "node_modules/hidden.txt").write_text("needle\n")
    if engine == "rg" and not fs_grep._RG_BIN:
        pytest.skip("rg unavailable")
    search = fs_grep._rg_grep if engine == "rg" else fs_grep._py_grep
    rows = search("needle", str(root), "*.txt", False, 100, 500, 40000)[0]
    assert len(rows) == 2
    assert {row[0] for row in rows} == {str(root / "visible.txt")}
    if engine == "rg":
        assert fs_grep._rg_count("needle", str(root), "*.txt", False) == {str(root / "visible.txt"): 2}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
