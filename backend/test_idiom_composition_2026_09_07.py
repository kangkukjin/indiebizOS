"""선정 관용구의 호출/조합 검증. 실제 파서·함수·파이프·변환자·파일 도구;
외부 웹/AI만 고정 응답, 해마 귀속은 메모리로 격리한다.
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest
import boot_paths  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from curate_idioms import validate_catalog

CATALOG = json.loads((ROOT / 'data/idioms/curated.json').read_text())
ENTRIES = {e['name']: e for e in CATALOG['idioms']}


def test_catalog_checks_signatures_and_composed_examples():
    assert len(validate_catalog(CATALOG)) == 8
    broken = json.loads(json.dumps(CATALOG))
    broken['idioms'][0]['example'] = '[fn:중복빼고추리기]{키: "id"}'
    with pytest.raises(ValueError, match='인자'):
        validate_catalog(broken)


def test_semicolon_body_is_recognized(monkeypatch):
    import fn_recognizer as f
    body = ENTRIES['중복빼고추리기']['body'].replace('\n', '; ')
    monkeypatch.setattr(f, '_aliased_shapes', lambda: {f.shape(body): '중복빼고추리기'})
    assert len(f.statements(body)) == 2
    assert f.fn_hint_for(body)['alias'] == '중복빼고추리기'
    assert len(f.statements('[self:read]{path: "a;b"}')) == 1


def test_prompt_shows_executable_call_and_composition():
    from ibl_access import _idiom_lines
    from workflow_contract import call_signature
    e = ENTRIES['중복빼고추리기']
    row = (e['when'], e['body'], 0, 0, e['topic'], e['name'], 'items', ' '.join(call_signature(e['body'])))
    card = '\n'.join(_idiom_lines(row, e))
    assert '[fn:중복빼고추리기]{키: "…", 개수: "…"}' in card
    assert '앞 통화: items' in card and e['example'] in card


@pytest.fixture
def run(monkeypatch, tmp_path):
    import ibl_engine
    import ibl_usage_db
    import workflow_engine
    from ibl_parser import parse
    from ibl_executors import _execute_table_each
    from tool_context import ToolContext

    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        return mod
    tools = ROOT / 'data/packages/installed/tools'
    dataops = load('_idiom_dataops', tools / 'data-ops/handler.py')
    fs = load('_idiom_fs', tools / 'system_essentials/handler.py')
    original = ibl_engine._execute_ibl_impl
    observed = {'brief': [], 'crawl': [], 'used': []}

    class DB:
        def find_phrase_by_alias(self, name):
            e = ENTRIES.get(name)
            return {'ibl_code': e['body'], 'alias': name} if e else None
        def update_success_by_code(self, code, ok, **kw):
            observed['used'].append(ok)
    monkeypatch.setattr(ibl_usage_db, 'IBLUsageDB', DB)
    monkeypatch.setattr(workflow_engine, 'get_workflow', lambda name: None)

    def leaf(ti, project, agent=None):
        node, act = ti.get('_node'), ti.get('action')
        p = dict(ti.get('params') or {})
        if node == 'table' and act == 'each':
            p['_depth'] = ti.get('_depth', 0)
            return _execute_table_each(p, project, agent_id=agent)
        if node == 'table' and 'data_' + str(act) in dataops._DISPATCH:
            return dataops.execute(p, ToolContext(project, 'data_' + act))
        if node == 'table' and act == 'brief':
            observed['brief'].append(p)
            return {'success': True, 'message': '요약 결과', 'items': [{'summary': '요약 결과'}]}
        if node == 'sense' and act == 'crawl':
            observed['crawl'].append(p['url'])
            if p['url'].endswith('/bad'):
                return {'success': False, 'error': '크롤 실패'}
            return {'success': True, 'text': '짧은 원문', 'items': [{'text': '짧은 원문'}]}
        mapped = {'read': 'read_op', 'file_find': 'glob_files', 'grep': 'grep_files', 'edit': 'edit_file', 'write': 'write_file'}
        if node == 'self' and act in mapped:
            return fs.execute(p, ToolContext(project, mapped[act], agent_id='test'))
        return original(ti, project, agent)
    monkeypatch.setattr(ibl_engine, '_execute_ibl_impl', leaf)

    def execute(code, prev=None):
        from thread_context import actor_context
        with actor_context(agent_id='test', origin='test'):
            out = workflow_engine.execute_pipeline(parse(code), str(tmp_path),
                      context={'_prev_result': json.dumps(prev, ensure_ascii=False) if isinstance(prev, (dict, list)) else prev} if prev is not None else None)
        assert out.get('success'), str(out)[:2500]
        result = out.get('final_result')
        return json.loads(result) if isinstance(result, str) and result.strip().startswith(('{', '[')) else result
    execute.observed = observed
    return execute


def test_two_idioms_then_word_preserve_currency_and_errors(run):
    rows = {'items': [{'title': '첫째', 'url': 'https://x/one'}, {'title': '중복', 'url': 'https://x/one'},
                      {'title': '실패', 'url': 'https://x/bad'}, {'title': '제외', 'url': 'https://x/last'}]}
    result = run('[fn:중복빼고추리기]{키: "url", 개수: 2} >> '
                 '[fn:각각읽고요약]{개수: 2, 지시: "두 문장"} >> [table:take]{n: 2}', rows)
    assert [r['title'] for r in result['items']] == ['첫째', '실패']
    assert result['items'][0]['summary'] == '요약 결과'
    assert '_error' in result['items'][1]
    assert run.observed['crawl'] == ['https://x/one', 'https://x/bad']


def test_chunk_idiom_processes_more_than_old_eight_chunks(run):
    run('[fn:잘라각각종합]{덩이지시: "100자 요약", 종합지시: "합쳐 요약"}', '가' * 135001)
    assert len(run.observed['brief']) == 11  # 10덩이 + 종합, 옛 8개 상한 초과
    assert all(p['instruction'] == '100자 요약' for p in run.observed['brief'][:-1])


def test_two_input_currencies_and_idempotent_write(run, tmp_path):
    path = str(tmp_path / 'ledger.json')
    code = '[fn:원장에누적]{옛것: {items: [{id: 1}]}, 새것: [{id: 1}, {id: 2}], 키: "id", 원장: ' + json.dumps(path) + '}'
    run(code)
    before = Path(path).read_text()
    run(code)
    assert Path(path).read_text() == before
    saved = json.loads(before)
    items = saved['items'] if isinstance(saved, dict) else saved
    assert [r['id'] for r in items] == [1, 2]


def test_latest_means_mtime_not_name(run, tmp_path):
    (tmp_path / 'z.md').write_text('old')
    (tmp_path / 'a.md').write_text('new')
    os.utime(tmp_path / 'z.md', (1000000000, 1000000000))
    result = run('[fn:최신파일읽기]{폴더: ' + json.dumps(str(tmp_path)) + ', 패턴: "*.md"}')
    assert 'new' in json.dumps(result, ensure_ascii=False)
    assert '"old"' not in json.dumps(result, ensure_ascii=False)


def test_find_read_and_edit_confirm(run, tmp_path):
    p = tmp_path / 'note.txt'; p.write_text('TODO\n초안\n')
    result = run('[fn:좁혀서읽기]{패턴: "TODO", 루트: ' + json.dumps(str(tmp_path)) + ', 파일패턴: "*.txt"}')
    assert result['items'] and 'TODO' in json.dumps(result, ensure_ascii=False)
    run('[fn:고치고확인하기]{파일: ' + json.dumps(str(p)) + ', 앞: "초안", 뒤: "완료", 확인: "완료"}')
    assert p.read_text() == 'TODO\n완료\n'


def test_spill_and_summary(run, tmp_path):
    p = tmp_path / 'raw.json'
    result = run('[fn:덜어내고요지만]{주소: "https://x/one", 스필경로: ' + json.dumps(str(p)) + ', 지시: "요약"}')
    assert p.exists() and '짧은 원문' in p.read_text()
    assert '요약 결과' in json.dumps(result, ensure_ascii=False)


def test_nested_instruction_is_data_even_with_quotes(run):
    instruction = 'O\'Reilly의 "핵심"을 요약\\정리\n두 줄'
    result = run('[fn:각각읽고요약]{개수: 1, 지시: ' + json.dumps(instruction) + '}',
                 {'items': [{'title': '문서', 'url': 'https://x/one'}]})
    assert not result['items'][0].get('_error'), result
    assert run.observed['brief'][0]['instruction'] == instruction


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
