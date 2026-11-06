"""Provider-independent persistent analysis, owned by workspace and backend lifetime."""
import atexit
import json
import threading
import time
from pathlib import Path

from code_analysis_scope import check, current_scope
from coding_git import CodingConflict, safe_path
from coding_store import fingerprint, identifier
from code_analysis_changes import identity
from code_analysis_drivers import environment, inventory, registry, select, project_root
from lsp_transport import LspError
from lsp_positions import encode

_MANAGERS, _LOCK = {}, threading.RLock()


def manager(store):
    with _LOCK:
        key = str(store.root)
        if key not in _MANAGERS:
            _MANAGERS[key] = Analysis(store)
        return _MANAGERS[key]


def shutdown(*, require_idle=False):
    with _LOCK:
        if require_idle and any(s.active for app in _MANAGERS.values() for s in app.sessions.values()):
            raise RuntimeError("분석 요청 종료 후 서버를 설치하세요")
        old = list(_MANAGERS.values())
        _MANAGERS.clear()
    for app in old:
        app.close()


atexit.register(shutdown)


class Analysis:
    def __init__(self, store):
        self.store, self.sessions = store, {}
        self.lock, self.stop = threading.RLock(), threading.Event()
        self.reaper = None

    def inspect(self, path):
        root = Path(path).expanduser().resolve(strict=True)
        check(root)
        if not root.is_dir():
            raise ValueError('코드 뷰의 path는 프로젝트 폴더입니다')
        row = {'id': 'codeview_' + fingerprint([str(root), identity(root), current_scope()])[:32],
               'name': root.name, 'path': str(root), 'mode': 'inspect', 'root_identity': identity(root)}
        return self.store.save('code_view', row)

    def validate(self, row):
        check(row['path'])
        if row.get('root_identity') and row['root_identity'] != identity(row['path']):
            raise CodingConflict('코드 뷰의 디렉터리가 교체됐습니다. 다시 여세요')

    def view(self, row, ref):
        value = self.store.get('code_snapshot' if ref.startswith('codesnapshot_') else 'code_draft', ref)
        if value['project'] != row['id'] or value['root_identity'] != identity(row['path']):
            raise PermissionError('다른 작업 공간·세대의 초안입니다')
        if value.get('closed'):
            raise CodingConflict('닫힌 초안 뷰입니다')
        return value

    def draft(self, row, *, client, view=None, path=None, text=None, expected=None, action='update'):
        self.validate(row)
        if not isinstance(client, str) or not client:
            raise ValueError('초안의 작성 창 client가 필요합니다')
        with self.store.lock('workspace:' + row['id']):
            if view:
                value = self.view(row, view)
                if value['client'] != client:
                    raise PermissionError('다른 작성 창의 초안입니다')
                if expected != value['revision']:
                    raise CodingConflict('초안 판본이 바뀌었습니다')
            else:
                value = {'id': identifier('code_draft'), 'project': row['id'], 'client': client, 'revision': 0,
                         'root_identity': identity(row['path']), 'files': {}, 'originals': {}}
            if value.get('pending_save') and action not in ('save', 'close'):
                raise CodingConflict('중단된 초안 저장을 먼저 다시 실행해 복구하세요')
            if action == 'close':
                value['closed'] = True
                self.close_view(row['id'], value['id'])
            elif action == 'save':
                check(row['path'], write=True)
                from code_analysis_changes import apply, prepare, encoded, decode, decoded
                if row.get('mode') == 'inspect':
                    raise PermissionError('inspect 뷰의 초안은 저장할 수 없습니다')
                edits = []
                for relative, content in value['files'].items():
                    original = value['originals'][relative]
                    encoding = decode(decoded(original['bytes']), relative)[1] if original['bytes'] is not None else 'utf-8'
                    after = {'bytes': encoded(encode(content, encoding)) if content is not None else None, 'mode': original['mode']}
                    edits.append({'path': relative, 'before': original, 'after': after})
                if not value.get('pending_save'):
                    proposal = prepare(self.store, row, edits, selector={'draft': value['id']})
                    value['pending_save'] = proposal['proposal']
                    self.store.save('code_draft', value)
                result = apply(self.store, row, value['pending_save'], recover=True)
                value['files'], value['originals'] = {}, {}
                value['last_save'] = result
                value.pop('pending_save')
            elif action == 'update':
                if not isinstance(text, str) or not path:
                    raise ValueError('초안에는 path와 text가 필요합니다')
                from code_analysis_changes import state
                target = safe_path(row['path'], path)
                value['originals'].setdefault(path, state(target))
                value['files'][path] = text
            else:
                raise ValueError('draft.action은 update/save/close입니다')
            value['revision'] += 1
            self.store.save('code_draft', value)
            return {'view': value['id'], 'revision': value['revision'], 'files': value['files'],
                    'closed': value.get('closed', False), 'saved': action == 'save'}

    def capabilities(self, row):
        self.validate(row)
        return {'coordinates': 'unicode_codepoint_1based', 'view': 'saved', 'servers': inventory(),
                'read': ['symbols', 'definition', 'declaration', 'type_definition', 'implementation', 'references',
                         'hover', 'signature', 'calls', 'types', 'diagnostics', 'completion', 'actions', 'batch'],
                'propose': ['rename', 'code_action', 'completion', 'format'],
                'sessions': [{'server': s.name, 'generation': s.generation, 'capabilities': s.capabilities,
                              'server_info': s.server_info, 'environment': s.environment, 'position_encoding': s.encoding}
                             for key, s in self.sessions.items() if key[0] == row['id']],
                'status': 'available' if any(i['installed'] for i in inventory()) else 'unavailable',
                'policy': registry()['policy'], 'inspect': row.get('mode') == 'inspect'}

    def session(self, row, selector):
        self.validate(row)
        view_id = selector.get('view', (selector.get('target') or {}).get('view', 'saved'))
        view = self.view(row, view_id) if view_id != 'saved' else None
        target = selector.get('path') or (selector.get('target') or {}).get('path') or next(iter(selector.get('paths', [])), None)
        if selector.get('ref'):
            record = self.store.get('workspace_analysis', selector['ref'])
            if record['project'] != row['id'] or record['view'] != view_id:
                raise PermissionError('다른 작업 공간·뷰의 참조입니다')
            name, spec = select(server=record['server'])
        else:
            if selector.get('analysis') == 'batch' and not target:
                first = next(iter(selector.get('requests', [])), {})
                target = first.get('path') or (first.get('target') or {}).get('path')
            name, spec = select(target, selector.get('server'))
        if target:
            safe_path(row['path'], target)
        source_row = row
        if view:
            from code_analysis_views import mirror
            with self.store.lock('workspace:' + row['id']):
                source_row = {**row, 'path': str(mirror(self.store, row, view, fixed=view.get('fixed', False)))}
        project = project_root(source_row['path'], target, spec)
        _, _, settings = environment(project, spec)
        from principal import cache_key
        key = (row['id'], view_id, name, str(project), fingerprint([identity(row['path']), cache_key(), {k: v for k, v in (current_scope() or {}).items() if k != 'writable'}, str(project), settings]))
        with self.lock:
            for old_key, old in list(self.sessions.items()):
                if old_key[:4] == key[:4] and (old_key != key or old.client.failure):
                    if old.active:
                        raise LspError('SERVER_RESTART_PENDING', '환경이 변경되어 진행 요청 종료 후 서버를 재시작합니다')
                    self.sessions.pop(old_key).close()
            if key not in self.sessions:
                self.reap(limit=True)
                if len(self.sessions) >= registry()['policy']['max_servers']:
                    raise LspError('SERVER_CAPACITY', '분석 서버 한도에 도달했습니다. 진행 요청 종료 후 다시 시도하세요')
                from code_analysis_documents import Session
                runtime = self.store.root / 'analysis_runtime' / fingerprint(key)[:24]
                self.sessions[key] = Session(source_row, name, spec, runtime, confined=bool(current_scope()), project_root=project)
            session = self.sessions[key]
            session.active += 1
            session.last_used = time.monotonic()
            if not self.reaper:
                self.reaper = threading.Thread(target=self._reap_loop, daemon=True, name='analysis-reaper')  # cc-ok: close owns stop and join
                from runtime_work import service_scope
                with service_scope(own_processes=True):
                    self.reaper.start()
            return session, view_id

    def query(self, row, selector, *, propose=False, cancelled=None):
        # A projection and the revision attached to its result must describe the same draft.
        with self.store.lock('workspace:' + row['id']):
            return self._query(row, selector, propose=propose, cancelled=cancelled)

    def _query(self, row, selector, *, propose=False, cancelled=None):
        selector = dict(selector)
        if selector.get('analysis') == 'batch' and not propose:
            requests = selector.get('requests', [])
            if not isinstance(requests, list) or len(requests) > 50 or any(r.get('analysis') == 'batch' for r in requests):
                raise ValueError('batch는 중첩 없는 읽기 요청 50개 이하입니다')
            items = []
            for request in requests:
                try:
                    result = self.query(row, {**request, **({'view': selector['view']} if selector.get('view') else {})}, cancelled=cancelled)
                    items.append({'success': True, **result})
                except (ValueError, LspError, OSError) as exc:
                    items.append({'success': False, 'error': str(exc), 'code': getattr(exc, 'code', 'INVALID_REQUEST')})
            return {'items': items, 'analysis': {'status': 'received' if all(i['success'] for i in items) else 'partial',
                                               'view': selector.get('view', 'saved'), 'project_graph_confirmed': False}}
        if cancelled is None:
            from execution_turn import current
            binding = current()
            cancelled = getattr(binding, 'cancel_check', None)
        if propose and selector.get('view', (selector.get('target') or {}).get('view', '')).startswith('codesnapshot_'):
            raise PermissionError('고정 스냅샷은 읽기 전용입니다')
        session, view = self.session(row, selector)
        try:
            with session.lock:
                session.synchronize()
                from code_analysis_operations import Operations
                operation = Operations(session, self.store, row, view, cancelled)
                result = operation.propose(selector) if propose else operation.read(selector)
                captured = {uri: doc['hash'] for uri, doc in session.documents.items()}
                session.synchronize()
                changed = [uri for uri, hashed in captured.items() if uri not in session.documents or session.documents[uri]['hash'] != hashed]
                metadata = {'server': session.name, 'server_info': session.server_info, 'generation': session.generation,
                            'view': view, 'status': 'stale' if changed else 'received', 'changed_documents': changed,
                            'documents': [{'uri': uri, 'hash': d['hash'], 'observed_version': d['version'],
                                           'server_confirmed_version': None} for uri, d in session.documents.items()],
                            'consistency': 'document_versions_observed', 'project_graph_confirmed': False,
                            'environment': session.environment, 'watch_error': session.watch_error}
                if propose and changed:
                    raise CodingConflict('분석 중 원본이 변경됐습니다. 제안을 다시 요청하세요')
                if propose and view != 'saved':
                    p = self.store.get('workspace_proposal', result['proposal'])
                    p['view'], p['draft_revision'] = view, self.view(row, view)['revision']
                    self.store.save('workspace_proposal', p)
                items = result.get('items', [])
                limit, offset = selector.get('limit', 200), selector.get('offset', 0)
                if type(limit) is not int or not 1 <= limit <= 1000 or type(offset) is not int or offset < 0:
                    raise ValueError('limit은 1~1000, offset은 0 이상의 정수입니다')
                result['total'] = len(items)
                if offset or len(items) > limit:
                    from common.spill import spill_write
                    full = spill_write(json.dumps({**result, 'analysis': metadata}, ensure_ascii=False), 'code_analysis')
                    result.update(items=items[offset:offset + limit], offset=offset, truncated=True, full_result=full['ref'])
                return {**result, 'analysis': metadata}
        finally:
            with self.lock:
                session.active -= 1
                session.last_used = time.monotonic()
                if getattr(session, 'retired', False) and not session.active:
                    for key, value in list(self.sessions.items()):
                        if value is session:
                            self.sessions.pop(key).close()

    def apply_draft(self, row, proposal, client):
        from code_analysis_changes import decoded, encoded
        with self.store.lock('workspace:' + row['id']):
            p = self.store.get('workspace_proposal', proposal)
            value = self.view(row, p['view'])
            if value['client'] != client:
                raise PermissionError('다른 작성 창의 초안입니다')
            if value.get('pending_save'):
                raise CodingConflict('중단된 초안 저장을 먼저 다시 실행해 복구하세요')
            if p.get('state') == 'applied':
                return p['result']
            if p['draft_revision'] != value['revision']:
                raise CodingConflict('초안이 제안 이후 바뀌었습니다')
            from code_analysis_changes import state
            for e in p['edits']:
                relative = e['path']
                original = state(safe_path(row['path'], relative))
                value['originals'].setdefault(relative, original)
                value['files'][relative] = __import__('lsp_positions').decode(decoded(e['after']['bytes']), relative)[0] if e['after']['bytes'] is not None else None
            value['revision'] += 1
            p.update(state='applied', result={'proposal': proposal, 'applied': True, 'view': value['id'],
                     'revision': value['revision'], 'files': value['files'], 'saved': False})
            self.store.save_many([('code_draft', value), ('workspace_proposal', p)])
            return p['result']

    def close_view(self, resource, view=None):
        with self.lock:
            for key in list(self.sessions):
                if key[0] == resource and (view is None or key[1] == view):
                    session = self.sessions[key]
                    if session.active:
                        session.retired = True
                    else:
                        self.sessions.pop(key).close()

    def reap(self, limit=False):
        import psutil
        policy = registry()['policy']
        total = 0
        for s in self.sessions.values():
            try:
                parent = psutil.Process(s.client.process.pid)
                total += sum(p.memory_info().rss for p in [parent, *parent.children(recursive=True)])
            except psutil.Error:
                pass
        for key, s in sorted(list(self.sessions.items()), key=lambda item: item[1].last_used):
            over = total > policy['memory_mb'] * 1024 * 1024 or limit and len(self.sessions) >= policy['max_servers']
            if not s.active and (over or time.monotonic() - s.last_used > policy['idle_seconds']):
                self.sessions.pop(key).close()
                if over:
                    break

    def _reap_loop(self):
        while not self.stop.wait(10):
            with self.lock:
                self.reap()

    def close(self):
        self.stop.set()
        with self.lock:
            for session in self.sessions.values():
                session.close()
            self.sessions.clear()
        if self.reaper and self.reaper is not threading.current_thread():
            self.reaper.join(timeout=3)
