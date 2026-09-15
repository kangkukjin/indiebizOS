"""31~40위 어휘 회귀: 임시 원장·파일, 외부 API/모델/스케줄러 대역만 사용."""
import importlib.util
import json
from pathlib import Path
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'data/packages/installed/tools'


def load(package, name='handler'):
    path = PKG / package / (name + '.py') if package else ROOT / 'backend/ibl/trigger_engine.py'
    spec = importlib.util.spec_from_file_location('rank31_' + package.replace('-', '_') + name, path)
    mod = importlib.util.module_from_spec(spec)
    old_path = sys.path[:]
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path[:] = old_path
    return mod


@pytest.fixture
def trigger(tmp_path, monkeypatch):
    mod = load('')
    monkeypatch.setattr(mod, 'TRIGGERS_PATH', tmp_path / 'triggers.json')
    monkeypatch.setattr(mod, 'DATA_PATH', tmp_path)
    calls = []
    monkeypatch.setattr(mod, '_sync_schedule_trigger', lambda t, a: calls.append((dict(t), a)) or True)
    return mod, calls


def test_trigger_type_change_removes_old_timer(trigger):
    mod, calls = trigger
    old = mod._create_trigger('fixture', {'cron': '0 9 * * *', 'pipeline': '[self:time]{}'})['trigger']
    calls.clear()
    config = {'channel_type': 'email', 'repeat': 'sender-specific-value'}
    result = mod._update_trigger(old['id'], {'type': 'channel', 'config': config})
    assert 'error' not in result
    assert result['trigger']['config'] == config
    assert [(t['type'], a) for t, a in calls] == [('schedule', 'delete')]
    calls.clear()
    result = mod._update_trigger(old['id'], {'type': 'schedule', 'cron': '0 10 * * *'})
    assert result['trigger']['config']['time'] == '10:00'
    assert [(t['type'], a) for t, a in calls] == [('schedule', 'add')]


@pytest.mark.parametrize('kind', ['channel', 'file', 'webhook'])
def test_trigger_preserves_non_schedule_config(trigger, kind):
    mod, calls = trigger
    config = {'repeat': 'message-rule', 'time': 'source-field', 'path': '/fixture'}
    result = mod._create_trigger('fixture', {'type': kind, 'config': config, 'pipeline': '[self:time]{}'})
    assert result['trigger']['config'] == config
    assert not calls


def test_trigger_invalid_type_does_not_save(trigger):
    mod, calls = trigger
    result = mod._create_trigger('bad', {'type': 'scheduel', 'pipeline': '[self:time]{}'})
    assert result.get('error')
    assert mod.load_triggers()['triggers'] == []


@pytest.mark.parametrize('limit, expected', [(0, []), (1, [2]), ('1', [2]), (-1, None)])
def test_trigger_history_limit(trigger, limit, expected):
    mod, _ = trigger
    mod._save_triggers({'triggers': [], 'history': [{'n': 1}, {'n': 2}]})
    result = mod._trigger_history('', {'limit': limit})
    if expected is None:
        assert result.get('error')
    else:
        assert [h['n'] for h in result['items']] == expected


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(PKG / 'system_essentials'))
    mod = load('system_essentials', 'ledger_ops')
    monkeypatch.setattr(mod, '_ROOT', tmp_path)
    return mod


def test_ledger_parallel_append_and_set_preserve_all_updates(ledger, tmp_path, monkeypatch):
    original = ledger._load_root

    def slow_read(*args):
        root = original(*args)
        time.sleep(.01)
        return root

    monkeypatch.setattr(ledger, '_load_root', slow_read)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda i: ledger.op_append({'path': 'rows.json', 'item': {'id': i}}), range(16)))
    assert all(r['success'] for r in results)
    assert sorted(r['id'] for r in json.loads((tmp_path / 'rows.json').read_text())) == list(range(16))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda i: ledger.op_set({'path': 'state.json', 'target': str(i), 'value': i}), range(16)))
    assert all(r['success'] for r in results)
    assert len(json.loads((tmp_path / 'state.json').read_text())) == 16


