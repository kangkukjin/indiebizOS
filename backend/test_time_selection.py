"""시간 선택압 관문 — 해마에 '빠르기' 축이 실제로 흐르는지 (2026-08-30).

배경: 시스템에 시간이 좌표(스케줄러·타임스탬프)로는 있었지만 **비용**으로는 없었다 —
같은 목표를 3초에 이루든 3분에 이루든 같은 성공이라 빨라질 유인이 없었다(사용자 판정:
"어떤 일을 시키면 그걸 더 빨리 하는 것에 인센티브가 없어" → 2번안 집행).

처방은 훈계(프롬프트 문장)가 아니라 이음매 4곳:
  ① 측정: agent_pipeline._collect 가 tool_start→tool_result 에서 elapsed_ms 도장
  ② 귀속: record_recall_outcome → update_success_by_code(avg_ms EWMA, 성공 실행만)
  ③ 생존: consolidate_distilled 근접중복 정리에서 같은 신뢰면 빠른 표현이 살아남음
  ④ 표시: 회상 XML 에 avg_ms 속성 — 리랭킹이 아니라 표시로 AI 가 판단(success_rate 철학)

이 배터리는 ②③④와 증류 출생 실측(_ibl_elapsed_ms)을 잰다. ①은 프로세스 내 스트림
이벤트라 여기선 계약(키 이름 elapsed_ms)만 ②의 입력으로 공유한다.

실행: .venv/bin/python -m pytest backend/test_time_selection.py
"""
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401


@pytest.fixture
def db(tmp_path, monkeypatch):
    """임시 DB 위의 IBLUsageDB — 라이브 해마·모델·vec 무접촉."""
    import ibl_usage_db as mod
    monkeypatch.setattr(mod, "DB_PATH", str(tmp_path / "usage.db"))
    monkeypatch.setattr(mod.IBLUsageDB, "_instance", None)
    monkeypatch.setattr(mod.IBLUsageDB, "_start_background_model_load",
                        classmethod(lambda cls: None))
    monkeypatch.setattr(mod.IBLUsageDB, "_index_single",
                        lambda self, *a, **k: None)
    monkeypatch.setattr(mod.IBLUsageDB, "_is_foreign_vocab",
                        staticmethod(lambda code: False))
    try:
        yield mod.IBLUsageDB()
    finally:
        mod.IBLUsageDB._instance = None  # 다음 시험이 실경로로 재초기화하게


def _avg_ms(db, example_id):
    with db._get_connection() as conn:
        return conn.execute("SELECT avg_ms FROM ibl_examples WHERE id=?",
                            (example_id,)).fetchone()["avg_ms"]


# ── T1: 마이그레이션 — 옛 스키마 DB 에 avg_ms 컬럼 보강 ────────────────────

