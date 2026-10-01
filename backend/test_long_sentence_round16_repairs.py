"""문맥 비교 하네스는 불완전한 상태 복원을 실행 전에 거절한다."""
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest


@pytest.fixture
def harness(tmp_path, monkeypatch):
    root = tmp_path
    work = root / 'work'
    here = root / 'prompts'
    for folder in (work, here, root / 'data', root / 'project'):
        folder.mkdir()
    def dump(path, value):
        path.write_text(json.dumps(value))
    monkeypatch.setitem(sys.modules, 'fixture', SimpleNamespace(
        ROOT=root, WORK=work, HERE=here, dump=dump))
    path = Path(__file__).resolve().parents[1] / 'docs/experiments/long_sentence_imagination/round_16/harness.py'
    spec = importlib.util.spec_from_file_location('lsi16_test_harness', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    c = {'project': {'id': 'fixture', 'path': str(root / 'project')},
         'agents': {'seed': {'id': 'worker'}}}
    dump(work / 'control.json', c)
    for filename, value in (('codex_sessions.json', {'fixture:worker@rehearsal#1': 'seed-thread'}),
                            ('codex_session_sizes.json', {'fixture:worker@rehearsal#1': 100})):
        dump(root / 'data' / filename, value)
    db = sqlite3.connect(root / 'project/conversations.db')
    for table in ('messages', 'tasks', 'pursuit', 'pursuit_event', 'pursuit_turn'):
        db.execute(f'CREATE TABLE {table}(id TEXT, state TEXT)')
    db.commit()
    backup = root / 'data/_backups/2026-10-01_lsi16_seed'
    backup.mkdir(parents=True)
    with sqlite3.connect(backup / 'conversations.db') as target:
        db.backup(target)
    db.close()
    lineage = work / 'lineage.jsonl'
    lineage.write_text('seed reference\n')
    dump(work / 'seed_snapshot.json', {'sessions': module.own_sessions(c),
                                      'lineages': {str(lineage): lineage.read_text()}})
    (here / 'prompt_warm.txt').write_text('요구 일부 변경')
    return module


def test_unchanged_seed_passes_readonly_gate(harness):
    harness.warm_preflight()


@pytest.mark.parametrize('table', ['messages', 'tasks', 'pursuit', 'pursuit_event', 'pursuit_turn'])
def test_changed_state_blocks_before_model_call(harness, monkeypatch, table):
    with sqlite3.connect(harness.ROOT / 'project/conversations.db') as db:
        db.execute(f'INSERT INTO {table} VALUES (?,?)', ('cold', 'changed'))
    monkeypatch.setattr(harness.requests, 'post', lambda *a, **k: pytest.fail('blocked request sent'))
    with pytest.raises(RuntimeError, match='state changed'):
        harness.run('warm')


def test_partial_warm_rollback_is_blocked_without_mutation(harness):
    before = (harness.WORK / 'seed_snapshot.json').read_bytes()
    with pytest.raises(RuntimeError, match='partial warm rollback'):
        harness.switch('warm')
    assert before == (harness.WORK / 'seed_snapshot.json').read_bytes()


@pytest.mark.parametrize('surface', ['session', 'lineage', 'cold'])
def test_changed_context_blocks_warm(harness, surface):
    if surface == 'session':
        (harness.ROOT / 'data/codex_sessions.json').write_text('{}')
    elif surface == 'lineage':
        (harness.WORK / 'lineage.jsonl').write_text('cold reference')
    else:
        (harness.WORK / 'cold_started.json').write_text('{}')
    with pytest.raises(RuntimeError):
        harness.warm_preflight()


@pytest.mark.parametrize('new_thread', [False, True])
def test_postflight_checks_thread_identity_not_growing_history_size(harness, monkeypatch, new_thread):
    def command(*args, **kwargs):
        path = harness.ROOT / 'data/codex_session_sizes.json'
        path.write_text(json.dumps({'fixture:worker@rehearsal#1': 500}))
        if new_thread:
            (harness.ROOT / 'data/codex_sessions.json').write_text(
                json.dumps({'fixture:worker@rehearsal#1': 'compacted-thread'}))
        return SimpleNamespace(text='result', status_code=200)
    monkeypatch.setattr(harness.requests, 'post', command)
    harness.run('warm')
    result = json.loads((harness.WORK / 'warm_context_check.json').read_text())
    assert result['valid'] is not new_thread
    assert (harness.WORK / 'warm_response.json').read_text() == 'result'


def test_cold_cannot_inherit_warm_artifacts(harness):
    (harness.WORK / 'warm_started.json').write_text('{}')
    with pytest.raises(RuntimeError, match='independent seed'):
        harness.switch('cold')


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
