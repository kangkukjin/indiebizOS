"""낡은 관용구 덮어쓰기 + 우회의 사건화 (2026-09-07, 사용자 판정 "덮어쓰기로 가줘").

관측(유튜브팁 보고서 09-07 실행자 보고): `[fn:유튜브팁보고서작성]` 을 한 줄로 부르지 않고 expand 로 정의를 연 뒤
가이드 절차로 직접 수행했다 — 저장된 본문이 낡았다는 이유로. 실물 대조 결과 맞는 진단이었다(원장 #4423,
09-04 생성, ✓0/✗0, 본문은 검색 2갈래·심사 없음인데 가이드 §2-0 은 09-05·09-06 두 번 개정으로 5갈래·심사 한 칸).
틀린 것은 마지막 한 문장 — "다음 증류가 관용구를 갱신할 것이다". 증류에는 갱신 경로가 **없었다**:
`unique_fn_name` 은 같은 이름·다른 골격에 `이름2` 를 주고 `add_example` 은 삽입뿐이라 낡은 정의가 이름을 붙든 채
남는다. 우회할수록 실행 0 이 유지되고, 실행 0 이라 아무도 갱신하지 않는 자기강화 루프.

계약:
  A1  돈 적 없는(✓0/✗0) 같은 이름·다른 골격 → 덮어쓸 자리. 돈 적 있으면 아니다(이름2 로 간다).
  A2  가지가 다르면 남의 함수다 — 덮지 않는다.
  A3  이름이 달라도 새 골격이 돈 적 없는 이름의 **변형**이면 그 이름을 물려받는다(ep2952 의 실물 모양).
  A4  replace_example: id 를 지키고 본문·이름·서명을 갈고 우회 횟수를 0 으로 되돌린다. 성공/실패는 건드리지 않는다.
  B1  record_bypass: 이름이 있는데 부르지 않고 손으로 친 실행 하나가 누계로 쌓인다. 실패로 세지 않는다.
  B2  표면이 말한다 — expand 카드·이름 지도가 '거부 N회'.
  B3  부르지 않고 베낀 턴은 '회상된 관용구를 썼다' 가 아니다(그 오판이 갱신본의 증류를 막던 마지막 문).

임시 DB 만 만진다 — 실 해마·임베딩·트리 무접촉.
실행: .venv/bin/python -m pytest backend/test_stale_idiom_overwrite_2026_09_07.py -q
"""
import os
import sqlite3
import sys

import pytest

BACKEND = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND)
import boot_paths  # noqa: E402,F401

# 낡은 본문(검색 2갈래) / 새 본문(검색 3갈래 + 심사 한 칸) — 유튜브팁 보고서의 실제 드리프트 모양을 줄인 것
OLD = '#!ibl edition=2\n[def:유튜브팁보고서작성]($주제){return [sense:search]{query:$주제}}'
NEW = '#!ibl edition=2\n[def:유튜브팁보고서작성]($주제){return [sense:search]{query:$주제,limit:20}}'

TOPIC = "보고서/유튜브 AI 팁"


