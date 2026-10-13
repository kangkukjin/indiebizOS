"""질문 계약의 인용·동시 수정·재개·격리 회귀. 외부 모델 호출 없음."""
import boot_paths  # noqa: F401
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from research_store import ResearchStore, ResearchConflict
from research_library import ResearchLibrary
from research_questions import ResearchQuestions
from research_context import scope


@pytest.fixture
def world(tmp_path):
    store = ResearchStore(tmp_path, 'question-test')
    tid = store.create_thread('연구')['id']
    return store, tid, ResearchQuestions(store, tid)


def create(questions, **changes):
    return questions.apply([{'expected_revision': 0, 'text': '어떤 조건에서 효과가 있는가?', **changes}])['items'][0]


def update(questions, q, **changes):
    return questions.apply([{'question_id': q['question_id'], 'expected_revision': q['revision'], **changes}])['items'][0]


def reference(store, tid, content='관찰된 효과가 있다.'):
    receipt = ResearchLibrary(store, tid).capture(content, title='자료', paragraphs=[('p1', content)])
    return {'version_ref': receipt['version_ref'], 'extraction_revision': 1, 'locator': 'p1', 'quote': content}


def test_revision_cas_atomic_batch_and_history(world):
    store, tid, questions = world
    q = create(questions)
    with pytest.raises(ResearchConflict):
        questions.apply([{'expected_revision': 0, 'text': '롤백돼야 한다'},
                         {'question_id': q['question_id'], 'expected_revision': 0, 'text': '충돌'}])
    assert len(questions.read()['items']) == 1
    def attempt(i):
        try:
            return update(questions, q, provisional_answer=str(i))
        except ResearchConflict:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(r is not None for r in pool.map(attempt, range(4))) == 1
    reopened = ResearchQuestions(ResearchStore(store.path), tid)
    history = reopened.read(question_id=q['question_id'], history=True)['items']
    assert [r['revision'] for r in history] == [2, 1]
    assert history[0]['previous_revision_digest'] == history[1]['revision_digest']
    assert history[1]['provisional_answer'] == ''
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM research_events WHERE kind LIKE 'question.%'").fetchone()[0] == 2


def test_reference_exact_quote_extraction_and_thread_scope(world):
    store, tid, questions = world
    ref = reference(store, tid)
    q = create(questions, supporting=[ref])
    assert q['supporting'][0]['observed_in'] == []
    for changed in ({'quote': '없는 원문'}, {'locator': 'p2'}, {'extraction_revision': 2}):
        with pytest.raises(ValueError):
            update(questions, q, supporting=[{**ref, **changed}])
    other = store.create_thread('독립')['id']
    with pytest.raises(ValueError):
        create(ResearchQuestions(store, other), supporting=[ref])
    assert not ResearchQuestions(store, other).read()['items']
    with pytest.raises(ValueError):
        ResearchQuestions(store, other).apply([{'question_id': q['question_id'], 'expected_revision': 0, 'text': '침범'}])


def test_agent_new_reference_requires_read_and_receipts_cannot_be_forged(world):
    store, tid, questions = world
    ref = reference(store, tid)
    run, _ = store.begin_run(tid, '조사', 'first')
    change = {'expected_revision': 0, 'text': '효과?', 'supporting': [{**ref, 'observed_in': [{'run_id': run}]}]}
    with pytest.raises(ValueError, match='읽은 뒤'):
        questions.apply([change], origin='agent', run=run)
    with scope({'project_uid': store.uid, 'thread_id': tid, 'run_id': run, 'path': str(store.path), 'epoch': store.epoch, 'mode': 'research'}):
        ResearchLibrary(store, tid).read(ref['version_ref'])
    q = questions.apply([change], origin='agent', run=run)['items'][0]
    assert q['supporting'][0]['observed_in'] == [{'run_id': run}]
    store.write_response(tid, run, '완료', 'completed')
    with pytest.raises(ResearchConflict):
        questions.apply([{'question_id': q['question_id'], 'expected_revision': 1}], origin='agent', run=run)
    later, _ = store.begin_run(tid, '이어서', 'second')
    q = questions.apply([{'question_id': q['question_id'], 'expected_revision': 1, 'provisional_answer': '잠정 판단'}], origin='agent', run=later)['items'][0]
    assert q['supporting'][0]['observed_in'] == [{'run_id': run}]


