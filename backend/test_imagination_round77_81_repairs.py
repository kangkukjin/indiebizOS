"""Producer contracts and shared boundaries from imagination reports 77–81."""
import boot_paths  # noqa: F401
import importlib.util
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'data/packages/installed/tools'


def module(package, name='handler'):
    spec = importlib.util.spec_from_file_location('r7781_' + package.replace('-', '_') + '_' + name,
                                                TOOLS / package / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def decode(value):
    from ibl_v2_adapters import decode_envelope
    return decode_envelope(value, {'protocol': 'legacy-envelope'})[0]


@pytest.mark.parametrize('operation', ['list', 'detail'])
def test_neighbors_never_emit_authentication(operation):
    mod = module('business')
    row = {'id': 1, 'name': 'fixture', 'portal_key': 'dummy-key', 'portal_pw': 'dummy-hash',
           'portal_login_id': 'login', 'warehouse_key': 'dummy', 'future_secret': 'dummy',
           'additional_info': 'public', 'is_indiebiz_peer': True}
    bm = SimpleNamespace(get_neighbors=lambda **_: [row], get_neighbor=lambda _: row,
                         get_contacts=lambda _: [], get_messages=lambda **_: [])
    value = json.loads(getattr(mod, '_nb_' + operation)(bm, {'id': 1}))
    actual = value['items'][0] if operation == 'list' else value['neighbor']
    assert actual['portal_member'] is True
    assert actual['additional_info'] == 'public'
    assert not set(actual) & {'portal_key', 'portal_pw', 'portal_login_id', 'warehouse_key', 'future_secret'}
    assert row['portal_key'] == 'dummy-key'


def test_context7_v2_schema_and_drift(monkeypatch):
    mod = module('context7')
    data = {'results': [{'id': '/x/y', 'title': 'Library', 'description': 'Description'}]}
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: data)
    monkeypatch.setattr(mod.requests, 'get', lambda *a, **k: response)
    row = decode(mod._resolve('Library'))['items'][0]
    assert row['title'] == 'Library' and row['id'] == '/x/y'
    data['results'][0].pop('title')
    assert mod._search_library_id('Library')['error_type'] == 'source_changed'


@pytest.mark.parametrize('existing', [False, True])
def test_nanet_end_page_preserves_rows(monkeypatch, existing):
    mod = module('study')
    calls = []
    def fake(*args):
        calls.append(args)
        if existing and len(calls) == 1:
            return {'result': [{'totalCount': 1, 'searchList': [{'title': 'Paper', 'pubYear': '2026'}]}]}
        return {'result': [{'error': [{'code': '201', 'message': 'no results'}]}]}
    monkeypatch.setattr(mod, '_nanet_call', fake)
    result = decode(mod._search_nanet({'query': 'fixture', 'limit': 10}))
    assert len(result['items']) == int(existing)
    assert not result['truncated']


def test_unsupported_source_filter_refused_before_network(monkeypatch):
    mod = module('study')
    monkeypatch.setattr(mod, '_search_arxiv', lambda _: pytest.fail('network must not run'))
    assert mod._paper_search({'source': 'arxiv', 'year_from': 2024}, None)['success'] is False


def test_local_calendar_and_spotlight_utc_match(monkeypatch):
    import file_index
    previous = os.environ.get('TZ')
    monkeypatch.setenv('TZ', 'Asia/Seoul'); time.tzset()
    try:
        monkeypatch.setattr(file_index, '_mdls_meta', lambda _: {
            'kMDItemContentCreationDate': datetime(2026, 8, 31, 16, 30)})
        row = file_index._item_from_meta('/nonexistent', ['taken_at'])
        assert row['taken_at'] == '2026-09-01T01:30:00+09:00'
        assert row['month'] == '2026-09'
        assert file_index._iso_bound('2026-09-01', False) == '2026-08-31T15:00:00Z'
        assert file_index._epoch_ms('2026-09-01', False) == int(datetime.fromisoformat('2026-09-01T00:00:00+09:00').timestamp()*1000)
    finally:
        if previous is None:
            os.environ.pop('TZ', None)
        else:
            os.environ['TZ'] = previous
        time.tzset()


