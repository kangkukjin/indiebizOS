"""4064: 읽기 실패의 원인 보존과 계약 조회를 곁들인 실행의 공통 경계."""
import asyncio
import errno
import importlib.util
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest

from ibl_v2_entry import handle_request
from ibl_v2_adapters import decode_envelope
from ibl_v2_ir import Fault
from result_read_contract import is_observation_request
from system_tools_ibl import _execute_ibl_unified_impl

ROOT = Path(__file__).resolve().parents[1]


def request(tmp_path, **payload):
    return json.loads(_execute_ibl_unified_impl({"edition": 2, **payload}, str(tmp_path)))


def test_missing_file_is_tool_failure_with_original_cause(tmp_path):
    result = handle_request({"edition": 2, "code": '[self:read]{path:"missing.txt"}'}, str(tmp_path))
    assert not result["success"]
    fault = result["diagnostic"]
    assert (fault["code"], fault["kind"]) == ("TOOL", "runtime")
    assert fault["details"] == {"error_type": "not_found", "errno": errno.ENOENT}


def test_parallel_missing_read_preserves_other_branch(tmp_path):
    (tmp_path / "present.txt").write_text("실제 자료")
    result = handle_request({"edition": 2, "code":
        '[self:read]{path:"present.txt"} & [self:read]{path:"missing.txt"}'}, str(tmp_path))
    assert not result["success"] and not result["source_complete"]
    assert result["diagnostic"]["partial"][0]["text"] == "실제 자료"
    assert result["diagnostic"]["code"] == "TOOL"


def test_permission_read_cannot_be_swallowed_as_empty(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("ep4064_handler",
        ROOT / "data/packages/installed/tools/system_essentials/handler.py")
    handler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(handler)
    (tmp_path / "locked.txt").write_text("private")

    def denied(*args, **kwargs):
        raise PermissionError(errno.EACCES, "denied")

    monkeypatch.setattr(handler._file_io, "read_text_window", denied)
    raw = handler.execute({"path": "locked.txt", "blocks": True},
                          SimpleNamespace(tool_name="read_op", project_path=str(tmp_path), agent_id=None))
    assert json.loads(raw)["error_type"] == "permission"
    with pytest.raises(Fault) as caught:
        decode_envelope(raw, {"protocol": "document-value/1", "value_path": "/value"})
    assert caught.value.kind == "permission" and not caught.value.catchable


def test_document_text_error_prefix_is_content_not_failure(tmp_path):
    (tmp_path / "errors.txt").write_text("Error: 예제로 쓴 본문")
    result = handle_request({"edition": 2, "code": '[self:read]{path:"errors.txt"}'}, str(tmp_path))
    assert result["success"] and result["value"]["text"] == "Error: 예제로 쓴 본문"
    with pytest.raises(Fault) as caught:
        decode_envelope("broken envelope", {"protocol": "document-value/1"})
    assert caught.value.code == "ADAPTER_SHAPE"


@pytest.mark.parametrize("state", ["absent", "empty", "present"])
def test_optional_file_guide_distinguishes_absent_from_empty(tmp_path, state):
    folder = tmp_path / "outputs"
    folder.mkdir()
    if state != "absent":
        (folder / "optional.json").write_text("" if state == "empty" else "[]")
    guide = (ROOT / "data/guides/ibl_composition.md").read_text()
    code = guide.split("<!-- example:optional_file -->", 1)[1].split("```ibl\n", 1)[1].split("```", 1)[0]
    result = handle_request({"edition": 2, "code": code}, str(tmp_path))
    assert result["success"] and result["source_complete"], result
    assert result["value"] == {"found": state != "absent", "text": "[]" if state == "present" else ""}
    assert (folder / "optional.json").exists() == (state != "absent")


def test_describe_and_write_execute_once_and_keep_result(tmp_path, monkeypatch):
    import ibl_v2_entry
    original, seen = ibl_v2_entry.handle_request, []

    def counted(*args, **kwargs):
        seen.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(ibl_v2_entry, "handle_request", counted)
    result = request(tmp_path, code='[self:write]{path:"outputs/a.txt",content:"saved"}',
                     describe=["self:write"])
    assert result["success"] and result["executed"]
    assert (tmp_path / "outputs/a.txt").read_text() == "saved"
    assert len(seen) == 1 and "describe" not in seen[0]
    assert result["value"]["success"]
    assert result["descriptions"][0]["action"] == "self:write"
    assert result["resume"]["run_id"]


@pytest.mark.parametrize("extra", [
    {"describe": ["self:missing_action"]}, {"describe": []},
    {"read_result": {"id": "unused"}},
    {"describe": ["self:write"], "read_result": {"id": "unused"}},
])
def test_invalid_lookup_never_executes_write(tmp_path, extra):
    result = request(tmp_path, code='[self:write]{path:"outputs/no.txt",content:"bad"}', **extra)
    assert result["success"] is False and result["executed"] is False
    assert not (tmp_path / "outputs/no.txt").exists()


def test_check_with_describe_never_executes_and_failure_is_preserved(tmp_path):
    result = request(tmp_path, code='[self:write]{path:"outputs/no.txt",content:"bad"}',
                     describe=["self:write"], check=True)
    assert result["ok"] and result["executed"] is False
    assert not (tmp_path / "outputs/no.txt").exists()
    failed = request(tmp_path, code='[self:read]{path:"missing.txt"}', describe=["self:read"])
    assert failed["success"] is False and failed["diagnostic"]["code"] == "TOOL"
    assert failed["descriptions"][0]["action"] == "self:read"
    assert request(tmp_path, code="", describe=["self:read"])["executed"] is False


def test_combined_execution_cannot_bypass_context_or_runtime_gates(tmp_path, monkeypatch):
    import runtime_work
    from system_tools_ibl import _execute_ibl_unified
    from turn_scope import allows_context_tool
    payload = {"edition": 2, "code": "return 1", "describe": ["self:read"]}
    assert not is_observation_request(payload)
    assert not allows_context_tool("execute_ibl", payload)
    work = runtime_work.WorkRegistry("ep4064")  # 접수 닫힘
    monkeypatch.setattr(runtime_work, "_registry", work)
    with pytest.raises(runtime_work.AdmissionClosed):
        _execute_ibl_unified(payload, str(tmp_path))
    assert request(tmp_path, code="", describe=["self:read"])["executed"] is False


def test_combined_http_execution_is_blocked_during_drain(monkeypatch):
    import runtime_work
    from api_runtime import RuntimeAdmission
    monkeypatch.setattr(runtime_work, "_registry", runtime_work.WorkRegistry("ep4064"))
    sent = []

    async def app(*args):
        pytest.fail("mixed execution bypassed admission")

    async def receive():
        return {"type": "http.request", "body": json.dumps({
            "code": "return 1", "describe": ["self:read"]}).encode(), "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(RuntimeAdmission(app)({"type": "http", "method": "POST", "path": "/ibl/execute",
                                       "headers": []}, receive, send))
    assert sent[0]["status"] == 503