def test_resolution_is_not_truth_and_new_information_reopens(world):
    store, tid, questions = world
    ref = reference(store, tid)
    counter = reference(store, tid, '다른 조건에서는 효과가 없다.')
    q = create(questions, supporting=[ref], contradicting=[counter], provisional_answer='조건에 따라 다르다', gaps=['조건 확인'])
    resolution = {'disposition': 'answered', 'rationale': '자료를 검토함'}
    with pytest.raises(ValueError):
        update(questions, q, resolution=resolution)
    with pytest.raises(ValueError, match='반박'):
        update(questions, q, gaps=[], resolution=resolution)
    with pytest.raises(ValueError, match='verified'):
        update(questions, q, resolution={'disposition': 'verified', 'rationale': '확인'})
    q = update(questions, q, gaps=[], resolution={**resolution, 'objections': [
        {'evidence_id': q['contradicting'][0]['evidence_id'], 'rationale': '서로 다른 조건을 비교한 자료다'}]})
    assert q['status'] == 'resolved'
    q = update(questions, q, gaps=['표본 차이도 확인'])
    assert q['status'] == 'open' and q['resolution'] is None
    assert questions.read(question_id=q['question_id'], history=True)['items'][1]['resolution']


def test_context_bounded_and_identity_survives_wording(world):
    store, tid, questions = world
    q = create(questions)
    duplicate = create(questions)
    assert duplicate['duplicate_candidates'] == [q['question_id']]
    updated = update(questions, q, text='새로운 질문 표현')
    assert updated['question_id'] == q['question_id'] and updated['fingerprint'] != q['fingerprint']
    assert questions.context(budget=1)['omitted'] == 2
    from research_runner import _context, QUESTIONS_ROLE
    payload = json.loads(_context(store, store.thread(tid), '질문').split('>\n', 1)[1].rsplit('\n<', 1)[0])
    assert payload['research_questions']['total'] == 2
    assert 'provisional_answer' in payload['research_questions']['items'][0]
    assert 'expected_revision' in QUESTIONS_ROLE
    other = store.create_thread('다른 대화')['id']
    assert ResearchQuestions(store, other).context()['total'] == 0


def test_public_operations_and_context_isolation(world, monkeypatch):
    import research_threads
    store, tid, questions = world
    monkeypatch.setattr(research_threads, 'resolve', lambda ref: ({'name': '연구'}, store))
    params = {'project_ref': store.uid, 'thread_ref': tid}
    out = research_threads.project_operation({**params, 'op': 'thread_update', 'questions': [{'expected_revision': 0, 'text': '조사할 질문'}]})
    qid = out['items'][0]['question_id']
    read = research_threads.project_operation({**params, 'op': 'thread_messages', 'questions_only': True, 'question_id': qid})
    assert read['items'][0]['text'] == '조사할 질문'
    with pytest.raises(ValueError):
        research_threads.project_operation({**params, 'op': 'thread_update', 'notes': '혼합', 'questions': []})
    with scope({'thread_id': tid, 'project_uid': store.uid}):
        with pytest.raises(PermissionError):
            research_threads.project_operation({**params, 'thread_ref': store.create_thread('다른')['id'], 'op': 'thread_messages', 'questions_only': True})


def test_chain_damage_fails_closed(world):
    store, tid, questions = world
    q = create(questions)
    update(questions, q, provisional_answer='새 답')
    with store.connect(True) as db:
        db.execute('DELETE FROM research_questions WHERE question_id=? AND revision=1', (q['question_id'],))
    with pytest.raises(ResearchConflict):
        questions.read()


def test_copy_preserves_history_in_new_project_namespace(tmp_path, monkeypatch):
    import system_docs
    from project_manager import ProjectManager
    monkeypatch.setattr(system_docs, 'update_inventory_projects', lambda *a: None)
    monkeypatch.setattr(system_docs, 'log_change', lambda *a: None)
    manager = ProjectManager(tmp_path)
    row = manager.create_project('원본', project_kind='research')
    store = ResearchStore(row['path'])
    tid = store.create_thread('질문')['id']
    q = create(ResearchQuestions(store, tid), supporting=[reference(store, tid)])
    copied = manager.copy_item(row['id'], '복제')
    clone = ResearchStore(copied['path'])
    questions = ResearchQuestions(clone, tid)
    restored = questions.read()['items'][0]
    assert restored['project_ref'] != q['project_ref']
    assert restored['question_id'] == q['question_id']
    update(questions, restored, provisional_answer='복제에서만 수정')
    assert ResearchQuestions(store, tid).read()['items'][0]['revision'] == 1


def test_library_mode_allows_local_questions_but_not_settings(world):
    from research_context import before
    store, tid, _ = world
    context = {'project_uid': store.uid, 'thread_id': tid, 'mode': 'library'}
    params = {'op': 'thread_update', 'project_ref': store.uid, 'thread_ref': tid, 'questions': []}
    with scope(context):
        before({'research_local': True}, params)
        with pytest.raises(PermissionError):
            before({'research_local': True}, {**params, 'mode': 'research'})
        with pytest.raises(PermissionError):
            before({'research_local': True}, {**params, 'thread_ref': 'other'})


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
