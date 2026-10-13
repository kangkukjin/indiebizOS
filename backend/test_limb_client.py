"""IndieBiz OS 손발(폰) — 등록·IBL 봉투·거절·해제 계약 (docs/INDIEBIZ_BODY_AS_LIMB_DESIGN_2026_10_13.md)."""
import boot_paths  # noqa: F401
import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import api_resident_pcs
import device_registry
import limb_keys
import limb_client
import resident_pcs as pcs
import resident_store


@pytest.fixture
def hub(tmp_path, monkeypatch):
    monkeypatch.setattr(limb_keys, '_store_path', lambda: tmp_path / 'keys.json')
    monkeypatch.setattr(limb_keys, '_cache', None)
    monkeypatch.setenv('INDIEBIZ_RUNTIME_STATE_DIR', str(tmp_path))
    monkeypatch.setattr(device_registry, 'register', lambda *a, **k: None)
    app = FastAPI()
    app.include_router(api_resident_pcs.router)
    return TestClient(app)


@pytest.fixture
def phone_env(tmp_path, monkeypatch):
    ud = tmp_path / 'phone' / 'userdata'
    ud.mkdir(parents=True)
    monkeypatch.setenv('INDIEBIZ_USERDATA', str(ud))
    monkeypatch.setattr(limb_client, '_body_profile', lambda: 'phone')
    return ud


def _enroll_phone(alias='삼성1', iid='c' * 32):
    inv = limb_keys.resident_invite(alias, 0)
    return limb_keys.resident_enroll(inv['key'], iid, alias, kind='phone', adapter='indiebiz-v1')


def _client(hub, rec, execute, cfg_extra=None):
    cfg = {'hub': 'http://hub', 'key': rec['key'], 'installation_id': rec['registration']['installation_id'],
           'alias': rec['alias'], 'device_id': rec['device_id'], **(cfg_extra or {})}
    limb_client.config_path().parent.mkdir(parents=True, exist_ok=True)
    limb_client.config_path().write_text(json.dumps(cfg), encoding='utf-8')

    def post(path, payload, timeout):
        r = hub.post(f'/limb/resident/{path}', json=payload)
        if r.status_code != 200:
            raise limb_client.LimbError(str(r.json().get('detail')), r.status_code)
        return r.json()
    return limb_client.LimbClient(cfg, 8765, post=post, execute=execute, card=lambda: {'identity': {'body': 'phone'}})


def test_phone_registration_runs_ibl_and_reports_result(hub, phone_env):
    rec = _enroll_phone()
    assert rec['registration']['adapter'] == 'indiebiz-v1' and rec['registration']['kind'] == 'phone'
    seen = []

    def execute(code, agent_id, timeout):
        seen.append((code, agent_id, timeout))
        return {'success': True, 'items': [{'ok': True}], 'message': '진동 400ms'}
    c = _client(hub, rec, execute)
    receipt = pcs.submit(rec['device_id'], {'op': 'ibl', 'ibl': "[limbs:phone]{op:'vibrate'}", 'timeout': 30}, 'req-1')
    assert receipt['state'] == 'queued'
    c.step(inline=True, wait=0)          # 작업 수신 + inline 실행 → 사건 spool
    assert seen == [("[limbs:phone]{op:'vibrate'}", 'limb', 30.0)]
    c.step(inline=True, wait=0)          # 사건 상행 → 허브 원장 반영
    result = resident_store.wait_result(receipt['job_id'], timeout=0)
    assert result['items'] == [{'ok': True}]
    history = resident_store.history(job=receipt['job_id'])
    assert history['tasks'][0]['state'] == 'succeeded'
    assert not list((limb_client.spool_dir() / 'events').glob('*.json'))   # ack 받은 사건은 지워진다
    # 허브가 신고받은 capabilities 로 몸을 안다
    reg = limb_keys.get_by_device(rec['device_id'])['registration']
    assert reg['capabilities']['adapter'] == 'indiebiz-v1' and reg['capabilities']['shell'] is False


