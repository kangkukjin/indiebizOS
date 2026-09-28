"""Coverage of model-visible candidates, actionable omissions and HTML body regions."""
import copy
import json
from pathlib import Path

import boot_paths  # noqa: F401
import pytest
from common.pkg_utils import load_sibling
from model_result_view import project_v2_result, read_result, resolve_input_refs
from model_value_preview import preview_value
from test_ibl_general_capabilities import boundary  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'data/packages/installed/tools/web/tool_webcrawl.py'


def candidates():
    return [{'id': i, 'title': f'Candidate {i}', **{f'field{j}': j for j in range(14)},
             'start_date': '2026-09-28', 'end_date': '2026-10-15',
             'description': 'Long detail. ' * 150} for i in range(11)]


def test_all_candidates_and_late_dates_survive_budget(boundary):
    rows = candidates()
    raw = {'edition': 2, 'success': True, 'source_complete': True,
           'value': [{'items': rows, 'count': len(rows)}]}
    before = copy.deepcopy(raw)
    shown = project_v2_result(raw)
    items = shown['value'][0]['items']
    assert len(items) == 11
    assert items[6]['title'] == 'Candidate 6'
    assert all(r['start_date'] == '2026-09-28' and r['end_date'] == '2026-10-15' for r in items)
    assert shown['_preview']['scope'] == 'display'
    assert raw == before
    values, _ = resolve_input_refs(shown['result_ref']['input_args'])
    assert values['입력'] == raw['value']
    change = shown['_preview']['changes'][0]
    page = read_result(change['read_args'])
    # 문자열 경로는 원문 글자 페이지(69회차 F69-2)
    assert page['read_scope']['format'] == 'text' and page['text'] == rows[0]['description']


def test_small_values_survive_large_evidence_without_false_preview(boundary):
    raw = {'edition': 2, 'success': True, 'value': list(range(20)),
           'source_complete': True, 'evidence': [{'detail': 'x' * 20000}]}
    shown = project_v2_result(raw)
    assert shown['value'] == list(range(20))
    assert '_preview' not in shown


def test_large_list_reports_missing_rows_and_readable_path(boundary):
    raw = {'edition': 2, 'success': True, 'source_complete': True,
           'value': {'rows': [{'title': f'Item {i}', 'date': '2026-09-28'} for i in range(10000)]}}
    shown = project_v2_result(raw)
    note = next(n for n in shown['_preview']['changes'] if n['kind'] == 'list')
    assert note['total'] == 10000 and note['shown'] == len(shown['value']['rows'])
    assert note['path'] == ['value', 'rows']
    assert shown['source_complete'] is True
    args = note['read_args']
    restored, _ = resolve_input_refs({'rows': {'$ref': args['id'], 'path': args['path']}})
    assert len(restored['rows']) == 10000
    assert len(json.dumps(shown, ensure_ascii=False)) < 24000
    from ibl_envelope import display_delivery_budget
    text = json.dumps(shown, ensure_ascii=False)
    assert display_delivery_budget(text, 100) >= len(text)


def test_deep_and_wide_values_expose_omissions_without_changing_failure(boundary):
    value = 'x' * 50000
    for _ in range(14):
        value = {'nested': value}
    raw = {'edition': 2, 'success': False, 'source_complete': False,
           'diagnostic': {'code': 'TOOL', 'message': 'failed'}, 'value': value}
    shown = project_v2_result(raw)
    assert shown['diagnostic'] == raw['diagnostic'] and not shown['success']
    assert not shown['source_complete']
    assert any(n['kind'] == 'depth' for n in shown['_preview']['changes'])
    wide = {f'field{i}': 'a' * 100 for i in range(3000)}
    view, meta = preview_value(wide, 2000, 'ref')
    assert len(view) < len(wide)
    assert meta['changes'][0]['kind'] == 'record'
    assert meta['changes_omitted'] > 0


@pytest.mark.parametrize('wrapper', ['main', 'article', 'div role="main"',
                                    'div itemprop="articleBody"', 'div class="entry-content"',
                                    'div class="ck-content"', 'div class="se-main-container"'])
def test_declared_body_removes_surrounding_menu_but_preserves_event_facts(wrapper):
    module = load_sibling(WEB, 'tool_webcrawl')
    close = wrapper.split()[0]
    html = f'''<html><title>Notice</title><body><div>LOGIN MENU</div><{wrapper}>
    <header><h1>Exhibition</h1><p>28 September</p></header>
    <table><tr><td>Hours</td><td>11–20</td></tr></table>
    <figure><figcaption>Image caption</figcaption></figure>
    <div role="navigation">SUBMENU</div><p hidden>HIDDEN</p><p>Admission free</p>
    </{close}><div>OTHER FOOTER</div></body></html>'''
    title, text = module._parse_html(html, 'https://fixture.test/notice')
    assert title == 'Notice'
    assert all(s in text for s in ['Exhibition', '28 September', 'Hours', '11–20', 'Image caption', 'Admission free'])
    assert all(s not in text for s in ['LOGIN MENU', 'SUBMENU', 'HIDDEN', 'OTHER FOOTER'])


def test_multiple_articles_and_unmarked_body_are_not_silently_lost():
    module = load_sibling(WEB, 'tool_webcrawl')
    _, text = module._parse_html('<body><article>First</article><article>Second</article></body>', 'https://fixture.test')
    assert 'First' in text and 'Second' in text
    _, text = module._parse_html('<body><header>Important title</header><div>Unknown structure</div></body>', 'https://fixture.test')
    assert 'Important title' in text and 'Unknown structure' in text


def test_reading_scope_is_exposed_and_html_kept():
    module = load_sibling(WEB, 'webcrawl_structure')
    html = '<body>Menu<div class="ck-content"><p>Notice</p></div></body>'
    structure = module.extract(html, 'https://fixture.test')
    out = module.project({'success': True, 'text': 'Notice', '_page_structure': structure}, 'content')
    assert out['content_selection'][0]['scope'] == 'declared_content'
    assert structure['documents'][0]['html'] == html
    assert '_page_structure' not in out


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
