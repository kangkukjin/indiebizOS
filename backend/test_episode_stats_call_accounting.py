"""조회 오탐·로그 이중 표현·부분 코퍼스 누락의 집계 회귀."""
import hashlib
import json

import boot_paths  # noqa: F401
import pytest

from test_fn_zero_rediagnosis_2026_09_07 import _load_script, _pulse_db, _run


def _sha(code):
    return hashlib.sha256(code.encode()).hexdigest()


def _tool(**args):
    return ('[Codex/test] tool_use mcp__indiebizos__execute_ibl '
            + json.dumps(args, ensure_ascii=False))


def _scan(codes, log, corpus=None, metadata=None):
    mod = _load_script()
    parse, trunc = mod._load_backend()
    assert parse is not None
    events = []
    for i, code in enumerate(codes):
        data = {"code_sha256": _sha(code), "code_chars": len(code), "fn_count": 0}
        data.update((metadata or {}).get(i, {}))
        events.append(("ibl.started", json.dumps(data)))
    trajectory = mod._pair_trajectory(events)
    return mod._scan(log, parse, trunc, trajectory, corpus or {})


def test_lookup_does_not_force_whole_episode_log_fallback():
    code = '[self:time]{} >> [table:take]{n:1}'
    broken = '[self:time]{broken'
    log = '\n'.join([
        _tool(code='', describe=['self:time']),
        _tool(code=code), '[IBL_DEBUG] code=' + code,
        _tool(read_result={'id': 'fixture'}),
        _tool(code=broken), '[IBL_DEBUG] code=' + broken,
        _tool(code=code), '[IBL_DEBUG] code=' + code,
    ])
    a = _scan(['', code, '', broken, code], log,
              {_sha(code): code, _sha(broken): broken})
    assert (a['IBL'], a['실행'], a['계약조회'], a['결과열람']) == (5, 3, 1, 1)
    assert (a['문장'], a['조합'], a['문법오류']) == (2, 2, 1)
    assert a['코드미기록'] == a['회수'] == 0
    assert a['_코드소스'] == 'corpus'


def test_log_only_dedup_preserves_repeated_executions():
    mod = _load_script()
    parse, trunc = mod._load_backend()
    code = '[self:time]{} >> [table:take]{n:1}'
    log = '\n'.join([
        _tool(code=code), '[IBL_DEBUG] code=' + code,
        _tool(code=code),  # DEBUG는 반복 실행 때 생략될 수도 있다.
        _tool(code=code), '[IBL_DEBUG] code=' + code,
        _tool(describe=['self:time']),
        _tool(code='', read_result={'id': 'fixture'}),
        _tool(recover='fixture-ticket'),
    ])
    a = mod._scan(log, parse, trunc)
    assert (a['IBL'], a['문장'], a['조합']) == (6, 3, 3)
    assert a['계약조회'] == a['결과열람'] == a['회수'] == 1
    assert a['문법오류'] == a['파싱실패'] == a['코드미기록'] == 0


def test_missing_corpus_recovers_only_matching_call():
    first = '$a = [self:time]{}'
    second = '$a >> [table:take]{n:1}'
    log = '\n'.join([_tool(code=second), '[IBL_DEBUG] code=' + second])
    a = _scan([first, second], log, {_sha(first): first})
    assert a['문장'] == 2
    assert a['문법오류'] == a['코드미기록'] == 0
    assert a['_코드소스'] == 'mixed'


def test_debug_restores_truncated_tool_code_once():
    mod = _load_script()
    parse, trunc = mod._load_backend()
    code = '[self:time]{} >> [table:take]{n:1}'
    log = '\n'.join([
        '[Codex/test] tool_use mcp__indiebizos__execute_ibl '
        '{"code":"[self:time]{} >> [ta...',
        '[IBL_DEBUG] code=' + code,
    ])
    a = mod._scan(log, parse, trunc)
    assert a['IBL'] == a['문장'] == a['조합'] == 1
    assert a['절단'] == a['문법오류'] == 0


