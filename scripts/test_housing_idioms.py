"""실제 IBL 실행기로 부동산 관용구의 단위·빈값·부분 실패·비파괴 계약 검사."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
import pytest
from ibl_v2_adapters import Adapter, load_registry
from ibl_v2_compile import compile_program
from ibl_v2_ir import Fault
from ibl_v2_runtime import Runtime


def run(file, call, inputs, adapters=None):
    registry = load_registry()
    for key, fn in (adapters or {}).items():
        registry[key] = Adapter(registry[key].contract, fn)
    source = (ROOT / 'data/idioms' / file).read_text() + '\n' + call
    plan = compile_program(source, registry, inputs)
    assert not plan.issues, plan.report()
    return Runtime(plan, inputs).run()


def filter_rows(rows, source='naver', low=20000, high=40000):
    out = run('housing_filter.ibl',
              '[fn:전세예산추리기]{목록:$rows,출처:$source,하한만원:$low,상한만원:$high}',
              dict(rows=rows, source=source, low=low, high=high))
    assert out['success'], out
    return out['value']


def test_naver_band_boundaries_monthly_missing_and_original_preserved():
    rows = [dict(meta='전세 2억', price=p, url=str(p), title='원문')
            for p in [199990000, 200000000, 400000000, 400010000]]
    rows += [dict(meta='월세 2억/50', price=200000000, url='monthly'),
             dict(meta='전세 가격 미확인', url='unknown'),
             dict(meta='전세 3억', price=300000000, url=None)]
    result = filter_rows(rows)
    assert [r['deposit_man'] for r in result['items']] == [20000, 40000]
    assert result['items'][0]['original'] == rows[1]
    assert result['outside_budget'] == 2 and result['other_deal'] == 1
    assert len(result['review']) == 2 and result['ok'] is False
    assert result['input_count'] == 7


def test_zigbang_manwon_and_contradictory_monthly():
    rows = [dict(meta='전세 2억', deposit=20000, rent=0, url='a'),
            dict(meta='전세 4억', deposit=40000, rent=0, url='b'),
            dict(meta='전세 잘못된 표기', deposit=30000, rent=50, url='c'),
            dict(meta='전세 1.9억', deposit=19000, rent=0, url='d')]
    out = filter_rows(rows, 'zigbang')
    assert [r['deposit_man'] for r in out['items']] == [20000, 40000]
    assert len(out['review']) == 1 and out['outside_budget'] == 1


def test_filter_empty_and_invalid_budget_are_distinct():
    assert filter_rows([])['ok'] is True
    assert filter_rows([], low=40000, high=20000)['ok'] is False
    assert filter_rows([], source='molit')['ok'] is False


def test_collection_preserves_empty_failure_and_all_five_requests():
    seen = []

    def realty(rt, args):
        seen.append(args)
        if args['source'] == 'zigbang':
            raise Fault('TOOL_ERROR', '직방 장애', kind='tool', partial={'items': [{'url': 'partial'}]})
        return {'items': [], 'source': args['source'], '조회지역': 'fixture'}

    out = run('housing_collect.ibl',
              '[fn:부동산기본수집]{지역:"테스트동",법정동코드:"11110",예산:$budget,기간:$period}',
              {'budget': {'jeonse_min': 20000, 'jeonse_max': 40000},
               'period': {'start_month': '202601', 'end_month': '202603'}},
              {'sense:realty': realty})
    assert out['success'], out
    value = out['value']
    assert len(seen) == 5 and value['failed'] == 1 and not value['ok']
    assert len(value['items']) == 5
    assert value['items'][0]['ok'] and value['items'][0]['count'] == 0
    assert value['items'][2]['error']['message'] == '직방 장애'
    assert value['items'][2]['error']['partial']['items'][0]['url'] == 'partial'
    assert all(r['deposit_min'] == 20000 and r['limit'] == 60
               for r in seen if r['source'] == 'naver')
    assert all(r['start_month'] == '202601' and r['region_code'] == '11110'
               for r in seen if r['source'] == 'molit')


def test_preparation_reads_full_latest_and_marks_required_failure():
    seen = []

    def listing(rt, args):
        if args['pattern'] == 'housing_report_*.md':
            return [{'name': 'housing_report_2026-09-01_a.md', 'path': '/a', 'is_dir': False},
                    {'name': 'housing_report_2026-09-24_b.md', 'path': '/b', 'is_dir': False}]
        return []

    def read(rt, args):
        seen.append(args)
        if args['path'].endswith('_report_config.json'):
            raise Fault('TOOL_ERROR', '설정 없음', kind='tool')
        return {'text': args['path'], 'blocks': [], 'data': {}}

    out = run('housing_prepare.ibl', '[fn:부동산준비읽기]{폴더:"/fixture",슬러그:"new_region"}',
              {}, {'self:list': listing, 'self:read': read})
    assert out['success'], out
    value = out['value']
    assert not value['ok'] and value['failed'] == 1
    assert value['previous_found'] and not value['region_found']
    assert next(d for d in value['documents'] if d['kind'] == 'previous')['path'] == '/b'
    assert all('limit' not in args for args in seen)


def test_revisit_does_not_turn_search_absence_into_gone_or_restore_rejected():
    old = [{'id': key, 'price': 100, 'status': 'rejected' if key == 'r' else 'active'}
           for key in ['same', 'changed', 'missing', 'r', 'duplicate']]
    current = [{'id': key, 'price': price} for key, price in
               [('same', 100), ('changed', 110), ('r', 90), ('new', 100),
                ('duplicate', 80), ('duplicate', 90)]]
    out = run('housing_compare.ibl', '[fn:매물재방문비교]{기존:$old,현재:$current}',
              {'old': old, 'current': current})
    assert out['success'], out
    states = {r['id']: r['status'] for r in out['value']['items']}
    assert states == dict(same='unchanged', changed='changed', missing='needs_recheck',
                          r='rejected', duplicate='conflict', new='new')
    assert old[2]['status'] == 'active'


def test_seeds_match_sources_and_do_not_promote():
    import json
    seeds = json.loads((ROOT / 'data/idioms/housing_seeds.json').read_text())
    names = {'부동산준비읽기': 'housing_prepare.ibl', '부동산기본수집': 'housing_collect.ibl',
             '전세예산추리기': 'housing_filter.ibl', '매물재방문비교': 'housing_compare.ibl'}
    for seed in seeds:
        assert not seed.get('always_on', False)
        if seed.get('alias'):
            assert seed['ibl_code'] == (ROOT / 'data/idioms' / names[seed['alias']]).read_text().strip()


def test_guide_collection_example_runs_with_partial_failure():
    import json
    import re
    guide = (ROOT / 'data/guides/housing_report.md').read_text()
    seeds = json.loads((ROOT / 'data/idioms/housing_seeds.json').read_text())
    library = {s['alias']: s['ibl_code'] for s in seeds if s.get('alias')}
    registry = load_registry()

    def realty(rt, args):
        if args['source'] == 'zigbang':
            raise Fault('TOOL_ERROR', 'fixture failure', kind='tool')
        if args['source'] == 'naver':
            return {'items': [{'meta': '전세 3억', 'price': 300000000, 'url': 'fixture'}]}
        return {'items': []}

    registry['sense:realty'] = Adapter(registry['sense:realty'].contract, realty)
    for code in re.findall(r'```ibl\n(.*?)```', guide, re.S):
        plan = compile_program(code, registry, definitions=library)
        assert not plan.issues, plan.report()
        if '부동산기본수집' in code:
            out = Runtime(plan, {}).run()
            assert out['success'], out
            assert out['value']['collection']['failed'] == 1
            assert len(out['value']['candidates']) == 2
            assert all(r['result']['items'][0]['deposit_man'] == 30000
                       for r in out['value']['candidates'])


def test_empty_revisit_lists():
    out = run('housing_compare.ibl', '[fn:매물재방문비교]{기존:[],현재:[]}', {})
    assert out['success'], out
    assert out['value']['items'] == []


def test_invalid_collection_budget_does_not_query():
    def unexpected(rt, args):
        pytest.fail('잘못된 예산으로 원천 조회')

    out = run('housing_collect.ibl',
              '[fn:부동산기본수집]{지역:"fixture",법정동코드:"11110",예산:{jeonse_min:40000,jeonse_max:20000},기간:{start_month:"202601",end_month:"202603"}}',
              {}, {'sense:realty': unexpected})
    assert out['success'] and not out['value']['ok']
