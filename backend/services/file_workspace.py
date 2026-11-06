"""Git-free file resources and strict patches, using the shared change journal."""
from pathlib import Path

from coding_git import safe_path, CodingConflict
from coding_store import CodingStore, fingerprint
from code_analysis_scope import check
from file_changes import state, identity, encoded, decoded, prepare, apply, recover
from lsp_positions import decode, encode
from text_patch import parse, update


class FileWorkspace:
    def __init__(self, store=None):
        self.store = store or CodingStore()

    def open(self, path, goal=None, mode=None):
        path = Path(path).expanduser().resolve(strict=True)
        check(path, write=mode != 'inspect')
        if not path.is_dir():
            raise ValueError('files 작업 공간은 폴더여야 합니다')
        row = {'id': 'files_' + fingerprint(str(path))[:32], 'path': str(path),
               'name': path.name, 'mode': mode or 'edit', 'root_identity': identity(path)}
        return self.store.save('file_workspace', row)

    def project(self, resource):
        row = self.store.get('file_workspace', resource)
        check(row['path'])
        if identity(row['path']) != row['root_identity']:
            raise CodingConflict('작업 공간이 교체됐습니다')
        return row

    def capabilities(self, row):
        return {'engine': 'files', 'read_projection': True, 'propose': True,
                'apply': row['mode'] != 'inspect', 'recover': True, 'close': True,
                'snapshot': False, 'save': False, 'restore': False,
                'coverage': 'tracked_changes'}

    def read(self, row, selector):
        path = safe_path(row['path'], selector.get('path', ''))
        if selector.get('view'):
            raise ValueError('files는 고정 snapshot 읽기를 지원하지 않습니다')
        if path.is_dir():
            return {'items': [{'path': p.relative_to(row['path']).as_posix(), 'directory': p.is_dir()}
                              for p in sorted(path.iterdir())[:1000] if not p.is_symlink()]}
        data = path.read_bytes()
        text, encoding = decode(data, path)
        return {'text': text, 'fingerprint': fingerprint(data), 'encoding': encoding}

    def propose(self, row, selector, replacement):
        if 'patch' not in selector:
            raise ValueError('files.propose에는 selector.patch가 필요합니다')
        return self.patch(row, selector['patch'], expected=selector.get('expected'),
                          request_id=selector.get('request_id'), format=selector.get('format', 'indiebiz-patch/1'))

    def patch(self, row, patch, *, expected=None, request_id=None, format='indiebiz-patch/1'):
        check(row['path'], write=True)
        expected = expected or {}
        signature = fingerprint({'patch': patch, 'expected': expected, 'format': format})
        with self.store.lock('workspace:' + row['id']):
            if request_id:
                for p in self.store.list('workspace_proposal'):
                    if p['project'] == row['id'] and (p.get('analysis') or {}).get('request_id') == request_id:
                        if p['analysis']['signature'] != signature:
                            raise CodingConflict('request_id를 다른 패치에 재사용했습니다')
                        return {'proposal': p['id'], 'state': p['state'], 'cached': True}
            edits = []
            def load(rel, require_hash=False):
                value = state(safe_path(row['path'], rel))
                actual = fingerprint(decoded(value['bytes'])) if value['bytes'] is not None else None
                if require_hash and rel not in expected:
                    raise ValueError('삭제·덮어쓸 이동에는 expected 해시가 필요합니다: ' + rel)
                if rel in expected and expected[rel] != actual:
                    raise CodingConflict('expected 해시 불일치: ' + rel)
                return value
            for entry in parse(patch, format):
                rel, op, body = entry['path'], entry['op'], entry['body']
                before = load(rel, op == 'delete')
                after = dict(before)
                if op == 'add':
                    if before['bytes'] is not None:
                        raise CodingConflict('생성 대상이 이미 있습니다: ' + rel)
                    if any(not line.startswith('+') for line in body):
                        raise ValueError('Add File의 본문은 +로 시작해야 합니다')
                    after['bytes'] = encoded(('\n'.join(line[1:] for line in body) + ('\n' if body else '')).encode())
                elif op == 'delete':
                    if body or before['bytes'] is None:
                        raise ValueError('잘못된 Delete File: ' + rel)
                    after['bytes'] = None
                else:
                    if before['bytes'] is None:
                        raise ValueError('수정 원본이 없습니다: ' + rel)
                    text, encoding = decode(decoded(before['bytes']), rel)
                    if '\0' in text:
                        raise ValueError('바이너리 패치는 지원하지 않습니다')
                    after['bytes'] = encoded(encode(update(text, body), encoding))
                if entry.get('move'):
                    dest = entry['move']; old_dest = load(dest)
                    if old_dest['bytes'] is not None:
                        load(dest, True)
                    edits.append({'path': dest, 'before': old_dest, 'after': after})
                    after = {**before, 'bytes': None}
                edits.append({'path': rel, 'before': before, 'after': after})
            return prepare(self.store, row, edits, metadata={'request_id': request_id, 'signature': signature})

    def apply(self, row, proposal, client=None):
        return apply(self.store, row, proposal)

    def recover(self, row):
        return recover(self.store, row)

    def close(self, row):
        return {'closed': True}

    def snapshot(self, row):
        raise ValueError('files의 복구는 대화 체크포인트 또는 변경 저널을 사용하세요')

    def save(self, *args):
        raise ValueError('files는 apply에서 저장됩니다. Git 기록은 kind:code를 사용하세요')

    versions = restore = save
