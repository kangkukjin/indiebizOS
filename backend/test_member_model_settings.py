"""회원 설정의 독립성·실행 경로·관리 권한과 PC별 통계의 날짜 경계를 검증한다."""
import boot_paths  # noqa: F401
import copy
import json
import threading
from datetime import date, timedelta

import pytest
import model_resolver as M
import member_model_settings as settings
import member_runtime
import principal
from test_api_member_pcs import client, register, HEADERS  # noqa: F401


@pytest.fixture
def models(tmp_path, monkeypatch):
    monkeypatch.setenv('INDIEBIZ_MODEL_CONFIG_ROOT', str(tmp_path))
    monkeypatch.setattr(M, 'get_base_path', lambda: tmp_path)
    data = tmp_path / 'data'
    data.mkdir(exist_ok=True)
    gear = copy.deepcopy(M._DEFAULT_GEAR)
    gear['current_gear'] = '최대'
    gear['overrides'] = {'owner-project:agent': '경량'}
    (data / 'model_gear.json').write_text(json.dumps(gear))
    for tier, filename in gear['tiers'].items():
        (data / filename).write_text(json.dumps({'provider': 'google', 'model': 'owner-' + tier,
                                                'enabled': True, 'apiKey': ''}))
    return data


def test_separate_fleet_settings_and_task_snapshot(client, models, tmp_path):
    original = {p.name: p.read_bytes() for p in models.iterdir() if p.suffix == '.json'}
    config = client.get('/member-pcs/models', headers=HEADERS).json()
    for tier, value in config['models'].items():
        assert value['model'] == 'owner-' + tier
        value['model'] = 'member-' + tier
    response = client.put('/member-pcs/models', headers=HEADERS, json=config)
    assert response.status_code == 200, response.text
    assert client.put('/member-pcs/model-gear', headers=HEADERS, json={'gear': '균형'}).status_code == 200
    assert M.resolve('execution')['model'] == 'owner-고급'
    with principal.narrow(principal.member('member', None, 'pc')):
        with member_runtime.turn_scope(tmp_path / 'turn1', 'pc', 'task1', threading.Event(), {}):
            assert M.resolve_agent_ai({}, 'member', 'agent')['model'] == 'member-중급'
            assert M.resolve('classify')['model'] == 'member-경량'
            assert M.resolve('consciousness')['model'] == 'member-중급'
            assert M.resolve('evaluate')['model'] == 'member-경량'
            assert M.resolve_compat_model('system')['model'] == 'member-고급'
            assert M.get_overrides() == {}
            # 관리자 변경을 흉내 내도 진행 중인 턴은 변하지 않는다.
            with settings.scope(), settings.lock:
                assert M.set_gear('절약')
                M.set_consciousness(False)
            assert M.get_gear() == '균형'
            assert M.consciousness_enabled()
        with member_runtime.turn_scope(tmp_path / 'turn2', 'pc', 'task2', threading.Event(), {}):
            assert M.resolve('execution')['model'] == 'member-경량'
            assert not M.consciousness_enabled()
    assert M.get_gear() == '최대' and M.consciousness_enabled()
    for name, content in original.items():
        assert (models / name).read_bytes() == content
    # 중앙 모델을 나중에 바꿔도 회원 설정은 유지한다.
    (models / 'system_ai_config.json').write_text('{"provider":"google","model":"changed"}')
    with settings.scope():
        assert M.resolve_compat_model('system')['model'] == 'member-고급'


