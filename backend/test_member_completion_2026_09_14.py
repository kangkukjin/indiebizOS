"""회원 인지/실행의 실물 관문. LLM/손발만 대역, 파서·엔진·러너는 실물."""
import boot_paths
import io
import json
import threading
from pathlib import Path
from types import SimpleNamespace
import pytest
import principal as P
import member_runtime as MR

@pytest.fixture(autouse=True)
def context():
    token=P.set_transport(P.OWNER)
    yield
    P.reset_transport(token)


def test_member_output_and_corpus_do_not_persist(tmp_path, monkeypatch):
    from episode_logger import record_ibl_code, record_trajectory_event, _TeeWriter
    import episode_logger as el
    monkeypatch.setattr(el,"_get_db",lambda:pytest.fail("opened owner's episode store"))
    out=io.StringIO()
    with P.narrow(P.member("A",4,"devA")), MR.turn_scope(tmp_path,"devA","task1",threading.Event(),{}):
        _TeeWriter(out).write("PRIVATE-CANARY")
        assert record_ibl_code("[self:write]{content:'PRIVATE-CANARY'}",True) is False
        assert record_trajectory_event("test",{"text":"PRIVATE-CANARY"}) is None
        from common.spill import spill_dir
        assert Path(spill_dir()).is_relative_to(tmp_path)
        from model_result_view import evidence_store
        assert evidence_store().directory.is_relative_to(tmp_path)
    assert not out.getvalue()


def test_member_tool_cannot_use_direct_shell():
    from member_runner import MemberRunner
    runner=MemberRunner.__new__(MemberRunner)
    assert json.loads(runner._member_tool("run_command",{"command":"touch /should-not-exist"}))["error_type"]=="permission"


def test_member_cli_provider_cannot_escape():
    from providers import get_provider
    with P.narrow(P.member("A",4,"devA")):
        with pytest.raises(PermissionError):get_provider("codex",api_key="",model="test",system_prompt="")


def test_actual_ibl_routes_to_member_without_hub_write(tmp_path,monkeypatch):
    import member_profile, member_bridge
    import vocabulary_state as vs
    from member_runner import MemberRunner
    monkeypatch.setattr(member_profile,"_package_open",lambda *a,**kw:True)
    monkeypatch.setattr(member_bridge,"connected",lambda dev:dev=="devA")
    sent=[]
    monkeypatch.setattr(member_bridge,"request",lambda cmd,**kw:sent.append(cmd) or {"success":True,"path":cmd.get("path")})
    runner=MemberRunner.__new__(MemberRunner);runner.project_path=tmp_path
    with P.narrow(P.member("A",4,"devA")), MR.turn_scope(tmp_path,"devA","task-one",threading.Event(),{}):
        import thread_context as tc
        with tc.actor_context(agent_id="member:A",task_id="task-one",origin="member"):
            result=runner._member_tool("execute_ibl",{"code":'[self:write]{path:"/member-only/file.txt",content:"PRIVATE-CANARY"}'})
    assert sent and sent[0]=={"op":"write","path":"/member-only/file.txt","content":"PRIVATE-CANARY"},result
    assert not Path('/member-only/file.txt').exists()
    assert not (tmp_path/'data'/'spill').exists()


def test_model_call_budget_shared_by_workers(tmp_path):
    from providers.base import BaseProvider
    p=SimpleNamespace(model="test",max_role_rounds=99)
    with P.narrow(P.member("A",4,"devA")), MR.turn_scope(tmp_path,"devA","task1",threading.Event(),{"max_model_calls":1}):
        BaseProvider._notify_round(p,1,99)
        with pytest.raises(RuntimeError,match="한도"):BaseProvider._notify_round(p,2,99)


def test_active_close_does_not_remove_working_directory(tmp_path):
    from member_session import MemberSession,load_policy
    s=MemberSession("A","d",4,"A",tmp_path,load_policy(tmp_path));s.dir.mkdir(parents=True)
    s.lock.acquire()
    try:
        s.close()
        assert s.cancel.is_set() and s.dir.exists()
    finally:s.lock.release()
    s.close();assert not s.dir.exists()


def test_actual_cognition_has_no_private_files_outside_turn(tmp_path,monkeypatch):
    import member_session, member_bridge, member_runner, ai_agent, conscious_supervisor
    from member_runner import MemberRunner
    from providers.base import BaseProvider
    monkeypatch.setattr(member_session,"_base",lambda:tmp_path)
    monkeypatch.setattr(member_bridge,"connected",lambda d:False)
    monkeypatch.setattr(MemberRunner,"_sync_execution_gear",lambda s:None)
    monkeypatch.setattr(MemberRunner,"_decide_request_type",lambda *a:("EXECUTE",None))
    monkeypatch.setattr(MemberRunner,"_resolve_execution_config",lambda *a:{"provider":"anthropic","model":"test"})
    class Provider:
        is_ready=True; model="test"; provider_name="test"; max_role_rounds=12
        _last_tool_calls=[];_last_tool_results=[];_last_tool_images=[]
        def __init__(self,ai):self.system_prompt=ai.system_prompt;self.agent_id=ai.agent_id
        def process_message_stream(self,message,history,**kwargs):
            BaseProvider._notify_round(self,1,12)
            print("PRIVATE-FULL-PIPELINE")
            yield {"type":"final","content":"작업 완료 PRIVATE-FULL-PIPELINE"}
    monkeypatch.setattr(ai_agent.AIAgent,"_init_provider",lambda self:setattr(self,"_provider",Provider(self)))
    # supervisor도 실물이며 API 판단이 없는 EXECUTE 차선을 탄다.
    manager=member_session.MemberSessionManager(tmp_path)
    result=manager.turn("A","devA",4,"A","PRIVATE-FULL-PIPELINE")
    assert result["success"],result
    assert "PRIVATE-FULL-PIPELINE" in result["response"]
    assert not list((tmp_path/'data'/'_member_tmp').iterdir())
    for p in (tmp_path/'data').rglob('*'):
        if p.is_file():assert b"PRIVATE-FULL-PIPELINE" not in p.read_bytes(),p


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
