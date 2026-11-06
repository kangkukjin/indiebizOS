"""Normalize LSP evidence into workspace items without losing original server payloads."""
import copy
from pathlib import Path

from coding_store import identifier
from lsp_positions import decode, digest, range_public, uri_path
from lsp_transport import LspError


class Results:
    def __init__(self, session, store, row, view='saved'):
        self.session, self.store, self.row, self.view = session, store, row, view

    def source(self, uri):
        doc = self.session.documents.get(uri)
        if doc:
            return doc
        path = uri_path(uri)
        data = path.read_bytes()
        text, encoding = decode(data, path)
        return {'text': text, 'hash': digest(data), 'version': None, 'encoding': encoding}

    def location(self, uri, span):
        path = uri_path(uri)
        source = self.source(uri)
        if path.is_relative_to(self.session.root):
            path = Path(self.row['path']) / path.relative_to(self.session.root)
            uri = path.as_uri()
        return {'uri': uri, 'path': path.relative_to(self.row['path']).as_posix() if path.is_relative_to(self.row['path']) else str(path),
                'range': range_public(source['text'], span, self.session.encoding),
                'document_hash': source['hash'], 'document_version': source['version'], 'view': self.view,
                'position_encoding': 'unicode_codepoint_1based', 'external': not path.is_relative_to(self.row['path'])}

    def normalize(self, value, uri=None):
        if isinstance(value, list):
            return [self.normalize(v, uri) for v in value]
        if not isinstance(value, dict):
            return value
        out = copy.deepcopy(value)
        target_uri = value.get('uri') or value.get('targetUri') or uri
        if 'targetUri' in value:
            out.update(self.location(value['targetUri'], value.get('targetSelectionRange') or value['targetRange']))
            out['target'] = {k: out[k] for k in ('uri', 'path', 'range', 'document_hash', 'document_version', 'view')}
        elif 'location' in value and isinstance(value['location'], dict) and 'range' in value['location']:
            loc = value['location']
            out.update(self.location(loc['uri'], loc['range']))
            out['target'] = {k: out[k] for k in ('uri', 'path', 'range', 'document_hash', 'document_version', 'view')}
        elif target_uri and 'range' in value:
            out.update(self.location(target_uri, value.get('selectionRange') or value['range']))
            out['target'] = {k: out[k] for k in ('uri', 'path', 'range', 'document_hash', 'document_version', 'view')}
        if 'children' in value:
            out['children'] = self.normalize(value['children'], target_uri)
        if 'relatedInformation' in value:
            out['relatedInformation'] = self.normalize(value['relatedInformation'])
        for key in ('from', 'to'):
            if isinstance(value.get(key), dict):
                out[key] = self.normalize(value[key])
        return out

    def remember(self, kind, value, doc=None):
        ref = identifier('analysis')
        documents = {uri: d['hash'] for uri, d in self.session.documents.items()}
        def collect(item):
            if isinstance(item, list):
                for child in item: collect(child)
            elif isinstance(item, dict):
                for key, child in item.items():
                    if key in ('uri', 'targetUri', 'oldUri', 'newUri') and isinstance(child, str) and child.startswith('file:'):
                        path = uri_path(child)
                        if path.is_file(): documents[child] = self.source(child)['hash']
                    elif isinstance(key, str) and key.startswith('file:'):
                        path = uri_path(key)
                        if path.is_file(): documents[key] = self.source(key)['hash']
                    collect(child)
        collect(value)
        self.store.save('workspace_analysis', {'id': ref, 'project': self.row['id'], 'view': self.view,
            'generation': self.session.generation, 'server': self.session.name, 'kind': kind, 'value': value,
            'documents': documents, 'doc': doc})
        return ref

    def recall(self, ref, kind=None):
        value = self.store.get('workspace_analysis', ref)
        if value['project'] != self.row['id'] or value['view'] != self.view:
            raise PermissionError('다른 작업 공간·뷰의 분석 참조입니다')
        if value['generation'] != self.session.generation:
            raise LspError('STALE_RESULT', '서버 세대가 바뀌었습니다. 후보를 다시 조회하세요')
        for uri, hashed in value['documents'].items():
            if self.source(uri)['hash'] != hashed:
                raise LspError('STALE_RESULT', '후보가 참조한 문서가 변경됐습니다')
        if kind and value['kind'] != kind:
            raise ValueError('후보 종류가 다릅니다')
        return value

    def candidates(self, kind, values, doc=None):
        result = []
        for raw in values or []:
            item = self.normalize(raw, doc and doc['uri'])
            item['ref'] = self.remember(kind, raw, doc and doc['uri'])
            result.append(item)
        return result
