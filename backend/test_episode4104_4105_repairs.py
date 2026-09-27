"""General regressions from typed recovery, source contracts and readable report QA."""
import base64
import importlib.util
import io
import json
import sys
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(relative, name):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize('source', [
    '[1,"a"] >> [table:each]{return unwrap($it).x}',
    '[{x:1},"a"] >> [table:each]{$r=unwrap($it);return $r.x}',
])
def test_invalid_unwrap_reports_type_instead_of_crashing(source):
    from ibl_v2_compile import compile_program
    result = compile_program(source).report()
    assert not result['ok']
    assert any(i['code'] == 'TYPE' for i in result['issues'])


def test_union_of_results_preserves_inner_types():
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    from ibl_v2_ir import ResultValue
    args = {'rows': [ResultValue(True, 1), ResultValue(True, 'a')]}
    plan = compile_program('$rows >> [table:each]{return unwrap($it)}', inputs=args)
    assert not plan.issues
    assert Runtime(plan, args).run()['value'] == [1, 'a']
    assert 'Result' not in str(plan.result_type)


@pytest.fixture(scope='module')
def registry():
    from ibl_v2_adapters import load_registry
    return load_registry()


@pytest.mark.parametrize('source', [
    '[sense:realty]{source:"zigbang",region:"city",limit:60}',
    '[{n:1}] >> [table:groupby]{by:[],agg:{total:["sum","n"]}}',
])
def test_bad_constraints_precede_all_effects(source, registry):
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    plan = compile_program(source, registry)
    assert any(i['code'] == 'ARGUMENT_CONTRACT' for i in plan.issues)
    assert Runtime(plan).run()['executed'] is False


def test_source_specific_maximum_does_not_limit_other_sources(registry):
    from ibl_v2_compile import compile_program
    from ibl_callable_contract import selected, problems
    c = registry['sense:realty'].contract
    assert problems(selected(c, {'source': 'zigbang'}), {'limit': 60})
    assert not problems(selected(c, {'source': 'naver'}), {'limit': 60})
    assert not compile_program('[sense:realty]{source:"naver",region:"city",limit:60}', registry).issues


@pytest.mark.parametrize('query,address,expected', [
    ('충남 논산시 내동', '충청남도 논산시 내동', True),
    ('전북 전주시', '전북특별자치도 전주시', True),
    ('경남 진주시', '경상남도 진주시', True),
    ('충북 논산시 내동', '충청남도 논산시 내동', False),
    ('장동', '전주시 색장동', False),
    ('논산시 내동', '충청남도 논산시 내동', True),
])
def test_province_aliases_keep_exact_neighborhood(query, address, expected, monkeypatch):
    folder = ROOT / 'data/packages/installed/tools/real-estate'
    monkeypatch.syspath_prepend(str(folder))
    mod = load('data/packages/installed/tools/real-estate/tool_naver.py', 'repair_naver')
    assert mod._region_matches(query, address) is expected


def test_guide_conditional_and_section_reads_do_not_hide_lost_context():
    from guide_registry import guide_read_view
    text = '# Root\nIntro\n## A\nFirst\n### Child\nNested\n## B\nLast\n'
    source = {'file': 'x.md', 'content': text}
    first = guide_read_view(source, {})
    assert first['content'] == text
    cached = guide_read_view(source, {'if_hash': first['content_hash']})
    assert cached['unchanged'] and 'content' not in cached
    changed = guide_read_view({**source, 'content': text+'new'}, {'if_hash': first['content_hash']})
    assert changed['content'].endswith('new')
    part = guide_read_view(source, {'section': 'A', 'if_hash': first['content_hash']})
    assert part['content'] == '## A\nFirst\n### Child\nNested\n'
    assert guide_read_view(source, {'section': 'missing'})['error']
    assert guide_read_view(source, {})['content'] == text


def test_failure_reference_opens_diagnostic_and_counts_leaves(monkeypatch, tmp_path):
    import model_result_view as view
    from supervision_store import TurnStore
    monkeypatch.setattr(view, 'evidence_store', lambda: TurnStore(tmp_path))
    raw = {'edition': 2, 'success': False, 'diagnostic': {'code': 'TOOL', 'message': 'bad'},
           'evidence': [{'id': 1, 'kind': 'tool_failure', 'incomplete': True},
                        {'id': 2, 'kind': 'failure'},
                        {'id': 3, 'kind': 'tool_failure', 'incomplete': False}]}
    result = view.project_result(raw)
    assert result['result_ref']['read_args']['path'] == ['diagnostic']
    assert result['evidence_summary']['tool_failures'] == 2
    assert result['evidence_summary']['source_failures'] == 1
    assert raw['evidence'][1]['kind'] == 'failure'
    store = TurnStore(tmp_path)
    store.log('tool.finished', internal_tool_failures=2, source_failures=1, check_rejected=True)
    assert store.cost['internal_tool_failures'] == 2
    assert store.cost['source_failures'] == store.cost['check_rejections'] == 1
    assert store.cost['execution_failures'] == 0


def image_payload(width, height):
    from PIL import Image
    im = Image.new('RGB', (width, height), 'white')
    im.putpixel((width-1, height-1), (255, 0, 0))
    buf = io.BytesIO(); im.save(buf, format='PNG')
    return {'base64': base64.b64encode(buf.getvalue()).decode(), 'media_type': 'image/png'}


