"""외부 PC 관용구: 실제 IBL 어댑터·실행기와 가짜 원격 응답으로 재전송·해제 경계를 검사."""
import boot_paths  # noqa: F401
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FILES = {row['alias']: next(p.name for p in (ROOT / 'data/idioms').glob('guestpc_*.ibl')
          if f"[def:{row['alias']}]" in p.read_text())
         for row in json.loads((ROOT / 'data/idioms/guestpc_seeds.json').read_text()) if row.get('alias')}


@pytest.fixture
def remote(monkeypatch, tmp_path):
    import ibl_engine
    import task_receipts as tasks
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    from ibl_edition import source_context

    state = dict(connected=True, state='running', result=None, fail_observation=False,
                 helper_exited=True, os='windows')
    calls = []
    job = dict(limb='guest-fixture', limb_name='사무실PC',
               task_ref={'kind': 'guestpc', 'task_id': 'job-1'})

    def leaf(step, *args, **kwargs):
        action = f"{step['_node']}:{step['action']}"
        p = step['params']
        calls.append((action, p))
        if action == 'self:limb':
            assert p['op'] == 'list'
            return {'success': True, 'items': [
                {'device_id': job['limb'], 'alias': job['limb_name'], 'connected': state['connected'], 'registration': state.get('registration')},
                {'device_id': 'other', 'alias': '다른PC', 'connected': True}]}
        if action == 'limbs:guestpc':
            assert p['limb'] in (job['limb'], job['limb_name'])
            if p['op'] == 'info':
                return {'success': True, **job, 'result': {'os': state['os'], 'cwd': '/fixture'}}
            if p['op'] == 'shell':
                return tasks.receipt('guestpc', 'job-1', limb=job['limb'], limb_name=job['limb_name'])
            if p['op'] == 'detach':
                return {'success': True, 'helper_exited': state['helper_exited']}
        if action == 'self:task':
            assert p['op'] == 'wait' and p['ref'] == job['task_ref']
            if state['fail_observation']:
                return {'success': False, 'error': '연결 오류'}
            return {'success': True, **tasks.view(p['ref'], state['state'], result=state['result'],
                                                progress={'tail': 'fixture progress'}),
                    'timed_out': state['state'] == 'running'}
        raise AssertionError((action, p))

    monkeypatch.setattr(ibl_engine, 'execute_ibl', leaf)
    registry = load_registry(str(tmp_path))
    definitions = {name: (ROOT / 'data/idioms' / file).read_text() for name, file in FILES.items()}

    def run(code, **inputs):
        plan = compile_program(code, registry, inputs=inputs, definitions=definitions)
        assert not plan.issues, plan.report()
        with source_context(2):
            out = Runtime(plan, inputs).run()
        assert out['success'], out
        return out['value']

    run.calls, run.state, run.job = calls, state, job
    return run


@pytest.mark.parametrize('os', ['windows', 'darwin', 'linux'])
def test_prepare_pins_selected_device_without_guessing_os(remote, os):
    remote.state['os'] = os
    out = remote('[fn:외부PC준비]{PC:"사무실PC"}')
    assert out['ok'] and out['env']['os'] == os
    assert remote.calls[-1][1]['limb'] == 'guest-fixture'


@pytest.mark.parametrize('pc,connected,status', [('', True, 'invalid_input'),
                                              ('없는PC', True, 'target_not_unique'),
                                              ('사무실PC', False, 'offline')])
def test_prepare_never_falls_back_to_another_pc(remote, pc, connected, status):
    remote.state['connected'] = connected
    assert remote('[fn:외부PC준비]{PC:$pc}', pc=pc)['status'] == status
    assert not any(a == 'limbs:guestpc' for a, _ in remote.calls)


def test_submit_once_and_resume_after_failed_observation(remote):
    remote.state['fail_observation'] = True
    out = remote(
        '[fn:외부PC작업실행]{PC:"사무실PC",명령:"echo hello",작업폴더:"C:/Work Dir",셸:"powershell",대기:10}')
    assert out['ok'] and out['observation']['status'] == 'observation_failed'
    assert out['task_ref'] == remote.job['task_ref']
    shell = [p for a, p in remote.calls if a == 'limbs:guestpc'][0]
    assert shell['background'] is True and shell['cwd'] == 'C:/Work Dir'
    assert shell['shell'] == 'powershell' and shell['timeout'] == 1800
    remote.state.update(fail_observation=False, state='succeeded', result={'exit': 0, 'stdout': 'hello'})
    checked = remote('[fn:외부PC작업확인]{작업:$job,대기:30}', job=out)
    assert checked['command_ok'] is True
    assert sum(a == 'limbs:guestpc' and p['op'] == 'shell' for a, p in remote.calls) == 1


