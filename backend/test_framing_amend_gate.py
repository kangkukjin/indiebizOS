# -*- coding: utf-8 -*-
'''fit 게이트 3값(amended_framing) + 결정론 가드 배터리 (2026-08-20).

왜 있나: framing 재사용 게이트의 반환이 {fits, criteria} 이진이라, 같은 태스크가
커졌을 때(판정 -> 적용) criteria 만 새로 뽑히고 task_framing 은 첫 판 그대로였다.
옛 지도로 새 땅을 걷는 상태가 구조적으로 만들어진다.

가드는 둘 다 결정론이다 — 의미 검사('핵심어가 남았나')를 가드에 넣으면 가드가
막으려는 병(경량 모델의 의미 오판)을 가드 안에 다시 들인다:
  _AMEND_MIN_LEN   길이 하한 미만이면 무시
  _AMEND_CHAIN_MAX 연속 고쳐쓰기 상한 — 넘으면 재사용 포기·의식 재각성
                   (누적 드리프트로 지도의 저작권이 조용히 경량 모델로 넘어가는 것 차단)

실행: .venv/bin/python backend/test_framing_amend_gate.py
'''
import importlib.util
import os
import sys
import types

# ★스크립트형 테스트(def test_* 없음·모듈 레벨에서 sys.modules 스텁 설치) — pytest 아래서는
# 수집이 임포트만 해도 스텁이 공유 프로세스에 남아, 뒤에 도는 다른 파일들이 가짜
# thread_context/consciousness_agent 를 물려받아 죽는다(2026-08-20 실측: test_steer·
# test_ibl_silent_failures AttributeError — 모듈 그림자 부류). 스텁 설치 *이전에* 스킵.
if __name__ != '__main__':
    import pytest
    pytest.skip('로컬 전용 스크립트 테스트 — .venv/bin/python backend/test_framing_amend_gate.py 로 직접 실행',
                allow_module_level=True)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, 'backend', 'cognition', 'cognitive_consciousness.py')

# 형제 모듈 스텁 — 인지층 전체를 켜지 않고 이 파일의 판단만 시험한다.
_tc = types.ModuleType('thread_context')
_tc.get_current_registry_key = lambda: 'K'
sys.modules['thread_context'] = _tc
_ca = types.ModuleType('consciousness_agent')
_ca.oneshot_ai_call = lambda *a, **k: None
sys.modules['consciousness_agent'] = _ca

_spec = importlib.util.spec_from_file_location('cc_under_test', TARGET)
CC = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CC)

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


class _Agent(CC.CognitiveConsciousnessMixin):
    def __init__(self, gate):
        self._gate = gate
        self.logs = []
        self.full_called = 0

    def _log(self, m):
        self.logs.append(m)

    def _consciousness_fit_gate(self, msg, prev):
        return self._gate

    def _run_consciousness(self, msg, hist, mem=''):
        self.full_called += 1
        return {'task_framing': '새 지도(의식)', 'achievement_criteria': '새 기준'}


BASE = {'task_framing': '원래 지도 — 4개 피드백을 판정하라(코드 수정 금지)',
        'achievement_criteria': '옛 기준'}


def drive(gate, prev):
    CC._FRAMING_CACHE.clear()
    CC.framing_cache_set('K', dict(prev))
    a = _Agent(gate)
    out = a._run_consciousness_or_reuse('새 메시지', ['h'], '')
    return a, out, CC.framing_cache_get('K')


def main():
    print('== 1. amend 정상 ==')
    g = {'fits': True, 'criteria': '새 기준',
         'amended_framing': '고쳐 쓴 지도 — 판정을 넘어 P0부터 실제로 수리한다'}
    a, out, cached = drive(g, BASE)
    check('task_framing 교체', out['task_framing'] == g['amended_framing'], out['task_framing'])
    check('_amend_count 1', out.get('_amend_count') == 1, out.get('_amend_count'))
    check('원본 보존(_framing_origin)', out.get('_framing_origin') == BASE['task_framing'])
    check('재고에도 반영', cached['task_framing'] == g['amended_framing'])
    check('의식 미호출(비용 불변)', a.full_called == 0)

    print('== 2. 길이 하한 미달 -> 무시 ==')
    a, out, cached = drive({'fits': True, 'amended_framing': '짧다', 'criteria': '새 기준'}, BASE)
    check('framing 불변', out['task_framing'] == BASE['task_framing'], out['task_framing'])
    check('_amend_count 안 오름', out.get('_amend_count') is None, out.get('_amend_count'))
    check('criteria 는 갱신', out['achievement_criteria'] == '새 기준')
    check('하한 로그', any('하한 미달' in m for m in a.logs), a.logs)

    print('== 3. amend 사슬 상한 -> 의식 재각성(래칫) ==')
    prev = dict(BASE)
    prev['_amend_count'] = CC._AMEND_CHAIN_MAX
    g = {'fits': True, 'criteria': 'c',
         'amended_framing': '또 고쳐 쓴 지도 — 범위가 다시 늘었다고 주장한다'}
    a, out, cached = drive(g, prev)
    check('의식 1회 호출', a.full_called == 1)
    check('새 지도로 대체', out['task_framing'] == '새 지도(의식)', out['task_framing'])
    check('재고 카운터 리셋', (cached or {}).get('_amend_count') is None)
    check('상한 로그', any('사슬 상한' in m for m in a.logs), a.logs)

    print('== 4. 상한이어도 amend 없으면 재사용 유지 ==')
    prev = dict(BASE)
    prev['_amend_count'] = 5
    a, out, cached = drive({'fits': True, 'amended_framing': '', 'criteria': 'c2'}, prev)
    check('순수 재사용은 드리프트 아님',
          a.full_called == 0 and out['task_framing'] == BASE['task_framing'])

    print('== 5. fits=false 회귀 ==')
    a, out, cached = drive({'fits': False, 'amended_framing': '', 'criteria': ''}, BASE)
    check('의식 호출', a.full_called == 1 and out['task_framing'] == '새 지도(의식)')

    print('== 6. 게이트 실패(None) 폴백 회귀 ==')
    a, out, cached = drive(None, BASE)
    check('풀 의식 폴백', a.full_called == 1)

    print('')
    print('결과: %d 통과 / %d 실패' % (_ok, _fail))
    return 1 if _fail else 0


if __name__ == '__main__':
    sys.exit(main())
