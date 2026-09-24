"""홈페이지 검토: 전건 이력, 부분 수집 실패와 함수 재사용 계약."""
import boot_paths  # noqa: F401
import importlib.util
import json
import os
import subprocess
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('homepage_work_test', ROOT / 'data/scripts/webapp_work.py')
work = importlib.util.module_from_spec(spec)
spec.loader.exec_module(work)


def test_history_keeps_over_100_commits_and_pins_head(tmp_path):
    def git(*args, date='2026-09-24T12:00:00+09:00'):
        env = {**os.environ, 'GIT_AUTHOR_DATE': date, 'GIT_COMMITTER_DATE': date}
        return subprocess.check_output(['git', '-C', str(tmp_path), *args], env=env, text=True).strip()
    git('init', '-q')
    git('config', 'user.name', 'Fixture')
    git('config', 'user.email', 'fixture@example.invalid')
    p = tmp_path / 'source.txt'
    p.write_text('old')
    git('add', '.')
    git('commit', '-qm', 'old', date='2026-09-17T00:00:00+09:00')
    for i in range(104):
        p.write_text(str(i))
        git('add', '.')
        git('commit', '-qm', f'change {i}')
    # 날짜가 역전된 tip 뒤의 최신 커밋도 빠뜨리지 않는다.
    p.write_text('older date at tip')
    git('add', '.')
    git('commit', '-qm', 'out of order', date='2026-09-17T00:00:00+09:00')
    out = work.history(tmp_path, '2026-09-18T00:00:00+09:00')
    assert out['count'] == len(out['items']) == 104
    assert out['head'] == git('rev-parse', 'HEAD')
    assert out['source_complete'] is True
    assert out['items'][0]['subject'] == 'change 103'
    assert work.history(tmp_path, '2027-01-01T00:00:00+09:00')['items'] == []


@pytest.mark.parametrize('since', [None, '', 'yesterday', '2026-09-18', '2026-09-18T00:00:00'])
def test_history_requires_explicit_datetime(tmp_path, since):
    with pytest.raises(ValueError, match='since'):
        work.history(tmp_path, since)


def test_history_failure_is_not_empty_success(tmp_path):
    with pytest.raises(ValueError, match='Git 이력 조회 실패'):
        work.history(tmp_path, '2026-09-18T00:00:00+09:00')


def run_program(call, *, sites=None, fail=None, screen_ok=True):
    from ibl_v2_adapters import Adapter, load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    from ibl_v2_ir import Fault
    registry = load_registry()
    calls = []

    def invoke(action, args):
        calls.append((action, args))
        if fail == (action, args.get('op')):
            raise Fault('SOURCE_FAILURE', 'fixture source failed')
        if action == 'engines:web_site':
            return {'sites': sites if sites is not None else [
                {'id': 'fixture-site', 'deploy_url': 'https://example.invalid/', 'local_path': '/fixture'}]}
        if action == 'sense:crawl':
            return {'text': 'current page', 'items': [{'url': 'https://example.invalid/link'}]}
        if action == 'engines:web':
            return {'items': [{'check': 'status', 'ok': True}, {'check': 'screenshot', 'ok': screen_ok}]}
        if action == 'self:script':
            return {'head': 'abc', 'items': [], 'count': 0, 'source_complete': True}
        if action == 'self:read':
            return {'text': 'canonical source'}
        raise AssertionError(action)

    params = {
        'engines:web_site': {'op': 'Text'},
        'sense:crawl': {'op': 'Text', 'url': 'Text', 'refresh': 'Bool'},
        'engines:web': {'op': 'Text', 'url': 'Text', 'checks': 'List<Text>'},
        'self:script': {'op': 'Text', 'id': 'Text', 'args': 'Record'},
        'self:read': {'path': 'Text'},
    }
    for action, schema in params.items():
        registry[action] = Adapter({'version': 1, 'params': schema, 'result': 'Unknown',
                                    'effects': ['read_external']},
                                   lambda rt, args, a=action: invoke(a, args))
    source = '\n'.join((ROOT / 'data/idioms' / f).read_text() for f in
                       ('homepage_inspect.ibl', 'homepage_review.ibl')) + '\n' + call
    plan = compile_program(source, registry)
    assert not plan.issues, plan.report()
    result = Runtime(plan).run()
    assert result['success'], result
    return result['value'], calls


