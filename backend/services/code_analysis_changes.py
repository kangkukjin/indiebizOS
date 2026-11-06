"""LSP WorkspaceEdit conversion; durable application belongs to file_changes."""
from coding_git import CodingConflict, safe_path
from coding_store import fingerprint
from lsp_positions import decode, encode, edit_text, uri_path
from file_changes import encoded, decoded, state, identity, prepare, recover, _replace
import file_changes


def apply(store, row, proposal, *, recover=False):
    return file_changes.apply(store, row, proposal, recover=recover, writer=_replace)


def workspace_edit(store, row, session, change, selector):
    if not isinstance(change, dict):
        raise ValueError('서버가 WorkspaceEdit를 반환하지 않았습니다')
    root = session.root
    originals, virtual = {}, {}

    def relative(uri):
        path = uri_path(uri)
        if not path.is_relative_to(root):
            raise PermissionError('의존성·작업 공간 밖 파일은 편집할 수 없습니다')
        rel = path.relative_to(root).as_posix()
        safe_path(root, rel)
        return rel

    def load(rel):
        if rel not in virtual:
            originals[rel] = state(safe_path(root, rel))
            doc = session.documents.get((root / rel).as_uri())
            if doc and doc['hash'] != (fingerprint(decoded(originals[rel]['bytes'])) if originals[rel]['bytes'] is not None else None):
                raise CodingConflict('서버가 읽은 원본이 변경됐습니다: ' + rel)
            virtual[rel] = dict(originals[rel])
        return virtual[rel]

    def text_edit(uri, edits, version=None):
        rel = relative(uri)
        current = load(rel)
        if current['bytes'] is None:
            raise ValueError('없는 파일의 TextEdit: ' + rel)
        doc = session.documents.get(uri)
        if version is not None and (not doc or doc['version'] != version):
            raise CodingConflict('서버가 반환한 편집의 문서 판본이 다릅니다')
        text, encoding = decode(decoded(current['bytes']), rel)
        current['bytes'] = encoded(encode(edit_text(text, edits, session.encoding), encoding))

    if change.get('changes') and change.get('documentChanges'):
        raise ValueError('changes와 documentChanges를 동시에 적용하지 않습니다')
    for uri, edits in change.get('changes', {}).items():
        text_edit(uri, edits)
    for item in change.get('documentChanges', []):
        if 'textDocument' in item:
            document = item['textDocument']
            text_edit(document['uri'], item['edits'], document.get('version'))
            continue
        kind, options = item.get('kind'), item.get('options', {})
        if kind == 'create':
            rel = relative(item['uri']); current = load(rel)
            if current['bytes'] is not None and not options.get('overwrite'):
                if options.get('ignoreIfExists'):
                    continue
                raise CodingConflict('생성할 파일이 이미 있습니다: ' + rel)
            current['bytes'] = encoded(b'')
        elif kind == 'rename':
            old, new = relative(item['oldUri']), relative(item['newUri'])
            source, dest = load(old), load(new)
            if source['bytes'] is None:
                raise CodingConflict('개명 원본이 없습니다: ' + old)
            if dest['bytes'] is not None and not options.get('overwrite'):
                if options.get('ignoreIfExists'):
                    continue
                raise CodingConflict('개명 목적지가 이미 있습니다: ' + new)
            virtual[new] = dict(source)
            source['bytes'] = None
        elif kind == 'delete':
            rel = relative(item['uri']); current = load(rel)
            if current['bytes'] is None and not options.get('ignoreIfNotExists'):
                raise CodingConflict('삭제 대상이 없습니다: ' + rel)
            current['bytes'] = None
        else:
            raise ValueError('지원하지 않는 파일 작업: ' + str(kind))
    edits = [{'path': rel, 'before': originals[rel], 'after': value} for rel, value in virtual.items() if value != originals[rel]]
    return prepare(store, row, edits, selector=selector,
                   metadata={'generation': session.generation, 'encoding': session.encoding,
                             'annotations': change.get('changeAnnotations', {})})
