"""사본 전체 준비·고정된 적용·실제 프로세스 쓰기 경계의 행동 검사."""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import boot_paths  # noqa: F401

PKG = Path(__file__).resolve().parents[1] / "data/packages/installed/tools/system_essentials"


def module(name):
    spec = importlib.util.spec_from_file_location("workspace_test_" + name, PKG / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    for args in (["init", "-q"], ["config", "user.email", "test@example.test"],
                 ["config", "user.name", "Test"]):
        subprocess.run(["git", *args], cwd=root, check=True)
    (root / ".gitignore").write_text(".worktrees/\ndata/system_ai_state/\n")
    (root / "a.txt").write_text("before")
    (root / "b.txt").write_text("before")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
    st = module("repair_staging")
    monkeypatch.setattr(st, "_repair_owner", lambda: "owner")
    sess = st.ensure_session(str(root), "task")
    wt = root / sess["worktree"]
    return root, wt, st, sess


def ready(root, st, sess):
    st._candidate.seal(str(root), sess, [{"gate": "test", "passed": True}],
                       {"status": "APPROVED"}, {"criteria": [{"id": "C1", "text": "two functions"}]})
    st._save_session(str(root), sess)


def test_all_changes_collected_but_preexisting_dirty_file_not_in_delta(setup):
    root, wt, st, sess = setup
    (wt / "a.txt").write_text("new")
    (wt / "binary.dat").write_bytes(b"\xff\x00")
    (wt / "binary.dat").chmod(0o755)
    (wt / "b.txt").unlink()
    ready(root, st, sess)
    assert {r["rel"] for r in sess["files"].values()} == {"a.txt", "b.txt", "binary.dat"}
    result = st._perform_apply(str(root), sess, [], None, None)
    assert result["applied"]
    assert (root / "a.txt").read_text() == "new"
    assert (root / "binary.dat").read_bytes() == b"\xff\x00"
    assert not (root / "b.txt").exists()
    assert (root / "binary.dat").stat().st_mode & 0o777 == 0o755


def test_partial_or_legacy_candidate_cannot_apply(setup):
    root, wt, st, sess = setup
    (wt / "a.txt").write_text("A done but B missing")
    st._candidate.collect(str(root), sess)
    before = (root / "a.txt").read_bytes()
    result = st._perform_apply(str(root), sess, [{"gate": "compile", "passed": True}], None, None)
    assert not result["applied"] and (root / "a.txt").read_bytes() == before


@pytest.mark.parametrize("change", ["candidate", "dependency", "live", "cancel"])
def test_stale_candidate_or_live_or_cancel_never_applies(setup, change):
    root, wt, st, sess = setup
    (wt / "a.txt").write_text("approved")
    ready(root, st, sess)
    if change == "candidate":
        (wt / "a.txt").write_text("unreviewed")
    elif change == "dependency":
        (wt / "b.txt").write_text("dependency changed")
    elif change == "live":
        (root / "a.txt").write_text("another editor")
    else:
        p = root / "data/system_ai_state/repair_continuations/task.cancel"
        p.parent.mkdir(parents=True)
        p.write_text('{}')
    before = (root / "a.txt").read_bytes()
    result = st._perform_apply(str(root), sess, [], None, None)
    assert not result["applied"] and (root / "a.txt").read_bytes() == before


def test_prepare_callback_cannot_swap_sealed_bytes(setup):
    root, wt, st, sess = setup
    (wt / "a.txt").write_text("approved")
    ready(root, st, sess)
    def mutate(path, content=None):
        (wt / "a.txt").write_text("unreviewed")
    result = st._perform_apply(str(root), sess, [], mutate, None)
    # 바이트는 이미 고정됨. 새 사본 바이트를 적용하는 일만은 없어야 한다.
    assert (root / "a.txt").read_text() in {"before", "approved"}


def test_symlink_and_path_escape_rejected(setup, tmp_path):
    root, wt, st, sess = setup
    for rel in ("../escape", ".git/config", "data/system_ai_state/forged.json"):
        with pytest.raises(ValueError):
            st._candidate.target(wt, rel)
    (wt / "escape").symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError):
        st._candidate.target(wt, "escape/a.txt")


