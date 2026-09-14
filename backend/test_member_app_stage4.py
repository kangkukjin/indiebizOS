"""앱 실행 잎 전체의 계약과 질문 뒤 산출물 전달·취소 회귀."""
import boot_paths  # noqa: F401
import json
from types import SimpleNamespace

import pytest
import principal as P
from member_app_actions import compile_apps, resolve


def test_all_nested_actions_options_and_root_actions_have_ids():
    source = [{'id': 'documents', 'inputs': [{'key': 'path'}],
        'action': '[self:list]{path:"$path"}',
        'view': [{'item_click': {'action': '[self:read]{path:"{path}"}'},
                  'button': {'action': '[self:write]{path:"{path}",content:"$text"}'},
                  'select': {'action': '[self:write]{path:"{path}",content:"{sel}"}'}}],
        'modes': [{'id': 'fill', 'inputs': [{'key': 'path'}, {'key': 'field',
            'options_action': '[self:fill]{path:"$path"}'}],
            'action': '[self:fill]{path:"$path",data:{"$field":"$value"}}'}]}]
    wire, registry = compile_apps(source)
    assert len(registry) == 6
    assert '[self:' not in json.dumps(wire)
    assert '[self:' in json.dumps(source)
    hostile = '"} >> [self:config]{} # $field {path}'
    result = resolve(registry, 'documents:fill', {'path': 'imports/a.docx', 'field': 'name', 'value': hostile})
    from ibl_parser import parse
    assert len(parse(result['code'])) == 1
    assert json.loads(result['code'].split('"name":')[1].split('}}')[0]) == hostile
    clicked = resolve(registry, 'documents:view:0:item_click', {'_row': {'path': hostile}})
    assert len(parse(clicked['code'])) == 1
    with pytest.raises(ValueError):
        resolve(registry, 'documents:view:0:item_click', {'_row': {'owner': 'private'}})
    assert resolve(registry, 'documents:fill:inputs:1:options_action', {'path': 'imports/a.docx'})['code'] == '[self:fill]{path:"imports/a.docx"}'


def test_numeric_inputs_cannot_become_code():
    _, registry = compile_apps([{'id': 'test', 'action': '[sense:search]{query:"$query",limit:$limit}'}])
    assert 'limit:3' in resolve(registry, 'test', {'query': 'q', 'limit': 3})['code']
    for raw in ['1} >> [self:config]{}', '{}', '"word"', 'NaN']:
        with pytest.raises(ValueError):
            resolve(registry, 'test', {'query': 'q', 'limit': raw})


def test_reply_preserves_output_and_cannot_resume_foreign_or_other_task():
    import client_agent as ca
    ca.RECORDS.clear()
    calls = []
    def turn(*args, **kwargs):
        calls.append(kwargs)
        return ({'success': True, 'input_required': '어느 기간?', 'response': '어느 기간?'}
                if len(calls) == 1 else {'success': True, 'response': '# 완성 보고서'})
    manager = SimpleNamespace(turn=turn)
    token = P.set_transport(P.OWNER)
    try:
        with P.narrow(P.member('a', 4, 'd')):
            env = {'version': 1, 'request_id': 'first', 'conversation_id': 'task'}
            assert ca.run(env, {'message': 'report', 'workflow': 'research_report', 'output': 'report.md'}, manager=manager)['input_required']
            reply = {**env, 'request_id': 'reply', 'reply_to': 'first'}
            assert not ca.run({**reply, 'conversation_id': 'foreign-task'}, {'message': 'month'}, manager=manager)['success']
        with P.narrow(P.member('b', 4, 'other')):
            assert not ca.run(reply, {'message': 'month'}, manager=manager)['success']
        with P.narrow(P.member('a', 4, 'd')):
            result = ca.run(reply, {'message': 'month'}, manager=manager)
            assert result['delivery'] == 'result_ready' and result['artifacts']
            assert calls[1]['client_context']['workflow'] is None
            assert not ca.run({**reply, 'request_id': 'again'}, {'message': 'month'}, manager=manager)['success']
            assert ca.run(reply, {'message': 'month'}, manager=manager) == result
    finally:
        P.reset_transport(token)
        ca.RECORDS.clear()


def test_cancelled_request_emits_cancelled_without_ready_artifact():
    import client_agent as ca
    ca.RECORDS.clear()
    token = P.set_transport(P.OWNER)
    try:
        events = []
        with P.narrow(P.member('a', 4, 'd')):
            result = ca.run({'version': 1, 'request_id': 'cancel', 'conversation_id': 't'},
                {'message': 'report', 'output': 'report.md'}, on_event=events.append,
                manager=SimpleNamespace(turn=lambda *a, **kw: {'success': False, 'error_type': 'cancelled'}))
        assert result['delivery'] == 'cancelled'
        assert not result.get('artifacts')
        assert events[-1]['type'] == 'cancelled'
    finally:
        P.reset_transport(token)
        ca.RECORDS.clear()


def test_web_renderer_preserves_literal_rows_and_never_posts_raw_code():
    import shutil
    import subprocess
    from pathlib import Path
    if not shutil.which('node'):
        pytest.skip('node required')
    wire, _ = compile_apps([{'id': 'files', 'inputs': [{'key': 'folder', 'default': '.'}],
        'action': '[self:list]{path:"$folder"}',
        'view': [{'button': {'action': '[self:read]{path:"{path}"}'}}]}])
    prelude = "const INSTRUMENTS=" + json.dumps(wire) + ";const CUR={inst:INSTRUMENTS[0]};" + r'''
const assert=require('node:assert/strict'),sent=[],pending=new Map();let seq=0;
function buildAction(t){return t}function rowAction(t){return t}
function ibl(t){return Promise.resolve(t)}function fillOptions(){}function selChanged(){}
function gatherInputs(){return {folder:'.'}}function jget(o,k){return o[k]}
const parent={postMessage:m=>sent.push(m)};
'''
    source = (Path(__file__).parent / 'static/member_app_requests.js').read_text()
    checks = r'''
(async()=>{
 const hostile='a"} >> [self:config]{} $folder {path}';
 const row=rowAction(INSTRUMENTS[0].view[0].button.action,{path:hostile,secret:'ignored'});
 ibl(row);assert.equal(sent[0].action_id,'files:view:0:button');
 assert.deepEqual(sent[0].args,{_row:{path:hostile}});assert.equal(sent[0].code,undefined);
 await assert.rejects(ibl('[self:config]{}'));
 INSTRUMENTS.length=0;assert.equal(await ibl('native compatibility'),'native compatibility');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    subprocess.run(['node'], input=prelude + source + checks, text=True, capture_output=True, check=True)


def test_session_cancel_during_execution_keeps_cancelled_semantics(tmp_path, monkeypatch):
    import member_runtime
    import member_bridge
    from member_session import MemberSession, MemberSessionManager
    class Runner:
        config = {}
        def cognitive_stream(self, *args, **kwargs):
            member_runtime.current()['cancel'].set()
            yield {'type': 'final', 'content': 'interrupted'}
    monkeypatch.setattr(member_bridge, 'connected', lambda _: False)
    monkeypatch.setattr(MemberSession, '_ensure_runner', lambda s: setattr(s, 'runner', Runner()))
    result = MemberSessionManager(tmp_path).turn('a', 'd', 4, 'a', 'request', local_task_id='t')
    assert not result['success']
    assert result['error_type'] == 'cancelled'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