def test_photo_limit_is_selection_candidate_limit_is_partial(monkeypatch):
    import file_index
    monkeypatch.setattr(file_index, '_run_mdfind', lambda *a: ['a.jpg', 'b.jpg'])
    monkeypatch.setattr(file_index, '_drop_pseudo_media', lambda p, _: p)
    monkeypatch.setattr(file_index, '_ranked_items', lambda *a: [{'path': 'a.jpg'}])
    args = ('photo', None, None, None, False, None, None, 1, 'mtime', [])
    assert decode(file_index._spotlight_query(*args))['truncations'][0]['scope'] == 'selection'
    monkeypatch.setattr(file_index, '_MAX_CANDIDATES', 1)
    from ibl_v2_ir import Fault
    with pytest.raises(Fault) as err:
        decode(file_index._spotlight_query(*args))
    assert err.value.code == 'PARTIAL_SOURCE'


def test_recent_chat_preview_is_usable(tmp_path):
    import sqlite3
    from drivers.sqlite_driver import SqliteDriver
    conn = sqlite3.connect(tmp_path / 'system_ai_memory.db')
    conn.execute('CREATE TABLE conversations(id INTEGER, timestamp TEXT, role TEXT, content TEXT)')
    conn.execute('INSERT INTO conversations VALUES(1,?,?,?)', ('2026-09-29', 'user', 'x'*400))
    conn.commit(); conn.close()
    value = decode(SqliteDriver()._handle_memory('recent_chats', {'project_path': str(tmp_path)}))
    assert value['items'][0]['content_len'] == 400
    assert value['items'][0]['truncated'] is True
    assert value['truncations'][0]['scope'] == 'selection'


def test_training_trajectory_uses_shared_origin(monkeypatch):
    import episode_logger
    import runtime_utils
    from thread_context import actor_context
    monkeypatch.setattr(runtime_utils, 'in_test_process', lambda: False)
    with actor_context(origin='training'):
        assert episode_logger._episode_source() == 'training'


def test_op_effect_variants_use_source_declaration():
    from ibl_v2_contracts import handler_contract
    from ibl_callable_contract import selected
    contract = handler_contract('custom', 'thing', {'params': {'op': 'operation'}, 'returns': 'items',
        'side_effect': True, 'ops': {'default': 'list', 'values': {'list': 'read', 'delete': 'write'},
                                   'side_effect': {'list': False}}})
    assert selected(contract, {})['effects'] == ['read_external']
    assert selected(contract, {'op': 'delete'})['effects'] == ['write_external']
    assert contract['effects'] == ['unknown']


def test_media_path_resolution_before_dispatch(monkeypatch, tmp_path):
    from tool_context import ToolContext
    mod = module('media_producer')
    monkeypatch.setattr(mod, 'create_tts', lambda args, base: {'args': args, 'base': base})
    ctx = ToolContext(str(tmp_path), 'create_tts')
    got = mod.execute({'output_filename': 'narr/a.mp3'}, ctx)
    assert got['args']['output_filename'] == str(tmp_path / 'narr/a.mp3')
    monkeypatch.setitem(mod._OP_DISPATCHERS['render_artifact'], 'html', lambda args, base: {'args': args, 'base': base})
    got = mod.execute({'path': 'input.html', 'output_path': 'review/page.png'}, ToolContext(str(tmp_path), 'render_artifact'))
    assert got['args']['path'] == str(tmp_path / 'input.html')
    assert got['base'] == str(tmp_path / 'review')


def test_tts_receipt_is_composable(monkeypatch, tmp_path):
    mod = module('media_producer')
    async def generate(text, path, *a, **k):
        Path(path).write_bytes(b'fixture')
        return {'engine': 'edge', 'voice': 'fixture'}
    monkeypatch.setattr(mod, 'generate_tts', generate)
    monkeypatch.setitem(sys.modules, 'moviepy', SimpleNamespace(AudioFileClip=lambda _: SimpleNamespace(duration=1.5, close=lambda: None)))
    value = decode(mod.create_tts({'text': 'fixture', 'output_filename': 'narr/a.mp3'}, str(tmp_path)))
    assert value['duration'] == 1.5 and Path(value['path']).exists()


def test_prescreen_verdict_is_structured():
    mod = module('media_producer', 'vision_read')
    from ibl_edition import source_context
    with source_context(2):
        value = decode(mod.critique_image({'image_path': '/fixture.png', 'intent': 'fixture', 'prescreen': 'blank'}, '.'))
    assert value['passed'] is False and value['score'] == 0
    assert value['tier'] == 'prescreen'


