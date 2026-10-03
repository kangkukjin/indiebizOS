"""수리 사본은 코드 작업 대상이며 일반 능력을 잃지 않는다."""
import boot_paths  # noqa: F401
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from test_repair_workspace_completion import setup, module  # noqa: F401
from thread_context import repair_workspace_scope, get_repair_workspace


@pytest.fixture
def repair_handler(setup, monkeypatch):
    from test_repair_staging import _load_handler
    root, wt, staging, session = setup
    handler = _load_handler()
    monkeypatch.setattr(handler, '_red_grant_active', lambda: {'task_id': 'task'})
    monkeypatch.setattr(handler, '_REPO_ROOT', root)
    monkeypatch.setattr(handler, '_staging_mod', lambda: staging)
    monkeypatch.setattr(handler, '_staging_key', lambda: 'task')
    return handler


def test_json_read_and_transform_use_candidate(repair_handler, setup):
    handler = repair_handler
    root, wt, _, _ = setup
    (root / 'rows.json').write_text('[{"source":"live"}]')
    (wt / 'rows.json').write_text('[{"source":"candidate"},{"source":"candidate"}]')
    with repair_workspace_scope(str(wt)):
        result = json.loads(handler.execute({'path': str(root / 'rows.json'), 'format': 'json', 'blocks': True},
                           SimpleNamespace(tool_name='read_op', project_path=str(root), agent_id='owner')))
    assert result['structured_data'] == [{'source': 'candidate'}, {'source': 'candidate'}]
    assert json.loads((root / 'rows.json').read_text()) == [{'source': 'live'}]


def test_scoped_entry_restores_context_and_parallel_snapshot(setup, monkeypatch):
    import repair_execution_scope
    import thread_context
    root, wt, staging, _ = setup
    handler = SimpleNamespace(_REPO_ROOT=root, _staging_mod=lambda: staging, _staging_key=lambda: 'task')
    monkeypatch.setattr(repair_execution_scope, 'active', lambda: True)
    monkeypatch.setattr(repair_execution_scope, 'activation_only', lambda: False)
    monkeypatch.setattr('tool_loader.load_tool_handler', lambda name: handler)
    @repair_execution_scope.scoped
    def probe():
        from concurrent.futures import ThreadPoolExecutor
        snapshot = thread_context.snapshot()
        def child():
            thread_context.restore(snapshot)
            from runtime_utils import expand_body_path
            return expand_body_path('~workspace/a.txt')
        with ThreadPoolExecutor(1) as pool:
            assert pool.submit(child).result() == str(wt / 'a.txt')
        raise ValueError('restore')
    assert get_repair_workspace() is None
    with pytest.raises(ValueError, match='restore'):
        probe()
    assert get_repair_workspace() is None


def test_registered_script_reads_candidate_and_keeps_live_unchanged(setup):
    root, wt, _, _ = setup
    ops = module('script_ops')
    scripts = wt / 'data/scripts'
    scripts.mkdir(parents=True)
    (scripts / 'registry.yaml').write_text('probe:\n  file: probe.py\n  interpreter: python\n')
    (scripts / 'probe.py').write_text('import json,os\nfrom pathlib import Path\n'
        'root=Path(os.environ["INDIEBIZ_BASE_PATH"])\n'
        'print(json.dumps({"value":root.joinpath("a.txt").read_text()}))\n'
        'root.joinpath("b.txt").write_text("candidate result")\n')
    (wt / 'a.txt').write_text('candidate')
    with repair_workspace_scope(str(wt)):
        from ibl_dependencies import script_snapshot
        assert str(scripts / 'probe.py') in script_snapshot({'id': 'probe'})['files']
        result = ops.op_run({'id': 'probe', '_ibl_edition': 2})
    assert result['success'], result
    assert result['value'] == {'value': 'candidate'}
    assert (wt / 'b.txt').read_text() == 'candidate result'
    assert (root / 'b.txt').read_text() == 'before'
    assert not (root / 'data/scripts.json').exists()


def test_temporary_script_uses_candidate_runtime(setup, repair_handler):
    from script_workspace import request_scope, workspace, prepare_path
    from file_script import execute
    root, wt, _, _ = setup
    with repair_workspace_scope(str(wt)), request_scope(str(root), 'owner'):
        work = workspace()
        source = work / 'probe.py'
        prepare_path(source)
        source.write_text('import json,os\nfrom pathlib import Path\n'
                          'Path(os.environ["INDIEBIZ_SCRIPT_RESULT"]).write_text(json.dumps(os.environ["INDIEBIZ_BASE_PATH"]))\n')
        result = execute(source, b'{}', work)
    assert result['ok'], result
    assert result['value'] == str(wt)
    assert Path(result['record']).is_relative_to(wt)
    assert not (root / 'data/script_runs').exists()


