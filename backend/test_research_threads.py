"""공개 판본 2 입구에서 생성·조회·접수·취소까지 검증한다."""
import boot_paths  # noqa: F401
import json
import threading
import time

import pytest
from test_lifecycle_vocab_2026_10_05 import world, _run


def test_research_public_ibl_roundtrip(world, monkeypatch):
    import research_threads as service
    import launcher_ops
    monkeypatch.setattr(service, 'schedule_index', lambda *a: None)
    row = launcher_ops.project_op({'op':'create','name':'교육 연구','project_kind':'research'})
    # project_op wraps creation in items; assert canonical row's type survives public service.
    from project_manager import ProjectManager
    project = next(p for p in ProjectManager().list_projects() if p['id']=='교육 연구')
    uid = project['project_uid']
    pp = project['path']
    result = _run('[self:project]{op:"thread_create",project_ref:$project,title:"교육"}', pp, {'project':uid})
    assert result.get('success') is not False, result
    serialized = json.dumps(result, ensure_ascii=False)
    assert 'thread_ref' in serialized, result
    thread = service.project_operation({'op':'thread_list','project_ref':uid})['items'][0]
    result = _run('[self:project]{op:"thread_messages",project_ref:$project,thread_ref:$thread}', pp, {'project':uid,'thread':thread['id']})
    assert result.get('success') is not False, result
    assert 'active_run' in json.dumps(result), result
    manifest = _run('[self:project]{op:"research_view",project_ref:$project,thread_ref:$thread}', pp, {'project':uid,'thread':thread['id']})
    assert manifest.get('success') is not False and 'manifest' in json.dumps(manifest), manifest


def test_stream_persists_final_and_cancel_receipts(world, monkeypatch):
    import research_threads as service
    from project_manager import ProjectManager
    from research_store import ResearchStore
    import runtime_work
    monkeypatch.setattr(service, 'schedule_index', lambda *a: None)
    row=ProjectManager().create_project('실행 연구', project_kind='research')
    store=ResearchStore(row['path']); tid=store.create_thread('교육')['id']
    started, finish = threading.Event(), threading.Event()
    def stream(store, tid, run, message, cancel):
        started.set()
        yield {'type':'text','content':'부분 응답'}
        finish.wait(3)
        yield {'type':'final','content':'완성한 응답'}
    monkeypatch.setattr(service,'_run_stream',stream)
    monkeypatch.setattr(service,'_summarize',None)
    receipt=service.start(store,tid,'교육 질문','request1')
    assert started.wait(2)
    run=store.thread(tid)['active_run']
    assert run
    duplicate=service.start(store,tid,'교육 질문','request1')
    assert duplicate['task_ref']['task_id']==run
    service.cancel_task({'kind':'research','task_id':run,'owner':store.uid})
    finish.set()
    deadline=time.monotonic()+4
    while store.thread(tid)['active_run'] and time.monotonic()<deadline:
        time.sleep(.02)
    assert store.messages(tid)['items'][-1]['status']=='cancelled'
    assert store.messages(tid)['items'][-1]['content']=='완성한 응답'


def test_summary_failure_preserves_completed_answer(world, monkeypatch):
    import research_threads as service
    import runtime_work
    import thread_context
    from project_manager import ProjectManager
    from research_store import ResearchStore
    row = ProjectManager().create_project('요약 실패 연구', project_kind='research')
    store = ResearchStore(row['path'])
    tid = store.create_thread('교육')['id']
    run, _ = store.begin_run(tid, '교육 질문', 'summary-failure')
    def summarize(*args):
        raise RuntimeError('보조 모델 일시 오류')
    monkeypatch.setattr(service, '_run_stream', lambda *args: iter([{'type': 'final', 'content': '보존할 답변'}]))
    monkeypatch.setattr(service, '_summarize', summarize)
    snapshot = thread_context.snapshot()
    try:
        service._work(store, tid, run, '교육 질문', threading.Event(),
                      runtime_work.reserve('research-chat'), snapshot)
    finally:
        thread_context.restore(snapshot)
    answer = store.messages(tid)['items'][-1]
    assert answer['content'] == '보존할 답변'
    assert answer['status'] == 'completed'
    assert store.thread(tid)['active_run'] is None


def test_foreign_principal_cannot_read_research(world, monkeypatch):
    import principal
    import research_threads as service
    from project_manager import ProjectManager
    row=ProjectManager().create_project('비공개', project_kind='research')
    token=principal.set_transport(principal.ANONYMOUS)
    try:
        with pytest.raises(PermissionError): service.notebook_operation({'op':'sources','project_ref':row['project_uid']})
    finally:
        principal.reset_transport(token)


