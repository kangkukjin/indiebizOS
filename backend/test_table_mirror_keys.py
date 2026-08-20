# -*- coding: utf-8 -*-
'''거울 키 재투영 배터리 — B15-1 (2026-08-20 상상훈련 15회차).

증상: [self:trigger]{op:'list'} >> [table:take]{n:1} 이 items 는 1건으로 줄이면서
도메인 이름으로 병기된 거울 키(triggers)에는 전 건을 남겨, 읽는 쪽에는
'take(1) 했는데 전 건이 나온다'로 보였다. 변환자는 일했고 봉투가 거짓말을 했다.
('비-통화 입력을 조용히 통과시킨다'는 첫 진단은 라이브 재현으로 반증됨 — take 는
 items 를 정확히 잘랐고, sense:host 대조군은 그대로 정직 거절이었다.)

수리 자리: data-ops handler 의 _reproject_mirrors (_emit_items/_emit_table 병목).
실행: .venv/bin/python backend/test_table_mirror_keys.py
'''
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'backend'))
HANDLER = os.path.join(ROOT, 'data', 'packages', 'installed', 'tools', 'data-ops', 'handler.py')
_spec = importlib.util.spec_from_file_location('dataops_handler', HANDLER)
H = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(H)

_ok = 0
_fail = 0


def check(name, cond, extra=''):
    global _ok, _fail
    if cond:
        _ok += 1
        print('  PASS ' + name)
    else:
        _fail += 1
        print('  FAIL ' + name + '  ' + str(extra))


class _Ctx:
    def __init__(self, tool):
        self.tool_name = tool

    def output_dir(self):
        return '/tmp'


def run(tool, prev, **params):
    p = dict(params)
    p['_prev_result'] = json.dumps(prev, ensure_ascii=False)
    return H.execute(p, _Ctx(tool))


def trig_env():
    '''trigger_engine.list_triggers 의 실제 모양 — items 와 triggers 가 같은 리스트.'''
    trig = [{'id': 't%d' % i, 'name': 'n%d' % i, 'enabled': True} for i in range(3)]
    sched = [{'id': 'e1'}, {'id': 'e2'}]
    return {'triggers': trig, 'items': trig, 'count': 3,
            'existing_schedules': sched, 'existing_count': 2}