def test_t1_migration_adds_avg_ms(tmp_path, monkeypatch):
    import ibl_usage_db as mod
    old = tmp_path / "old.db"
    conn = sqlite3.connect(old)
    conn.execute("""CREATE TABLE ibl_examples (
        id INTEGER PRIMARY KEY AUTOINCREMENT, intent TEXT NOT NULL,
        ibl_code TEXT NOT NULL, nodes TEXT DEFAULT '', category TEXT DEFAULT 'single',
        difficulty INTEGER DEFAULT 1, source TEXT DEFAULT 'synthetic',
        success_count INTEGER DEFAULT 0, fail_count INTEGER DEFAULT 0,
        tags TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    conn.execute("INSERT INTO ibl_examples (intent, ibl_code, created_at, updated_at) "
                 "VALUES ('옛 항목', '[self:script]{}', '2026-01-01', '2026-01-01')")
    conn.commit()
    conn.close()

    monkeypatch.setattr(mod, "DB_PATH", str(old))
    monkeypatch.setattr(mod.IBLUsageDB, "_instance", None)
    monkeypatch.setattr(mod.IBLUsageDB, "_start_background_model_load",
                        classmethod(lambda cls: None))
    try:
        db = mod.IBLUsageDB()
        with db._get_connection() as c:
            row = c.execute("SELECT avg_ms FROM ibl_examples LIMIT 1").fetchone()
        assert row["avg_ms"] == -1.0  # 기존 행=미측정 sentinel
    finally:
        mod.IBLUsageDB._instance = None


# ── T2: EWMA 귀속 — 성공 실행시간만, 실패·미측정은 불변 ────────────────────

def test_t2_ewma_success_only(db):
    eid = db.add_example("메일 확인", "[sense:email]{}", source="distilled")
    assert _avg_ms(db, eid) == -1.0  # 출생 미측정

    ok = db.update_success_by_code("[sense:email]{}", True, elapsed_ms=1000)
    assert ok and _avg_ms(db, eid) == 1000.0  # 첫 관측=그대로 채택

    db.update_success_by_code("[sense:email]{}", True, elapsed_ms=2000)
    assert _avg_ms(db, eid) == pytest.approx(1300.0)  # 0.7*1000 + 0.3*2000

    # 실패의 시간은 빠르기가 아니다 — avg_ms 불변, fail_count 만 증가
    db.update_success_by_code("[sense:email]{}", False, elapsed_ms=99999)
    assert _avg_ms(db, eid) == pytest.approx(1300.0)

    # 미측정 성공(다른 진입 경로) — 카운트만, EWMA 불변
    db.update_success_by_code("[sense:email]{}", True, elapsed_ms=None)
    assert _avg_ms(db, eid) == pytest.approx(1300.0)

    with db._get_connection() as conn:
        r = conn.execute("SELECT success_count, fail_count FROM ibl_examples "
                         "WHERE id=?", (eid,)).fetchone()
    assert (r["success_count"], r["fail_count"]) == (3, 1)


def test_t2b_birth_measurement(db):
    eid = db.add_example("빠른 조회", "[sense:price]{}", source="distilled", avg_ms=4200.0)
    assert _avg_ms(db, eid) == 4200.0


# ── T3: 증류 출생 실측 집계 — 성공한 execute_ibl 만 합산 ───────────────────

def test_t3_ibl_elapsed_aggregation():
    from ibl_usage_rag import _ibl_elapsed_ms
    calls = [
        {"tool_name": "execute_ibl", "input": {}, "success": True, "elapsed_ms": 1200},
        {"tool_name": "execute_ibl", "input": {}, "success": True, "elapsed_ms": 800},
        {"tool_name": "execute_ibl", "input": {}, "success": False, "elapsed_ms": 60000},  # 실패=제외
        {"tool_name": "web_search", "input": {}, "success": True, "elapsed_ms": 500},      # 비IBL=제외
        {"tool_name": "execute_ibl", "input": {}, "success": True},                        # 미측정=제외
    ]
    assert _ibl_elapsed_ms(calls) == 2000
    # 측정된 호출이 하나도 없으면 None (0 으로 오보하지 않는다 — 절단 정직과 같은 결)
    assert _ibl_elapsed_ms([{"tool_name": "execute_ibl", "input": {}, "success": True}]) is None
    assert _ibl_elapsed_ms([]) is None


# ── T4: 생존 선택 — 근접중복 정리에서 같은 신뢰면 빠른 표현이 남는다 ────────

def test_t4_dedup_prefers_faster_at_equal_trust():
    from ibl_usage_db import IBLUsageDB
    q = IBLUsageDB._dedup_quality
    fast = {"id": 1, "success_count": 3, "fail_count": 0, "avg_ms": 2000.0}
    slow = {"id": 2, "success_count": 3, "fail_count": 0, "avg_ms": 9000.0}
    unmeasured = {"id": 3, "success_count": 3, "fail_count": 0, "avg_ms": -1.0}
    assert max([slow, fast], key=q) is fast          # 같은 신뢰 → 빠른 쪽 생존
    assert max([unmeasured, slow], key=q) is slow    # 실측이 미측정을 이긴다

    # 시간은 성공률·검증량을 넘지 못한다 — 빠르지만 덜 검증된 표현이 밀어내지 않게
    proven_slow = {"id": 4, "success_count": 5, "fail_count": 0, "avg_ms": 9000.0}
    fast_flaky = {"id": 5, "success_count": 1, "fail_count": 1, "avg_ms": 500.0}
    assert max([fast_flaky, proven_slow], key=q) is proven_slow


# ── T5: 표시 — 회상 XML 에 avg_ms 속성(미측정은 숨김) ─────────────────────

def test_t5_reference_xml_shows_avg_ms():
    from ibl_usage_db import UsageExample
    from ibl_usage_rag import IBLUsageRAG
    measured = UsageExample(id=1, intent="메일 확인", ibl_code="[sense:email]{}",
                            nodes="sense", category="single", difficulty=1,
                            score=0.9, source="distilled", success_rate=1.0, avg_ms=1300.0)
    unmeasured = UsageExample(id=2, intent="가격 조회", ibl_code="[sense:price]{}",
                              nodes="sense", category="single", difficulty=1,
                              score=0.88, source="distilled", success_rate=-1.0, avg_ms=-1.0)
    xml = IBLUsageRAG()._format_references([measured, unmeasured])
    assert 'avg_ms="1300"' in xml
    assert xml.count("avg_ms=") == 1  # 미측정은 숨김(-1 sentinel 미노출)
    assert "avg_ms는 과거 성공 실행의 평균 소요시간" in xml  # 필드 설명이 note 에 있음


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-q"]))
