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

FORMATS = {'xlsx', 'xltx', 'ods', 'ots'}
ODF = 'urn:oasis:names:tc:opendocument:xmlns:'
XLINK = '{http://www.w3.org/1999/xlink}href'
MIMES = {'ods': 'application/vnd.oasis.opendocument.spreadsheet',
         'ots': 'application/vnd.oasis.opendocument.spreadsheet-template'}


def inspect(data, format):
    """Reject active/external input before the engine sees any conversion bytes."""
    if format not in FORMATS:
        raise DocumentUnsupported('변환 사본은 XLSX·XLTX·ODS·OTS만 지원합니다')
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
    with spreadsheet_files.archive(data) as archive:
        names = set(archive.namelist())
        if archive.read('mimetype').decode('ascii').strip() != MIMES[format]:
            raise DocumentUnsupported('확장자와 ODF 형식이 다릅니다')
        if not {'content.xml', 'META-INF/manifest.xml'} <= names:
            raise DocumentUnsupported('ODF 통합문서 구조가 불완전합니다')
        sheets = boolean_literals = boolean_formulas = 0
        for name in names:
            # vj-ok: archive part security classification, not cell comparison.
            if any(part in name.lower().split('/') for part in ('scripts', 'basic')):
                raise DocumentUnsupported('매크로가 있는 ODF는 변환하지 않습니다')
            if not name.endswith('.xml'):
                continue
            root = fromstring(archive.read(name))
            for element in root.iter():
                local = element.tag.rsplit('}', 1)[-1]
                if local in {'script', 'event-listener', 'encryption-data',
                             'dde-link', 'database-source-sql', 'database-source-query',
                             'database-source-table', 'object-ole'}:
                    raise DocumentUnsupported('외부 연결·스크립트·암호화 ODF는 변환하지 않습니다')
                href = element.get(XLINK)
                if href and not href.startswith('#'):
                    link = urlsplit(href)
                    target = posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(link.path)))
                    # Embedded charts refer to their containing workbook as '..'.
                    # Resolve within the package, including its root directory.
                    internal = target == '.' or target in names or any(n.startswith(target+'/') for n in names)
                    if link.scheme or link.netloc or target == '..' or target.startswith(('/', '../')) or not internal:
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
        raise DocumentUnsupported('ODS·OTS 변환에는 LibreOffice가 필요합니다')
    filters = {'xlsx': 'Calc MS Excel 2007 XML', 'xltx': 'Calc MS Excel 2007 XML Template',
               'ods': 'calc8', 'ots': 'calc8_template'}
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
    if {source_format, output_format} & {'ods', 'ots'}:
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
        raise DocumentUnsupported('변환 사본은 XLSX·XLTX·ODS·OTS만 지원합니다')
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
    output_info = inspect(converted, output_format)
    if source_info['sheets'] != output_info['sheets']:
        raise DocumentUnsupported('변환 중 시트 수가 달라졌습니다. 결과를 등록하지 않았습니다')
    # Conversion chains retain earlier known losses as well as this step's facts.
    changes = list(document.get('provenance', {}).get('loss_report', {}).get('changes', []))
    if source_info['boolean_literal_nodes'] != output_info['boolean_literal_nodes']:
        changes.append('불리언 상수 기록 수가 달라졌습니다. TRUE/FALSE 수식으로 바뀔 수 있어 입력 타입 보존을 보장하지 않습니다.')
    report = {'status': 'partial', 'changes': changes, 'source_format': source_format, 'output_format': output_format,
              'source': source_info, 'output': output_info, 'sheet_count_preserved': True,
              'unverified': ['셀 타입·수식 의미', '피벗·차트·이름·유효성', '서식·인쇄·날짜 체계'],
              'engine': ('copy' if source_format == output_format else 'LibreOffice'
                         if {source_format, output_format} & {'ods', 'ots'} else 'ONLYOFFICE'),
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
