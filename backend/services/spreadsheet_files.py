"""Bounded spreadsheet inspection. Never rewrites an existing workbook."""
import io
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
        for sheet in sheets:
            for formula in fromstring(z.read(sheet['path'])).iter(NS+'f'):
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
        return {'sheets':sheets,'date_system':'1904' if properties is not None and properties.get('date1904') in ('1','true') else '1900',
                'blocked_parts':sorted(set(blocked)), 'calc_properties':dict(book.find(NS+'calcPr').attrib) if book.find(NS+'calcPr') is not None else {}}


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
