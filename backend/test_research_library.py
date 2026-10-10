"""불변 원문·재색인·자료 접근 인용·프로젝트 범위 계약."""
import boot_paths  # noqa: F401
import json
import pytest
from research_store import ResearchStore
from research_library import ResearchLibrary
from research_context import scope


@pytest.fixture
def lib(tmp_path, monkeypatch):
    import notebook_store
    monkeypatch.setattr(notebook_store, 'semantic_available', lambda: False)
    return ResearchLibrary(ResearchStore(tmp_path, 'library-one'))


def test_versions_keep_old_bytes_and_duplicate_capture_is_idempotent(lib):
    a = lib.capture('처음 확보한 교육 자료입니다.', title='논문', origin='https://example.org/p', run='r', call='c')
    again = lib.capture('처음 확보한 교육 자료입니다.', title='논문', origin='https://example.org/p', run='r', call='c')
    b = lib.capture('수정된 교육 자료입니다. 반론이 추가되었습니다.', title='논문', origin='https://example.org/p')
    assert a == again and a['source_ref'] == b['source_ref'] and a['version_ref'] != b['version_ref']
    assert '처음' in lib.read(a['version_ref'])['text']
    assert len(lib.versions(a['source_ref'])['items']) == 2


def test_file_snapshot_survives_removal_and_index_can_rebuild(lib, tmp_path):
    path = tmp_path / 'source.txt'
    path.write_text('교육 정책은 작은 학급의 교육 효과와 경제적 비용을 함께 평가합니다. ' * 20)
    receipt = lib.add_file(path)
    path.unlink()
    assert '교육 정책' in lib.read(receipt['version_ref'])['text']
    lib.index_pending()
    hits = lib.search('교육')['items']
    assert hits and hits[0]['version_ref'] == receipt['version_ref']
    lib.exclude(receipt['source_ref'])
    assert not lib.search('교육')['items']
    lib.exclude(receipt['source_ref'], False)
    assert lib.search('교육')['items']


def test_unsupported_preserves_original_and_reports_failure(lib, tmp_path):
    path = tmp_path / 'sample.bin'; path.write_bytes(b'\x00\x01\x02')
    receipt = lib.add_file(path)
    version = lib.version(receipt['version_ref'])
    assert lib.store.blob(version['blob']) == b'\x00\x01\x02'
    assert version['index_state'] == 'unsupported'
    assert version['error']


def test_citation_requires_actual_read_and_retains_extraction_revision(lib):
    receipt = lib.capture('교육 효과를 주장한 원문 자료입니다. 통제집단의 한계가 있습니다.', title='논문')
    vid = receipt['version_ref']
    marker = f'[자료:{vid}:문단 1]'
    assert not lib.citations(marker, 'run1')
    with scope({'project_uid': lib.store.uid, 'run_id': 'run1'}):
        content = lib.read(vid)
    loc = lib.paragraphs(vid)[0][0][0]
    marker = f'[자료:{vid}:{loc}]'
    cited = lib.citations(marker, 'run1')
    assert cited and cited[0]['extraction_revision'] == 1
    lib._extraction(vid, [(loc, '추출기 변경으로 달라진 문장입니다.')])
    assert '통제집단' in lib.citations(marker, 'run1')[0]['quote']
    assert '통제집단' in lib.read(vid, revision=1)['text']
    with pytest.raises(ValueError):
        lib.read(vid, revision=99)
    assert not lib.citations(marker, 'run2')


def test_project_scoped_search_and_references(lib, tmp_path):
    other = tmp_path / 'other'; other.mkdir()
    foreign = ResearchLibrary(ResearchStore(other, 'library-two'))
    a = lib.capture('교육 프로젝트에만 있는 비공개 연구자료입니다.', title='교육')
    b = foreign.capture('경제 프로젝트에만 있는 다른 비공개 연구자료입니다.', title='경제')
    lib.index_pending(); foreign.index_pending()
    assert not foreign.search('교육')['items']
    with pytest.raises(ValueError):
        foreign.read(a['version_ref'])
    assert foreign.search('경제')['items'][0]['version_ref'] == b['version_ref']


def test_capture_precedes_reduction_and_save_failure_closes_gate(lib, monkeypatch):
    import research_capture
    import research_context
    monkeypatch.setattr(research_capture, 'schedule_index', lambda path: None)
    tid = lib.store.create_thread('교육')['id']
    run, _ = lib.store.begin_run(tid, '조사', '1')
    ctx = dict(project_uid=lib.store.uid, epoch=lib.store.epoch, path=str(lib.store.path), thread_id=tid, run_id=run, mode='research')
    payload = {'text': '확보한 전체 본문 문장입니다. ' * 2000, 'token': 'secret-value'}
    with scope(ctx):
        result = research_context.observe({'router':'handler', 'tool':'read'}, {}, payload)
        assert result['research_materials']
    sources = lib.sources()['items']
    v = lib.version(sources[0]['version_ref'])
    raw = lib.store.blob(v['blob']).decode()
    assert 'secret-value' not in raw and payload['text'] in raw
    monkeypatch.setattr(research_context, '_capture', lambda *args: (_ for _ in ()).throw(OSError('disk full')))
    with scope(ctx):
        with pytest.raises(OSError): research_context.observe({'router':'handler'}, {}, payload)
        with pytest.raises(RuntimeError): research_context.before({'router':'handler'}, {})


