"""A persistent LSP document view with file observation and honest diagnostic versions."""
import copy
import threading
import time
from pathlib import Path

from coding_git import safe_path
from coding_store import identifier
from code_analysis_drivers import environment, launch
from code_analysis_process import spawn_factory
from lsp_positions import decode, digest
from lsp_transport import Client, LspError


class Session:
    def __init__(self, row, name, spec, runtime, *, confined=False, overlays=None, project_root=None):
        self.root = Path(row['path']).resolve()
        self.project_root = Path(project_root or self.root)
        self.name, self.spec = name, spec
        self.generation = identifier('server')
        self.documents, self.diagnostics, self.registrations, self.progress = {}, {}, {}, {}
        self.overlays = overlays if overlays is not None else {}
        self.lock, self.diag_lock = threading.RLock(), threading.Condition()
        self.stop = threading.Event()
        self.dirty, self.watch_error = False, None
        self.last_used, self.active = time.monotonic(), 0
        self.settings, initialization, self.environment = environment(self.project_root, spec)
        command, env = launch(spec, runtime)
        self.client = Client(command, self.root, env, spawn=spawn_factory(runtime, confined=confined),
                             on_request=self.on_request, on_notice=self.on_notice)
        try:
            initialized = self.client.request('initialize', {
                'processId': __import__('os').getpid(), 'rootUri': self.project_root.as_uri(),
                'workspaceFolders': [{'uri': self.project_root.as_uri(), 'name': self.project_root.name}],
                'clientInfo': {'name': 'IndieBiz OS', 'version': '1'},
                'initializationOptions': initialization,
                'capabilities': {
                    'general': {'positionEncodings': ['utf-8', 'utf-16', 'utf-32']},
                    'workspace': {'configuration': True, 'workspaceFolders': True, 'applyEdit': False,
                                  'didChangeWatchedFiles': {'dynamicRegistration': True},
                                  'workspaceEdit': {'documentChanges': True, 'resourceOperations': ['create', 'rename', 'delete'],
                                                    'failureHandling': 'abort'},
                                  'diagnostics': {'refreshSupport': True}},
                    'textDocument': {'synchronization': {'didSave': True, 'dynamicRegistration': True},
                        'publishDiagnostics': {'versionSupport': True, 'relatedInformation': True},
                        'definition': {'linkSupport': True}, 'declaration': {'linkSupport': True},
                        'typeDefinition': {'linkSupport': True}, 'implementation': {'linkSupport': True},
                        'documentSymbol': {'hierarchicalDocumentSymbolSupport': True},
                        'completion': {'completionItem': {'snippetSupport': False, 'insertReplaceSupport': True,
                            'resolveSupport': {'properties': ['documentation', 'detail', 'additionalTextEdits', 'textEdit']}}},
                        'codeAction': {'dataSupport': True, 'resolveSupport': {'properties': ['edit']},
                            'codeActionLiteralSupport': {'codeActionKind': {'valueSet': ['', 'quickfix', 'refactor', 'source']}}},
                        'diagnostic': {'relatedDocumentSupport': True}},
                    'window': {'workDoneProgress': True}}}, timeout=40)
            self.capabilities = initialized.get('capabilities', {})
            self.server_info = initialized.get('serverInfo', {})
            self.encoding = self.capabilities.get('positionEncoding', 'utf-16')
            if self.encoding not in ('utf-8', 'utf-16', 'utf-32'):
                raise LspError('POSITION_ENCODING_UNSUPPORTED', self.encoding)
            self.client.notify('initialized')
            self.client.notify('workspace/didChangeConfiguration', {'settings': self.settings})
            self.watcher = threading.Thread(target=self.watch, daemon=True, name='code-analysis-watch')  # cc-ok: stop event and close/join own observer
            from runtime_work import service_scope
            with service_scope(own_processes=True):
                self.watcher.start()
        except BaseException:
            self.client.close(graceful=False)
            raise

    def on_request(self, method, params):
        if method == 'workspace/configuration':
            result = []
            for item in params.get('items', []):
                from common.field_path import walk_path, MISSING
                value = walk_path(self.settings, item.get('section') or '')
                if value is MISSING:
                    value = None
                result.append(value)
            return result
        if method == 'workspace/workspaceFolders':
            return [{'uri': self.project_root.as_uri(), 'name': self.project_root.name}]
        if method == 'workspace/applyEdit':
            return {'applied': False, 'failureReason': '변경은 workspace.propose/apply 원장을 거쳐야 합니다'}
        if method == 'client/registerCapability':
            for reg in params.get('registrations', []):
                self.registrations[reg['id']] = reg
            return None
        if method == 'client/unregisterCapability':
            for reg in params.get('unregisterations', params.get('unregistrations', [])):
                self.registrations.pop(reg['id'], None)
            return None
        if method == 'window/workDoneProgress/create':
            self.progress[params['token']] = {'kind': 'begin'}
            return None
        if method == 'workspace/diagnostic/refresh':
            with self.diag_lock:
                for value in self.diagnostics.values():
                    value['refresh_pending'] = True
            return None
        if method == 'window/showMessageRequest':
            return None
        raise LspError(-32601, '지원하지 않는 서버 요청: ' + method)

    def on_notice(self, method, params):
        if method == 'textDocument/publishDiagnostics':
            with self.diag_lock:
                self.diagnostics[params['uri']] = {**params, 'received_at': time.time(), 'source': 'push'}
                self.diag_lock.notify_all()
        elif method == '$/progress':
            self.progress[params['token']] = params['value']

    def supports(self, capability, method=None):
        value = self.capabilities.get(capability)
        return value is not None and value is not False or any(r['method'] == method for r in self.registrations.values())

    def document(self, relative):
        path = safe_path(self.root, relative)
        data = self.overlays[relative].encode('utf-8') if relative in self.overlays else path.read_bytes()
        text, encoding = decode(data, path)
        uri, hashed = path.as_uri(), digest(data)
        previous = self.documents.get(uri)
        if previous and previous['hash'] == hashed:
            return previous
        doc = {'uri': uri, 'path': relative, 'text': text, 'encoding': encoding, 'hash': hashed,
               'version': previous['version'] + 1 if previous else 1, 'observed_at': time.time()}
        language = self.spec['extensions'].get(path.suffix)
        if not language:
            raise LspError('LANGUAGE_UNSUPPORTED', '선택한 서버가 이 파일을 처리하지 않습니다')
        sync = self.capabilities.get('textDocumentSync', 0)
        sync_kind = sync.get('change', 0) if isinstance(sync, dict) else sync
        if previous and sync_kind:
            # An incremental server also accepts a single full-document replacement range.
            changes = {'text': text}
            if sync_kind == 2:
                from lsp_positions import to_lsp
                parts = previous['text'].split('\n')
                changes['range'] = {'start': {'line': 0, 'character': 0}, 'end': to_lsp(previous['text'],
                    {'line': len(parts), 'column': len(parts[-1].removesuffix('\r')) + 1}, self.encoding)}
            self.client.notify('textDocument/didChange', {'textDocument': {'uri': uri, 'version': doc['version']}, 'contentChanges': [changes]})
        else:
            if previous:
                self.client.notify('textDocument/didClose', {'textDocument': {'uri': uri}})
            self.client.notify('textDocument/didOpen', {'textDocument': {'uri': uri, 'languageId': language, 'version': doc['version'], 'text': text}})
        self.documents[uri] = doc
        if relative not in self.overlays and isinstance(sync, dict) and sync.get('save') is not None and sync.get('save') is not False:
            save = {'textDocument': {'uri': uri}}
            if isinstance(sync['save'], dict) and sync['save'].get('includeText'):
                save['text'] = text
            self.client.notify('textDocument/didSave', save)
        return doc

    def synchronize(self):
        for uri, doc in list(self.documents.items()):
            if (self.root / doc['path']).is_file() or doc['path'] in self.overlays:
                self.document(doc['path'])
            else:
                self.client.notify('textDocument/didClose', {'textDocument': {'uri': uri}})
                self.documents.pop(uri, None)
                self.diagnostics.pop(uri, None)
        for relative in self.overlays:
            if Path(relative).suffix in self.spec['extensions']:
                self.document(relative)

    def watch(self):
        try:
            from watchfiles import watch
            def include(change, path):
                parts = Path(path).relative_to(self.root).parts
                return not any(p in ('node_modules', '.venv', '__pycache__', '.git', '_backups') for p in parts)
            for batch in watch(self.root, stop_event=self.stop, watch_filter=include, debounce=150, step=50):
                with self.lock:
                    if self.stop.is_set():
                        break
                    self.dirty = True
                    self.client.notify('workspace/didChangeWatchedFiles', {'changes': [
                        {'uri': Path(path).as_uri(), 'type': {1: 1, 2: 2, 3: 3}[int(kind)]} for kind, path in batch]})
                    self.synchronize()
        except Exception as exc:
            self.watch_error = str(exc)
            self.dirty = True

    def diagnostic(self, relative, wait=0):
        doc = self.document(relative)
        uri = doc['uri']
        if self.supports('diagnosticProvider', 'textDocument/diagnostic'):
            prior = self.diagnostics.get(uri, {})
            result = self.client.request('textDocument/diagnostic', {'textDocument': {'uri': uri},
                **({'previousResultId': prior['resultId']} if prior.get('resultId') else {})})
            if result['kind'] == 'unchanged':
                if not prior:
                    raise LspError('DIAGNOSTICS_UNKNOWN', '이전 진단 없는 unchanged 응답')
                result = {**prior, 'resultId': result.get('resultId')}
            else:
                result['diagnostics'] = result.get('items', [])
            result.update(version=doc['version'], source='pull', received_at=time.time())
            self.diagnostics[uri] = result
        with self.diag_lock:
            deadline = time.monotonic() + min(max(float(wait), 0), 10)
            def current_report():
                value = self.diagnostics.get(uri)
                return bool(value is not None and not value.get('refresh_pending') and (
                    value.get('version') == doc['version'] or value.get('version') is None
                    and value.get('received_at', 0) >= doc.get('observed_at', 0)))
            while not current_report() and time.monotonic() < deadline:
                self.diag_lock.wait(timeout=min(.1, max(.001, deadline - time.monotonic())))
            value = copy.deepcopy(self.diagnostics.get(uri))
        status = 'pending' if value is None else ('stale' if value.get('received_at', 0) < doc.get('observed_at', 0) else
                 'version_unconfirmed' if value.get('version') is None else
                 'received' if value['version'] == doc['version'] and not value.get('refresh_pending') else 'stale')
        return doc, value or {}, status

    def close(self):
        self.stop.set()
        self.client.close()
        if getattr(self, 'watcher', None) and self.watcher is not threading.current_thread():
            self.watcher.join(timeout=3)
