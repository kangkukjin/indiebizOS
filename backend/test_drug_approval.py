"""Approved-product source distinguishes an empty page from unavailable evidence."""
import boot_paths  # noqa: F401
import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture
def source():
    spec = importlib.util.spec_from_file_location('drug_approval_test', ROOT / 'data/scripts/drug_approval.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

@pytest.mark.parametrize('raw', [{}, {'error': 'key=secret'}, {'header': {'resultCode': '30'}},
    {'header': {'resultCode': '00'}, 'body': {'totalCount': 1, 'items': 'broken'}}])
def test_unavailable_is_not_empty(source, monkeypatch, raw):
    monkeypatch.setattr(source, 'api_call', lambda *a, **k: raw)
    out = source.lookup({'query': '제품'})
    assert not out['success'] and out['source_complete'] is False
    assert out['error_code'] == 'SOURCE_UNAVAILABLE' and 'secret' not in str(out)

@pytest.mark.parametrize('items', [None, '', []])
def test_successful_empty_page(source, monkeypatch, items):
    monkeypatch.setattr(source, 'api_call', lambda *a, **k: {
        'header': {'resultCode': '00'}, 'body': {'totalCount': 0, 'items': items}})
    out = source.lookup({'query': '없는품목'})
    assert out['success'] and out['items'] == [] and out['total'] == 0 and not out['has_more']


def test_prescription_products_and_page_identity(source, monkeypatch):
    seen = []
    row = {'ITEM_SEQ': '123', 'ITEM_NAME': '의약품', 'ETC_OTC_CODE': '전문의약품', 'MAIN_ITEM_INGR': '성분'}
    def api(service, endpoint, **kw):
        seen.append((service, endpoint, kw['params']))
        return {'response': {'header': {'resultCode': '00'}, 'body': {'totalCount': 23, 'items': {'item': row}}}}
    monkeypatch.setattr(source, 'api_call', api)
    out = source.lookup({'id': '123', 'page': 2, 'limit': 10})
    assert out['items'][0]['classification'] == '전문의약품'
    assert out['items'][0]['raw'] == row and out['next_page'] == 3
    assert seen[0][2] == {'type': 'json', 'item_seq': '123', 'pageNo': 2, 'numOfRows': 10}

@pytest.mark.parametrize('args', [[], {}, {'query': 'x', 'page': True}, {'query': 'x', 'limit': 101}])
def test_bad_input_does_not_call_source(source, monkeypatch, args):
    monkeypatch.setattr(source, 'api_call', lambda *a, **k: pytest.fail('invalid input'))
    assert source.lookup(args)['success'] is False


def test_registered_contract_is_read_only_and_fresh():
    import yaml
    from ibl_v2_adapters import validate_contract
    registry = yaml.safe_load((ROOT / 'data/scripts/registry.yaml').read_text())
    # Registry uses a script-id mapping under scripts.
    entry = registry.get('scripts', registry)['의약품허가조회']
    contract = entry['callable_contract']
    validate_contract(contract)
    assert contract['effects'] == ['read_external'] and contract['per_run']
    assert (ROOT / 'data/scripts' / entry['file']).is_file()

if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
