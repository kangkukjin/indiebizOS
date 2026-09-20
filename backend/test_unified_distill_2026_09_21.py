"""통합 증류: 저장 정밀도·0건 정상·한 번 판단·재배달의 실제 DB 효과."""
import copy
import json
import sqlite3
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest

import unified_distill as ud
import distill_ledger as ledger
from distill_memory_adapters import memory_modules, apply_deep, prepare_deep, prepare_forage, apply_forage
from distill_receipts import fingerprint


@pytest.fixture
def env(tmp_path, monkeypatch):
    import pulse_db
    import forage_memory
    db, tree = memory_modules()
    monkeypatch.setattr(pulse_db, 'CONSCIOUSNESS_DB_PATH', tmp_path / 'pulse.db')
    monkeypatch.setattr(forage_memory, '_DB_PATH', str(tmp_path / 'forage.db'))
    monkeypatch.setattr(forage_memory, '_doc_refresh', lambda *a, **k: None)
    monkeypatch.setattr(db, '_index_one', lambda *a, **k: True)
    monkeypatch.setattr(db, '_tree_refresh', lambda *a, **k: None)
    monkeypatch.setattr(tree, 'map_text', lambda *a: '- 문체')
    job = {'schema_version': 1, 'job_key': 'job-1', 'principal': 'owner', 'agent_id': 'test-agent',
           'project_id': 'test-project', 'project_path': str(tmp_path), 'turn_id': 'turn-1',
           'recorded_at': '2026-09-21T10:00:00+09:00', 'timezone': 'KST', 'user_message': '나는 앞으로 존댓말을 선호해.',
           'response': '알겠습니다.', 'write_deep': True, 'tool_calls': [],
           'model': {'provider': 'test', 'model': 'frozen', 'role': 'execution', 'pin_key': 'p:a'}}
    return SimpleNamespace(job=job, db=db, tree=tree, root=tmp_path, monkeypatch=monkeypatch)


def candidate(**extra):
    return {'future_use': '다음 대화의 말투 선택', 'novelty': '기존에 없던 지속적인 말투 선호', 'durable': True,
            'user_source_ids': [1], 'retention': 'user_preference', 'node': '문체', 'keywords': '존댓말',
            'category': '사용자선호', 'relation': 'NEW', 'existing_id': None, **extra}


def deep_section(env):
    from memory_evidence import durable_source_units
    return {'eligible': True, 'units': durable_source_units(env.job['user_message']), 'allowed_ids': [1],
            'known': [], 'tree': '- 문체', 'queries': [], 'omitted_ids': []}


def arm(env, decision=None, sections=None):
    asked = []
    sections = {'deep': deep_section(env)} if sections is None else sections
    env.monkeypatch.setattr(ud, 'prepare', lambda job: {'sections': copy.deepcopy(sections), 'skip_reasons': {}, 'snapshot': {}})
    env.monkeypatch.setattr('model_resolver.provider_from_frozen', lambda desc: desc)
    def ask(provider, prompt, **kwargs):
        asked.append((provider, json.loads(prompt), kwargs))
        return decision if isinstance(decision, str) else json.dumps(decision or empty(), ensure_ascii=False)
    env.monkeypatch.setattr('consciousness_agent.call_oneshot_provider', ask)
    return asked


def empty(**extra):
    return {'schema_version': 1, 'execution': [], 'deep': [], 'forage': [], **extra}


def count(env):
    return env.db.count(env.job['project_path'], env.job['agent_id'])


def test_empty_is_success_without_storage(env):
    asked = arm(env)
    assert ud.run(env.job)['status'] == 'completed_empty'
    assert len(asked) == 1 and count(env) == 0
    assert ud.run(env.job)['status'] == 'completed_empty'
    assert len(asked) == 1


def test_all_ineligible_costs_zero_calls(env):
    asked = arm(env, sections={})
    assert ud.run(env.job)['status'] == 'skipped'
    assert asked == [] and count(env) == 0


@pytest.mark.parametrize('edit', [{'durable': False}, {'future_use': ''}, {'novelty': ''},
                                  {'user_source_ids': [99]}, {'user_source_ids': [True]},
                                  {'relation': 'REPLACE', 'existing_id': 99}, {'node': ''}])
def test_no_value_or_ungrounded_candidate_never_saved(env, edit):
    asked = arm(env, empty(deep=[candidate(**edit)]))
    state = ud.run(env.job)
    assert state['receipts']['deep:0']['status'] == 'rejected'
    assert count(env) == 0 and len(asked) == 1


