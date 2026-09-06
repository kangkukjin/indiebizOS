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
    # ★옛 검사식 r['triggers'] == r['items'] 는 agg='count' 스칼라가 *거절*되던 동안
    # None == None 으로 공허 통과했다 (2026-08-21 스칼라 count 수용이 드러냄).
    # 의도(거울 = 집계 행)를 직접 단언한다 — 표 경로 거울은 변환된 행 dict (검사 5 규약).
    check('집계 성공(스칼라 count 수용)', r.get('success', True) is not False, r.get('error'))
    check('거울도 집계행', r.get('triggers') == [{'enabled': True, 'count': 3}], r.get('triggers'))

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
    # B38-2(2026-08-25): items 봉투를 _get_table 이 먼저 흡수해 직접 병렬만 table로
    # 나가던 경로 의존을 제거했다. 단일 통화 정본대로 items 입력 join은 items를 낸다.
    check('join 정상(items→items)', len(r.get('items', [])) == 1, r)
    r = H.execute({'_prev_result': prev}, _Ctx('data_union'))
    # 형태 보존(언어 개정 2026-09-06, 1e468150): items 분기끼리의 union 은 items 를 낸다 — 표는 명시 표형 입력에만.
    check('union 정상(items→items)', len(r.get('items', [])) == 2, r)

    print('')
    print('결과: %d 통과 / %d 실패' % (_ok, _fail))
    return 1 if _fail else 0


# ─────────────────────────────────────────────────────────────────────────────
def test_battery_under_pytest():
    """pytest 가 이 배터리를 **보게 하는 다리** (2026-08-23).

    이 파일은 `check(name, cond)` 누적형 스크립트라 `def test_*` 가 없다 — 그래서
    정본 러너(pytest.ini·CI `python -m pytest -m "not local"`)가 여기서 **0건을 수집하고
    조용히 지나갔다**. 실측: 통화 거울 키 배터리가 CI 에서 한 번도 안 돌고 있었다.
    ★0건 수집은 '통과'가 아니라 '아무것도 안 봤다'이다 — 러너가 그 둘을 같은 초록으로
    보여주는 것이 거짓 초록의 뿌리다(27·28회차 상상훈련이 이 초록을 "전부 통과"로 적었다).
    본문은 모듈 레벨에서 스텁·전역을 만지므로 **별도 프로세스**로 돌린다(공유 프로세스
    오염 회피 — test_framing_amend_gate 가 모듈 스킵을 택한 것과 같은 이유의 반대편 해법).
    """
    import subprocess
    import sys as _sys
    proc = subprocess.run([_sys.executable, os.path.abspath(__file__)],
                          cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, \
        "배터리 실패 (rc=%s)\n%s" % (proc.returncode, ((proc.stdout or "") + (proc.stderr or ""))[-3000:])


# RUNNER: script-battery — 직접 실행이 배터리 전체를 돌리고 실패 시 종료코드≠0 을 낸다.
# pytest 는 이 파일을 다리 시험(별도 프로세스)으로 본다. `__main__` 을 pytest 로
# 위임하면 다리가 자기를 다시 불러 무한 재귀하므로 여기만 위임하지 않는다.
# (가드: backend/test_single_runner.py R2 — 면제는 추론이 아니라 이 선언으로만.)
if __name__ == '__main__':
    sys.exit(main())