def test_long_image_tiles_preserve_last_pixel_and_reject_silent_truncation():
    from PIL import Image
    mod = load('data/packages/installed/tools/media_producer/vision_read.py', 'repair_vision')
    original = image_payload(390, 7418)
    images, note = mod._readable_images(original)
    assert images[0] is original and len(images) == 6 and '원본' in note
    tiles = [Image.open(io.BytesIO(base64.b64decode(i['base64']))) for i in images[1:]]
    assert all(max(i.size) <= 1600 for i in tiles)
    assert tiles[-1].getpixel((389, tiles[-1].height-1)) == (255, 0, 0)
    normal = image_payload(800, 800)
    assert mod._readable_images(normal) == ([normal], '')
    with pytest.raises(ValueError, match='24개'):
        mod._readable_images(image_payload(10, 40000))


def test_report_tables_wrap_on_desktop_and_mobile(tmp_path):
    from playwright.sync_api import sync_playwright
    from runtime_utils import setup_playwright_browsers_path
    setup_playwright_browsers_path()
    html = load('data/scripts/보고서HTML.py', 'repair_html')
    text = '긴 설명이 끊기지 않고 끝까지 읽혀야 합니다. ' * 20
    source = '<style>'+html._CSS % {'acc': '#111', 'acc_d': '#fff'}+'</style><main><table><tr><th>항목</th><th>설명</th></tr><tr><td>검사</td><td>'+text+'</td></tr></table></main>'
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for width in (390, 1280):
            page = browser.new_page(viewport={'width': width, 'height': 900})
            page.set_content(source)
            sizes = page.locator('table').evaluate('(e)=>[e.clientWidth,e.scrollWidth,e.clientHeight]')
            assert sizes[1] <= sizes[0] + 2
            assert sizes[2] > 100
            assert page.locator('td').last.inner_text() == text.strip()
            page.close()
        browser.close()
    render = load('data/packages/installed/tools/media_producer/render_artifact.py', 'repair_render')
    out = json.loads(render.render_op_html({'html': source, 'width': 390, 'height': 200}, str(tmp_path)))
    row = out['items'][0]
    assert row['height'] > 200
    assert row['layout']['overflow_count'] == 0


def test_report_qa_passes_dom_facts_through_real_ibl(registry):
    from ibl_v2_adapters import Adapter
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    seen = []
    def read(rt, args):
        seen.append(args['question'])
        return {'message': 'readable'}
    mocks = {
        'self:script': lambda rt, args: {'items': [{'links': 2, 'tables': 1, 'headings': 1, 'dropped_lines': 0, 'bytes': 100}]},
        'engines:render': lambda rt, args: {'items': [{'label': 'mobile', 'path': '/image.png', 'layout': {'overflow_count': 0}}]},
        'engines:image_read': read,
    }
    registry = {**registry, **{k: Adapter(registry[k].contract, v) for k, v in mocks.items()}}
    source = (ROOT / 'data/idioms/report_html_qa.ibl').read_text() + '\n[fn:보고서HTML검수]{원본:"/a.md",출력:"/a.html",제목:"test"}'
    plan = compile_program(source, registry)
    assert not plan.issues
    result = Runtime(plan).run()
    assert result['success'], result
    assert result['value']['reviews'][0]['ok'], result
    assert 'overflow_count' in seen[0]


def test_read_image_sends_all_tiles_in_one_call(tmp_path, monkeypatch):
    mod = load('data/packages/installed/tools/media_producer/vision_read.py', 'repair_tile_call')
    payload = image_payload(390, 7418)
    path = tmp_path / 'long.png'
    path.write_bytes(base64.b64decode(payload['base64']))
    calls = []
    def model(prompt, **kwargs):
        calls.append(kwargs)
        return '끝까지 읽음'
    monkeypatch.setattr(mod, '_ai_call', model)
    mod.read_image({'path': str(path), 'question': '읽기'}, str(tmp_path))
    assert len(calls) == 1 and len(calls[0]['images']) == 6


def test_dynamic_limit_is_checked_before_source_call(registry):
    from ibl_v2_adapters import Adapter
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    def forbidden(*args):
        pytest.fail('must reject before calling source')
    registry = {**registry, 'sense:realty': Adapter(registry['sense:realty'].contract, forbidden)}
    inputs = {'n': 60}
    plan = compile_program('[sense:realty]{source:"zigbang",region:"fixture",limit:$n}', registry, inputs)
    assert not plan.issues
    result = Runtime(plan, inputs).run()
    assert not result['success'] and '50' in result['error']


def test_join_diagnostic_supplies_argument_order():
    from ibl_v2_compile import compile_program
    issues = compile_program('return join(["a"], ",")').report()['issues']
    assert issues and all('join(Text, List<Text>)' in i['hint'] for i in issues)


def test_legacy_zigbang_limit_rejects_before_geocoding(monkeypatch):
    mod = load('data/packages/installed/tools/real-estate/tool_zigbang.py', 'repair_zigbang')
    monkeypatch.setattr(mod, '_geocode', lambda *a: pytest.fail('invalid limit must not geocode'))
    result = mod.get_zigbang_listings({'region': 'fixture', 'limit': 60})
    assert result['success'] is False and '50' in result['error']


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
