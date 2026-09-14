"""ep3388: taskless 실제 HTTP 진입·감독·초안·MCP 합류와 원자료 표시 회귀."""
import asyncio
import importlib.util
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
import boot_paths  # noqa: F401
import thread_context as tc
import episode_logger as el
from agent_pipeline import CognitivePipelineMixin
from cognitive_consciousness import CognitiveConsciousnessMixin
from cognitive_eval import CognitiveEvalMixin
from supervision_store import TurnStore, digest

ROOT = Path(__file__).resolve().parents[1]
DRAFT = '$자료 = [table:take]{items:[{k:1},{k:2}],n:2}'
FRAMING = {'task_framing': '자료 확인', 'achievement_criteria': '수치 검증', 'imagined_ibl': DRAFT}


def load_package(name):
    spec = importlib.util.spec_from_file_location('ep3388_' + name.replace('-', '_'),
        ROOT / 'data/packages/installed/tools' / name / 'handler.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    previous = tc.snapshot()
    tc.clear_all_context()
    token = el._current_episode.set(None)
    db_path = tmp_path / 'episodes.db'
    def db():
        conn = sqlite3.connect(db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn
    monkeypatch.setattr(el, '_get_db', db)
    el._ensure_episode_tables()
    monkeypatch.setattr(el, '_extract_and_save_summary', lambda *a, **kw: None)
    monkeypatch.setattr('common.spill.spill_dir', lambda: str(tmp_path))
    monkeypatch.setattr('conscious_supervisor.TurnStore',
                        lambda directory: TurnStore(tmp_path / 'supervision' / Path(directory).name))
    monkeypatch.setattr('pursuit_bind.owner_for', lambda runner: None)
    monkeypatch.setattr('world_pulse._load_config', lambda: {'conscious_supervisor': {'tick_s': 1000}})
    monkeypatch.setattr('agent_pipeline._reload_gate_notice', lambda: '')
    try:
        yield db_path
    finally:
        el.EpisodeLogger.end_episode()
        el._current_episode.reset(token)
        tc.restore(previous)


class Runner(CognitivePipelineMixin, CognitiveConsciousnessMixin, CognitiveEvalMixin):
    def __init__(self, path, stream):
        self.project_path = path
        self.config = {'id': 'agent_test', 'name': '자료'}
        self.ai = SimpleNamespace(agent_id='project:agent_test', project_path=str(path),
                                  _provider=None, tools=[], process_message_stream=stream,
                                  _custom_execute_tool=lambda *a, **kw: {'success': True})
    def _sync_execution_gear(self):
        pass
    def _build_execution_memory(self, *a, **kw):
        return '', 0, ''
    def _decide_request_type(self, *a):
        return 'THINK', None
    def _load_role(self):
        return ''
    def _get_available_tools(self):
        return ['execute_ibl']
    def _build_system_prompt_split(self, *a):
        return 'fixture', ''
    def _log(self, *a):
        pass
    def _after_response_async(self, *a, **kw):
        pass


def install_judge(monkeypatch, phases):
    def process(**kw):
        # 실제 consciousness mixin이 감독 객체를 전달했는지 검사한다.
        return json.loads(kw['supervisor'].plan('계획 입력', '계획 역할'))
    monkeypatch.setattr('consciousness_agent.get_consciousness_agent',
                        lambda: SimpleNamespace(is_ready=True, process=process))
    monkeypatch.setattr('consciousness_agent.get_world_pulse_text', lambda: '')
    def invoke(c, *a, phase='review', **kw):
        phases.append((phase, c.task))
        if phase == 'plan':
            return json.dumps(FRAMING, ensure_ascii=False)
        c.store.read_response(mark=True)
        return json.dumps({'status': 'APPROVED' if phase == 'final' else 'CONTINUE',
                           'reason': '시험 근거 확인', 'response_version': c.store.version,
                           'response_hash': digest(c.store.text)})
    monkeypatch.setattr('supervisor_runtime.invoke', invoke)
    monkeypatch.setattr('final_evaluator.invoke', invoke)


@pytest.mark.parametrize('summary', ['', '제주 관광 비교 기간을 2025년으로 정정했다.'])
def test_history_selection_reaches_executor_through_real_pipeline(tmp_path, monkeypatch, isolated, summary):
    history = [{'role': 'user', 'content': '블루칼라 보고서는 표만 작성해'},
               {'role': 'user', 'content': '제주 관광을 2024년 기준으로 비교해'},
               {'role': 'user', 'content': '그 기간은 2025년으로 고쳐'}]
    message = '제주 관광을 왜 계속 유치하는지 설명해' if not summary else '그 비교를 계속해'
    plan_inputs, executor_inputs = [], []

    def process(**kwargs):
        plan_inputs.append(kwargs)
        return {'task_framing': '현재 제주 관광 질문에 답한다', 'history_summary': summary,
                'achievement_criteria': ''}

    def stream(**kwargs):
        executor_inputs.append(kwargs)
        yield {'type': 'final', 'content': '제주 관광 질문에 대한 답변'}

    monkeypatch.setattr('consciousness_agent.get_consciousness_agent',
                        lambda: SimpleNamespace(is_ready=True, process=process))
    monkeypatch.setattr('consciousness_agent.get_world_pulse_text', lambda: '')
    events = list(Runner(tmp_path, stream).cognitive_stream(message, history))
    assert not [e for e in events if e['type'] == 'error'], events
    assert plan_inputs[0]['history'] == history  # 의식에는 관련성을 판단할 원문이 있다.
    assert plan_inputs[0]['user_message'] == message
    actual = executor_inputs[0]['history']
    if summary:
        assert len(actual) == 1 and summary in actual[0]['content']
        assert actual[0]['_history_replacement'] is True
        assert '블루칼라' not in actual[0]['content'] and '2024' not in actual[0]['content']
    else:
        assert actual == []
    assert message in executor_inputs[0]['message_content']
    assert len(history) == 3


def test_http_command_without_task_runs_plan_review_final_and_mcp(tmp_path, monkeypatch, isolated):
    import api_agents
    from api_ibl import execute_ibl_code, IBLRequest
    from supervision_bus import current
    from ibl_turn_vars import load_draft
    phases, identities = [], []
    install_judge(monkeypatch, phases)
    monkeypatch.setattr(api_agents, 'project_manager', SimpleNamespace(get_project_path=lambda _: tmp_path))
    original = '  승인한 본문\n\n끝.  \n'

    def stream(**kwargs):
        task = tc.get_current_task_id()
        controller = current()
        identities.append((task, el.EpisodeLogger.current().trajectory.run_id))
        assert task and controller.task == task and load_draft() == DRAFT
        # 네트워크 모델만 대역. 실제 MCP 재진입 수신 핸들러→워커→IBL→변수를 두 번 돈다.
        def bridge(code):
            return asyncio.run(execute_ibl_code(IBLRequest(code=code,
                project_path=str(tmp_path), agent_id='project:agent_test', task_id=task,
                episode_id=el.EpisodeLogger.current().episode_id,
                parent_run_id=el.EpisodeLogger.current().trajectory.run_id)))
        first = bridge('$초안')
        assert first.get('success') is True and first['turn_vars']['live'] == ['자료'], first
        second = bridge('$자료 >> [table:take]{n:1}')
        assert second.get('success') is True and '자료' in second['turn_vars']['injected'], second
        # The supervisor now revalidates stale reasons before paying for a model.
        # Exercise an actual unresolved failure chain rather than injecting a label.
        for _ in range(2):
            failed = bridge('$자료 >> [table:select]{columns:["없는열"]}')
            assert failed.get('success') is False, failed
        controller.review('repeated_failure')
        yield {'type': 'text', 'content': original}
        yield {'type': 'final', 'content': original}

    runner = Runner(tmp_path, stream)
    for _ in range(2):
        assert api_agents._run_agent_command('project', 'agent_test', runner, '검증해줘') == original
        assert tc.get_current_task_id() is None and current() is None
    assert len({task for task, _ in identities}) == 2
    assert [p for p, _ in phases] == ['plan', 'review', 'final'] * 2
    with sqlite3.connect(isolated) as conn:
        episodes = conn.execute('SELECT id,task_id,run_id,ended_at FROM episode_log').fetchall()
        assert len(episodes) == 2 and all(row[3] for row in episodes)
        for ep_id, task, run, _ in episodes:
            rows = conn.execute('SELECT task_id,run_id,kind FROM trajectory_event WHERE episode_id=?', (ep_id,)).fetchall()
            assert rows and all(t == task and r == run for t, r, k in rows)
            assert 'supervision.turn.opened' in [k for t, r, k in rows]
            assert 'ibl.started' in [k for t, r, k in rows]
    with sqlite3.connect(tmp_path / 'conversations.db') as conn:
        assert conn.execute("SELECT count(*) FROM tasks WHERE status='completed'").fetchone()[0] == 2


def test_common_entry_recovers_episode_id_and_restores_context(tmp_path, monkeypatch, isolated):
    from supervision_bus import current
    identities = []
    def body(self, message, history, **kw):
        identities.append(tc.get_current_task_id())
        assert current() is not None
        yield {'type': 'final', 'content': 'ok'}
    monkeypatch.setattr(Runner, '_cognitive_stream_body', body)
    runner = Runner(tmp_path, lambda **kw: iter(()))
    el.EpisodeLogger.start_episode('자료', 'ID 생략')
    task = el.episode_task_id()
    assert task and tc.get_current_task_id() is None
    list(runner.cognitive_stream('ID 생략'))
    assert identities == [task] and tc.get_current_task_id() is None
    assert current(runner.ai.agent_id, task) is None
    el.EpisodeLogger.end_episode()
    list(runner.cognitive_stream('에피소드도 없는 호출'))
    assert identities[-1] and identities[-1] != task


def test_common_entry_closes_supervisor_on_generator_exit(tmp_path, monkeypatch, isolated):
    from supervision_bus import current
    seen = []
    def body(self, *a, **kw):
        seen.append(current())
        yield {'type': 'text', 'content': '일하는 중'}
    monkeypatch.setattr(Runner, '_cognitive_stream_body', body)
    stream = Runner(tmp_path, lambda **kw: iter(())).cognitive_stream('중단')
    next(stream)
    stream.close()
    assert seen[0].stopped.is_set()
    assert tc.get_current_task_id() is None and current() is None


def test_http_failure_closes_episode_and_task(tmp_path, monkeypatch, isolated):
    import api_agents
    monkeypatch.setattr(api_agents, 'project_manager', SimpleNamespace(get_project_path=lambda _: tmp_path))
    def fail(*a, **kw):
        raise RuntimeError('시험 실패')
    runner = SimpleNamespace(config={'name': '실패'}, cognitive_stream=fail)
    with pytest.raises(RuntimeError, match='시험 실패'):
        api_agents._run_agent_command('p', 'a', runner, '실패 시험')
    assert tc.get_current_task_id() is None
    with sqlite3.connect(isolated) as conn:
        assert conn.execute('SELECT ended_at FROM episode_log').fetchone()[0]
    with sqlite3.connect(tmp_path / 'conversations.db') as conn:
        assert conn.execute('SELECT status FROM tasks').fetchone()[0] == 'failed'


@pytest.mark.parametrize('pipeline', [False, True])
def test_auxiliary_rows_are_not_repeated_and_raw_is_recoverable(tmp_path, monkeypatch, pipeline):
    import model_result_view as view
    store = TurnStore(tmp_path)
    monkeypatch.setattr(view, 'evidence_store', lambda: store)
    raw_data = [{'year': i, 'raw': '원자료' * 200} for i in range(756)]
    value = {'success': True, 'data': raw_data, 'count': 756,
             'items': [{'year': i, 'rate': i / 10} for i in range(14)],
             'warning': '다른 조사 계열과 비교 금지'}
    raw = {'success': True, 'final_result': json.dumps(value),
           'results': [{'step': 1, 'result': json.dumps(value)}]} if pipeline else value
    before = json.dumps(raw)
    out = view.project_result(raw)
    final = out['final_result'] if pipeline else out
    final = json.loads(final) if isinstance(final, str) else final
    assert len(json.dumps(out, ensure_ascii=False)) < 6000
    assert final['_model_omitted']['data']['count'] == 756
    assert final['warning'] == value['warning'] and len(raw_data) == 756
    assert json.dumps(raw) == before
    ref = out['result_ref']['id']
    assert json.loads(store.read_evidence(ref, limit=None)['text']) == raw
    path = ['final_result', 'items'] if pipeline else ['items']
    page = view.read_result({'id': ref, 'path': path, 'limit': 200})
    text = page['text']
    while page['next_offset'] is not None:
        page = view.read_result({'id': ref, 'path': path, 'offset': page['next_offset'], 'limit': 200})
        text += page['text']
    assert json.loads(text) == value['items']
    row = view.read_result({'id': ref, 'path': path + [13]})
    assert json.loads(row['text']) == value['items'][13]
    for invalid in (path + [-1], path + [True], 'items', ['missing']):
        with pytest.raises(ValueError):
            view.read_result({'id': ref, 'path': invalid})


def test_xls_reads_through_self_read_and_filter_recovery(tmp_path):
    reader = load_package('system_essentials')
    context = SimpleNamespace(tool_name='read_op', project_path=str(tmp_path), agent_id=None)
    result = json.loads(reader.execute({'file_path': str(ROOT / 'backend/fixtures/episode3388.xls')}, context))
    assert result['success'] and result['table']['columns'] == ['year', 'rate', 'text']
    assert result['table']['rows'][0][:2] == [2024, 11.8]
    assert result['sheet_count'] == 2
    ops = load_package('data-ops')
    value = {'items': [{'text': '긴' * 201}, {'text': '짧음'}]}
    error = ops._op_filter(value, {'where': 'len(text) > 200'})
    assert error['success'] is False and 'table:compute' in error['error']
    computed = ops._op_compute(value, {'set': {'문자수': 'len(text)'}})
    selected = ops._op_filter(computed, {'where': '문자수 > 200'})
    assert len(selected['items']) == 1 and selected['items'][0]['text'] == '긴' * 201


@pytest.mark.parametrize('explicit_format', ['', 'xls', 'xlsx'])
def test_xls_missing_sheet_is_not_replaced_with_another(tmp_path, explicit_format):
    reader = load_package('system_essentials')
    context = SimpleNamespace(tool_name='read_op', project_path=str(tmp_path), agent_id=None)
    out = json.loads(reader.execute({'path': str(ROOT / 'backend/fixtures/episode3388.xls'),
                                    'sheet': 'missing', 'format': explicit_format}, context))
    assert out['success'] is False and out['sheets'] == ['Rates', 'Notes']
    assert 'table' not in out


def test_explicit_internal_role_does_not_spawn_supervisor(tmp_path, monkeypatch, isolated):
    from supervision_bus import current
    def body(self, *a, **kw):
        assert current() is None
        yield {'type': 'final', 'content': 'internal'}
    monkeypatch.setattr(Runner, '_cognitive_stream_body', body)
    out = list(Runner(tmp_path, lambda **kw: iter(())).cognitive_stream('internal', force_role='forage'))
    assert out[-1]['content'] == 'internal' and tc.get_current_task_id() is None


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
