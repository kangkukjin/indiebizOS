"""경험 증류의 '턴의 길' (2026-11-14, docs/MEMORY_REPAIR_PLAN_2026_11_14.md R4).

재현한 결함: 실패한 뒤 성공한 275턴 가운데 실행기억이 저장된 턴은 10개였고, 저장된 것도 마지막 코드뿐이라
"무엇이 왜 안 됐고 무엇을 찾아봤더니 풀렸는가"가 남지 않았다. 여기서는
  ① 프로그램이 사실만 모으는가(호출 순서·오류 머리·조회 단계, 곧장 성공한 턴은 입력을 늘리지 않음)
  ② 판단이 고른 길이 근거 안의 단계일 때만 저장되는가
  ③ 이미 아는 원문이면 새 행 없이 그 용례에 덧붙는가
  ④ 회상에 날짜와 함께 보이는가
를 잠근다.

실행: .venv/bin/python -m pytest backend/test_distill_route_2026_11_14.py -q
"""
import boot_paths  # noqa: F401
import json

import pytest

from distill_route import MAX_ROUTES, MAX_STEPS, attach_route, build_route, turn_path
from test_time_selection import db  # noqa: F401

CODE = '#!ibl edition=2\nreturn [sense:restaurant]{query: "청주 맛집"}'
OK = {'success': True, 'executed': True, 'source_complete': True, 'value': {'items': [{'name': '경주집'}]}}


def run(code=CODE, ok=True, error='', check=False):
    result = OK if ok else {'success': False, 'error': error}
    return {'tool_name': 'execute_ibl', 'success': ok, 'elapsed_ms': 5,
            'input': {'code': code, **({'check': True} if check else {})}, 'result': json.dumps(result, ensure_ascii=False)}


BAD = run('#!ibl edition=2\nreturn [sense:restaurant]{qeury: "청주 맛집"}', ok=False,
          error='실행 전 검사에서 거절했습니다: 알 수 없는 인자: qeury. 비슷한 인자: query')
GUIDE = {'tool_name': 'read_guide', 'success': True, 'input': {'query': 'remote_phone.md'}, 'result': '…'}


def test_a_turn_that_succeeded_at_once_adds_nothing_to_the_judges_input():
    assert turn_path([run()], {1: 1}) is None
    assert turn_path([run(), BAD], {1: 1}) is None            # 통한 원문 뒤의 실패는 그 길의 헛걸음이 아니다
    assert turn_path([run(check=True, ok=False, error='검사 거절'), run()], {2: 1}) is None  # 검사만 한 호출은 실행이 아니다
    assert turn_path([BAD], {}) is None                        # 통한 원문이 없으면 길도 없다


def test_path_carries_facts_only_order_error_head_and_lookups():
    path = turn_path([GUIDE, BAD, {'tool_name': 'Bash', 'success': True, 'input': {'command': 'ls'}}, run()], {4: 1})
    assert (path['failed_runs'], path['lookups']) == (1, 1)
    guide, bad, shell, good = path['steps']
    assert guide == {'step': 1, 'tool': 'read_guide', 'name': 'remote_phone.md', 'lookup': True}
    assert bad['ok'] is False and bad['actions'] == ['sense:restaurant'] and '알 수 없는 인자: qeury' in bad['error']
    assert shell == {'step': 3, 'tool': 'Bash', 'ok': True} and good['source_id'] == 1
    assert 'command' not in json.dumps(path)                   # 셸 명령 본문은 싣지 않는다


def test_long_turns_are_cut_to_a_bounded_number_of_steps():
    calls = [BAD] * (MAX_STEPS + 10) + [run()]
    path = turn_path(calls, {len(calls): 1})
    assert len(path['steps']) == MAX_STEPS and path['omitted_steps'] == 11
    assert path['steps'][-1]['source_id'] == 1 and path['failed_runs'] == MAX_STEPS + 10


