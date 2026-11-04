"""같은 산출물 판본·호출 계보의 비용만 연결하고 미측정을 보존한다."""
import boot_paths  # noqa: F401
import hashlib
import json
import sqlite3

import pytest
from research_measurement import aggregate, measure


@pytest.fixture
def ledger(tmp_path):
    path = tmp_path / 'pulse.db'
    with sqlite3.connect(path) as db:
        db.executescript('''CREATE TABLE episode_log(id,task_id,run_id,started_at,ended_at,total_ms);
            INSERT INTO episode_log VALUES(1,'task','root','start','end',1000);
            CREATE TABLE trajectory_event(run_id,event_seq,episode_id,parent_run_id,kind,data);''')
    def insert(kind, data, *, run='root', episode=1):
        with sqlite3.connect(path) as db:
            db.execute('INSERT INTO trajectory_event VALUES(?,(SELECT COUNT(*) FROM trajectory_event),?,?,?,?)',
                       (run, episode, '', kind, json.dumps(data)))
    return path, insert


def test_shared_usage_identity_not_response_snapshots_and_postprocessing(ledger):
    path, insert = ledger
    insert('model.call_started', {'call_id': 'a'})
    usage = {'call_id': 'a', 'usage_id': 'u', 'accounting': 'billable_usage',
             'input': 100, 'output': 30, 'cache_read': 90, 'cache_create': 0, 'reasoning': 20}
    insert('model.usage', usage)
    insert('model.usage', usage)
    insert('model.response_snapshot', {**usage, 'input': 999})
    insert('model.call_finished', {'call_id': 'a'})
    insert('model.call_started', {'call_id': 'b', 'parent_call_id': 'a'}, run='post', episode=None)
    insert('model.usage', {**usage, 'usage_id': 'v', 'call_id': 'b', 'parent_call_id': 'a',
                          'input': 10, 'output': 2, 'cache_read': 0, 'reasoning': 0, 'role': 'distill'}, run='post', episode=None)
    insert('model.call_finished', {'call_id': 'b'}, run='post', episode=None)
    before = path.read_bytes()
    result = aggregate(path, 1)
    assert result['input_plus_output'] == 142 and result['measured']['reasoning'] == 20
    assert result['duplicates_removed'] == 1 and result['joined_runs'] == ['post', 'root']
    assert result['roles']['distill']['input'] == 10
    assert result['unmeasured_calls'] == [] and path.read_bytes() == before


def test_missing_conflicting_retry_counts_and_human_revision(ledger, tmp_path):
    path, insert = ledger
    insert('model.call_started', {'call_id': 'failed'})
    insert('model.call_finished', {'call_id': 'failed'})
    usage = {'accounting': 'billable_usage', 'usage_id': 'retry', 'call_id': 'retry', 'input': 10}
    insert('model.usage', usage)
    insert('model.usage', {**usage, 'input': 20})
    artifact = tmp_path / 'answer.md'
    artifact.write_text('관측은 있고 전체 효과는 미확인이다.')
    checksum = hashlib.sha256(artifact.read_bytes()).hexdigest()
    review = {'artifact_sha256': checksum, 'active_review_seconds': 15, 'active_edit_seconds': None,
              'critical_claim_changes': 1, 'quality': {'factual_errors': 1}, 'usable_result_elapsed_ms': None}
    result = measure(path, 1, artifact, task='synthetic', variant='candidate', review=review)
    assert result['cost']['measured']['output'] is None
    assert result['cost']['input_plus_output'] is None and result['cost']['conflicts']
    assert result['cost']['unmeasured_calls'][0]['call_id'] == 'failed'
    assert result['human_review']['active_edit_seconds'] is None and not result['effect_established']
    artifact.write_text('수정된 결과')
    with pytest.raises(ValueError, match='다른 산출물'):
        measure(path, 1, artifact, task='synthetic', variant='candidate', review=review)


def test_empty_ledger_is_unmeasured_not_zero(ledger):
    result = aggregate(ledger[0], 1)
    assert result['input_plus_output'] is None and result['measured']['input'] is None
    assert not result['complete']


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
