"""작명 경로 두 벌의 관문 짝맞춤 + 굳은 몸 이름 회수 (2026-09-07 이름 전수 감사).

관측(이름 붙은 용례 44건 전수 감사): 40건 실행 0 인데 '실행 0' 은 한 부류가 아니었다 — 낡음(드리프트) 2건,
굳은 몸 6건, 너무 일반적인 골격 6건, 기회는 있었는데 안 불림 15건, 가지가 안 돎 5건.

이 시험이 지키는 것은 그중 **굳은 몸**: 본문에 홈 경로가 박혀 슬롯이 0 인 프로그램. 낡은 게 아니라
처음부터 다시 쓸 수 없다 — 이름을 불러도 남의 그날 그 파일을 다시 만질 뿐이라 영원히 실행 0 이다.
뿌리는 **관문을 한쪽 길에만 단 것**: 이름을 주는 길이 둘(관용구 증류 `_distill_phrase`, 낱말 자동 작명
`ibl_usage_rag`)인데 `_phrase_private_reason` 은 앞의 것에만 달려 있었다. 6건 전부 뒤의 길에서 태어났다.
`uncallable_reason`·`slot_values_ungrounded` 는 이 몸을 통과시킨다(슬롯이 없으면 값 접지는 검사할 것이 없다).

계약:
  G1  두 작명 경로가 같은 관문을 쓴다 — 개인 명사가 박힌 몸은 어느 길로도 **이름을 받지 못한다**.
  G2  이름은 안 주되 **용례로는 저장한다** — 그 턴에 실제로 일어난 일이라 본문을 잃으면 안 된다.
  G3  스윕의 대상 선정은 관문의 자와 같다 — 사람이 고른 목록으로 쓸지 않는다(고른 범위는 반드시 샌다).
  G4  실행 이력이 섞이면 스윕은 멈춘다 — 돈 적 있는 이름은 남의 이력이라 손으로 판정할 것.

임시 DB 만 만진다 — 실 해마·임베딩·트리 무접촉.
실행: .venv/bin/python -m pytest backend/test_name_gate_parity_2026_09_07.py -q
"""
import os
import sqlite3
import sys

BACKEND = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND)
import boot_paths  # noqa: E402,F401

from test_idiom_tier import _arm, GREP, READ, SLOTS, TOOL_CALLS  # noqa: E402  (정교한 하네스를 두 벌로 두지 않는다)

HOME_BODY = GREP + "\n" + READ          # 두 문장, 홈 경로가 슬롯으로 비워지지 않은 채 박혀 있다


# ───────────────────────────────────────────────────── G1·G2 작명 경로 짝맞춤
def test_g1_개인명사가_박힌_몸은_낱말_경로에서도_이름을_못_받는다(monkeypatch):
    saved = _arm(monkeypatch, {"intent": "찾아 읽기", "code": HOME_BODY, "topic": "개발/프론트",
                               "phrase": [], "slots": {}})
    import ibl_usage_rag as rag
    rag.distill_experience("찾아 읽기", TOOL_CALLS, top_score=0.3)
    assert saved, "용례 자체가 사라졌다 — 관문은 이름만 막아야 한다"
    assert saved[0]["ibl_code"] == HOME_BODY            # G2: 본문은 그대로 남는다
    assert (saved[0].get("alias") or "") == ""          # G1: 이름은 주지 않는다


def test_g1_슬롯으로_비운_몸은_이름을_받는다(monkeypatch):
    """관문이 '두 문장이면 무조건 거절' 로 넓어지지 않았는지 — 비워진 몸은 여전히 이름을 받는다."""
    clean = ('[self:grep]{pattern: "${패턴}", root_path: "${루트}", limit: 60}\n'
             '[self:read]{path: "${파일}", start_line: 440, end_line: 620}')
    saved = _arm(monkeypatch, {"intent": "찾아 읽기", "code": clean, "topic": "개발/프론트",
                               "code_name": "찾아읽기", "phrase": [], "slots": SLOTS})
    import ibl_usage_rag as rag
    rag.distill_experience("찾아 읽기", TOOL_CALLS, top_score=0.3)
    assert saved and (saved[0].get("alias") or "") == "찾아읽기"


