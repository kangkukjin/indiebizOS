"""Conversion copies preserve source ownership and reject active file content."""
import io
import zipfile

import boot_paths  # noqa: F401
import pytest
from openpyxl import Workbook, load_workbook

import spreadsheet_formats as formats
from office_sessions import DocumentConflict, DocumentUnsupported
from spreadsheet_workspace import SpreadsheetWorkspace


def xlsx(value=12, template=False):
    book = Workbook(); book.template = template
    book.active['A1'] = '00123'; book.active['B1'] = value
    book.active['C1'] = '=B1*2'
    output = io.BytesIO(); book.save(output)
    return output.getvalue()


def odf(extra='', files=None, format='ods'):
    output = io.BytesIO()
    content = ('<office:document-content xmlns:office="'+formats.ODF+'office:1.0" '
               'xmlns:table="'+formats.ODF+'table:1.0" xmlns:xlink="http://www.w3.org/1999/xlink">'
               '<office:body><office:spreadsheet><table:table table:name="Sheet1">'+extra+
               '</table:table></office:spreadsheet></office:body></office:document-content>')
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('mimetype', formats.MIMES[format])
        archive.writestr('content.xml', content)
        archive.writestr('META-INF/manifest.xml', '<manifest/>')
        for name, value in (files or {}).items():
            archive.writestr(name, value)
    return output.getvalue()


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(formats.document_office, 'available', lambda: True)
    return SpreadsheetWorkspace(tmp_path/'office')


def opened(app, tmp_path):
    source = tmp_path/'original.xlsx'; source.write_bytes(xlsx())
    return source, app.open(source)['document']


def test_copy_records_pinned_draft_not_original(app, tmp_path, monkeypatch):
    source, doc = opened(app, tmp_path)
    session = app.acquire(doc['id'], 'one')['session']
    session.update(blob=app.store.blob(xlsx(37)), state='draft', session_revision=1)
    app.store.put('session', session)
    seen = []
    def converter(app, document_id, data, source_format, output_format):
        seen.append(load_workbook(io.BytesIO(data)).active['B1'].value)
        return odf()
    monkeypatch.setattr(formats, '_convert_bytes', converter)
    result = formats.convert(app, doc['id'], 'ods', doc['revision_id'], session['id'],
                             session['client_id'], session['engine_epoch'], 1)
    assert seen == [37]
    assert load_workbook(source).active['B1'].value == 12
    assert result['document']['id'] != doc['id']
    assert result['document']['provenance']['unsaved'] is True
    assert result['conversion_report']['status'] == 'partial'
    assert result['conversion_report']['unverified']
    assert app.detail(doc['id'])['session']['blob'] == session['blob']


def test_revision_and_writer_conflicts_before_conversion(app, tmp_path, monkeypatch):
    _, doc = opened(app, tmp_path)
    monkeypatch.setattr(formats, '_convert_bytes', lambda *a: pytest.fail('must not convert'))
    with pytest.raises(DocumentConflict):
        formats.convert(app, doc['id'], 'ods', 'stale')
    app.acquire(doc['id'], 'one')
    with pytest.raises((DocumentConflict, ValueError, TypeError)):
        formats.convert(app, doc['id'], 'ods', doc['revision_id'])


def test_changed_session_during_conversion_is_not_registered(app, tmp_path, monkeypatch):
    _, doc = opened(app, tmp_path)
    session = app.acquire(doc['id'], 'one')['session']
    def converter(*args):
        session['session_revision'] += 1
        app.store.put('session', session)
        return odf()
    monkeypatch.setattr(formats, '_convert_bytes', converter)
    with pytest.raises(DocumentConflict):
        formats.convert(app, doc['id'], 'ods', doc['revision_id'], session['id'],
                        session['client_id'], session['engine_epoch'], 0)
    assert len(app.list()) == 1


@pytest.mark.parametrize('extra,files', [
    ('<table:table-source xlink:href="https://example.org/private"/>', {}),
    ('<office:script/>', {}),
    ('', {'Basic/macro.xml': '<script/>'}),
    ('<table:table-cell table:formula="of:=WEBSERVICE(&quot;https://x&quot;)"/>', {}),
    ('', {'META-INF/evil.xml': '<encryption-data/>'}),
])
def test_odf_active_inputs_rejected(extra, files):
    with pytest.raises(DocumentUnsupported):
        formats.inspect(odf(extra, files), 'ods')


def test_template_identity_and_rejection_of_renamed_format():
    assert formats.inspect(xlsx(template=True), 'xltx')['sheets'] == 1
    with pytest.raises(DocumentUnsupported):
        formats.inspect(xlsx(template=True), 'xlsx')
    with pytest.raises(DocumentUnsupported):
        formats.inspect(odf(format='ots'), 'ods')


def test_converter_content_ticket_and_expiry(app, tmp_path):
    _, doc = opened(app, tmp_path)
    app.store.put('sheet_conversion', {'id':'conversion', 'document_id':doc['id'],
        'blob':doc['source_sha256'], 'token':'secret', 'expires':9999999999})
    assert formats.content(app, 'conversion', 'secret') == app.store.bytes(doc['source_sha256'])
    with pytest.raises(PermissionError):
        formats.content(app, 'conversion', 'wrong')
    row = app.store.get('sheet_conversion', 'conversion'); row['expires'] = 0
    app.store.put('sheet_conversion', row)
    with pytest.raises(PermissionError):
        formats.content(app, 'conversion', 'secret')


def test_odf_internal_chart_does_not_count_as_workbook_sheet():
    payload=odf('<table:table-cell xlink:href="./Object 1"/>',
                {'Object 1/content.xml':'<table xmlns="'+formats.ODF+'table:1.0" xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href=".."/>'})
    assert formats.inspect(payload,'ods')['sheets']==1


def test_missing_libreoffice_is_explicit(monkeypatch):
    monkeypatch.setattr(formats.shutil,'which',lambda name:None)
    with pytest.raises(DocumentUnsupported,match='LibreOffice'):
        formats._libreoffice(xlsx(),'xlsx','ods')


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
