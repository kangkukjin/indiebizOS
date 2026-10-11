"""Read-derived code reuse must not spend a new-code gate twice."""
import boot_paths  # noqa: F401
from pathlib import Path

import pytest
import selfbuild_gate as gate


@pytest.fixture(autouse=True)
def ledger():
    gate.reset('purchase-reuse')
    gate.reset('other-reuse')
    yield
    gate.reset('purchase-reuse')
    gate.reset('other-reuse')


def body(n=180, prefix='original'):
    return '\n'.join(f'{prefix}_{i} = {i}' for i in range(n))


def test_read_copy_with_small_policy_change_is_not_new_implementation(tmp_path):
    old = body()
    gate.note_code_read('purchase-reuse', str(tmp_path/'old.py'), old)
    changed = old.replace('original_7 = 7', 'original_7 = 3')
    assert gate.note_code_write('purchase-reuse', str(tmp_path/'new.py'), changed) is None
    assert gate.state('purchase-reuse')['lines'] == 0
    assert gate.state('purchase-reuse')['consulted'] is None


def test_reading_code_does_not_exempt_new_implementation(tmp_path):
    old = body()
    gate.note_code_read('purchase-reuse', str(tmp_path/'old.py'), old)
    assert gate.note_code_write('purchase-reuse', str(tmp_path/'new.py'), old+'\n'+body(prefix='new'))
    assert gate.state('purchase-reuse')['lines'] == 180


def test_repeated_matching_lines_only_discount_original_multiplicity(tmp_path):
    gate.note_code_read('purchase-reuse', str(tmp_path/'old.py'), 'x=1')
    assert gate.note_code_write('purchase-reuse', str(tmp_path/'new.py'), '\n'.join(['x=1']*180))
    assert gate.state('purchase-reuse')['lines'] == 179


def test_sources_do_not_cross_agents_turns_or_noncode_files(tmp_path):
    old = body()
    gate.note_code_read('other-reuse', str(tmp_path/'old.py'), old)
    gate.note_code_read('purchase-reuse', str(tmp_path/'old.md'), old)
    assert gate.note_code_write('purchase-reuse', str(tmp_path/'new.py'), old)
    gate.reset('purchase-reuse')
    gate.note_code_read('purchase-reuse', str(tmp_path/'old.py'), old)
    gate.reset('purchase-reuse')
    assert gate.note_code_write('purchase-reuse', str(tmp_path/'new.py'), old)


def test_source_memory_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, '_MAX_KEPT_CODE', 100)
    monkeypatch.setattr(gate, '_MAX_READ_SOURCES', 2)
    for i in range(4):
        gate.note_code_read('purchase-reuse', str(tmp_path/f'{i}.py'), 'a'*40)
    sources = gate._entry('purchase-reuse').read_sources
    assert list(sources) == [str(tmp_path/'2.py'),str(tmp_path/'3.py')]
    assert sum(map(len,sources.values())) <= 100


def test_real_file_read_then_write_reuses_code(tmp_path):
    import importlib.util
    from tool_context import ToolContext
    path = Path(__file__).resolve().parents[1] / 'data/packages/installed/tools/system_essentials/handler.py'
    spec = importlib.util.spec_from_file_location('selfbuild_read_handler', path)
    handler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(handler)
    old = body()
    source=tmp_path/'source.py'; source.write_text(old)
    context=ToolContext(tool_name='read_file',project_path=str(tmp_path),agent_id='purchase-reuse')
    result=handler.execute({'path':str(source)},context)
    assert result == old
    assert gate.note_code_write('purchase-reuse',str(tmp_path/'copy.py'),old.replace('original_3 = 3','original_3 = 7')) is None
    assert gate.state('purchase-reuse')['fired'] == 0


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