def test_a_route_is_kept_only_where_it_points_into_the_evidence():
    path = turn_path([GUIDE, BAD, run(), BAD], {3: 1})
    chosen = {'consulted_steps': [1, 2, 99, True], 'failed': [
        {'steps': [2], 'cause': '인자 이름은 qeury 가 아니라 query'},
        {'steps': [4], 'cause': '통한 원문 뒤의 실패'},            # 뒤의 실패는 이 길이 아니다
        {'steps': [2], 'cause': ''}]}                              # 원인을 못 대면 적지 않는다
    route = build_route(path, chosen, [1], '2026-11-14T16:30:00+09:00')
    assert route == {'at': '2026-11-14', 'consulted': [{'guide': 'remote_phone.md'}],
                     'failed': [{'actions': ['sense:restaurant'], 'cause': '인자 이름은 qeury 가 아니라 query',
                                 'error': path['steps'][1]['error']}]}
    assert build_route(path, {'consulted_steps': [3]}, [1]) is None    # 조회가 아닌 단계는 참고한 것이 아니다
    assert build_route(path, chosen, [7]) is None and build_route(path, None, [1]) is None
    assert build_route(None, chosen, [1]) is None


def test_route_is_shown_at_recall_with_its_date():
    from corpus_policy import route_note
    from ibl_usage_db import UsageExample
    from ibl_usage_rag import IBLUsageRAG
    route = {'at': '2026-11-14', 'consulted': [{'guide': 'remote_phone.md'}],
             'failed': [{'actions': ['sense:crawl'], 'error': 'HTTP 403', 'cause': '봇 차단이라 내장 브라우저로 풀림'}]}
    note = route_note(json.dumps({'routes': [{'at': '2026-10-01', 'consulted': [], 'failed': []}, route]}))
    assert note == '2026-11-14 참고: remote_phone.md / 안 된 길: sense:crawl — 봇 차단이라 내장 브라우저로 풀림'
    assert route_note('{}') == '' and route_note(json.dumps({'routes': [route], 'evidence_stale': True})) == ''
    base = dict(nodes='sense', category='single', difficulty=1, success_rate=-1.0, source='distilled', score=0.9)
    xml = IBLUsageRAG()._format_references([
        UsageExample(id=1, intent='기사 본문', ibl_code=CODE, provenance=json.dumps({'routes': [route]}), **base),
        UsageExample(id=2, intent='가격 조회', ibl_code=CODE, **base)])
    assert xml.count(' route="') == 1 and '안 된 길: sense:crawl' in xml
    assert '그날의 사실이지 금지가 아니다' in xml


@pytest.fixture
def corpus(db, monkeypatch, tmp_path):
    import hippo_tree
    monkeypatch.setattr(hippo_tree, 'DOC_DIR', str(tmp_path / 'tree'))
    return db


def _routes(db, ident):
    with db._get_connection() as conn:
        return json.loads(conn.execute('SELECT provenance FROM ibl_examples WHERE id=?', (ident,)).fetchone()[0]).get('routes')


def test_route_is_attached_to_the_known_example_instead_of_a_new_row(corpus):
    ident = corpus.add_example('청주 맛집', CODE, source='manual_seed')
    other = '#!ibl edition=2\nreturn [sense:restaurant]{query: "부산 맛집"}'
    named = corpus.add_example('이름 있는 것', other, source='distilled')
    with corpus._get_connection() as conn:
        conn.execute("UPDATE ibl_examples SET alias='하나' WHERE id=?", (named,))
        conn.commit()
    for day in range(1, MAX_ROUTES + 2):
        assert attach_route(corpus, CODE, {'at': f'2026-11-{day:02d}', 'consulted': [], 'failed': []}) == ident
    assert [r['at'] for r in _routes(corpus, ident)] == ['2026-11-02', '2026-11-03', '2026-11-04']  # 최근 것만
    assert attach_route(corpus, other, {'at': 'x'}) == 0 and not _routes(corpus, named)             # 이름 있는 함수
    assert attach_route(corpus, '#!ibl edition=2\nreturn 2', {'at': 'x'}) == 0                      # 없는 원문


