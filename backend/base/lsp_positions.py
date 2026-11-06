"""LSP coordinates and file identities. Public coordinates are 1-based codepoints."""
import codecs
import hashlib
import io
import tokenize
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname


def digest(data):
    return hashlib.sha256(data).hexdigest()


def decode(data, path=''):
    if data.startswith(codecs.BOM_UTF8):
        encoding = 'utf-8-sig'
    elif data.startswith(codecs.BOM_UTF16_LE):
        return data[2:].decode('utf-16-le'), 'utf-16-le-bom'
    elif data.startswith(codecs.BOM_UTF16_BE):
        return data[2:].decode('utf-16-be'), 'utf-16-be-bom'
    elif str(path).endswith('.py'):
        encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
    else:
        encoding = 'utf-8'
    return data.decode(encoding), encoding


def encode(text, encoding):
    if encoding == 'utf-16-le-bom':
        return codecs.BOM_UTF16_LE + text.encode('utf-16-le')
    if encoding == 'utf-16-be-bom':
        return codecs.BOM_UTF16_BE + text.encode('utf-16-be')
    return text.encode(encoding)


def uri_path(uri):
    parsed = urlsplit(uri)
    if parsed.scheme != 'file' or parsed.query or parsed.fragment:
        raise ValueError('LSP 파일 URI가 필요합니다')
    if parsed.netloc not in ('', 'localhost'):
        raise ValueError('원격 파일 URI는 이 작업 공간에서 지원하지 않습니다')
    return Path(url2pathname(parsed.path)).resolve()


def lines(text):
    # splitlines() also splits Unicode paragraph separators; LSP does not.
    return text.split('\n')


def line_text(text, line):
    parts = lines(text)
    if type(line) is not int or not 0 <= line < len(parts):
        raise ValueError('줄 번호가 본문 범위를 벗어났습니다')
    return parts[line].removesuffix('\r')


def units(text, encoding):
    if encoding == 'utf-16':
        return len(text.encode('utf-16-le')) // 2
    if encoding == 'utf-8':
        return len(text.encode('utf-8'))
    if encoding == 'utf-32':
        return len(text)
    raise ValueError('미지원 LSP 위치 인코딩: ' + encoding)


def to_lsp(text, position, encoding='utf-16'):
    line, column = position['line'], position['column']
    if type(line) is not int or type(column) is not int or line < 1 or column < 1:
        raise ValueError('행과 열은 1 이상의 정수여야 합니다')
    value = line_text(text, line - 1)
    if column > len(value) + 1:
        raise ValueError('열 번호가 본문 범위를 벗어났습니다')
    return {'line': line - 1, 'character': units(value[:column - 1], encoding)}


def from_lsp(text, position, encoding='utf-16'):
    line, count = position['line'], position['character']
    value = line_text(text, line)
    if type(count) is not int or count < 0:
        raise ValueError('잘못된 LSP 열 번호')
    consumed = 0
    for index, char in enumerate(value):
        if consumed == count:
            return {'line': line + 1, 'column': index + 1}
        consumed += units(char, encoding)
        if consumed > count:
            raise ValueError('문자 내부를 가리키는 LSP 위치입니다')
    return {'line': line + 1, 'column': len(value) + 1}


def range_public(text, span, encoding='utf-16'):
    return {key: from_lsp(text, span[key], encoding) for key in ('start', 'end')}


def range_lsp(text, span, encoding='utf-16'):
    return {key: to_lsp(text, span[key], encoding) for key in ('start', 'end')}


def offset(text, position, encoding='utf-16'):
    public = from_lsp(text, position, encoding)
    return sum(len(p) + 1 for p in lines(text)[:public['line'] - 1]) + public['column'] - 1


def edit_text(text, edits, encoding='utf-16'):
    spans = []
    for edit in edits:
        span = edit.get('range') or edit.get('replace')
        if not span or not isinstance(edit.get('newText'), str):
            raise ValueError('유효한 TextEdit가 필요합니다')
        start, end = (offset(text, span[k], encoding) for k in ('start', 'end'))
        if start > end:
            raise ValueError('뒤집힌 편집 범위')
        spans.append((start, end, edit['newText']))
    ordered = sorted(spans, key=lambda s: (s[0], s[1]))
    for left, right in zip(ordered, ordered[1:]):
        if left[1] > right[0]:
            raise ValueError('겹치거나 중복된 편집 범위')
    for start, end, replacement in reversed(ordered):
        text = text[:start] + replacement + text[end:]
    return text
