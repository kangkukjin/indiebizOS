"""Current source format at persistence and transport boundaries."""
import hashlib
import re

CURRENT_EDITION = 2
_HEADER = re.compile(r"\A\s*#!ibl[ \t]+edition=(\d+)[ \t]*(?:\n|$)")


def source_edition(source, requested=None):
    if not isinstance(source, str):
        raise ValueError('SOURCE_TYPE: code는 IBL 원문 문자열이어야 합니다.')
    header = _HEADER.match(source)
    if source.lstrip().startswith('#!ibl') and not header:
        raise ValueError('EDITION_HEADER: 파일 헤더는 #!ibl edition=2입니다.')
    declared = int(header[1]) if header else None
    if requested is not None and (type(requested) is not int or requested != CURRENT_EDITION):
        raise ValueError('EDITION_UNSUPPORTED: 지원하는 원문 형식은 edition=2입니다.')
    if declared is not None and declared != CURRENT_EDITION:
        raise ValueError('EDITION_UNSUPPORTED: 지원하지 않는 파일 형식입니다.')
    if declared is None and requested is None:
        raise ValueError('EDITION_REQUIRED: edition:2 또는 #!ibl edition=2가 필요합니다.')
    return CURRENT_EDITION


def require_current(source, requested=None):
    return source_edition(source, requested)


def explicit_source(source, requested=None):
    source_edition(source, requested)
    return source if source.lstrip().startswith('#!ibl') else '#!ibl edition=2\n' + source


def pin_source(source, requested=None):
    """Newly authored source is stored with an explicit format, never inferred on read."""
    if source == "":
        return ""
    return explicit_source(source, CURRENT_EDITION if requested is None else requested)


def program_hash(source, edition=CURRENT_EDITION):
    source_edition(source, edition)
    return hashlib.sha256(f'ibl-edition:{CURRENT_EDITION}\0{source}'.encode('utf-8', 'replace')).hexdigest()


def authoring_request(request):
    source = request.get('code') or request.get('pipeline') or ''
    if request.get('edition') is not None or (isinstance(source, str) and source.lstrip().startswith('#!ibl')):
        return request
    return {**request, 'edition': CURRENT_EDITION}


def text_result(text, **fields):
    """A producer-confirmed text result has the same shape in every caller."""
    return {**fields, 'success': True, 'message': text}
