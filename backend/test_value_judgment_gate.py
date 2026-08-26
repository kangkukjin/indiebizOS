"""사설 값 판정 관문(check_value_judgment) 다리 시험 + 46회차 후속 스윕 행동 가드.

관문의 뜻: 값의 동등·순서·포함 판정은 common/value_semantics 한 벌 — 상상훈련이
칸을 파서 발견하기를 기다리지 않고, 사설 판정의 **탄생을 커밋 전에 차단**한다
(43~46회차 4연속 같은 속(사설 값 판정)의 새 종이 태어난 구조 원인의 근본 수리).
"""

import importlib.util
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts" / "check_value_judgment.py"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def checker():
    return _load(CHECKER, "vj_checker")


@pytest.fixture(scope="module")
def data_ops():
    return _load(ROOT / "data/packages/installed/tools/data-ops/handler.py",
                 "vj_data_ops")


# ── 관문 자체 ────────────────────────────────────────────────────────────────

def test_gate_passes_on_current_tree():
    """저장소 전체가 관문을 통과한다 — pre-commit 과 같은 판정을 CI 도 본다."""
    proc = subprocess.run([sys.executable, str(CHECKER)],
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_gate_has_teeth_on_planted_violations(checker, tmp_path):
    """심어 둔 위반을 문다 — 규칙 [A] 사설 정규화 매칭."""
    bad = tmp_path / "planted.py"
    bad.write_text(
        "def f(a, b, rows, cond):\n"
        "    x = a.lower() == b.lower()\n"                 # [A] 양측 정규화 비교
        "    y = str(a).lower() in str(b).lower()\n"       # [A] 옛 where_dsl 모양
        "    z = a.lower().startswith(b)\n"                # [A'] 메서드형 매칭
        "    ok = a.lower() == 'https'\n"                  # 통과 — 코드 소유 상수 대조
        "    return x, y, z, ok\n")
    hits = checker._scan_file(bad, "planted.py", census=False)
    assert len(hits) == 3, hits


def test_gate_respects_vj_ok_with_reason_only(checker, tmp_path):
    """vj-ok 는 사유가 있어야 통과 — 벌거벗은 억제는 불가."""
    with_reason = tmp_path / "a.py"
    with_reason.write_text("x = p.lower() == q.lower()  # vj-ok: 프로토콜 식별자\n")
    assert checker._scan_file(with_reason, "a.py", census=False) == []
    bare = tmp_path / "b.py"
    bare.write_text("x = p.lower() == q.lower()  # vj-ok\n")
    assert len(checker._scan_file(bare, "b.py", census=False)) == 1


def test_gate_delegation_passes(checker, tmp_path):
    """정본 심볼 위임은 통과한다 — 한 벌 채택이 벌칙이 되지 않는다."""
    good = tmp_path / "c.py"
    good.write_text(
        "from common.value_semantics import text_match, values_equal\n"
        "def f(a, b):\n"
        "    return text_match('contains', a.lower(), b) or values_equal(a, b)\n")
    assert checker._scan_file(good, "c.py", census=False) == []


def test_gate_surface_files_exist(checker):
    """명단의 조건 표면 파일은 실존한다 — 이사·개명 시 명단도 따라와야 한다."""
    for rel in checker.SURFACE_FILES:
        assert (ROOT / rel).exists(), rel


# ── 스윕 행동 가드 — 조건 언어의 살아있던 결함 2건 ──────────────────────────

def test_fullfield_search_does_not_promote_null_or_repr(data_ops):
    """연산자 없는 전-필드 substring 이 결측을 "None" 텍스트로 승격하지 않는다
    (B46-3 의 잔당 — census 가 적발). 구조 값의 repr 파편도 검색되지 않는다."""
    rows = {"items": [
        {"m": None}, {"m": ["가나"]}, {"m": "none 이라는 단어"},
    ]}
    result = data_ops._op_filter(rows, {"where": "none"})
    assert result["success"] is True
    assert [r["m"] for r in result["items"]] == ["none 이라는 단어"]
    # repr 파편("['가나']" 의 대괄호·따옴표)은 어떤 행도 잡지 않는다
    for probe in ("['", "']"):
        got = data_ops._op_filter(rows, {"where": probe})
        assert got.get("items") == [], (probe, got)


def test_fullfield_search_inherits_text_normalization(data_ops):
    """전-필드 검색도 eq 의 텍스트 계약(casefold·NFC)을 승계한다."""
    nfd = unicodedata.normalize("NFD", "가나다")
    rows = {"items": [{"t": nfd}, {"t": "Seoul Food"}]}
    assert len(data_ops._op_filter(rows, {"where": "가나"})["items"]) == 1
    assert len(data_ops._op_filter(rows, {"where": "seoul"})["items"]) == 1


def test_since_watch_uses_conditional_equality(data_ops, tmp_path, monkeypatch):
    """since watch 의 변화 판정은 values_equal — 생산자의 표기 변경(1→"1")을
    값 변화로 오보하지 않고, 실제 값 변화는 계속 신고한다."""
    import sqlite3

    db = tmp_path / "table_since.db"

    def _conn():
        conn = sqlite3.connect(str(db))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS since_seen ("
            " stream TEXT NOT NULL, k TEXT NOT NULL, watched TEXT,"
            " first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,"
            " PRIMARY KEY (stream, k))")
        return conn

    monkeypatch.setattr(data_ops, "_since_conn", _conn)
    base = {"items": [{"id": "r1", "가격": 1000}]}
    first = data_ops._op_since(base, {"key": "s", "by": "id", "watch": "가격"})
    assert first.get("seeded") is True
    # 표기만 변경(1000 → "1,000") — 변화 아님
    renotated = {"items": [{"id": "r1", "가격": "1,000"}]}
    second = data_ops._op_since(renotated, {"key": "s", "by": "id", "watch": "가격"})
    assert second["items"] == [], second
    # 실제 값 변화(1,000 → 2,000) — 신고
    changed = {"items": [{"id": "r1", "가격": 2000}]}
    third = data_ops._op_since(changed, {"key": "s", "by": "id", "watch": "가격"})
    assert len(third["items"]) == 1 and third["items"][0]["_since"] == "changed"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
