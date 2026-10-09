"""기기 전달 원장의 재기동·지연·동시 회수 계약."""
import boot_paths  # noqa: F401
import json
import threading

import phone_jobs as jobs


def test_restart_preserves_queue_result_and_owner(monkeypatch):
    queued = jobs.enqueue('pc', '{}')
    done = jobs.enqueue('pc', '{}')
    jobs.set_result(done, {'exit': 0})
    monkeypatch.setattr(jobs, '_GENERATION', 'after-restart')
    assert jobs.owner_of(done) == 'pc'
    assert jobs.peek_result(done) == {'result': {'exit': 0}}
    assert [x['id'] for x in jobs.pull_blocking('pc')] == [queued]


def test_delivered_job_is_not_replayed_after_restart(monkeypatch):
    jid = jobs.enqueue('pc', '{}')
    assert jobs.pull_blocking('pc')[0]['id'] == jid
    monkeypatch.setattr(jobs, '_GENERATION', 'after-restart')
    assert jobs.pull_blocking('pc') == []
    assert jobs.job_status(jid)['state'] == 'unknown'
    jobs.set_result(jid, {'exit': 0})
    assert jobs.peek_result(jid) == {'result': {'exit': 0}}


def test_long_job_owner_survives_other_enqueues(monkeypatch):
    now = jobs.time.time()
    jid = jobs.enqueue('pc', json.dumps({'timeout': 1800}))
    jobs.pull_blocking('pc')
    monkeypatch.setattr(jobs.time, 'time', lambda: now + 1600)
    jobs.enqueue('other', '{}')
    assert jobs.owner_of(jid) == 'pc'
    jobs.set_result(jid, {'stdout': 'done'})
    assert jobs.wait_result(jid, 0) == {'stdout': 'done'}


def test_expired_and_cancelled_are_not_running(monkeypatch):
    now = jobs.time.time()
    expired = jobs.enqueue('pc', '{}')
    cancelled = jobs.enqueue('pc', '{}')
    assert jobs.cancel_pending(cancelled)
    monkeypatch.setattr(jobs.time, 'time', lambda: now + jobs.JOB_TTL + 1)
    assert jobs.pull_blocking('pc') == []
    assert jobs.job_status(expired)['state'] == 'expired'
    assert jobs.job_status(cancelled)['state'] == 'cancelled'


def test_duplicate_result_does_not_overwrite_or_resurrect_consumed():
    jid = jobs.enqueue('pc', '{}')
    jobs.set_result(jid, {'exit': 0})
    assert jobs.wait_result(jid, 0) == {'exit': 0}
    jobs.set_result(jid, {'exit': 1})
    assert jobs.peek_result(jid) == {'consumed': True}
    with jobs._db() as conn:
        assert json.loads(conn.execute('select result from jobs where id=?', (jid,)).fetchone()[0]) == {'exit': 0}


def test_concurrent_polls_deliver_once():
    jid = jobs.enqueue('pc', '{}')
    got = []
    threads = [threading.Thread(target=lambda: got.extend(jobs.pull_blocking('pc'))) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert [row['id'] for row in got] == [jid]


def test_result_survives_five_minutes(monkeypatch):
    now = jobs.time.time()
    jid = jobs.enqueue('pc', '{}')
    jobs.set_result(jid, {'exit': 0})
    monkeypatch.setattr(jobs.time, 'time', lambda: now + 3600)
    assert jobs.peek_result(jid) == {'result': {'exit': 0}}


def test_result_and_owner_survive_new_process():
    import os
    import subprocess
    import sys
    jid = jobs.enqueue('pc', '{}')
    jobs.pull_blocking('pc')
    script = """import boot_paths, phone_jobs
import sys
assert phone_jobs.owner_of(sys.argv[1]) == 'pc'
assert phone_jobs.pull_blocking('pc') == []
phone_jobs.set_result(sys.argv[1], {'exit': 0, 'from': 'new-process'})
"""
    env = dict(os.environ, PYTHONPATH=str(__import__('pathlib').Path(__file__).parent))
    subprocess.run([sys.executable, '-c', script, jid], env=env, check=True)
    assert jobs.peek_result(jid)['result']['from'] == 'new-process'


if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
