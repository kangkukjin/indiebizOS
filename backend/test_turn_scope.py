"""첨부·진행 중인 요청의 후속을 단순 사실 통보와 구분한다."""
import json

import boot_paths  # noqa: F401
import pytest

from cognitive_consciousness import CognitiveConsciousnessMixin
from turn_scope import classification_message
from test_conscious_supervisor import supervisor, manager_tool  # noqa: F401
from test_lifecycle_vocab_2026_10_05 import world, _run  # noqa: F401


def test_classification_context_is_bounded_text_without_attachment_bytes():
    history = [
        {"role": "user", "content": "old unrelated request"},
        {"role": "user", "content": "x" * 3000},
        {"role": "tool", "content": "tool secret"},
        {"role": "assistant", "content": "수치를 알려주시면 기록하겠습니다.",
         "images": [{"base64": "secret"}]},
    ]
    text = classification_message("117 72이고 맥박 73", history, [{"base64": "secret"}])
    value = json.loads(text)
    assert value["current_message"] == "117 72이고 맥박 73"
    assert value["attached_images"] == 1
    assert [x["role"] for x in value["recent_dialogue"]] == ["user", "assistant"]
    assert len(value["recent_dialogue"][0]["content"]) == 1500
    assert "old unrelated" not in text and "secret" not in text


@pytest.mark.parametrize("images, expected", [([], "CONTEXT_UPDATE"), ([{}], "EXECUTE")])
def test_image_cannot_be_locked_by_text_only_context_classification(monkeypatch, images, expected):
    monkeypatch.setattr("model_resolver.consciousness_enabled", lambda: True)
    seen = []
    monkeypatch.setattr("consciousness_agent.oneshot_ai_call",
                        lambda message, **kw: seen.append(message) or "CONTEXT_UPDATE")
    runner = CognitiveConsciousnessMixin()
    runner._log = lambda *a: None
    history = [{"role": "assistant", "content": "수치를 알려주시면 기록하겠습니다."}]
    assert runner._decide_request_type("오늘 측정 결과야", 0, "", history, images) == (expected, None)
    assert len(seen) == 1
    assert json.loads(seen[0])["recent_dialogue"] == history


def test_plain_notification_keeps_original_classifier_input():
    assert classification_message("숙소 예약되었다.") == "숙소 예약되었다."


@pytest.mark.parametrize('mode', ['research', 'library'])
def test_notification_perspective_roundtrip_and_real_boundaries(world, supervisor, mode):
    from project_manager import ProjectManager
    from research_store import ResearchStore
    from research_context import scope
    project = ProjectManager().create_project('관점 회귀', project_kind='research')
    store = ResearchStore(project['path'])
    tid = store.create_thread('돌봄')['id']
    other = store.create_thread('다른 대화')['id']
    run, _ = store.begin_run(tid, '걸을 수 있지만 병환과 외로움이 문제다', 'first')
    uid = store.messages(tid)['items'][0]['id']
    revision = store.thread(tid)['revision']
    notes = f'# 사용자의 관점\n걸을 수 있으나 병환과 외로움이 문제다. [발언:{uid}]'
    inputs = dict(project=store.uid, thread=tid, revision=revision, notes=notes)
    code = ('#!ibl edition=2\n$operation = "thread_update"\n'
            'return [self:project]{op:$operation,project_ref:$project,thread_ref:$thread,'
            'expected_revision:$revision,notes:$notes}')
    supervisor.request_intent = 'context_update'
    supervisor.configure(None)

    def execute(source=code, values=None):
        params = inputs if values is None else values
        return supervisor.run_tool('execute_ibl', {'code': source, 'edition': 2, 'inputs': params},
                                   lambda: _run(source, project['path'], params))

    with scope(dict(project_uid=store.uid, thread_id=tid, run_id=run, mode=mode)):
        saved = execute()
        assert saved.get('success') is not False, saved
        assert store.thread(tid)['notes'] == notes
        assert store.thread(tid)['revision'] > revision
        stale = execute(values={**inputs, 'notes': notes + '\n덮어쓰기'})
        assert stale.get('success') is False, stale
        assert store.thread(tid)['notes'] == notes
        foreign = execute(values={**inputs, 'thread': other, 'revision': store.thread(other)['revision']})
        assert foreign.get('success') is False, foreign
        assert not store.thread(other)['notes']
        assert supervisor.failures == 2  # 실제 거절은 공통 실패 관측에 도달한다.
        if mode == 'library':
            outside = execute('return [sense:search]{query:"새 조사"}', {})
            assert outside.get('success') is False, outside
    assert sum(r["kind"] == "tool.finished" for r in supervisor.recent) >= 3


def test_notification_health_save_reaches_real_storage(world, supervisor, monkeypatch):
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] /
                                   'data/packages/installed/tools/health-record'))
    import health_storage
    root = world.tmp / 'health'
    monkeypatch.setattr(health_storage, 'DATA_DIR', str(root))
    monkeypatch.setattr(health_storage, 'DB_PATH', str(root / 'records.db'))
    monkeypatch.setattr(health_storage, 'IMAGES_DIR', str(root / 'images'))
    monkeypatch.setattr(health_storage, 'DEFAULT_PERSON', '회귀 인물')
    monkeypatch.setattr(health_storage, '_sync_migrated', False)
    supervisor.request_intent = 'context_update'
    supervisor.configure(None)
    code = ('#!ibl edition=2\nreturn [self:health]{op:"save",category:"혈압",'
            'systolic:117,diastolic:72,note:"맥박 73",person:"회귀 인물"}')
    result = supervisor.run_tool('execute_ibl', {'code': code}, lambda: _run(code, str(world.tmp)))
    assert result.get('success') is not False, result
    with health_storage.get_db_connection() as db:
        rows = db.execute('SELECT category,value_json,note FROM measurements').fetchall()
    assert len(rows) == 1 and rows[0]['category'] == 'blood_pressure'
    assert json.loads(rows[0]['value_json']) == {'systolic': 117, 'diastolic': 72}
    assert rows[0]['note'] == '맥박 73'


def test_notification_manager_execution_uses_same_resource_authority(supervisor):
    supervisor.request_intent = 'context_update'
    supervisor.executor_paused = True
    result = manager_tool(supervisor, {'op': 'execute', 'name': 'inspect', 'input': {'record': '정정'}})
    assert result['success'] and supervisor.calls[-1][1] == {'record': '정정'}
    denied = manager_tool(supervisor, {'op': 'execute', 'name': 'not_in_catalog', 'input': {}})
    assert denied['success'] is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