class _FakeDB:
    """원장 표면만 흉내내는 시험용 몸 — 실 임베딩·트리를 부르지 않는다."""

    def __init__(self, path):
        self.path = str(path)
        self.indexed = []
        conn = sqlite3.connect(self.path)
        conn.execute("""CREATE TABLE ibl_examples (
            id INTEGER PRIMARY KEY AUTOINCREMENT, intent TEXT, ibl_code TEXT, nodes TEXT DEFAULT '',
            category TEXT DEFAULT 'single', difficulty INTEGER DEFAULT 1, source TEXT DEFAULT 'synthetic',
            success_count INTEGER DEFAULT 0, fail_count INTEGER DEFAULT 0, avg_ms REAL DEFAULT -1.0,
            avg_tokens REAL DEFAULT -1.0, tags TEXT DEFAULT '', created_at TEXT, updated_at TEXT,
            topic TEXT DEFAULT '', alias TEXT DEFAULT '', returns TEXT DEFAULT '', signature TEXT,
            returns_observed TEXT DEFAULT '', provenance TEXT DEFAULT '',
            bypass_count INTEGER DEFAULT 0, executable INTEGER DEFAULT 1)""")
        conn.execute('CREATE VIEW ibl_current_examples AS SELECT * FROM ibl_examples WHERE executable=1')
        conn.commit()
        conn.close()

    def _get_connection(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _index_single(self, example_id, intent, ibl_code):
        self.indexed.append((example_id, intent, ibl_code))

    def find_phrase_by_alias(self, name):
        from ibl_name_search import find_phrase_by_alias
        return find_phrase_by_alias(self, name)

    def add(self, alias, code, *, topic=TOPIC, ok=0, fail=0, bypass=0, intent="뜻"):
        with self._get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO ibl_examples (intent, ibl_code, category, topic, alias, success_count, fail_count, "
                "bypass_count, created_at, updated_at) VALUES (?,?,'phrase',?,?,?,?,?,'2026-09-04','2026-09-04')",
                (intent, code, topic, alias, ok, fail, bypass))
            from test_function_support import import_memory
            import_memory(conn)
            if ok or fail:
                from function_store import resolve, reference
                from capability_history import record_function_call
                from ibl_edition import source_edition
                ref = reference(resolve(alias, include_inactive=True))
                for i in range(ok + fail):
                    record_function_call(ref, f"fixture-{alias}-{i}", "call", success=i < ok,
                                         dependency_revision="fixture", source_complete=True)
            conn.commit()
            return cur.lastrowid

    def row(self, example_id):
        with self._get_connection() as conn:
            return dict(conn.execute("SELECT * FROM ibl_examples WHERE id=?", (example_id,)).fetchone())


@pytest.fixture
def db(tmp_path, monkeypatch):
    import ibl_usage_db
    monkeypatch.setattr(ibl_usage_db, "_tree_refresh", lambda *a, **k: None)   # 실 가지 문서 무접촉
    return _FakeDB(tmp_path / "usage.db")




# ─────────────────────────────────────────────────────── A1~A3 덮어쓸 자리 판정














# ─────────────────────────────────────────────────────────── A4 실제 덮어쓰기


def test_a4_파싱_불가_본문은_덮지_않는다(db):
    from ibl_name_search import replace_example
    rid = db.add("유튜브팁보고서작성", OLD)
    assert replace_example(db, rid, intent="x", ibl_code="이건 그냥 산문이다", alias="유튜브팁보고서작성") == 0
    assert db.row(rid)["ibl_code"] == OLD                # 낡았어도 파싱 되는 본문이 낫다


# ───────────────────────────────────────────────────────────── B1~B2 우회 기록
def test_b1_우회는_누계로_쌓이고_실패로_세지_않는다(db):
    from ibl_name_search import record_bypass
    rid = db.add("유튜브팁보고서작성", OLD)
    assert record_bypass(db, "유튜브팁보고서작성") == 1
    assert record_bypass(db, "유튜브팁보고서작성") == 2
    r = db.row(rid)
    assert r["bypass_count"] == 2 and r["fail_count"] == 0     # 정의가 실패한 게 아니라 거부당한 것이다
    assert record_bypass(db, "없는이름") == 0
    assert record_bypass(db, "") == 0


def test_b2_표면이_거부를_말한다(db):
    import hippo_tree
    rid = db.add("유튜브팁보고서작성", OLD, bypass=4)
    card = hippo_tree.phrase_expand_card(db.row(rid))
    assert "실행 0" in card and "거부 4회" in card
    assert card.index("호출:") < card.index("[def:")           # 호출 한 줄이 여전히 먼저(09-07 관문 1)
    # 거부가 없으면 그 말은 없다 — 아직 안 써 본 새 정의를 낡았다고 하지 않는다
    fresh = db.add("새이름", NEW.replace("유튜브팁보고서작성", "새이름"))
    assert "거부" not in hippo_tree.phrase_expand_card(db.row(fresh))


# ───────────────────────────────────────────── B3 베낀 턴은 '썼다' 가 아니다


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-q"]))