@pytest.mark.parametrize('first, second, count', [(True, 1, 2), ('A', 'a', 1), ('가', '\u1100\u1161', 1)])
def test_ledger_upsert_uses_shared_key_equality(ledger, first, second, count):
    from common.value_semantics import values_equal
    assert ledger.op_upsert({'path': 'rows.json', 'item': {'id': first}})['success']
    assert ledger.op_upsert({'path': 'rows.json', 'item': {'id': second, 'value': 2}})['success']
    result = ledger.op_select({'path': 'rows.json'})
    assert result['count'] == count
    assert values_equal(first, second) is (count == 1)


def test_ledger_validates_merged_row_and_preserves_bytes(ledger, tmp_path):
    ledger.op_append({'path': 'rows.json', 'item': {'id': 'a', 'tags': ['one', 'two'], 'state': 'invalid'}})
    before = (tmp_path / 'rows.json').read_bytes()
    for gate in ({'list_limits': {'tags': {'max_items': 1}}}, {'enum_fields': {'state': ['valid']}}):
        result = ledger.op_upsert({'path': 'rows.json', 'item': {'id': 'a', 'value': 2}, **gate})
        assert result['success'] is False
        assert (tmp_path / 'rows.json').read_bytes() == before


@pytest.mark.parametrize('xml, success', [('<dbs/>', True), ('<dbs><db><prfnm>공연</prfnm></db></dbs>', True),
                                         ('<error><message>denied</message></error>', False),
                                         ('<html><body>maintenance</body></html>', False)])
def test_performance_error_xml_is_not_empty_success(monkeypatch, xml, success):
    mod = load('culture', 'tool_kopis')
    monkeypatch.setattr(mod, '_check_api_key', lambda: None)
    monkeypatch.setattr(mod, 'api_call', lambda *a, **k: xml)
    result = mod.call_kopis_api('pblprfr', {})
    assert ('error' not in result) is success
    if success:
        assert isinstance(result['data'], list)


@pytest.mark.parametrize('raw, expected', [(False, False), ('false', False), ('true', True), (None, True)])
def test_forage_reconcile_false_does_not_mutate(monkeypatch, raw, expected):
    mod = load('pc-manager')
    calls = []
    monkeypatch.setitem(sys.modules, 'forage_doc', SimpleNamespace(reconcile=lambda *a, **k: calls.append(k) or {'success': True}))
    result = json.loads(mod.execute({'op': 'reconcile', 'apply': raw}, SimpleNamespace(tool_name='forage_op')))
    assert result['success']
    assert calls == [{'apply': expected}]


def test_forage_invalid_layer_rejected_before_write(monkeypatch):
    mod = load('pc-manager')
    calls = []
    monkeypatch.setitem(sys.modules, 'forage_memory', SimpleNamespace(note_map=lambda **k: calls.append(k) or {'success': True}))
    result = json.loads(mod.execute({'op': 'note', 'layer': 'owenr', 'locus': '/fixture', 'kind': 'identity', 'claim': 'fixture'}, SimpleNamespace(tool_name='forage_op')))
    assert result['success'] is False and not calls


def test_forage_note_string_flags(monkeypatch):
    mod = load('pc-manager')
    calls = []
    monkeypatch.setitem(sys.modules, 'forage_memory', SimpleNamespace(note_map=lambda **k: calls.append(k) or {'success': True}))
    result = json.loads(mod.execute({'op': 'note', 'body': 'test', 'locus': '/fixture', 'kind': 'identity', 'claim': 'fixture',
                                     'generalizes': 'false', 'surface_flag': 'false', 'territory': 'false'}, SimpleNamespace(tool_name='forage_op')))
    assert result['success']
    assert all(calls[0][k] is False for k in ('generalizes', 'surface_flag', 'territory'))