@pytest.mark.parametrize('raw', ['not json', '[]', '{}', '{"schema_version":1,"deep":[]}'])
def test_invalid_response_is_permanent_not_repaired(env, raw):
    asked = arm(env, raw)
    for _ in range(2):
        with pytest.raises(ledger.PermanentDistillError):
            ud.run(env.job)
    assert len(asked) == 1 and count(env) == 0


def test_save_after_commit_crash_replays_without_model_or_duplicate(env):
    asked = arm(env, empty(deep=[candidate()]))
    attempts = []
    def projection(*args, **kwargs):
        attempts.append(args)
        if len(attempts) == 1:
            raise OSError('crash after durable memory commit')
    env.monkeypatch.setattr(env.db, '_tree_refresh', projection)
    with pytest.raises(RuntimeError, match='storage_retry'):
        ud.run(env.job)
    assert count(env) == 1
    assert ledger.read('job-1')['decision']['deep'] == [candidate()]
    # 재시작: runner/모델 설정은 바뀌어도 영속한 판단과 봉투로 저장만 재개한다.
    state = ud.run({**env.job, 'model': {'provider': 'changed', 'model': 'changed'}})
    assert state['status'] == 'completed' and count(env) == 1
    assert len(asked) == 1 and len(attempts) == 2


def test_failure_before_mutation_has_no_receipt_or_memory(env):
    asked = arm(env, empty(deep=[candidate()]))
    original = env.db.save
    env.monkeypatch.setattr(env.db, 'save', lambda *a, **k: (_ for _ in ()).throw(sqlite3.OperationalError('busy')))
    with pytest.raises(RuntimeError):
        ud.run(env.job)
    assert count(env) == 0
    env.monkeypatch.setattr(env.db, 'save', original)
    assert ud.run(env.job)['status'] == 'completed'
    assert count(env) == len(asked) == 1


def test_partial_success_is_not_reapplied(env):
    c1, c2 = candidate(), candidate(user_source_ids=[2], node='물건', keywords='프린터')
    env.job['user_message'] += ' 나는 라벨 프린터를 보유하고 있어.'
    section = deep_section(env)
    section['allowed_ids'] = [1, 2]
    asked = arm(env, empty(deep=[c1, c2]), {'deep': section})
    original, calls = env.db.save, []
    def save(*args, **kwargs):
        calls.append(kwargs['node'])
        if kwargs['node'] == '물건' and calls.count('물건') == 1:
            raise sqlite3.OperationalError('busy')
        return original(*args, **kwargs)
    env.monkeypatch.setattr(env.db, 'save', save)
    with pytest.raises(RuntimeError):
        ud.run(env.job)
    assert count(env) == 1
    ud.run(env.job)
    assert count(env) == 2 and calls.count('문체') == 1 and len(asked) == 1


def test_replace_compare_and_swap_and_replay(env):
    ident = env.db.save(env.job['project_path'], env.job['agent_id'], '나는 반말을 선호해.', node='문체')
    row = env.db.read(env.job['project_path'], env.job['agent_id'], ident)
    row['version'] = fingerprint({k: row.get(k) for k in ('content', 'source_ref', 'node')})
    section = deep_section(env); section['known'] = [row]
    c = candidate(relation='REPLACE', existing_id=ident, existing_version=row['version'],
                  correction_source_ids=[1], explicit_correction=True)
    first = apply_deep(env.job, section, c, 'replace-1')
    second = apply_deep(env.job, section, c, 'replace-1')
    assert first['status'] == second['status'] == 'saved' and count(env) == 1
    current = env.db.read(env.job['project_path'], env.job['agent_id'], ident)
    assert json.loads(current['source_ref'])['superseded']['content'] == row['content']
    assert apply_deep(env.job, section, c, 'competing-replacement')['status'] == 'deferred'


def test_quoted_text_and_dangling_reference_cannot_become_user_fact(env):
    env.job['user_message'] = '> 나는 앞으로 존댓말을 선호해.'
    section = deep_section(env)
    assert apply_deep(env.job, section, candidate(), 'quoted')['status'] == 'rejected'
    env.job['user_message'] = '그걸 앞으로 계속 쓰기로 했어.'
    section = deep_section(env)
    assert apply_deep(env.job, section, candidate(), 'dangling')['status'] == 'rejected'
    assert count(env) == 0


