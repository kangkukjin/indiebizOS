"""일반 심층연구의 자료실 신원·MCP 연결·대화 격리·취소 회귀."""
from pathlib import Path
from types import SimpleNamespace
import pytest
import boot_paths  # noqa: F401
import thread_context as tc
from research_context import TurnResearch, current, adopt_execution, before
from conversation_sessions import Binding, scope as conversation_scope
from research_store import ResearchStore
from research_library import ResearchLibrary


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    import research_capture
    from project_manager import ProjectManager
    monkeypatch.setattr(ProjectManager, 'list_projects', lambda self: [{'id': 'general', 'name': '일반'}])
    monkeypatch.setattr(ProjectManager, 'get_project_path', lambda self, key: str(tmp_path))
    monkeypatch.setattr('research_runner._search', None)
    tc.set_current_agent_id('agent')
    tc.set_current_task_id('task')
    yield SimpleNamespace(project_path=tmp_path, config={'id': 'agent'}), tmp_path
    tc.clear_all_context()


def test_only_deep_research_activates_and_mcp_cannot_cross_project(workspace):
    runner, path = workspace
    with TurnResearch() as turn:
        assert turn.activate(runner, {}, '안녕') == ''
        assert not (path / 'research').exists()
        guidance = turn.activate(runner, {'_research_plan': {'path': 'plan.md'}}, '연구해')
        assert 'self:notebook' in guidance
        ctx = dict(current())
        with adopt_execution('agent', 'task', str(path)):
            assert current()['thread_id'] == ctx['thread_id']
            from research_threads import notebook_operation
            assert notebook_operation({'project_ref': ctx['project_uid'], 'op': 'sources'})['items'] == []
            before({'group': 'delegation'}, {})  # 일반 실행 권한은 연구 전용 제한으로 바뀌지 않는다.
        with pytest.raises(PermissionError):
            with adopt_execution('agent', 'task', str(path / 'other')):
                pass
        assert list(turn.events(iter([{'type': 'final', 'content': '완료'}])))[0]['content'] == '완료'
    assert current() is None
    assert ResearchStore(path).thread(ctx['thread_id'])['active_run'] is None
    with adopt_execution('agent', 'task', str(path)):
        assert current() is None


def test_conversation_continuity_is_not_agent_wide(workspace):
    runner, path = workspace
    refs = []
    for n, session in enumerate(['one', 'one', 'two']):
        tc.set_current_task_id('task' + str(n))
        with conversation_scope(Binding(str(path / 'conversations.db'), session, 'agent')):
            with TurnResearch() as turn:
                turn.activate(runner, {'_research_plan': {'path': 'plan.md'}}, '후속 연구')
                ctx = dict(current()); refs.append(ctx['thread_id'])
                lib = ResearchLibrary(ResearchStore(path), ctx['thread_id'])
                if n == 0:
                    lib.capture('이 대화의 근거', title='근거')
                assert bool(lib.sources()['items']) == (n < 2)
                list(turn.events(iter([{'type': 'final', 'content': '완료'}])))
    assert refs[0] == refs[1] != refs[2]


def test_exception_cleans_context_and_marks_interrupted_work_failed(workspace):
    runner, path = workspace
    with pytest.raises(RuntimeError, match='cancel'):
        with TurnResearch() as turn:
            turn.activate(runner, {'_research_plan': {'path': 'plan.md'}}, '연구')
            ctx = dict(current())
            raise RuntimeError('cancel')
    store = ResearchStore(path)
    assert current() is None and store.thread(ctx['thread_id'])['active_run'] is None
    with store.connect() as db:
        assert db.execute('SELECT status FROM tasks WHERE task_id=?', (ctx['run_id'],)).fetchone()[0] == 'failed'


def test_file_citation_failure_is_visible_before_delivery(workspace):
    runner, path = workspace
    (path / 'outputs').mkdir()
    (path / 'outputs/report.md').write_text('성공했다 [자료:missing:p1]')
    with TurnResearch() as turn:
        turn.activate(runner, {'_research_plan': {'path': 'plan.md'}}, '연구')
        ctx = dict(current())
        response = turn.validate('[보고서](outputs/report.md)')
        assert '인용 검증을 완료하지 못했습니다' in response
        list(turn.events(iter([{'type': 'final', 'content': response}])))
    store = ResearchStore(path)
    with store.connect() as db:
        assert db.execute('SELECT status FROM tasks WHERE task_id=?', (ctx['run_id'],)).fetchone()[0] == 'failed'


