"""알림 발사 원장 회귀 — **전달은 휘발해도 원장은 남는다** (2026-08-23).

재현하는 결함(실측): 사용자가 "이 알림이 자꾸 뜬다"고 물었는데 **언제·무엇이·몇 번**
떴는지 되짚을 방법이 없었다. 알림함은 notification_manager 의 deque(maxlen=100) 뿐이라
백엔드가 리로드되면 통째로 사라진다(조사 시점 조회 = 0건). 원장이 없으면 같은 물음이
다음에도 추측으로 끝난다.

처방: 입구 한 곳(NotificationManager.create — 호출처 23곳이 전부 여기로 모인다)에서
world_pulse.db 의 notify_log 에 한 줄 남긴다. 격리 규율은 action_health 와 같은 한 벌
(_in_test_process / _in_rehearsal → source 컬럼) — 시험·리허설이 쏜 알림이 실사용
집계를 물들이지 않는다.

실행: .venv/bin/python -m pytest backend/test_notify_ledger.py
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401


def _tmp_pulse(tmp_path, monkeypatch):
    """notify_log 가 **없는** 빈 DB — 기존 설치와 같은 처지(지연 마이그레이션을 잰다)."""
    import pulse_db
    path = str(tmp_path / "world_pulse.db")
    sqlite3.connect(path).close()   # 파일만 있고 테이블은 없다

    def _get():
        c = sqlite3.connect(path, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr(pulse_db, "_get_pulse_db", _get)
    monkeypatch.setattr(pulse_db, "_NOTIFY_LOG_ENSURED", False, raising=False)
    return _get


def _rows(get):
    conn = get()
    try:
        out = [dict(r) for r in conn.execute("SELECT * FROM notify_log ORDER BY id")]
    except sqlite3.OperationalError:
        out = None      # 테이블 자체가 없다 = 원장이 아예 안 생겼다
    conn.close()
    return out


def test_n1_every_notification_leaves_one_line(tmp_path, monkeypatch):
    """발사 한 건 = 원장 한 줄. 없으면 '자꾸 뜬다'에 답할 근거가 없다."""
    import notification_manager as nm_mod
    get = _tmp_pulse(tmp_path, monkeypatch)

    mgr = nm_mod.NotificationManager()
    mgr.create(title="스케줄 실행 완료", message="'[IBL] youtube_ai_tips_daily'",
               type="success", source="scheduler", deliver=False)

    rows = _rows(get)
    assert rows is not None, "notify_log 가 없다 — 기존 설치에서 지연 마이그레이션이 안 돌았다"
    assert len(rows) == 1, f"발사 1건에 원장 {len(rows)}줄"
    r = rows[0]
    assert r["title"] == "스케줄 실행 완료"
    assert r["type"] == "success"
    assert r["emitter"] == "scheduler", "쏜 주체(emitter)가 안 남으면 '누가 뜨게 했나'를 못 센다"
    assert r["timestamp"], "시각이 없으면 '언제'를 못 센다"


def test_n2_empty_notification_is_not_a_notification(tmp_path, monkeypatch):
    """제목도 본문도 없는 껍데기는 알림이 아니다 — 원장도 남기지 않는다(21회차 규약과 일관)."""
    import notification_manager as nm_mod
    get = _tmp_pulse(tmp_path, monkeypatch)

    mgr = nm_mod.NotificationManager()
    mgr.create(title="", message="", source="scheduler", deliver=False)

    assert _rows(get) in (None, []), "빈 껍데기가 원장에 남았다"


def test_n3_gateway_path_is_logged_too(tmp_path, monkeypatch):
    """관문(notify_dispatch.notify_user)은 create(deliver=False) 로 들어온다 — 이 경로도 남아야 한다.

    입구가 둘로 보이지만 기록은 한 곳이라는 것을 못박는 시험. 여기가 빠지면
    메신저·손발·포털 알림이 통째로 원장 밖이 된다.
    """
    import notification_manager as nm_mod
    import notify_dispatch
    get = _tmp_pulse(tmp_path, monkeypatch)

    shared = nm_mod.NotificationManager()
    monkeypatch.setattr(nm_mod, "get_notification_manager", lambda: shared)
    monkeypatch.setattr(
        notify_dispatch, "deliver_notification",
        lambda title, body, kind="info", command=None, command_params=None, badge=True: True)

    notify_dispatch.notify_user(title="💬 홍길동", body="안녕하세요", source="messenger")

    rows = _rows(get)
    assert rows and len(rows) == 1, "관문 경로의 알림이 원장에 안 남았다"
    assert rows[0]["emitter"] == "messenger"


def test_n4_rehearsal_and_test_are_isolated(tmp_path, monkeypatch):
    """의도된 알림(시험·리허설)은 실사용 칸에 쌓이지 않는다 — action_health 와 같은 규율."""
    import notification_manager as nm_mod
    import pulse_db
    get = _tmp_pulse(tmp_path, monkeypatch)

    mgr = nm_mod.NotificationManager()
    mgr.create(title="시험 알림", message="x", source="system", deliver=False)   # 이 프로세스 = pytest

    monkeypatch.setattr(pulse_db, "_in_test_process", lambda: False)
    monkeypatch.setattr(pulse_db, "_context_isolation_source", lambda: "training")
    mgr.create(title="리허설 알림", message="y", source="system", deliver=False)

    monkeypatch.setattr(pulse_db, "_context_isolation_source", lambda: None)
    mgr.create(title="실사용 알림", message="z", source="system", deliver=False)

    got = [(r["title"], r["source"]) for r in _rows(get)]
    assert got == [("시험 알림", "test"), ("리허설 알림", "training"), ("실사용 알림", "usage")], got


def test_n5_ledger_never_kills_the_notification(tmp_path, monkeypatch):
    """원장이 고장 나도 알림은 산다 — 기록은 곁다리지 본체가 아니다."""
    import notification_manager as nm_mod
    import pulse_db
    _tmp_pulse(tmp_path, monkeypatch)

    def _boom(*a, **kw):
        raise RuntimeError("원장 고장")

    monkeypatch.setattr(pulse_db, "record_notification", _boom)
    mgr = nm_mod.NotificationManager()
    n = mgr.create(title="살아야 한다", message="본문", source="system", deliver=False)

    assert n and n.get("title") == "살아야 한다"
    assert mgr.get_all(limit=1)[0]["title"] == "살아야 한다"


def test_n6_schema_is_declared_once(tmp_path, monkeypatch):
    """새 설치(_init_pulse_db)와 기존 설치(지연 마이그레이션)가 같은 DDL 한 벌을 쓴다.

    복제하면 한쪽만 늘어나 두 설치의 원장이 조용히 갈린다(채널·오류 컬럼이 겪은 부류).
    """
    import pulse_db
    src = open(pulse_db.__file__, encoding="utf-8").read()
    assert src.count("CREATE TABLE IF NOT EXISTS notify_log") == 1, \
        "notify_log DDL 이 복제됐다 — _NOTIFY_LOG_DDL 한 벌만 둘 것"
    assert "_NOTIFY_LOG_DDL" in src and "_ensure_notify_log" in src


# ── 전달 격리 (2026-08-23) — 기록은 남고, 사용자에게는 닿지 않는다 ────────────────
# 실측된 결함: 회귀 배터리가 스케줄러 run_workflow 를 스텁 없이 실물 실행해
# "워크플로우 실행 완료/실패" 알림이 런처·OS 알림까지 나갔다(배터리 1회 = 4건).
# 코드를 고칠 때마다 사용자에게 유령 알림이 떴다. 시험 파일마다 스텁하는 대신
# 나가는 문(deliver_notification)에서 한 번 막는다 — 열거 목록은 반드시 뒤처지므로.


def _delivery_spies(monkeypatch):
    """진짜 출구 둘(런처 WS·OS 네이티브)에 스파이를 심는다."""
    import desktop_notify
    import websocket_manager
    seen = {"launcher": 0, "native": 0}
    monkeypatch.setattr(websocket_manager, "send_launcher_command_sync",
                        lambda *a, **kw: seen.update(launcher=seen["launcher"] + 1) or True)
    monkeypatch.setattr(desktop_notify, "native_notify",
                        lambda *a, **kw: seen.update(native=seen["native"] + 1))
    return seen


def test_n7_test_process_notifications_never_reach_the_user(tmp_path, monkeypatch):
    """시험이 만든 알림은 화면에 뜨지 않는다 — 그래도 원장에는 남는다(감사용)."""
    import notify_dispatch
    get = _tmp_pulse(tmp_path, monkeypatch)
    seen = _delivery_spies(monkeypatch)

    import notification_manager as nm_mod
    shared = nm_mod.NotificationManager()
    monkeypatch.setattr(nm_mod, "get_notification_manager", lambda: shared)

    delivered = notify_dispatch.notify_user(
        title="워크플로우 실행 완료", body="'_t_params_w15' (1/1 steps)", source="scheduler")

    assert delivered is False
    assert seen == {"launcher": 0, "native": 0}, \
        f"시험 알림이 사용자에게 전달됐다: {seen} — 유령 알림의 재발"
    rows = _rows(get)
    assert rows and rows[-1]["source"] == "test", "전달을 막느라 기록까지 잃었다(감사 불능)"


def test_n8_real_notifications_still_get_through(tmp_path, monkeypatch):
    """격리가 전달 자체를 죽이면 안 된다 — 실사용 알림은 그대로 닿는다."""
    import notify_dispatch
    _tmp_pulse(tmp_path, monkeypatch)
    seen = _delivery_spies(monkeypatch)
    monkeypatch.setattr(notify_dispatch, "_in_test_process", lambda: False)

    import notification_manager as nm_mod
    shared = nm_mod.NotificationManager()
    monkeypatch.setattr(nm_mod, "get_notification_manager", lambda: shared)

    delivered = notify_dispatch.notify_user(title="진짜 알림", body="사용자에게 닿아야 한다")

    assert delivered is True
    assert seen["launcher"] == 1, f"실사용 알림이 전달되지 않았다: {seen}"


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__] + _sys.argv[1:]))