def test_a_wandering_turn_reaches_the_judge_even_when_the_procedure_is_known(corpus):
    """원문이 이미 아는 절차면 예전에는 판단 전에 생략했다 — 헤맨 길이 있으면 넘기고, 길만 덧붙인다."""
    from ibl_usage_rag import apply_experience, prepare_experience
    import unified_distill as ud
    ident = corpus.add_example('청주 맛집', CODE, source='manual_seed')
    assert prepare_experience('청주 맛집', [run()], 0.0, unified=True) is False      # 곧장 성공 + 아는 절차 = 전과 같이 생략
    section = prepare_experience('청주 맛집', [BAD, run()], 0.0, unified=True)
    assert section['known_procedure'] and section['path']['failed_runs'] == 1
    shown = ud.model_input({'sections': {'execution': section}, 'skip_reasons': {}, 'snapshot': {}})
    assert shown['sections']['execution']['path'] == section['path']
    assert shown['sections']['execution']['known_procedure'] == section['known_procedure']
    keep = {'decision': 'keep', 'source_ids': [1], 'intent': '지역 맛집 찾기', 'topic': '', 'scope': 'component',
            'benefit': '인자 이름 헛걸음을 줄인다', 'applicability': '맛집 검색',
            'route': {'failed': [{'steps': [1], 'cause': '인자 이름은 query'}]}}
    with corpus._get_connection() as conn:
        before = conn.execute('SELECT COUNT(*) FROM ibl_examples').fetchone()[0]
    assert apply_experience(section, {**keep, 'route': None}) is False                # 길이 없으면 중복이라 저장하지 않는다
    assert apply_experience(section, keep) is True
    with corpus._get_connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM ibl_examples').fetchone()[0] == before
    assert _routes(corpus, ident)[0]['failed'][0]['cause'] == '인자 이름은 query'


def test_judges_prompt_states_route_as_optional_fact_not_prohibition():
    import unified_distill as ud
    assert 'route는 선택이고 없는 것이 정상이다' in ud.SYSTEM_PROMPT
    assert '금지문이 아니라 무엇이 왜 안 됐는지의 사실로 쓴다' in ud.SYSTEM_PROMPT
    assert 'route(선택):{consulted_steps' in ud.SYSTEM_PROMPT


# ───────────────────────── R6: 사용자가 방법을 바로잡은 턴 ─────────────────────────

CRAWL = '#!ibl edition=2\nreturn [sense:crawl]{url: "https://example.com/menu"}'
PREVIOUS = {'user_message': '청주에서 점심 먹을 곳 좀 찾아줘', 'recorded_at': '2026-11-14T10:00:00+09:00',
            'tool_calls': [run(CRAWL), run(CRAWL, check=True, ok=False, error='검사')]}


def test_previous_turn_is_handed_over_as_facts_only():
    from distill_route import MAX_PREVIOUS_STEPS, previous_summary
    seen = previous_summary(PREVIOUS, '2026-11-14T10:12:30+09:00')
    assert seen == {'user_message': '청주에서 점심 먹을 곳 좀 찾아줘', 'minutes_ago': 12,
                    'steps': [{'step': 1, 'tool': 'execute_ibl', 'ok': True, 'actions': ['sense:crawl']}]}
    assert previous_summary({**PREVIOUS, 'tool_calls': [GUIDE]}, '2026-11-14T10:12:30+09:00') is None  # 실행이 없던 턴
    assert previous_summary(None, 'x') is None
    many = previous_summary({**PREVIOUS, 'tool_calls': [run(CRAWL)] * (MAX_PREVIOUS_STEPS + 3)}, 'bad date')
    assert len(many['steps']) == MAX_PREVIOUS_STEPS and many['omitted_steps'] == 3 and many['minutes_ago'] is None