def test_performance_default_and_unknown_region(monkeypatch):
    mod = module('culture'); kopis = module('culture', 'tool_kopis')
    monkeypatch.setitem(sys.modules, 'tool_kopis', SimpleNamespace(get_performances=lambda **kw: kw, search_by_keyword=lambda **kw: kw))
    assert mod._perf_search({'date_from': '2026-10-03', 'date_to': '2026-10-04'})['prfstate'] is None
    assert kopis._resolve_region('충북')
    with pytest.raises(ValueError):
        kopis._resolve_region('청주')


def test_coordinates_do_not_admit_national_restaurants(monkeypatch):
    mod = module('location-services')
    local = {'name': 'near', 'lat': 36.6, 'lng': 127.4, 'distance': '619'}
    remote = {'name': 'far', 'lat': 37.5, 'lng': 127.0}
    monkeypatch.setattr(mod, 'search_kakao_restaurants', lambda *a: {'restaurants': [local]})
    monkeypatch.setattr(mod, 'search_naver_local', lambda *a: {'restaurants': [remote]})
    monkeypatch.setattr(mod, 'build_location_map', lambda **kw: {})
    result = mod.search_restaurants_combined('food', x='127.4', y='36.6', radius=700, enrich=False)
    assert [r['name'] for r in result['items']] == ['near']
    assert result['items'][0]['distance'] == 619
    assert result['items'][0]['blog_count'] is None


def test_stay_nightly_price_and_empty_filter(monkeypatch):
    mod = module('location-services', 'tool_stay')
    monkeypatch.setattr(mod, 'has_curl_cffi', lambda: True)
    data = {'props': {'pageProps': {'paginationInfo': {'totalCount': 1, 'totalPageCount': 1},
            'domesticList': {'body': {'items': [{'meta': {'name': 'hotel'},
                 'room': {'stay': {'price': {'discountTotalPrice': 150000}}}}]}}}}}
    response = SimpleNamespace(status_code=200, text='<script id="__NEXT_DATA__">'+json.dumps(data)+'</script>')
    monkeypatch.setattr(mod, 'chrome_get', lambda *a, **k: response)
    args = {'region': 'fixture', 'checkin': '2026-10-10', 'checkout': '2026-10-12', 'max_price': 100000}
    result = decode(mod._search_goodchoice(args))
    assert result['items'][0]['price_per_night'] == 75000
    assert result['items'][0]['nights'] == 2
    assert decode(mod._search_goodchoice({**args, 'max_price': 10000}))['items'] == []


def test_citation_retains_late_quote_and_rejects_invented_quote(monkeypatch):
    mod = module('notebook')
    raw = 'a' * 196 + 'actual quoted sentence' + 'b' * 100
    monkeypatch.setattr(mod, '_source_chunks', lambda *a: [{'loc': '49:22', 'text': raw}])
    docs = [{'id': 67, 'title': 'fixture', 'body': '[49:22] ' + raw}]
    cites, bad = mod._verify_document_citations(None, '“actual quoted sentence” [#67 49:22]', docs)
    assert not bad and 'actual quoted sentence' in cites[0]['quote']
    cites, bad = mod._verify_document_citations(None, '“invented” [#67 49:22]', docs)
    assert bad and not cites


def test_unknown_memory_read_does_not_create_store(tmp_path):
    mod = module('memory', 'memory_db')
    assert mod.search(str(tmp_path), 'missing-agent', 'fixture') == []
    assert mod.read(str(tmp_path), 'missing-agent', 1) is None
    assert not list(tmp_path.iterdir())


def test_memory_search_uses_system_store_and_nonadjacent_words(tmp_path):
    import sqlite3
    mod = module('memory')
    conn = sqlite3.connect(tmp_path / 'system_ai_memory.db')
    conn.execute('CREATE TABLE conversations(id INTEGER, role TEXT, timestamp TEXT, content TEXT)')
    conn.execute('INSERT INTO conversations VALUES(1,?,?,?)', ('user', '2026-09-29', 'AI 관련 블로그'))
    conn.commit(); conn.close()
    rows = mod._search_conversations(str(tmp_path), 'AI 블로그')
    assert len(rows) == 1 and rows[0]['conversation_id'] == 1


