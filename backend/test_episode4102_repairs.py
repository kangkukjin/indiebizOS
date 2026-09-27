"""General numeric transport, selection honesty and multimodal reading boundaries."""
import base64
import json
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
from PIL import Image
from common.pkg_utils import load_sibling
from ibl_v2_adapters import decode_envelope
from ibl_v2_compat import plain_arguments
from ibl_v2_ir import Fault, UNIT, pack
from test_ibl_general_capabilities import boundary  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'data/packages/installed/tools/web/tool_webcrawl.py'
TOOLS = ROOT / 'data/packages/installed/tools'
ADAPTER = {'protocol': 'legacy-envelope', 'value_path': ''}


@pytest.mark.parametrize('text', ['36.51053125899817', '127.24044686110923', '0.1', '-0.0', '1e-100'])
def test_decimal_json_transport_roundtrips_and_keeps_original(text):
    value = {'rows': [{'n': Decimal(text)}]}
    wire = plain_arguments(value)
    assert Decimal(str(json.loads(json.dumps(wire))['rows'][0]['n'])) == Decimal(text)
    assert isinstance(value['rows'][0]['n'], Decimal)
    assert wire is not value


@pytest.mark.parametrize('value', [Decimal('0.10000000000000001'), Decimal('1e1000'),
                                   Decimal('1e-1000'), 2**60, UNIT])
def test_unrepresentable_numbers_and_interpreter_objects_still_fail(value):
    with pytest.raises(Fault) as fault:
        plain_arguments({'rows': [value]})
    assert fault.value.code == 'LEGACY_VALUE'
    assert '$args.rows[0]' in str(fault.value)


@pytest.mark.parametrize('value', [Decimal('NaN'), Decimal('sNaN'), Decimal('Infinity'), float('nan')])
def test_nonfinite_numbers_remain_rejected(value):
    with pytest.raises(Fault):
        plain_arguments({'n': value})


def test_installed_adapter_passes_projected_numeric_copy(monkeypatch, tmp_path):
    import ibl_engine
    import ibl_v2_adapters
    from ibl_v2_entry import handle_request
    calls = []
    def execute(command, *args, **kwargs):
        calls.append(command)
        return {'success': True, 'items': [], 'lat': command['params']['lat']}
    monkeypatch.setattr(ibl_engine, 'execute_ibl', execute)
    result = handle_request({'edition': 2, 'code':
        '[sense:place]{query:"fixture",lat:36.51053125899817,lng:127.24044686110923}'}, str(tmp_path))
    assert result['success'], result
    assert type(calls[0]['params']['lat']) is float


def places(monkeypatch):
    module = load_sibling(TOOLS / 'location-services/handler.py', 'tool_place')
    monkeypatch.setattr(module, 'check_api_key', lambda *_: (True, None))
    return module


def docs(count):
    return [{'id': str(i), 'place_name': str(i), 'x': '127.2', 'y': '36.5'} for i in range(count)]


def test_requested_place_sample_can_flow_but_incomplete_sample_cannot(monkeypatch):
    module = places(monkeypatch)
    monkeypatch.setattr(module, 'api_call', lambda *a, **k: {
        'meta': {'pageable_count': 10, 'total_count': 100, 'is_end': True}, 'documents': docs(10)})
    result = module.place_search({'query': 'fixture', 'limit': 2})
    assert result['truncations'][0]['scope'] == 'selection'
    assert len(decode_envelope(result, ADAPTER)[0]['items']) == 2
    monkeypatch.setattr(module, 'api_call', lambda *a, **k: {
        'meta': {'pageable_count': 10, 'is_end': True}, 'documents': docs(1)})
    with pytest.raises(Fault) as fault:
        decode_envelope(module.place_search({'query': 'fixture', 'limit': 2}), ADAPTER)
    assert fault.value.code == 'PARTIAL_SOURCE'


def test_place_second_page_failure_is_not_swallowed(monkeypatch):
    module = places(monkeypatch)
    answers = iter([{'meta': {'pageable_count': 30, 'is_end': False}, 'documents': docs(15)},
                    {'error': 'provider timeout'}])
    monkeypatch.setattr(module, 'api_call', lambda *a, **k: next(answers))
    result = module.place_search({'query': 'fixture', 'limit': 30})
    assert not result['success'] and result['failed_page'] == 2 and len(result['items']) == 15
    with pytest.raises(Fault):
        decode_envelope(result, ADAPTER)


def test_snapshot_display_selection_flows_but_source_markers_still_fail(monkeypatch):
    import sys
    monkeypatch.syspath_prepend(str(TOOLS / 'browser-action'))
    snapshot = load_sibling(TOOLS / 'browser-action/handler.py', 'browser_snapshot')
    monkeypatch.setattr(snapshot, 'MAX_RESULT_CHARS', 150)
    result = snapshot._finalize_snapshot([{'ref': str(i), 'name': 'x' * 80} for i in range(4)], 'https://fixture.test', 'test')
    assert result['truncated'] and result['shown_count'] < result['element_count']
    assert decode_envelope(result, ADAPTER)[0]['success']
    for marker in [{'scope': 'source'}, {'scope': 'unknown'}]:
        with pytest.raises(Fault):
            decode_envelope({**result, 'truncations': [marker]}, ADAPTER)


