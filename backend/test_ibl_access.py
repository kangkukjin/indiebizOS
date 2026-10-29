"""소개 선택은 역사 행에 남아도 현재 활성 함수의 계약으로 전달된다."""
import json
import sqlite3
import sys
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

import ibl_access
from test_function_support import current_source, register_fixture_dependencies

ROOT = Path(__file__).resolve().parents[1]
NAMES = {'좁혀서읽기', '주소마다읽기', '열추려보기', '정렬해추리기', '본문에서찾기', '주소별발췌'}


@pytest.fixture
def selected(tmp_path, monkeypatch):
    from function_library import register
    import runtime_utils
    import ibl_v2_adapters
    import ibl_registry

    registry = ibl_v2_adapters.load_registry()
    monkeypatch.setattr(ibl_v2_adapters, 'load_registry', lambda *a, **k: registry)
    monkeypatch.setattr(runtime_utils, 'get_base_path', lambda: tmp_path)
    monkeypatch.setattr(ibl_registry, 'code_is_own', lambda code: True)

    folder = tmp_path / 'data/idioms'
    folder.mkdir(parents=True)
    (folder / 'current_call_lessons.json').write_bytes(
        (ROOT / 'data/idioms/current_call_lessons.json').read_bytes())
    db = tmp_path / 'data/ibl_usage.db'
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE ibl_examples(id INTEGER PRIMARY KEY, intent, ibl_code, '
                     'success_count, fail_count, topic, alias, returns, signature, always_on, '
                     'created_at, updated_at, executable, provenance)')
        conn.execute('CREATE VIEW ibl_current_examples AS SELECT * FROM ibl_examples WHERE executable=1')
        for name in sorted(NAMES):
            source = current_source(name)
            register_fixture_dependencies(source)
            register(name, source)
            # 옛 본문·실적은 역사로 남고 소개 선정 표식만 유지된 실데이터를 재현한다.
            conn.execute('INSERT INTO ibl_examples VALUES(NULL,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                         ('옛 소개', '$return="OLD_BODY"', 999, 0, '검증', name, 'old', 'old',
                          1, '2026-01', '2026-01', 0, '{}'))
    monkeypatch.setattr(ibl_access, '_get_nodes_path', lambda: ROOT / 'data/ibl_nodes.yaml')
    monkeypatch.setattr(ibl_access, '_idioms_cache', {'text': None, 't': 0, 'key': None})
    return db


def test_historical_selection_reaches_environment_with_current_contracts(selected):
    before = selected.read_bytes()
    text = ibl_access.build_environment()
    assert ibl_access.exposed_idiom_names(None) == NAMES
    for name in NAMES:
        assert f'[fn:{name}]' in text
    assert 'OLD_BODY' not in text and '사용 999회' not in text
    assert '대상은 {url,pattern,context?,limit?} 목록' in text
    assert '[fn:주소별발췌]{대상:' in text
    assert selected.read_bytes() == before
    hidden = ibl_access.build_environment(expose_idioms=False)
    assert '<ibl_idioms' not in hidden and '↳ 관용구' not in hidden


def test_inactive_function_and_unselected_name_stay_hidden(selected):
    from function_library import register, retire
    retire('주소별발췌')
    register('비선정함수', '#!ibl edition=2\n[def:비선정함수](){return 1}')
    names = ibl_access.exposed_idiom_names(None)
    assert names == NAMES - {'주소별발췌'}


def test_current_review_hold_and_node_scope_still_apply(selected):
    with sqlite3.connect(selected) as conn:
        conn.execute('INSERT INTO ibl_examples VALUES(NULL,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                     ('보류', current_source('주소별발췌'), 0, 0, '검증', '주소별발췌', '', '',
                      0, '2026-02', '2026-02', 1,
                      json.dumps({'corpus_review': {'decision': 'hold'}})))
    assert '주소별발췌' not in ibl_access.exposed_idiom_names(None)
    scoped = ibl_access.exposed_idiom_names({'self', 'table'})
    assert '주소마다읽기' not in scoped
    assert {'열추려보기', '정렬해추리기'} <= scoped


def test_demote_clears_historical_selection_and_refreshes_cached_map(selected, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    import register_idiom
    import ibl_usage_db
    from types import SimpleNamespace

    assert '주소별발췌' in ibl_access.exposed_idiom_names(None)
    monkeypatch.setattr(register_idiom, '_db_path', lambda: str(selected))
    monkeypatch.setattr(ibl_usage_db, 'IBLUsageDB', lambda: SimpleNamespace(
        find_phrase_by_alias=lambda name: {'ibl_code': current_source(name)}))
    assert register_idiom._promote('주소별발췌', False) == 0
    assert '주소별발췌' not in ibl_access.exposed_idiom_names(None)
    with sqlite3.connect(selected) as conn:
        assert conn.execute('SELECT always_on,executable,success_count FROM ibl_examples '
                            'WHERE alias=?', ('주소별발췌',)).fetchone() == (0, 0, 999)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
