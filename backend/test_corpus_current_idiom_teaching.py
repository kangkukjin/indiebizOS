"""Current calls must see their resolved contract, not old same-name evidence."""
import boot_paths  # noqa: F401
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
import ibl_access
from test_ibl_v2_assets import memory  # noqa: F401 — isolated DB/FTS/vector fixture
from ibl_v2_adapters import Adapter
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]
LESSONS = json.loads((ROOT / 'data/idioms/current_call_lessons.json').read_text())['idioms']


def db():
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE ibl_examples(intent,ibl_code,success_count,fail_count,topic,alias,returns,signature,always_on,updated_at)')
    return conn


def test_same_name_native_contract_does_not_inherit_legacy_success():
    with db() as conn:
        old = ('옛 뜻', '$return=$목록', 99, 1, '목록', 'f', 'items', '목록', 1, '2026-01')
        native = ('현재 뜻', '#!ibl edition=2\n[def:f]($목록){return $목록}', 0, 0, '목록', 'f', 'List', '목록', 0, '2026-02')
        conn.executemany('INSERT INTO ibl_examples VALUES (?,?,?,?,?,?,?,?,?,?)', [old, native])
        from function_library import register
        register('f', native[1])
        result = ibl_access._current_idiom_rows(conn, [old[:8]], 'returns', 'signature')
        assert result[0][1] == native[1] and result[0][2:4] == (0, 0)
        assert conn.execute('SELECT success_count FROM ibl_examples WHERE always_on=1').fetchone()[0] == 99


def test_only_selected_names_are_exposed_and_legacy_has_no_current_pipe_slot():
    with db() as conn:
        old=('뜻','$return=$목록',3,0,'목록','f','items','목록',1,'2026-01')
        conn.execute('INSERT INTO ibl_examples VALUES (?,?,?,?,?,?,?,?,?,?)',old)
        assert ibl_access._current_idiom_rows(conn,[old[:8]],'returns','signature')==[]
        assert conn.execute('SELECT returns FROM ibl_examples').fetchone()[0]=='items'



def test_latest_legacy_body_keeps_history_without_current_exposure():
    with db() as conn:
        old=('옛 뜻','$return=$목록',99,0,'목록','f','items','목록',1,'2026-01')
        latest=('새 뜻','$return=$새목록',0,0,'목록','f','items','새목록',0,'2026-02')
        conn.executemany('INSERT INTO ibl_examples VALUES (?,?,?,?,?,?,?,?,?,?)',[old,latest])
        assert ibl_access._current_idiom_rows(conn,[old[:8]],'returns','signature')==[]
        assert conn.execute('SELECT success_count FROM ibl_examples ORDER BY updated_at').fetchall()==[(99,),(0,)]



def test_current_pipe_slot_disallows_duplicate_argument():
    code = '#!ibl edition=2\n[def:f]($목록,$개수){return $목록}'
    assert '목록' in ibl_access._authoring_pipe_note(code)
    assert '동시 명시 금지' in ibl_access._authoring_pipe_note(code)
    plan = compile_program(code + '\n[] >> [fn:f]{목록:[],개수:0}')
    assert any(i['code'] == 'PIPE_COLLISION' for i in plan.issues)


def test_changed_definition_hides_stale_lesson():
    source = '#!ibl edition=2\n[def:f]($목록){return $목록}'
    lesson = {'source_edition': 2, 'source_sha256': hashlib.sha256(source.encode()).hexdigest()}
    assert ibl_access._current_lesson(lesson, source) == lesson
    assert ibl_access._current_lesson(lesson, source + '\n') == lesson
    assert ibl_access._current_lesson(lesson, source + '; [self:read]{path:"x"}') == {}


def test_current_example_header_does_not_comment_out_the_whole_example():
    source = '#!ibl edition=2\n[def:f]($목록){return $목록}'
    r = ('뜻', source, 0, 0, '목록', 'f', 'List', '목록')
    lines = ibl_access._idiom_lines(r, {'inputs': '목록', 'example': '#!ibl edition=2\nreturn [fn:f]{목록:[]}'}, authoring=True)
    assert '  조합 예: return [fn:f]{목록:[]}' in lines
    assert not any('#!ibl edition=2;' in line for line in lines)


@pytest.mark.parametrize('lesson', LESSONS, ids=lambda x: x['name'])
def test_current_call_examples_compile_against_current_definitions(lesson):
    from test_function_support import current_source
    from ibl_v2_adapters import load_registry
    source=current_source(lesson['name'])
    assert lesson['source_edition']==2
    assert hashlib.sha256(source.strip().encode()).hexdigest()==lesson['source_sha256']
    plan=compile_program(lesson['example'],load_registry(),definitions={name:current_source(name) for name in ('위치마다읽기','본문에서찾기',lesson['name'])})
    assert not plan.issues,plan.report()



def test_native_body_returns_matches_and_separates_execution_evidence(memory,tmp_path):
    from ibl_v2_entry import handle_request
    from test_function_support import current_source
    from function_library import register
    lesson=next(row for row in LESSONS if row['name']=='본문에서찾기')
    register('본문에서찾기',current_source('본문에서찾기'))
    result=handle_request({'edition':2,'code':lesson['example']},str(tmp_path))
    assert result['success'],result
    value=result['value']
    assert [r['text'] for r in value['items']]==['앞 문단','핵심 근거']
    assert all(r['url']=='https://example.com/' for r in value['items'])
    assert 'match_info' in value and 'results' not in value
    assert any(e['kind']=='function_result' for e in result['evidence'])
    assert any(e['kind']=='invoke' and e.get('action')=='self:script' for e in result['evidence'])



if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))


def test_current_catalog_is_discoverable_without_rewriting_old_corpus(memory):
    from function_library import register
    from function_memory import catalog_search_rows
    from ibl_name_search import search_aliased
    ref=register('퇴출검색검증','#!ibl edition=2\n[def:퇴출검색검증](){return 42}','퇴출검색검증')
    with memory._get_connection() as conn:
        before=[tuple(row) for row in conn.execute('SELECT * FROM ibl_examples')]
    rows=search_aliased(memory,'퇴출검색검증')
    own=next(row for row in rows if row.alias=='퇴출검색검증')
    assert own.success_rate==-1 and own.source=='function_catalog'
    assert json.loads(own.provenance)['function_ref']==ref
    with memory._get_connection() as conn:
        assert [tuple(row) for row in conn.execute('SELECT * FROM ibl_examples')]==before
