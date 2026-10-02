"""Explicit CSV decoding/types and repeatable import copies; never guess IDs."""
import csv
import io
from datetime import date
from pathlib import Path

from common.value_semantics import numeric_value
from office_sessions import DocumentConflict, DocumentUnsupported
from office_store import identifier

ENCODINGS={'utf-8','utf-8-sig','utf-16','cp949','euc-kr'}
KINDS={'text','number','percent','boolean','date'}
MAX_CELLS=2000000


def decode(data,encoding='utf-8-sig',delimiter=',',quotechar='"'):
    if encoding not in ENCODINGS or delimiter not in (',','\t',';','|') or quotechar not in ('"',"'"):
        raise ValueError('인코딩·구분자·따옴표 설정을 확인하세요')
    try:
        text=data.decode(encoding,errors='strict')
    except UnicodeError as exc:
        raise ValueError('선택한 인코딩으로 읽을 수 없습니다. 인코딩을 다시 선택하세요') from exc
    rows=[];cells=0
    for row in csv.reader(io.StringIO(text,newline=''),delimiter=delimiter,quotechar=quotechar,strict=True):
        cells+=len(row)
        if len(rows)>=1048576 or len(row)>16384 or cells>MAX_CELLS:
            raise DocumentUnsupported('가져오기 한계를 초과했습니다. 원본은 유지됩니다. 필터·집계·분할 후 다시 가져오세요')
        if any(len(value)>32767 for value in row):
            raise ValueError('32767자를 초과하는 셀이 있습니다. 원문을 잘라 저장하지 않습니다')
        rows.append(row)
    return rows


def typed(value,kind):
    if kind=='text':return value
    if value=='':return None
    if kind in ('number','percent'):
        number=numeric_value(value)
        if number is None:raise ValueError('숫자 형식이 아닙니다')
        significant=value.replace(',','').replace('.','').lstrip('+-0')
        if len(significant.rstrip('%'))>15:
            raise ValueError('15자리 숫자 정밀도를 넘습니다. 텍스트 열로 가져오세요')
        return number/100 if kind=='percent' else number
    if kind=='boolean':
        if value.lower() not in ('true','false'):raise ValueError('true/false가 아닙니다')
        return value.lower()=='true'
    if kind=='date':return date.fromisoformat(value)
    raise ValueError('지원하지 않는 열 타입입니다')


def source(app,document_id,expected_revision):
    d=app._doc(document_id)
    if d['revision_id']!=expected_revision:
        raise DocumentConflict('가져오기 원본 버전이 바뀌었습니다')
    if d['source_format'] not in {'csv','tsv'}:
        raise DocumentUnsupported('CSV/TSV 가져오기 전용입니다')
    return d,app.store.bytes(d['source_sha256'])


def prepare(data,encoding,delimiter,quotechar,header,types):
    if type(header) is not bool:
        raise ValueError('header는 boolean입니다')
    rows=decode(data,encoding,delimiter,quotechar)
    width=max((len(r) for r in rows),default=0)
    if not width:raise ValueError('가져올 셀이 없습니다')
    types=types or ['text']*width
    if len(types)!=width or any(t not in KINDS for t in types):raise ValueError('모든 열의 타입을 지정하세요')
    converted=[];errors=[]
    for n,row in enumerate(rows):
        if len(row)!=width:
            errors.append({'row':n+1,'error':'열 개수가 다릅니다','expected':width,'actual':len(row)})
            continue
        result=[]
        for i,value in enumerate(row):
            try:result.append(typed(value,'text' if n==0 and header else types[i]))
            except ValueError as exc:
                errors.append({'row':n+1,'column':i+1,'value':value,'error':str(exc)})
                result.append(value)
        converted.append(result)
    return rows,converted,types,errors


def preview(app,document_id,expected_revision,encoding='utf-8-sig',delimiter=',',quotechar='"',header=True,types=None):
    _,data=source(app,document_id,expected_revision)
    rows,_,types,errors=prepare(data,encoding,delimiter,quotechar,header,types)
    return {'rows':rows[:30],'total_rows':len(rows),'shown_rows':min(30,len(rows)), 'truncated':len(rows)>30,  # clamp-ok: display-only preview; total_rows/shown_rows/truncated disclose selection after full_scan
            'types':types,'errors':errors[:100],'error_count':len(errors),'errors_truncated':len(errors)>100,
            'header':header,'full_scan':True,'duplicate_headers':len(rows[0])!=len(set(rows[0])) if header and rows else False}


def import_csv(app,document_id,expected_revision,encoding='utf-8-sig',delimiter=',',quotechar='"',header=True,types=None):
    from openpyxl import Workbook
    from document_creation import import_bytes
    d,data=source(app,document_id,expected_revision)
    rows,converted,types,errors=prepare(data,encoding,delimiter,quotechar,header,types)
    if errors:
        raise ValueError(f'전체 {len(rows)}행 검사에서 {len(errors)}개 타입·열 오류가 있습니다. 미리보기에서 확인하세요')
    book=Workbook();sheet=book.active;sheet.title='가져온 자료'
    for r,row in enumerate(converted,1):
        for c,value in enumerate(row,1):
            cell=sheet.cell(r,c,value)
            if isinstance(value,str):
                cell.data_type='s'  # '=,+,-,@' and numeric identifiers remain literal text.
                cell.number_format='@'
            elif isinstance(value,date):cell.number_format='yyyy-mm-dd'
            elif types[c-1]=='percent':cell.number_format='0.00%'
    if header:sheet.freeze_panes='A2'
    output=io.BytesIO();book.save(output)
    result=import_bytes(app,Path(d['title']).stem+'_imported.xlsx',output.getvalue())
    recipe={'id':identifier(),'source_resource_id':document_id,'source_revision_id':expected_revision,
            'source_sha256':d['source_sha256'],'target_resource_id':result['document']['id'],
            'encoding':encoding,'delimiter':delimiter,'quotechar':quotechar,'header':header,'types':types,
            'rows_imported':len(rows),'cells_imported':sum(len(r) for r in rows),'original_preserved':True,
            'baseline_blob':result['document']['source_sha256'], 'sheet_id':'1', 'runs':[]}
    app.store.put('sheet_import',recipe)
    result['import']=recipe
    return result