def test_notebook_research_public_binding_and_capture_gate(world, monkeypatch):
    import research_capture
    import research_threads
    from research_context import scope
    from project_manager import ProjectManager
    from research_store import ResearchStore
    monkeypatch.setattr(research_threads, 'schedule_index', lambda *a: None)
    monkeypatch.setattr(research_capture, 'schedule_index', lambda *a: None)
    row=ProjectManager().create_project('자료 연구', project_kind='research')
    store=ResearchStore(row['path'])
    tid=store.create_thread('교육')['id']
    inputs={'project':store.uid,'thread':tid,'text':'교육 연구의 실제 자료 내용입니다. 작고 큰 학급의 차이를 관찰합니다.'}
    result=_run('[self:notebook]{op:"add",project_ref:$project,thread_ref:$thread,text:$text,title:"자료"}', row['path'], inputs)
    assert result.get('success') is not False, result
    sources=research_threads.notebook_operation({'op':'sources','project_ref':store.uid,'thread_ref':tid})['items']
    assert len(sources)==1, result
    vid=sources[0]['version_ref']
    run,_=store.begin_run(tid,'자료 질문','1')
    with scope(dict(project_uid=store.uid,epoch=store.epoch,path=row['path'],thread_id=tid,run_id=run,mode='library')):
        result=_run('[self:notebook]{op:"read",project_ref:$project,version_ref:$version}',row['path'],dict(project=store.uid,version=vid))
        assert result.get('success') is not False, result
        assert '교육 연구의 실제' in json.dumps(result,ensure_ascii=False)
        blocked=_run('[sense:search]{query:"외부 검색"}',row['path'])
        assert blocked.get('success') is False, blocked




def test_attachment_originals_message_reopen_and_model_input(world, monkeypatch, tmp_path):
    import base64
    import research_threads as service
    from research_runner import attachment_input
    from research_library import ResearchLibrary
    from research_store import ResearchStore, ResearchConflict
    from project_manager import ProjectManager
    monkeypatch.setattr(service, 'schedule_index', lambda *a: None)
    row = ProjectManager().create_project('첨부 연구', project_kind='research')
    store = ResearchStore(row['path']); tid = store.create_thread('교육')['id']
    path = tmp_path / '근거.txt'; path.write_text('첨부 문서에 담긴 교육 정책의 근거입니다. ' * 10)
    image = tmp_path / '사진.png'
    image.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII='))
    params = [{'path':str(path),'name':path.name}, {'path':str(image),'name':image.name}]
    attachments = service.prepare_attachments(store, tid, params, 'req')
    assert service.prepare_attachments(store, tid, params, 'req') == attachments
    run, fresh = store.begin_run(tid, '', 'req', attachments)
    assert fresh and not store.begin_run(tid, '', 'req', attachments)[1]
    with pytest.raises(ResearchConflict): store.begin_run(tid, '', 'req', attachments[:1])
    raw = image.read_bytes(); path.unlink(); image.unlink()
    reopened = ResearchStore(row['path'])
    assert reopened.messages(tid)['items'][0]['attachments'] == attachments
    message, images = attachment_input(reopened, tid, run, '')
    assert '교육 정책의 근거' in message
    assert base64.b64decode(images[0]['base64']) == raw
    assert len(ResearchLibrary(reopened, tid).sources()['items']) == 2
    other = reopened.create_thread('경제')['id']
    assert not ResearchLibrary(reopened, other).sources()['items']


def test_agent_cannot_read_another_thread_or_unscoped_library(world, monkeypatch):
    import research_threads as service
    from research_context import scope, before
    from project_manager import ProjectManager
    from research_store import ResearchStore
    monkeypatch.setattr(service, 'schedule_index', lambda *a: None)
    row = ProjectManager().create_project('격리 연구', project_kind='research')
    store = ResearchStore(row['path']); a = store.create_thread('교육')['id']; b = store.create_thread('경제')['id']
    with pytest.raises(ValueError): service.notebook_operation({'op':'sources','project_ref':store.uid})
    with scope({'project_uid':store.uid,'thread_id':a,'run_id':'test'}):
        with pytest.raises(PermissionError): service.notebook_operation({'op':'sources','project_ref':store.uid,'thread_ref':b})
        with pytest.raises(PermissionError): service.project_operation({'op':'thread_messages','project_ref':store.uid,'thread_ref':b})
        with pytest.raises(PermissionError): service.project_operation({'op':'thread_search','project_ref':store.uid})
        with pytest.raises(PermissionError): before({'research_local':True}, {'project_ref':store.uid,'thread_ref':b})
        assert service.notebook_operation({'op':'sources','project_ref':store.uid})['items'] == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