def test_portal_read_does_not_mutate():
    mod = module('community-portal')
    state = {'portals': []}
    core = SimpleNamespace(load_state=lambda: state, portal_by_ref=lambda *a: None,
                           mutate_state=lambda *a: pytest.fail('read attempted a write'))
    assert mod._get_portal(core, {}) == (state, {})
    with pytest.raises(ValueError, match='포털을 찾을 수 없습니다'):
        mod._get_portal(core, {'portal': 'missing'})


def test_closed_publish_and_feed_refuse_fake_previews():
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    registry = load_registry()
    for source in ['[others:publish]{title:"t", content:"x", dry_run:true}',
                   '[others:feed]{op:"post",content:"x",preview:true}']:
        assert any(i['code'] == 'UNKNOWN_ARGUMENT' for i in compile_program(source, registry).report()['issues'])


def test_health_missing_person_lookup_is_not_creation(tmp_path, monkeypatch):
    import sqlite3
    mod = module('health-record', 'health_storage')
    path = tmp_path / 'health.db'
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE persons(id INTEGER, name TEXT, deleted INTEGER)')
    conn.commit(); conn.close()
    def connect():
        con = sqlite3.connect(path); con.row_factory = sqlite3.Row
        return con
    monkeypatch.setattr(mod, 'get_db_connection', connect)
    assert mod.get_person_id('missing') is None
    with connect() as con:
        assert con.execute('SELECT COUNT(*) FROM persons').fetchone()[0] == 0


def test_engine_health_agrees_with_string_failure(monkeypatch):
    import ibl_engine
    import pulse_db
    from system_tools_ibl import _execute_ibl_unified
    rows = []
    monkeypatch.setattr(ibl_engine, '_route_handler', lambda *a, **k: json.dumps({'success': False, 'message': 'fixture failure'}))
    monkeypatch.setattr(pulse_db, 'record_action_health', lambda *a, **k: rows.append((a,k)))
    _execute_ibl_unified({'code': '[table:take]{items:[{a:1}],n:1}', 'verbose': True}, str(ROOT))
    assert rows
    args, kwargs = rows[-1]
    assert kwargs.get('success', args[2] if len(args) > 2 else None) is False


@pytest.mark.parametrize('html,success', [('<html>changed</html>', False),
    ('<script type="application/ld+json">{"@type":"ItemList","itemListElement":[]}</script>', True)])
def test_danggeun_schema_drift_is_not_empty_result(monkeypatch, html, success):
    mod = module('shopping-assistant', 'tool_used')
    monkeypatch.setattr(mod, '_get', lambda *a, **k: (html, 200))
    value = mod.search_danggeun('fixture')
    assert value.get('success', True) is success
    if not success:
        assert value['error_type'] == 'source_changed'


def test_declared_effect_census_matches_all_op_variants():
    from ibl_v2_adapters import load_registry
    from ibl_registry import load_nodes_installed
    from ibl_ops import op_side_effect
    from ibl_callable_contract import selected
    registry = load_registry()
    checked = 0
    for node, config in load_nodes_installed()['nodes'].items():
        for action, definition in config.get('actions', {}).items():
            adapter = registry.get(f'{node}:{action}')
            if not adapter or definition.get('callable_contract'):
                continue
            for op in (definition.get('ops') or {}).get('values', {}):
                effects = selected(adapter.contract, {'op': op})['effects']
                expected = 'write_external' if op_side_effect(definition, op) else 'read_external'
                assert expected in effects, (node, action, op, effects)
                checked += 1
    assert checked > 100
    for key, op in [('engines:web_site', 'list'), ('engines:web', 'snapshot'), ('engines:web_component', 'catalog')]:
        assert selected(registry[key].contract, {'op': op})['effects'] == ['read_external']


def test_inbox_counts_are_unreplied_not_read_status(monkeypatch):
    mod = module('business')
    monkeypatch.setattr(mod, '_indienet', lambda: None)
    bm = SimpleNamespace(get_inbox_summary=lambda **kw: [
        {'id': 1, 'name': 'fixture', '_unread': 2, '_last': {'content': 'hi', 'message_time': '2026-09-29T10:00:00'},
         '_channel_contacts': []}])
    value = json.loads(mod._msg_inbox(bm, {}))
    row = value['items'][0]
    assert row['unreplied'] == row['unread'] == 2
    assert row['created_at'] is not None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
