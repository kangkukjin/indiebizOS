"""일반 업무에서 기존 파일 도구→사본→apply→같은 프로세스 새 부품 실행."""
import json
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace as NS

import boot_paths  # noqa: F401
import pytest
import component_runtime as runtime
import execution_turn
from tool_context import ToolContext
from coding_process import available
from test_repair_staging import _load_handler, _make_repo

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not available(), reason='macOS component sandbox')


@pytest.fixture
def setup(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path / 'repo')
    (repo/'frontend').mkdir()
    (repo/'frontend/.keep').write_text('')
    subprocess.run(['git','config','user.name','Test'],cwd=repo,check=True)
    subprocess.run(['git','config','user.email','test@example.test'],cwd=repo,check=True)
    spec = runtime.registry(ROOT)['web.naver_response']
    source = repo / spec['source']; source.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(ROOT / spec['source'],source)
    shutil.copyfile(ROOT / Path(spec['source']).parent / 'runtime_components.json',source.parent / 'runtime_components.json')
    (repo / '.gitignore').write_text('.worktrees/\ndata/system_ai_state/\ndata/restart_control/\ndata/script_runs/\n')
    subprocess.run(['git','add','.'],cwd=repo,check=True)
    subprocess.run(['git','commit','-qm','fixture'],cwd=repo,check=True)
    handler = _load_handler(); handler._REPO_ROOT=repo
    monkeypatch.setattr('runtime_utils.get_code_root',lambda:repo)
    monkeypatch.setattr('runtime_utils.get_source_root',lambda:repo)
    monkeypatch.setattr('runtime_utils.get_base_path',lambda:repo)
    monkeypatch.setattr('thread_context.get_task_origin',lambda:'user')
    monkeypatch.setattr('principal.is_owner',lambda:True)
    turn=execution_turn.Binding(NS(), 'owner','component-test',context={},conversation=None,
                                component_repair_allowed=True)
    token=execution_turn._current.set(turn)
    yield repo,source,handler,turn
    execution_turn._current.reset(token)


def invoke(handler,repo,tool,payload):
    result=handler.execute(payload,ToolContext(tool_name=tool,project_path=str(repo),agent_id='owner'))
    try: return json.loads(result)
    except ValueError: return result


def revised(source):
    return source.replace("data.get('items')", "data.get('items', data.get('results'))").replace(
        "data['items']", "data.get('items', data.get('results'))")


def test_user_task_repairs_transform_without_grant_restart_or_replay(setup):
    repo,source,h,turn=setup
    before=source.read_text();pid=os.getpid()
    value={'response':{'results':[{'title':'Recovered','description':'D','link':'https://example.test'}]},'type':'news'}
    with pytest.raises(ValueError): runtime.call('web.naver_response',value)
    result=invoke(h,repo,'write_file',{'path':str(source),'content':revised(before)})
    assert isinstance(result,dict) and result.get('staged'),result
    assert source.read_text()==before
    applied=invoke(h,repo,'patch_op',{'op':'apply'})
    assert applied['success'] and applied['activated'] and not applied['restart_required'],applied
    assert applied['commit']['success']
    assert os.getpid()==pid
    assert runtime.call('web.naver_response',value)[0]['title']=='Recovered'
    assert subprocess.check_output(['git','show','HEAD:'+str(source.relative_to(repo))],cwd=repo).decode()==revised(before)
    # 다른 요청·새 실행 객체도 같은 영속 판본을 읽는다.
    token=execution_turn._current.set(None)
    try: assert runtime.call('web.naver_response',value)[0]['url']=='https://example.test'
    finally: execution_turn._current.reset(token)


def test_failed_candidate_and_mixed_control_edit_never_apply(setup):
    repo,source,h,turn=setup
    before=source.read_text()
    assert invoke(h,repo,'write_file',{'path':str(source),'content':'def transform(x): return []'})['staged']
    result=invoke(h,repo,'patch_op',{'op':'apply'})
    assert result['success'] is False and source.read_text()==before
    st=h._staging_mod();session=st.read_session(str(repo),turn.component_session)
    (repo/session['worktree']/'backend/cognition/victim.py').write_text('VALUE="unsafe"')
    result=invoke(h,repo,'patch_op',{'op':'apply'})
    assert result['success'] is False and '등록된 부품' in result['error']
    assert source.read_text()==before


def test_no_automatic_authority_for_external_or_unbound_turn(setup,monkeypatch):
    repo,source,h,turn=setup
    turn.component_repair_allowed=False
    scope=h._component_scope()
    assert scope.binding() is None
    turn.component_repair_allowed=True
    monkeypatch.setattr('principal.is_owner',lambda:False)
    assert scope.binding() is None


def test_conflict_and_cancel_preserve_live_source(setup):
    repo,source,h,turn=setup
    old=source.read_text()
    assert invoke(h,repo,'write_file',{'path':str(source),'content':revised(old)})['staged']
    source.write_text(old+'\n# concurrent owner edit\n')
    result=invoke(h,repo,'patch_op',{'op':'apply'})
    assert not result['success'] and ('충돌' in result['error'] or '기준' in result['error'])
    assert source.read_text().endswith('# concurrent owner edit\n')
    turn.cancel_check=lambda:True
    result=invoke(h,repo,'patch_op',{'op':'apply'})
    assert not result['success'] and '취소' in result['error']


def test_interrupted_apply_recovers_same_candidate_and_commits(setup,monkeypatch):
    repo,source,h,turn=setup
    assert invoke(h,repo,'write_file',{'path':str(source),'content':revised(source.read_text())})['staged']
    scope=h._component_scope()
    real_finish=scope.finish
    monkeypatch.setattr(scope,'finish',lambda *a: (_ for _ in ()).throw(RuntimeError('after source write')))
    result=invoke(h,repo,'patch_op',{'op':'apply'})
    assert not result['success']
    monkeypatch.setattr(scope,'finish',real_finish)
    # 외부 제어자가 아닌 같은 apply 영수증이 이미 반영한 바이트를 확인하고 이어간다.
    result=invoke(h,repo,'patch_op',{'op':'apply'})
    assert result['success'] and result['activated']
    assert invoke(h,repo,'read_file',{'path':str(source)})


def test_component_scope_cannot_edit_governing_contract_or_journal(setup):
    repo,source,h,turn=setup
    assert invoke(h,repo,'write_file',{'path':str(source),'content':revised(source.read_text())})['staged']
    for rel in ('data/common_prompts/policy.md','data/restart_control/components/active.json',
                str(source.relative_to(repo).parent/'runtime_components.json')):
        result=invoke(h,repo,'write_file',{'path':str(repo/rel),'content':'changed'})
        assert (isinstance(result,str) and result.startswith('Error:')) or result.get('success') is False,result


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
