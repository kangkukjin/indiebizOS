"""연구 저장소와 프로젝트 수명 전환의 직렬화. 프로젝트 이름은 신원이 아니다."""
import functools
import shutil
import sqlite3
import threading
from contextlib import ExitStack
from pathlib import Path

_guard = threading.Lock()
_locks = {}


def project_lock(path):
    with _guard:
        return _locks.setdefault(str(Path(path).resolve()), threading.RLock())


def lifecycle(fn):
    """이동/삭제 중 새 저장을 막고 기존 실행은 명시적으로 중단하도록 안내한다."""
    @functools.wraps(fn)
    def guarded(manager, *args, **kwargs):
        from research_store import ResearchStore, ResearchConflict
        rows = manager.list_projects()
        item = args[0] if args else kwargs.get('item_id', kwargs.get('name'))
        ids = {p['id'] for p in rows if (p.get('in_trash') if fn.__name__ == 'empty_trash'
                                       else item in {p['id'], p.get('name')})}
        while True:
            children = {p['id'] for p in rows if p.get('parent_folder') in ids}
            if children <= ids:
                break
            ids |= children
        affected = [p for p in rows if p['id'] in ids and p.get('project_kind') == 'research']
        with ExitStack() as stack:
            stores = []
            for row in sorted(affected, key=lambda p: p['id']):
                path = manager.get_project_path(row['id'])
                stack.enter_context(project_lock(path))
                if not path.exists():
                    continue
                store = ResearchStore(path)
                with store.connect() as db:
                    if db.execute('SELECT 1 FROM research_threads WHERE active_run IS NOT NULL').fetchone():
                        raise ResearchConflict('연구 대화가 진행 중입니다. 대화에서 중단한 뒤 다시 시도하세요')
                stores.append(store)
            # 복제는 원본 신원을 무효화할 필요가 없다. 다른 전환은 늦은 작업의 쓰기를 차단한다.
            if fn.__name__ != 'copy_item':
                for store in stores:
                    with store.connect(True) as db:
                        enabled = 0 if fn.__name__ in {'move_to_trash', 'delete_project', 'empty_trash'} else 1
                        db.execute('UPDATE research_project SET epoch=epoch+1,enabled=?', (enabled,))
            try:
                return fn(manager, *args, **kwargs)
            except BaseException:
                for store in stores:
                    if store.db_path.exists():
                        with store.connect(True) as db:
                            db.execute('UPDATE research_project SET enabled=1')
                raise
    return guarded


def copy_project(source, destination, uid):
    """SQLite는 온라인 백업으로, 불변 파일은 그대로 복제. 색인은 재생성한다."""
    from research_store import ResearchStore
    source, destination = Path(source), Path(destination)
    try:
        shutil.copytree(source, destination, ignore=shutil.ignore_patterns(
            'conversations.db*', 'index.db*', 'staging'))
        with sqlite3.connect(source / 'conversations.db', timeout=10) as src:
            with sqlite3.connect(destination / 'conversations.db', timeout=10) as dst:
                src.backup(dst)
                dst.execute('UPDATE research_project SET uid=?,epoch=epoch+1,enabled=1', (uid,))
                dst.execute("UPDATE research_jobs SET state='pending',index_source=NULL,error=''")
        store = ResearchStore(destination)
        store.recover_runs(set())
    except BaseException:
        if destination.exists():
            shutil.rmtree(destination)
        raise
