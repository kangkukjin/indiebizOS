"""Current source survives authoring, storage, scheduling and rendering boundaries."""
import boot_paths  # noqa: F401
import pytest
from ibl_translate import translated_source, strip_code_fence
from ibl_edition import pin_source, source_context


def test_translation_preserves_complete_source_and_rejects_prose():
    source = '#!ibl edition=2\n$x = [1,2]\nreturn len($x)'
    assert translated_source('```ibl\n'+source+'\n```') == source
    assert strip_code_fence(source) == source
    with pytest.raises(Exception):
        translated_source('실행하세요: [self:write]{path:"a",content:"b"}')
    assert translated_source('return 0').endswith('return 0')


def test_new_storage_pins_context_without_changing_existing_source():
    assert pin_source('return 1') == 'return 1'
    with source_context(2):
        assert pin_source('return 1') == '#!ibl edition=2\nreturn 1'
        assert pin_source('#!ibl edition=1\n[self:time]{}').startswith('#!ibl edition=1')
        assert pin_source('') == ''
    assert pin_source('return 1') == 'return 1'


def test_scheduled_source_preserves_inputs_actor_and_origin(tmp_path, monkeypatch):
    import ibl_run_journal
    import thread_context as tc
    from calendar_actions import CalendarActionsMixin
    monkeypatch.setattr(ibl_run_journal, 'journal_root', lambda _: tmp_path/'runs')
    original = tc.snapshot()
    try:
        result = CalendarActionsMixin._execute_scheduled_pipeline(
            '#!ibl edition=2\nreturn $n * 3', str(tmp_path), 'scheduled-agent', inputs={'n':7})
        assert result['success'] and result['value'] == 21
        assert tc.snapshot() == original
    finally:
        tc.restore(original)


def test_saved_current_function_runs_through_existing_entry(tmp_path, monkeypatch):
    import workflow_store, ibl_usage_db, ibl_run_journal
    from workflow_engine import execute_workflow_action, execute_workflow
    monkeypatch.setattr(workflow_store, '_get_workflows_path', lambda: tmp_path)
    monkeypatch.setattr(ibl_usage_db, 'DB_PATH', str(tmp_path/'usage.db'))
    monkeypatch.setattr(ibl_usage_db.IBLUsageDB, '_instance', None)
    monkeypatch.setattr(ibl_run_journal, 'journal_root', lambda _: tmp_path/'runs')
    saved = execute_workflow_action('workflow', {'op':'save','code':'[def:곱]($x){return $x * 4}'}, str(tmp_path))
    assert saved['success'], saved
    result = execute_workflow('곱', str(tmp_path), params={'x':5})
    assert result['success'] and result['value'] == 20


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