def test_phone_body_refuses_shell_and_helper_refuses_ibl(hub, phone_env):
    phone = _enroll_phone()
    with pytest.raises(ValueError, match='unsupported_on_this_body'):
        pcs.submit(phone['device_id'], {'op': 'shell', 'cmd': 'ls'}, 'req-s')
    with pytest.raises(ValueError, match='ibl_code_required'):
        pcs.submit(phone['device_id'], {'op': 'ibl', 'ibl': '  '}, 'req-e')
    inv = limb_keys.resident_invite('desk', 0)
    pc = limb_keys.resident_enroll(inv['key'], 'd' * 32)
    with pytest.raises(ValueError, match='unsupported_resident_operation'):
        pcs.submit(pc['device_id'], {'op': 'ibl', 'ibl': '[self:read]{}'}, 'req-p')
    # 손발 쪽도 모르는 봉투는 정직하게 거절(허브 관문을 우회해 큐에 들어와도)
    c = _client(hub, phone, lambda *a: {'success': True})
    out = c._dispatch({'id': 'x', 'code': json.dumps({'op': 'shell', 'cmd': 'rm -rf /'})})
    assert out['success'] is False and out['error'] == 'unsupported_on_this_body'
    assert c._dispatch({'id': 'y', 'code': json.dumps({'op': 'info'})})['adapter'] == 'indiebiz-v1'


def test_failure_envelope_projects_to_failed_task(hub, phone_env):
    rec = _enroll_phone()
    c = _client(hub, rec, lambda *a: {'success': False, 'error': '마이크 권한 없음'})
    receipt = pcs.submit(rec['device_id'], {'op': 'ibl', 'ibl': "[sense:listen]{op:'record'}"}, 'req-f')
    c.step(inline=True, wait=0); c.step(inline=True, wait=0)
    assert resident_store.history(job=receipt['job_id'])['tasks'][0]['state'] == 'failed'


def test_remove_from_hub_wipes_phone_credential(hub, phone_env):
    rec = _enroll_phone()
    c = _client(hub, rec, lambda *a: {'success': True})
    pcs.remove(rec['device_id'])
    c.step(inline=True, wait=0)
    assert c.stopped.is_set() and not limb_client.config_path().exists()
    assert limb_keys.get_by_device(rec['device_id'])['registration']['state'] == 'removed'


def test_revoke_from_hub_wipes_phone_credential(hub, phone_env):
    rec = _enroll_phone()
    c = _client(hub, rec, lambda *a: {'success': True})
    limb_keys.revoke(rec['device_id'])
    c.step(inline=True, wait=0)
    assert c.stopped.is_set() and not limb_client.config_path().exists()


def test_restart_during_execution_reports_unknown_not_rerun(hub, phone_env):
    rec = _enroll_phone()
    calls = []
    c = _client(hub, rec, lambda *a: calls.append(a) or {'success': True})
    receipt = pcs.submit(rec['device_id'], {'op': 'ibl', 'ibl': "[limbs:phone]{op:'vibrate'}"}, 'req-r')
    c.step(inline=False, wait=0)                       # 수신만(워커는 띄우되 기록은 queued/running)
    c.stop()
    c._worker and c._worker.join(5)
    # 실행 중 죽은 것처럼 기록을 running 으로 되돌린다
    c._record(receipt['job_id'], state='running')
    for p in (limb_client.spool_dir() / 'events').glob('*.json'):
        p.unlink()
    c2 = _client(hub, rec, lambda *a: calls.append(a) or {'success': True})
    before = len(calls)
    c2._recover()
    assert len(calls) == before                        # 재실행 없음
    c2.step(inline=True, wait=0)
    task = resident_store.history(job=receipt['job_id'])['tasks'][0]
    assert task['state'] == 'unknown' and task['result']['unknown'] is True


def test_pc_profile_never_becomes_a_limb(tmp_path, monkeypatch):
    monkeypatch.setattr(limb_client, '_body_profile', lambda: 'mac')
    monkeypatch.setenv('INDIEBIZ_USERDATA', str(tmp_path))
    limb_client.config_path().parent.mkdir(parents=True, exist_ok=True)
    limb_client.config_path().write_text(json.dumps({'hub': 'http://x', 'key': 'k', 'installation_id': 'i'}))
    assert limb_client.start(8765) is False


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
