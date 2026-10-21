"""등록 계약의 실제 값 경계와 첫 배포 부품의 호환성을 확인한다."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import boot_paths  # noqa: F401
import pytest
import yaml
from ibl_callable_contract import checked_values
from ibl_v2_adapters import validate_contract
from ibl_v2_types import guard
from ibl_v2_ir import Fault

ROOT = Path(__file__).resolve().parents[1]
REG = yaml.safe_load((ROOT / 'data/scripts/registry.yaml').read_text())


def call(name, args):
    contract, values = checked_values(REG[name]['callable_contract'], args)
    proc = subprocess.run([sys.executable, str(ROOT / 'data/scripts' / REG[name]['file'])],
                          input=json.dumps(values), text=True, capture_output=True, timeout=30)
    result = json.loads(proc.stdout)
    if result.get('success') is not False:
        guard(result, contract['result'], name)
    return result


@pytest.mark.parametrize('name', ['이미지변환','압축','PC제어부품','TV제어',
                                  'python_libraries','시험','의약품허가조회'])
def test_contracts_validate_and_keep_conservative_effects(name):
    contract = REG[name]['callable_contract']
    validate_contract(contract)
    if name in ['이미지변환','압축','PC제어부품','TV제어']:
        assert contract['effects'] == ['unknown']
        assert contract['result'] != 'Record' or contract.get('variants')


@pytest.mark.parametrize('name,args', [
    ('이미지변환',{'op':'info','path':'a','out_dir':'ignored'}),
    ('이미지변환',{'path':'a','width':50,'scale':.5}),
    ('압축',{'op':'list','path':'a','overwrite':True}), ('압축',{'op':'unpack','paths':['a']}),
    ('TV제어',{'target':'a','op':'mute','enabled':True}),
    ('PC제어부품',{'op':'contract','source':'ignored'}),
])
def test_bad_combinations_fail_before_effect(name, args):
    with pytest.raises((ValueError, Fault)):
        checked_values(REG[name]['callable_contract'], args)


def test_image_and_archive_real_values_and_partial_errors(tmp_path):
    from PIL import Image
    path = tmp_path / 'picture.png'
    Image.new('RGB', (64, 32)).save(path)
    info = call('이미지변환', {'op':'info','path':str(path)})
    assert info['items'][0]['width'] == 64
    converted = call('이미지변환', {'paths':[str(path),str(tmp_path/'missing.png')],
                                 'width':32,'out_dir':str(tmp_path/'converted')})
    assert converted['count'] == 1 and len(converted['errors']) == 1
    archive = call('압축', {'op':'pack','paths':[str(path)],'output':str(tmp_path/'files.zip')})
    listing = call('압축', {'op':'list','path':archive['output']})
    assert listing['count'] == 1
    unpacked = call('압축', {'op':'unpack','path':archive['output'],'out_dir':str(tmp_path/'out')})
    assert Path(unpacked['items'][0]['out']).is_file()


def test_compatibility_entry_copied_to_turn(tmp_path):
    import os
    shim = tmp_path / 'pc_control.py'
    shim.write_bytes((ROOT / 'data/instruments/pc_control.py').read_bytes())
    proc = subprocess.run([sys.executable,str(shim)], input='{"op":"contract"}',
                          env={**os.environ,'INDIEBIZ_BASE_PATH':str(ROOT)},capture_output=True,text=True)
    assert json.loads(proc.stdout)['success']


def test_installed_functions_have_single_source_and_compile(monkeypatch, tmp_path):
    from ibl_v2_store import installed_definitions, definitions
    from ibl_v2_learning import check_source
    library = installed_definitions()
    assert set(library) == {
        'PC제어', 'PC제어확인', 'PC제어실행', 'PC조회묶음', 'Android제어', 'Android제어확인',
    }
    for name, source in library.items():
        assert check_source(source, True, library=library) is None
        assert definitions()[name].strip() == source.strip()
    seeds = json.loads((ROOT/'data/idioms/pc_control_seeds.json').read_text())
    assert all('ibl_code' not in row and (ROOT/'data/idioms'/row['source_file']).is_file() for row in seeds)


@pytest.mark.parametrize('bad', [False, True])
def test_registered_pc_uses_real_script_boundary(tmp_path, monkeypatch, bad):
    from test_script_operation_outcomes import load, PKG
    ops = load(PKG / 'script_ops.py')
    monkeypatch.setattr(ops, '_SCRIPT_DIR', ROOT / 'data/scripts')
    monkeypatch.setattr(ops, '_RUN_DIR', tmp_path / 'runs')
    monkeypatch.setattr(ops, '_read_registry', lambda: REG)
    monkeypatch.setattr(ops, '_update_state', lambda *a, **k: None)
    args = {'op':'contract', **({'source':'ignored'} if bad else {})}
    result = ops.op_run({'id':'PC제어부품','args':args,'_ibl_edition':2})
    assert result['success'] is not bad, result
    if not bad:
        assert result['value']['platforms'] == ['darwin','windows']


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
