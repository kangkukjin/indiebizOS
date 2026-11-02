"""Completed research accounting excludes snapshots and reports missing usage."""
import importlib.util
import json
from pathlib import Path
import sqlite3


def test_cost_joins_child_calls_without_double_counting(tmp_path):
    path = Path(__file__).resolve().parents[1] / 'docs/experiments/episode_5767_repair/cost.py'
    spec = importlib.util.spec_from_file_location('repair_cost', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    db = tmp_path / 'pulse.db'
    with sqlite3.connect(db) as conn:
        conn.executescript('''CREATE TABLE episode_log(id,task_id,run_id,started_at,ended_at,total_ms);
            INSERT INTO episode_log VALUES(1,'task','root','a','b',10);
            CREATE TABLE trajectory_event(run_id,event_seq,episode_id,parent_run_id,kind,data);''')
        events = [
            ('root', 1, 'model.call_started', {'call_id': 'a'}),
            ('root', 1, 'model.call_finished', {'call_id': 'a'}),
            ('root', 1, 'model.usage', {'call_id': 'a', 'round_index': 1, 'accounting': 'billable_usage',
                                     'input': 10, 'output': 2, 'cache_read': 8, 'cache_create': 0}),
            ('root', 1, 'model.usage', {'call_id': 'a', 'round_index': 1, 'accounting': 'billable_usage',
                                     'input': 10, 'output': 2, 'cache_read': 8, 'cache_create': 0}),
            ('root', 1, 'model.response_observed', {'call_id': 'a', 'input': 999}),
            ('child', 2, 'model.call_started', {'call_id': 'b', 'parent_call_id': 'a'}),
            ('child', 2, 'model.call_finished', {'call_id': 'b', 'parent_call_id': 'a'}),
            ('other', 3, 'model.usage', {'call_id': 'c', 'input': 999, 'accounting': 'billable_usage'}),
        ]
        for index, (run, episode, kind, data) in enumerate(events):
            conn.execute('INSERT INTO trajectory_event VALUES(?,?,?,?,?,?)',
                         (run, index, episode, '', kind, json.dumps(data)))
    before = db.read_bytes()
    result = module.aggregate(db, 1)
    assert result['input_plus_output'] == 12
    assert result['measured']['cache_read'] == 8
    assert result['duplicates_removed'] == 1 and result['billable_records'] == 1
    assert result['joined_runs'] == ['child', 'root']
    assert result['unmeasured_calls'][0]['call_id'] == 'b'
    assert result['unmeasured_calls'][0]['reason'] == 'finished_without_usage'
    assert not result['complete'] and db.read_bytes() == before


if __name__ == '__main__':
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
