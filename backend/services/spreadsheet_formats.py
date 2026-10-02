"""Explicit spreadsheet conversion copies through the installed office engine.

Conversion never publishes to the source file. The editor remains the authority
for active edits; callers must capture and fence its draft before conversion.
"""
import posixpath
import re
import secrets
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx
import jwt
from defusedxml.ElementTree import fromstring

import document_office
import spreadsheet_files
from document_creation import import_bytes
from office_sessions import DocumentConflict, DocumentUnsupported, read_bytes
from office_store import identifier

FORMATS = {'xlsx', 'xltx', 'ods', 'ots', 'fods'}
ODF = 'urn:oasis:names:tc:opendocument:xmlns:'
XLINK = '{http://www.w3.org/1999/xlink}href'
MIMES = {'ods': 'application/vnd.oasis.opendocument.spreadsheet',
         'ots': 'application/vnd.oasis.opendocument.spreadsheet-template'}


def inspect(data, format):
    """Reject active/external input before the engine sees any conversion bytes."""
    if format not in FORMATS:
        raise DocumentUnsupported('변환 사본은 XLSX·XLTX·ODS·OTS·FODS만 지원합니다')
    if format in {'xlsx', 'xltx'}:
        meta = spreadsheet_files.validate(data)
        with spreadsheet_files.archive(data) as archive:
            types = fromstring(archive.read('[Content_Types].xml'))
            kind = next((e.get('ContentType', '') for e in types
                         if e.get('PartName') == '/xl/workbook.xml'), '')
            expected = ('application/vnd.openxmlformats-officedocument.'
                        'spreadsheetml.' + ('template' if format == 'xltx' else 'sheet') + '.main+xml')
            if kind != expected:
                raise DocumentUnsupported('확장자와 통합문서 형식이 다릅니다')
            boolean_literals = boolean_formulas = 0
            for sheet in meta['sheets']:
                for cell in fromstring(archive.read(sheet['path'])).iter(spreadsheet_files.NS+'c'):
                    if cell.get('t') == 'b':
                        if cell.find(spreadsheet_files.NS+'f') is None:
                            boolean_literals += 1
                        else:
                            boolean_formulas += 1
        return {'sheets': len(meta['sheets']), 'date_system': meta['date_system'],
                'boolean_literal_nodes': boolean_literals, 'boolean_formula_nodes': boolean_formulas}
    if format == 'fods':
        from office_sessions import MAX_BYTES
        if len(data) > MAX_BYTES:
            raise DocumentUnsupported('스프레드시트 크기 상한은 25MB입니다')
        root = fromstring(data)
        office = '{'+ODF+'office:1.0}'
        if root.tag != office+'document' or root.get(office+'mimetype') != MIMES['ods']:
            raise DocumentUnsupported('올바른 FODS 통합문서가 아닙니다')
        return _inspect_odf({'content.xml': root}, {'content.xml'}, flat=True)
    with spreadsheet_files.archive(data) as archive:
        names = set(archive.namelist())
        if not {'mimetype', 'content.xml', 'META-INF/manifest.xml'} <= names:
            raise DocumentUnsupported('ODF 통합문서 구조가 불완전합니다')
        if archive.read('mimetype').decode('ascii').strip() != MIMES[format]:
            raise DocumentUnsupported('확장자와 ODF 형식이 다릅니다')
        for name in names:
            # vj-ok: archive part security classification, not cell comparison.
            if any(part in name.lower().split('/') for part in ('scripts', 'basic')):
                raise DocumentUnsupported('매크로가 있는 ODF는 변환하지 않습니다')
        parts = {name: fromstring(archive.read(name)) for name in names if name.endswith('.xml')}
    return _inspect_odf(parts, names)


def _empty_script_library(element):
    """LibreOffice emits an inert Basic library container even in macro-free FODS."""
    script = '{'+ODF+'script:1.0}'
    return (element.tag == '{'+ODF+'office:1.0}script'
            and element.attrib == {script+'language': 'ooo:Basic'}
            and not (element.text or '').strip() and len(element) == 1
            and element[0].tag == '{http://openoffice.org/2004/office}libraries'
            and not element[0].attrib and len(element[0]) == 0
            and not (element[0].text or '').strip()
            and not (element[0].tail or '').strip())

def _flat_chart_parent(element, parents):
    """A nested ODF chart's '..' refers to its in-document drawing host, not a file."""
    if element.tag != '{'+ODF+'chart:1.0}chart':
        return False
    for tag in ('office:1.0}chart', 'office:1.0}body',
                'office:1.0}document', 'drawing:1.0}object'):
        element = parents.get(element)
        if element is None or element.tag != '{'+ODF+tag:
            return False
    return True