def test_inprocess_debug_without_tool_use_still_counts():
    mod = _load_script()
    parse, trunc = mod._load_backend()
    code = '[self:time]{}'
    log = '\n'.join([
        '[IBL_DEBUG] code=' + code,
        '[06:00:00] [test] [self:time] -> OK (1ms)',
        '[06:00:01] [test] [self:time] -> OK (1ms)',
    ])
    a = mod._scan(log, parse, trunc)
    assert a['IBL'] == 2 and a['문장'] == 1
    assert a['코드미기록'] == a['종류미상'] == 1


def test_pipeline_alias_does_not_duplicate_debug():
    mod = _load_script()
    parse, trunc = mod._load_backend()
    code = '[self:time]{}'
    a = mod._scan(_tool(pipeline=code) + '\n[IBL_DEBUG] code=' + code, parse, trunc)
    assert a['IBL'] == a['문장'] == 1
    assert a['문법오류'] == 0


@pytest.mark.parametrize('debug_suffix', ['\n[fn:열추려보기]{}', '...'])
def test_multiline_or_truncated_debug_does_not_duplicate_full_tool_call(debug_suffix):
    mod = _load_script()
    parse, trunc = mod._load_backend()
    code = '[self:time]{}\n[fn:열추려보기]{}'
    debug = '[self:time]{}' + debug_suffix
    a = mod._scan(_tool(code=code) + '\n[IBL_DEBUG] code=' + debug, parse, trunc)
    assert a['IBL'] == 1 and a['문장'] == 2
    assert a['절단'] == a['문법오류'] == 0


def test_missing_earlier_assignment_is_unknown_context_not_syntax_error():
    first = '$a = [self:time]{}'
    second = '$a >> [table:count]{}'
    a = _scan([first, second], '', {_sha(second): second})
    assert a['코드미기록'] == a['문맥불명'] == 1
    assert a['문법오류'] == 0


def test_partial_old_lookup_log_does_not_guess_other_empty_call_modes():
    a = _scan(['', ''], _tool(code='', describe=['self:time']))
    assert a['종류미상'] == 2
    assert a['계약조회'] == a['회수'] == a['문법오류'] == 0


def test_trajectory_classifies_empty_calls_without_logs_or_corpus():
    metadata = {0: {'request_keys': ['describe']},
                1: {'request_keys': ['read_result']},
                2: {'request_keys': ['recover']},
                3: {'request_keys': []}}
    a = _scan([''] * 5, '', metadata=metadata)
    assert [a[k] for k in ('계약조회', '결과열람', '회수', '빈호출', '종류미상')] == [1] * 5
    assert a['코드미기록'] == a['문법오류'] == 0


@pytest.mark.parametrize('mode', ['episodes', 'totals'])
def test_public_output_keeps_call_categories(tmp_path, monkeypatch, capsys, mode):
    mod = _load_script()
    code = '[self:time]{}'
    log = '\n'.join([_tool(code=code), _tool(code='', describe=['self:time']),
                     _tool(code='', read_result={'id': 'fixture'})])
    monkeypatch.setattr(mod, 'DB', _pulse_db(tmp_path, [(code, True), ('', True), ('', True)], log))
    row = _run(mod, monkeypatch, capsys, {'last': 1, 'mode': mode})['items'][0]
    assert row['실행'] == row['계약조회'] == row['결과열람'] == 1
    assert row['IBL'] == 3
    assert row['회수'] == row['종류미상'] == 0


@pytest.mark.parametrize('tool_input,keys', [
    ({'describe': ['self:time']}, ['describe']),
    ({'read_result': {'id': 'fixture'}}, ['read_result']),
    ({'code': '[self:time]{}'}, []),
])
def test_writer_preserves_request_kind_without_request_values(
        monkeypatch, tmp_path, isolated_episode_store, tool_input, keys):
    import sqlite3
    import episode_logger as el
    import system_tools_ibl as ibl

    monkeypatch.setattr(ibl, '_execute_ibl_unified_impl', lambda *a: '{"success":true}')
    with el.trajectory_scope(task_id='call_accounting_test'):
        ibl._execute_ibl_unified(tool_input, str(tmp_path), agent_id='test')
    with sqlite3.connect(isolated_episode_store, timeout=10) as conn:
        data = json.loads(conn.execute(
            "SELECT data FROM trajectory_event WHERE kind='ibl.started'").fetchone()[0])
    assert data['request_keys'] == keys
    assert 'describe' not in data and 'read_result' not in data


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