def test_commit_uses_existing_imprint_and_preserves_other_index_changes(setup):
    root, wt, st, sess = setup
    (root / "b.txt").write_text("another editor")
    subprocess.run(["git", "add", "b.txt"], cwd=root, check=True)
    st._candidate.refresh(str(root), sess)
    (wt / "a.txt").write_text("approved")
    ready(root, st, sess)
    assert st._perform_apply(str(root), sess, [], None, None)["applied"]
    result = st.commit_applied(str(root), sess["key"])
    assert result["success"], result
    assert subprocess.check_output(["git", "show", "HEAD:a.txt"], cwd=root) == b"approved"
    assert subprocess.check_output(["git", "show", "HEAD:b.txt"], cwd=root) == b"before"
    assert subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=root).strip() == b"b.txt"
    first = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root)
    assert st.commit_applied(str(root), sess["key"])["success"]
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root) == first


def test_schedule_failure_does_not_fall_back_to_live(setup, monkeypatch):
    root, wt, st, sess = setup
    (wt / "a.txt").write_text("approved")
    import supervision_bus
    from test_repair_staging import _ready_supervisor
    monkeypatch.setattr(supervision_bus, "current", lambda: _ready_supervisor())
    monkeypatch.setattr(st, "_reload_triggering", lambda s: True)
    monkeypatch.setattr(st, "_schedule_deferred_apply", lambda *a: None)
    result = st.op_apply({"_repo_root": str(root), "_grant_key": sess["key"]})
    assert not result["applied"]
    assert (root / "a.txt").read_text() == "before"
    assert (wt / "a.txt").read_text() == "approved"


def test_post_apply_command_cannot_edit_live_source(setup):
    from repair_process import run
    root, wt, st, sess = setup
    result = run([sys.executable, "-c", 'from pathlib import Path; Path("a.txt").write_text("leak")'],
                 root, readonly=True)
    assert result.returncode != 0
    assert (root / "a.txt").read_text() == "before"


def test_local_server_works_but_live_api_connection_and_foreign_signal_do_not(setup):
    from repair_process import run
    root, wt, st, sess = setup
    command = '''import socket
s = socket.socket(); s.bind(("127.0.0.1", 0)); s.listen()
c = socket.socket(); c.connect(s.getsockname()); p, _ = s.accept(); print("PASS")
'''
    assert run([sys.executable, "-c", command], wt).returncode == 0
    result = run([sys.executable, "-c", 'import socket; socket.create_connection(("127.0.0.1", 8765), 1)'], wt)
    assert result.returncode != 0
    outside = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        result = run([sys.executable, "-c", f'import os,signal; os.kill({outside.pid}, signal.SIGTERM)'], wt)
        assert result.returncode != 0 and outside.poll() is None
    finally:
        outside.terminate()
        outside.wait(timeout=5)


