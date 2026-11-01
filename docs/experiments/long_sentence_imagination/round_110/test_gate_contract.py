"""격리 후보의 실제 상태 전이·차단·판본 결속 검사. 의미 판정은 모델 실험에서 본다."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('gate110', Path(__file__).with_name('five_principle_gate.py'))
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

USER = '경험을 이해해서 다음 면담 질문을 만들고 싶다.'
CANDIDATE = {'research_plan': '경험을 비교하고 미확인 내용을 다음 질문으로 잇는다.',
             'criteria': [{'text': '의미를 보존한다.'}]}


def checks(candidate, status='pass'):
    return {'checks': [{'principle': key, 'status': status,
                        'user_quote': '경험을 이해해서',
                        'evidence': [{'field': 'research_plan', 'quote': candidate['research_plan']}],
                        'reason': '확인한 연결의 근거 요약',
                        'repair': '' if status == 'pass' else '빠진 비교 조건을 명시한다.'}
                       for key in gate.PRINCIPLES]}


def run(reviews, repaired=None):
    events, calls = [], []
    def review(candidate, revision):
        calls.append(('review', revision))
        output = reviews[revision](candidate)
        return json.dumps(output, ensure_ascii=False) if isinstance(output, dict) else output
    def repair(candidate, audit):
        calls.append(('repair', audit['revision']))
        assert audit['candidate_sha256'] == gate.digest(candidate)
        return copy.deepcopy(repaired or candidate)
    def validate(candidate):
        if not isinstance(candidate, dict) or not candidate.get('research_plan'):
            raise ValueError('빈 계획')
    outcome = gate.run(CANDIDATE, [USER], review, repair, validate,
                       lambda kind, value: events.append((kind, copy.deepcopy(value))))
    return outcome, calls, events


def test_pass_keeps_input_and_avoids_repair():
    initial = copy.deepcopy(CANDIDATE)
    out, calls, events = run([checks])
    assert out['release_allowed'] and out['status'] == 'passed'
    assert calls == [('review', 0)] and not out['revisions']
    assert out['candidate'] == CANDIDATE == initial
    assert events[-1][0] == 'outcome'


def test_failure_repairs_once_and_rechecks_every_principle_on_changed_version():
    changed = {**CANDIDATE, 'research_plan': '조건을 대조하고 경험을 다음 질문으로 잇는다.'}
    out, calls, _ = run([lambda c: checks(c, 'fail'), checks], changed)
    assert calls == [('review', 0), ('repair', 0), ('review', 1)]
    assert out['release_allowed'] and out['candidate'] == changed
    assert out['audits'][0]['candidate_sha256'] != out['audits'][1]['candidate_sha256']
    assert len(out['audits'][1]['checks']) == 5
    assert not gate.releasable(changed, out['audits'][0])
    assert gate.releasable(changed, out['audits'][1])


@pytest.mark.parametrize('status', ['fail', 'uncertain'])
def test_still_not_passed_cannot_escape_by_exhausting_budget(status):
    out, calls, _ = run([lambda c: checks(c, status), lambda c: checks(c, status)])
    assert out['status'] == 'not_passed' and not out['release_allowed']
    assert calls == [('review', 0), ('repair', 0), ('review', 1)]
    assert len(out['revisions']) == 1


@pytest.mark.parametrize('mutation', [
    lambda x: x['checks'].pop(),
    lambda x: x['checks'].__setitem__(1, copy.deepcopy(x['checks'][0])),
    lambda x: x['checks'].reverse(),
    lambda x: x['checks'][0].update(status='approved'),
    lambda x: x['checks'][0].update(user_quote='사용자가 말하지 않은 목적'),
    lambda x: x['checks'][0].update(reason=''),
    lambda x: x['checks'][0].update(evidence=[]),
    lambda x: x['checks'][0]['evidence'][0].update(quote='계획에 없는 문장'),
    lambda x: x['checks'][0]['evidence'][0].update(field='criteria/0/text'),
    lambda x: x['checks'][0]['evidence'][0].update(field='criteria/99/text'),
    lambda x: x['checks'][0]['evidence'][0].update(quote=''),
    lambda x: x['checks'][0].update(status='fail', repair=''),
    lambda x: x.update(approved=True),
])
def test_invalid_attestation_is_blocked_without_extra_model_calls(mutation):
    def malformed(c):
        value = checks(c)
        mutation(value)
        return value
    out, calls, _ = run([malformed])
    assert out['status'] == 'invalid' and not out['release_allowed']
    assert calls == [('review', 0)]


def test_second_audit_must_quote_revised_plan_not_stale_plan():
    changed = {**CANDIDATE, 'research_plan': '새로 고친 질문과 자료 연결'}
    out, calls, _ = run([lambda c: checks(c, 'fail'), lambda c: checks(CANDIDATE)], changed)
    assert out['status'] == 'invalid' and not out['release_allowed']
    assert out['candidate'] == changed and len(out['audits']) == 1
    assert calls[-1] == ('review', 1)


def test_nested_field_evidence_and_fenced_json():
    def nested(c):
        value = checks(c)
        value['checks'][0]['evidence'] = [{'field': 'criteria/0/text', 'quote': '의미를 보존한다.'}]
        return '```json\n'+json.dumps(value, ensure_ascii=False)+'\n```'
    out, calls, _ = run([nested])
    assert out['release_allowed'] and len(calls) == 1


def test_bad_repaired_plan_never_reaches_recheck_or_release():
    out, calls, _ = run([lambda c: checks(c, 'fail')], {'research_plan': ''})
    assert out['status'] == 'repair_failed' and not out['release_allowed']
    assert calls == [('review', 0), ('repair', 0)]
    assert out['candidate'] == CANDIDATE


def test_native_review_error_is_recorded_not_passed():
    def error(c):
        raise RuntimeError('서비스 실패')
    out, calls, _ = run([error])
    assert out['status'] == 'invalid' and not out['release_allowed']
    assert out['error'] == '서비스 실패'


def test_valid_all_pass_is_not_a_semantic_correctness_proof():
    # 정확한 인용과 이유 문자열만으로 의미의 참을 기계가 판정할 수는 없다.
    def dubious(c):
        value = checks(c)
        for row in value['checks']:
            row['reason'] = '이 판정 이유가 타당한지는 별도 의미 검토가 필요하다.'
        return value
    out, _, _ = run([dubious])
    assert out['release_allowed']