def test_search_failure_closes_only_deep(env):
    import distill_memory_adapters as adapters
    env.monkeypatch.setattr(env.db, 'search', lambda *a, **k: (_ for _ in ()).throw(sqlite3.OperationalError('busy')))
    env.monkeypatch.setattr(adapters, 'prepare_forage', lambda job: {'eligible': True, 'observations': []})
    result = ud.prepare(env.job)
    assert 'deep' not in result['sections'] and 'forage' in result['sections']
    assert result['skip_reasons']['deep'].startswith('preparation_failed')


def test_search_uses_preceding_context_and_never_reads_ai_answer(env):
    env.job['user_message'] = '나는 책을 종이로 읽어. 앞으로도 그걸 유지할 거야.'
    env.job['response'] = 'AI INVENTED FACT'
    queries = []
    env.monkeypatch.setattr(env.db, 'search', lambda *a, **k: queries.append(k['query']) or [])
    result = prepare_deep(env.job)
    assert '종이로' in queries[1] and all('AI INVENTED FACT' not in q for q in queries)
    assert result['allowed_ids'] == [1, 2]


def test_budget_omits_whole_section_and_does_not_cut_source(env):
    text = '한' * 30000
    prepared = {'snapshot': {}, 'skip_reasons': {}, 'sections': {
        'execution': {'rows': [{'id': 1, 'code': text}]}, 'deep': deep_section(env)}}
    fitted = ud.fit_input(prepared)
    assert 'execution' not in fitted['sections'] and 'deep' in fitted['sections']
    assert fitted['input_bytes'] <= ud.MAX_INPUT_BYTES


def test_forage_ignores_assistant_only_or_failed_observation(env):
    env.job['response'] = 'https://example.test 에는 자료가 없다.'
    env.job['write_deep'] = False
    assert not prepare_forage(env.job)['eligible']
    env.job['tool_calls'] = [{'input': {'url': 'https://example.test'}, 'result': 'not found', 'success': False}]
    assert not prepare_forage(env.job)['eligible']


def test_forage_real_observation_and_retry_do_not_reinforce_twice(env):
    import forage_memory as fm
    env.job['tool_calls'] = [{'tool_name': 'execute_ibl', 'input': {'code': '[sense:crawl]{url:"https://example.test/docs"}'},
                             'result': {'url': 'https://example.test/docs', 'text': '문서 링크는 버전별로 분류됨'}, 'success': True}]
    prepared = prepare_forage(env.job)
    c = {'locus': 'https://example.test/docs', 'body': 'web', 'observation_ids': [1],
         'claim': '문서는 버전별 경로로 분류된다.', 'kind': 'convention', 'prior_class': 'structural',
         'generalizes': True, 'relation': 'NEW'}
    first = apply_forage(env.job, prepared, c, 'space-1')
    second = apply_forage(env.job, prepared, c, 'space-1')
    assert first['status'] == second['status'] == 'saved'
    conn = fm._connect()
    rows = conn.execute('SELECT provenance FROM forage_map').fetchall(); conn.close()
    assert len(rows) == 1 and not json.loads(rows[0][0]).get('reinforced_by')
    assert apply_forage(env.job, prepared, {**c, 'kind': 'dead_branch'}, 'bad')['status'] == 'rejected'


def test_frozen_model_uses_current_secret_but_never_resolves_gear(monkeypatch):
    import model_resolver as mr
    seen = []
    monkeypatch.setattr(mr, 'resolve', lambda *a, **k: pytest.fail('must not resolve current gear'))
    monkeypatch.setattr(mr, 'env_key_for_provider', lambda p: 'runtime-secret')
    monkeypatch.setattr(mr, '_provider_from_desc', lambda d, **k: seen.append((d, k)) or SimpleNamespace(model=d['model']))
    original = {'provider': 'openai', 'model': 'chosen-model', 'tier': '고급', 'api_key': 'do-not-persist'}
    frozen = mr.freeze_descriptor(original, role='execution', pin_key='p:a')
    assert 'api_key' not in frozen and 'do-not-persist' not in json.dumps(frozen)
    assert mr.provider_from_frozen(frozen).model == 'chosen-model'
    assert seen[0][0]['model'] == 'chosen-model' and seen[0][0]['api_key'] == 'runtime-secret'


@pytest.mark.parametrize('principal', [None, 'anonymous', 'member:one', 'body:neighbor'])
def test_unknown_or_nonowner_never_writes(env, principal):
    asked = arm(env, empty(deep=[candidate()]))
    with pytest.raises(ledger.PermanentDistillError):
        ud.run({**env.job, 'principal': principal})
    assert not asked and count(env) == 0


