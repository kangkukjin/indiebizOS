"""일반 업무에서 기존 파일 도구→사본→apply→같은 프로세스 새 부품 실행."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
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


def test_lost_binding_recovers_candidate_without_replacing_work(setup):
    repo, source, h, turn = setup
    turn.request = '자료를 조회하고 보고서를 저장해줘'
    staged = invoke(h, repo, 'write_file', {'path': str(source), 'content': revised(source.read_text())})
    replacement = execution_turn.Binding(NS(), turn.agent, turn.task, context={}, conversation=None,
                                        component_repair_allowed=True)
    token = execution_turn._current.set(replacement)
    try:
        status = invoke(h, repo, 'patch_op', {'op': 'status'})
        assert status['key'] == staged['key']
        assert status['parent_request'] == turn.request
        applied = invoke(h, repo, 'patch_op', {'op': 'apply'})
        assert applied['success'] and applied['key'] == staged['key']
    finally:
        execution_turn._current.reset(token)


@pytest.mark.parametrize('whole', [False, True])
def test_registered_component_propose_uses_same_candidate_without_red_grant(setup, whole):
    repo, source, h, turn = setup
    before = source.read_text()
    change = ({'content': revised(before)} if whole else
              {'old_string': before, 'new_string': revised(before)})
    staged = invoke(h, repo, 'patch_op', {'op': 'propose', 'path': str(source),
                                        'reason': '응답 목록 키 변경', **change})
    assert staged['staged'] and staged['key'] == turn.component_session
    assert source.read_text() == before
    assert invoke(h, repo, 'patch_op', {'op': 'apply', 'key': staged['key']})['success']
    assert source.read_text() == revised(before)


def test_explicit_resume_requires_original_conversation_and_agent(setup):
    repo, source, h, turn = setup
    turn.conversation = NS(db_path=str(repo / 'conversation.db'), session_id='original')
    staged = invoke(h, repo, 'write_file', {'path': str(source), 'content': revised(source.read_text())})
    replacement = execution_turn.Binding(NS(), turn.agent, 'next-task', context={},
                                        conversation=NS(db_path=turn.conversation.db_path, session_id='other'),
                                        component_repair_allowed=True)
    token = execution_turn._current.set(replacement)
    try:
        denied = invoke(h, repo, 'patch_op', {'op': 'apply', 'key': staged['key']})
        assert not denied['success'] and '대화' in denied['error']
        replacement.conversation = turn.conversation
        replacement.agent = 'other-agent'
        denied = invoke(h, repo, 'patch_op', {'op': 'apply', 'key': staged['key']})
        assert not denied['success'] and '행위자' in denied['error']
        replacement.agent = turn.agent
        # 같은 대화라도 새 작업이 임의의 수리 사본을 자동 선택하지 않는다.
        assert h._component_scope().restore_session(h._staging_mod(), repo, replacement) is None
        assert invoke(h, repo, 'patch_op', {'op': 'apply', 'key': staged['key']})['success']
    finally:
        execution_turn._current.reset(token)


def test_parent_continuation_attaches_trusted_candidate_key(setup):
    repo, source, h, turn = setup
    turn.conversation = NS(db_path=str(repo / 'conversation.db'), session_id='original')
    staged = invoke(h, repo, 'write_file', {'path': str(source), 'content': revised(source.read_text())})
    resumed = execution_turn.Binding(NS(), turn.agent, 'resumed-task', context={},
                                    conversation=turn.conversation, component_repair_allowed=True,
                                    component_resume_key=staged['key'])
    token = execution_turn._current.set(resumed)
    try:
        applied = invoke(h, repo, 'patch_op', {'op': 'apply'})
        assert applied['success'] and applied['key'] == staged['key']
    finally:
        execution_turn._current.reset(token)


def test_long_task_can_repair_twice_with_distinct_sessions(setup):
    repo, source, h, turn = setup
    turn.task = 'task_sysai_' + 'a' * 40
    first = invoke(h, repo, 'write_file', {'path': str(source), 'content': revised(source.read_text())})
    assert invoke(h, repo, 'patch_op', {'op': 'apply'})['success']
    second = invoke(h, repo, 'write_file', {'path': str(source), 'content': source.read_text() + '\n# second correction\n'})
    assert first['key'] != second['key']
    assert invoke(h, repo, 'patch_op', {'op': 'apply'})['success']


def test_parent_resume_can_start_again_after_discard_receipt(setup):
    repo, source, h, turn = setup
    turn.conversation = NS(db_path=str(repo / 'conversation.db'), session_id='original')
    staged = invoke(h, repo, 'write_file', {'path': str(source), 'content': revised(source.read_text())})
    assert invoke(h, repo, 'patch_op', {'op': 'discard'})['success']
    # discard 영수증 저장 뒤 부모 체크포인트 이전에 죽은 경우.
    resumed = execution_turn.Binding(NS(), turn.agent, 'resumed-after-discard', context={},
                                    conversation=turn.conversation, component_repair_allowed=True,
                                    component_resume_key=staged['key'])
    token = execution_turn._current.set(resumed)
    try:
        retry = invoke(h, repo, 'write_file', {'path': str(source), 'content': revised(source.read_text())})
        assert retry.get('staged') and retry['key'] != staged['key'], retry
        assert not resumed.component_resume_key
    finally:
        execution_turn._current.reset(token)


def test_discarded_attempt_is_not_reused_after_context_loss(setup):
    repo, source, h, turn = setup
    first = invoke(h, repo, 'write_file', {'path': str(source), 'content': revised(source.read_text())})
    assert invoke(h, repo, 'patch_op', {'op': 'discard'})['success']
    replacement = execution_turn.Binding(NS(), turn.agent, turn.task, context={}, conversation=None,
                                        component_repair_allowed=True)
    token = execution_turn._current.set(replacement)
    try:
        denied = invoke(h, repo, 'patch_op', {'op': 'apply', 'key': first['key']})
        assert not denied['success'] and '폐기' in denied['error']
        replacement.component_attempt = 0  # 자동 회수도 폐기된 시도 번호를 넘어야 한다.
        second = invoke(h, repo, 'write_file', {'path': str(source), 'content': revised(source.read_text())})
        assert second['staged'] and first['key'] != second['key']
        assert invoke(h, repo, 'patch_op', {'op': 'apply'})['success']
    finally:
        execution_turn._current.reset(token)


@pytest.mark.system
def test_new_process_recovers_staged_component_and_applied_receipt(setup):
    repo, source, h, turn = setup
    turn.request = '원래 검색 결과를 저장해줘'
    staged = invoke(h, repo, 'write_file', {'path': str(source), 'content': revised(source.read_text())})
    # 불완전한 다른 세션 원장 때문에 회수를 포기하지 않는다.
    folder = repo / 'data/system_ai_state/repair_sessions'
    (folder / 'component-broken.json').write_text('[]')
    program = '''
import json, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import boot_paths, execution_turn, runtime_utils, thread_context
from test_repair_staging import _load_handler
from tool_context import ToolContext
from types import SimpleNamespace as NS
repo = Path(sys.argv[2])
runtime_utils.get_code_root = runtime_utils.get_source_root = runtime_utils.get_base_path = lambda: repo
thread_context.set_task_origin('user')
turn = execution_turn.Binding(NS(), 'owner', 'component-test', context={}, conversation=None,
                              component_repair_allowed=True)
execution_turn._current.set(turn)
handler = _load_handler()
handler._REPO_ROOT = repo
result = json.loads(handler.execute({'op': 'apply'}, ToolContext(
    tool_name='patch_op', project_path=str(repo), agent_id='owner')))
print(json.dumps({'result': result, 'pid': os.getpid()}))
'''
    commits = []
    for _ in range(2):
        child = subprocess.run([sys.executable, '-c', program, str(ROOT / 'backend'), str(repo)],
                               capture_output=True, text=True, timeout=60, check=True)
        row = json.loads(child.stdout.splitlines()[-1])
        result = row['result']
        assert row['pid'] != os.getpid()
        assert result['success'] and result['activated'] and not result['restart_required']
        assert result['key'] == staged['key'] and result['parent_request'] == turn.request
        commits.append(result['commit']['commit'])
    assert commits[0] == commits[1], '복구된 적용 영수증을 다시 커밋하면 안 된다'


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
