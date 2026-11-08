"""Real IBL source edges determine which calculations become stale."""
import boot_paths  # noqa: F401
from pathlib import Path

from test_situation_evidence import active, module  # noqa: F401
from ibl_v2_adapters import load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime


def test_actual_file_calculation_tracks_only_used_inputs(active, tmp_path):
    path = tmp_path / 'values.json'
    other = tmp_path / 'other.json'
    path.write_text('{"amount":10}')
    other.write_text('{"amount":99}')
    code = ('$unused=[self:read]{path:$other}; $r=[self:read]{path:$source}; '
            'return $r.data.amount*2')
    inputs = {'source': str(path), 'other': str(other)}
    registry = load_registry(str(Path(__file__).resolve().parents[1]))
    plan = compile_program(code, registry, inputs)
    assert not plan.issues, plan.issues
    out = Runtime(plan, inputs).run()
    assert out['success'] and out['value'] == 20, out
    rows = [r for r in active.situation.snapshot()['observations'] if r['latest']['facet'] == 'derived_result']
    assert len(rows) == 1
    relations = rows[0]['latest']['relation']
    assert [r['subject']['address'] for r in relations] == [str(path)]
    module('essentials_file_io').atomic_write_text(other, '{"amount":999}')
    row = next(r for r in active.situation.snapshot()['observations'] if r['latest']['facet'] == 'derived_result')
    assert row['availability'] != 'needs_recheck'
    module('essentials_file_io').atomic_write_text(path, '{"amount":20}')
    row = next(r for r in active.situation.snapshot()['observations'] if r['latest']['facet'] == 'derived_result')
    assert row['availability'] == 'needs_recheck'


def test_edit_effect_survives_later_transformation_failure(active, tmp_path):
    path = tmp_path / 'draft.txt'
    path.write_text('OLD')
    code = '[self:edit]{path:$path,old_string:"OLD",new_string:"NEW"} >> [table:each]{return 1} ?? "FAIL"'
    inputs = {'path': str(path)}
    plan = compile_program(code, load_registry(str(Path(__file__).resolve().parents[1])), inputs)
    assert not plan.issues, plan.issues
    runtime = Runtime(plan, inputs)
    result = runtime.run()
    assert path.read_text() == 'NEW'
    assert result['success'] and result['value'] == 'FAIL', result
    # Catch transforms the value, not the already completed file operation.
    assert any(row.get('kind') == 'tool_evidence' for row in runtime.trace)
    observations = active.situation.snapshot()['observations']
    assert any(row['latest']['subject'].get('address') == str(path) for row in observations)


if __name__ == '__main__':
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