@pytest.mark.parametrize('failure', [{'success': False, 'error': 'offline'}, {'success': False}, {'error': 'offline'}])
def test_youtube_batch_reports_partial_and_total_failure(failure):
    mod = load('youtube')
    yt = SimpleNamespace(search_youtube=lambda query, count: failure if query == 'bad' else {
        'success': True, 'results': [{'video_id': 'a', 'title': 'fixture'}], 'clamped': True, 'requested': 100})
    result = mod._direct_search({'queries': ['good', 'bad'], 'limit': 100}, yt)
    assert result['success'] is False and result['partial'] is True
    assert result['items'][0]['video_id'] == 'a'
    assert result['errors'][0]['query'] == 'bad'
    assert result['sections'][0]['requested'] == 100
    result = mod._direct_search({'queries': ['bad']}, yt)
    assert result['success'] is False and not result['partial'] and not result['items']


def test_youtube_batch_keeps_dedup_and_sections():
    mod = load('youtube')
    yt = SimpleNamespace(search_youtube=lambda **k: {'success': True, 'results': [{'video_id': 'a'}]})
    result = mod._direct_search({'queries': 'first,second'}, yt)
    assert result['success'] and result['count'] == 1
    assert [s['count'] for s in result['sections']] == [1, 0]


@pytest.mark.parametrize('queries', [[], {}, 1, [None]])
def test_youtube_invalid_queries_do_not_search(queries):
    mod = load('youtube')
    def search(**k):
        pytest.fail('invalid input invoked search')
    result = mod._direct_search({'queries': queries}, SimpleNamespace(search_youtube=search))
    assert result['success'] is False


@pytest.mark.parametrize('code, alive', [(200, True), (401, True), (403, True), (404, False), (410, False), (503, False)])
def test_webapp_http_status_is_about_app(monkeypatch, code, alive):
    monkeypatch.syspath_prepend(str(PKG / 'system_essentials'))
    mod = load('system_essentials', 'webapp_registry')
    monkeypatch.setattr(mod, '_all_entries', lambda: [{'title': 'fixture', 'url': 'https://fixture.invalid'}])
    import requests
    monkeypatch.setattr(requests, 'get', lambda *a, **k: SimpleNamespace(status_code=code, close=lambda: None))
    assert mod.op_status({})['items'][0]['alive'] is alive


def test_webapp_concurrent_registration_preserves_entries(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(PKG / 'system_essentials'))
    mod = load('system_essentials', 'webapp_registry')
    monkeypatch.setattr(mod, '_MANUAL_PATH', tmp_path / 'webapps.json')
    monkeypatch.setattr(mod, '_derived', lambda: [])
    # 원장 관측도 라이브에 남기지 않는다.
    monkeypatch.setitem(sys.modules, 'write_ledger', SimpleNamespace(log_write=lambda *a, **k: None))
    original = mod._load_manual
    def slow_read():
        rows = original()
        time.sleep(.01)
        return rows
    monkeypatch.setattr(mod, '_load_manual', slow_read)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda i: mod.op_register({'name': str(i), 'url': f'https://fixture.invalid/{i}'}), range(16)))
    assert all(r['success'] for r in results)
    assert len(mod.op_list({})['items']) == 16
    assert mod.op_remove({'name': '0'})['success']
    assert len(mod.op_list({})['items']) == 15


def test_weather_wind_unit_and_zero_longitude(monkeypatch):
    mod = load('location-services')
    calls = []
    def get(url, **kwargs):
        calls.append(kwargs['params'])
        return SimpleNamespace(ok=True, json=lambda: {'current': {'wind_speed_10m': 2}, 'daily': {}})
    monkeypatch.setattr(mod.requests, 'get', get)
    result = json.loads(mod.execute({'lat': 51, 'lon': 0}, SimpleNamespace(tool_name='get_weather')))
    assert result['success']
    assert calls[0]['longitude'] == 0 and calls[0]['wind_speed_unit'] == 'ms'
    assert result['current']['wind_speed'] == 2 and result['current']['wind_speed_unit'] == 'm/s'


