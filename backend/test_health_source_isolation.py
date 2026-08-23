"""건강 원장의 출처 격리 회귀 — **리허설은 삶이 아니다** (2026-08-23)

재현하는 결함(실측):
  ① 상상 훈련은 갭을 찾으려고 *일부러* 안 되는 문장·없는 종목(`ZZZZINVALID`)·빈 손을 밟는다.
     그 의도된 실패가 `action_health` 에 `source='usage'` 로 쌓였고, 8배 회차 **20분**이 남긴
     `table:flatten` 실패 32건이 **만성 실패 순위 1위**(7일 37건 중 86%)를 만들었다.
     사용자 알림함까지 올라갔던 B18-1 사고(자기시험의 의도된 실패)의 재연 직전이었다.
  ② 집계 질의 두 곳(건강 요약·X-Ray)이 `last_usage_failure` 만 `source` 를 보고
     `total`/`successes` 는 **출처 무관**으로 셌다 — 그래서 격리 표식을 달아도
     사용자가 보는 성공률에는 리허설이 계속 섞였다(flatten 40%).

처방(B18-1 과 같은 규율):
  · **지우지 않고 표식** — `source='training'`.
  · 판정은 이름 규약이 아니라 **행위자 봉투**(`origin: "training"` → actor_context 전파).
  · 판정은 **한 벌** — `thread_context.in_rehearsal()`, `pulse_db` 는 위임만.
  · 격리 SQL 조각도 **한 벌** — `pulse_db.NOT_ISOLATED_SQL`(두 집계가 같은 것을 쓴다).
  · `self_check`(12시간 순찰)은 격리하지 **않는다** — 몸이 스스로를 실제로 재는 진짜 신호다.

실행: .venv/bin/python -m pytest backend/test_health_source_isolation.py
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401


def _tmp_pulse(tmp_path, monkeypatch):
    """action_health 스키마만 있는 빈 DB — 라이브 원장 무접촉."""
    import pulse_db
    path = str(tmp_path / "world_pulse.db")
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE action_health (
        id INTEGER PRIMARY KEY AUTOINCREMENT, node TEXT NOT NULL, action TEXT NOT NULL,
        success INTEGER NOT NULL, response_ms INTEGER, source TEXT NOT NULL DEFAULT 'usage',
        timestamp TEXT NOT NULL, channel TEXT, error TEXT)""")
    conn.commit()
    conn.close()

    def _get():
        c = sqlite3.connect(path, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr(pulse_db, "_get_pulse_db", _get)
    monkeypatch.setattr(pulse_db, "_AH_COLS_ENSURED", True, raising=False)
    # 이 배터리 자신이 시험 프로세스라 B18-1 이 먼저 잡아 'test' 로 바꾼다 — 리허설 판정을
    # 재려면 그 앞 조항을 잠시 꺼야 한다(두 격리는 독립이고, 순서는 시험이 먼저가 맞다).
    monkeypatch.setattr(pulse_db, "_in_test_process", lambda: False)
    return _get


def _rows(get):
    conn = get()
    out = [dict(r) for r in conn.execute("SELECT node, action, success, source FROM action_health ORDER BY id")]
    conn.close()
    return out


def test_r1_judgment_is_single_sourced():
    """판정을 복제하면 원장마다 '리허설'이 다른 뜻이 된다 — pulse_db 는 위임만."""
    import pulse_db
    import thread_context
    assert callable(thread_context.in_rehearsal)
    src = open(pulse_db.__file__, encoding="utf-8").read()
    assert "REHEARSAL_ORIGINS" not in src, \
        "pulse_db 가 리허설 판정을 다시 복제했다 — thread_context.in_rehearsal 에 위임할 것"
    assert "from thread_context import in_rehearsal" in src


def test_r2_rehearsal_origin_is_marked(tmp_path, monkeypatch):
    """origin='training' 으로 실행된 액션은 실사용 칸에 쌓이지 않는다."""
    import pulse_db
    from thread_context import actor_context
    get = _tmp_pulse(tmp_path, monkeypatch)

    with actor_context(agent_id="system_ai", origin="training"):
        pulse_db.record_action_health("table", "flatten", False, 12, error="목록이 없습니다")
        pulse_db.record_action_health("table", "take", True, 3)
    # 봉투 밖 = 평범한 실사용
    pulse_db.record_action_health("table", "flatten", False, 9, error="진짜 실패")
    # 자가점검은 격리 대상이 아니다 — 몸이 스스로를 실제로 재는 신호
    pulse_db.record_action_health("sense", "weather", False, 5, source="self_check")

    rows = _rows(get)
    assert rows[0]["source"] == "training", rows      # 리허설 실패
    assert rows[1]["source"] == "training", rows      # 리허설 성공도 같은 출처
    assert rows[2]["source"] == "usage", rows         # 봉투 밖은 그대로
    assert rows[3]["source"] == "self_check", rows    # 순찰은 격리 안 함


def test_r3_origin_does_not_leak_after_context(tmp_path, monkeypatch):
    """봉투는 끝나면 걷힌다 — 다음 실행이 리허설로 오염되면 원장이 거짓말한다."""
    import pulse_db
    from thread_context import actor_context
    get = _tmp_pulse(tmp_path, monkeypatch)
    with actor_context(agent_id="system_ai", origin="training"):
        pulse_db.record_action_health("a", "x", True, 1)
    pulse_db.record_action_health("a", "y", True, 1)
    rows = _rows(get)
    assert [r["source"] for r in rows] == ["training", "usage"], rows


def test_r4_aggregates_exclude_isolated_sources():
    """집계가 격리 출처를 빼는가 — 같은 조각을 **한 벌**로 쓰는가.

    옛 질의는 `last_usage_failure` 만 source 를 보고 `total`/`successes` 는 안 봤다.
    그래서 표식을 달아도 사용자가 보는 성공률에는 리허설이 계속 섞였다.
    """
    import pulse_db
    assert pulse_db.NOT_ISOLATED_SQL and "training" in pulse_db.NOT_ISOLATED_SQL
    assert "self_check" not in pulse_db.NOT_ISOLATED_SQL, "순찰을 격리하면 진짜 신호가 사라진다"
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for rel in ("backend/cognition/world_pulse_health.py", "backend/surface/api_xray.py"):
        src = open(os.path.join(root, rel), encoding="utf-8").read()
        assert "NOT_ISOLATED_SQL" in src, f"{rel} 이 격리 조각을 안 쓴다 — 성공률에 리허설이 섞인다"
        assert "from pulse_db import NOT_ISOLATED_SQL" in src, \
            f"{rel} 이 조각을 복제했을 수 있다 — pulse_db 한 벌에서 가져올 것"


def test_r5_trainer_is_told_to_declare_origin():
    """가이드가 훈련자에게 봉투를 실으라고 말하는가 — 기전만 있고 지시가 없으면 안 실린다."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    guide = open(os.path.join(root, "data", "guides", "imagination_training.md"), encoding="utf-8").read()
    assert '"origin": "training"' in guide or "origin: \"training\"" in guide, \
        "훈련 가이드에 origin 봉투 지시가 없다"


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__] + _sys.argv[1:]))