def test_member_rejects_unpublished_description_before_execution(tmp_path, monkeypatch):
    from member_runner import MemberRunner
    monkeypatch.setattr("member_profile.visible", lambda *args: False)
    runner = SimpleNamespace(config={"allowed_nodes": None}, project_path=tmp_path)
    result = json.loads(MemberRunner._member_tool(runner, "execute_ibl", {
        "code": '[self:write]{path:"no.txt",content:"bad"}', "describe": ["self:write"]}))
    assert result["success"] is False and not (tmp_path / "no.txt").exists()


def test_describe_preserves_legacy_plain_text(tmp_path):
    (tmp_path / "plain.txt").write_text("007")
    result = request(tmp_path, edition=1, code='[self:read]{path:"plain.txt"}', describe=["self:read"])
    assert result["result"] == "007"
    assert result["descriptions"][0]["action"] == "self:read"


def test_member_combined_call_keeps_member_execution_context(tmp_path):
    import principal
    import member_runtime
    from member_runner import MemberRunner
    from thread_context import actor_context
    runner = MemberRunner.__new__(MemberRunner)
    runner.config = {"allowed_nodes": ["self", "table"]}
    runner.project_path = tmp_path
    with principal.narrow(principal.member("ep4064", 4, "device")), member_runtime.turn_scope(
            tmp_path / "member", "device", "ep4064", threading.Event(), {}), actor_context(
            agent_id="member:ep4064", task_id="ep4064"):
        result = json.loads(runner._member_tool("execute_ibl", {
            "edition": 2, "code": "return 4064", "describe": ["self:read"]}))
    assert result["success"] and result["value"] == 4064
    assert result["descriptions"][0]["action"] == "self:read"


def test_mcp_combined_call_keeps_repeat_guard(monkeypatch):
    import mcp_server
    seen = []
    monkeypatch.setattr(mcp_server, "_post_backend", lambda *args: '{"success":true,"value":1}')
    monkeypatch.setattr(mcp_server, "_repeat_advisory", lambda *args: seen.append(args) or "")
    async def run():
        await mcp_server.execute_ibl("return 1", describe=["self:read"])
        await mcp_server.execute_ibl("", describe=["self:read"])
    asyncio.run(run())
    assert len(seen) == 1 and "return 1" in seen[0][1]


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
