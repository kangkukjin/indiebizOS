"""LSP standard operations behind one provider-independent workspace selector."""
from lsp_positions import range_lsp, to_lsp
from lsp_transport import LspError
from code_analysis_results import Results

POSITION = {
    'definition': ('textDocument/definition', 'definitionProvider'),
    'declaration': ('textDocument/declaration', 'declarationProvider'),
    'type_definition': ('textDocument/typeDefinition', 'typeDefinitionProvider'),
    'implementation': ('textDocument/implementation', 'implementationProvider'),
    'references': ('textDocument/references', 'referencesProvider'),
    'hover': ('textDocument/hover', 'hoverProvider'),
    'signature': ('textDocument/signatureHelp', 'signatureHelpProvider'),
    'completion': ('textDocument/completion', 'completionProvider'),
}


class Operations:
    def __init__(self, session, store, row, view='saved', cancelled=None):
        self.s, self.store, self.row, self.view = session, store, row, view
        self.results = Results(session, store, row, view)
        self.cancelled = cancelled

    def call(self, method, params, capability=None):
        if capability and not self.s.supports(capability, method):
            raise LspError('UNSUPPORTED', '이 서버가 지원하지 않는 기능: ' + method)
        return self.s.client.request(method, params, cancelled=self.cancelled)

    def document(self, selector):
        target = selector.get('target') or {}
        path = selector.get('path') or target.get('path')
        if not path:
            raise ValueError('selector.path 또는 앞선 결과의 target이 필요합니다')
        first_open = (self.s.root / path).as_uri() not in self.s.documents
        doc = self.s.document(path)
        if first_open and self.s.spec.get('driver') in ('pyright', 'typescript'):
            _, _, status = self.s.diagnostic(path, wait=10)
            if status == 'pending':
                raise LspError('INITIALIZING', '프로젝트 분석을 준비하고 있습니다. 진단 수신 후 다시 조회하세요')
        if target.get('document_hash') and target['document_hash'] != doc['hash']:
            raise LspError('STALE_RESULT', '위치의 원문 지문이 바뀌었습니다')
        return doc

    def position(self, selector, doc):
        point = (selector.get('target') or {}).get('range', {}).get('start') or selector
        return {'textDocument': {'uri': doc['uri']}, 'position': to_lsp(doc['text'], point, self.s.encoding)}

    def read(self, selector):
        op = selector['analysis']
        if op == 'batch':
            requests = selector.get('requests', [])
            if not isinstance(requests, list) or len(requests) > 50:
                raise ValueError('batch.requests는 50개 이하의 읽기입니다')
            items = []
            for request in requests:
                if request.get('analysis') == 'batch':
                    raise ValueError('batch 중첩은 지원하지 않습니다')
                try:
                    items.append({'success': True, **self.read(request)})
                except (ValueError, LspError, OSError) as exc:
                    items.append({'success': False, 'error': str(exc), 'code': getattr(exc, 'code', 'INVALID_REQUEST')})
            return {'items': items}
        if op == 'symbols':
            if selector.get('ref'):
                raw = self.results.recall(selector['ref'], 'symbol')['value']
                value = self.call('workspaceSymbol/resolve', raw)
                return {'items': self.results.candidates('symbol', [value])}
            if selector.get('path'):
                doc = self.document(selector)
                value = self.call('textDocument/documentSymbol', {'textDocument': {'uri': doc['uri']}}, 'documentSymbolProvider')
                return {'items': self.results.normalize(value or [], doc['uri'])}
            value = self.call('workspace/symbol', {'query': selector.get('query', '')}, 'workspaceSymbolProvider')
            return {'items': self.results.candidates('symbol', value)}
        if op in ('calls', 'types'):
            prefix = 'callHierarchy' if op == 'calls' else 'typeHierarchy'
            provider = prefix + 'Provider'
            direction = selector.get('direction', 'prepare')
            if direction == 'prepare':
                doc = self.document(selector)
                values = self.call('textDocument/prepare' + prefix[0].upper() + prefix[1:], self.position(selector, doc), provider)
            else:
                choices = {'calls': {'incoming': 'incomingCalls', 'outgoing': 'outgoingCalls'},
                           'types': {'supertypes': 'supertypes', 'subtypes': 'subtypes'}}
                if direction not in choices[op]:
                    raise ValueError('잘못된 계층 방향')
                raw = self.results.recall(selector['ref'], op)['value']
                values = self.call(prefix + '/' + choices[op][direction], {'item': raw}, provider)
            items = self.results.candidates(op, values)
            if direction != 'prepare' and op == 'calls':
                for item, raw in zip(items, values or []):
                    key = 'from' if direction == 'incoming' else 'to'
                    item[key]['ref'] = self.results.remember(op, raw[key])
            return {'items': items}
        if op == 'diagnostics':
            return self.diagnostics(selector)
        if op == 'actions':
            if selector.get('ref'):
                previous = self.results.recall(selector['ref'], 'action')
                resolved = self.call('codeAction/resolve', previous['value'])
                return {'items': self.results.candidates('action', [resolved], self.s.documents.get(previous['doc']))}
            doc = self.document(selector)
            span = range_lsp(doc['text'], selector['range'], self.s.encoding)
            diagnostics = self.s.diagnostics.get(doc['uri'], {}).get('diagnostics', [])
            values = self.call('textDocument/codeAction', {'textDocument': {'uri': doc['uri']}, 'range': span,
                'context': {'diagnostics': diagnostics, **({'only': selector['only']} if selector.get('only') else {})}}, 'codeActionProvider')
            return {'items': self.results.candidates('action', values, doc)}
        if op == 'completion' and selector.get('ref'):
            previous = self.results.recall(selector['ref'], 'completion')
            value = self.call('completionItem/resolve', previous['value'])
            return {'items': self.results.candidates('completion', [value], self.s.documents.get(previous['doc']))}
        if op in POSITION:
            doc = self.document(selector)
            params = self.position(selector, doc)
            if op == 'references':
                params['context'] = {'includeDeclaration': bool(selector.get('include_declaration', True))}
            value = self.call(*[POSITION[op][0], params, POSITION[op][1]])
            if op == 'completion':
                values = value.get('items', []) if isinstance(value, dict) else value or []
                for candidate in values:
                    if not candidate.get('textEdit'):
                        public = selector.get('target', {}).get('range', {}).get('start') or selector
                        line, column = public['line'], public['column']
                        prefix = doc['text'].split('\n')[line - 1][:column - 1]
                        start = len(prefix)
                        while start and (prefix[start - 1].isalnum() or prefix[start - 1] in '_$'):
                            start -= 1
                        candidate['textEdit'] = {'range': {'start': to_lsp(doc['text'], {'line': line, 'column': start + 1}, self.s.encoding),
                                                           'end': params['position']},
                                                 'newText': candidate.get('insertText', candidate['label'])}
                # Not advertising itemDefaults avoids positional defaults that are invisible to a candidate.
                return {'items': self.results.candidates('completion', values, doc), 'incomplete': bool(isinstance(value, dict) and value.get('isIncomplete'))}
            values = value if isinstance(value, list) else [value] if value is not None else []
            return {'items': self.results.normalize(values, doc['uri'])}
        raise ValueError('지원하는 analysis: symbols/definition/declaration/type_definition/implementation/references/hover/signature/calls/types/diagnostics/completion/actions/batch')

    def diagnostics(self, selector):
        if selector.get('scope') == 'workspace' and isinstance(self.s.capabilities.get('diagnosticProvider'), dict) and self.s.capabilities['diagnosticProvider'].get('workspaceDiagnostics'):
            value = self.call('workspace/diagnostic', {'previousResultIds': []})
            items = []
            for report in value.get('items', []):
                uri = report['uri']
                for diag in report.get('items', []):
                    items.append(self.results.normalize(diag, uri))
            return {'items': items, 'diagnostics': {'scope': 'workspace', 'status': 'received', 'complete': True, 'reports': value.get('items', [])}}
        paths = selector.get('paths') or ([selector['path']] if selector.get('path') else [d['path'] for d in self.s.documents.values()])
        items, states = [], []
        for path in paths:
            doc, value, status = self.s.diagnostic(path, selector.get('wait', 0))
            items.extend(self.results.normalize(value.get('diagnostics', []), doc['uri']))
            states.append({'path': path, 'status': status, 'document_version': doc['version'],
                           'diagnostic_version': value.get('version'), 'source': value.get('source'),
                           'result_id': value.get('resultId'), 'related_documents': value.get('relatedDocuments')})
        return {'items': items, 'diagnostics': {'scope': selector.get('scope', 'files'), 'files': states,
                'complete': bool(states) and selector.get('scope') != 'workspace' and all(s['status'] == 'received' for s in states),
                'note': 'workspace 전체 완료는 서버의 workspace pull 진단이 있을 때만 확정합니다'}}

    def propose(self, selector):
        op = selector['analysis']
        if op == 'rename':
            doc = self.document(selector)
            params = self.position(selector, doc)
            params['newName'] = selector['new_name']
            change = self.call('textDocument/rename', params, 'renameProvider')
        elif op == 'format':
            doc = self.document(selector)
            params = {'textDocument': {'uri': doc['uri']}, 'options': selector.get('options', {'tabSize': 4, 'insertSpaces': True})}
            if selector.get('range'):
                params['range'] = range_lsp(doc['text'], selector['range'], self.s.encoding)
                edits = self.call('textDocument/rangeFormatting', params, 'documentRangeFormattingProvider')
            else:
                edits = self.call('textDocument/formatting', params, 'documentFormattingProvider')
            change = {'changes': {doc['uri']: edits or []}}
        elif op in ('code_action', 'completion'):
            kind = 'action' if op == 'code_action' else op
            candidate = self.results.recall(selector['ref'], kind)
            value = candidate['value']
            provider = self.s.capabilities.get('codeActionProvider' if kind == 'action' else 'completionProvider')
            if isinstance(provider, dict) and provider.get('resolveProvider'):
                value = self.call('codeAction/resolve' if kind == 'action' else 'completionItem/resolve', value)
            if value.get('disabled'):
                raise LspError('ACTION_DISABLED', value['disabled'].get('reason', '비활성 액션'))
            if kind == 'action':
                change = value.get('edit')
                command = value.get('command')
                if command:
                    from code_analysis_drivers import command_edit
                    command = value if isinstance(command, str) else command
                    additional = command_edit(self.s, command)
                    if change:
                        raise LspError('COMMAND_UNSUPPORTED', '편집과 별도 명령이 함께 있는 액션은 순서 계약이 필요합니다')
                    change = additional
            else:
                if value.get('command'):
                    raise LspError('COMMAND_UNSUPPORTED', '추가 명령이 필요한 완성 후보입니다')
                if value.get('insertTextFormat', 1) != 1:
                    raise LspError('SNIPPET_UNSUPPORTED', '서버가 광고하지 않은 snippet을 반환했습니다')
                edit = value.get('textEdit')
                if not edit:
                    raise LspError('EDIT_UNAVAILABLE', '후보에 적용 위치가 없습니다. 위치를 다시 조회하세요')
                change = {'changes': {candidate['doc']: [edit, *value.get('additionalTextEdits', [])]}}
        else:
            raise ValueError('propose.analysis는 rename/code_action/completion/format입니다')
        from code_analysis_changes import workspace_edit
        return workspace_edit(self.store, self.row, self.s, change, selector)