def test_weather_requests_display_unit(monkeypatch):
    mod = load('location-services')
    calls = []
    monkeypatch.setattr(mod.requests, 'get', lambda *a, **k: calls.append(k['params']) or SimpleNamespace(ok=True, json=lambda: {'current': {}, 'daily': {}}))
    assert mod.get_weather_openmeteo(lat=37, lon=127)['success']
    assert calls[0]['wind_speed_unit'] == 'ms'


def test_blog_content_title_and_unknown_op(monkeypatch):
    mod = load('blog')
    calls = []
    monkeypatch.setitem(sys.modules, 'tool_blog_rag', SimpleNamespace(get_post_content=lambda **k: calls.append(k) or {'success': True}))
    monkeypatch.setattr(mod, '_op_posts', lambda *a: pytest.fail('unknown op must not list posts'))
    ctx = SimpleNamespace(tool_name='blog_op')
    assert json.loads(mod.execute({'op': 'search', 'mode': 'content', 'title': 'fixture'}, ctx))['success']
    assert calls == [{'post_id': 'fixture'}]
    assert json.loads(mod.execute({'op': 'typo'}, ctx))['success'] is False


def test_blog_unknown_op_refused(monkeypatch):
    mod = load('blog')
    monkeypatch.setattr(mod, '_op_posts', lambda *a: pytest.fail('unknown op must not list posts'))
    assert json.loads(mod.execute({'op': 'typo'}, SimpleNamespace(tool_name='blog_op')))['success'] is False


def test_portal_intro_can_be_cleared(monkeypatch):
    mod = load('community-portal')
    portal = {'intro': 'old', 'limits': {}}
    state = {'portals': [portal]}
    def mutate(fn):
        fn(state)
        return state
    core = SimpleNamespace(ensure_default_portal=lambda s: portal, portal_by_ref=lambda *a: portal, mutate_state=mutate)
    monkeypatch.setattr(mod, '_core', lambda: core)
    monkeypatch.setattr(mod, '_portal_kv', lambda *a: {})
    assert json.loads(mod._fn_config({'intro': ''}))['success']
    assert portal['intro'] == ''


def test_portal_audit_filters_before_limit(tmp_path, monkeypatch):
    core = load('community-portal', 'portal_core')
    monkeypatch.setattr(core, '_AUDIT_PATH', tmp_path / 'audit.jsonl')
    entries = [{'portal': 'AAAAA', 'who': 'old', 'ok': True}, {'portal': 'BBBBB', 'who': 'new', 'ok': True}]
    core._AUDIT_PATH.write_text('\n'.join(json.dumps(e) for e in entries))
    handler = load('community-portal')
    monkeypatch.setattr(handler, '_core', lambda: core)
    monkeypatch.setattr(core, 'load_state', lambda: {'portals': [{'slug': 'AAAAA', 'title': 'A', 'id': 'a'}]})
    result = json.loads(handler.execute({'op': 'audit', 'portal': 'A', 'limit': 1}, SimpleNamespace(tool_name='portal_op')))
    assert 'old' in result['items'][0]['title'] and 'AAAAA' in result['items'][0]['meta']
    assert json.loads(handler._fn_audit({'limit': 0}))['items'] == []
    assert json.loads(handler._fn_audit({'portal': 'missing'}))['success'] is False