def test_model_settings_and_credentials_reach_child_without_copy(setup, monkeypatch, tmp_path):
    from repair_process import run
    root, wt, _, _ = setup
    settings = tmp_path / 'settings'
    (settings / 'data').mkdir(parents=True)
    (settings / '.env').write_text('REPAIR_FIXTURE_KEY=fixture-only\n')
    (settings / 'data/model_gear.json').write_text('{"current_gear":"fixture-gear"}')
    monkeypatch.setenv('INDIEBIZ_MODEL_CONFIG_ROOT', str(settings))
    backend = Path(__file__).parent
    code = ('import sys,os; sys.path.insert(0,' + repr(str(backend)) + '); import boot_paths; '
            'import model_resolver; assert model_resolver.get_gear()=="fixture-gear"; '
            'assert os.environ["REPAIR_FIXTURE_KEY"]=="fixture-only"; '
            'from runtime_utils import get_base_path; assert str(get_base_path())==' + repr(str(wt)) + '; print("PASS")')
    result = run([sys.executable, '-c', code], wt)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'PASS'
    assert not (wt / '.env').exists()
    assert not (wt / 'data/model_gear.json').exists()


def test_external_network_is_allowed_only_for_repair_profile(tmp_path):
    from coding_process import sandbox_command
    normal = sandbox_command(['echo'], tmp_path, tmp_path)
    repair = sandbox_command(['echo'], tmp_path, tmp_path, local_network=True, external_network=True)
    assert '(deny network*)' in normal[2]
    assert '(deny network*)' not in repair[2]
    assert '(deny file-write*)' in repair[2]


def test_ordinary_ai_package_reachable_in_repair(monkeypatch):
    import ibl_routing
    monkeypatch.setattr('repair_context.active', lambda: True)
    # Exercise the real routing boundary; avoid a paid model call in regression.
    called = []
    handler = SimpleNamespace(execute=lambda tool_input, context: called.append(tool_input) or {'items': [{'translation': '設定'}]})
    monkeypatch.setattr('tool_loader.load_tool_handler', lambda name: handler)
    result = ibl_routing._route_handler('ai_transform', {'items': [{'source': '설정'}]}, str(Path.cwd()))
    assert called and '設定' in str(result)


def test_public_ibl_read_select_dedup_and_turn_script(setup, repair_handler, monkeypatch):
    import tool_loader
    from ibl_v2_entry import handle_request
    root, wt, _, _ = setup
    (wt / 'rows.json').write_text('[{"source":"candidate"},{"source":"candidate"}]')
    original = tool_loader.load_tool_handler
    monkeypatch.setattr(tool_loader, 'load_tool_handler', lambda name:
                        repair_handler if name in {'patch_op', 'read_op', 'write_file'} else original(name))
    monkeypatch.setattr('repair_execution_scope.active', lambda: True)
    monkeypatch.setattr('repair_execution_scope.activation_only', lambda: False)
    code = ('$doc=[self:read]{path:"~workspace/rows.json",format:"json"}; '
            'return $doc.data >> [table:select]{columns:["source"]} >> [table:dedup]{by:"source"}')
    result = handle_request({'code': code, 'edition': 2}, str(root), 'owner')
    assert result['success'], result
    assert result['value']['items'] == [{'source': 'candidate'}]
    code = ('[self:write]{path:"~turn/probe.py",content:$source}; '
            'return [self:script]{path:"~turn/probe.py"}')
    source = ('import json,os\nfrom pathlib import Path\n'
              'Path(os.environ["INDIEBIZ_SCRIPT_RESULT"]).write_text(json.dumps({"base":os.environ["INDIEBIZ_BASE_PATH"]}))\n')
    result = handle_request({'code': code, 'edition': 2, 'inputs': {'source': source}}, str(root), 'owner')
    assert result['success'], result
    assert result['value'] == {'base': str(wt)}
    assert get_repair_workspace() is None


