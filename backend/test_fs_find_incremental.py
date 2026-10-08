"""Replay the October 8 incremental POS report on isolated, real files."""
import boot_paths  # noqa: F401
import importlib.util
import json
import os
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from ibl_v2_adapters import load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Budget, Runtime

ROUND = Path(__file__).resolve().parents[1] / 'docs/experiments/long_sentence_imagination/round_34'


def test_original_failure_and_repaired_full_sequence(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('_incremental_pos', ROUND / 'harness/prepare.py')
    data = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(data)
    data.OUT = tmp_path
    monkeypatch.setattr(data.time, 'sleep', lambda _: None)
    data.generate()
    data.stage(1, 'trainer')
    inputs = {k: str(tmp_path / v) for k, v in
              [('inbox', 'inbox/trainer'), ('statedir', 'state'), ('out', 'result')]}
    for name in ('state', 'result'):
        (tmp_path / name).mkdir()
    state = tmp_path / 'state/state.json'
    calls = []
    registry = load_registry(str(tmp_path))
    for name in ('self:read', 'self:write'):
        original = registry[name]
        def tracked(runtime, args, *, original=original, name=name, **kwargs):
            calls.append((name, args['path']))
            return original.run(runtime, args, **kwargs)
        registry[name] = replace(original, run=tracked)

    def execute(filename, *, store_kind=False):
        calls.clear()
        source = (ROUND / 'drafts' / filename).read_text()
        if store_kind:
            source = source.replace('$run = {', '$by_store_kind = $allcontrib >> [table:groupby]{by:["store","kind"],agg:{amount:["sum","amount"],qty:["sum","qty"]}} >> [table:sort]{by:["store","kind"]}\n$run = {')
            source = source.replace('totals_by_store:$by_store,', 'totals_by_store:$by_store,totals_by_store_kind:$by_store_kind,')
        plan = compile_program(source, registry, inputs)
        result = Runtime(plan, inputs, budget=Budget(steps=1_000_000, rows=100_000)).run()
        assert result['success'], result
        parsed = json.loads((tmp_path / 'result/result.json').read_text())
        reads = sum(name == 'self:read' and '/inbox/' in path for name, path in calls)
        writes = sum(name == 'self:write' and path == str(state) for name, path in calls)
        return parsed, reads, writes

    def oracle(run=3):
        data.oracle(run, 'trainer')
        return json.loads((tmp_path / f'oracle/trainer_run{run}.json').read_text())

    def verify(actual, expected):
        for key in ('totals_by_sku', 'totals_by_store', 'files_total', 'rows_total'):
            assert actual[key] == expected[key], key
        assert sorted(row['name'] for row in actual['run']['failed']) == expected['failed_files']

    def restored_edit():
        path = data.inbox('trainer') / data.day_name(7)
        before = path.stat()
        content = path.read_text()
        # A new same-size, same-nanosecond timestamp variant on generated source.
        rows = json.loads(content)
        amount = rows[0]['amount']
        changed = amount + 1
        assert len(str(changed)) == len(str(amount))
        content = content.replace(f'"amount": {amount}', f'"amount": {changed}', 1)
        path.write_text(content)
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        assert (path.stat().st_size, path.stat().st_mtime_ns) == (before.st_size, before.st_mtime_ns)

    # Preserve and reproduce v0's successful-but-wrong behavior, then migrate its state.
    v0 = 'main_v0.ibl'
    repaired = 'main_repaired_incremental.ibl'
    old, _, _ = execute(v0)
    restored_edit()
    stale, reads, writes = execute(v0)
    expected = oracle()
    assert stale['totals_by_sku'] == old['totals_by_sku'] != expected['totals_by_sku']
    assert reads == 0 and writes == 1
    migrated, reads, writes = execute(repaired)
    verify(migrated, expected)
    assert reads == 10 and writes == 1  # no stored hashes: conservatively rebuild once

    # Reset only this private dataset and replay the report's four original stages.
    state.unlink()
    evidence = []
    for run, expected_reads in ((1, 10), (2, 11), (3, 0), (4, 10)):
        data.stage(run, 'trainer')
        previous = (state.read_bytes(), state.stat().st_mtime_ns) if state.exists() else None
        actual, reads, writes = execute(repaired)
        expected = oracle(run)
        verify(actual, expected)
        for key in ('processed_new', 'reprocessed'):
            assert actual['run'][key] == expected['run'][key]
        assert reads == expected_reads and writes == (0 if run == 3 else 1)
        if run == 3:
            assert (state.read_bytes(), state.stat().st_mtime_ns) == previous
            variant, variant_reads, variant_writes = execute(repaired, store_kind=True)
            verify(variant, expected)
            assert variant['totals_by_store_kind'] == expected['totals_by_store_kind']
            assert variant_reads == variant_writes == 0
        evidence.append({'run': run, 'business_reads': reads, 'state_writes': writes,
                         'files': actual['files_total'], 'rows': actual['rows_total']})

    # Repair the corrupt file, then repeat the restored-timestamp attack with hashes present.
    shutil.copy(data.OUT / 'source/all' / data.day_name(25), data.inbox('trainer') / data.day_name(25))
    recovered, reads, writes = execute(repaired)
    verify(recovered, oracle())
    assert reads == 1 and recovered['run']['processed_new'] == [data.day_name(25)]
    restored_edit()
    corrected, reads, writes = execute(repaired)
    verify(corrected, oracle())
    assert reads == 1 and corrected['run']['reprocessed'] == [data.day_name(7)]
    # Removal must remove the old contribution without rereading unchanged inputs.
    (data.inbox('trainer') / data.day_name(1)).unlink()
    removed, reads, writes = execute(repaired)
    verify(removed, oracle())
    assert reads == 0 and writes == 1 and removed['files_total'] == 29
    assert '집계는 이전과 같다' not in (tmp_path / 'result/summary.md').read_text()
    for path in data.inbox('trainer').glob('*.json'):
        path.unlink()
    empty, reads, writes = execute(repaired)
    verify(empty, oracle())
    assert reads == 0 and writes == 1 and empty['files_total'] == 0
    _, reads, writes = execute(repaired)
    assert reads == writes == 0
    print('INCREMENTAL_REPLAY', json.dumps(evidence))


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