def test_out_of_scope_stage_receipt_prevents_duplicate_calls(env):
    ledger.create(env.job)
    calls = []
    def action():
        calls.append('effect')
        raise RuntimeError('unknown outcome')
    ledger.once(env.job['job_key'], 'guide', action)
    ledger.once(env.job['job_key'], 'guide', action)
    assert calls == ['effect']
    assert ledger.read('job-1')['receipts']['stage:guide']['status'] == 'failed'


def test_batch_same_source_different_rationale_is_saved_once(env):
    asked = arm(env, empty(deep=[candidate(), candidate(novelty='말투를 지속적으로 맞추는 데 필요')]))
    result = ud.run(env.job)
    assert count(env) == 1 and len(asked) == 1
    assert result['receipts']['deep:1']['reason'] == 'duplicate_batch_candidate'


def test_preparation_does_not_mark_search_hits_as_used(env):
    ident = env.db.save(env.job['project_path'], env.job['agent_id'], '나는 앞으로 존댓말을 선호해.', node='문체')
    env.monkeypatch.setattr(env.db, 'search', lambda *a, **kw: [{'id': ident}])
    before = env.db.read(env.job['project_path'], env.job['agent_id'], ident, touch=False)['used_at']
    prepare_deep(env.job)
    assert env.db.read(env.job['project_path'], env.job['agent_id'], ident, touch=False)['used_at'] == before


def test_all_three_kinds_share_one_judgment_and_replay(env):
    import forage_memory as fm
    env.job['tool_calls'] = [{'input': {'url': 'https://example.test/docs'},
                             'result': {'text': 'https://example.test/docs 버전별 문서'}, 'success': True}]
    forage = prepare_forage(env.job)
    spatial = {'future_use': '다음 버전 문서 탐색 경로 선택', 'novelty': '처음 관측한 버전별 문서 경로', 'durable': True,
               'locus': 'https://example.test/docs', 'body': 'web', 'observation_ids': [1],
               'claim': '문서는 버전별 경로로 분류된다.', 'kind': 'convention', 'prior_class': 'structural',
               'generalizes': True, 'relation': 'NEW'}
    executed = []
    env.monkeypatch.setattr('ibl_usage_rag.apply_experience', lambda p,c,**kw: executed.append(kw['candidate_key']) or True)
    execution = {'future_use': '다음 표 정리', 'novelty': '새 열 추리기 절차', 'durable': True, 'source_ids': [1]}
    asked = arm(env, empty(execution=[execution], deep=[candidate()], forage=[spatial]), {
        'execution': {'prompt': '실제 성공한 문장 번호 1'}, 'deep': deep_section(env), 'forage': forage})
    ud.run(env.job); ud.run(env.job)
    conn = fm._connect(); n = conn.execute('SELECT COUNT(*) FROM forage_map').fetchone()[0]; conn.close()
    assert len(asked) == len(executed) == count(env) == n == 1


def test_queue_common_path_reuses_durable_decision_and_stages(env):
    from distill_queue import DistillQueue, _Job
    from cognitive_distill import CognitiveDistillMixin
    asked = arm(env, empty(deep=[candidate()]))
    feedback = []
    env.monkeypatch.setattr('ibl_usage_rag.record_recall_outcome', lambda *a, **kw: feedback.append('recall'))
    env.job['guides_used'] = []
    env.job['tool_calls'] = [{'result': 'done'}]
    runner = CognitiveDistillMixin()
    runner.project_path, runner.agent_id = env.job['project_path'], env.job['agent_id']
    job = _Job(1, runner, env.job, {'agent_id': env.job['agent_id'], 'project_id': env.job['project_id']})
    DistillQueue._execute(job)
    DistillQueue._execute(job)
    assert len(asked) == count(env) == 1 and feedback == ['recall']


@pytest.mark.parametrize('role,pin', [('execution', '프로젝트:agent'), ('system_ai', ''),
                                     ('system_ai', 'system_ai_delegation'), ('reflex', ''),
                                     ('system_repair', ''), ('forage', '')])
