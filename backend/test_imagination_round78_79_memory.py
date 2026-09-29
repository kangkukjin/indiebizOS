"""상상훈련 78·79회차 잔여 수리 — 기억·건강·원장 표면 (2026-09-29).

  · F78-2: 열린 인자 계약(open_params)이 check 를 눈멀게 했다 — recent_chats days·query·since 침묵 무시.
           닫힌 계약 + UNKNOWN_ARGUMENT 안내, 그리고 열린 계약 전수 관문(사유 없는 개방 = 빌드 실패).
  · F78-3: 건강 교재의 최상위 systolic/diastolic 이 선언 밖(UNKNOWN_ARGUMENT) · 측정 조회 선언 "items" ↔ 실제 table.
  · B72-3: memory search 대화 미리보기 200자 무표지.
  · F78-4: 조합 지표의 "훈련 도달 가능"이 잠든 묶음·남의 몸 어휘를 셌다 — 정본 판정 함수 재사용.
  · F78-5: [self:ledger] 원자 쓰기가 몸의 쓰기 원장에 없었다.
시험은 전부 임시 경로에만 쓴다(실제 원장·DB 불가침).
"""
import boot_paths  # noqa: F401
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'data/packages/installed/tools'
SCRIPTS = ROOT / 'scripts'


def module(package, name='handler'):
    spec = importlib.util.spec_from_file_location('r7879m_' + package.replace('-', '_') + '_' + name,
                                                TOOLS / package / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def script(name):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    return importlib.import_module(name)


def report(source):
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    return compile_program('#!ibl edition=2\n' + source, load_registry()).report()


def issues(source, code='UNKNOWN_ARGUMENT'):
    return [i['message'] for i in report(source)['issues'] if i['code'] == code]


def decode(value):
    from ibl_v2_adapters import decode_envelope
    return decode_envelope(value, {'protocol': 'legacy-envelope'})[0]


# ── F78-2 ────────────────────────────────────────────────────────────────

def test_recent_chats_filters_are_refused_with_guidance():
    found = issues('return [self:recent_chats]{project_id:"fixture", limit:20, days:7, query:"x", since:"2026-09-22"}')
    assert {m.split('.')[0] for m in found} == {'알 수 없는 인자: days', '알 수 없는 인자: query', '알 수 없는 인자: since'}
    assert all('[table:filter]' in m for m in found)       # 선언 데이터의 안내가 붙는다
    assert not issues('return [self:recent_chats]{limit:5, agent:"fixture"}')


def test_system_ai_recent_chats_refuses_agent_axis(tmp_path):
    from drivers.sqlite_driver import SqliteDriver
    conn = sqlite3.connect(tmp_path / 'system_ai_memory.db')
    conn.execute('CREATE TABLE conversations(id INTEGER, timestamp TEXT, role TEXT, content TEXT)')
    conn.execute('INSERT INTO conversations VALUES(1,?,?,?)', ('2026-09-29', 'user', 'fixture'))
    conn.commit(); conn.close()
    out = SqliteDriver()._handle_memory('recent_chats', {'project_path': str(tmp_path), 'agent': 'someone'})
    assert out.get('success') is False and 'agent' in out.get('error', '')
    ok = SqliteDriver()._handle_memory('recent_chats', {'project_path': str(tmp_path)})
    assert ok.get('success') is not False and len(ok['items']) == 1


@pytest.mark.parametrize('source', [
    '[others:delegate]{agent_id:"a", message:"m", dry_run:true}',
    '[others:board]{op:"create", hashtag:"x", preview:true}',
    '[others:follow]{op:"add", pubkey:"x", confirm:false}',
    '[others:ask]{message:"m", simulate:true}',
    '[self:download]{url:"https://example.com/a", output:"a.bin"}',
    '[table:reduce]{items:[{a:1}], step:"acc + a", bogus:1}',
])
def test_census_closed_actions_refuse_unknown_arguments(source):
    assert issues('return ' + source)


@pytest.mark.parametrize('source', [
    '[others:delegate]{agent_id:"a", message:"m", mode:"workflow", do:"[self:time]{}"}',
    '[others:board]{op:"create", tag:"x", board_name:"y"}',
    '[others:follow]{op:"add", npub:"x", name:"y"}',
    '[self:install_lib]{package:"duckdb", check:true}',
    '[self:goal]{op:"log", task_id:"t", category:"c", description:"d", result:"failure", lesson:"l"}',
    '[limbs:open_window]{app:"multichat", room_id:"r", room_name:"n"}',
    '[table:reduce]{items:[{a:1}], init:0, expr:"acc + a", as:"s"}',
])
def test_census_closed_actions_keep_implementation_keys(source):
    assert not issues('return ' + source)


def test_open_params_gate_is_clean_and_self_tests(tmp_path):
    import yaml
    gate = script('iblbuild_open_params')
    data = yaml.safe_load((ROOT / 'data/ibl_nodes.yaml').read_text(encoding='utf-8'))
    found, reasoned = gate.validate_open_params(data, ROOT)
    assert found == []
    assert reasoned == ['self:workflow', 'table:each']          # 사유를 단 개방만 남는다
    base = {'router': 'system', 'func': 'x'}
    fake = {'nodes': {'n': {'actions': {
        'silent': dict(base),                                                  # 선언 없음 → 열림·사유 없음
        'reasoned': {**base, 'open_params': True, 'open_params_reason': '자유 키가 본질'},
        'closed': {**base, 'open_params': False, 'params': {'a': 'string'}},
        'stale': {**base, 'open_params': False, 'params': {'a': 'string'}, 'open_params_reason': '옛 사유'},
    }}}}
    found, reasoned = gate.validate_open_params(fake, tmp_path)
    assert reasoned == ['n:reasoned']
    assert [f.split(']')[0] for f in found] == ['[n:silent', '[n:stale']


# ── F78-3 ────────────────────────────────────────────────────────────────

def test_health_flat_blood_pressure_is_declared_and_saved(monkeypatch):
    assert not issues('return [self:health]{op:"save", category:"혈압", systolic:128, diastolic:85}')
    assert not issues('return [self:health]{op:"save", category:"혈압", value:{systolic:128, diastolic:85}}')
    mod = module('health-record')
    saved = {}
    monkeypatch.setattr(mod.storage, 'save_measurement', lambda **k: saved.update(k) or 1)
    out = json.loads(mod.save_health_info({'category': '혈압', 'systolic': '128', 'diastolic': 85}))
    assert out['success'] is True
    assert saved['value'] == {'systolic': 128, 'diastolic': 85} and saved['category'] == 'blood_pressure'


def test_reads_gate_sees_literal_tuple_loops(tmp_path):
    gate = script('iblbuild_action_reads')
    (tmp_path / 'handler.py').write_text(
        'FLAT = ("alpha", "beta")\n'
        'def save(d):\n'
        '    for k in FLAT:\n'
        '        if k in d:\n'
        '            pass\n'
        '    for j in ("gamma",):\n'
        '        d.get(j)\n'
        '    return d.get("delta")\n')
    reads = gate._Reads(gate._module_index(tmp_path))
    assert reads.of('handler', 'save', 0) == {'alpha', 'beta', 'gamma', 'delta'}


@pytest.mark.parametrize('rows', [[], [{'category': 'blood_pressure', 'measured_at': '2026-09-01T08:00:00',
                                        'value': {'systolic': 128, 'diastolic': 85}, 'note': None, 'id': 1}]])
def test_measurement_query_is_one_shape(monkeypatch, rows):
    mod = module('health-record')
    monkeypatch.setattr(mod.storage, 'get_measurements', lambda **k: rows)
    out = json.loads(mod.get_health_context({'query_type': 'measurements', 'category': 'blood_pressure'}))
    assert {'text', 'count', 'table', 'blocks', 'points'} <= set(out)
    assert 'items' not in out and out['count'] == len(rows)
    assert out['table']['columns'][0] == '날짜' and len(out['table']['rows']) == len(rows)


# ── B72-3 ────────────────────────────────────────────────────────────────

def test_conversation_preview_marks_truncation_like_deep_memory(tmp_path):
    mod = module('memory')
    conn = sqlite3.connect(tmp_path / 'system_ai_memory.db')
    conn.execute('CREATE TABLE conversations(id INTEGER, role TEXT, timestamp TEXT, content TEXT)')
    conn.execute('INSERT INTO conversations VALUES(1,?,?,?)', ('user', '2026-09-29', 'fixture ' + 'x' * 400))
    conn.execute('INSERT INTO conversations VALUES(2,?,?,?)', ('user', '2026-09-29', 'fixture short'))
    conn.commit(); conn.close()
    rows = {r['conversation_id']: r for r in mod._search_conversations(str(tmp_path), 'fixture')}
    assert rows[1]['preview_truncated'] is True and rows[1]['content_chars'] == 408
    assert len(rows[1]['preview']) == mod.CONVERSATION_PREVIEW_CHARS
    assert rows[2]['preview_truncated'] is False and rows[2]['content_chars'] == 13
    # 장기기억 가지(memory_provenance.search_view)와 같은 표지 이름 — 레코드 투영도 그대로 싣는다
    from memory_provenance import search_view
    deep = search_view({'content': 'y' * 500, 'source_ref': None}, 'y')
    assert {'preview_truncated', 'content_chars', 'preview_offset'} <= set(deep) & set(rows[1])
    rec = mod._memories_to_records([rows[1]])[0]
    assert rec['preview_truncated'] is True and rec['content_chars'] == 408


def test_memory_search_envelope_declares_selection_truncation(tmp_path, monkeypatch):
    mod = module('memory')
    monkeypatch.setattr(mod, '_search_conversations', lambda *a, **k: [
        {'conversation_id': 1, 'preview': 'p', 'preview_truncated': True, 'preview_offset': 0,
         'content_chars': 999, 'from_agent': 'user', 'to_agent': None, 'created_at': '2026-09-29',
         'source': 'conversation'}])
    db = type('DB', (), {'VALID_CATEGORIES': set(), 'search': staticmethod(lambda **k: [])})
    raw = mod._memory_search(db, {'query': 'fixture'}, str(tmp_path), 'fixture')
    env = json.loads(raw)
    assert env['truncations'][0]['scope'] == 'selection' and env['truncations'][0]['rows'] == 1
    assert decode(raw)['items'][0]['preview_truncated'] is True   # 선택 범위라 PARTIAL_SOURCE 아님


# ── F78-4 ────────────────────────────────────────────────────────────────

def test_metrics_reuse_canonical_reachability(tmp_path, monkeypatch):
    import yaml
    import ibl_registry
    import vocabulary_state
    metrics = script('vocab_composition_metrics')
    reg = tmp_path / 'ibl_nodes.yaml'
    reg.write_text(yaml.safe_dump({'nodes': {'self': {'actions': {
        'awake': {}, 'asleep': {}, 'hidden': {'prompt_hidden': True}, 'phone': {'runs_on': 'phone_only'}}}}}))
    monkeypatch.setattr(metrics, 'REG', str(reg))
    asleep = {'self:asleep'}
    monkeypatch.setattr(ibl_registry, 'self_can_run',
                        lambda n, a, c: f'{n}:{a}' not in asleep and not c.get('prompt_hidden') and not c.get('runs_on'))
    monkeypatch.setattr(vocabulary_state, 'action_reason', lambda n, a, c=None, root=None: 'zz' if f'{n}:{a}' in asleep else None)
    out = metrics.load_unreachable_actions()
    assert set(out) == {'self:asleep', 'self:hidden', 'self:phone'}
    assert out['self:asleep'] == '잠든 묶음' and 'prompt_hidden' in out['self:hidden'] and 'phone_only' in out['self:phone']
    m = metrics._measure_codes(['[self:awake]{} >> [table:take]{n:1}'], {'self:awake', 'self:asleep', 'self:hidden'}, out)
    assert m['미조합_도달가능'] == 0 and set(m['미조합_도달불가_사유']) == {'self:asleep', 'self:hidden'}


# ── F78-5 ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('call', ['append', 'set'])
def test_ledger_write_lands_in_body_write_ledger(tmp_path, monkeypatch, call):
    import write_ledger
    import thread_context as tc
    ledger = module('system_essentials', 'ledger_ops')
    monkeypatch.setattr(ledger, '_ROOT', tmp_path)
    monkeypatch.setattr(write_ledger, '_ROOT', tmp_path)
    monkeypatch.setattr(write_ledger, '_LEDGER_PATH', tmp_path / 'data' / 'write_ledger.jsonl')
    monkeypatch.setattr(tc, 'get_current_agent_id', lambda: 'fixture-agent')
    monkeypatch.setattr(tc, 'get_current_task_id', lambda: 'fixture-task')
    monkeypatch.setattr(tc, 'get_task_origin', lambda: 'training')
    if call == 'append':
        out = ledger.op_append({'path': 'data/fixture_ledger.json', 'item': {'id': 1}})
    else:
        out = ledger.op_set({'path': 'data/fixture_ledger.json', 'target': 'k', 'value': 1})
    assert out['success'] is True
    rows = [json.loads(line) for line in (tmp_path / 'data' / 'write_ledger.jsonl').read_text().splitlines()]
    assert len(rows) == 1
    row = rows[0]
    assert row['gate'] == 'self_ledger' and row['path'] == 'data/fixture_ledger.json'
    assert (row['agent'], row['task'], row['origin']) == ('fixture-agent', 'fixture-task', 'training')
    assert row['size'] == (tmp_path / 'data' / 'fixture_ledger.json').stat().st_size


def test_failed_ledger_write_is_not_logged(tmp_path, monkeypatch):
    import write_ledger
    ledger = module('system_essentials', 'ledger_ops')
    monkeypatch.setattr(ledger, '_ROOT', tmp_path)
    monkeypatch.setattr(write_ledger, '_ROOT', tmp_path)
    monkeypatch.setattr(write_ledger, '_LEDGER_PATH', tmp_path / 'data' / 'write_ledger.jsonl')
    out = ledger.op_set({'path': 'data/fixture_ledger.json', 'value': 1})   # target 없는 set = 관문 거절
    assert out['success'] is False
    assert not (tmp_path / 'data' / 'write_ledger.jsonl').exists()


def test_closed_system_declaration_is_documented_vocab():
    """닫힌 비핸들러 선언의 키는 판본 1 소프트 경고의 '문서화 어휘'다 — scope 가 'op 를 의도했나요?'를 받으면
    평문 실패("오류: …") 앞에 경고가 붙어 스케줄 파이프라인이 실패를 성공으로 읽었다(회귀 실측)."""
    import yaml
    from ibl_param_vocab import check_params
    data = yaml.safe_load((ROOT / 'data/ibl_nodes.yaml').read_text(encoding='utf-8'))
    cfg = data['nodes']['others']['actions']['delegate']
    assert check_params('others', 'delegate', {'scope': 'cross', 'agent_id': 'a', 'message': 'm'}, cfg) is None
    found = check_params('self', 'recent_chats', {'days': 7}, data['nodes']['self']['actions']['recent_chats'])
    assert found and found['unknown'] == ['days']


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
