"""Preserve literal booleans across office converters without evaluating formulas.

Only validated conversion copies enter here. Original formulas are never replaced;
source sheet name, coordinates, output type and cached value must all agree.
"""
import io
import zipfile

from lxml import etree
from openpyxl.utils.cell import coordinate_to_tuple

import spreadsheet_files
from office_sessions import DocumentUnsupported

OFFICE = '{urn:oasis:names:tc:opendocument:xmlns:office:1.0}'
TABLE = '{urn:oasis:names:tc:opendocument:xmlns:table:1.0}'
NS = spreadsheet_files.NS
MAX_BOOLEANS = 100000


def _xml(data):
    return etree.fromstring(data, etree.XMLParser(resolve_entities=False, no_network=True))


def _parts(data, format):
    if format == 'fods':
        return {'content.xml': _xml(data)}
    with spreadsheet_files.archive(data) as archive:
        if format in {'xlsx', 'xltx'}:
            return {s['path']: _xml(archive.read(s['path']))
                    for s in spreadsheet_files.inspect(data)['sheets']}
        return {'content.xml': _xml(archive.read('content.xml'))}


def _repeat(element, field, maximum):
    value = int(element.get(TABLE+field, '1'))
    if not 1 <= value <= maximum:
        raise DocumentUnsupported('ODF 반복 행·열 범위가 올바르지 않습니다')
    return value


def _rows(table):
    # Row groups belong to this sheet; chart/object tables inside cells do not.
    for child in table:
        if child.tag == TABLE+'table-row':
            yield child
        elif child.tag in {TABLE+'table-header-rows', TABLE+'table-rows', TABLE+'table-row-group'}:
            yield from _rows(child)

def _cells(data, format, parts):
    """Yield boolean XML nodes with their bounded logical coordinate rectangles."""
    if format in {'xlsx', 'xltx'}:
        for sheet in spreadsheet_files.inspect(data)['sheets']:
            for cell in parts[sheet['path']].iter(NS+'c'):
                if cell.get('t') == 'b':
                    row, col = coordinate_to_tuple(cell.get('r', ''))
                    value = cell.findtext(NS+'v')
                    if value not in {'0', '1'}:
                        raise DocumentUnsupported('불리언 캐시가 올바르지 않습니다')
                    formula = cell.find(NS+'f')
                    yield (sheet['name'], row, col, 1, 1, value == '1',
                           formula.text if formula is not None else None, cell, sheet['path'])
        return
    sheets = parts['content.xml'].findall(OFFICE+'body/'+OFFICE+'spreadsheet/'+TABLE+'table')
    for sheet in sheets:
        row = 1
        for line in _rows(sheet):
            rows = _repeat(line, 'number-rows-repeated', 1048576)
            col = 1
            for cell in line:
                if cell.tag not in {TABLE+'table-cell', TABLE+'covered-table-cell'}:
                    continue
                cols = _repeat(cell, 'number-columns-repeated', 16384)
                if cell.get(OFFICE+'value-type') == 'boolean':
                    value = cell.get(OFFICE+'boolean-value')
                    if value not in {'true', 'false', '1', '0'}:
                        raise DocumentUnsupported('ODF 불리언 값이 올바르지 않습니다')
                    if row+rows-1 > 1048576 or col+cols-1 > 16384:
                        raise DocumentUnsupported('ODF 불리언 좌표가 통합문서 한계를 넘습니다')
                    yield (sheet.get(TABLE+'name'), row, col, rows, cols,
                           value in {'true', '1'}, cell.get(TABLE+'formula'), cell, 'content.xml')
                col += cols
            row += rows


def _keys(cell):
    name, row, col, rows, cols = cell[:5]
    if rows*cols > MAX_BOOLEANS:
        raise DocumentUnsupported('불리언 보존 검사 상한 100,000셀을 초과했습니다')
    return [(name, r, c) for r in range(row, row+rows) for c in range(col, col+cols)]


def preserve_booleans(source, source_format, output, output_format):
    """Return output bytes and the count of proven literal representations repaired."""
    originals = {}
    for cell in _cells(source, source_format, _parts(source, source_format)):
        if cell[6] is None:
            for key in _keys(cell):
                if key in originals:
                    raise DocumentUnsupported('중복 불리언 셀 주소입니다')
                originals[key] = cell[5]
            if len(originals) > MAX_BOOLEANS:
                raise DocumentUnsupported('불리언 보존 검사 상한 100,000셀을 초과했습니다')
    if not originals:
        return output, 0
    parts = _parts(output, output_format)
    seen = set(); changed = set(); repaired = 0
    for cell in _cells(output, output_format, parts):
        keys = _keys(cell)
        matched = [key for key in keys if key in originals]
        if not matched:
            continue
        if any(key in seen or originals[key] is not cell[5] for key in matched):
            raise DocumentUnsupported('변환 중 불리언 값 또는 셀 대응이 달라졌습니다')
        formula = cell[6]
        if formula is not None:
            expected = 'TRUE()' if cell[5] else 'FALSE()'
            allowed = {expected} if output_format in {'xlsx', 'xltx'} else {'of:='+expected}
            if formula.upper() not in {item.upper() for item in allowed} or len(matched) != len(keys):
                raise DocumentUnsupported('불리언 상수의 변환 수식을 안전하게 보존할 수 없습니다')
            node = cell[7]
            if output_format in {'xlsx', 'xltx'}:
                if node.find(NS+'f').attrib:
                    raise DocumentUnsupported('공유·배열 불리언 수식은 상수로 바꾸지 않습니다')
                node.remove(node.find(NS+'f'))
            else:
                if any('number-matrix-' in key for key in node.attrib):
                    raise DocumentUnsupported('배열 불리언 수식은 상수로 바꾸지 않습니다')
                del node.attrib[TABLE+'formula']
            changed.add(cell[8]); repaired += len(matched)
        seen.update(matched)
    if seen != originals.keys():
        raise DocumentUnsupported('변환 중 불리언 상수가 누락되거나 타입이 달라졌습니다')
    if not changed:
        return output, 0
    replacements = {name: etree.tostring(parts[name], encoding='UTF-8', xml_declaration=True)
                    for name in changed}
    if output_format == 'fods':
        return replacements['content.xml'], repaired
    result = io.BytesIO()
    with spreadsheet_files.archive(output) as source_zip, zipfile.ZipFile(result, 'w') as dest:
        for item in source_zip.infolist():
            dest.writestr(item, replacements.get(item.filename, source_zip.read(item.filename)))
    return result.getvalue(), repaired