def _inspect_odf(parts, names, flat=False):
    sheets = boolean_literals = boolean_formulas = 0
    for name, root in parts.items():
        parents = {child: parent for parent in root.iter() for child in parent} if flat else {}
        for element in root.iter():
            local = element.tag.rsplit('}', 1)[-1]
            if local == 'script' and _empty_script_library(element):
                continue
            if local in {'script', 'event-listener', 'encryption-data',
                         'dde-link', 'database-source-sql', 'database-source-query',
                         'database-source-table', 'object-ole'}:
                raise DocumentUnsupported(f'외부 연결·스크립트·암호화 ODF는 변환하지 않습니다 ({local})')
            href = element.get(XLINK)
            if href and not href.startswith('#') and not (
                    flat and href == '..' and _flat_chart_parent(element, parents)):
                link = urlsplit(href)
                target = posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(link.path)))
                # Embedded charts may reference the containing packaged workbook.
                # A flat document has no sibling package parts to resolve.
                internal = target == '.' or target in names or any(n.startswith(target+'/') for n in names)
                if flat or link.scheme or link.netloc or target == '..' or target.startswith(('/', '../')) or not internal:
                    raise DocumentUnsupported(f'외부 참조가 있는 ODF는 변환하지 않습니다 ({name}: {href})')
            formula = element.get('{'+ODF+'table:1.0}formula', '')
            if name == 'content.xml' and element.get('{'+ODF+'office:1.0}value-type') == 'boolean':
                if formula:
                    boolean_formulas += 1
                else:
                    boolean_literals += 1
            if re.search(r'WEBSERVICE|DDE\s*\(|IMAGE\s*\(|https?:|file:|\|', formula, re.I):
                raise DocumentUnsupported('외부 자원 수식은 변환하지 않습니다')
        if name == 'content.xml':
            sheets = len(root.findall('{'+ODF+'office:1.0}body/{'+ODF+
                                      'office:1.0}spreadsheet/{'+ODF+'table:1.0}table'))
    if not sheets:
        raise DocumentUnsupported('ODF 시트를 찾지 못했습니다')
    return {'sheets': sheets, 'date_system': 'unverified',
            'boolean_literal_nodes': boolean_literals, 'boolean_formula_nodes': boolean_formulas}


def _libreoffice(data, source_format, output_format):
    executable = shutil.which('soffice')
    if not executable:
        raise DocumentUnsupported('ODS·OTS·FODS 변환에는 LibreOffice가 필요합니다')
    filters = {'xlsx': 'Calc MS Excel 2007 XML', 'xltx': 'Calc MS Excel 2007 XML Template',
               'ods': 'calc8', 'ots': 'calc8_template', 'fods': 'OpenDocument Spreadsheet Flat XML'}
    with tempfile.TemporaryDirectory(prefix='sheet-convert-') as folder:
        root = Path(folder)
        profile = root/'profile'; (profile/'user').mkdir(parents=True)
        (profile/'user/registrymodifications.xcu').write_text(
            '<oor:items xmlns:oor="http://openoffice.org/2001/registry">'
            '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
            '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>'
            '</item></oor:items>')
        source = root/('source.'+source_format); source.write_bytes(data)
        output = root/'output'; output.mkdir()
        result = subprocess.run([executable, '-env:UserInstallation='+profile.as_uri(),
            '--headless', '--norestore', '--convert-to', output_format+':'+filters[output_format],
            '--outdir', str(output), str(source)], capture_output=True, text=True, timeout=120)
        path = output/('source.'+output_format)
        if result.returncode or not path.is_file():
            raise DocumentUnsupported('LibreOffice 변환에 실패했습니다: '+result.stderr[-1000:])
        return read_bytes(path)


def _convert_bytes(app, document_id, data, source_format, output_format):
    # The installed ONLYOFFICE ODF converter emits invalid numFmts attributes.
    # Use a separate, explicitly reported conversion copy, never editor caches.
    if {source_format, output_format} & {'ods', 'ots', 'fods'}:
        return _libreoffice(data, source_format, output_format)
    cfg = document_office.settings()
    if not cfg:
        raise DocumentUnsupported('로컬 사무 편집 엔진을 시작하세요')
    row = {'id': identifier(), 'token': secrets.token_urlsafe(32),
           'document_id': document_id, 'blob': app.store.blob(data),
           'expires': time.time()+240}
    app.store.put('sheet_conversion', row)
    request = {'async': False, 'filetype': source_format, 'outputtype': output_format,
               'key': row['id'], 'url': cfg['callback_origin'].rstrip('/') +
               '/spreadsheets/convert-io/' + row['id'] + '?ticket=' + row['token'],
               'title': 'conversion.' + source_format}
    request['token'] = jwt.encode(request, cfg['secret'], algorithm='HS256')
    try:
        response = httpx.post(cfg['url'].rstrip('/')+'/converter', json=request,
                              headers={'Accept': 'application/json'}, timeout=180, trust_env=False)
        response.raise_for_status()
        result = response.json()
        if not result.get('endConvert') or not result.get('fileUrl'):
            raise DocumentUnsupported('엔진 변환 실패: '+str(result.get('error', '미완료')))
        return document_office.download(result['fileUrl'], cfg)
    finally:
        row['expires'] = 0
        app.store.put('sheet_conversion', row)