def test_patch_post_apply_verification_failure_is_reported(tmp_path, monkeypatch):
    mod = load('system_essentials', 'repair_staging')
    live, staged = tmp_path / 'live.py', tmp_path / 'staged.py'
    live.write_text('old\n')
    staged.write_text('new\n')
    sess = {'files': {str(live): {'staged': str(staged), 'rel': 'live.py'}}, 'worktree': 'fixture'}
    saved = []
    monkeypatch.setattr(mod, '_save_session', lambda repo, s: saved.append(dict(s)))
    monkeypatch.setattr(mod, '_cleanup_old', lambda *a: None)
    monkeypatch.setattr(mod, 'sync_live_derived', lambda *a: {'gate': 'live_derived', 'passed': False, 'detail': 'fixture failure'})
    result = mod._perform_apply(str(tmp_path), sess, [], None, None)
    assert live.read_text() == 'new\n' and result['applied'] is True
    assert result['success'] is False and result['verified'] is False and result['error']
    assert saved[0]['verified'] is False
    monkeypatch.setattr(mod, 'read_session', lambda *a: saved[0])
    again = mod.perform_scheduled_apply(str(tmp_path), 'fixture')
    assert again['success'] is False and again['applied'] is True


def test_patch_parallel_proposals_have_distinct_sessions(tmp_path, monkeypatch):
    mod = load('system_essentials', 'repair_staging')
    barrier = threading.Barrier(2)
    sessions = {}
    monkeypatch.setattr(mod, '_is_git_repo', lambda *a: True)
    monkeypatch.setattr(mod, 'read_session', lambda *a: None)
    monkeypatch.setattr(mod, 'datetime', SimpleNamespace(now=lambda: SimpleNamespace(strftime=lambda *a: 'same_second')))
    def stage(repo, key, target):
        barrier.wait(timeout=5)
        path = tmp_path / (key + '.py')
        sessions[key] = {'worktree': '.', 'files': {}}
        return str(path)
    monkeypatch.setattr(mod, 'stage_file', stage)
    monkeypatch.setattr(mod, 'load_session', lambda repo, key: sessions[key])
    monkeypatch.setattr(mod, '_git', lambda *a: SimpleNamespace(stdout='diff'))
    monkeypatch.setattr(mod, 'verify', lambda *a: (True, []))
    monkeypatch.setattr(mod, '_save_session', lambda *a: None)
    def propose(i):
        return mod.op_propose({'_repo_root': str(tmp_path), '_red_check': lambda p: 'red',
                               'path': 'backend/x.py', 'content': str(i), 'reason': 'fixture'})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(propose, range(2)))
    assert all(r['success'] for r in results)
    assert results[0]['proposal_id'] != results[1]['proposal_id']


@pytest.mark.parametrize('result, expected', [
    ({'success': True, 'final_result': {'items': [{'id': 1}]}}, True),
    ({'success': False, 'error': 'fixture failure'}, False),
    ('{"success": false, "message": "fixture failure"}', False),
])
def test_channel_trigger_project_and_result_history(tmp_path, monkeypatch, result, expected):
    import channel_poller as mod
    import calendar_actions
    import trigger_engine
    import workflow_engine
    poller = object.__new__(mod.ChannelPoller)
    poller._log = lambda *a: None
    runs, calls = [], []
    monkeypatch.setattr(mod, 'threading', SimpleNamespace(Thread=lambda target, **k: SimpleNamespace(start=target)))
    monkeypatch.setattr(calendar_actions.CalendarActionsMixin, '_owner_run_path', staticmethod(lambda pid: str(tmp_path / pid)))
    monkeypatch.setattr(workflow_engine, 'execute_pipeline', lambda steps, path, **k: runs.append((path, k)) or result)
    monkeypatch.setattr(trigger_engine, 'add_history', lambda *a, **k: calls.append((a, k)))
    mod.ChannelPoller._fire_channel_pipeline.__wrapped__(poller, {
        'id': 'fixture', 'name': 'fixture', 'pipeline': '[self:time]{}', 'project_id': 'project'
    }, 'gmail', 'sender', 'subject', 'body')
    assert runs[0][0] == str(tmp_path / 'project')
    assert 'subject' in runs[0][1]['context']['_prev_result']
    assert len(calls) == 1 and calls[0][0][2] is expected
    if not expected:
        assert calls[0][1]['error']
    else:
        assert calls[0][1]['count'] == 1


