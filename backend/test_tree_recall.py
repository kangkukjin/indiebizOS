"""트리 기억 공통 회상(tree_recall) — 가지 먼저·안/밖·색인 재사용·심층기억 어댑터·주입 회귀 (2026-09-17).

실 인코더를 올리지 않는다: 토큰 해시로 만든 결정적 가짜 벡터로 기계 계약만 본다. 실 기억 DB 무접촉.
"""
import os
import re
import sqlite3
import sys
import zlib

import numpy as np
import pytest

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401

MEM_PKG = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                                        "data", "packages", "installed", "tools", "memory"))
if MEM_PKG not in sys.path:
    sys.path.insert(0, MEM_PKG)


def _fake_encode(texts):
    out = np.zeros((len(texts), 768), dtype="float32")
    for k, t in enumerate(texts):
        for tok in re.findall(r"[0-9A-Za-z가-힣]{2,}", t):
            out[k, zlib.crc32(tok.encode()) % 768] += 1.0
        n = np.linalg.norm(out[k]) or 1.0
        out[k] /= n
    return out


@pytest.fixture
def TR(tmp_path, monkeypatch):
    import tree_recall as T
    monkeypatch.setenv("INDIEBIZ_RECALL_INDEX_DIR", str(tmp_path / "ridx"))
    monkeypatch.setattr(T, "_model_state", "ready")
    calls = []
    monkeypatch.setattr(T, "_encode", lambda texts: (calls.append(len(texts)), _fake_encode(texts))[1])
    T._cache.clear()
    T.calls = calls
    return T


class _Store:
    def __init__(self, T, items, branches, key="t"):
        self.key, self._i, self._b, self._T = key, items, branches, T

    def items(self): return self._i
    def branches(self): return self._b
    def lexical(self, q, items): return self._T.lexical_rank(q, items)


def _world(T):
    I, B = T.Item, T.Branch
    items = [I("a1", ("여행", "속초"), "속초 호텔 예약 체스터톤스"), I("a2", ("여행", "속초"), "속초 점심 생선구이"),
             I("a3", ("여행", "속초"), "속초 출발 시각 아홉시"), I("b1", ("가족",), "어머니 수원 거주"),
             I("c1", ("취향", "음식"), "호텔 조식 대신 시장 음식 선호")]
    branches = [B(("여행",), "여행 계획"), B(("여행", "속초"), "속초 여행 숙소 호텔 일정"),
                B(("가족",), "가족 구성"), B(("취향", "음식"), "음식 취향")]
    return items, branches


def test_branch_first_inside_and_outside(TR):
    items, branches = _world(TR)
    r = TR.recall(_Store(TR, items, branches), "속초 호텔 방에서 요리할 수 있나", n_branches=1)
    assert r["status"] == "ok" and r["branches"][0] == ("여행", "속초")
    assert len(r["items"]) == 2 and all(it.path == ("여행", "속초") for it in r["items"])
    assert len(r["outside"]) == 1 and r["outside"][0].path != ("여행", "속초")
    assert r["items"][0].id == "a1"


def test_see_also_widens_the_inside(TR):
    items, _ = _world(TR)
    B = TR.Branch
    branches = [B(("여행", "속초"), "속초 여행 숙소 호텔 일정", see_also=(("취향", "음식"),)), B(("가족",), "가족 구성"),
                B(("취향", "음식"), "음식 취향")]
    r = TR.recall(_Store(TR, items, branches), "속초 호텔 조식", n_branches=1, k_in=3)
    assert ("취향", "음식") in r["branches"] and "c1" in [it.id for it in r["items"]]


def test_branch_filter_skips_routing(TR):
    items, branches = _world(TR)
    r = TR.recall(_Store(TR, items, branches), "호텔", branch_filter=[("가족",)], k_in=1)
    assert r["branches"] == [("가족",)] and [it.id for it in r["items"]] == ["b1"]


def test_without_encoder_only_lexical_and_no_branch_claim(TR, monkeypatch):
    monkeypatch.setattr(TR, "_model_state", "failed")
    items, branches = _world(TR)
    r = TR.recall(_Store(TR, items, branches), "생선구이")
    assert r["status"] == "lexical_only" and r["branches"] == [] and r["items"][0].id == "a2"
    assert TR.recall(_Store(TR, items, branches), "전혀없는말")["items"] == []


def test_index_reencodes_only_changed_text(TR):
    items, branches = _world(TR)
    s = _Store(TR, items, branches)
    TR.recall(s, "속초")
    first = sum(TR.calls)
    TR._cache.clear()                                         # 재기동 가정 — 디스크 색인에서 되살린다
    TR.calls.clear()
    TR.recall(s, "속초")
    assert sum(TR.calls) == 1, "질문 1건만 임베딩해야 한다"
    items[0] = TR.Item("a1", ("여행", "속초"), "속초 호텔 예약이 바뀌었다")
    TR._cache.clear(); TR.calls.clear()
    TR.recall(_Store(TR, items, branches), "속초")
    assert sum(TR.calls) == 2 and first > 2


