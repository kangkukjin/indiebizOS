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


# ── B25-1 회귀 (2026-08-23 상상훈련 25회차) ──────────────────────────────────
# 조건 좌변이 소스 참조(`node:action{}.경로`)든 변수 참조(`$r.경로`)든 **같은 경로
# 해소기**를 쓴다. 갈라지면 한 문법이 좌변 종류에 따라 두 갈래가 되고, 소스 참조
# 쪽 판정 불능은 else 까지 보류시켜 문장을 통째로 죽인다(보고서 최소 재현 (a)(b)(c)).
import ibl_exec_sense as es                                    # noqa: E402
from ibl_predicates import walk_path, _MISSING as _PRED_MISSING  # noqa: E402

_ENVELOPE = {
    "city": "청주",
    "current": {"temp": 24.7, "condition": "대체로 맑음"},
    "items": [{"date": "2026-08-22", "max_temp": 30.3, "min_temp": 23.4},
              {"date": "2026-08-23", "max_temp": 33.4, "min_temp": 23.8}],
}


def test_source_ref_walks_list_index():
    """(b) 소스 참조의 리스트 인덱스 — 옛 판은 여기서 _FIELD_MISSING 이었다."""
    assert es._extract_dotted_field_checked(_ENVELOPE, "items.0.max_temp") == 30.3


def test_source_and_var_resolvers_agree():
    """(a)(b)(c) 불변식 — 두 좌변이 같은 경로에 같은 값을 내야 한다."""
    for path in ("items.0.max_temp", "items.1.min_temp", "current.temp", "city"):
        src = es._extract_dotted_field_checked(_ENVELOPE, path)
        var = walk_path(_ENVELOPE, path)
        assert src == var, (path, src, var)


def test_absent_path_still_missing():
    """★B10-case 계약 보존 — 부재는 여전히 부재(값 null 과 구별)."""
    for path in ("items.9.max_temp", "items.0.없는칸", "current.없음", "없는키",
                 "city.max_temp"):
        assert es._extract_dotted_field_checked(_ENVELOPE, path) is es._FIELD_MISSING, path
    assert walk_path(_ENVELOPE, "items.9.max_temp") is _PRED_MISSING


def test_null_value_is_not_missing():
    """필드는 실존하되 값이 null 이면 부재가 아니다(정당한 부재)."""
    env = {"items": [{"battery_percent": None}]}
    assert es._extract_dotted_field_checked(env, "items.0.battery_percent") is None


def test_hints_show_list_row_paths():
    """힌트가 `items` 에서 멈추지 않는다 — 결함의 공범이었던 자리."""
    hints = es._field_path_hints(_ENVELOPE)
    assert any(h.startswith("items.0.") for h in hints), hints
    assert "items" not in hints, hints


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    # ★두 번째 러너를 두지 않는다. 손으로 적은 러너는 반드시 드리프트한다 — 새 시험 함수를
    # 러너에 안 적으면 직접 실행이 **그 시험만 조용히 건너뛰고 종료코드 0** 을 낸다.
    # 실측(2026-08-23): 배터리 44개·시험 303건 중 **147건**이 직접 실행에서 한 번도 안 돌았고,
    # 27·28회차 상상훈련이 그 초록을 "전부 통과"로 보고서에 적었다(거짓 초록).
    # 위임하면 직접 실행도 살고(순찰·손버릇) 수집은 pytest 가 하므로 드리프트가 불가능하다.
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__, "-q"] + _sys.argv[1:]))