def test_actual_swapped_provider_descriptor_is_captured_before_restore(env, role, pin):
    import model_resolver as mr
    descriptor = mr.freeze_descriptor({'provider': 'codex', 'model': 'swapped-model', 'source': 'pin'}, role=role, pin_key=pin)
    runner = SimpleNamespace(ai=SimpleNamespace(_provider=SimpleNamespace(distill_descriptor=descriptor)))
    captured = ud.capture_model(runner)
    runner.ai._provider = SimpleNamespace(distill_descriptor={'provider': 'other', 'model': 'restored'})
    assert captured['model'] == 'swapped-model' and captured['role'] == role and captured['pin_key'] == pin


def test_refused_output_schema_boolean_is_not_version_one():
    with pytest.raises(ledger.PermanentDistillError):
        ud.parse_decision(json.dumps(empty(schema_version=True)))


def test_invalid_source_shape_rejects_candidate_without_retry(env):
    asked = arm(env, empty(deep=[candidate(user_source_ids=1)]))
    result = ud.run(env.job)
    assert result['receipts']['deep:0']['status'] == 'rejected' and len(asked) == 1


def test_pending_document_projection_cannot_reverse_sync_and_delete_memory(env):
    from distill_receipts import projection_pending
    asked = arm(env, empty(deep=[candidate()]))
    env.monkeypatch.setattr(env.db, '_tree_refresh', lambda *a, **kw: (_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(RuntimeError):
        ud.run(env.job)
    path = env.db._get_db_path(env.job['project_path'], env.job['agent_id'])
    assert projection_pending(path)
    assert env.tree.sync_node(path, '문체')['reason'] == 'pending_distill_projection'
    assert count(env) == 1
    env.monkeypatch.setattr(env.db, '_tree_refresh', lambda *a, **kw: None)
    ud.run(env.job)
    assert not projection_pending(path) and count(env) == 1 and len(asked) == 1


def test_execution_store_commit_failure_has_one_row_and_projection_receipt(env):
    import ibl_usage_db as module
    from distill_receipts import projection_pending
    path = str(env.root / 'execution.db')
    env.monkeypatch.setattr(module, 'DB_PATH', path)
    env.monkeypatch.setattr(module.IBLUsageDB, '_instance', None)
    env.monkeypatch.setattr(module.IBLUsageDB, '_is_foreign_vocab', lambda *a: False)
    env.monkeypatch.setattr(module.IBLUsageDB, '_index_single', lambda *a, **kw: None)
    attempts = []
    def render(*args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise OSError('document write failed')
    env.monkeypatch.setattr(module, '_tree_refresh', render)
    db = module.IBLUsageDB()
    kwargs = dict(intent='시각 조회', ibl_code='[self:time]', candidate_key='execution-once')
    with pytest.raises(OSError):
        db.add_example(**kwargs)
    assert projection_pending(path)
    ident = db.add_example(**kwargs)
    assert ident and not projection_pending(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM ibl_examples').fetchone()[0] == 1


def test_forage_projection_failure_does_not_reinforce_again(env):
    import forage_memory as fm
    from distill_receipts import projection_pending
    calls = []
    def render(*a, **kw):
        calls.append(1)
        if len(calls) == 1:
            raise OSError('document write failed')
    env.monkeypatch.setattr(fm, '_doc_refresh', render)
    kwargs = dict(body='web', locus='https://example.test/docs', kind='convention',
                  claim='버전별 경로에 문서가 있다.', candidate_key='spatial-once', generalizes=True)
    with pytest.raises(OSError):
        fm.note_map(**kwargs)
    assert projection_pending(fm._DB_PATH)
    fm.note_map(**kwargs)
    assert not projection_pending(fm._DB_PATH)
    conn = fm._connect()
    rows = conn.execute('SELECT provenance FROM forage_map').fetchall(); conn.close()
    assert len(rows) == 1 and not json.loads(rows[0][0]).get('reinforced_by')


def test_new_queue_registry_key_is_unresolvable_by_legacy_worker(env):
    import distill_queue as dq
    q = dq.DistillQueue()
    env.monkeypatch.setattr(q, '_put', lambda job: None)
    q.enqueue(object(), env.job, ident={'registry_key': 'test-project:test-agent'})
    conn = dq._conn()
    key = conn.execute('SELECT registry_key FROM distill_queue').fetchone()[0]; conn.close()
    assert key == 'distill-v1:test-project:test-agent'
    import agent_registry
    runner = object()
    env.monkeypatch.setattr(agent_registry, 'runner_registry', {'test-project:test-agent': runner})
    assert agent_registry.runner_registry.get(key) is None
    assert dq.DistillQueue._resolve_runner(key) is runner


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