def test_large_delta_goes_background_not_inline(TR, monkeypatch):
    I = TR.Item
    items = [I(str(k), ("가",), f"기억 {k}번") for k in range(TR.INLINE_SYNC_MAX + 5)]
    started = []
    monkeypatch.setattr(TR, "_sync_background", lambda store: started.append(store.key))
    r = TR.recall(_Store(TR, items, [TR.Branch(("가",), "가")], key="big"), "기억")
    assert r["status"] == "lexical_only" and started == ["big"]


def _mk_memory_db(path):
    conn = sqlite3.connect(path)
    conn.executescript("""CREATE TABLE memories (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT DEFAULT '',
        keywords TEXT DEFAULT '', content TEXT NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        used_at DATETIME DEFAULT NULL, source_ref TEXT DEFAULT NULL, node TEXT DEFAULT '');""")
    rows = [("의사결정", "호텔,속초", "속초 숙소 예약 완료 체스터톤스 호텔 " + "가" * 400, "2026-09-10T10:00:00", "여행 계획/속초"),
            ("사용자정보", "가족", "어머니는 수원에 거주", "2026-09-01T10:00:00", "가족"),
            ("작업기록", "점심", "속초 점심 후보 생선구이", "2026-09-12T10:00:00", "여행 계획/속초")]
    conn.executemany("INSERT INTO memories (category, keywords, content, created_at, node) VALUES (?,?,?,?,?)", rows)
    conn.commit(); conn.close()


def test_deep_store_truncates_label_and_cuts_by_time(TR, tmp_path):
    from recall_store import DeepMemoryStore, ITEM_CHARS
    db = str(tmp_path / "memory_x.db"); _mk_memory_db(db)
    s = DeepMemoryStore(db)
    long_one = next(it for it in s.items() if it.id == "1")
    assert long_one.path == ("여행 계획", "속초") and "‹#1›" in long_one.label and "…" in long_one.label
    assert len(long_one.label) < ITEM_CHARS + 40
    assert {b.path for b in s.branches()} >= {("여행 계획", "속초"), ("가족",)}
    assert [it.id for it in DeepMemoryStore(db, before="2026-09-05T00:00:00").items()] == ["2"]


def test_branch_entry_reads_cues_and_see_also(tmp_path):
    import memory_tree as MT
    p = tmp_path / "memory.md"
    p.write_text('<!-- memory-node agent="x" node="여행 계획/속초" -->\n# 기억\n> 속초 여행의 숙소·일정\n'
                 '찾는 말: 우리가 가는 호텔, 이번 여행\n함께 볼 가지: 취향/음식, 가족\n\n## 기억\n- [기타] x ‹#1›\n', encoding="utf-8")
    e = MT.entry_of(str(p))
    assert e == {"gist": "속초 여행의 숙소·일정", "cues": "우리가 가는 호텔, 이번 여행", "see_also": ["취향/음식", "가족"]}


def test_map_falls_back_to_top_level_when_long(tmp_path, monkeypatch):
    import memory_tree as MT
    rows = [{"node": "", "count": 0, "gist": ""}] + [
        {"node": n, "count": c, "gist": g} for n, c, g in
        [("여행", 1, "여행 요약"), ("여행/속초", 8, "속초 요약"), ("여행/서울", 3, ""), ("가족", 4, "가족 요약")]]
    monkeypatch.setattr(MT, "map_lines", lambda db: rows)
    assert "여행/속초 (8)" in MT.map_text("x")
    short = MT.map_text("x", max_chars=10)
    assert short.split("\n") == ["- 여행 (12 · 하위 2가지) — 여행 요약", "- 가족 (4) — 가족 요약"]


def test_injection_block_and_no_block_without_related(TR, tmp_path, monkeypatch):
    import associative_recall as AR
    db = str(tmp_path / "memory_x.db"); _mk_memory_db(db)
    scent = lambda q: AR._recalled_memory(AR.RecallRequest(None, q, [], "pipeline"), None).text
    monkeypatch.setattr(AR, "deep_memory_db", lambda runner: db)
    xml = scent("속초 호텔에서 요리할 수 있나")
    assert xml.startswith("<recalled_memory ") and "고른 가지:" in xml and "‹#1›" in xml and xml.count("\n- [") <= 3
    monkeypatch.setattr(AR, "deep_memory_db", lambda runner: "")
    assert scent("속초") == ""


