"""원샷 잠금 전경 우선 회귀 테스트 (2026-09-02).

  ① 배경이 잡고 있는 동안 전경·배경이 함께 기다리면, 풀린 뒤 전경이 먼저 잡는다.
  ② 전경 대기자가 없으면 배경끼리는 선착순(기아 없음).
  ③ distill_queue 워커 스레드는 배경 표식을 달고 실행한다.

실행: .venv/bin/python -m pytest -q backend/test_oneshot_priority.py
"""
import sys
import threading
import time

import pytest

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401


def _contend(lock, order, name, background, start_evt):
    start_evt.wait()
    with lock.held(background=background):
        order.append(name)


def test_foreground_acquires_before_waiting_background():
    from consciousness_agent import _PriorityLock
    lock = _PriorityLock()
    order, go = [], threading.Event()
    lock.acquire(background=True)                     # 배경 호출 진행 중
    bg2 = threading.Thread(target=_contend, args=(lock, order, "bg2", True, go))
    fg = threading.Thread(target=_contend, args=(lock, order, "fg", False, go))
    bg2.start(); time.sleep(0.05)                     # 배경이 먼저 줄을 선다
    fg.start(); go.set(); time.sleep(0.1)
    lock.release()                                    # 진행 중 호출 종료
    fg.join(2); bg2.join(2)
    assert order == ["fg", "bg2"], order              # 전경이 먼저
    assert lock.bg_yields >= 1


def test_backgrounds_are_fifo_without_foreground():
    from consciousness_agent import _PriorityLock
    lock = _PriorityLock()
    order, go = [], threading.Event()
    lock.acquire(background=True)
    ts = [threading.Thread(target=_contend, args=(lock, order, f"bg{i}", True, go)) for i in range(3)]
    for t in ts:
        t.start(); time.sleep(0.02)
    go.set(); time.sleep(0.1)
    lock.release()
    for t in ts:
        t.join(2)
    assert sorted(order) == ["bg0", "bg1", "bg2"] and len(order) == 3   # 기아 없음


def test_distill_worker_marks_background(tmp_path, monkeypatch):
    import pulse_db
    import distill_queue as dq
    import consciousness_agent as ca
    monkeypatch.setattr(pulse_db, "CONSCIOUSNESS_DB_PATH", tmp_path / "world_pulse.db")
    monkeypatch.setattr(dq, "RETRY_BACKOFF_SEC", (0, 0, 0))
    monkeypatch.setattr(dq.DistillQueue, "_instance", None)
    seen = {}

    class R:
        def _after_response(self, *a, **k):
            seen["bg"] = ca.is_oneshot_background()
    try:
        q = dq.DistillQueue.get()
        q.enqueue(R(), {"user_message": "u", "response": "a"},
                  ident={"registry_key": "p:a", "agent_id": "a"})
        assert q.drain(timeout=5)["drained"]
        assert seen == {"bg": True}
        assert ca.is_oneshot_background() is False      # 메인(전경) 스레드는 무표식
    finally:
        dq.DistillQueue._instance = None


if __name__ == "__main__":                      # 러너는 하나 — pytest
    sys.exit(pytest.main([__file__, "-q"]))
