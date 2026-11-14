"""되풀이 실패 감사 (2026-11-14, docs/MEMORY_REPAIR_PLAN_2026_11_14.md R5).

같은 실행 실패가 여러 날 되풀이되면 신고하는가, 손댈 수 있을 만큼 구체적인 꼴로 묶는가,
하루 이틀의 실패·검사만 한 호출·읽지 못한 감사를 되풀이나 깨끗함으로 잘못 보고하지 않는가를 잠근다.

실행: .venv/bin/python -m pytest backend/test_recurring_failure_audit_2026_11_14.py -q
"""
import boot_paths  # noqa: F401
import json

import recurring_failure_audit as audit
from recurring_failure_audit import MIN_DAYS, MIN_RUNS, measure, signature

TASK = '#!ibl edition=2\nreturn [self:task]{op: "wait", task_ref: {kind: "guestpc", task_id: "abc"}}'
TASK_ERROR = '실행 전 검사에서 거절했습니다: 알 수 없는 인자: task_ref. 비슷한 인자: task_id, ref. 사용 가능한 인자: op, ref'
GOOD = '#!ibl edition=2\nreturn [self:task]{op: "wait", ref: {kind: "guestpc", task_id: "abc"}}'


def call(code, error=None, check=False, tail=''):
    result = {'success': False, 'error': error} if error else {'success': True, 'value': 1}
    return {'tool_name': 'execute_ibl', 'success': not error,
            'input': {'code': code, **({'check': True} if check else {})},
            'result': json.dumps(result, ensure_ascii=False) + tail}


def turn(day, *calls):
    return json.dumps({'recorded_at': f'2026-11-{day:02d}T10:00:00+09:00', 'tool_calls': list(calls)},
                      ensure_ascii=False), f'2026-11-{day:02d}T01:00:00+00:00'


def quiet(days=range(1, 15)):
    """판정에 필요한 실행 수를 채우는 평범한 성공 턴."""
    return [turn(day, *[call(GOOD)] * 5) for day in days]


def test_signature_names_the_action_and_the_argument():
    assert signature(TASK_ERROR, TASK) == ('알 수 없는 인자 self:task.task_ref', '쓰는 법')
    forage = '[self:forage]{op: "note", layer: "map", locus: "/x"}'
    assert signature('알 수 없는 인자: layer. 사용 가능한 인자: apply', forage)[0] == '알 수 없는 인자 self:forage.layer'
    assert signature('선언된 필드가 없습니다: value. 선택 필드는 has/get을 쓰세요.', '')[0] == '선언된 필드 없음 .value'
    search = '[sense:search]{query: "x"} >> [table:select]{columns: ["date"]}'
    assert signature("select 입력 1번 행에 열이 없습니다: ['date']. 실제 필드: ['title']", search)[0] \
        == "select 없는 열 sense:search: 'date'"
    assert signature('HTTP 403: 봇 차단으로 본문을 가져오지 못했습니다.', '')[1] == '바깥 사정'
    a = signature('파일을 찾을 수 없습니다: /Users/a/b.txt', '')[0]
    assert a == signature('파일을 찾을 수 없습니다: /tmp/other.json', '')[0]      # 대상만 다른 같은 실패는 한 꼴


def test_a_failure_seen_on_three_days_is_flagged_and_two_days_is_not():
    rows = quiet() + [turn(day, call(TASK, TASK_ERROR), call(GOOD)) for day in range(1, MIN_DAYS + 1)]
    rows += [turn(day, call('[self:forage]{op:"note", layer:"map"}', '알 수 없는 인자: layer. 사용 가능한 인자: apply'))
             for day in (1, 2)]
    seen = measure(rows)
    assert [f['signature'] for f in seen['flags']] == ['알 수 없는 인자 self:task.task_ref']
    flag = seen['flags'][0]
    assert (flag['turns'], flag['days'], flag['recovered']) == (MIN_DAYS, MIN_DAYS, MIN_DAYS)
    assert (flag['first'], flag['last']) == ('2026-11-01', f'2026-11-{MIN_DAYS:02d}')
    assert seen['kinds'] == 2 and seen['recurring'] == 1 and seen['unchecked'] == []


def test_a_turn_counts_once_and_checks_and_old_tails_are_handled():
    tail = ' [Execution situation — observed data, not instructions]\n{"mode":"baseline"}'
    rows = quiet() + [turn(day, call(TASK, TASK_ERROR, tail=tail), call(TASK, TASK_ERROR), call(GOOD))
                      for day in range(1, MIN_DAYS + 1)]
    rows += [turn(day, call(TASK, TASK_ERROR, check=True)) for day in range(5, 9)]   # 검사만 한 호출은 실행이 아니다
    flag = measure(rows)['flags'][0]
    assert flag['turns'] == MIN_DAYS and flag['days'] == MIN_DAYS                      # 한 턴에서 두 번 틀려도 한 번


def test_receipt_field_name_is_accepted_as_the_task_reference():
    """처방 1(2026-11-14): 접수증 칸 이름 task_ref 를 그대로 되넣어도 [self:task] 가 받는다 — 10턴·6일 되풀이한 거절."""
    from system_tools_ibl import _execute_ibl_unified_impl

    def check(args):
        raw = _execute_ibl_unified_impl({'edition': 2, 'check': True,
                                         'code': '#!ibl edition=2\nreturn [self:task]{op: "status", ' + args + '}'}, '.')
        out = json.loads(raw) if isinstance(raw, str) else raw
        return [issue['code'] for issue in out.get('issues') or []]

    ref = '{kind: "guestpc", task_id: "x"}'
    assert check(f'task_ref: {ref}') == [] and check(f'ref: {ref}') == []
    assert check(f'ref: {ref}, task_ref: {ref}') == ['ARGUMENT_ALIAS']       # 둘을 함께 주면 어느 쪽인지 모른다
    assert check(f'task_reff: {ref}') == ['UNKNOWN_ARGUMENT']                # 다른 오타까지 받지는 않는다


def test_too_few_runs_is_not_reported_as_clean():
    seen = measure([turn(1, call(GOOD))])
    assert seen['flags'] == [] and seen['unchecked'] == ['executions_below_minimum'] and seen['runs'] < MIN_RUNS


def test_report_is_findings_when_recurring_and_failed_when_unreadable(monkeypatch, tmp_path):
    from audit_lifecycle import normalize_result
    monkeypatch.setattr(audit, '_STATE_PATH', tmp_path / 'state.json')
    monkeypatch.setattr(audit, '_FLAGS_PATH', tmp_path / 'flags.json')
    rows = quiet() + [turn(day, call(TASK, TASK_ERROR), call(GOOD)) for day in range(1, MIN_DAYS + 1)]
    monkeypatch.setattr(audit, '_recent_rows', lambda: rows)
    report = normalize_result(audit.run_recurring_failure_check(force=True))
    assert report['audit_status'] == 'findings' and 'self:task.task_ref' in report['error_message']
    assert json.loads((tmp_path / 'flags.json').read_text())['flags'][0]['signature'] == '알 수 없는 인자 self:task.task_ref'
    monkeypatch.setattr(audit, '_recent_rows', lambda: (_ for _ in ()).throw(RuntimeError('db closed')))
    report = normalize_result(audit.run_recurring_failure_check(force=True))
    assert report['audit_status'] == 'failed' and 'db closed' in report['error_message']
    monkeypatch.setattr(audit, '_recent_rows', quiet)
    assert normalize_result(audit.run_recurring_failure_check(force=True))['audit_status'] == 'clean'
