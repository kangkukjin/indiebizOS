"""Calendar workers keep their original store through fixture teardown."""
import json
import threading

import calendar_manager


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

