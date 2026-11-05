"""Only authenticated, current-run public reading excerpts reach the partial display."""
import boot_paths  # noqa: F401
import pytest
from research_store import ResearchStore
from research_library import ResearchLibrary
from research_partial_results import collect
from research_threads import chat_activity


@pytest.fixture
def reading(tmp_path):
    store = ResearchStore(tmp_path, 'p')
    tid = store.create_thread('연구')['id']
    run, _ = store.begin_run(tid, '비교해줘', 'r')
    lib = ResearchLibrary(store, tid)
    def add(origin='https://example.org/source', quote='확보한 원문', read_run=None):
        receipt = lib.capture('확보한 원문', title='출처', origin=origin, run=run,
                              paragraphs=[['p1', '확보한 원문']])
        with store.connect(True) as db:
            db.execute('INSERT INTO research_access VALUES (?,?,?,?,?)',
                       (read_run or run, receipt['version_ref'], 1, 'p1', quote))
        return receipt
    return store, tid, run, add


def test_public_read_excerpts_are_persistent_and_not_final( reading):
    store, tid, run, add = reading
    receipt = add()
    events = collect(store, tid, run)
    assert len(events) == 1 and events[0]['state'] == 'observed'
    assert events[0]['content'] == '확보한 원문'
    assert events[0]['version'] == receipt['version_ref']
    with store.connect(True) as db:
        store.event(db, 'partial_result', events[0], tid, run)
        store.event(db, 'partial_result', events[0], tid, run)
    restored = chat_activity(ResearchStore(store.path), tid, run)['tool_activities']
    assert len(restored) == 1 and restored[0]['partialResult']['content'] == '확보한 원문'
    assert store.thread(tid)['active_run'] == run


@pytest.mark.parametrize('case', ['private', 'unread', 'forged', 'cancel', 'excluded'])
def test_partial_display_never_opens_unverified_or_private_content(reading, case):
    store, tid, run, add = reading
    receipt = add(origin='/private/draft.md' if case == 'private' else 'https://example.org/source',
                  quote='위조 인용' if case == 'forged' else '확보한 원문',
                  read_run='another-run' if case == 'unread' else None)
    if case == 'excluded':
        with store.connect(True) as db:
            db.execute('UPDATE research_sources SET excluded=1 WHERE id=?', (receipt['source_ref'],))
    events = collect(store, tid, run, cancelled=lambda: case == 'cancel')
    assert not any(e['state'] == 'observed' for e in events)
    assert all(not e['content'] for e in events)


def test_removed_source_withdraws_persisted_excerpt(reading):
    store, tid, run, add = reading
    add()
    event = collect(store, tid, run)[0]
    with store.connect(True) as db:
        store.event(db, 'partial_result', event, tid, run)
        db.execute('DELETE FROM research_access WHERE run_id=?', (run,))
    current = collect(store, tid, run)
    assert len(current) == 1 and current[0]['id'] == event['id']
    assert current[0]['state'] == 'withdrawn' and current[0]['content'] == ''
