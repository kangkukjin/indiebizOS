"""DOCX 문단 조회·선택 교체. ZIP 파트 보존, Word 변경 추적과 주석."""
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import re

from lxml import etree

_spec = importlib.util.spec_from_file_location('essentials_ooxml', Path(__file__).with_name('essentials_ooxml.py'))
office = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(office)
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = {'w': W}
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'


def tag(name):
    return '{' + W + '}' + name


def _parts(parts):
    return [n for n in parts if n == 'word/document.xml' or re.fullmatch(r'word/(header|footer)\d+\.xml', n)]


def _text(p):
    # 현재 표시되는 텍스트. 삭제 기록·중첩 텍스트상자는 본문 문자열에 섞지 않는다.
    return ''.join(t.text or '' for t in p.xpath('.//w:t[not(ancestor::w:del)]', namespaces=NS)
                   if next(t.iterancestors(tag('p')), None) is p)


def _editable(p):
    if any(a.tag in {tag('sdt'), tag('ins'), tag('del')} for a in p.iterancestors()):
        return False
    for node in p:
        if node.tag == tag('pPr'):
            continue
        if node.tag != tag('r') or any(c.tag not in {tag('rPr'), tag('t')} for c in node):
            return False
    return True


def _rows(parts):
    for part in _parts(parts):
        root = office.xml(parts[part])
        for i, p in enumerate(root.iter(tag('p'))):
            cell = next(p.iterancestors(tag('tc')), None)
            yield part, root, p, {'block_id': f'{part}#p{i}', 'part': part, 'text': _text(p),
                                 'in_table': cell is not None, 'editable': _editable(p)}


def op_inspect(params):
    path, digest, parts, _, _ = office.load(params, {'.docx'})
    if 'word/document.xml' not in parts:
        raise ValueError('DOCX 본문이 없습니다.')
    limit = params.get('limit', 200)
    if type(limit) is not int or not 1 <= limit <= 2000:
        raise ValueError('limit은 1~2000 정수입니다.')
    offset = params.get('offset', 0)
    if type(offset) is not int or offset < 0:
        raise ValueError('offset은 0 이상의 정수입니다.')
    rows = [r for _, _, _, r in _rows(parts)]
    return {'success': True, 'path': str(path), 'sha256': digest,
            'items': rows[offset:offset + limit], 'total': len(rows),
            'truncated': offset + limit < len(rows), 'offset': offset,
            'note': 'editable=false는 필드·링크·기존 변경/주석·복합 요소가 있어 선택 교체를 지원하지 않는 문단입니다.'}


def _run(template, text, deleted=False):
    run = etree.Element(tag('r'), attrib=dict(template.attrib))
    prop = template.find(tag('rPr'))
    if prop is not None:
        run.append(deepcopy(prop))
    t = etree.SubElement(run, tag('delText' if deleted else 't'))
    t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    t.text = text
    return run


def _replace(p, old, new, tracked, author, now, next_id):
    text = _text(p)
    start, stop = text.index(old), text.index(old) + len(old)
    position, inserted = 0, False
    insertion_node = None
    for run in list(p):
        if run.tag != tag('r'):
            continue
        value = ''.join(t.text or '' for t in run.findall(tag('t')))
        end = position + len(value)
        if position >= stop or end <= start:
            position = end
            continue
        lo, hi = max(0, start - position), min(len(value), stop - position)
        nodes = []
        if lo:
            nodes.append(_run(run, value[:lo]))
        if tracked:
            deleted = etree.Element(tag('del'), {tag('id'): str(next(next_id)), tag('author'): author, tag('date'): now})
            deleted.append(_run(run, value[lo:hi], deleted=True))
            nodes.append(deleted)
        if not inserted:
            if new:
                insertion_node = _run(run, new)
                if tracked:
                    wrapper = etree.Element(tag('ins'), {tag('id'): str(next(next_id)), tag('author'): author, tag('date'): now})
                    wrapper.append(insertion_node)
                    insertion_node = wrapper
                nodes.append(insertion_node)
            inserted = True
        if hi < len(value):
            nodes.append(_run(run, value[hi:]))
        index = p.index(run)
        p.remove(run)
        for node in nodes:
            p.insert(index, node)
            index += 1
        position = end
    return insertion_node


