import boot_paths  # noqa: F401
import json
import member_jobs as jobs


def test_ephemeral_delivery_is_session_scoped_once_and_forgets_content():
    jobs._JOBS.clear()
    key = jobs.enqueue('a', json.dumps({'body_session': 'new', 'content': 'private'}))
    assert not jobs.pull_blocking('b', 0, 'new')
    assert not jobs.pull_blocking('a', 0, 'old')
    assert jobs.pull_blocking('a', 0, 'new')[0]['id'] == key
    assert not jobs.pull_blocking('a', 0, 'new')
    jobs.set_result(key, {'private': 'result'})
    assert jobs.wait_result(key, 0) == {'private': 'result'}
    assert jobs.owner_of(key) == 'a'
    assert jobs._JOBS[key]['result'] is None and jobs._JOBS[key]['code'] == ''
    jobs.set_result(key, {'private': 'duplicate'})
    assert jobs.wait_result(key, 0) is None
    jobs._JOBS.clear()
    assert jobs.owner_of(key) is None


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