def main():
    print('== 1. 거울 키 재투영 (take) ==')
    r = run('data_take', trig_env(), n=1)
    check('items 1건', len(r['items']) == 1, r.get('items'))
    check('거울 키 triggers 도 1건', len(r['triggers']) == 1, r.get('triggers'))
    check('_mirrored 표식', r.get('_mirrored') == ['triggers'], r.get('_mirrored'))
    check('종류 다른 형제 원장 보존', len(r['existing_schedules']) == 2)
    check('existing_count 불변', r['existing_count'] == 2)
    check('형제 원장은 자백 대상', r.get('_untransformed') == ['existing_schedules'],
          r.get('_untransformed'))

    print('== 1-2. 파생 원천 자백 (others:agents 의 projects) ==')
    # items 는 projects 트리를 펼쳐 만든 것이라 평평한 items 로 되돌릴 수 없다.
    # 드롭도 재투영도 아닌 자백 — 읽는 쪽의 오독만 막고 데이터는 하나도 안 버린다.
    env = {'items': [{'project': 'a', 'id': 'x'}, {'project': 'b', 'id': 'y'}],
           'projects': [{'project_id': 'a', 'agents': []}, {'project_id': 'b', 'agents': []}],
           'total_agents': 2}
    r = run('data_take', env, n=1)
    check('projects 자백', r.get('_untransformed') == ['projects'], r.get('_untransformed'))
    check('projects 원본 보존(드롭 아님)', len(r['projects']) == 2)
    check('거울 아님(_mirrored 없음)', '_mirrored' not in r, r.get('_mirrored'))

    print('== 1-3. 자백 잡음 억제 ==')
    r = run('data_take', {'items': [{'a': 1}, {'b': 2}], 'tags': ['x', 'y'], 'empty': []}, n=1)
    check('스칼라·빈 리스트는 자백 안 함', '_untransformed' not in r, r.get('_untransformed'))

    print('== 2. filter 전멸 ==')
    r = run('data_filter', trig_env(), where='절대없는문자열ZZZ')
    check('items 0건', r['items'] == [])
    check('거울 키도 0건', r['triggers'] == [], r.get('triggers'))

    print('== 3. 복사본 병기(값 동등 폴백) ==')
    trig = [{'id': 'a'}, {'id': 'b'}]
    r = run('data_take', {'items': trig, 'switches': list(trig), 'count': 2}, n=1)
    check('복사본 거울도 잡힘', len(r['switches']) == 1, r.get('switches'))

    print('== 4. 무관 리스트 오폭 없음 ==')
    env = {'items': [{'id': 'a'}, {'id': 'b'}], 'unrelated': [{'z': 1}],
           'empty': [], 'tags': ['x']}
    r = run('data_take', env, n=1)
    check('무관 dict 리스트 보존', r['unrelated'] == [{'z': 1}], r.get('unrelated'))
    check('빈 리스트 보존', r['empty'] == [], r.get('empty'))
    check('스칼라 리스트 보존', r['tags'] == ['x'], r.get('tags'))
    check('_mirrored 없음', '_mirrored' not in r, r.get('_mirrored'))

    print('== 5. 전 단항 변환자 (items 경로·table 경로) ==')
    for tool, params in (('data_sort', {'by': 'name'}),
                         ('data_select', {'columns': ['name']}),
                         ('data_dedup', {'by': 'name'}),
                         ('data_rename', {'map': {'name': 'nm'}})):
        r = run(tool, trig_env(), **params)
        n_cur = len(r['items']) if isinstance(r.get('items'), list) else len(r.get('rows', []))
        check(tool + ': 거울 길이 == 통화 길이',
              isinstance(r.get('triggers'), list) and len(r['triggers']) == n_cur,
              str(len(r.get('triggers', []))) + ' vs ' + str(n_cur))
        check(tool + ': 형제 원장 보존', len(r.get('existing_schedules', [])) == 2)
    r = run('data_select', trig_env(), columns=['name'])
    check('table 경로 거울은 변환된 행 dict',
          r.get('triggers') == [{'name': 'n0'}, {'name': 'n1'}, {'name': 'n2'}], r.get('triggers'))

    print('== 6. groupby (행 모양이 바뀌는 변환) ==')
    r = run('data_groupby', trig_env(), by='enabled', agg='count')
    check('거울도 집계행', r.get('triggers') == r.get('items'), r.get('triggers'))

    print('== 7. 순수 table 통화 회귀 ==')
    r = run('data_take', {'columns': ['k', 'v'], 'rows': [['a', 1], ['b', 2], ['c', 3]]}, n=1)
    check('표 rows 1건', len(r.get('rows', [])) == 1, r.get('rows'))
    check('_mirrored 없음', '_mirrored' not in r, r.get('_mirrored'))

    print('== 8. 비-통화 정직 거절 회귀 (대조군 sense:host resources) ==')
    host = {'success': True, 'battery': None, 'cpu': {}, 'disks': [{'free_gb': 10}], 'memory': {}}
    r = run('data_take', host, n=2)
    check('정직 거절 유지',
          r.get('success') is False and 'items 통화를 찾지 못했' in r.get('error', ''), r)

    print('== 9. 통짜 리스트 입력(봉투 없음) ==')
    r = run('data_take', [{'id': 'a'}, {'id': 'b'}], n=1)
    check('리스트 입력 정상', len(r['items']) == 1 and '_mirrored' not in r, r)

    print('== 10. 이항 변환자 회귀 ==')
    a = json.dumps({'items': [{'k': 'x', 'v': 1}]}, ensure_ascii=False)
    b = json.dumps({'items': [{'k': 'x', 'w': 2}]}, ensure_ascii=False)
    prev = json.dumps([a, b], ensure_ascii=False)
    r = H.execute({'_prev_result': prev, 'on': 'k'}, _Ctx('data_join'))
    check('join 정상', len(r.get('table', {}).get('rows', [])) == 1, r)
    r = H.execute({'_prev_result': prev}, _Ctx('data_union'))
    check('union 정상', len(r.get('table', {}).get('rows', [])) == 2, r)

    print('')
    print('결과: %d 통과 / %d 실패' % (_ok, _fail))
    return 1 if _fail else 0


if __name__ == '__main__':
    sys.exit(main())
