"""51~60위 감사 회귀: 화면/외부 API는 대역, 저장소·문서는 임시 경로."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import boot_paths  # noqa: F401
import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'data/packages/installed/tools'


def load(package, name='handler'):
    path = PKG / package / (name + '.py')
    spec = importlib.util.spec_from_file_location('rank51_' + package.replace('-', '_') + name, path)
    mod = importlib.util.module_from_spec(spec)
    old = sys.path[:]
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path[:] = old
    return mod


@pytest.fixture(autouse=True)
def fake_kosis_key(monkeypatch):
    monkeypatch.setenv('KOSIS_API_KEY', 'test-only')


@pytest.mark.parametrize('known', [False, True])
def test_screen_ref_failure_never_types_in_current_focus(monkeypatch, known):
    mod = load('computer-use')
    writes = []
    monkeypatch.setattr(mod, '_get_pyautogui', lambda: NS(write=lambda *a, **k: writes.append(a)))
    monkeypatch.setattr(mod, '_ax_set_value', lambda *a: False)
    monkeypatch.setattr(mod, '_AX_SESSION', {'r1': {'el': object()}} if known else {})
    result = json.loads(mod._do_type({'ref': 'r1', 'text': 'secret'}))
    assert result['success'] is False
    assert writes == []


def test_screen_inline_region_reaches_capture(monkeypatch):
    mod = load('computer-use')
    seen = []
    monkeypatch.setattr(mod, '_capture_screenshot', lambda r: seen.append(r) or {})
    monkeypatch.setattr(mod, '_get_screen_size', lambda: (1280, 800))
    mod._do_screenshot({'x': 2, 'y': 3, 'width': 20, 'height': 30})
    assert seen == [{'x': 2, 'y': 3, 'width': 20, 'height': 30}]


@pytest.mark.parametrize('xy', [(1280, 0), (0, 800)])
def test_screen_rejects_outside_pixel_boundary(xy):
    with pytest.raises(ValueError):
        load('computer-use')._validate_coords(*xy)


@pytest.mark.parametrize('reply', ['', '   '])
def test_brief_empty_response_retries_then_fails(monkeypatch, reply):
    import oneshot_facade
    calls = []
    monkeypatch.setattr(oneshot_facade, 'execution_oneshot', lambda *a, **kw: calls.append(a) or reply)
    result = json.loads(load('ai-ops')._brief({'items': [{'x': 1}], 'instruction': '요약'}))
    assert result['success'] is False and len(calls) == 2


def test_brief_zero_rows_skips_model(monkeypatch):
    import oneshot_facade
    monkeypatch.setattr(oneshot_facade, 'execution_oneshot', lambda *a, **k: pytest.fail('unexpected model'))
    out = json.loads(load('ai-ops')._brief({'items': [], 'instruction': '요약'}))
    assert out['success'] and out['rows_in'] == 0 and 'message' not in out


def test_compute_mixed_rows_are_not_silently_deleted():
    out = load('data-ops')._op_compute({'items': [{'x': 1}, 7]}, {'set': {'y': '2'}})
    assert out['success'] is False


def test_compute_numeric_and_cell_errors():
    out = load('data-ops')._op_compute({'items': [{'x': '3,500'}, {'x': 0}]}, {'set': {'y': '7000 / x'}})
    assert out['items'][0]['y'] == 2
    assert out['items'][1]['y'] is None and out['compute_errors'] == 1


def restaurants(monkeypatch, fail=False):
    mod = load('location-services')
    rows = [{'name': str(i), 'lat': 37, 'lng': 127} for i in range(5)]
    monkeypatch.setattr(mod, 'search_kakao_restaurants', lambda *a: {'error': 'offline'} if fail else {'restaurants': rows[:2]})
    monkeypatch.setattr(mod, 'search_naver_local', lambda *a: {'error': 'offline'} if fail else {'restaurants': rows[2:]})
    return mod


def test_restaurant_total_failure_is_failure(monkeypatch):
    out = restaurants(monkeypatch, True).search_restaurants_combined('밥', enrich=False)
    assert out['success'] is False and len(out['errors']) == 2


@pytest.mark.parametrize('limit', [0, 2, -1, 'oops'])
def test_restaurant_limit(monkeypatch, limit):
    mod = restaurants(monkeypatch)
    out = json.loads(mod.execute({'query': '밥', 'limit': limit, 'enrich': False}, NS(tool_name='search_restaurants')))
    if isinstance(limit, int) and limit >= 0:
        assert len(out['items']) == limit
    else:
        assert out['success'] is False


def test_kosis_search_retains_table_ids(monkeypatch):
    mod = load('kosis', 'tool_kosis_api')
    monkeypatch.setattr(mod, 'api_call', lambda *a, **k: [{'ORG_ID': '101', 'TBL_ID': 'DT_X', 'TBL_NM': '인구'}])
    out = mod.integrated_search('인구')
    assert out['items'][0]['org_id'] == '101' and out['items'][0]['tbl_id'] == 'DT_X'


@pytest.mark.parametrize('endpoint', ['integrated_search', 'indicators', 'statistics_info', 'statistics_data'])
def test_kosis_error_object_not_success(monkeypatch, endpoint):
    mod = load('kosis', 'tool_kosis_api')
    monkeypatch.setattr(mod, 'api_call', lambda *a, **k: {'err': '20', 'errMsg': 'invalid key'})
    assert mod._make_request(endpoint, {})['success'] is False


@pytest.mark.parametrize('method,args', [('integrated_search', ('x',)), ('get_statistics_data', ('101', 'x')), ('get_indicators', ())])
def test_kosis_empty_rows_stay_currency(monkeypatch, method, args):
    mod = load('kosis', 'tool_kosis_api')
    monkeypatch.setattr(mod, 'api_call', lambda *a, **k: [])
    out = getattr(mod, method)(*args)
    assert out['success'] and out['items'] == []


def test_kosis_indicator_catalog_is_currency(monkeypatch):
    mod = load('kosis', 'tool_kosis_api')
    monkeypatch.setattr(mod, 'api_call', lambda *a, **k: [{'INDICATOR_ID': 'a', 'INDICATOR_NM': '인구'}])
    assert mod.get_indicators()['items'][0]['indicator_id'] == 'a'


def test_document_json_array_is_table_not_json_prose(tmp_path):
    mod = load('data-ops', 'doc_build')
    out = json.loads(mod.render_document({'_prev_result': '[{"value": "hello"}]', 'format': 'html'}, str(tmp_path)))
    assert out['success']
    text = Path(out['path']).read_text()
    assert '<table' in text and '[{&quot;' not in text


@pytest.mark.parametrize('bad', [True, 0.5, 'oops'])
def test_ai_invalid_index_never_attaches_wrong_source(monkeypatch, bad):
    import oneshot_facade
    monkeypatch.setattr(oneshot_facade, 'oneshot_json', lambda *a, **k: ([{'_i': bad, 'label': 'new'}], None))
    out = json.loads(load('ai-ops')._transform({'items': [{'secret': 'zero'}, {'secret': 'one'}], 'instruction': '표시'}))
    assert out['success'] is False


def test_ai_input_index_does_not_override_internal_index(monkeypatch):
    import oneshot_facade
    prompts = []
    monkeypatch.setattr(oneshot_facade, 'oneshot_json', lambda p, *a: prompts.append(p) or ([{'_i': 0, 'label': 'new'}], None))
    out = json.loads(load('ai-ops')._transform({'items': [{'_i': 99, 'name': 'a'}], 'instruction': '표시'}))
    payload = json.loads(prompts[0].split('[items]\n')[1].split('\n\n[지시]')[0])
    assert payload[0]['_i'] == 0 and out['items'][0]['name'] == 'a'
    assert '_i' not in out['items'][0]


@pytest.mark.parametrize('fields', [[{}], [1]])
def test_ai_invalid_fields_are_rejected(monkeypatch, fields):
    import oneshot_facade
    monkeypatch.setattr(oneshot_facade, 'oneshot_json', lambda *a, **k: pytest.fail('invalid fields reached model'))
    out = json.loads(load('ai-ops')._transform({'items': [{'x': 1}], 'fields': fields, 'instruction': '표시'}))
    assert out['success'] is False


def storage(tmp_path, monkeypatch):
    mod = load('pc-manager', 'storage_db')
    monkeypatch.setattr(mod, 'SCANS_DIR', str(tmp_path / 'scans'))
    monkeypatch.setattr(mod, 'SCANS_JSON', str(tmp_path / 'scans/scans.json'))
    return mod


def test_storage_rescan_preserves_annotations(tmp_path, monkeypatch):
    mod = storage(tmp_path, monkeypatch)
    folder = tmp_path / 'files'; folder.mkdir(); (folder / 'a.txt').write_text('abc')
    assert mod.scan_directory(str(folder))['success']
    mod.add_annotation(str(folder), str(folder), 'keep me')
    assert mod.scan_directory(str(folder))['success']
    assert mod.get_annotations(str(folder))['annotations'][0]['note'] == 'keep me'
    out = mod.get_summary(str(folder))
    assert out['items'][0]['extension'] == 'txt'


def test_storage_file_is_not_directory(tmp_path, monkeypatch):
    mod = storage(tmp_path, monkeypatch)
    path = tmp_path / 'a.txt'; path.write_text('a')
    assert mod.scan_directory(str(path))['success'] is False


@pytest.mark.parametrize('content', ['{broken', '{}', '[2]'])
def test_storage_corrupt_registry_is_not_overwritten(tmp_path, monkeypatch, content):
    mod = storage(tmp_path, monkeypatch)
    mod._ensure_scans_dir(); Path(mod.SCANS_JSON).write_text(content)
    with pytest.raises(ValueError):
        mod.create_scan(str(tmp_path))
    assert Path(mod.SCANS_JSON).read_text() == content


def test_messages_missing_neighbor_is_error():
    mod = load('business')
    bm = NS(get_neighbor=lambda n: None, get_contacts=lambda n: [], get_messages=lambda **k: [])
    out = json.loads(mod._msg_thread(bm, {'neighbor_id': 999}))
    assert out['success'] is False


def test_package_list_includes_active_and_action_count(monkeypatch):
    import package_manager, ibl_routing, vocabulary_state
    monkeypatch.setattr(package_manager.package_manager, 'list_installed', lambda **k: [{'id': 'web', 'name': 'Web'}])
    monkeypatch.setattr(package_manager.package_manager, 'list_available', lambda **k: [{'id': 'sleep', 'name': 'Sleep', 'installed': False}])
    monkeypatch.setattr(vocabulary_state, 'inventory', lambda: {'actions': {'sense:search': 'web', 'sense:crawl': 'web'}})
    out = ibl_routing._package_op({'op': 'list'})
    assert out['items'][0]['active'] is True and out['items'][0]['action_count'] == 2
    assert out['items'][1]['active'] is False


def test_storage_walk_failure_rolls_back_files_and_metadata(tmp_path, monkeypatch):
    mod = storage(tmp_path, monkeypatch)
    folder = tmp_path / 'files'; folder.mkdir(); (folder / 'old.txt').write_text('abc')
    assert mod.scan_directory(str(folder))['success']
    before = Path(mod.SCANS_JSON).read_bytes()
    def broken_walk(path, onerror):
        onerror(PermissionError('denied'))
        yield
    monkeypatch.setattr(mod.os, 'walk', broken_walk)
    out = mod.scan_directory(str(folder))
    assert out['success'] is False
    assert mod.get_summary(str(folder))['file_count'] == 1
    conn = mod._get_connection(out['scan_id'])
    try:
        assert conn.execute('select filename from files').fetchone()[0] == 'old.txt'
    finally:
        conn.close()
    assert Path(mod.SCANS_JSON).read_bytes() == before


def test_storage_volume_name_resolves(monkeypatch):
    mod = load('pc-manager')
    monkeypatch.setitem(sys.modules, 'storage_db', NS(
        list_scans=lambda: {'scans': [{'name': 'Photos', 'root_path': '/photos'}]},
        get_summary=lambda p: {'resolved': p}))
    assert json.loads(mod._get_storage_summary({'volume_name': 'photos'}))['resolved'] == '/photos'


@pytest.mark.parametrize('names', [['Alice'], ['Alice', 'ALICE']])
def test_messages_name_resolution(monkeypatch, names):
    mod = load('business')
    rows = [{'id': i + 1, 'name': n} for i, n in enumerate(names)]
    bm = NS(get_neighbors=lambda: rows, get_neighbor=lambda n: rows[n - 1],
            get_contacts=lambda n: [], get_messages=lambda **k: [])
    out = json.loads(mod._msg_thread(bm, {'neighbor_id': 'alice'}))
    if len(names) == 1:
        assert out['neighbor_id'] == 1 and out['name'] == 'Alice'
    else:
        assert out['success'] is False


def test_kosis_false_info_uses_data(monkeypatch):
    mod = load('kosis')
    monkeypatch.setattr(mod, 'load_module', lambda n: NS(get_statistics_data=lambda **kw: {'selected': 'data'}))
    assert mod.execute({'org_id': '101', 'tbl_id': 'T', 'info': 'false'}, NS(tool_name='kosis_lookup'))['selected'] == 'data'


@pytest.mark.parametrize('count', [0, '0', -1, 1.5, True, 'bad'])
def test_kosis_limit_zero_and_invalid_skip_request(monkeypatch, count):
    mod = load('kosis', 'tool_kosis_api')
    monkeypatch.setattr(mod, 'api_call', lambda *a, **k: pytest.fail('unexpected API request'))
    out = mod.integrated_search('x', count)
    assert out['success'] is (count in (0, '0'))


def test_screen_capture_failure_does_not_reuse_file(tmp_path, monkeypatch):
    mod = load('computer-use')
    paths = []
    def failed_capture(args, **kwargs):
        paths.append(args[-1])
        return NS(returncode=1)
    monkeypatch.setattr(mod.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(mod.subprocess, 'run', failed_capture)
    for _ in range(2):
        with pytest.raises(PermissionError):
            mod._capture_screenshot()
    assert paths[0] != paths[1] and all(not Path(p).exists() for p in paths)



def test_restaurant_partial_pagination_failure_keeps_rows(monkeypatch):
    mod = load('location-services')
    monkeypatch.setattr(mod, 'check_api_key', lambda name: (True, None))
    answers = iter([{'documents': [{'place_name': 'a', 'x': '127', 'y': '37'}],
                     'meta': {'is_end': False}}, {'error': 'offline'}])
    monkeypatch.setattr(mod, 'api_call', lambda *a, **kw: next(answers))
    out = mod.search_kakao_restaurants('밥', size=20)
    assert out['success'] is False and out['partial'] and len(out['restaurants']) == 1


def test_restaurant_branches_with_different_addresses_are_distinct(monkeypatch):
    mod = restaurants(monkeypatch)
    monkeypatch.setattr(mod, 'search_kakao_restaurants', lambda *a: {'restaurants': [
        {'name': '카페(강남점)', 'address': '강남로 1', 'lat': 37, 'lng': 127}]})
    monkeypatch.setattr(mod, 'search_naver_local', lambda *a: {'restaurants': [
        {'name': '카페(서초점)', 'address': '서초로 2', 'lat': 37.1, 'lng': 127.1}]})
    assert len(mod.search_restaurants_combined('카페', enrich=False)['items']) == 2


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
