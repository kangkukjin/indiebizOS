"""프로젝트별 웹앱 관용구의 계획·실행·실패 계약."""
import boot_paths  # noqa: F401
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("webapp_work_test", ROOT / "data/scripts/webapp_work.py")
work = importlib.util.module_from_spec(spec)
spec.loader.exec_module(work)


@pytest.fixture
def project(tmp_path, monkeypatch):
    p = tmp_path / "app with spaces"
    p.mkdir()
    (p / "README.md").write_text("# Fixture app\n")
    (p / "AGENTS.md").write_text("Use declared checks.\n")
    (p / "webapp-checks.json").write_text(json.dumps({"checks": [
        {"name": "test", "argv": [sys.executable, "-c", "print('tests passed')"]},
        {"name": "build", "argv": [sys.executable, "-c", "print('build failed');raise SystemExit(7)"]},
    ]}))
    monkeypatch.setattr(work, "LOG_ROOT", tmp_path / "logs")
    return p


def test_inspection_has_documents_and_no_repository_is_not_failure(project):
    out = work.inspect_project(project)
    assert out['git']['status'] == 'not_repository'
    assert {Path(d['path']).name for d in out['documents']} == {'README.md', 'AGENTS.md'}
    assert out['checks_available']


def test_npm_project_discovers_only_defined_checks(tmp_path):
    (tmp_path / 'package.json').write_text(json.dumps({'scripts': {'build': 'node build.js', 'deploy': 'publish'}}))
    out = work.configuration(tmp_path)
    assert out['checks'] == [{'name': 'build', 'argv': ['npm', 'run', 'build']}]
    with pytest.raises(ValueError, match='검사 설정 없음: test'):
        work.plan(tmp_path, ['test', 'build'])
    (tmp_path / 'pnpm-lock.yaml').touch()
    assert work.configuration(tmp_path)['checks'][0]['argv'][0] == 'pnpm'
    (tmp_path / 'yarn.lock').touch()
    with pytest.raises(ValueError, match='충돌'):
        work.configuration(tmp_path)


def test_empty_or_missing_checks_never_pass(project, tmp_path):
    with pytest.raises(ValueError, match='비어 있지 않은'):
        work.plan(project, [])
    with pytest.raises(ValueError, match='검사 설정 없음'):
        work.plan(tmp_path, ['test'])


def test_pass_fail_and_log_evidence(project):
    plan = work.plan(project, ['test', 'build'])
    results = [work.run_check(project, name, 10, plan['fingerprint']) for name in ['test', 'build']]
    assert [r['ok'] for r in results] == [True, False]
    assert [r['exit_code'] for r in results] == [0, 7]
    assert 'build failed' in Path(results[1]['log_path']).read_text()


def test_changed_configuration_requires_replanning(project):
    plan = work.plan(project, ['test'])
    (project / 'package.json').write_text('{"name":"changed"}')
    with pytest.raises(ValueError, match='설정이 바뀌었'):
        work.run_check(project, 'test', 10, plan['fingerprint'])


def test_timeout_and_literal_argv_are_preserved(project):
    literal = '$(touch never-created); spaced "argument"'
    (project / 'webapp-checks.json').write_text(json.dumps({'checks': [
        {'name': 'echo', 'argv': [sys.executable, '-c', 'import sys;print(sys.argv[1])', literal]},
        {'name': 'slow', 'argv': [sys.executable, '-c', 'import time;time.sleep(20)']},
    ]}))
    plan = work.plan(project, ['echo', 'slow'])
    result = work.run_check(project, 'echo', 10, plan['fingerprint'])
    assert literal in result['output_tail'] and not (project / 'never-created').exists()
    slow = work.run_check(project, 'slow', .1, plan['fingerprint'])
    assert slow['status'] == 'timeout' and not slow['ok']


def test_actual_ibl_programs_compose_adapter_results(project):
    from ibl_v2_adapters import Adapter, load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    registry = load_registry()
    registry['self:script'] = Adapter({
        'version': 1, 'params': {'op': 'Text', 'id': 'Text', 'args': 'Record'},
        'result': 'Unknown', 'effects': ['write_external'],
    }, lambda rt, args: work.execute(args['args']))
    registry['self:read'] = Adapter({
        'version': 1, 'params': {'path': 'Text', 'limit': 'Number'},
        'result': 'Unknown', 'effects': ['read_external'],
    }, lambda rt, args: {'text': Path(args['path']).read_text()})
    for file, call in [('webapp_prepare.ibl', '[fn:웹앱작업준비]{프로젝트:$프로젝트}'),
                       ('webapp_check.ibl', '[fn:웹앱검사하기]{프로젝트:$프로젝트}')]:
        source = (ROOT / 'data/idioms' / file).read_text() + '\n' + call
        inputs = {'프로젝트': str(project)}
        plan = compile_program(source, registry, inputs)
        assert not plan.issues, plan.report()
        out = Runtime(plan, inputs).run()
        assert out['success'], out
        if file == 'webapp_check.ibl':
            assert out['value']['ok'] is False
            assert out['value']['failed'] == 1
            assert [x['status'] for x in out['value']['items']] == ['passed', 'failed']
        else:
            assert len(out['value']['documents']) == 2


def test_seed_definitions_are_canonical_and_non_promoted():
    seeds = json.loads((ROOT / 'data/idioms/webapp_seeds.json').read_text())
    names = {'웹앱작업준비': 'webapp_prepare.ibl', '웹앱검사하기': 'webapp_check.ibl'}
    for row in seeds:
        assert not row.get('always_on', False)
        if row.get('alias'):
            assert row['ibl_code'] == (ROOT / 'data/idioms' / names[row['alias']]).read_text().strip()


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