def test_readiness_reuses_existing_evaluator_and_returns_in_same_execution(setup, supervisor, monkeypatch):
    import final_evaluator
    from repair_readiness import prepare
    root, wt, st, sess = setup
    (wt / "a.txt").write_text("A done")
    supervisor.repair_granted = True
    from red_report import current_owner
    sess["owner"] = current_owner()
    supervisor.framing = {"criteria": [{"text": "A"}, {"text": "B"}]}
    supervisor._final_criteria_contract = None
    supervisor.store.put_response("사본 A와 B를 검사했습니다")
    candidate = st._candidate
    h = candidate.digest(candidate.collect(str(root), sess))
    sess["execution_checks"] = [{"id": "test-run", "status": "passed", "candidate_hash": h,
                                 "environment_hash": candidate.environment(wt),
                                 "output": "A passes; B fails"}]
    sess["execution_checks"].append({**sess["execution_checks"][0], "id": "failed-run", "status": "failed", "output": "B fails"})
    def reject(*a, **kw):
        assert any(r["status"] == "failed" for r in supervisor._evaluation_packet["context"]["workspace_evidence"])
        return json.dumps({"status": "REWORK", "workspace_coverage": [{"criterion_id": "C1", "status": "passed", "evidence_ids": ["test-run"]}]})
    monkeypatch.setattr(final_evaluator, "invoke", reject)
    verify = lambda *a: (True, [{"gate": "compile", "passed": True}])
    result = prepare(supervisor, str(root), sess, verify, candidate)
    assert not result["success"] and result["missing_criteria"] == ["C2"]
    assert "readiness" not in sess and (root / "a.txt").read_text() == "before"
    (wt / "b.txt").write_text("B done")
    sess["execution_checks"] = [{"id": "test-run", "status": "passed", "candidate_hash": candidate.digest(candidate.collect(str(root), sess)),
                                 "environment_hash": candidate.environment(wt), "output": "A passes; B passes"}]
    monkeypatch.setattr(final_evaluator, "invoke", lambda *a, **kw: json.dumps({
        "status": "APPROVED", "workspace_coverage": [{"criterion_id": c, "status": "passed", "evidence_ids": ["test-run"]} for c in ("C1", "C2")]}))
    assert prepare(supervisor, str(root), sess, verify, candidate)["success"]
    assert (root / "a.txt").read_text() == "before"
    st._save_session(str(root), sess)
    writes = []
    for _ in range(2):
        assert st._perform_apply(str(root), sess, [], lambda path, content=None: writes.append(path), None)["applied"]
    assert len(writes) == 2  # 한 묶음의 두 파일, 재호출에서는 적용하지 않음
    assert len(list((root / ".worktrees").iterdir())) == 1
    before = int(subprocess.check_output(["git", "rev-list", "--count", "HEAD"], cwd=root))
    for _ in range(2):
        assert st.commit_applied(str(root), sess["key"])["success"]
    assert int(subprocess.check_output(["git", "rev-list", "--count", "HEAD"], cwd=root)) == before + 1


@pytest.mark.parametrize("attack", ["direct", "child", "symlink", "git", "ledger", "hardlink"])
def test_os_boundary_rejects_live_writes_and_allows_workspace(setup, attack):
    from repair_process import run
    root, wt, st, sess = setup
    target = root / (".git/config" if attack == "git" else
                     "data/system_ai_state/repair_sessions/task.json" if attack == "ledger" else "a.txt")
    before = target.read_bytes()
    if attack == "symlink":
        (wt / "outside").symlink_to(target)
        target = wt / "outside"
    code = f'from pathlib import Path; Path({str(target)!r}).write_text("leak")'
    if attack == "hardlink":
        code = f'import os; from pathlib import Path; os.link({str(target)!r}, "linked"); Path("linked").write_text("leak")'
    if attack == "child":
        code = f'import subprocess,sys; sys.exit(subprocess.call([sys.executable,"-c",{code!r}]))'
    result = run([sys.executable, "-c", code], wt)
    assert result.returncode != 0
    assert target.read_bytes() == before
    result = run([sys.executable, "-c", 'from pathlib import Path; Path("ok.txt").write_text("ok"); print("PASS")'], wt)
    assert result.returncode == 0, result.stderr
    assert (wt / "ok.txt").read_text() == "ok"


from test_conscious_supervisor import supervisor  # noqa: E402,F401


@pytest.mark.parametrize('mode', ['zero', 'skip', 'failed', 'empty', 'timeout', 'changed', 'passed'])
def test_execution_evidence_rejects_missing_or_stale_results(setup, monkeypatch, mode):
    import repair_process
    import supervision_bus
    root, wt, st, sess = setup
    monkeypatch.setattr(supervision_bus, 'current', lambda: None)
    scope = module('repair_tool_scope')
    handler = SimpleNamespace(_staging_mod=lambda: st, _REPO_ROOT=root, _staging_key=lambda: 'task')
    def execute(*args, **kwargs):
        if mode == 'timeout':
            raise subprocess.TimeoutExpired('probe', 1)
        if mode == 'changed':
            (wt / 'a.txt').write_text('changed while tested')
        output = {'zero': 'no tests ran', 'skip': '2 passed, 1 skipped', 'failed': '{"success":false}',
                  'empty': '', 'changed': '2 passed', 'passed': '2 passed'}[mode]
        return subprocess.CompletedProcess('probe', 0, output, '')
    monkeypatch.setattr(repair_process, 'run', execute)
    result = scope.run_shell(handler, 'probe', 1)
    assert (result['verification']['status'] == 'passed') is (mode == 'passed')
    assert st.read_session(str(root), 'task')['execution_checks'][-1]['id'] == result['verification']['id']