def test_world_dictionary_matches_the_tree():
    """가지 사전(branches.yaml)은 트리와 같이 움직여야 한다 — 없는 경로·사전 없는 가지는 여기서 잡힌다."""
    from runtime_utils import get_base_path
    from world_recall_store import WorldStore
    store = WorldStore(get_base_path())
    assert store.unknown_dictionary_paths() == []
    missing = ["/".join(b.path) for b in store.branches() if not (b.cues or b.gist)]
    assert missing == [], f"사전 항목 없는 가지: {missing[:5]}"
    assert store.map_text().count(" · ") >= 10 and "\n" not in store.map_text()
    it = next(i for i in store.items() if i.id == "ortools")
    assert it.label.endswith(": OR-Tools") and len(it.path) == 2


def test_world_memory_block_dedupes_and_can_be_turned_off(TR, monkeypatch):
    import catalog_recall as C
    events = []
    monkeypatch.setattr(C, "_record", events.append)
    monkeypatch.setattr(C, "load_config", lambda root: {})
    monkeypatch.setattr(TR, "INLINE_SYNC_MAX", 10 ** 9)          # 가짜 인코더라 첫 색인을 그 자리에서 만든다
    xml = C.world_memory_for_turn("직원 근무표를 제약을 지키며 짜야 한다")
    assert xml.startswith("<world_map ") and "<world_memory " in xml and "고른 가지:" in xml
    body = xml.split("<world_memory", 1)[1]
    names = [l.split(": ", 1)[1] for l in body.split("\n") if ": " in l and not l.startswith(("고른 가지", " note"))][:3]
    assert 1 <= len(names) <= 3 and events[-1]["channel"] == "world_memory" and events[-1]["status"] == "ok"
    again = C.world_memory_for_turn("직원 근무표를 제약을 지키며 짜야 한다", lexical_snippet=" ".join(names))
    assert all(n not in again.split("<world_memory", 1)[-1] for n in names) or "<world_memory" not in again
    monkeypatch.setattr(C, "load_config", lambda root: {"world_memory": False})
    assert C.world_memory_for_turn("직원 근무표") == ""
    monkeypatch.setattr(C, "load_config", lambda root: {"semantic_enabled": False})     # 옛 자리표 키는 끄지 못한다
    assert C.world_memory_for_turn("직원 근무표") != ""


def test_search_floor_drops_unrelated_semantic_hits_but_keeps_lexical(TR):
    items, branches = _world(TR)
    s = _Store(TR, items, branches)
    assert TR.search(s, "전혀상관없는질문", min_sim=0.5)["ids"] == []        # 빈 목록이 정직한 답
    r = TR.search(s, "생선구이", min_sim=0.99)                               # 의미 채널은 다 떨어져도 글자로 잡힌 것은 남는다
    assert r["status"] == "ok" and r["ids"] == ["a2"]
    assert TR.search(s, "호텔", branch_filter=[("가족",)])["ids"] in (["b1"], [])


class _FakeModel:
    calls = 0

    def encode(self, texts, **kw):
        _FakeModel.calls += 1
        single = isinstance(texts, str)
        out = _fake_encode([texts] if single else list(texts))
        return out[0] if single else out


def test_memory_vectors_carry_encoder_stamp_and_rebuild_when_it_differs(tmp_path, monkeypatch):
    """기억의 벡터는 만든 인코더의 표식을 갖는다 — 어긋나면 쓰이기 전에 통째로 다시 만든다(2026-09-17).
    해마 재학습 때 심층기억 재색인이 빠져 옛 공간의 벡터가 남아 있던 결함(코사인 중앙 0.71)의 구조적 봉인."""
    pytest.importorskip("sqlite_vec")
    import memory_db as db
    path = str(tmp_path / "memory_x.db"); _mk_memory_db(path)
    monkeypatch.setattr(db, "_get_model", lambda: _FakeModel())
    monkeypatch.setattr(db, "_vec_stamp_value", lambda: "enc-A#1")
    assert db.get_meta(path, db.VEC_STAMP) is None
    assert db._ensure_vec_current(path) and db.get_meta(path, db.VEC_STAMP) == "enc-A#1"
    assert len(db._load_vectors(path)) == 3
    before = _FakeModel.calls
    assert db._ensure_vec_current(path) and _FakeModel.calls == before          # 표식이 맞으면 다시 만들지 않는다
    monkeypatch.setattr(db, "_vec_stamp_value", lambda: "enc-B#1")              # 인코더가 바뀌었다
    assert db._ensure_vec_current(path) and _FakeModel.calls > before
    assert db.get_meta(path, db.VEC_STAMP) == "enc-B#1" and len(db._load_vectors(path)) == 3


def test_memory_encoder_is_not_the_retrained_hippocampus_model():
    import inspect
    import memory_db as db
    src = inspect.getsource(db._get_model)
    assert "tree_recall" in src and "IBLUsageDB" not in src.split('"""')[-1]


if __name__ == '__main__':
    import sys, pytest
    sys.exit(pytest.main([__file__] + sys.argv[1:]))