def test_library_mode_blocks_external_dispatch(lib):
    from research_context import before
    with scope({'mode':'library'}):
        with pytest.raises(PermissionError): before({'router':'handler'}, {'query':'web'})
        before({'research_local':True}, {'op':'search'})
        with pytest.raises(PermissionError): before({'research_local':True}, {'op':'add'})


def test_deleted_derived_index_rebuilds_from_saved_bytes(lib):
    receipt = lib.capture('교육 자료의 원문은 색인 삭제와 별개로 남아 있어야 합니다. ' * 10, title='보존')
    lib.index_pending()
    assert lib.search('교육')['items']
    for suffix in ('', '-wal', '-shm'):
        lib.index.db_path.with_name(lib.index.db_path.name + suffix).unlink(missing_ok=True)
    lib.index_pending()
    assert lib.search('교육')['items'][0]['version_ref'] == receipt['version_ref']


def test_capture_copies_expiring_source_and_ignores_display_changes(lib, monkeypatch):
    import research_capture
    from common.spill import spill_write
    monkeypatch.setattr(research_capture, 'schedule_index', lambda *a: None)
    tid = lib.store.create_thread('교육')['id']; run, _ = lib.store.begin_run(tid, '조사', '1')
    ctx=dict(project_uid=lib.store.uid, epoch=lib.store.epoch, path=str(lib.store.path), thread_id=tid, run_id=run)
    full='모델에는 일부만 보여도 획득한 교육 원문 전체는 남깁니다. ' * 100
    ref=spill_write(json.dumps({'text':full},ensure_ascii=False))['ref']
    config={'router':'handler','tool':'crawl','research_coverage':'full'}
    result={'text':full[:100],'source_ref':ref,'_display':{'max_chars':10}}
    first=research_capture.capture(ctx,config,{'url':'https://example.org/p'},result,'1')
    result['_display']={'max_chars':20}
    second=research_capture.capture(ctx,config,{'url':'https://example.org/p'},result,'2')
    assert first['research_materials'][0]['version_ref']==second['research_materials'][0]['version_ref']
    assert len(first['research_materials'])==2
    from pathlib import Path
    Path(ref['path']).unlink()
    saved=lib.version(first['research_materials'][1]['version_ref'])
    assert full in lib.store.blob(saved['blob']).decode()




def test_thread_library_filters_before_ranking_versions_and_exclusion(lib):
    a = lib.store.create_thread('교육')['id']
    b = lib.store.create_thread('경제')['id']
    first, second = ResearchLibrary(lib.store, a), ResearchLibrary(lib.store, b)
    old = first.capture('교육 공동 자료의 첫 판본입니다. ' * 20, title='공동 주소', origin='https://example.org/shared')
    new = second.capture('교육 공동 자료의 수정 판본입니다. ' * 20, title='공동 주소', origin='https://example.org/shared')
    for i in range(40):
        second.capture('교육 교육 교육 다른 대화의 자료입니다. ' * 20, title=f'외부 {i}')
    lib.index_pending(limit=100)
    assert first.sources()['items'][0]['version_ref'] == old['version_ref']
    assert [v['version_ref'] for v in first.versions(old['source_ref'])['items']] == [old['version_ref']]
    assert first.search('교육', 1)['items'][0]['version_ref'] == old['version_ref']
    with pytest.raises(ValueError): first.read(new['version_ref'])
    first.exclude(old['source_ref'])
    assert not first.search('교육')['items']
    assert second.search('교육')['items']
    assert not second.version(new['version_ref'])['excluded']
    with scope({'project_uid':lib.store.uid,'thread_id':a,'run_id':'scope'}):
        assert not ResearchLibrary(lib.store).sources()['items']
        with pytest.raises(PermissionError): ResearchLibrary(lib.store, b)
        with pytest.raises(PermissionError): first.capture('혼입', title='거부', thread=b)


def test_docx_uses_existing_converter_without_chat_truncation(lib, tmp_path):
    from docx import Document
    document = Document(); document.add_paragraph('문서 첨부로 전달하는 교육 자료입니다. ' * 7000)
    path = tmp_path / '보고서.docx'; document.save(path)
    receipt = lib.add_file(path)
    paragraphs, _ = lib.paragraphs(receipt['version_ref'])
    assert sum(len(t) for _, t in paragraphs) > 100000
    assert lib.version(receipt['version_ref'])['index_state'] == 'pending'


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