def test_repair_api_route_and_session_keep_ordinary_permissions(monkeypatch):
    import repair_context
    import ibl_routing
    import ibl_script_session
    import api_engine
    import ibl_registry
    monkeypatch.setattr(repair_context, 'active', lambda: {'task_id': 'repair'})
    monkeypatch.setattr(ibl_registry, 'is_registry_tool', lambda name: True)
    monkeypatch.setattr(api_engine, 'execute_tool', lambda name, args, path: {'items': [{'value': 7}]})
    assert ibl_routing._route_api_engine('fixture', {}, '.', 'fixture')['items'][0]['value'] == 7
    monkeypatch.setattr('principal.is_owner', lambda: True)
    monkeypatch.setattr('thread_context.get_allowed_nodes', lambda: None)
    ibl_script_session.authorize()
    monkeypatch.setattr('principal.is_owner', lambda: False)
    from ibl_v2_ir import Fault
    with pytest.raises(Fault, match='주인'):
        ibl_script_session.authorize()


def test_commit_keeps_preexisting_dirty_hunk_in_same_file(setup):
    root, wt, st, sess = setup
    original = '\n'.join(str(i) for i in range(50)) + '\n'
    (root / 'a.txt').write_text(original)
    subprocess.run(['git', 'add', 'a.txt'], cwd=root, check=True)
    subprocess.run(['git', 'commit', '-qm', 'long fixture'], cwd=root, check=True)
    dirty = original.replace('1\n', 'owner edit\n', 1)
    (root / 'a.txt').write_text(dirty)
    subprocess.run(['git', 'add', 'a.txt'], cwd=root, check=True)
    st._candidate.refresh(str(root), sess)
    (wt / 'a.txt').write_text(dirty.replace('45\n', 'repair edit\n'))
    ready(root, st, sess)
    assert st._perform_apply(str(root), sess, [], None, None)['applied']
    result = st.commit_applied(str(root), sess['key'])
    assert result['success'], result
    committed = subprocess.check_output(['git', 'show', 'HEAD:a.txt'], cwd=root).decode()
    assert 'repair edit' in committed and 'owner edit' not in committed
    assert 'owner edit' in (root / 'a.txt').read_text()
    staged = subprocess.check_output(['git', 'show', ':a.txt'], cwd=root).decode()
    assert 'owner edit' in staged and 'repair edit' in staged
    diff = subprocess.check_output(['git', 'diff', '--cached'], cwd=root).decode()
    assert 'owner edit' in diff and 'repair edit' not in diff


def test_activation_receipt_prevents_duplicate_commands(setup, monkeypatch):
    import red_apply
    root, wt, st, sess = setup
    (wt / 'a.txt').write_text('approved')
    ready(root, st, sess)
    calls = []
    monkeypatch.setattr(red_apply, '_run_post_verify', lambda *a, **kw: calls.append(a) or {'exit_code': 0})
    for _ in range(2):
        row = st.read_session(str(root), 'task')
        assert st._candidate.activation(str(root), row, 'active_verify_cmd', 'check', st._save_session)['state'] == 'passed'
    assert len(calls) == 1
    row['activation_checks']['active_verify_cmd']['state'] = 'running'
    row['activation_checks']['active_verify_cmd']['output_path'] = str(root / 'missing')
    st._save_session(str(root), row)
    assert st._candidate.activation(str(root), row, 'active_verify_cmd', 'check', st._save_session)['state'] == 'running'
    assert len(calls) == 1


