"""P1·P2 회귀 (2026-08-20 수리 배치): 조건 블록 관측 메타 + since 첫 검침 플래그.

  P2 — [if:]/[case:] 가 분기 결과에 matched(탄 분기 라벨)·matched_value(좌변 실측값)를
       병기한다. 종전엔 분기 결과만 반환해 오분기가 원리적으로 진단 불가였다.
       분기 결과가 곧 파이프 통화라 dict 일 때만 setdefault(기존 키 불침범),
       비-dict 결과는 감싸지 않는다(하류 통화 계약 보존).
  P1 — [table:since] 첫 검침이 seeded:true 를 신고한다(B15-2). note 산문만으론
       트리거가 "첫 회 0행"과 "고장 0행"을 기계적으로 구별할 수 없었다. 2회차 미표기.

실행: .venv/bin/python3 -m pytest backend/test_condition_observability.py
"""
import importlib.util
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: F401

import ibl_executors as ex


def _patched(monkeypatch, value=2500.0, branch_result=None):
    """좌변 읽기와 분기 실행을 결정론 스텁으로 — 실행 엔진 없이 관측 계약만 찌른다."""
    monkeypatch.setattr(ex, "_get_sense_value_checked", lambda s, p, a: (value, None))
    monkeypatch.setattr(ex, "_run_branch",
                        lambda action, ti, p, a: (branch_result if branch_result is not None
                                                  else {"ok": True}))


def test_if_matched_meta(monkeypatch):
    _patched(monkeypatch, value=2500.0)
    r = ex._execute_condition(
        {"branches": [{"condition": "sense:kospi > 2400", "action": {"x": 1}}]}, "/tmp", "t")
    assert r["matched"] == "sense:kospi > 2400" and r["matched_value"] == 2500.0, r


def test_if_else_meta(monkeypatch):
    _patched(monkeypatch, value=100.0)
    r = ex._execute_condition(
        {"branches": [{"condition": "sense:kospi > 2400", "action": {"x": 1}},
                      {"action": {"y": 2}}]}, "/tmp", "t")
    assert r["matched"] == "else", r


def test_if_nondict_passthrough(monkeypatch):
    """비-dict 분기 결과는 감싸지 않는다 — 통화 계약 보존."""
    _patched(monkeypatch, value=2500.0, branch_result="평문 결과")
    r = ex._execute_condition(
        {"branches": [{"condition": "sense:kospi > 2400", "action": {"x": 1}}]}, "/tmp", "t")
    assert r == "평문 결과"


def test_if_meta_no_overwrite(monkeypatch):
    """분기 결과가 이미 matched 키를 가지면 침범하지 않는다 (setdefault 계약)."""
    _patched(monkeypatch, value=1.0, branch_result={"matched": "고유값"})
    r = ex._execute_condition(
        {"branches": [{"condition": "sense:x == 1", "action": {"x": 1}}]}, "/tmp", "t")
    assert r["matched"] == "고유값"


def test_case_matched_meta(monkeypatch):
    _patched(monkeypatch, value="비")
    r = ex._execute_case(
        {"source": "sense:weather", "branches": [
            {"pattern": "비", "action": {"x": 1}},
            {"pattern": "맑음", "action": {"y": 2}}]}, "/tmp", "t")
    assert r["matched"] == "비" and r["matched_value"] == "비", r


def test_case_default_meta(monkeypatch):
    _patched(monkeypatch, value="눈")
    r = ex._execute_case(
        {"source": "sense:weather",
         "branches": [{"pattern": "비", "action": {"x": 1}}],
         "default": {"z": 3}}, "/tmp", "t")
    assert r["matched"] == "default" and r["matched_value"] == "눈", r


def test_bool_compat_wrapper(monkeypatch):
    """ibl_engine 재수출 계약 — _evaluate_sense_condition 은 여전히 bool 을 반환."""
    monkeypatch.setattr(ex, "_get_sense_value_checked", lambda s, p, a: (2500.0, None))
    assert ex._evaluate_sense_condition("sense:kospi > 2400", "/tmp", "t") is True
    assert ex._evaluate_sense_condition("sense:kospi < 2400", "/tmp", "t") is False


def test_since_seeded_flag(monkeypatch):
    """P1: 첫 검침 seeded:true, 2회차 미표기."""
    spec = importlib.util.spec_from_file_location(
        "dataops_handler",
        Path(__file__).resolve().parents[1]
        / "data/packages/installed/tools/data-ops/handler.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    td = tempfile.mkdtemp()
    db = str(Path(td) / "since.db")

    def fake_conn():
        conn = sqlite3.connect(db, timeout=10)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS since_seen ("
            " stream TEXT NOT NULL, k TEXT NOT NULL, watched TEXT,"
            " first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,"
            " PRIMARY KEY (stream, k))")
        return conn

    monkeypatch.setattr(mod, "_since_conn", fake_conn)
    prev = {"items": [{"url": "http://a", "title": "A"}]}
    r1 = mod._op_since(prev, {"key": "테스트스트림"})
    assert r1.get("seeded") is True and r1["items"] == [], r1
    r2 = mod._op_since(prev, {"key": "테스트스트림"})
    assert "seeded" not in r2, r2
