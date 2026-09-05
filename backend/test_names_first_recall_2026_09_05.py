"""이름 먼저 회상 (2026-09-05, 처방 1 — 사용자 판정 "그 순서대로 착수").

recall{store:"실행"} 이 모델에게 주는 것은 *부를 수 있는 이름*이지 베낄 본문이 아니다:
  · 이름 있는 관용구 → 서명(호출 한 줄)·문장 수·성공/실패·마지막 날짜. 본문은 expand:"이름" 으로만.
  · 한 문장 용례 → 그대로(낱말 사용이지 프로그램 베끼기가 아니다).
  · 여러 문장 무명 용례 → 문장 수만(이름이 붙기 전까지 expand:"#id").
  · 주행 절 → 건수만(expand:"주행").
상시 `<ibl_idioms>` 블록도 호출 한 줄만 싣고 `[def:]` 본문을 내리지 않는다.

실행: .venv/bin/python -m pytest -q backend/test_names_first_recall_2026_09_05.py
"""
import sqlite3
import sys
from datetime import datetime

import pytest

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: E402,F401

SINGLE = '[self:ledger]{path: "outputs/x/_covered.json", op: "select", target: "covered"}'
MULTI = ('$원장 = [self:ledger]{path: "outputs/x/_covered.json", op: "select"}; '
         '$검색 = [sense:search_youtube]{query: "AI", limit: 12} >> [table:dedup]{by: "video_id"}; '
         '$검색 >> [self:write]{path: "outputs/x/r.md"}')
PHRASE = ('$원장 = [self:ledger]{path: "${원장경로}", op: "select"}; '
          '$검색 = [sense:search_youtube]{query: "${주제}", limit: 12} >> [table:dedup]{by: "video_id"}')


def _mk_db(path):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE ibl_examples (
            id INTEGER PRIMARY KEY AUTOINCREMENT, intent TEXT NOT NULL, ibl_code TEXT NOT NULL,
            nodes TEXT DEFAULT '', category TEXT DEFAULT 'single', difficulty INTEGER DEFAULT 1,
            source TEXT DEFAULT 'synthetic', success_count INTEGER DEFAULT 0, fail_count INTEGER DEFAULT 0,
            avg_ms REAL DEFAULT -1.0, avg_tokens REAL DEFAULT -1.0, tags TEXT DEFAULT '',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, topic TEXT DEFAULT '', alias TEXT DEFAULT '');
    """)
    conn.commit(); conn.close()


def _add(db, intent, code, topic, category="single", alias="", ok=0):
    now = datetime.now().isoformat()
    conn = sqlite3.connect(db)
    cur = conn.execute("INSERT INTO ibl_examples (intent, ibl_code, category, alias, success_count, created_at, updated_at, topic) "
                       "VALUES (?,?,?,?,?,?,?,?)", (intent, code, category, alias, ok, now, now, topic))
    conn.commit(); conn.close()
    return cur.lastrowid


@pytest.fixture
def env(tmp_path, monkeypatch):
    import hippo_tree as HT
    db = str(tmp_path / "usage.db"); _mk_db(db)
    monkeypatch.setattr(HT, "DOC_DIR", str(tmp_path / "tree"))
    monkeypatch.setattr(HT, "GUIDE_DB_PATH", str(tmp_path / "guide_db.json"))
    monkeypatch.setattr(HT, "_default_db_path", lambda: db)
    return HT, db


def test_recall_shows_names_not_bodies(env):
    HT, db = env
    t = "보고서/유튜브 AI 팁"
    s_id = _add(db, "원장을 id·verdict 로 읽는다", SINGLE, t)
    m_id = _add(db, "팁 보고서 전 과정", MULTI, t, category="pipeline")
    p_id = _add(db, "후보 영상을 모은다", PHRASE, t, category="phrase", alias="팁영상수집", ok=3)
    HT.note_run(t, "오늘 주행", [SINGLE, MULTI], ok=True, db_path=db)
    out = HT.recall(t, db)
    text = out["text"]
    assert "## 부를 수 있는 함수" in text and "[fn:팁영상수집]{원장경로: \"…\", 주제: \"…\"}" in text
    assert "✓3" in text
    assert "[def: 팁영상수집]{" not in text and "search_youtube" not in text.split("## 용례")[0].split("## 부를 수 있는 함수")[1]
    # 한 문장 용례는 그대로, 여러 문장 무명 용례는 문장 수만
    assert SINGLE.replace("`", "'") in text
    assert "[self:write]" not in text and f"expand:\"#{m_id}\"" in text and "문장 3" in text
    assert "## 주행 1건" in text and "expand:\"주행\"" in text
    # JSON 봉투도 본문을 감춘다(모델은 text 만 읽지 않는다)
    items = {r["id"]: r for r in out["items"]}
    assert items[s_id]["ibl_code"] == SINGLE
    assert "expand" in items[m_id]["ibl_code"] and "[self:write]" not in items[m_id]["ibl_code"]
    ph = out["phrases"][0]
    assert ph["alias"] == "팁영상수집" and ph["call"].startswith("[fn:팁영상수집]") and "expand" in ph["ibl_code"]
    assert out["expand_hint"]


def test_expand_opens_one_body(env):
    HT, db = env
    t = "보고서/유튜브 AI 팁"
    m_id = _add(db, "팁 보고서 전 과정", MULTI, t, category="pipeline")
    _add(db, "후보 영상을 모은다", PHRASE, t, category="phrase", alias="팁영상수집")
    HT.note_run(t, "오늘 주행", [SINGLE, MULTI], ok=True, db_path=db)
    body = HT.recall(t, db, expand="팁영상수집")["text"]
    assert body.startswith("[def: 팁영상수집]{") and "search_youtube" in body and "호출:" in body
    one = HT.recall(t, db, expand=f"#{m_id}")["text"]
    assert "[self:write]" in one
    runs = HT.recall(t, db, expand="주행")["text"]
    assert runs.startswith("## 주행") and "오늘 주행" in runs
    assert "없습니다" in HT.recall(t, db, expand="없는이름")["text"]
    assert HT.recall(t, db, expand="all")["text"].startswith("<!-- hippo-topic")


def test_idioms_block_has_no_def_bodies():
    import ibl_access
    ibl_access._idioms_cache.update({"t": 0.0, "text": "", "key": "x"})   # 캐시 무효화
    text = ibl_access._idioms_block(None)
    if not text:
        pytest.skip("관용구 원장이 비어 있음")
    assert not any(l.startswith("  [def:") or l.startswith("    [") for l in text.splitlines()), "본문 블록이 실려 있다"
    assert "[fn:" in text and "expand" in text


if __name__ == "__main__":
    # 러너는 하나다 — 직접 실행도 pytest 에 위임한다.
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
