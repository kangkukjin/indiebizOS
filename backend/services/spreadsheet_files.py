"""Bounded spreadsheet inspection. Never rewrites an existing workbook."""
import csv
import html
import io
import json
import posixpath
import re
import zipfile
from copy import deepcopy
from functools import lru_cache
from common.value_semantics import numeric_value

from defusedxml.ElementTree import fromstring
from office_sessions import DocumentUnsupported, MAX_BYTES

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'


def archive(data):
    if len(data) > MAX_BYTES:
        raise ValueError('스프레드시트 크기 상한은 25MB입니다')
    z = zipfile.ZipFile(io.BytesIO(data))
    names = z.namelist()
    if len(names) != len(set(names)) or len(names) > 10000:
        z.close()
        raise ValueError('중복 또는 과도한 ZIP 항목입니다')
    if sum(i.file_size for i in z.infolist()) > 200 * 1024 * 1024:
        z.close()
        raise ValueError('압축 해제 크기 상한을 초과했습니다')
    return z


def inspect(data):
    # Content-keyed cache: immutable source/draft bytes, never path or session ID.
    # Four compressed inputs are bounded by MAX_BYTES; callers own their metadata.
    return deepcopy(_inspect_bytes(bytes(data)))


@lru_cache(maxsize=4)
def _inspect_bytes(data):
    with archive(data) as z:
        if 'xl/workbook.xml' not in z.namelist():
            raise DocumentUnsupported('올바른 XLSX 통합문서가 아닙니다')
        book = fromstring(z.read('xl/workbook.xml'))
        relationships = fromstring(z.read('xl/_rels/workbook.xml.rels'))
        targets = {r.get('Id'): r.get('Target') for r in relationships}
        sheets = []
        for s in book.findall(NS+'sheets/'+NS+'sheet'):
            target = targets.get(s.get(REL+'id'), '')
            path = posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/'+target)
            if not path.startswith('xl/') or path not in z.namelist():
                raise ValueError('시트 관계가 올바르지 않습니다')
            sheets.append({'sheet_id':s.get('sheetId'), 'name':s.get('name'), 'path':path, 'state':s.get('state','visible')})
        blocked = []
        empty = True
        for sheet in sheets:
            root = fromstring(z.read(sheet['path']))
            if empty and (root.find('.//'+NS+'c/'+NS+'v') is not None or root.find('.//'+NS+'c/'+NS+'f') is not None):
                empty = False
            for formula in root.iter(NS+'f'):
                if re.search(r"\[[^\]]+\][A-Za-z0-9 _.']*!|https?:|WEBSERVICE|IMAGE\s*\(|RTD\s*\(|\|",formula.text or '',re.I):
                    blocked.append(sheet['path']+':external-formula')
        for name in z.namelist():
            if any(part in name.lower() for part in ('vbaproject', 'externallink', 'connections.xml', 'querytables/', 'activex/')):  # vj-ok: OOXML ZIP part-name security screening, not worksheet value equality
                blocked.append(name)
            if name.endswith('.rels'):
                for r in fromstring(z.read(name)):
                    if r.get('TargetMode') == 'External' and not r.get('Type','').endswith('/hyperlink'):
                        blocked.append(name+':external-resource')
        properties = book.find(NS+'workbookPr')
        from spreadsheet_grid import grid_blockers
        return {'sheets':sheets,'date_system':'1904' if properties is not None and properties.get('date1904') in ('1','true') else '1900',
                'blocked_parts':sorted(set(blocked)), 'calc_properties':dict(book.find(NS+'calcPr').attrib) if book.find(NS+'calcPr') is not None else {},
                'grid_blockers':grid_blockers(z.namelist()), 'empty':empty}


def validate(data):
    result = inspect(data)
    if result['blocked_parts']:
        raise DocumentUnsupported('외부 연결·매크로·외부 자원이 있는 파일은 원본 보존 상태로 열람합니다. 안전한 편집 어댑터 검증이 필요합니다')
    return result


