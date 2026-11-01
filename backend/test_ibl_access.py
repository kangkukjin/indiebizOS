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


@pytest.mark.parametrize("returns, expected", [
    ("Record⟨관측: items·count·source_ref⟩", "Record⟨관측⟩"),
    ("List<Record⟨관측: text·url⟩>", "List<Record⟨관측⟩>"),
    ("Record{items: List<Text>}", "Record{items: List<Text>}"),
])
def test_compact_map_preserves_shape_and_input_conditions(returns, expected):
    from hippo_tree import phrase_call_line
    from ibl_signature_slot import signature_of
    source = '#!ibl edition=2\n[def:조사]($목록,$개수){return $목록}'
    signature = signature_of(source)
    row = ('실패 행을 보존하며 목록을 읽을 때', source, 17, 2, '수집', '조사', returns, signature)
    lesson = {'inputs': '개수는 0 이상. 실패·부분 결과를 보존한다.',
              'example': 'return [fn:조사]{목록:[],개수:0}'}
    lines = ibl_access._idiom_lines(row, lesson, authoring=True)
    text = '\n'.join(lines)
    assert f'→ {expected}' in text
    assert '[fn:조사]{목록: "…", 개수: "…"}' in text
    assert '언제: 실패 행을 보존하며 목록을 읽을 때' in text
    assert '연결: 앞 값 → 목록' in text
    assert lesson['inputs'] in text
    assert not any(label in text for label in ('골격:', '조합 예:', '사용 19회'))
    assert ibl_access._anchor_line(row) == '    ↳ 관용구 [fn:조사] (호출·용도: ibl_idioms)'
    # 회상·상세가 쓰는 공용 호출 표시는 관측 필드를 계속 보존한다.
    assert returns in phrase_call_line('조사', source, returns, signature)


def test_compact_map_does_not_guess_unknown_signature():
    row = ('용도', '', 0, 0, '기타', '미상', '', None)
    text = '\n'.join(ibl_access._idiom_lines(row))
    assert '[fn:미상] — 서명 미상, describe로 인자 확인' in text
    assert '연결:' not in text
