"""IBL 진행 신고 → 채팅 표면 (2026-10-26).

무엇을 고치려고 생겼나: execute_ibl 한 호출이 몇 분을 돌아도 채팅에는 "🔧 execute_ibl 실행 중..." 카드
하나만 떴다. 액션 단위 진행(ibl_progress report_step/beat)은 표면 티켓(/ibl/recover 당김)으로만 갔고
채팅 WS 에는 'progress' 이벤트가 없었다. 수리:
  · supervision_bus 에 task_id 별 진행 수신자(sink) — 감독 컨트롤러와 별개의 사람 화면용 통로
  · ibl_v2_runtime 이 액션 호출 경계마다 report_step, [table:each] 행마다 beat
  · chat_streams 가 수신자를 런의 큐에 걸고 WS 'progress' 로 전달
  · conversation_sessions 는 progress 를 턴 현재값으로, 도구 호출 앞 중간 서술을 interim_text 사건으로 보존

실행: .venv/bin/python -m pytest backend/test_progress_to_chat.py
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401

import thread_context as tc  # noqa: E402
import supervision_bus  # noqa: E402


@pytest.fixture
def task():
    prev = tc.get_current_task_id()
    tc.set_current_task_id("task_progress_test")
    try:
        yield "task_progress_test"
    finally:
        supervision_bus.unregister_progress_sink("task_progress_test")
        tc.set_current_task_id(prev or "")


def test_진행_수신자는_task_id로_찾고_해제되면_조용하다(task):
    seen = []
    supervision_bus.register_progress_sink(task, seen.append)
    supervision_bus.progress({"step": 1, "of": 0, "action": "self:read"})
    supervision_bus.progress({"row": 1, "rows": 3})
    assert seen == [{"step": 1, "of": 0, "action": "self:read"}, {"row": 1, "rows": 3}]
    supervision_bus.unregister_progress_sink(task, seen.append)
    supervision_bus.progress({"row": 2, "rows": 3})
    assert len(seen) == 2, "해제 뒤에도 신고가 닿았다"


def test_다른_task의_신고는_내_수신자에_안_온다(task):
    seen = []
    supervision_bus.register_progress_sink(task, seen.append)
    tc.set_current_task_id("task_someone_else")
    try:
        supervision_bus.progress({"action": "x"})
    finally:
        tc.set_current_task_id(task)
    assert seen == []


def test_수신자_예외는_실행을_깨지_않는다(task):
    def boom(_):
        raise RuntimeError("표면이 죽었다")
    supervision_bus.register_progress_sink(task, boom)
    supervision_bus.progress({"action": "x"})   # 예외 없이 통과


def test_런타임이_액션_경계와_each_행을_신고한다(task, monkeypatch, tmp_path):
    """표면 티켓이 없어도(채팅 런) 버스로는 간다 — claim 이 None 이어도 report_step/beat 은 신고한다."""
    import ibl_v2_runtime
    from ibl_v2_adapters import Adapter
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    monkeypatch.setattr(ibl_v2_runtime, "_PROGRESS_MIN_INTERVAL_S", 0.0)   # 접기 끔 — 전 신고를 본다
    tc.set_surface_ticket(None)
    tc.set_progress_ticket(None)
    seen = []
    supervision_bus.register_progress_sink(task, seen.append)
    adapter = Adapter({'version': 1, 'params': {'n': 'Number'}, 'result': 'Number', 'effects': ['read_external']},
                      lambda rt, args: args['n'])
    plan = compile_program('[table:each]{items:[7,8]}{[test:observe]{n:$it}}', {'test:observe': adapter})
    assert not plan.issues, plan.report()
    out = Runtime(plan).run()
    assert out['success'], out
    actions = [e for e in seen if "action" in e]
    rows = [e for e in seen if "row" in e]
    assert [e["action"] for e in actions] == ["test:observe", "test:observe"], seen
    assert [e["step"] for e in actions] == [1, 2], "호출 번호는 1부터 하나씩"
    assert all(e["of"] == 0 for e in actions), "분모는 미지(0) — 거짓 분모를 만들지 않는다"
    assert [e["detail"] for e in actions] == rows, "행 안의 액션 좌표는 자기 회차를 동봉한다"
    assert rows == [{"row": 1, "rows": 2, "row_label": "7"}, {"row": 2, "rows": 2, "row_label": "8"}], seen


def test_each_밖의_액션_좌표에는_회차가_없다(task, monkeypatch):
    import ibl_v2_runtime
    from ibl_v2_adapters import Adapter
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    monkeypatch.setattr(ibl_v2_runtime, "_PROGRESS_MIN_INTERVAL_S", 0.0)
    tc.set_surface_ticket(None)
    seen = []
    supervision_bus.register_progress_sink(task, seen.append)
    adapter = Adapter({'version': 1, 'params': {'n': 'Number'}, 'result': 'Number', 'effects': ['read_external']},
                      lambda rt, args: args['n'])
    plan = compile_program('$a = [table:each]{items:[1]}{[test:observe]{n:$it}}\nreturn [test:observe]{n:9}', {'test:observe': adapter})
    assert not plan.issues, plan.report()
    assert Runtime(plan).run()['success']
    actions = [e for e in seen if "action" in e]
    assert "detail" in actions[0] and "detail" not in actions[-1], "each 가 끝나면 회차가 따라오지 않는다"


def test_같은_액션의_연속_신고는_간격_안에서_접힌다(task, monkeypatch):
    import ibl_v2_runtime
    from ibl_v2_adapters import Adapter
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    monkeypatch.setattr(ibl_v2_runtime, "_PROGRESS_MIN_INTERVAL_S", 60.0)
    tc.set_surface_ticket(None)
    seen = []
    supervision_bus.register_progress_sink(task, seen.append)
    adapter = Adapter({'version': 1, 'params': {'n': 'Number'}, 'result': 'Number', 'effects': ['read_external']},
                      lambda rt, args: args['n'])
    # 행마다 같은 액션 두 번 — 행 안에서는 접히고, 행이 바뀌면(회차가 다른 좌표) 다시 신고한다(2026-10-27 개정:
    # 접기 키=(액션, 회차). 액션 이름만으로 접으면 each 밖 첫 좌표가 삼켜져 티켓에 옛 행이 남았다).
    plan = compile_program('[table:each]{items:[1,2,3]}{[test:observe]{n:$it}; [test:observe]{n:$it}}', {'test:observe': adapter})
    assert not plan.issues, plan.report()
    out = Runtime(plan).run()
    assert out['success'], out
    actions = [e for e in seen if "action" in e]
    assert len(actions) == 3, ("같은 액션은 같은 행 안에서만 접힌다", seen)
    assert [e["detail"]["row"] for e in actions] == [1, 2, 3], actions
    assert len([e for e in seen if "row" in e]) == 3, "행은 키(번호)가 바뀌므로 매번"


def test_표면_수신자는_좌표를_기억하고_움직임에_덧붙인다(monkeypatch):
    import chat_streams
    monkeypatch.setattr(chat_streams, "_PROGRESS_BEAT_MIN_INTERVAL_S", 0.0)
    got = []
    sink = chat_streams.make_progress_sink(got.append)
    sink({"step": 3, "of": 0, "action": "limbs:youtube"})
    sink({"row": 2, "rows": 4, "row_label": "abc"})
    sink("not a dict")
    sink({})
    sink({"step": 4, "of": 0, "action": "self:struct", "detail": {"row": 2, "rows": 4}})
    assert [e["type"] for e in got] == ["progress", "progress", "progress"]
    assert got[0]["action"] == "limbs:youtube" and "detail" not in got[0] and got[0]["at"] > 0
    assert got[1]["action"] == "limbs:youtube" and got[1]["step"] == 3, "움직임에 마지막 좌표가 실린다"
    assert got[1]["detail"] == {"row": 2, "rows": 4, "row_label": "abc"}
    assert got[2]["action"] == "self:struct" and got[2]["detail"] == {"row": 2, "rows": 4}, "좌표가 품은 회차는 그대로"


def test_표면_수신자는_연속_beat_을_접지만_좌표는_바로_싣는다(monkeypatch):
    import chat_streams
    monkeypatch.setattr(chat_streams, "_PROGRESS_BEAT_MIN_INTERVAL_S", 60.0)
    got = []
    sink = chat_streams.make_progress_sink(got.append)
    sink({"row": 1, "rows": 9})
    sink({"row": 2, "rows": 9})
    sink({"step": 1, "of": 0, "action": "self:read"})
    sink({"step": 2, "of": 0, "action": "self:write"})
    assert [e.get("detail", {}).get("row", e.get("action")) for e in got] == [1, "self:read", "self:write"]


def test_progress_표면_계약():
    import chat_streams
    payload = chat_streams.progress_event_payload(
        {"type": "progress", "step": 2, "of": 0, "action": "self:struct", "detail": {"row": 1, "rows": 4}, "at": 1.5},
        "홈페이지")
    assert payload == {"type": "progress", "agent": "홈페이지", "at": 1.5, "step": 2, "of": 0,
                       "action": "self:struct", "detail": {"row": 1, "rows": 4}}


def _session_db(tmp_path):
    import conversation_sessions as sessions
    path = tmp_path / "conversations.db"
    with sessions.connection(path) as conn:
        conn.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, content TEXT)")
        sessions.ensure_schema(conn, "messages")
        conn.execute("INSERT INTO conversation_sessions(id,owner,title,created_at,updated_at) VALUES (?,?,?,?,?)",
                     ("s1", "owner", "t", "start", "start"))
        conn.execute("INSERT INTO conversation_turns(id,session_id,state,process,started_at) VALUES (?,?,?,?,?)",
                     ("turn1", "s1", "running", "p", "start"))
    return sessions, path


def test_세션_기록은_progress_를_턴_현재값으로_두고_끝나면_비운다(tmp_path):
    sessions, path = _session_db(tmp_path)
    with sessions.scope(sessions.Binding(str(path), "s1", "owner", "turn1")):
        sessions.record_event({"type": "progress", "step": 1, "of": 0, "action": "self:read", "at": 10.0})
        sessions.record_event({"type": "progress", "step": 2, "of": 0, "action": "self:write", "at": 11.0})
        with sessions.connection(path) as conn:
            prog = json.loads(conn.execute("SELECT progress FROM conversation_turns").fetchone()[0])
            assert prog["action"] == "self:write" and prog["step"] == 2
            assert conn.execute("SELECT count(*) FROM conversation_events").fetchone()[0] == 0, "진행은 사건으로 쌓지 않는다"
        sessions.record_event({"type": "tool_result", "name": "execute_ibl", "result": "ok", "is_error": False})
        with sessions.connection(path) as conn:
            assert conn.execute("SELECT progress FROM conversation_turns").fetchone()[0] == ""


def test_세션_기록은_도구_호출_앞의_중간_서술을_사건으로_남긴다(tmp_path):
    sessions, path = _session_db(tmp_path)
    with sessions.scope(sessions.Binding(str(path), "s1", "owner", "turn1")):
        sessions.record_event({"type": "stream_chunk", "content": "먼저 파일을 "})
        sessions.record_event({"type": "stream_chunk", "content": "읽겠습니다."})
        sessions.record_event({"type": "tool_start", "id": "t1", "name": "execute_ibl", "input": {}})
        sessions.record_event({"type": "tool_start", "id": "t2", "name": "execute_ibl", "input": {}})   # 초안 없음 → 사건 없음
        sessions.record_event({"type": "response", "content": "끝"})
    with sessions.connection(path) as conn:
        events = [json.loads(r[0]) for r in conn.execute("SELECT payload FROM conversation_events ORDER BY id")]
        assert conn.execute("SELECT stream_content FROM conversation_turns").fetchone()[0] == ""
    kinds = [e["type"] for e in events]
    assert kinds == ["interim_text", "tool_start", "tool_start", "response"], kinds
    assert events[0]["content"] == "먼저 파일을 읽겠습니다."


def test_스냅샷의_progress_는_dict_와_경과초(tmp_path):
    import chat_session_service as service
    assert service._progress_view("") is None
    assert service._progress_view("not json") is None
    assert service._progress_view('"str"') is None
    import time
    view = service._progress_view(json.dumps({"type": "progress", "action": "self:read", "at": time.time() - 5}))
    assert view["action"] == "self:read" and 4.5 <= view["age_s"] <= 8


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))


# ── 2026-10-28 긴문장 100회차 L100-5 — HTTP 턴(/system-ai/chat)의 진행 수신자 ─────────────────────────────────
def test_HTTP_턴_수신자는_진행을_턴_현재값으로_쓰고_끝나면_비운다(tmp_path, monkeypatch):
    sessions, path = _session_db(tmp_path)
    binding = sessions.Binding(str(path), "s1", "owner", "turn1")
    clock = {"t": 100.0}
    monkeypatch.setattr(sessions.time, "time", lambda: clock["t"])
    sink = sessions.progress_sink(binding)
    sink({"step": 1, "of": 0, "action": "self:read", "reused": False})
    sink({"row": 1, "rows": 3})                     # 첫 beat — 좌표를 덧붙여 쓴다
    sink({"row": 2, "rows": 3})                     # 0.2초 안 연속 beat 은 접는다
    with sessions.connection(path) as conn:
        prog = json.loads(conn.execute("SELECT progress FROM conversation_turns").fetchone()[0])
    assert prog["type"] == "progress" and prog["action"] == "self:read" and prog["step"] == 1, prog
    assert prog["detail"] == {"row": 1, "rows": 3}, ("beat 접기", prog)
    clock["t"] += 1
    sink({"row": 3, "rows": 3, "phase": "compute"})
    sink({"step": 2, "of": 0, "action": "self:write", "reused": True, "detail": {"row": 3, "rows": 3}})
    with sessions.connection(path) as conn:
        prog = json.loads(conn.execute("SELECT progress FROM conversation_turns").fetchone()[0])
        assert prog["action"] == "self:write" and prog["reused"] is True and prog["detail"]["row"] == 3, prog
        assert conn.execute("SELECT count(*) FROM conversation_events").fetchone()[0] == 0, "진행은 사건으로 쌓지 않는다"
    sessions.clear_progress(binding)
    with sessions.connection(path) as conn:
        assert conn.execute("SELECT progress FROM conversation_turns").fetchone()[0] == ""


def test_HTTP_턴_수신자는_버스에_등록되면_신고를_받는다(task, tmp_path):
    sessions, path = _session_db(tmp_path)
    binding = sessions.Binding(str(path), "s1", "owner", "turn1")
    sink = sessions.progress_sink(binding)
    supervision_bus.register_progress_sink(task, sink)
    from ibl_progress import report_step
    report_step(None, 4, 0, "self:script", detail={"row": 2, "rows": 5})
    with sessions.connection(path) as conn:
        prog = json.loads(conn.execute("SELECT progress FROM conversation_turns").fetchone()[0])
    assert prog["step"] == 4 and prog["action"] == "self:script" and prog["detail"]["rows"] == 5 and prog["reused"] is False, prog


def test_progress_publication_is_serial_and_unregister_closes_late_calls(task):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    entered, release, second_entered = threading.Event(), threading.Event(), threading.Event()
    seen = []

    def put(event):
        if event['step'] == 1:
            entered.set()
            assert release.wait(3)
        seen.append(event['step'])

    sink = supervision_bus.ProgressSink(put)
    supervision_bus.register_progress_sink(task, sink)

    def second():
        second_entered.set()
        sink({'step': 2, 'action': 'read'})

    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(sink, {'step': 1, 'action': 'read'})
        assert entered.wait(3)
        later = pool.submit(second)
        assert second_entered.wait(3)
        release.set()
        first.result(timeout=3)
        later.result(timeout=3)
    assert seen == [1, 2]
    supervision_bus.unregister_progress_sink(task, sink)
    sink({'step': 3, 'action': 'read'})  # 해제 전에 다른 스레드가 집어 둔 수신자
    assert seen == [1, 2]


def test_finished_turn_clears_progress_and_rejects_late_updates(tmp_path):
    sessions, path = _session_db(tmp_path)
    binding = sessions.Binding(str(path), 's1', 'owner', 'turn1')
    sink = sessions.progress_sink(binding)
    sink({'step': 1, 'action': 'self:read'})
    store = sessions.SessionStore(path, 'messages', 'owner', create_legacy=False)
    store.finish(binding)
    sink({'step': 2, 'action': 'self:read'})
    with sessions.connection(path) as conn:
        state, progress = conn.execute('SELECT state,progress FROM conversation_turns').fetchone()
    assert state == 'completed' and progress == ''


def test_chat_card_renders_reuse_and_compute_without_protocol_labels():
    """Render the real React tool card with a backend progress payload."""
    import subprocess
    from pathlib import Path
    js = r'''
const esbuild=require('./frontend/node_modules/esbuild');
const result=esbuild.buildSync({stdin:{contents:`
  import React from 'react';
  import {renderToStaticMarkup} from 'react-dom/server';
  import {ToolHistoryPanel} from './src/components/chat/ToolHistoryPanel';
  const cases=[
    {action:'self:read',step:3,of:0,reused:true,detail:{row:2,rows:5,phase:'compute'},at:Date.now()},
    {action:'self:write',step:4,of:0,reused:false,detail:{row:3,rows:5},at:Date.now()}
  ];
  process.stdout.write(JSON.stringify(cases.map(progress => renderToStaticMarkup(
    React.createElement(ToolHistoryPanel,{toolHistory:[{name:'execute_ibl',status:'running',progress}]})))));
`,resolveDir:process.cwd()+'/frontend',loader:'tsx'},bundle:true,write:false,platform:'node',
  format:'cjs',jsx:'automatic',define:{'import.meta.env':'{}'},logLevel:'silent'});
new Function('require',result.outputFiles[0].text)(require);
'''
    result = subprocess.run(['node', '-e', js], capture_output=True, text=True,
                            cwd=Path(__file__).resolve().parents[1], timeout=30, check=True)
    reused, normal = json.loads(result.stdout)
    assert 'self:read(재사용)' in reused and '2/5행 계산 중' in reused
    assert 'phase=' not in reused and 'compute' not in reused
    assert 'self:write' in normal and '재사용' not in normal and '계산 중' not in normal