def test_missing_site_never_fetches_another_page():
    value, calls = run_program('[fn:홈페이지살펴보기]{사이트:"unknown"}')
    assert not value['ok']
    assert [a for a, _ in calls] == ['engines:web_site']


@pytest.mark.parametrize('failure', [('sense:crawl', 'content'), ('sense:crawl', 'links')])
def test_page_partial_failure_preserves_other_evidence(failure):
    value, calls = run_program('[fn:홈페이지살펴보기]{사이트:"fixture-site"}', fail=failure)
    assert not value['ok'] and value['failed'] == 1
    assert len(value['items']) == 3
    assert sum(row['ok'] for row in value['items']) == 2
    reads = [args for action, args in calls if action == 'sense:crawl']
    assert [r['refresh'] for r in reads] == [True, False]


def test_inner_screenshot_failure_is_not_success():
    value, _ = run_program('[fn:홈페이지살펴보기]{사이트:"fixture-site"}', screen_ok=False)
    assert not value['ok'] and value['failed'] == 1


def test_review_reuses_page_and_reports_empty_documents():
    call = '[fn:홈페이지갱신검토자료]{사이트:"fixture-site",저장소:".",기준시각:"2026-09-18T00:00:00+09:00",정본문서:[],화면:false}'
    value, calls = run_program(call)
    assert not value['ok']
    assert value['history']['source_complete']
    assert not any(a == 'engines:web' for a, _ in calls)
    assert len([a for a, _ in calls if a == 'engines:web_site']) == 1
    value, calls = run_program(call.replace('정본문서:[]', '정본문서:["README.md"]'))
    assert value['ok'] and value['documents'][0]['text'] == 'canonical source'
    value, _ = run_program(call.replace('정본문서:[]', '정본문서:["README.md"]'), fail=('self:read', None))
    assert not value['ok'] and value['document_failures'] == 1


def test_seeds_match_sources_and_do_not_promote():
    seeds = json.loads((ROOT / 'data/idioms/homepage_seeds.json').read_text())
    names = {'홈페이지살펴보기': 'homepage_inspect.ibl', '홈페이지갱신검토자료': 'homepage_review.ibl'}
    for seed in seeds:
        assert not seed.get('always_on', False)
        if seed.get('alias'):
            assert seed['ibl_code'] == (ROOT / 'data/idioms' / names[seed['alias']]).read_text().strip()


def test_registration_commits_dependencies_before_dependents(tmp_path):
    spec = importlib.util.spec_from_file_location('homepage_registration_test', ROOT / 'scripts/register_webapp_idioms.py')
    registration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(registration)
    database = tmp_path / 'memory.db'
    with sqlite3.connect(database) as conn:
        conn.execute('CREATE TABLE ibl_examples(intent TEXT, ibl_code TEXT)')

    class Memory:
        def _get_connection(self):
            return sqlite3.connect(database)

        def add_examples_batch(self, rows):
            # 기존 저장 입구처럼 배치 시작 때 DB에서 의존성을 읽는다.
            with self._get_connection() as conn:
                known = {r[0] for r in conn.execute('SELECT ibl_code FROM ibl_examples')}
                assert all(row.get('dependency') in known for row in rows if row.get('dependency'))
                conn.executemany('INSERT INTO ibl_examples VALUES (?,?)', [(r['intent'], r['ibl_code']) for r in rows])
            return len(rows)

    seeds = [{'intent': 'base', 'ibl_code': 'base'},
             {'intent': 'composed', 'ibl_code': 'composed', 'dependency': 'base'},
             {'intent': 'call', 'ibl_code': 'call', 'dependency': 'composed'}]
    assert registration.insert_seeds(Memory(), seeds, tmp_path) == 3
    assert registration.insert_seeds(Memory(), seeds, tmp_path) == 0


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
