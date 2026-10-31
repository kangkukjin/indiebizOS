"""수명 기록은 실행·수리·검증을 구분하고 현재 구현에만 검증을 연결한다."""
import boot_paths  # noqa: F401
import pytest
import capability_history as h


def item(implementation='one', dependency='base', created=None):
    return {'kind': 'action', 'name': 'sense:sample', 'implementation_revision': implementation,
            'dependency_revision': dependency, 'revision': implementation + ':' + dependency,
            'created_at': created}


@pytest.fixture
def path(tmp_path):
    return tmp_path / 'history.db'


def verify(path, revision='one:base', outcome='passed', scope='fixture'):
    return h.record('action:sense:sample', 'verified', revision, scope=scope, outcome=outcome,
                    evidence='pytest fixture receipt', path=path)


def test_unknown_birth_is_not_install_date_and_execution_is_not_verification(path):
    h.observe({'action:sense:sample': item()}, path)
    h.record_execution('action:sense:sample', True, path=path)
    row = h.rows(path)[0]
    assert row['created_at'] is None and row['first_observed_at']
    assert row['implementation_changed_at'] is None
    assert row['last_execution']['success'] == 1
    assert row['verification_status'] == 'unverified' and row['last_verified_at'] is None


def test_change_stales_verification_and_rejects_old_receipt(path, monkeypatch):
    monkeypatch.setattr(h, 'now', lambda: '2026-10-20T00:00:00+00:00')
    h.observe({'action:sense:sample': item(created='2026-01-01')}, path)
    verify(path)
    monkeypatch.setattr(h, 'now', lambda: '2026-10-21T00:00:00+00:00')
    h.observe({'action:sense:sample': item('two', created='2026-10-21')}, path)
    row = h.rows(path)[0]
    assert row['created_at'] == '2026-01-01'
    assert row['verification_status'] == 'stale'
    assert row['implementation_changed_at'] == h.now()
    assert row['last_verified_at'] == '2026-10-20T00:00:00+00:00'
    with pytest.raises(ValueError, match='REVISION_CHANGED'):
        verify(path)
    verify(path, 'two:base')
    assert h.rows(path)[0]['verification_status'] == 'current'


def test_dependency_change_does_not_rewrite_implementation_age(path):
    h.observe({'action:sense:sample': item()}, path)
    verify(path)
    h.observe({'action:sense:sample': item(dependency='changed')}, path)
    row = h.rows(path)[0]
    assert row['implementation_changed_at'] is None
    assert row['dependencies_changed_at'] and row['verification_status'] == 'stale'


def test_repair_is_not_verified_and_invalidates_prior_check(path):
    h.observe({'action:sense:sample': item()}, path)
    verify(path)
    h.record('action:sense:sample', 'repaired', 'one:base', evidence='change receipt',
             reason='인증 설정 수리', path=path)
    row = h.rows(path)[0]
    assert row['last_repaired_at'] and row['verification_status'] == 'stale'
    verify(path, outcome='failed')
    assert h.rows(path)[0]['verification_status'] == 'failed'
    verify(path)
    assert h.rows(path)[0]['verification_status'] == 'current'


def test_scopes_are_separate_latest_failure_overrides_its_pass(path):
    h.observe({'action:sense:sample': item()}, path)
    verify(path)
    verify(path, scope='live API', outcome='failed')
    row = h.rows(path)[0]
    assert row['verification_status'] == 'failed'
    assert {r['scope']: r['status'] for r in row['verifications']} == {'fixture': 'current', 'live API': 'failed'}


def test_latest_failure_preserves_historical_success_time(path, monkeypatch):
    h.observe({'action:sense:sample': item()}, path)
    monkeypatch.setattr(h, 'now', lambda: '2026-10-20T00:00:00+00:00')
    verify(path)
    monkeypatch.setattr(h, 'now', lambda: '2026-10-21T00:00:00+00:00')
    verify(path, outcome='failed')
    row = h.rows(path)[0]
    assert row['last_verified_at'] == '2026-10-20T00:00:00+00:00'
    assert row['last_checked_at'] == h.now()
    assert row['verification_status'] == 'failed'


def test_absence_keeps_history_and_pagination(path):
    h.observe({'action:sense:sample': item()}, path)
    verify(path)
    h.observe({}, path)
    assert not h.rows(path)[0]['present']
    with pytest.raises(ValueError, match='존재'):
        verify(path)
    page = h.history('action:sense:sample', limit=2, path=path)
    tail = h.history('action:sense:sample', after=page['next_cursor'], limit=2, path=path)
    assert [r['event'] for r in page['items'] + tail['items']] == ['first_observed', 'verified', 'absent']
    assert tail['next_cursor'] is None


@pytest.mark.parametrize('fields', [{}, {'scope': 'unit', 'outcome': 'passed'},
                                   {'scope': '', 'outcome': 'passed', 'evidence': 'receipt'}])
def test_verification_needs_scope_result_and_evidence(path, fields):
    h.observe({'action:sense:sample': item()}, path)
    with pytest.raises(ValueError):
        h.record('action:sense:sample', 'verified', 'one:base', path=path, **fields)



def test_repair_child_observations_do_not_reach_owner(tmp_path, monkeypatch):
    import os
    import sys
    from pathlib import Path
    from repair_process import run
    owner, child = tmp_path / 'owner', tmp_path / 'candidate'
    child.mkdir()
    monkeypatch.delenv('INDIEBIZ_RUNTIME_STATE_DIR', raising=False)
    monkeypatch.setattr(h, 'get_base_path', lambda: owner)
    ref = {'function_id': 'fixture', 'revision': 'revision'}
    h.record_function_call(ref, 'owner', '1', success=True, dependency_revision='owner')
    code = (f'import sys; sys.path.insert(0, {str(Path(__file__).parent)!r}); import boot_paths; '
            'import capability_history as h; '
            f'h.record_function_call({ref!r}, "child", "1", success=True, dependency_revision="candidate"); '
            f'assert h.function_statistics({ref!r})["success_count"]==1')
    env = {k: v for k, v in os.environ.items() if k != 'INDIEBIZ_RUNTIME_STATE_DIR'}
    result = run([sys.executable, '-c', code], child, env=env, timeout=30)
    assert result.returncode == 0, result.stderr
    assert (child / 'data/capability_history.db').is_file()
    assert h.function_statistics(ref)['success_count'] == 1

if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
