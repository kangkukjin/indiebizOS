"""시간·토큰 선택압 관문 — 해마에 '비용' 축이 실제로 흐르는지 (2026-08-30).

배경: 시스템에 시간이 좌표(스케줄러·타임스탬프)로는 있었지만 **비용**으로는 없었다 —
같은 목표를 3초에 이루든 3분에 이루든 같은 성공이라 빨라질 유인이 없었다(사용자 판정:
"어떤 일을 시키면 그걸 더 빨리 하는 것에 인센티브가 없어" → 2번안 집행). 같은 세션에서
토큰 축 추가(사용자: "토큰 소모를 상관없어하는 태도도 문제" — 단 품질을 깎아 아끼는 것은
금물). 두 축은 다른 낭비를 잰다 — avg_ms=IBL 실행의 빠르기, avg_tokens=그 표현을 두른
턴의 모델 소요(불필요한 서치·재시도가 찍히는 자리).

처방은 훈계(프롬프트 문장)가 아니라 이음매:
  ① 측정: agent_pipeline._collect 의 elapsed_ms 도장 + providers.base 턴 토큰 원장
           (contextvar — 프로바이더 스왑·oneshot 을 한 턴으로 겹쳐 적음)
  ② 귀속: record_recall_outcome → update_success_by_code(avg_ms·avg_tokens EWMA, 성공만)
  ③ 생존: 근접중복 정리 생존키 성공률→시도수→빠르기→토큰 검약→최신
  ④ 표시: 회상 XML avg_ms·avg_tokens 속성 — 리랭킹이 아니라 표시로 AI 가 판단

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


# ── T6: 토큰 EWMA — 성공만, 시간과 독립 누적 ──────────────────────────────

def _avg_tokens(db, example_id):
    with db._get_connection() as conn:
        return conn.execute("SELECT avg_tokens FROM ibl_examples WHERE id=?",
                            (example_id,)).fetchone()["avg_tokens"]


def test_t6_token_ewma_success_only(db):
    eid = db.add_example("파일 정리", "[self:files]{}", source="distilled")
    assert _avg_tokens(db, eid) == -1.0

    db.update_success_by_code("[self:files]{}", True, elapsed_ms=500, tokens=10000)
    assert _avg_tokens(db, eid) == 10000.0 and _avg_ms(db, eid) == 500.0

    db.update_success_by_code("[self:files]{}", True, tokens=20000)  # 시간 미측정 턴
    assert _avg_tokens(db, eid) == pytest.approx(13000.0)  # 0.7*10000 + 0.3*20000
    assert _avg_ms(db, eid) == 500.0                       # 미측정 축은 불변(독립)

    db.update_success_by_code("[self:files]{}", False, tokens=999999)  # 실패=불반영
    assert _avg_tokens(db, eid) == pytest.approx(13000.0)


def test_t6b_birth_tokens(db):
    eid = db.add_example("검색 요약", "[sense:search]{}", source="distilled",
                         avg_ms=3000.0, avg_tokens=15000.0)
    assert _avg_tokens(db, eid) == 15000.0


# ── T7: 턴 토큰 원장 — 프로바이더 스왑을 한 턴으로 겹쳐 적고, 0은 미측정 ────

def test_t7_turn_token_ledger():
    from providers.base import (ProviderMetrics, begin_turn_token_ledger,
                                read_turn_tokens)
    begin_turn_token_ledger()
    m1, m2 = ProviderMetrics(), ProviderMetrics()   # 실행 기어 + 스왑/oneshot 기어
    m1.record_request(100.0, input_tokens=8000, output_tokens=1200)
    m2.record_request(50.0, input_tokens=3000, output_tokens=800)
    assert read_turn_tokens() == 13000              # 인스턴스 무관, 턴 합산

    begin_turn_token_ledger()                       # 다음 턴 — 원장 리셋
    assert read_turn_tokens() is None               # 기록 0 = 미측정(0 오보 금지)
    m1.record_request(10.0)                         # usage 미보고 프로바이더(0,0)
    assert read_turn_tokens() is None


# ── T8: 생존 — 토큰 검약은 빠르기 다음, 신뢰를 넘지 못함 ───────────────────

def test_t8_dedup_token_axis():
    from ibl_usage_db import IBLUsageDB
    q = IBLUsageDB._dedup_quality
    base = {"success_count": 3, "fail_count": 0, "avg_ms": 2000.0}
    thrifty = {**base, "id": 1, "avg_tokens": 5000.0}
    wasteful = {**base, "id": 2, "avg_tokens": 40000.0}
    unmeasured = {**base, "id": 3, "avg_tokens": -1.0}
    assert max([wasteful, thrifty], key=q) is thrifty     # 같은 신뢰·같은 빠르기 → 검약 생존
    assert max([unmeasured, wasteful], key=q) is wasteful  # 실측이 미측정을 이긴다

    # 품질을 깎아 아끼는 선택은 키에서 불가능 — 성공률이 언제나 앞선다
    cheap_flaky = {"id": 4, "success_count": 1, "fail_count": 1,
                   "avg_ms": 100.0, "avg_tokens": 100.0}
    proven_costly = {"id": 5, "success_count": 5, "fail_count": 0,
                     "avg_ms": 9000.0, "avg_tokens": 90000.0}
    assert max([cheap_flaky, proven_costly], key=q) is proven_costly


# ── T9: 표시 — avg_tokens 속성(미측정 숨김) ───────────────────────────────

def test_t9_reference_xml_shows_avg_tokens():
    from ibl_usage_db import UsageExample
    from ibl_usage_rag import IBLUsageRAG
    ex = UsageExample(id=1, intent="메일 확인", ibl_code="[sense:email]{}",
                      nodes="sense", category="single", difficulty=1,
                      score=0.9, source="distilled", success_rate=1.0,
                      avg_ms=1300.0, avg_tokens=12500.0)
    bare = UsageExample(id=2, intent="가격 조회", ibl_code="[sense:price]{}",
                        nodes="sense", category="single", difficulty=1,
                        score=0.88, source="distilled", success_rate=-1.0)
    xml = IBLUsageRAG()._format_references([ex, bare])
    assert 'avg_tokens="12500"' in xml
    assert xml.count("avg_tokens=") == 1
    assert "품질을 깎아 아끼는 것은 금물" in xml  # 사용자 계약이 note 에 그대로


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-q"]))
