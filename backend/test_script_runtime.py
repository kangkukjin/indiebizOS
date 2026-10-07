"""Same registered script value and contract in foreground and detached execution."""
import boot_paths  # noqa: F401
import json
import sys
import pytest
from test_script_operation_outcomes import load, PKG, ops  # noqa: F401


@pytest.mark.parametrize('protocol', ['registered-json/1', 'ibl-script/2'])
def test_contract_preserves_full_background_value_and_rejects_wrong_type(ops, monkeypatch, tmp_path, protocol):
    contract = {'version': 1, 'params': {'n': 'Number'}, 'result': {'answer': 'Number'},
                'effects': ['pure'], 'adapter': {'protocol': protocol}}
    entry = {'file': 'check.py', 'interpreter': 'python', 'callable_contract': contract}
    monkeypatch.setattr(ops, '_read_registry', lambda: {'check': entry})
    script = ops._SCRIPT_DIR / 'check.py'
    script.write_text('import json,sys\na=json.load(sys.stdin)\na=a.get("args",a)\nv={"answer":a["n"]*2}\n'
                      + ('print(json.dumps({"protocol":"ibl-script/2","ok":True,"value":v}))' if protocol == 'ibl-script/2' else 'print(json.dumps(v))'))
    foreground = ops.op_run({'id': 'check', 'args': {'n': 7}, '_ibl_edition': 2})
    assert foreground['success'] and foreground['value'] == {'answer': 14}
    assert not ops.op_run({'id': 'check', 'args': {'n': 'bad'}, '_ibl_edition': 2})['success']
    # The real detached runner reads only its persisted job; no parent state.
    runner = load(PKG / '_bg_runner.py')
    monkeypatch.setattr(runner, '_announce', lambda job: None)
    job = tmp_path / 'job.json'
    stdin = ops._runtime.v2_input(entry, {'n': 7})
    job.write_text(json.dumps({'job_id': 'j', 'script': str(script), 'interpreter': sys.executable,
                              'stdin': json.dumps(stdin), 'log': str(tmp_path / 'job.log'),
                              'value_edition': 2, 'callable_contract': contract}))
    monkeypatch.setattr(sys, 'argv', ['runner', str(job)])
    runner.main()
    result = json.loads(job.read_text())
    assert result['status'] == 'done' and result['result'] == foreground['value']


def test_legacy_background_arbitrary_json_is_not_truncated_to_stdout(ops, monkeypatch, tmp_path):
    runner = load(PKG / '_bg_runner.py')
    monkeypatch.setattr(runner, '_announce', lambda job: None)
    script = ops._SCRIPT_DIR / 'check.py'
    script.write_text('import json; print(json.dumps({"payload": "x"*20000}))')
    job = tmp_path / 'job.json'
    job.write_text(json.dumps({'job_id': 'j', 'script': str(script), 'interpreter': sys.executable,
                              'stdin': '{}', 'log': str(tmp_path / 'job.log'), 'value_edition': 2}))
    monkeypatch.setattr(sys, 'argv', ['runner', str(job)])
    runner.main()
    assert len(json.loads(job.read_text())['result']['payload']) == 20000


def test_discover_contract_check_run_and_changed_input_without_reading_source(ops, monkeypatch, tmp_path):
    import yaml
    import runtime_utils, ibl_v2_store, workflow_store
    from ibl_dependencies import script_contract
    from ibl_v2_adapters import Adapter, decode_envelope
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    from reusable_catalog import candidates
    root = tmp_path / 'data/scripts'
    root.mkdir(parents=True)
    contract = {'version': 1, 'params': {'n': 'Number'}, 'result': {'answer': 'Number'},
                'effects': ['pure'], 'adapter': {'protocol': 'registered-json/1'}}
    entry = {'file': 'opaque.py', 'interpreter': 'python', 'description': 'sensor calibration multiply', 'callable_contract': contract}
    (root / 'opaque.py').write_text('import sys,json; a=json.load(sys.stdin); print(json.dumps({"answer":a["n"]*2}))')
    (root / 'registry.yaml').write_text(yaml.safe_dump({'opaque': entry}))
    monkeypatch.setattr(runtime_utils, 'get_base_path', lambda: tmp_path)
    monkeypatch.setattr(workflow_store, '_get_workflows_path', lambda: tmp_path / 'workflows')
    monkeypatch.setattr(ops, '_SCRIPT_DIR', root)
    monkeypatch.setattr(ops, '_read_registry', lambda: {'opaque': entry})
    found = candidates('sensor calibration')
    assert found[0]['id'] == 'script:opaque' and found[0]['contract']['result'] == {'answer': 'Number'}
    base = {'version': 1, 'params': {'id': 'Text', 'args': 'Record'}, 'result': 'Unknown',
            'effects': ['unknown'], 'adapter': {'protocol': 'ibl-script/2', 'value_path': '/value'}}
    def invoke(rt, args):
        return decode_envelope(ops.op_run({**args, '_ibl_edition': 2}), base['adapter'], args)[0]
    registry = {'self:script': Adapter(base, invoke, specialize=script_contract)}
    for n in (7, 11):
        code = f'$x=[self:script]{{id:"opaque",args:{{n:{n}}}}}\nassert $x.answer == {n*2}\nreturn $x.answer'
        plan = compile_program(code, registry)
        assert not plan.issues, plan.report()
        result = Runtime(plan).run()
        assert result['success'] and result['value'] == n*2, result
        assert result['capability_usage'] == [{'id': 'script:opaque', 'success': True}]
    assert compile_program('[self:script]{id:"opaque",args:{n:"bad"}}', registry).issues
    contract.update(defaults={'n': 3}, aliases={'value': 'n'}, enums={'n': [3, 7]})
    (root / 'registry.yaml').write_text(yaml.safe_dump({'opaque': entry}))
    for args, expected in [('{}', 6), ('{value:7}', 14)]:
        plan = compile_program('[self:script]{id:"opaque",args:' + args + '}', registry)
        assert not plan.issues, plan.report()
        assert Runtime(plan).run()['value'] == {'answer': expected}
    assert compile_program('[self:script]{id:"opaque",args:{value:8}}', registry).issues


def test_background_typed_business_failure_field_is_data_and_null_is_preserved(ops):
    ops._JOB_DIR.mkdir()
    for name, value in [('business', {'operation_outcome': {'status': 'failed'}}), ('null', None)]:
        (ops._JOB_DIR / (name + '.json')).write_text(json.dumps({
            'job_id': name, 'status': 'done', 'result': value,
            'callable_contract': {'adapter': {'protocol': 'ibl-script/2'}}}))
        out = ops.op_status({'job_id': name})
        assert out['success'] and out['result'] == value and not out.get('operation_outcomes')


def test_plain_contract_preserves_legacy_permission_evidence(ops, monkeypatch):
    contract = {'version': 1, 'params': {}, 'result': 'Record', 'effects': ['unknown'],
                'adapter': {'protocol': 'registered-json/1'}}
    monkeypatch.setattr(ops, '_read_registry', lambda: {'check': {
        'file': 'check.py', 'interpreter': 'python', 'callable_contract': contract}})
    (ops._SCRIPT_DIR / 'check.py').write_text('import json; print(json.dumps({"success":False,"denied":True,"error_type":"permission","error":"no"}))')
    result = ops.op_run({'id': 'check', '_ibl_edition': 2})
    assert not result['success'] and result['denied'] and result['error_type'] == 'permission'


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