def test_channel_trigger_parse_failure_is_logged(monkeypatch):
    import channel_poller as mod
    import trigger_engine
    poller = object.__new__(mod.ChannelPoller)
    poller._log = lambda *a: None
    calls = []
    monkeypatch.setattr(mod, 'threading', SimpleNamespace(Thread=lambda target, **k: SimpleNamespace(start=target)))
    monkeypatch.setattr(trigger_engine, 'add_history', lambda *a, **k: calls.append((a, k)))
    mod.ChannelPoller._fire_channel_pipeline.__wrapped__(poller, {
        'id': 'fixture', 'name': 'fixture', 'pipeline': '[self:time]{broken: '
    }, 'gmail', 'sender', 'subject', 'body')
    assert len(calls) == 1 and calls[0][0][2] is False and calls[0][1]['error']


def test_channel_trigger_subject_filter(monkeypatch):
    import channel_poller as mod
    import trigger_engine
    poller = object.__new__(mod.ChannelPoller)
    poller._log = lambda *a: None
    poller._fired_channel_triggers = set()
    calls = []
    poller._fire_channel_pipeline = lambda *a: calls.append(a)
    monkeypatch.setattr(trigger_engine, 'load_triggers', lambda: {'triggers': [
        {'id': 'fixture', 'type': 'channel', 'enabled': True, 'config': {'subject_contains': 'INVOICE'}}]})
    poller._check_channel_triggers('gmail', 'sender', 'unrelated', 'invoice in body only', 'one')
    assert not calls
    poller._check_channel_triggers('gmail', 'sender', 'New invoice', 'body', 'two')
    assert len(calls) == 1


def test_channel_trigger_dry_run_uses_type_specific_config(monkeypatch):
    from api_ibl import validate_code
    import trigger_engine
    payload = '[self:trigger]{op:"create", type:"channel", name:"fixture", config:{repeat:"source-rule"}, do:"[self:time]{}"}'
    assert validate_code(payload)['valid']
    monkeypatch.setattr(trigger_engine, 'load_triggers', lambda: {'triggers': [
        {'id': 'fixture', 'type': 'channel'}]})
    assert validate_code('[self:trigger]{op:"update", id:"fixture", config:{repeat:"source-rule"}}')['valid']


def test_failed_patch_verification_reaches_restart_controller(tmp_path, monkeypatch):
    import restart_red as mod
    import red_watchdog
    path = tmp_path / 'manifest.json'
    path.write_text('{}')
    monkeypatch.setattr(mod, 'manifest_path', lambda *a: path)
    monkeypatch.setattr(mod, 'read_json', lambda *a: {'owner': 'fixture', 'files': {'x': 'fixture'}})
    monkeypatch.setattr(mod, 'inspect_job', lambda *a: {'controller_apply': {
        'applied': True, 'success': False, 'verified': False, 'error': 'derived failed', 'checks': []}})
    monkeypatch.setattr(red_watchdog, '_touches_safety', lambda *a: False)
    state = {'generation': 'fixture', 'request': {'operation': 'red_apply', 'payload': {'job_path': 'fixture'}}}
    assert mod.verify_after_boot(tmp_path, state) is False
    assert json.loads(path.with_name('result.json').read_text())['outcome'] == 'verification_failed'


def test_patch_delete_failure_is_not_reported_as_removed(tmp_path, monkeypatch):
    mod = load('system_essentials', 'repair_staging')
    path = tmp_path / 'keep.py'
    path.write_text('original')
    original = mod.os.remove
    def remove(target):
        if str(target) == str(path):
            raise PermissionError('fixture')
        return original(target)
    monkeypatch.setattr(mod.os, 'remove', remove)
    monkeypatch.setattr(mod, '_save_session', lambda *a: pytest.fail('failed deletion marked applied'))
    with pytest.raises(OSError, match='삭제 실패'):
        mod._perform_apply(str(tmp_path), {'files': {str(path): {'op': 'delete', 'rel': path.name}}}, [], None, None)
    assert path.read_text() == 'original'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