def test_g1_두_경로가_같은_관문을_부른다():
    """짝이 맞는지 자리로도 확인 — 한쪽에만 달린 관문이 이 부류를 만들었다."""
    word = open(os.path.join(BACKEND, "cognition", "ibl_usage_rag.py"), encoding="utf-8").read()
    phrase = open(os.path.join(BACKEND, "cognition", "ibl_idiom.py"), encoding="utf-8").read()
    for gate in ("_phrase_private_reason", "uncallable_reason", "slot_values_ungrounded"):
        assert gate in word, f"낱말 자동 작명 경로에 {gate} 가 없다"
        assert gate in phrase, f"관용구 증류 경로에 {gate} 가 없다"


# ─────────────────────────────────────────────────────────── G3·G4 스윕 규율
def _arm_migration(m, monkeypatch, tmp_path, rows):
    """DB **와 스냅샷 자리 둘 다** 임시로 — 영속 경로를 하나만 임시화하면 시험이 실물을 덮는다
    (2026-09-07 실측: 첫 판이 실제 _backups 의 스냅샷을 시험 데이터로 덮어썼다)."""
    monkeypatch.setattr(m, "DB", _db(tmp_path, rows))
    monkeypatch.setattr(m, "SNAP_DIR", tmp_path / "_backups")


def _db(tmp_path, rows):
    p = tmp_path / "usage.db"
    c = sqlite3.connect(p)
    c.execute("""CREATE TABLE ibl_examples (id INTEGER PRIMARY KEY, intent TEXT, ibl_code TEXT,
                 category TEXT DEFAULT 'single', topic TEXT DEFAULT '', alias TEXT DEFAULT '',
                 success_count INTEGER DEFAULT 0, fail_count INTEGER DEFAULT 0, updated_at TEXT)""")
    c.executemany("INSERT INTO ibl_examples (id,intent,ibl_code,alias,success_count,fail_count) VALUES (?,?,?,?,?,?)",
                  rows)
    c.commit(); c.close()
    return p


def test_g3_스윕_대상은_관문이_고른다(tmp_path, monkeypatch):
    import migrate_private_body_aliases as m
    _arm_migration(m, monkeypatch, tmp_path, [
        (1, "굳은 것", HOME_BODY, "굳은이름", 0, 0),
        (2, "비워진 것", '[self:grep]{pattern: "${패턴}"}\n[self:read]{path: "${파일}"}', "성한이름", 0, 0),
        (3, "이름 없는 것", HOME_BODY, "", 0, 0),
    ])
    conn = m._conn()
    try:
        got = {h["alias"] for h, _ in m.targets(conn)}
    finally:
        conn.close()
    assert got == {"굳은이름"}                     # 비워진 몸도, 이름 없는 행도 건드리지 않는다
    assert m.strip(dry=False) == 1
    conn = m._conn()
    try:
        rows = {r["id"]: dict(r) for r in conn.execute("SELECT id, alias, ibl_code FROM ibl_examples")}
    finally:
        conn.close()
    assert rows[1]["alias"] == "" and rows[1]["ibl_code"] == HOME_BODY   # 이름만 떼고 본문은 남긴다
    assert rows[2]["alias"] == "성한이름"


def test_g4_실행_이력이_섞이면_멈춘다(tmp_path, monkeypatch):
    import migrate_private_body_aliases as m
    _arm_migration(m, monkeypatch, tmp_path, [
        (1, "굳었지만 돈 것", HOME_BODY, "돈이름", 2, 0),
        (2, "굳은 것", HOME_BODY, "굳은이름", 0, 0),
    ])
    assert m.strip(dry=False) == 0                 # 한 건도 쓰지 않는다
    conn = m._conn()
    try:
        aliases = {r[0] for r in conn.execute("SELECT alias FROM ibl_examples")}
    finally:
        conn.close()
    assert aliases == {"돈이름", "굳은이름"}


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-q"]))