def test_member_config_owner_gate_validation_and_secret_storage(client, models, monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    routes = [('/models', 'GET', None), ('/models', 'PUT', {}),
              ('/model-gear', 'GET', None), ('/model-gear', 'PUT', {'gear': '절약'}),
              ('/model-gear/presets', 'PUT', {}), ('/model-gear/consciousness', 'PUT', {'enabled': False})]
    for path, method, payload in routes:
        assert client.request(method, '/member-pcs' + path, json=payload).status_code == 403
        with principal.narrow(principal.member('member', None, 'pc')):
            assert client.request(method, '/member-pcs' + path, headers=HEADERS, json=payload).status_code == 403
    config = client.get('/member-pcs/models', headers=HEADERS).json()
    config['models']['고급']['apiKey'] = 'fake-test-key'
    result = client.put('/member-pcs/models', headers=HEADERS, json=config)
    assert result.status_code == 200
    assert 'fake-test-key' not in result.text
    assert 'fake-test-key' not in settings.path().read_text()
    assert 'fake-test-key' in (models.parent / '.env').read_text()
    config['models']['고급']['provider'] = 'codex'
    response = client.put('/member-pcs/models', headers=HEADERS, json=config)
    assert response.status_code == 200
    assert response.json()['models']['고급']['provider'] == 'codex'
    assert client.put('/member-pcs/model-gear', headers=HEADERS, json={'gear': 'bad'}).status_code == 400
    assert client.put('/member-pcs/model-gear/consciousness', headers=HEADERS, json={'enabled': 'false'}).status_code == 400
    assert client.put('/member-pcs/model-gear/presets', headers=HEADERS, json={'presets': {'절약': {'실행': '경량'}}}).status_code == 400
    presets = copy.deepcopy(M._DEFAULT_GEAR['presets'])
    presets['최대']['평가'] = '고급'
    result = client.put('/member-pcs/model-gear/presets', headers=HEADERS, json={'presets': presets})
    assert result.status_code == 200 and result.json()['axes']['평가']['model'] == 'owner-고급'
    assert M.resolve('evaluate')['tier'] == '경량'


def test_statistics_month_boundary_history_and_pc_isolation(client, tmp_path):
    import member_activity as activity
    first = register(client)
    second = register(client, name='다른 PC')
    today = date.today()
    days = {(today - timedelta(days=age)).isoformat(): {'tokens': tokens, 'turns': 1}
            for age, tokens in ((0, 120000), (29, 80000), (30, 50000), (-1, 90000))}
    (tmp_path / 'data/member_usage.json').write_text(json.dumps({first['device_id']: days}))
    for i in range(52):
        key = f'task-{i:03}'
        activity.begin(tmp_path, key, first['device_id'], first['device_id'], '업무 PC', key, f'작업 {i}')
        activity.finish(tmp_path, key, 'failed' if i == 51 else 'completed', i * 1000, [])
    activity.begin(tmp_path, 'other', second['device_id'], second['device_id'], '다른 PC', 'other', '다른 사람 요청')
    # 회원 신원이 같아도 다른 기기의 상세는 노출하지 않는다.
    activity.begin(tmp_path, 'wrong-device', first['device_id'], 'wrong-device', '별도 기기', '', '보이지 않아야 함')
    url = f"/member-pcs/{first['device_id']}/statistics"
    assert client.get(url).status_code == 403
    with principal.narrow(principal.member(first['device_id'], None, first['device_id'])):
        assert client.get(url, headers=HEADERS).status_code == 403
    result = client.get(url, headers=HEADERS).json()
    assert result['tokens_month'] == 200000 and result['turns_month'] == 2
    assert result['period_start'] == (today - timedelta(days=29)).isoformat()
    assert len(result['tasks']) == 50 and result['next_offset'] == 50
    assert result['tasks'][0]['status'] == 'failed' and result['tasks'][0]['tokens'] == 51000
    rest = client.get(url + '?offset=50', headers=HEADERS).json()
    assert len(rest['tasks']) == 2 and rest['next_offset'] is None
    assert not {t['id'] for t in result['tasks']} & {t['id'] for t in rest['tasks']}
    assert client.get(url + '?offset=-1', headers=HEADERS).status_code == 400
    empty = client.get(f"/member-pcs/{second['device_id']}/statistics", headers=HEADERS).json()
    assert empty['tokens_month'] == 0 and len(empty['tasks']) == 1
    (tmp_path / 'data/member_usage.json').write_text('broken')
    assert client.get(url, headers=HEADERS).status_code == 503


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