def test_native_tool_capture_and_interrupted_run_recovery(workspace):
    runner, path = workspace
    import research_capture
    from unittest.mock import patch
    with TurnResearch() as turn:
        turn.activate(runner, {'_research_plan': {'path': 'plan.md'}}, '연구')
        ctx = dict(current())
        with patch.object(research_capture, 'schedule_index'):
            list(turn.events(iter([
                {'type': 'tool_start', 'id': 'read1', 'name': 'Read', 'input': {}},
                {'type': 'tool_result', 'id': 'read1', 'name': 'Read', 'result': '실제 반환된 원문'},
                {'type': 'final', 'content': '완료'},
            ])))
        lib = ResearchLibrary(ResearchStore(path), ctx['thread_id'])
        assert lib.sources()['items']
    store = ResearchStore(path)
    crashed, _ = store.begin_run(ctx['thread_id'], '중단될 요청', 'crashed')
    tc.set_current_task_id('next-task')
    with TurnResearch() as turn:
        turn.activate(runner, {'_research_plan': {'path': 'plan.md'}}, '다음 연구')
        with store.connect() as db:
            assert db.execute('SELECT status FROM tasks WHERE task_id=?', (crashed,)).fetchone()[0] == 'interrupted'
        list(turn.events(iter([{'type': 'final', 'content': '완료'}])))


def test_existing_workspace_identity_survives_project_relocation(workspace):
    runner, path = workspace
    original = ResearchStore(path, 'persistent-identity')
    with TurnResearch() as turn:
        turn.activate(runner, {'_research_plan': {'path': 'plan.md'}}, '연구')
        assert current()['project_uid'] == original.uid
        list(turn.events(iter([{'type': 'final', 'content': '완료'}])))


@pytest.mark.parametrize('flag,surface', [('_member', 'member'), ('_is_system_ai', 'system_ai')])
def test_unsupported_identity_reports_coverage_without_creating_library(workspace, flag, surface):
    runner, path = workspace
    runner.config[flag] = True
    framing = {'_research_plan': {'path': 'plan.md'}}
    with TurnResearch() as turn:
        guidance = turn.activate(runner, framing, '연구')
        assert surface in guidance and not current()
        assert framing['_research_coverage']['library_attached'] is False
    assert not (path / 'research').exists()


def test_native_duplicate_return_is_captured_once_but_new_payload_is_preserved(workspace, monkeypatch):
    from research_context import capture_stream
    import research_context
    captured = []
    monkeypatch.setattr(research_context, '_capture', lambda ctx, cfg, args, result, call: captured.append(result) or result)
    with research_context.scope({'attached': True}):
        events = [{'type': 'tool_result', 'id': 'r', 'name': 'Read', 'result': value}
                  for value in ['원문', '원문', '새 판본']]
        events += [{'type': 'tool_start', 'id': 'r', 'name': 'Read', 'input': {}},
                   {'type': 'tool_result', 'id': 'r', 'result': '원문'}]
        assert list(capture_stream(iter(events))) == events
    assert captured == ['원문', '새 판본', '원문']


def test_supported_workspace_capture_read_question_submit_review_roundtrip(workspace, monkeypatch):
    import research_capture
    from research_context import citation_review
    from research_questions import ResearchQuestions
    runner, path = workspace
    monkeypatch.setattr(research_capture, 'schedule_index', lambda path: None)
    with TurnResearch() as turn:
        turn.activate(runner, {'_research_plan': {'path': 'plan.md'}}, '정격과 실사용을 구별')
        ctx = dict(current())
        list(turn.events(iter([{'type': 'tool_result', 'id': 'read', 'name': 'Read',
                               'result': '정격은 상한이고 실사용량은 조건에 따라 다르다.'}])))
        store = ResearchStore(path)
        lib = ResearchLibrary(store, ctx['thread_id'])
        vid = lib.sources()['items'][0]['version_ref']
        page = lib.read(vid)
        refs = lib.citations(page['text'], ctx['run_id'])
        assert refs
        ref = refs[0]
        questions = ResearchQuestions(store, ctx['thread_id'])
        q = questions.apply([{'expected_revision': 0, 'text': '실사용량 판단', 'supporting': [
            {'version_ref': ref['version_id'], 'extraction_revision': ref['extraction_revision'],
             'locator': ref['locator'], 'quote': ref['quote']}], 'gaps': ['가동 조건']}],
            origin='agent', run=ctx['run_id'])['items'][0]
        (path / 'outputs').mkdir()
        report = path / 'outputs/result.md'
        report.write_text('실사용량은 아직 미확인이다. ' + f"[자료:{vid}:{ref['locator']}]")
        response = '[보고서](outputs/result.md)'
        assert turn.validate(response) == response
        result = citation_review(report.read_text(), question_ids=[q['question_id']])
        assert not result['invalid'] and result['questions']['items'][0]['status'] == 'open'
        assert result['valid'][0]['semantic_status'] == 'unreviewed'
        list(turn.events(iter([{'type': 'final', 'content': response}])))
    assert current() is None


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__]))
