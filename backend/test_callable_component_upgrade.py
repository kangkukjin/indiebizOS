"""배포 부품은 새 설치·기존 사용자 원장 모두에서 코드와 계약이 함께 도착한다."""
import json
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def sync(resources, userdata, fail=0):
    code = """
import {syncUserData} from './frontend/electron/userdata_sync.js';
const [resourcesPath,userDataPath,fail]=process.argv.slice(1);
try {console.log(JSON.stringify(syncUserData({resourcesPath,userDataPath,log:()=>{},failAfterEntries:Number(fail)})));}
catch(e) {console.error(e.message);process.exit(1);}
"""
    return subprocess.run(['node','--input-type=module','-e',code,str(resources),str(userdata),str(fail)],
                          cwd=ROOT,text=True,capture_output=True,timeout=30)


def put(root, path, content):
    p=root/path
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(content)


@pytest.fixture
def deployment(tmp_path):
    resources, userdata = tmp_path/'resources',tmp_path/'user'
    put(resources,'data/core_manifest.json',json.dumps({'core':{
        'scripts':['pc.py','protected.py'], 'idioms':['installed.json','pc.ibl']}}))
    put(resources,'data/scripts/pc.py','new code')
    put(resources,'data/scripts/protected.py','bundled code')
    put(resources,'data/idioms/installed.json','{"PC":"pc.ibl"}')
    put(resources,'data/idioms/pc.ibl','new definition')
    put(resources,'data/scripts/registry.yaml',yaml.safe_dump({
        'PC':{'file':'pc.py','description':'new','callable_contract':{'version':1},
              'lifecycle':{'source_observation':True}},
        'Protected':{'file':'protected.py','description':'bundle'}}))
    return resources,userdata


def test_existing_registry_and_personal_entries_are_preserved(deployment):
    resources, user = deployment
    personal={'file':'custom.py','description':'personal','origin':'user'}
    put(user,'data/scripts/registry.yaml',yaml.safe_dump({
        'PC':{'file':'pc.py','description':'old','lifecycle':{'kept':True}},
        'Private':personal, 'Protected':{'file':'protected.py','origin':'user','description':'my version'}}))
    put(user,'data/scripts/protected.py','my code')
    put(user,'data/idioms/pc.ibl','old definition')
    put(user,'data/idioms/installed.json','{}')
    result=sync(resources,user)
    assert result.returncode==0,result.stderr
    registry=yaml.safe_load((user/'data/scripts/registry.yaml').read_text())
    assert registry['PC']['callable_contract']=={'version':1}
    assert registry['PC']['lifecycle']=={'kept':True}
    assert registry['Private']==personal
    assert registry['Protected']['origin']=='user'
    assert (user/'data/scripts/protected.py').read_text()=='my code'
    assert (user/'data/idioms/pc.ibl').read_text()=='new definition'
    assert json.loads(sync(resources,user).stdout)['changed']==0


def test_clean_install_and_interrupted_merge_recover(deployment):
    resources,user=deployment
    first=sync(resources,user)
    assert first.returncode==0,first.stderr
    installed=yaml.safe_load((user/'data/scripts/registry.yaml').read_text())['PC']
    assert installed['file']=='pc.py'
    assert 'lifecycle' not in installed
    put(user,'data/scripts/registry.yaml','PC:\n  file: pc.py\n  description: old\n')
    failed=sync(resources,user,1)
    assert failed.returncode!=0
    assert (user/'data/.upgrade_pending').is_file()
    recovered=sync(resources,user)
    assert recovered.returncode==0,recovered.stderr
    assert json.loads(recovered.stdout)['rolledBack']
    assert yaml.safe_load((user/'data/scripts/registry.yaml').read_text())['PC']['description']=='new'


if __name__=='__main__':
    import sys
    raise SystemExit(pytest.main([__file__]+sys.argv[1:]))