@pytest.fixture
def crawl(monkeypatch, tmp_path):
    from common import spill
    monkeypatch.setattr(spill, '_root', lambda: str(tmp_path / 'spill'))
    module = load_sibling(WEB, 'tool_webcrawl')
    view = load_sibling(WEB, 'webcrawl_view')
    original_load = module.load_sibling
    monkeypatch.setattr(module, 'load_sibling', lambda anchor, name: view if name == 'webcrawl_view' else original_load(anchor, name))
    calls = []
    html = '<html><title>Notice</title><nav>login<img src="/logo.png"></nav><article id="notice"><p>Hours 9–18</p>'
    html += ''.join(f'<img src="/{i}.png" alt="poster {i}">' for i in range(5)) + '</article></html>'
    def get(url):
        calls.append(url)
        return SimpleNamespace(status_code=200, url=url, headers={'Content-Type':'text/html; charset=utf-8'}, content=html.encode())
    monkeypatch.setattr(module, '_http_get', get)
    monkeypatch.setattr(module, '_get_chrome_driver', lambda: None)
    monkeypatch.setattr(module, '_get_browser_session', lambda: None)
    monkeypatch.setattr(view, 'image_attachment', lambda url, source: {'b64': 'YQ==' * 1000, 'media_type':'image/png', 'url':url})
    return module, view, calls


def test_content_and_image_pages_share_html_and_exclude_navigation(crawl):
    module, _, calls = crawl
    first = module.crawl_website('https://fixture.test/notice', selector='#notice', include_images=True)
    assert first['success'] and first['text'] == 'Hours 9–18', json.dumps(first,ensure_ascii=False)
    assert first['image_count'] == 5 and len(first['image_items']) == 4 and first['next_image_offset'] == 4
    assert all('logo' not in item['url'] for item in first['image_items'])
    assert decode_envelope(first, ADAPTER)[0]['success']
    second = module.crawl_website('https://fixture.test/notice', selector='#notice', include_images=True, image_offset=4)
    assert second['success'] and len(second['image_items']) == 1 and second['next_image_offset'] is None
    assert calls == ['https://fixture.test/notice']
    assert first['source_ref'] == second['source_ref']
    saved = json.loads(Path(first['source_ref']['path']).read_text())
    assert len(saved['_page_structure']['documents']) == 1


def test_bad_selection_and_image_failure_are_visible(crawl, monkeypatch):
    module, view, _ = crawl
    assert not module.crawl_website('https://fixture.test/notice', selector='#missing')['success']
    assert not module.crawl_website('https://fixture.test/notice', selector='[')['success']
    def fail(*args):
        raise OSError('download failed')
    monkeypatch.setattr(view, 'image_attachment', fail)
    result = module.crawl_website('https://fixture.test/notice', include_images=True)
    assert not result['success'] and len(result['errors']) == 4 and result['text'] == 'Hours 9–18'


@pytest.mark.parametrize('options', [{'image_limit':5}, {'image_offset':-1}, {'include_images':'yes'},
                                    {'image_offset':1}, {'op':'links','selector':'article'}])
def test_invalid_image_selection_never_fetches(crawl, options):
    module, _, calls = crawl
    assert not module.crawl_website('https://fixture.test/notice', **options)['success']
    assert calls == []


def test_image_bytes_survive_v2_preview_and_native_harvest(boundary, crawl):
    from model_result_view import project_v2_result
    from image_envelopes import harvest_images
    value = crawl[0].crawl_website('https://fixture.test/notice', include_images=True)
    raw = {'edition':2, 'success':True, 'source_complete':True, 'value':value,
           'value_wire':{'protocol':'ibl-value/1','data':pack(value)}}
    shown = project_v2_result(raw)
    assert len(shown['images']) == 4
    _, images = harvest_images(json.dumps(shown))
    assert len(images) == 4 and all(i['b64'] == 'YQ==' * 1000 for i in images)
    assert raw['value']['image_items'][0]['image_data']['b64'] == 'YQ==' * 1000


def test_download_attachment_validates_raster_and_has_size_budget(monkeypatch):
    view = load_sibling(WEB, 'webcrawl_view')
    output = BytesIO(); Image.new('RGB', (20,30)).save(output, 'PNG')
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def raise_for_status(self): pass
        def iter_content(self, _): yield output.getvalue()
    monkeypatch.setattr(view.requests, 'get', lambda *a, **k: Response())
    result = view.image_attachment('https://fixture.test/img', 'https://fixture.test')
    assert result['original_size'] == [20,30] and base64.b64decode(result['b64']).startswith(b'\xff\xd8')
    monkeypatch.setattr(view, 'MAX_IMAGE_BYTES', 2)
    with pytest.raises(ValueError, match='8MiB'):
        view.image_attachment('https://fixture.test/img', 'https://fixture.test')


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