def content(app, conversion_id, ticket):
    row = app.store.get('sheet_conversion', conversion_id)
    app._doc(row['document_id'])
    if row['expires'] < time.time() or not secrets.compare_digest(row['token'], ticket):
        raise PermissionError('변환 자료 접근 자격이 만료됐습니다')
    return app.store.bytes(row['blob'])


def convert(app, document_id, output_format, expected_revision, session_id=None,
            client_id=None, epoch=None, expected=None):
    if output_format not in FORMATS:
        raise DocumentUnsupported('변환 사본은 XLSX·XLTX·ODS·OTS·FODS만 지원합니다')
    with app.store.lock():
        document = app._doc(document_id)
        if document['revision_id'] != expected_revision:
            raise DocumentConflict('원본 버전이 바뀌었습니다')
        source_format = document['source_format']
        if source_format not in FORMATS:
            raise DocumentUnsupported('이 형식의 안전한 변환 경로는 아직 없습니다')
        session = None
        if document['session_id']:
            _, session = app._session(document_id, session_id, client_id, epoch, expected)
        blob = session['blob'] if session else document['source_sha256']
        data = app.store.bytes(blob)
        source_info = inspect(data, source_format)
    converted = data if source_format == output_format else _convert_bytes(
        app, document_id, data, source_format, output_format)
    inspect(converted, output_format)
    from spreadsheet_conversion_types import preserve_booleans
    converted, repaired_booleans = preserve_booleans(data, source_format, converted, output_format)
    output_info = inspect(converted, output_format)
    if source_info['sheets'] != output_info['sheets']:
        raise DocumentUnsupported('변환 중 시트 수가 달라졌습니다. 결과를 등록하지 않았습니다')
    # Conversion chains retain earlier known losses as well as this step's facts.
    changes = list(document.get('provenance', {}).get('loss_report', {}).get('changes', []))
    # Literal preservation is checked by logical sheet/cell coordinates above.
    # ODF repeat compression means XML node counts are not cell counts.
    report = {'status': 'partial', 'changes': changes, 'source_format': source_format, 'output_format': output_format,
              'source': source_info, 'output': output_info, 'sheet_count_preserved': True,
              'boolean_literals_restored': repaired_booleans, 'source_boolean_literals_preserved': True,
              'unverified': ['셀 타입·수식 의미', '피벗·차트·이름·유효성', '서식·인쇄·날짜 체계'],
              'engine': ('copy' if source_format == output_format else 'LibreOffice'
                         if {source_format, output_format} & {'ods', 'ots', 'fods'} else 'ONLYOFFICE'),
              'calculation': '변환 엔진에서 재계산될 수 있습니다. 활성 편집기의 계산값을 대체하지 않습니다.',
              'message': '변환 사본입니다. 원본은 보존했습니다. 수식·차트·서식·인쇄를 비교하세요.'}
    with app.store.lock():
        current = app._doc(document_id)
        if current['revision_id'] != expected_revision or current['session_id'] != document['session_id']:
            raise DocumentConflict('변환 중 원본 또는 작성 세션이 바뀌었습니다')
        if session:
            _, current_session = app._session(document_id, session_id, client_id, epoch, expected)
            if current_session['blob'] != blob:
                raise DocumentConflict('변환 중 편집 초안이 바뀌었습니다')
    # import_bytes acquires the shared writer lock itself. Publish a new resource
    # from the pinned bytes; subsequent source edits cannot change this copy.
    result = import_bytes(app, Path(document['title']).stem+'_converted.'+output_format, converted)
    output = result['document']
    output['provenance'] = {'resource_id': document_id, 'revision_id': expected_revision,
        'snapshot_sha256': blob, 'session_revision': expected if session else None,
        'unsaved': blob != document['source_sha256'], 'original_preserved': True,
        'engine': report['engine'], 'loss_report': report}
    app.store.put('document', output)
    result['conversion_report'] = report
    return result
