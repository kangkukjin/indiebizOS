"""Referenced dependency identity, safe receipt retention and scoped recovery."""
import sqlite3
import time
import pytest
import boot_paths  # noqa
from ibl_v2_compile import compile_program
from ibl_v2_adapters import Adapter
from ibl_v2_runtime import Runtime
from ibl_run_journal import Journal, inspect_run, cleanup_runs
from ibl_v2_ir import Fault


def test_only_used_transitive_native_definitions_and_contracts_pin_plan():
    a = '#!ibl edition=2\n[def:a](){return [fn:b]{}}'
    b = '#!ibl edition=2\n[def:b](){return 2}'
    unused = '#!ibl edition=2\n[def:c](){return 3}'
    source = '[fn:a]{}'
    plan = compile_program(source, definitions={'a':a, 'b':b})
    contract = Adapter({'params':{}, 'result':'Number', 'effects':['pure']}, lambda *_:1)
    grown = compile_program(source, {'x:y':contract}, definitions={'a':a,'b':b,'c':unused})
    assert plan.fingerprint == grown.fingerprint
    changed = compile_program(source, definitions={'a':a, 'b':b.replace('return 2','return 4')})
    assert plan.fingerprint != changed.fingerprint
    assert compile_program('return 21').fingerprint == compile_program('return 21', {'x:y':contract}, definitions={'c':unused}).fingerprint


def test_legacy_static_transitive_assets_are_bounded():
    from ibl_dependencies import legacy_snapshot
    assets = {'a': {'code':'[fn:b]{}'}, 'b':{'code':'[self:time]'}}
    before = legacy_snapshot('a', assets)
    assert legacy_snapshot('a', {**assets, 'c':{'code':'[self:time]'}}) == before
    assert legacy_snapshot('a', {**assets, 'b':{'code':'[self:time]{format:"date"}'}}) != before


def test_script_snapshot_tracks_imports_and_dynamic_selection(tmp_path):
    from ibl_dependencies import script_snapshot
    import yaml
    registry = {'one':{'file':'one.py'}, 'other':{'file':'other.py'}}
    (tmp_path/'registry.yaml').write_text(yaml.safe_dump(registry))
    (tmp_path/'one.py').write_text('import local_part\nprint(local_part.VALUE)')
    (tmp_path/'local_part.py').write_text('VALUE=1')
    (tmp_path/'other.py').write_text('print(2)')
    before = script_snapshot({'id':'one'}, tmp_path)
    dynamic = script_snapshot({}, tmp_path)
    (tmp_path/'other.py').write_text('print(3)')
    assert before == script_snapshot({'id':'one'}, tmp_path)
    assert dynamic != script_snapshot({}, tmp_path)
    (tmp_path/'local_part.py').write_text('VALUE=2')
    assert before != script_snapshot({'id':'one'}, tmp_path)


def test_completed_pruning_keeps_uncertain_interrupted_and_locked(tmp_path):
    plan = compile_program('return 4')
    with Journal(tmp_path, 'completed') as journal:
        completed = journal.run_id
        Runtime(plan, journal=journal).run()
    state = inspect_run(tmp_path, completed)
    assert state['status'] == 'completed' and state['created_at'] <= state['ended_at']
    with Journal(tmp_path, 'uncertain') as journal:
        uncertain = journal.run_id
        journal.begin('write', 'request')
    assert inspect_run(tmp_path, uncertain)['status'] == 'uncertain'
    with Journal(tmp_path, 'interrupted') as journal:
        interrupted = journal.run_id
    assert inspect_run(tmp_path, interrupted)['status'] == 'interrupted'
    with Journal(tmp_path, 'locked') as journal:
        locked = journal.run_id
        Runtime(plan, journal=journal).run()
        assert inspect_run(tmp_path, locked)['locked']
        outcome = cleanup_runs(tmp_path, now=time.time()+40*86400, max_bytes=0)
        assert outcome['removed'] == 1 and outcome['over_capacity']
    assert inspect_run(tmp_path, completed)['status'] == 'unavailable'
    for key in (uncertain, interrupted, locked):
        assert (tmp_path/(key+'.sqlite')).is_file()
    with pytest.raises(Fault):
        with Journal(tmp_path, 'completed', {'run_id':completed}):
            pass


def test_old_journal_without_lifecycle_is_preserved(tmp_path):
    run_id = 'a'*32
    with sqlite3.connect(tmp_path/(run_id+'.sqlite')) as db:
        db.executescript("CREATE TABLE meta(identity TEXT,blocked TEXT); INSERT INTO meta VALUES('x',NULL); CREATE TABLE calls(id TEXT,request TEXT,receipt TEXT);")
    assert inspect_run(tmp_path, run_id)['status'] == 'interrupted'
    assert cleanup_runs(tmp_path, max_bytes=0)['removed'] == 0


def test_scoped_recovery_route_uses_same_project(tmp_path, monkeypatch):
    import asyncio
    import ibl_run_journal
    from api_ibl import RecoverRequest, recover_ibl_result
    monkeypatch.setattr(ibl_run_journal, 'journal_root', lambda p: tmp_path / p)
    with Journal(tmp_path/'one', 'p') as journal:
        run_id = journal.run_id
        Runtime(compile_program('return 1'), journal=journal).run()
    assert asyncio.run(recover_ibl_result(RecoverRequest(run_id=run_id, project_path='one')))['status'] == 'completed'
    assert asyncio.run(recover_ibl_result(RecoverRequest(run_id=run_id, project_path='two')))['status'] == 'unavailable'


def test_script_relative_import_dependency(tmp_path):
    from ibl_dependencies import script_snapshot
    (tmp_path/'registry.yaml').write_text('one: {file: main.py}')
    (tmp_path/'main.py').write_text('import pkg.work')
    pkg = tmp_path/'pkg'; pkg.mkdir()
    (pkg/'__init__.py').write_text('')
    (pkg/'work.py').write_text('from . import data')
    (pkg/'data.py').write_text('N=1')
    first = script_snapshot({'id':'one'}, tmp_path)
    (pkg/'data.py').write_text('N=2')
    assert first != script_snapshot({'id':'one'}, tmp_path)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