def _comments(parts):
    rel_name = 'word/_rels/document.xml.rels'
    rels = office.xml(parts[rel_name]) if rel_name in parts else etree.Element('{' + REL + '}Relationships', nsmap={None: REL})
    ctype = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments'
    matches = [e for e in rels if e.get('Type') == ctype]
    if matches and (len(matches) != 1 or matches[0].get('Target') != 'comments.xml'):
        raise ValueError('표준 comments.xml 외의 주석 파트는 이번 편집에서 지원하지 않습니다.')
    if not matches:
        used = {e.get('Id') for e in rels}
        i = 1
        while f'rId{i}' in used:
            i += 1
        etree.SubElement(rels, '{' + REL + '}Relationship', Id=f'rId{i}', Type=ctype, Target='comments.xml')
    comments = office.xml(parts['word/comments.xml']) if 'word/comments.xml' in parts else etree.Element(tag('comments'), nsmap={'w': W})
    content = office.xml(parts['[Content_Types].xml'])
    if not any(e.get('PartName') == '/word/comments.xml' for e in content):
        etree.SubElement(content, '{' + CT + '}Override', PartName='/word/comments.xml',
                         ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml')
    parts[rel_name] = office.encoded(rels)
    parts['[Content_Types].xml'] = office.encoded(content)
    return comments


def op_edit(params):
    path, digest, parts, infos, zip_comment = office.load(params, {'.docx'})
    if params.get('expected_sha256') != digest:
        raise ValueError('inspect의 sha256을 expected_sha256으로 지정하세요. 원본 변경 시 다시 조회해야 합니다.')
    edits = params.get('edits')
    if not isinstance(edits, list) or not 1 <= len(edits) <= 200:
        raise ValueError('edits는 1~200개 교체 객체의 배열입니다.')
    tracked = params.get('track_changes', True)
    if type(tracked) is not bool:
        raise ValueError('track_changes는 boolean입니다.')
    author = params.get('author', 'IndieBizOS')
    if not isinstance(author, str) or not author.strip() or len(author) > 100:
        raise ValueError('author는 1~100자 문자열입니다.')
    dest = office.output_path(params, path, '_edited')
    # 한 파트의 문단들은 반드시 같은 XML 트리에서 선택한다.
    roots = {part: office.xml(parts[part]) for part in _parts(parts)}
    blocks = {f'{part}#p{i}': (part, p) for part, root in roots.items()
              for i, p in enumerate(root.iter(tag('p')))}
    planned, seen = [], set()
    for edit in edits:
        if not isinstance(edit, dict) or set(edit) - {'block_id', 'old_string', 'new_string', 'comment'}:
            raise ValueError('교체 객체의 키: block_id, old_string, new_string, comment(선택).')
        ident = edit.get('block_id')
        if not isinstance(ident, str) or ident not in blocks or ident in seen:
            raise ValueError('유효한 block_id를 문단당 한 번만 지정하세요.')
        seen.add(ident)
        part, p = blocks[ident]
        old, new = edit.get('old_string'), edit.get('new_string')
        if not isinstance(old, str) or not old or not isinstance(new, str):
            raise ValueError('비어있지 않은 old_string과 문자열 new_string이 필요합니다.')
        if any(c in old + new for c in '\r\n\t') or old == new:
            raise ValueError('한 문단 안의 서로 다른 일반 텍스트만 교체합니다(줄바꿈/탭 제외).')
        if not _editable(p) or _text(p).count(old) != 1:
            raise ValueError(f'{ident}: 지원하지 않는 복합 문단이거나 old_string이 정확히 한 번 일치하지 않습니다.')
        comment = edit.get('comment')
        if comment is not None and (not isinstance(comment, str) or not comment.strip() or part != 'word/document.xml' or not new):
            raise ValueError('comment는 본문/표의 비어있지 않은 교체 텍스트에 붙이는 문자열입니다.')
        planned.append((edit, part, p))
    import itertools
    ids = [int(e.get(tag('id'))) for n, b in parts.items() if n.startswith('word/') and n.endswith('.xml')
           for e in office.xml(b).iter() if (e.get(tag('id')) or '').isdigit()]
    next_id = itertools.count(max(ids, default=0) + 1)
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    comments = _comments(parts) if any(e.get('comment') is not None for e, _, _ in planned) else None
    changed, changes = set(), []
    for edit, part, p in planned:
        node = _replace(p, edit['old_string'], edit['new_string'], tracked, author, now, next_id)
        if edit.get('comment') is not None:
            cid = str(next(next_id))
            node.addprevious(etree.Element(tag('commentRangeStart'), {tag('id'): cid}))
            end = etree.Element(tag('commentRangeEnd'), {tag('id'): cid})
            node.addnext(end)
            ref = etree.Element(tag('r'))
            etree.SubElement(ref, tag('commentReference'), {tag('id'): cid})
            end.addnext(ref)
            comment = etree.SubElement(comments, tag('comment'), {tag('id'): cid, tag('author'): author, tag('date'): now})
            cp = etree.SubElement(comment, tag('p'))
            cp.append(_run(etree.Element(tag('r')), edit['comment']))
        changed.add(part)
        changes.append({'block_id': edit['block_id'], 'before': edit['old_string'], 'after': edit['new_string'],
                        'tracked': tracked, 'comment': edit.get('comment')})
    for part in changed:
        parts[part] = office.encoded(roots[part])
    if comments is not None:
        parts['word/comments.xml'] = office.encoded(comments)
    if tracked:
        if 'word/settings.xml' not in parts:
            raise ValueError('변경 추적을 위한 settings.xml이 없는 DOCX는 지원하지 않습니다.')
        settings = office.xml(parts['word/settings.xml'])
        tracking = settings.find(tag('trackRevisions'))
        if tracking is None:
            # CT_Settings 순서: revisionView 다음, doNotTrackMoves 이전.
            preceding = ('writeProtection view zoom removePersonalInformation removeDateAndTime '
                         'doNotDisplayPageBoundaries displayBackgroundShape printPostScriptOverText '
                         'printFractionalCharacterWidth printFormsData embedTrueTypeFonts embedSystemFonts '
                         'saveSubsetFonts saveFormsData mirrorMargins alignBordersAndEdges '
                         'bordersDoNotSurroundHeader bordersDoNotSurroundFooter gutterAtTop '
                         'hideSpellingErrors hideGrammaticalErrors activeWritingStyle proofState formsDesign '
                         'attachedTemplate linkStyles stylePaneFormatFilter stylePaneSortMethod documentType '
                         'mailMerge revisionView').split()
            index = max((i + 1 for i, e in enumerate(settings) if e.tag in {tag(n) for n in preceding}), default=0)
            tracking = etree.Element(tag('trackRevisions'))
            settings.insert(index, tracking)
        tracking.set(tag('val'), 'true')
        parts['word/settings.xml'] = office.encoded(settings)
    office.save(path, digest, dest, parts, infos, zip_comment)
    return {'success': True, 'path': str(dest), 'source_path': str(path), 'source_sha256': digest,
            'items': changes, 'changed_count': len(changes), 'track_changes': tracked,
            'note': '새 텍스트는 교체 범위 첫 run의 글자 서식을 사용합니다. 원본은 보존했습니다.'}
