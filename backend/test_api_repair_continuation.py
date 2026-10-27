"""실제 kick 진입점에서 종결 작업의 통지만 재전달한다."""
from types import SimpleNamespace

import pytest
import boot_paths  # noqa: F401
import api_repair_continuation as consumer
import repair_continuation as journal
import repair_root
import runtime_work


def test_kick_retries_terminal_delivery_without_reexecuting_repair(tmp_path, monkeypatch):
    monkeypatch.setenv('INDIEBIZ_BASE_PATH', str(tmp_path))
    work = SimpleNamespace(phase='ACTIVE', generation='g2', snapshot=lambda: {'active_roots': 0, 'active_children': 0})
    monkeypatch.setattr(runtime_work, 'registry', lambda: work)
    monkeypatch.setattr(runtime_work, 'bind_lease', lambda fn, label: fn)
    monkeypatch.setattr(consumer.threading, 'Thread', lambda target, **k: SimpleNamespace(start=target))
    monkeypatch.setattr(consumer, '_last_scan', 0)
    row = {'task_id': 'done', 'root_task_id': 'done', 'status': 'completed', 'authorized_origin': 'user'}
    journal.save(row, tmp_path)
    repair_root.close(tmp_path, 'done', complete=True, reason='verified')
    def failed(row):
        raise OSError('offline')
    monkeypatch.setattr(consumer, '_deliver_blocked', failed)
    assert not consumer._deliver(row, '완료', tmp_path, completion=True)
    calls = []
    monkeypatch.setattr(consumer, '_deliver_blocked', lambda row: calls.append(row['reason']))
    monkeypatch.setattr(consumer, '_receipt_completion', lambda *a: pytest.fail('completion rerun'))
    monkeypatch.setattr(consumer, 'outcome', lambda *a: pytest.fail('execution rerun'))
    consumer.kick()
    assert calls == ['완료']
    assert 'delivery_pending' not in journal.read('done', tmp_path)
    assert repair_root.projection(tmp_path, 'done')['complete']
    assert repair_root.projection(tmp_path, 'done')['delivery_status'] == 'delivered'
    monkeypatch.setattr(consumer, '_last_scan', 0)
    consumer.kick()
    assert calls == ['완료']


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