def test_same_root_has_one_owner(setup):
    root, wt, st, sess = setup
    with st._candidate.locked(str(root), 'owner-task', nonblocking=True):
        with pytest.raises(BlockingIOError):
            with st._candidate.locked(str(root), 'owner-task', nonblocking=True):
                pytest.fail('duplicate owner')


def test_interrupted_immediate_apply_uses_existing_rollback_and_preserves_foreign_edit(setup):
    from restart_protocol import atomic_json
    root, wt, st, sess = setup
    (wt / 'a.txt').write_text('approved')
    ready(root, st, sess)
    home = root / 'data/system_ai_state/red_backups/task'
    home.mkdir(parents=True)
    backup = home / 'before'
    backup.write_text('before')
    atomic_json(home / 'manifest.json', {'files': {str(root / 'a.txt'): str(backup)},
                'target_hashes': {str(root / 'a.txt'): sess['sealed']['a.txt']['after']['sha']}})
    sess['status'] = 'applying'
    st._save_session(str(root), sess)
    (root / 'a.txt').write_text('foreign edit')
    assert not st._recover_immediate(str(root), sess)
    assert (root / 'a.txt').read_text() == 'foreign edit'
    (root / 'a.txt').write_text('approved')
    assert st._recover_immediate(str(root), sess)
    assert (root / 'a.txt').read_text() == 'before'
    assert (wt / 'a.txt').read_text() == 'approved'
    assert st.read_session(str(root), sess['key'])['status'] == 'staging'
    assert 'readiness' not in sess


def test_ignored_new_code_cannot_disappear_from_apply_bundle(setup):
    root, wt, st, sess = setup
    (wt / '.gitignore').write_text((wt / '.gitignore').read_text() + 'backend/hidden.py\n')
    (wt / 'backend').mkdir()
    (wt / 'backend/hidden.py').write_text('value = 1')
    with pytest.raises(ValueError, match='누락'):
        ready(root, st, sess)
    assert not (root / 'backend/hidden.py').exists()


def test_native_repair_provider_commands_have_no_writing_builtin_tools(monkeypatch):
    from providers import get_provider
    import repair_context
    monkeypatch.setattr(repair_context, 'active', lambda: {'task_id': 'fixture'})
    codex = get_provider('codex', api_key='', model='fixture', system_prompt='')
    codex._binary_path = '/fake/codex'
    command = codex._build_command(stream=True)
    assert '--dangerously-bypass-approvals-and-sandbox' not in command
    assert command[command.index('--sandbox') + 1] == 'read-only'
    assert 'approval_policy="never"' in command
    claude = get_provider('claude_code', api_key='', model='fixture', system_prompt='')
    claude._binary_path = '/fake/claude'
    command = claude._build_command(stream=True)
    assert command[command.index('--tools') + 1] == ''
    assert '--strict-mcp-config' in command
    assert command[command.index('--setting-sources') + 1] == ''
    assert all(name.startswith('mcp__indiebizos__') for name in command[command.index('--allowed-tools') + 1].split(','))


def test_identical_delta_in_a_different_root_is_a_new_commit(setup):
    root, wt, st, sess = setup
    (wt / 'a.txt').write_text('approved')
    ready(root, st, sess)
    assert st._perform_apply(str(root), sess, [], None, None)['applied']
    first = st.commit_applied(str(root), sess['key'])
    assert first['success']
    subprocess.run(['git', 'revert', '--no-edit', first['commit']], cwd=root, check=True, capture_output=True)
    second = st.ensure_session(str(root), 'different-root')
    (root / second['worktree'] / 'a.txt').write_text('approved')
    ready(root, st, second)
    assert st._perform_apply(str(root), second, [], None, None)['applied']
    committed = st.commit_applied(str(root), second['key'])
    assert committed['success'] and committed['commit'] != first['commit']
    assert subprocess.check_output(['git', 'show', 'HEAD:a.txt'], cwd=root) == b'approved'


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