def test_registered_background_script_uses_candidate(setup):
    root, wt, _, _ = setup
    ops = module('script_ops')
    scripts = wt / 'data/scripts'
    scripts.mkdir(parents=True)
    (scripts / 'registry.yaml').write_text('probe:\n  file: probe.py\n  interpreter: python\n')
    (scripts / 'probe.py').write_text('import json,os\nprint(json.dumps({"items":[{"base":os.environ["INDIEBIZ_BASE_PATH"]}]}))\n')
    with repair_workspace_scope(str(wt)):
        job = ops.op_run({'id': 'probe', 'background': True})
        assert job['success'], job
        result = ops.op_status({'job_id': job['job_id'], 'wait': 5})
    assert result['success'], result
    assert result['status'] == 'done', result
    assert result['result']['items'] == [{'base': str(wt)}]
    assert not (root / 'data/script_runs').exists()


def test_session_script_composes_in_repair_candidate(setup, monkeypatch):
    import shutil
    import yaml
    from ibl_v2_entry import handle_request
    root, wt, _, _ = setup
    live_scripts = Path(__file__).resolve().parents[1] / 'data/scripts'
    scripts = wt / 'data/scripts'
    scripts.mkdir(parents=True)
    registry = yaml.safe_load((live_scripts / 'registry.yaml').read_text())
    entry = registry['python_libraries']
    (scripts / 'registry.yaml').write_text(yaml.safe_dump({'python_libraries': entry}))
    worker_dir = Path(entry['file']).parent
    shutil.copytree(live_scripts / worker_dir, scripts / worker_dir)
    with repair_workspace_scope(str(wt)):
        code = ('return [self:script]{id:"python_libraries",'
                'args:{op:"call",target:"os:getcwd"}}')
        result = handle_request({'code': code, 'edition': 2}, str(root), 'owner')
    assert result['success'], result
    assert result['value'] == str(wt)
    assert not (root / 'data/scripts.json').exists()


@pytest.mark.parametrize('state', ['missing', 'apply_scheduled', 'applied'])
def test_public_status_does_not_create_or_reopen_workspace(setup, repair_handler, monkeypatch, state):
    import tool_loader
    from ibl_v2_entry import handle_request
    root, wt, staging, session = setup
    if state == 'missing':
        Path(staging._session_path(str(root), 'task')).unlink()
    else:
        session['status'] = state
        staging._save_session(str(root), session)
    original = tool_loader.load_tool_handler
    monkeypatch.setattr(tool_loader, 'load_tool_handler', lambda name:
                        repair_handler if name == 'patch_op' else original(name))
    monkeypatch.setattr('repair_execution_scope.active', lambda: True)
    monkeypatch.setattr('repair_execution_scope.activation_only', lambda: False)
    monkeypatch.setattr(staging, 'ensure_session', lambda *a: pytest.fail('status created or reopened workspace'))
    result = handle_request({'code': 'return [self:patch]{op:"status"}', 'edition': 2}, str(root), 'owner')
    assert result['success'], result
    observed = staging.read_session(str(root), 'task')
    assert observed is None if state == 'missing' else observed['status'] == state
    assert get_repair_workspace() is None


def test_parallel_first_use_prepares_candidate_once(setup, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    import time
    import repair_execution_scope
    import thread_context
    root, wt, staging, _ = setup
    calls = []
    def create(*args):
        calls.append(args)
        time.sleep(.02)
        return {'worktree': str(wt.relative_to(root))}
    monkeypatch.setattr(staging, 'read_session', lambda *a: None)
    monkeypatch.setattr(staging, 'ensure_session', create)
    handler = SimpleNamespace(_REPO_ROOT=root, _staging_mod=lambda: staging, _staging_key=lambda: 'task')
    monkeypatch.setattr('tool_loader.load_tool_handler', lambda name: handler)
    monkeypatch.setattr(repair_execution_scope, 'active', lambda: True)
    monkeypatch.setattr(repair_execution_scope, 'activation_only', lambda: False)
    @repair_execution_scope.scoped
    def probe():
        snapshot = thread_context.snapshot()
        barrier = threading.Barrier(4)
        def child():
            thread_context.restore(snapshot)
            barrier.wait(timeout=5)
            return get_repair_workspace()
        with ThreadPoolExecutor(4) as pool:
            return [f.result() for f in [pool.submit(child) for _ in range(4)]]
    assert probe() == [str(wt)] * 4
    assert len(calls) == 1
    assert get_repair_workspace() is None


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
