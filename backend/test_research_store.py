"""연구 정본의 격리·복구·프로젝트 수명 회귀. 라이브 프로젝트를 쓰지 않는다."""
import boot_paths  # noqa: F401
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from project_manager import ProjectManager
from research_store import ResearchStore, ResearchConflict
from research_library import ResearchLibrary


@pytest.fixture
def project(tmp_path, monkeypatch):
    import system_docs
    monkeypatch.setattr(system_docs, 'update_inventory_projects', lambda *a: None)
    monkeypatch.setattr(system_docs, 'log_change', lambda *a: None)
    manager = ProjectManager(tmp_path)
    row = manager.create_project('교육 연구', project_kind='research')
    return manager, row, ResearchStore(row['path'])


def test_thread_messages_never_mix_and_legacy_history_excludes_research(project):
    _, _, store = project
    first, second = [store.create_thread(title)['id'] for title in ('교육', '경제')]
    a, _ = store.begin_run(first, '교육 질문', 'a')
    b, _ = store.begin_run(second, '경제 질문', 'b')
    store.write_response(first, a, '교육 답', 'completed')
    store.write_response(second, b, '경제 답', 'completed')
    assert [m['content'] for m in store.messages(first)['items']] == ['교육 질문', '교육 답']
    assert [m['content'] for m in store.messages(second)['items']] == ['경제 질문', '경제 답']
    user = store.conversations.get_or_create_agent('user', 'human')
    agent = store.conversations.get_or_create_agent('연구 도우미', 'ai_agent')
    assert not store.conversations.get_history_for_ai(agent, user)


def test_idempotent_send_and_one_active_turn(project):
    store = project[2]
    tid = store.create_thread('교육')['id']
    run, fresh = store.begin_run(tid, '첫 질문', 'request1')
    assert fresh
    assert store.begin_run(tid, '첫 질문', 'request1') == (run, False)
    with pytest.raises(ResearchConflict):
        store.begin_run(tid, '다른 내용', 'request1')
    with pytest.raises(ResearchConflict):
        store.begin_run(tid, '두 번째', 'request2')
    store.recover_runs(set())
    assert store.messages(tid)['items'][-1]['status'] == 'interrupted'
    assert store.thread(tid)['active_run'] is None
    with pytest.raises(ResearchConflict):
        store.write_response(tid, run, '늦은 답변')
    assert store.begin_run(tid, '다음 질문', 'request2')[1]


def test_concurrent_requests_reserve_only_one_run(project):
    store = project[2]
    tid = store.create_thread('교육')['id']
    def start(_):
        return store.begin_run(tid, '같은 질문', 'same')
    with ThreadPoolExecutor(max_workers=6) as pool:
        runs = list(pool.map(start, range(6)))
    assert len({r[0] for r in runs}) == 1
    assert sum(r[1] for r in runs) == 1
    assert len(store.messages(tid)['items']) == 2


def test_rename_copy_trash_restore_preserve_data_and_invalidate_old_writers(project):
    manager, row, old = project
    tid = old.create_thread('교육')['id']
    lib = ResearchLibrary(old)
    receipt = lib.capture('변하지 않는 원문입니다. 학급 규모 교육 연구.', title='논문')
    renamed = manager.rename_item(row['id'], '교육 장기 연구')
    assert renamed['project_uid'] == old.uid
    with pytest.raises((ResearchConflict, sqlite3.OperationalError)):
        old.put_blob('이동 전 작업자')
    store = ResearchStore(renamed['path'])
    assert ResearchLibrary(store).read(receipt['version_ref'])['text'].endswith('교육 연구.')
    copied = manager.copy_item(renamed['id'], '연구 복제')
    assert copied['project_kind'] == 'research' and copied['project_uid'] != store.uid
    clone = ResearchStore(copied['path'])
    assert clone.thread(tid)['title'] == '교육'
    assert ResearchLibrary(clone).read(receipt['version_ref'])['text'].endswith('교육 연구.')
    manager.move_to_trash(renamed['id'])
    with pytest.raises(ResearchConflict):
        store.put_blob('휴지통 뒤 늦은 자료')
    manager.restore_from_trash(renamed['id'])
    assert ResearchStore(renamed['path']).thread(tid)['title'] == '교육'
    manager.delete_project(renamed['id'], False)
    with pytest.raises(ResearchConflict):
        store.put_blob('삭제 뒤 늦은 자료')
    assert not store.root.exists()


def test_lifecycle_blocks_running_conversation(project):
    manager, row, store = project
    tid = store.create_thread('교육')['id']
    store.begin_run(tid, '조사해줘', 'a')
    for action in (lambda: manager.rename_item(row['id'], 'new'), lambda: manager.copy_item(row['id']),
                   lambda: manager.move_to_trash(row['id']), lambda: manager.delete_project(row['id'], False)):
        with pytest.raises(ResearchConflict):
            action()
    assert store.path.exists()


def test_note_revision_and_archive(project):
    store = project[2]
    tid = store.create_thread('교육')['id']
    store.update_thread(tid, expected=1, notes='작은 학급의 반론도 조사')
    with pytest.raises(ResearchConflict):
        store.update_thread(tid, expected=1, notes='덮어쓰기')
    store.update_thread(tid, archived=True)
    with pytest.raises(ResearchConflict):
        store.begin_run(tid, '질문', '1')
    assert not store.threads()['items']
    assert len(store.threads(archived=True)['items']) == 1


def test_project_template_upgrade_preserves_user_templates(tmp_path, monkeypatch):
    import json
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root / 'scripts'))
    import build_core_manifest
    manifest = build_core_manifest.build_manifest()
    assert 'templates/research' in manifest['core']['instruments']
    manifest['retired'] = {}
    resources, user = tmp_path / 'resources', tmp_path / 'user'
    for base in (resources, user):
        folder = base / 'data/instruments/templates'
        folder.mkdir(parents=True)
        (folder / 'research.yaml').write_text('new research' if base == resources else 'old research')
        (folder / 'personal.yaml').write_text('bundle personal' if base == resources else 'my personal')
    (resources / 'data/core_manifest.json').write_text(json.dumps(manifest))
    script = """
import { syncUserData } from './frontend/electron/userdata_sync.js';
syncUserData({resourcesPath: process.argv[1], userDataPath: process.argv[2], log: () => {}});
"""
    subprocess.run(['node', '--input-type=module', '-e', script, str(resources), str(user)],
                   cwd=root, check=True, capture_output=True, timeout=20)
    assert (user / 'data/instruments/templates/research.yaml').read_text() == 'new research'
    assert (user / 'data/instruments/templates/personal.yaml').read_text() == 'my personal'


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
