"""Current listing search: spatial coverage, missing data and bounded detail work."""
import importlib.util
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import boot_paths  # noqa: F401
import pytest


@pytest.fixture
def mod():
    path = Path(__file__).resolve().parents[1] / 'data/packages/installed/tools/real-estate/tool_zigbang.py'
    spec = importlib.util.spec_from_file_location('test_realty_zigbang', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def detail(iid, deposit=10000, area=None):
    return {'itemId': iid, 'salesType': '전세', 'price': {'deposit': deposit, 'rent': 0},
            'area': {'전용면적M2': 55} if area is None else area,
            'location': {'lat': 37, 'lng': 127}, 'floor': {}}


def test_radius_reads_neighbor_cell_and_deduplicates_details(mod, monkeypatch):
    center = (36.999, 127.002)
    nearby = (37.007, 127.002)
    assert mod._geohash(*center) != mod._geohash(*nearby)
    seen, calls = [], []
    def listing(url, **kwargs):
        gh = parse_qs(urlparse(url).query)['geohash'][0]
        seen.append(gh)
        return {'items': [{'id': 7, 'lat': nearby[0], 'lng': nearby[1]}] if gh == mod._geohash(*nearby) else []}
    monkeypatch.setattr(mod, '_http_json', listing)
    monkeypatch.setattr(mod, '_fetch_detail', lambda iid: calls.append(iid) or detail(iid))
    out = mod.get_zigbang_listings(dict(lat=center[0], lng=center[1], radius=1000, lease='전세'))
    assert [r['itemId'] for r in out['items']] == [7]
    assert calls == [7]
    assert len(seen) == len(set(seen))


def test_marker_duplicates_are_fetched_once(mod, monkeypatch):
    monkeypatch.setattr(mod, '_http_json', lambda *a, **k: {'items': [{'id': 1, 'lat': 37, 'lng': 127}] * 3})
    calls = []
    monkeypatch.setattr(mod, '_fetch_detail', lambda iid: calls.append(iid) or detail(iid))
    out = mod.get_zigbang_listings(dict(lat=37, lng=127, lease='전세'))
    assert calls == [1]
    assert len(out['items']) == 1


def test_supply_area_does_not_impersonate_exclusive_area(mod):
    row = mod._detail_to_row(detail(1, area={'공급면적M2': 80, '계약면적M2': 90}), 'villa', (37, 127), 0)
    assert row['area_m2'] is None
    assert row['supply_area_m2'] == 80
    assert row['contract_area_m2'] == 90


def test_failed_detail_preserves_success_and_failure(mod, monkeypatch):
    monkeypatch.setattr(mod, '_http_json', lambda *a, **k: {'items': [{'id': i, 'lat': 37, 'lng': 127} for i in (1, 2)]})
    monkeypatch.setattr(mod, '_fetch_detail', lambda iid: detail(iid) if iid == 1 else None)
    out = mod.get_zigbang_listings(dict(lat=37, lng=127, lease='전세'))
    assert [r['itemId'] for r in out['items']] == [1]
    assert out['source_complete'] is False
    assert out['errors'][0]['item_id'] == 2


def test_detail_error_keeps_reason(mod, monkeypatch):
    monkeypatch.setattr(mod, '_http_json', lambda *a, **k: {'items': [{'id': 1, 'lat': 37, 'lng': 127}]})
    def fail(iid):
        raise TimeoutError('detail timed out')
    monkeypatch.setattr(mod, '_fetch_detail', fail)
    out = mod.get_zigbang_listings(dict(lat=37, lng=127, lease='전세'))
    assert out['source_complete'] is False
    assert 'detail timed out' in out['errors'][0]['error']
    assert '없습니다' not in out['message']


def test_limit_counts_filtered_results_and_stops(mod, monkeypatch):
    monkeypatch.setattr(mod, '_http_json', lambda *a, **k: {'items': [{'id': i, 'lat': 37 + i / 100000, 'lng': 127} for i in range(1, 6)]})
    calls = []
    monkeypatch.setattr(mod, '_fetch_detail', lambda iid: calls.append(iid) or detail(iid, 30000 if iid == 1 else 10000))
    out = mod.get_zigbang_listings(dict(lat=37, lng=127, lease='전세', deposit_max=20000, limit=1))
    assert [r['itemId'] for r in out['items']] == [2]
    assert calls == [1, 2]
    assert out['truncations'][0]['scope'] == 'selection'


def test_cell_failure_preserves_other_cells(mod, monkeypatch):
    gh = mod._geohash(37, 127)
    def listing(url, **kwargs):
        if parse_qs(urlparse(url).query)['geohash'][0] == gh:
            return {'items': [{'id': 1, 'lat': 37, 'lng': 127}]}
        raise TimeoutError('cell failed')
    monkeypatch.setattr(mod, '_http_json', listing)
    monkeypatch.setattr(mod, '_fetch_detail', lambda iid: detail(iid))
    out = mod.get_zigbang_listings(dict(lat=37, lng=127, lease='전세'))
    assert [r['itemId'] for r in out['items']] == [1]
    assert out['source_complete'] is False
    assert out['errors'][0]['stage'] == 'list'


@pytest.mark.parametrize('lat,lng,radius', [(float('nan'),127,3000),(91,127,3000),(37,181,3000),(37,127,-1)])
def test_invalid_geometry_fails_before_network(mod, monkeypatch, lat, lng, radius):
    monkeypatch.setattr(mod, '_http_json', lambda *a, **k: pytest.fail('invalid geometry reached network'))
    assert mod.get_zigbang_listings(dict(lat=lat,lng=lng,radius=radius))['success'] is False


def test_full_ibl_keeps_partial_listings_and_reuses_snapshot(mod, monkeypatch, tmp_path):
    import json
    from dataclasses import replace
    from ibl_v2_adapters import load_registry, decode_envelope, Adapted
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    monkeypatch.setattr(mod, '_http_json', lambda *a, **k: {'items': [
        {'id': i, 'lat': 37, 'lng': 127} for i in (1, 2, 3)]})
    monkeypatch.setattr(mod, '_fetch_detail', lambda iid: None if iid == 2 else
                        detail(iid, area={'공급면적M2': 80} if iid == 3 else None))
    registry = load_registry(str(tmp_path))
    original = registry['sense:realty']
    calls = []
    def run(runtime, args):
        calls.append(args)
        raw = (mod.get_zigbang_listings({**args, 'lat': 37, 'lng': 127})
               if args['source'] == 'zigbang' else {'success': True, 'items': []})
        return Adapted(*decode_envelope(raw, original.contract['adapter']))
    registry['sense:realty'] = replace(original, run=run, dependency=None)
    code = (Path(__file__).resolve().parents[1] /
            'docs/experiments/long_sentence_imagination/round_56/drafts/main_v2.ibl').read_text()
    inputs = dict(snapshot='', cap=20000, out=str(tmp_path / 'base'))
    plan = compile_program(code, registry, inputs)
    assert not plan.issues, plan.report()
    result = Runtime(plan, inputs).run()
    assert result['success'], json.dumps(result.get('diagnostic'), ensure_ascii=False)
    assert result['source_complete'] is False
    assert result['value']['rows'] == 2
    assert result['value']['qualified'] == 1
    assert result['value']['unknown'] == 1
    assert result['value']['failed'] == 2
    rows = json.loads((tmp_path / 'base/comparison.json').read_text())['rows']
    assert all(r['search_regions'] == ['평택 비전동', '평택 동삭동'] for r in rows)
    raw = tmp_path / 'base/raw.json'
    before = raw.read_bytes()
    inputs.update(snapshot=str(raw), cap=9000, out=str(tmp_path / 'variant'))
    second = Runtime(compile_program(code, registry, inputs), inputs).run()
    assert second['success'], second
    assert second['value']['qualified'] == 0 and second['value']['unknown'] == 1
    assert len(calls) == 4 and raw.read_bytes() == before


@pytest.mark.parametrize('center', [(37,127), (35,129), (0,179.999), (-35,-179.999)])
def test_radius_cover_includes_every_sampled_bearing(mod, center):
    import math
    lat, lng = center
    radius = 3000
    cells = mod._radius_cells(lat, lng, radius)
    for bearing in range(0, 360, 5):
        a, b, d, t = math.radians(lat), math.radians(lng), radius / 6371000, math.radians(bearing)
        y = math.asin(math.sin(a)*math.cos(d) + math.cos(a)*math.sin(d)*math.cos(t))
        x = b + math.atan2(math.sin(t)*math.sin(d)*math.cos(a), math.cos(d)-math.sin(a)*math.sin(y))
        assert mod._geohash(math.degrees(y), (math.degrees(x)+180) % 360-180) in cells


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