@pytest.mark.parametrize('state,result,settled,command_ok', [
    ('running', None, False, None), ('unknown', None, False, None),
    ('failed', None, True, False), ('cancelled', None, True, False),
    ('succeeded', None, True, None), ('succeeded', {'exit': 0}, True, True),
    ('succeeded', {'exit': 7}, True, False),
    ('succeeded', {'exit': 0, 'timeout': True}, True, False),
    ('succeeded', {'error': 'spawn failed'}, True, None),
])
def test_receipt_completion_is_not_command_success(remote, state, result, settled, command_ok):
    remote.state.update(state=state, result=result)
    out = remote('[fn:외부PC작업확인]{작업:$job}', job=remote.job)
    assert out['settled'] is settled and out['command_ok'] is command_ok
    assert out['result'] == result
    assert [a for a, _ in remote.calls] == ['self:task']


@pytest.mark.parametrize('state', ['running', 'unknown'])
def test_finish_does_not_detach_unfinished_jobs(remote, state):
    remote.state['state'] = state
    out = remote('[fn:외부PC작업마무리]{PC:"사무실PC",작업들:[$job],해제:true}', job=remote.job)
    assert out['status'] == 'unfinished' and not out['detached']
    assert not any(a == 'limbs:guestpc' for a, _ in remote.calls)


def test_finish_rejects_mixed_targets_and_empty_jobs(remote):
    other = {**remote.job, 'limb': 'other'}
    for jobs, pc in [([], '사무실PC'), ([remote.job, other], '사무실PC'), ([remote.job], '다른PC')]:
        out = remote('[fn:외부PC작업마무리]{PC:$pc,작업들:$jobs,해제:true}', pc=pc, jobs=jobs)
        assert not out['ok'] and not out['detached']
    assert not remote.calls


def test_finish_keeps_failed_command_evidence_when_detaching(remote):
    remote.state.update(state='succeeded', result={'exit': 9, 'stderr': 'build failed'})
    out = remote('[fn:외부PC작업마무리]{PC:"사무실PC",작업들:[$job],해제:true}', job=remote.job)
    assert out['detached'] and not out['ok'] and not out['commands_ok']
    assert out['items'][0]['result']['stderr'] == 'build failed'


def test_finish_does_not_detach_when_observation_fails(remote):
    remote.state['fail_observation'] = True
    out = remote('[fn:외부PC작업마무리]{PC:"사무실PC",작업들:[$job],해제:true}', job=remote.job)
    assert out['status'] == 'unfinished'
    assert out['items'][0]['task_ref'] == remote.job['task_ref']
    assert not any(a == 'limbs:guestpc' for a, _ in remote.calls)


@pytest.mark.parametrize('detach,confirmed', [(False, True), (True, True), (True, False)])
def test_finish_distinguishes_requested_and_confirmed_detach(remote, detach, confirmed):
    remote.state.update(state='succeeded', result={'exit': 0}, helper_exited=confirmed)
    out = remote('[fn:외부PC작업마무리]{PC:"사무실PC",작업들:[$job],산출물:["C:/out.txt"],해제:$detach}',
                 job=remote.job, detach=detach)
    assert out['detached'] is (detach and confirmed)
    assert out['ok'] is (not detach or confirmed)
    assert out['artifacts'] == ['C:/out.txt'] and not out['artifacts_verified']
    detaches = [p for a, p in remote.calls if a == 'limbs:guestpc']
    assert len(detaches) == int(detach)
    if detaches:
        assert detaches[0]['limb'] == 'guest-fixture'


def test_invalid_wait_does_not_submit_command(remote):
    out = remote('[fn:외부PC작업실행]{PC:"사무실PC",명령:"echo hello",작업폴더:"C:/",대기:241}')
    assert not out['ok'] and not remote.calls


def test_seed_sources_match_files():
    seeds = json.loads((ROOT / 'data/idioms/guestpc_seeds.json').read_text())
    for row in seeds:
        assert not row.get('always_on', False)
        if row.get('alias'):
            assert row['ibl_code'] == (ROOT / 'data/idioms' / FILES[row['alias']]).read_text().strip()


@pytest.mark.parametrize('name', ['prepare', 'run', 'check', 'finish'])
def test_guide_examples_execute_with_real_ibl_adapters(remote, name):
    text = (ROOT / 'data/guides/guest_helper.md').read_text()
    examples = dict(re.findall(r'<!-- example:guestpc_(\w+) -->\s*```ibl\n(.*?)\n```', text, re.S))
    remote.state.update(state='succeeded', result={'exit': 0, 'stdout': 'HELPER_OK'})
    out = remote(examples[name], 작업=remote.job)
    assert out['ok']


@pytest.mark.parametrize('patch', [{'limb': ''}, {'task_ref': {'kind': 'script', 'task_id': '1'}},
                                 {'task_ref': {'kind': 'guestpc', 'task_id': ''}}])
def test_invalid_receipt_is_not_observed(remote, patch):
    out = remote('[fn:외부PC작업확인]{작업:$job}', job={**remote.job, **patch})
    assert out['status'] == 'invalid_input' and not out['settled']
    assert not remote.calls



def test_prepare_rejects_network_appliance_without_guestpc_call(remote):
    remote.state["registration"] = {"adapter": "network-api", "state": "active"}
    result = remote('[fn:외부PC준비]{PC:"사무실PC",환경조회:false}')
    assert not result["ok"] and result["status"] == "unsupported_target"
    assert not any(a == "limbs:guestpc" for a, _ in remote.calls)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