def calculation_state(data):
    """Inspect saved calculation evidence without recalculating in another engine."""
    meta=inspect(data)
    errors=[]; missing=[]; unsupported=[]
    with archive(data) as z:
        for sheet in meta['sheets']:
            for cell in fromstring(z.read(sheet['path'])).iter(NS+'c'):
                formula=cell.find(NS+'f'); value=cell.find(NS+'v')
                ref={'sheet_id':sheet['sheet_id'],'cell':cell.get('r')}
                if cell.get('t')=='e':
                    errors.append({**ref,'error_code':value.text if value is not None else None})
                if formula is not None:
                    if formula.get('t','normal')!='normal':
                        unsupported.append(ref)
                    if value is None or value.text is None:
                        missing.append(ref)
    status='external_unresolved' if meta['blocked_parts'] else 'unsupported' if unsupported else 'error' if errors else 'stale' if missing else 'fresh'
    return {'status':status,'errors':errors,'missing_cache':missing,'unverified_formula_structures':unsupported}


def bounds(address):
    match = re.fullmatch(r'([A-Z]{1,3})([1-9][0-9]*)(?::([A-Z]{1,3})([1-9][0-9]*))?', address or '')
    if not match:
        raise ValueError('A1 또는 A1:C10 범위를 입력하세요')
    def column(text):
        n = 0
        for c in text:
            n = n*26+ord(c)-64
        return n
    a,b,c,d = match.groups()
    x1,y1,x2,y2 = column(a),int(b),column(c or a),int(d or b)
    if x1>x2 or y1>y2 or x2>16384 or y2>1048576 or (x2-x1+1)*(y2-y1+1)>10000:
        raise ValueError('유효한 범위와 한 번에 10,000셀 상한을 확인하세요')
    return x1,y1,x2,y2


def cell_name(column, row):
    name=''
    while column:
        column, rem=divmod(column-1,26)
        name=chr(65+rem)+name
    return name+str(row)


