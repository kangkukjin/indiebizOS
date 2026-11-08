"""Calendar workers keep their original store through fixture teardown."""
import json
import threading

import calendar_manager


def test_update_returns_detached_saved_snapshot_and_bool_compatibility(tmp_path, monkeypatch):
    monkeypatch.setattr(calendar_manager, 'CALENDAR_CONFIG_PATH', tmp_path / 'calendar.json')
    manager = calendar_manager.CalendarManagerBase(lambda _: None)
    event = manager.add_event('test', event_date='2026-11-09', event_time='10:00')
    receipt = manager.update_event_result(event['id'], time='11:30', action_params={'nested': {'value': 1}})
    assert receipt == json.loads(manager.config_path.read_text())['events'][0]
    assert manager.update_event(event['id'], time='12:00') is True
    manager.config['events'][0]['action_params']['nested']['value'] = 2
    assert receipt['time'] == '11:30' and receipt['action_params']['nested']['value'] == 1
    assert manager.update_event('missing', time='12:00') is False
    assert manager.update_event_result('missing', time='12:00') is None


def test_ibl_event_update_returns_the_saved_event(tmp_path, monkeypatch):
    from system_ai_tools import _execute_manage_events
    monkeypatch.setattr(calendar_manager, 'CALENDAR_CONFIG_PATH', tmp_path / 'calendar.json')
    manager = calendar_manager.CalendarManagerBase(lambda _: None)
    monkeypatch.setattr(calendar_manager, 'get_calendar_manager', lambda: manager)
    event = manager.add_event('test', event_date='2026-11-09', event_time='10:00')
    result = json.loads(_execute_manage_events({'op': 'update', 'event_id': event['id'], 'time': '11:30'}))
    assert result['success'] and result['event'] == json.loads(manager.config_path.read_text())['events'][0]


def test_worker_finishing_after_path_change_keeps_original_store(tmp_path, monkeypatch):
    original = tmp_path / "isolated" / "calendar.json"
    restored = tmp_path / "restored" / "calendar.json"
    original.parent.mkdir()
    restored.parent.mkdir()
    sentinel = b'{"events":[{"id":"user-schedule"}]}'
    restored.write_bytes(sentinel)
    monkeypatch.setattr(calendar_manager, "CALENDAR_CONFIG_PATH", original)
    monkeypatch.setattr(calendar_manager, "DATA_PATH", original.parent)
    manager = calendar_manager.CalendarManagerBase(log_callback=lambda _: None)
    entered, release = threading.Event(), threading.Event()
    manager.config = {"events": [{"id": "worker", "action": "test", "repeat": "daily"}]}

    def action(_):
        entered.set()
        assert release.wait(10)
        return {"success": True}

    manager.actions = {"test": action}
    worker = threading.Thread(target=manager._execute_task, args=(manager.config["events"][0],))
    worker.start()
    try:
        assert entered.wait(10)
        monkeypatch.setattr(calendar_manager, "CALENDAR_CONFIG_PATH", restored)
    finally:
        release.set()
        worker.join(timeout=10)
    assert not worker.is_alive()
    assert restored.read_bytes() == sentinel
    assert not restored.with_suffix(".json.bak").exists()
    assert json.loads(original.read_text()) == manager.config