def test_a_users_correction_is_kept_only_when_it_points_at_the_previous_run():
    from distill_route import previous_summary
    before = previous_summary(PREVIOUS, '2026-11-14T10:12:30+09:00')
    assert turn_path([run()], {1: 1}) is None
    path = turn_path([run()], {1: 1}, always=True)              # 곧장 성공한 턴이어도 바로잡힌 길을 묶을 번호는 있어야 한다
    assert path['failed_runs'] == 0 and path['steps'][0]['source_id'] == 1
    fix = {'corrected': {'previous_steps': [1], 'cause': '웹 긁기 말고 맛집 검색을 쓰라고 함'}}
    route = build_route(path, fix, [1], '2026-11-14T10:12:30+09:00', before)
    assert route == {'at': '2026-11-14', 'consulted': [], 'failed': [
        {'actions': ['sense:crawl'], 'error': '', 'cause': '웹 긁기 말고 맛집 검색을 쓰라고 함', 'by': 'user'}]}
    assert build_route(path, fix, [1], None, None) is None                                   # 직전 턴 근거 없이는 안 적는다
    assert build_route(path, {'corrected': {'previous_steps': [9], 'cause': 'x'}}, [1], None, before) is None
    assert build_route(path, {'corrected': {'previous_steps': [1], 'cause': ' '}}, [1], None, before) is None
    from corpus_policy import route_note
    assert route_note(json.dumps({'routes': [route]})) == '2026-11-14 사용자가 바로잡음: sense:crawl — 웹 긁기 말고 맛집 검색을 쓰라고 함'


def test_the_ledger_finds_the_previous_turn_of_the_same_conversation(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    import distill_ledger as ledger
    import pulse_db
    monkeypatch.setattr(pulse_db, 'CONSCIOUSNESS_DB_PATH', tmp_path / 'pulse.db')
    now = datetime.now(timezone(timedelta(hours=9)))

    def job(key, minutes_ago, agent='agent_001'):
        return {'job_key': key, 'agent_id': agent, 'registry_key': '추천:' + agent, 'project_id': '추천', 'principal': 'owner',
                'recorded_at': (now - timedelta(minutes=minutes_ago)).isoformat(), 'user_message': key, 'tool_calls': []}

    for row in (job('old', 200), job('first', 30), job('other-agent', 5, agent='agent_002'), job('second', 10)):
        ledger.create(row)
    current = job('current', 0)
    ledger.create(current)
    assert ledger.previous_turn(current)['job_key'] == 'second'                    # 같은 대화에서 가장 가까운 앞 턴
    assert ledger.previous_turn(job('lonely', 0, agent='agent_003')) is None        # 다른 대화의 턴은 직전 턴이 아니다
    assert ledger.previous_turn(job('late', -120)) is None                          # 한 시간이 넘으면 건네지 않는다
    assert ledger.previous_turn({**current, 'recorded_at': None}) is None


def test_a_corrected_turn_attaches_the_users_correction_to_the_known_example(corpus):
    """R6 끝에서 끝: 직전 턴은 다른 방법, 이번 턴은 곧장 성공한 아는 절차 — 판단이 교정이라고 고르면 그 용례에 붙는다."""
    from distill_route import previous_summary
    from ibl_usage_rag import apply_experience, prepare_experience
    import unified_distill as ud
    ident = corpus.add_example('청주 맛집', CODE, source='manual_seed')
    before = previous_summary(PREVIOUS, '2026-11-14T10:12:30+09:00')
    assert prepare_experience('그렇게 말고 맛집 검색으로 찾아줘', [run()], 0.0, unified=True) is False   # 직전 턴 근거가 없으면 전과 같다
    section = prepare_experience('그렇게 말고 맛집 검색으로 찾아줘', [run()], 0.0, unified=True, previous=before)
    assert section['previous_turn'] == before and section['known_procedure'] and section['path']['failed_runs'] == 0
    shown = ud.model_input({'sections': {'execution': section}, 'skip_reasons': {}, 'snapshot': {}})
    assert shown['sections']['execution']['previous_turn'] == before
    keep = {'decision': 'keep', 'source_ids': [1], 'intent': '지역 맛집 찾기', 'topic': '', 'scope': 'component',
            'benefit': '맛집은 전용 검색으로', 'applicability': '맛집·식당을 찾을 때',
            'route': {'corrected': {'previous_steps': [1], 'cause': '웹 긁기 말고 맛집 검색을 쓰라고 함'}}}
    assert apply_experience(section, keep) is True
    assert _routes(corpus, ident)[0]['failed'][0] == {
        'actions': ['sense:crawl'], 'error': '', 'cause': '웹 긁기 말고 맛집 검색을 쓰라고 함', 'by': 'user'}
    assert 'route.corrected를 붙인다' in ud.SYSTEM_PROMPT and '새 과제는 교정이 아니다' in ud.SYSTEM_PROMPT