def render_range(observed, format='csv', encoding='utf-8-sig', newline='crlf', text_mode='safe'):
    """Export an immutable projection; JSON retains cell types and provenance.

    CSV/TSV are value-only and cannot encode the distinction between a blank
    cell and empty text. Safe mode prefixes potentially executable strings;
    raw mode preserves text but lets external consumers interpret it.
    """
    if format not in {'csv', 'tsv', 'html', 'json'}:
        raise ValueError('범위 출력 형식은 csv/tsv/html/json입니다')
    if encoding not in {'utf-8', 'utf-8-sig', 'utf-16', 'cp949', 'euc-kr'}:
        raise ValueError('지원하는 출력 인코딩을 선택하세요')
    if newline not in {'crlf', 'lf'} or text_mode not in {'safe', 'raw'}:
        raise ValueError('줄바꿈 또는 텍스트 출력 정책이 올바르지 않습니다')
    x1, y1, x2, y2 = bounds(observed['range'])
    width = x2 - x1 + 1
    items = observed['items']
    if observed.get('truncated') or len(items) != width * (y2 - y1 + 1):
        raise ValueError('불완전한 범위는 내보낼 수 없습니다')
    summary = {k: observed[k] for k in ('resource_id', 'revision_id', 'snapshot_id',
               'session_revision', 'calc_revision', 'calc_status', 'unsaved', 'range',
               'sheet', 'date_system', 'provenance')}
    summary.update(format=format, rows=y2-y1+1, columns=width, cells=len(items),
                   escaped_text_cells=0, missing_formula_cells=0, error_cells=0,
                   text_mode=text_mode, value_only=format != 'json')
    values = []
    for cell in items:
        value = cell['effective_value']
        if cell['error_code']:
            summary['error_cells'] += 1
            value = cell['error_code']
        elif cell['formula'] and value is None:
            summary['missing_formula_cells'] += 1
        if type(value) is bool:
            text = 'TRUE' if value else 'FALSE'
        else:
            text = '' if value is None else str(value)
        if (format in {'csv', 'tsv'} and text_mode == 'safe'
                and isinstance(value, str)
                and (text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')))):
            text = "'" + text
            summary['escaped_text_cells'] += 1
        values.append(text)
    rows = [values[i:i+width] for i in range(0, len(values), width)]
    if format in {'csv', 'tsv'}:
        stream = io.StringIO(newline='')
        writer = csv.writer(stream, delimiter=',' if format == 'csv' else '\t',
                            lineterminator='\r\n' if newline == 'crlf' else '\n')
        writer.writerows(rows)
        text = stream.getvalue()
        summary.update(encoding=encoding, newline=newline, blank_and_empty_text_merged=True)
        mime = 'text/csv' if format == 'csv' else 'text/tab-separated-values'
    elif format == 'json':
        text = json.dumps({'metadata': summary, 'items': items}, ensure_ascii=False, allow_nan=False)
        encoding, mime = 'utf-8', 'application/json'
    else:
        caption = html.escape(observed['sheet']['name'] + '!' + observed['range'])
        text = '<!doctype html><meta charset="utf-8"><title>' + caption + '</title>'
        text += '<table><caption>' + caption + '</caption><tbody>'
        text += ''.join('<tr>' + ''.join('<td>' + html.escape(v) + '</td>' for v in row) + '</tr>' for row in rows)
        text += '</tbody></table><pre>' + html.escape(json.dumps(summary, ensure_ascii=False)) + '</pre>'
        encoding, mime = 'utf-8', 'text/html'
    try:
        content = text.encode(encoding, errors='strict')
    except UnicodeEncodeError as exc:
        raise ValueError('선택한 인코딩으로 표현하지 못하는 문자가 있습니다. UTF-8을 선택하세요') from exc
    if len(content) > MAX_BYTES:
        raise ValueError('출력 상한 25MB를 초과했습니다. 범위를 나누세요')
    if mime.startswith('text/'):
        mime += '; charset=' + ('utf-8' if encoding == 'utf-8-sig' else encoding)
    return content, mime, summary


def projection(data, sheet_id, address):
    meta=inspect(data)
    sheet=next((s for s in meta['sheets'] if s['sheet_id']==str(sheet_id)), None)
    if not sheet:
        raise ValueError('시트 식별자가 없습니다')
    x1,y1,x2,y2=bounds(address)
    with archive(data) as z:
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            strings=[''.join(t.text or '' for t in s.iter(NS+'t')) for s in fromstring(z.read('xl/sharedStrings.xml'))]
        root=fromstring(z.read(sheet['path']))
        nodes={c.get('r'):c for c in root.iter(NS+'c')}
        items=[]
        for row in range(y1,y2+1):
            for col in range(x1,x2+1):
                name=cell_name(col,row)
                node=nodes.get(name)
                value, formula, typ, error = None,None,'blank',None
                if node is not None:
                    f=node.find(NS+'f'); v=node.find(NS+'v'); typ=node.get('t','n')
                    formula='='+ (f.text or '') if f is not None else None
                    raw=v.text if v is not None else None
                    if typ=='s':
                        value=strings[int(raw)] if raw is not None else ''
                        typ='text'
                    elif typ=='inlineStr':
                        value=''.join(t.text or '' for t in node.iter(NS+'t')); typ='text'
                    elif typ=='b':
                        value=raw=='1'; typ='boolean'
                    elif typ=='e':
                        error=raw; typ='error'
                    elif typ in ('str','d'):
                        value=raw if raw is not None else ''; typ='text' if typ=='str' else 'date'
                    elif raw is not None:
                        value=numeric_value(raw)
                        if value is None:
                            raise ValueError('유한하지 않거나 올바르지 않은 셀 숫자입니다')
                        typ='number'
                    else:
                        typ='blank'
                items.append({'cell':name,'entered_value':value if formula is None else None,'value_type':typ,
                    'formula':formula,'effective_value':value,'error_code':error,'style_id':node.get('s','0') if node is not None else '0',
                    'formula_type':node.find(NS+'f').get('t','normal') if node is not None and node.find(NS+'f') is not None else None})
        return {'items':items,'count':len(items),'truncated':False,'sheet':sheet,'range':address,
                'date_system':meta['date_system'],'protected':root.find(NS+'sheetProtection') is not None,
                'merged_ranges':[m.get('ref') for m in root.iter(NS+'mergeCell')]}
