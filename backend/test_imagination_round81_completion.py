"""81회차 잔여: 기본 사진 범위, 실제 반환값, 식별자, 검수·진단 경계."""
import boot_paths  # noqa: F401
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'data/packages/installed/tools'


def module(package, name='handler'):
    spec = importlib.util.spec_from_file_location('completion81_' + package.replace('-', '_') + name,
                                                TOOLS / package / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize('engine', ['spotlight', 'walk'])
def test_photo_exclusion_precedes_candidate_cap_and_limit(tmp_path, monkeypatch, engine):
    import file_index
    generated = tmp_path / 'outputs'
    personal = tmp_path / 'outputs-personal'
    generated.mkdir(); personal.mkdir()
    for p in [generated / 'a.png', generated / 'b.png', personal / 'camera.jpg']:
        p.write_bytes(b'fixture')
    monkeypatch.setattr(file_index, '_MAX_CANDIDATES', 1)
    monkeypatch.setattr(file_index, '_run_mdfind', lambda *a: [str(generated / 'a.png'), str(generated / 'b.png'), str(personal / 'camera.jpg')])
    monkeypatch.setattr(file_index, '_ranked_items', lambda paths, sort, limit, facets, **kw: [{'path': p} for p in paths[:limit]])
    query = getattr(file_index, '_' + engine + '_query')
    result = query('photo', None, None, None, False, None, str(tmp_path), 1, 'date', (),
                   exclude_paths=(str(generated),))
    assert result['total'] == 1
    assert result['items'] == [{'path': str(personal / 'camera.jpg')}]
    assert not result['truncated']
    assert 'warning' not in result


def test_photo_default_scope_preserves_explicit_path_and_phone(monkeypatch):
    mod = module('photo-manager')
    calls = []
    monkeypatch.setattr(mod.file_index, 'detect_body', lambda: {'profile': 'pc'})
    def query(**args):
        calls.append(args)
        return {'success': True, 'items': []}
    monkeypatch.setattr(mod.file_index, 'query', query)
    mod._query_photos({})
    mod._query_photos({'path': '/body/outputs'})
    mod._query_photos({'source': 'usb'})
    assert [c['path'] for c in calls] == [str(Path.home() / 'Pictures'), '/body/outputs', None]
    monkeypatch.setattr(mod.file_index, 'detect_body', lambda: {'profile': 'phone'})
    mod._query_photos({})
    assert calls[-1]['path'] is None


def test_camera_absence_does_not_claim_generated_origin():
    mod = module('photo-manager')
    record = mod._photo_record({'path': '/photos/scan.jpg'})
    assert record['origin'] == 'unknown' and record['lat'] is None and record['lng'] is None
    record = mod._photo_record({'camera': 'fixture', 'lat': 0, 'lng': 0})
    assert record['origin'] == 'camera' and record['lat'] == record['lng'] == 0


@pytest.mark.parametrize('raw,expected', [('1997', 1997), ('', None), (None, None), ('unknown', None),
                                         ('1997.5', None), (True, None), ('0', None)])
def test_music_year_is_numeric_or_unknown_without_rewriting_tag(raw, expected):
    mod = module('music-player', 'music_core')
    row = mod.track_row({'path': '/fixture.mp3', 'year': raw, 'genre': 'Jazz / 재즈'})
    assert row['year'] == expected
    assert row['year_raw'] == (raw or '')
    assert row['genre'] == 'Jazz / 재즈'


def test_radio_identity_only_when_catalog_supports_it(monkeypatch):
    mod = module('radio', 'tool_radio')
    known = mod._favorite_record({'name': 'KBS Cool FM'})
    assert known['station_id'] == 'kbs_coolfm' and known['broadcaster'] == 'KBS'
    known = mod._favorite_record({'name': 'My channel', 'stream_url': mod.TBS_URLS['fm']})
    assert known['station_id'] == 'tbs_fm'
    unknown = mod._favorite_record({'name': 'KBS fan mix', 'stream_url': 'https://example.invalid/radio'})
    assert unknown['station_id'] is None and unknown['broadcaster'] is None
    monkeypatch.setattr(mod, '_load_favorites', lambda: [{'name': 'KBS Cool FM'}])
    monkeypatch.setattr(mod, '_save_favorites', lambda _: pytest.fail('list must not write'))
    assert json.loads(mod.get_radio_favorites())['items'][0]['station_id'] == 'kbs_coolfm'
    assert 'stream_url' in json.loads(mod.get_korean_radio())['items'][0]


@pytest.mark.parametrize('op,argument', [('filter', 'where:($r)=>$r.missing == 1'),
                                      ('select', 'columns:($r)=>{x:$r.missing}'),
                                      ('compute', 'set:($r)=>{x:$r.missing}')])
def test_callback_fault_retains_row_and_field(op, argument):
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    source = '[table:' + op + ']{items:[{missing:1},{}],' + argument + '}'
    result = Runtime(compile_program(source, load_registry())).run()
    assert not result['success']
    details = result['diagnostic']['details']
    assert details['row_index'] == 1
    assert details['operation'] == op
    assert details['missing_fields'] == ['missing']


def test_schema_enum_reaches_current_compiler():
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    report = compile_program('[engines:tts]{text:"fixture",engine:"qwen3"}', load_registry()).report()
    assert report['status'] == 'invalid'
    assert any('engine' in str(issue) for issue in report['issues'])


@pytest.mark.parametrize('args', [{'topic': 'fixture'}, {'scenes': [{'title': 'missing html'}]}])
def test_internal_video_validation_is_explicit_failure(args, tmp_path):
    mod = module('media_producer')
    result = mod.create_html_video(args, str(tmp_path))
    assert result['success'] is False and result['error']


def test_html_broken_image_is_observed_without_network(tmp_path):
    from runtime_utils import setup_playwright_browsers_path
    setup_playwright_browsers_path()
    mod = module('media_producer', 'render_artifact')
    result = json.loads(mod.render_op_html({'html': '<h1>Visible page</h1><img src="file:///missing-image-81.png">',
                                          'width': 320, 'height': 180}, str(tmp_path)))
    assert result.get('success', True), result
    assert '이미지 로드 실패' in result['items'][0]['prescreen']
    assert result['items'][0]['layout']['broken_images']


def test_web_collections_preserve_legacy_values_and_supply_items(monkeypatch):
    from types import SimpleNamespace
    mod = module('web-builder')
    monkeypatch.setattr(mod, '_require_module', lambda _: SimpleNamespace(list_sites=lambda _: {'success': True, 'sites': [{'id':'x'}]}))
    sites = mod._h_site_list({}, None)
    assert sites['items'] == sites['sites'] == [{'id':'x'}]
    for kind, field in [('components','components'), ('sections','sections')]:
        monkeypatch.setattr(mod, '_h_list_' + kind, lambda *a, f=field: {'success':True, 'categories':{'hero':{f:[{'name':'x'}]}}})
        result = mod._h_web_catalog({'kind':kind}, None)
        assert result['items'] == [{'name':'x', 'category':'hero'}]
        assert result['count'] == 1 and result['categories']



def test_unobserved_operation_does_not_borrow_default_columns(monkeypatch):
    import ibl_access
    import ibl_typecheck
    monkeypatch.setattr(ibl_access, '_return_shapes', lambda: {
        'fixture:resource': {'kind':'items','keys':['card']},
        'fixture:resource#list': {'kind':'items','keys':['card']}})
    monkeypatch.setattr(ibl_typecheck, '_action_def', lambda *a: {
        'fixture':'[fixture:resource]{op:"list"}',
        'ops':{'default':'list','values':{'list':'cards','load':'details'}}})
    assert ibl_typecheck.catalog_entry('fixture','resource',{'op':'load'}) is None
    assert ibl_typecheck.catalog_entry('fixture','resource',{})['keys'] == ['card']



def test_supported_schema_values_remain_compilable():
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    registry = load_registry()
    for code in ('[sense:book]{source:"google",query:"fixture"}',
                 '[limbs:launch]{action:"open_ui"}'):
        assert compile_program(code, registry).report()['status'] != 'invalid'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
