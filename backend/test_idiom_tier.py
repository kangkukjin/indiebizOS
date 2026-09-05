"""관용구 층(idiom tier) 회귀 — 낱말과 얼린 워크플로 사이의 가로대 (2026-09-04, docs/IBL_IDIOM_TIER_HANDOFF.md).

계약:
  P1  접지 = 순서 보존 부분열: 관용구의 각 문장은 슬롯을 이번 값으로 되돌렸을 때 실행 호출과 머리·인자 키가
      같아야 하고(문자열·수치는 비워 비교), 순서는 실행 순서의 부분열. 순서 어긋남·미실행 문장은 거절.
  P2  증류는 낱말(code)과 관용구(phrase)를 독립으로 저장한다 — 낱말이 스킵돼도 관용구는 산다. 관용구는
      category='phrase', 코드는 `; ` 로 이은 문장 열, 슬롯은 `${…}` 그대로(값은 저장하지 않는다).
  P3  회상된 관용구가 실행에 쓰였으면(머리 열 부분열 절반 이상) 새 관용구를 뽑지 않고, 귀속은 그 관용구에 간다.
  P4  가지 문서 `## 관용구` 절이 정본 — 렌더/파싱 왕복, 사람이 적은 새 블록은 색인 INSERT, 지우면 DELETE.
      지도에 `관용구 n`.
  P5  회상 XML: 낱말 채널은 관용구를 제외하고(반사 top-1 은 낱말만), 관용구는 kind="phrase" 번호 목록으로 실린다.
  P6  트레이너: 관용구는 별도 버킷·머리 열 패턴, 정규화가 `${슬롯}`·중첩 중괄호에서 잔해를 남기지 않는다.

임시 DB·임시 문서 폴더만 만진다 — 실 해마·임베딩·트리 무접촉.
실행: .venv/bin/python -m pytest backend/test_idiom_tier.py -q
"""
import json
import os
import sqlite3
import sys
import types
from datetime import datetime

import pytest

BACKEND = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND)
import boot_paths  # noqa: E402,F401

GREP = '[self:grep]{pattern: "notebook", root_path: "/Users/me/Desktop/AI/indiebizOS/frontend/src", limit: 60}'
READ = '[self:read]{path: "/Users/me/Desktop/AI/indiebizOS/frontend/src/components/GenericInstrument.tsx", start_line: 440, end_line: 620}'
EDIT = '[self:edit]{path: "/Users/me/Desktop/AI/indiebizOS/frontend/src/components/GenericInstrument.tsx", old_string: "a", new_string: "b"}'
PIPE = '[sense:search]{query: "AI 팁", limit: 12} >> [table:take]{n: 5}'
CALLS = [GREP, READ, EDIT, PIPE]
PHRASE = ['[self:grep]{pattern: "${패턴}", root_path: "${루트}", limit: 60}',
          '[self:read]{path: "${파일}", start_line: 440, end_line: 620}',
          '[self:edit]{path: "${파일}", old_string: "${앞}", new_string: "${뒤}"}']
SLOTS = {"패턴": "notebook", "루트": "/Users/me/Desktop/AI/indiebizOS/frontend/src",
         "파일": "/Users/me/Desktop/AI/indiebizOS/frontend/src/components/GenericInstrument.tsx", "앞": "a", "뒤": "b"}


# ---------------------------------------------------------------- P1 접지
def test_p1_ordered_subsequence_with_slots_grounds():
    import ibl_usage_rag as rag
    assert rag._phrase_grounded(PHRASE, SLOTS, CALLS) is None
    # 값이 달라도(수치·문자열) 머리·키가 같으면 접지 — 값만 추상화
    assert rag._phrase_grounded([PHRASE[0].replace("60", "10")], SLOTS, CALLS) is None
    # 부분열: 가운데를 건너뛰어도 순서만 맞으면 통과
    assert rag._phrase_grounded([PHRASE[0], PHRASE[2]], SLOTS, CALLS) is None


def test_p1_reorder_and_unexecuted_rejected():
    import ibl_usage_rag as rag
    why = rag._phrase_grounded([PHRASE[2], PHRASE[0]], SLOTS, CALLS)
    assert why and "순서" in why
    why = rag._phrase_grounded([PHRASE[0], '[self:write]{path: "${파일}", content: "x"}'], SLOTS, CALLS)
    assert why and "실행에 없음" in why
    # 인자 키는 부분집합이면 된다(모델이 선택 인자를 빼도 골격) — 실행에 없던 키는 거절
    assert rag._phrase_grounded(['[self:grep]{pattern: "${패턴}", limit: 60}'], SLOTS, CALLS) is None
    why = rag._phrase_grounded(['[self:grep]{pattern: "${패턴}", depth: 3}'], SLOTS, CALLS)
    assert why and "실행에 없음" in why
    # op(동사)는 값이 같아야 한다 — 머리·키가 같아도 op 가 다르면 다른 문장
    calls = ['[self:memory]{op: "recall", node: "x"}', '[self:memory]{op: "store", node: "x"}']
    assert rag._phrase_grounded(['[self:memory]{op: "recall", node: "${가지}"}', '[self:memory]{op: "store", node: "${가지}"}'], {"가지": "x"}, calls) is None
    why = rag._phrase_grounded(['[self:memory]{op: "store", node: "${가지}"}', '[self:memory]{op: "recall", node: "${가지}"}'], {"가지": "x"}, calls)
    assert why and "순서" in why
    # & 병렬문은 가지의 부분집합이면 접지, >> 파이프는 길이·연산자·머리 열이 같아야
    par = '[sense:search]{source: "gnews", query: "a", limit: 12} & [sense:search]{source: "naver", query: "b", limit: 10} & [sense:stock]{op: "quote", ticker: "^TNX"}'
    assert rag._phrase_grounded(['[sense:search]{source: "gnews", query: "${질의}", limit: 12} & [sense:stock]{op: "quote", ticker: "${지수}"}'], {"질의": "a", "지수": "^TNX"}, [par]) is None
    assert rag._phrase_grounded(['[sense:search]{query: "${질의}"} >> [table:take]{n: 5}'], {"질의": "AI 팁"}, CALLS) is None
    assert rag._phrase_grounded(['[sense:search]{query: "${질의}"} >> [table:take]{n: 5} >> [table:sort]{by: "x"}'], {"질의": "AI 팁"}, CALLS)
    # 별개 호출을 >> 로 봉합한 문장은 실행에 없다
    why = rag._phrase_grounded([PHRASE[0] + " >> " + PHRASE[1]], SLOTS, CALLS)
    assert why


def test_p1_slot_quoting_normalized():
    import ibl_usage_rag as rag
    slots = {"개수": "12", "위도": 36.64, "폴더": "~workspace/out"}
    assert rag._normalize_slot_quoting('[table:take]{n: ${개수}}', slots) == '[table:take]{n: $개수}'
    assert rag._normalize_slot_quoting('[self:file_find]{path: ${폴더}, lat: ${위도}}', slots) == '[self:file_find]{path: "${폴더}", lat: $위도}'
    assert rag._normalize_slot_quoting('[self:read]{path: "${폴더}/a.md"}', slots) == '[self:read]{path: "${폴더}/a.md"}'   # 따옴표 안은 그대로
    from ibl_param_vocab import code_syntax_error
    assert code_syntax_error(rag._normalize_slot_quoting('[sense:place]{query: "x", lat: ${위도}, limit: ${개수}}', slots)) is None


def test_p1_def_body_newlines_survive_one_line_join():
    import hippo_tree
    from ibl_param_vocab import code_syntax_error
    sent = '[def: 줄이기]{\n  $선별 = [table:ai]{instruction: "x", fields: ["a"]}\n  $return = $선별 >> [table:brief]{instruction: "$지시"}\n}'
    one = hippo_tree.join_sentences(['$본문 = [fn:줄이기]{지시: "${지시}"}', sent])
    assert "\n" not in one and "$선별 = [table:ai]" in one and "; $return = $선별" in one
    assert code_syntax_error(one) is None                      # 한 줄 표기가 그대로 파싱된다
    assert hippo_tree.split_sentences(one)[1].startswith("[def: 줄이기]")


def test_p1_private_path_rejected_and_slot_names():
    import ibl_usage_rag as rag
    import hippo_tree
    assert rag._phrase_private_reason(hippo_tree.join_sentences(PHRASE)) is None
    assert "홈 경로" in (rag._phrase_private_reason(READ) or "")
    assert hippo_tree.slot_names(hippo_tree.join_sentences(PHRASE)) == ["패턴", "루트", "파일", "앞", "뒤"]


# ---------------------------------------------------------------- P2 증류
def _arm(monkeypatch, reply, recall=None):
    import ibl_usage_db as mod
    import thread_context
    import hippo_tree
    monkeypatch.setattr(thread_context, "get_goal_eval_outcome", lambda: None)
    monkeypatch.setattr(thread_context, "clear_goal_eval_outcome", lambda: None)
    thread_context.set_phrase_recall(recall or [])
    monkeypatch.setattr(mod.IBLUsageDB, "hippo_disabled", classmethod(lambda cls: False))
    fake = types.ModuleType("consciousness_agent")
    fake.oneshot_ai_call = lambda **kw: json.dumps(reply, ensure_ascii=False)
    monkeypatch.setitem(sys.modules, "consciousness_agent", fake)
    monkeypatch.setattr(hippo_tree, "note_run", lambda *a, **k: {"success": True, "sentences": 0})
    monkeypatch.setattr(hippo_tree, "map_text", lambda *a, **k: "- 개발/프론트 (3)")
    saved = []
    monkeypatch.setattr(mod.IBLUsageDB, "_instance", None)
    monkeypatch.setattr(mod.IBLUsageDB, "__init__", lambda self, *a, **k: None)
    monkeypatch.setattr(mod.IBLUsageDB, "add_example", lambda self, **kw: saved.append(kw) or len(saved))
    monkeypatch.setattr(mod.IBLUsageDB, "_index_single", lambda self, *a, **k: None)
    import ibl_usage_rag as rag
    monkeypatch.setattr(rag, "_validate_ibl_actions", lambda code: True)
    import ibl_param_vocab
    monkeypatch.setattr(ibl_param_vocab, "check_code_params", lambda code: [])
    # 학습 파일은 건드리지 않는다
    import pathlib
    real = pathlib.Path.write_text
    monkeypatch.setattr(pathlib.Path, "write_text", lambda self, *a, **k: None if self.name == "ibl_distilled.json" else real(self, *a, **k))
    return saved


TOOL_CALLS = [{"tool_name": "execute_ibl", "input": {"code": c}, "success": True} for c in CALLS]


def test_p2_phrase_saved_independently_of_word(monkeypatch):
    import ibl_usage_rag as rag
    saved = _arm(monkeypatch, {"intent": "프론트 컴포넌트를 찾아 읽고 고친다", "code": "", "topic": "개발/프론트",
                               "phrase": PHRASE, "slots": SLOTS})
    assert rag.distill_experience("파일 필드 추가해줘", TOOL_CALLS, top_score=0.3) is True
    assert len(saved) == 1
    ph = saved[0]
    assert ph["category"] == "phrase" and ph["topic"] == "개발/프론트" and "phrase" in ph["tags"]
    assert ph["ibl_code"] == "; ".join(PHRASE)            # 슬롯은 그대로, 값은 저장 안 됨
    assert "/Users/" not in ph["ibl_code"]


def test_p2_word_and_phrase_both_saved(monkeypatch):
    import ibl_usage_rag as rag
    saved = _arm(monkeypatch, {"intent": "검색해 상위 5건", "code": PIPE, "topic": "개발/프론트",
                               "phrase": PHRASE, "slots": SLOTS})
    assert rag.distill_experience("AI 팁 5개", TOOL_CALLS, top_score=0.3) is True
    cats = sorted(s["category"] for s in saved)
    assert cats == ["phrase", "pipeline"]


def test_p2_ungrounded_or_single_phrase_not_saved(monkeypatch):
    import ibl_usage_rag as rag
    saved = _arm(monkeypatch, {"intent": "x", "code": "", "topic": "개발/프론트",
                               "phrase": [PHRASE[2], PHRASE[0]], "slots": SLOTS})
    assert rag.distill_experience("x", TOOL_CALLS, top_score=0.3) is False and saved == []
    saved = _arm(monkeypatch, {"intent": "x", "code": "", "topic": "개발/프론트", "phrase": [PHRASE[0]], "slots": SLOTS})
    assert rag.distill_experience("x", TOOL_CALLS, top_score=0.3) is False and saved == []
    # 슬롯으로 비우지 않은 홈 경로는 개인 명사 관문에서 거절
    saved = _arm(monkeypatch, {"intent": "x", "code": "", "topic": "개발/프론트", "phrase": [GREP, READ], "slots": {}})
    assert rag.distill_experience("x", TOOL_CALLS, top_score=0.3) is False and saved == []


def test_p2_prompt_asks_second_question_without_placeholder_heads():
    import ibl_usage_rag as rag
    p = rag._build_distill_prompt("u", "  1. [a:b]", "", "")
    assert "되풀이될 모양" in p and '"phrase"' in p and '"slots"' in p
    assert "[node:" not in p


# ---------------------------------------------------------------- P3 회상 사용·귀속
def test_p3_phrase_used_half_rule():
    import ibl_usage_rag as rag
    code = "; ".join(PHRASE)
    assert rag._phrase_used(code, CALLS) is True
    assert rag._phrase_used(code, [GREP, PIPE]) is False          # 3문장 중 1 → 미달
    assert rag._phrase_used(code, [GREP, READ]) is True           # 2/3 → 사용
    assert rag._phrase_used(code, [EDIT, GREP, READ]) is True     # 순서 보존 부분열(grep, read)


def test_p3_known_phrase_used_skips_new_phrase(monkeypatch):
    import ibl_usage_rag as rag
    saved = _arm(monkeypatch, {"intent": "x", "code": "", "topic": "개발/프론트", "phrase": PHRASE, "slots": SLOTS},
                 recall=["; ".join(PHRASE)])
    assert rag.distill_experience("x", TOOL_CALLS, top_score=0.3) is False and saved == []


def test_p3_recall_outcome_attributes_to_used_phrase(monkeypatch):
    import ibl_usage_rag as rag
    import ibl_usage_db as mod
    import thread_context
    hits = []
    monkeypatch.setattr(mod.IBLUsageDB, "_instance", None)
    monkeypatch.setattr(mod.IBLUsageDB, "__init__", lambda self, *a, **k: None)
    monkeypatch.setattr(mod.IBLUsageDB, "update_success_by_code", lambda self, code, ok, **kw: hits.append((code, ok)) or True)
    used = "; ".join(PHRASE)
    unused = '[sense:realty]{region: "${지역}"}; [self:write]{path: "${경로}", content: "x"}'
    thread_context.set_phrase_recall([used, unused])
    rag.record_recall_outcome("", 0.0, TOOL_CALLS)          # 낱말 top-1 없음 — 관용구 귀속은 그래도 돈다
    assert hits == [(used, True)]
    assert thread_context.get_phrase_recall() == []         # 꺼내면 비운다


# ---------------------------------------------------------------- P4 가지 문서
def _mk_db(path):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE ibl_examples (
            id INTEGER PRIMARY KEY AUTOINCREMENT, intent TEXT NOT NULL, ibl_code TEXT NOT NULL,
            nodes TEXT DEFAULT '', category TEXT DEFAULT 'single', difficulty INTEGER DEFAULT 1,
            source TEXT DEFAULT 'synthetic', success_count INTEGER DEFAULT 0, fail_count INTEGER DEFAULT 0,
            avg_ms REAL DEFAULT -1.0, avg_tokens REAL DEFAULT -1.0, tags TEXT DEFAULT '',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, topic TEXT DEFAULT '');
    """)
    conn.commit(); conn.close()


def _add(db, intent, code, topic, category="single", ok=0, alias=""):
    now = datetime.now().isoformat()
    conn = sqlite3.connect(db)
    try:
        conn.execute("SELECT alias FROM ibl_examples LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE ibl_examples ADD COLUMN alias TEXT DEFAULT ''")
    cur = conn.execute("INSERT INTO ibl_examples (intent, ibl_code, category, success_count, created_at, updated_at, topic, alias) VALUES (?,?,?,?,?,?,?,?)",
                       (intent, code, category, ok, now, now, topic, alias))
    conn.commit(); conn.close()
    return cur.lastrowid


@pytest.fixture
def env(tmp_path, monkeypatch):
    import hippo_tree as HT
    import ibl_usage_db as mod
    db = str(tmp_path / "usage.db"); _mk_db(db)
    monkeypatch.setattr(HT, "DOC_DIR", str(tmp_path / "tree"))
    monkeypatch.setattr(HT, "GUIDE_DB_PATH", str(tmp_path / "guide_db.json"))
    monkeypatch.setattr(HT, "_default_db_path", lambda: db)
    monkeypatch.setattr(mod, "_CODE_VALIDATOR", lambda code: None)
    return HT, db


def test_p4_phrase_section_roundtrip_and_map(env):
    HT, db = env
    _add(db, "검색해 상위 5건", PIPE, "개발/프론트", "pipeline")
    pid = _add(db, "찾아 읽고 고친다", "; ".join(PHRASE), "개발/프론트", "phrase", ok=2, alias="찾아고치기")
    path = HT.refresh_topic("개발/프론트", db)
    text = open(path, encoding="utf-8").read()
    assert "## 용례" in text and "## 관용구" in text
    assert text.index("## 용례") < text.index("## 관용구") < text.index("## 갱신 기록")
    assert f"### 찾아고치기 — 찾아 읽고 고친다 · 문장 3 · 슬롯 패턴, 루트, 파일, 앞, 뒤 ‹#{pid} · ✓2/✗0" in text
    assert '호출: `[fn:찾아고치기]{패턴: "…", 루트: "…", 파일: "…", 앞: "…", 뒤: "…"}`' in text   # 관용구 = 이름 붙은 함수
    assert "1. `" + PHRASE[0] + "`" in text
    # 용례 절엔 관용구가 섞이지 않는다
    sec = text[text.index("## 용례"):text.index("## 관용구")]
    assert "${패턴}" not in sec
    known, fresh = HT.parse_phrases(text)
    assert known == [{"intent": "찾아 읽고 고친다", "ibl_code": "; ".join(PHRASE), "id": pid, "alias": "찾아고치기"}] and fresh == []
    # 사람이 머리의 이름을 바꾸면 색인이 따라온다
    with open(path, "w", encoding="utf-8") as f:
        f.write(text.replace("### 찾아고치기 — ", "### 찾아서고치기 — "))
    os.utime(path, (os.path.getmtime(path) + 5, os.path.getmtime(path) + 5))
    assert HT.sync_topic("개발/프론트", db)["updated"] == 1
    assert HT.rows_of("개발/프론트", db, kind="phrase")[0]["alias"] == "찾아서고치기"
    assert "개발/프론트 (1 · 관용구 1)" in HT.map_text(db)
    r = HT.recall("개발/프론트", db)
    assert r["count"] == 1 and r["phrase_count"] == 1 and r["phrases"][0]["id"] == pid


def test_p4_human_block_inserted_and_removed_block_deleted(env):
    HT, db = env
    pid = _add(db, "찾아 읽고 고친다", "; ".join(PHRASE), "개발/프론트", "phrase")
    path = HT.refresh_topic("개발/프론트", db)
    text = open(path, encoding="utf-8").read()
    # 사람이 새 블록을 적는다(#id 없음) + 기존 블록을 지운다
    head, sec, tail = HT._split_phrases(text)
    new_sec = (HT.PHRASES + "\n" + HT.PHRASES_NOTE + "\n"
               "### 지역을 조회해 저장한다 · 문장 2 · 슬롯 지역, 경로\n"
               "1. `[sense:realty]{region: \"${지역}\"}`\n"
               "2. `[self:write]{path: \"${경로}\", content: \"$items\"}`\n")
    os.utime(path, None)
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + new_sec + tail)
    os.utime(path, (os.path.getmtime(path) + 5, os.path.getmtime(path) + 5))
    out = HT.sync_topic("개발/프론트", db)
    assert out["inserted"] == 1 and out["deleted"] == 1, out
    rows = HT.rows_of("개발/프론트", db, kind="phrase")
    assert len(rows) == 1 and rows[0]["category"] == "phrase" and rows[0]["ibl_code"].startswith("[sense:realty]")
    assert HT.rows_of("개발/프론트", db, kind="word") == []
    # 한 문장짜리 블록은 관용구가 아니다 — 거절 사유
    text = open(path, encoding="utf-8").read()
    with open(path, "a", encoding="utf-8") as f:
        pass
    head, sec, tail = HT._split_phrases(text)
    sec += "### 한 문장 · 문장 1\n1. `[self:time]`\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + sec + tail)
    os.utime(path, (os.path.getmtime(path) + 10, os.path.getmtime(path) + 10))
    out = HT.sync_topic("개발/프론트", db)
    assert out.get("rejected") and "문장 수 1" in out["rejected"][0]


# ---------------------------------------------------------------- P5 회상 XML
class _Ex:
    def __init__(self, code, intent="i", score=0.9, category="single", topic=""):
        self.ibl_code, self.intent, self.score, self.category, self.topic = code, intent, score, category, topic
        self.success_rate, self.avg_ms, self.avg_tokens, self.nodes = -1.0, -1.0, -1.0, ""


def test_p5_references_carry_phrase_block_and_word_channel_excludes_phrase(monkeypatch):
    import ibl_usage_rag as rag
    import ibl_usage_db as mod
    import thread_context
    calls = []
    def fake_search(self, query, top_k=5, **kw):
        calls.append(kw)
        if kw.get("category") == "phrase":
            return [_Ex("; ".join(PHRASE), "찾아 읽고 고친다", 0.8, "phrase", "개발/프론트")]
        return [_Ex(PIPE, "검색", 0.7)]
    monkeypatch.setattr(mod.IBLUsageDB, "_instance", None)
    monkeypatch.setattr(mod.IBLUsageDB, "__init__", lambda self, *a, **k: None)
    monkeypatch.setattr(mod.IBLUsageDB, "search_hybrid", fake_search)
    monkeypatch.setattr(rag, "_own_only", lambda r: r)
    monkeypatch.setattr(rag, "_extract_implementations_from_refs", lambda x: "")
    r = rag.IBLUsageRAG(); r.clear_cache()
    monkeypatch.setattr(r, "_is_ibl_relevant", lambda q: True)
    xml, top_score, top_code = rag.build_execution_memory("컴포넌트 고쳐줘")
    assert top_code == PIPE and top_score == 0.7                      # 반사 top-1 은 낱말
    assert any(k.get("exclude_category") == "phrase" for k in calls)  # 낱말 채널은 관용구 제외
    assert 'kind="phrase"' in xml and 'sentences="3"' in xml and "[def: 이름]{\n  " + PHRASE[0] in xml   # 이름 없는 옛 관용구도 정의 블록으로
    assert 'slots="패턴, 루트, 파일, 앞, 뒤"' in xml
    assert thread_context.get_phrase_recall() == ["; ".join(PHRASE)]
    # 관용구 임계: MIN_SCORE 미만은 싣지 않는다(저신뢰 폴백 없음)
    calls.clear()
    def low(self, query, top_k=5, **kw):
        return [_Ex("; ".join(PHRASE), score=0.5, category="phrase")] if kw.get("category") == "phrase" else []
    monkeypatch.setattr(mod.IBLUsageDB, "search_hybrid", low)
    r.clear_cache()
    assert r.search_phrases("x") == []


# ---------------------------------------------------------------- P6 트레이너
def test_p6_trainer_pattern_and_bucket():
    import ibl_embedding_trainer as T
    assert T.normalize_code_to_pattern("; ".join(PHRASE)) == "[self:grep]; [self:read]; [self:edit]"
    assert T.normalize_code_to_pattern('[table:each]{do: "[a:b]{x: 1}"} >> [c:d]{n: ${n}}') == "[table:each] >> [c:d]"
    assert T.is_phrase_code("; ".join(PHRASE)) and not T.is_phrase_code('[a:b]{x: "1; 2"}')
    data = [{"ibl_code": "[a:b]{} >> [c:d]{}"}] * 3 + [{"ibl_code": "[a:b]{}; [c:d]{}"}] * 3
    kept = T.balance_by_action(data, max_per_action=2)
    assert len(kept) == 4       # 두 버킷 각 2건 — 낱말 집합이 같아도 관용구는 별도 버킷


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


# ---------------------------------------------------------------- P7 교재 상시 블록
def test_p7_always_on_idioms_block(tmp_path, monkeypatch):
    """최빈도 관용구 IDIOMS_TOP 건이 <ibl_idioms> 로 환경 프롬프트에 실린다 — 사용 횟수 내림차순, 허용 노드 밖 어휘는 제외, 5분 캐시."""
    import ibl_access as A
    import runtime_utils
    db = str(tmp_path / "usage.db"); _mk_db(db)
    conn = sqlite3.connect(db)
    now = datetime.now().isoformat()
    rows = [("자주", "; ".join(PHRASE), 5, 1), ("드물", '[sense:search]{query: "${q}"}; [table:take]{n: 3}', 0, 0),
            ("낱말", PIPE, 9, 0)]
    conn.execute("ALTER TABLE ibl_examples ADD COLUMN alias TEXT DEFAULT ''")
    for intent, code, sc, fc in rows:
        conn.execute("INSERT INTO ibl_examples (intent, ibl_code, category, success_count, fail_count, created_at, updated_at, topic, alias) VALUES (?,?,?,?,?,?,?,?,?)",
                     (intent, code, "phrase" if intent != "낱말" else "pipeline", sc, fc, now, now, "개발", "자주찾기" if intent == "자주" else ""))
    conn.commit(); conn.close()
    (tmp_path / "data").mkdir()
    os.replace(db, str(tmp_path / "data" / "ibl_usage.db"))
    monkeypatch.setattr(runtime_utils, "get_base_path", lambda: tmp_path)
    monkeypatch.setattr(A, "_idioms_cache", {"t": 0.0, "text": "", "key": None})
    block = A._idioms_block(None)
    assert block.startswith("<ibl_idioms") and block.endswith("</ibl_idioms>")
    assert block.index("- 자주찾기 — 자주 (개발) · 문장 3 사용 6회") < block.index("- (이름 없음) — 드물 (개발)")
    assert '  [fn:자주찾기]{패턴: "…", 루트: "…", 파일: "…", 앞: "…", 뒤: "…"}' in block          # 그대로 쓰는 호출 한 줄
    # 이름 먼저(2026-09-05): 정의 블록은 싣지 않는다 — 본문은 recall{expand:"이름"} 으로만
    assert "  [def: 자주찾기]{" not in block and PHRASE[0] not in block and "expand" in block
    assert PIPE not in block                                   # 낱말은 싣지 않는다
    monkeypatch.setattr(A, "_idioms_cache", {"t": 0.0, "text": "", "key": None})
    assert "드물" not in A._idioms_block({"self"})              # sense 가 허용 밖이면 그 관용구는 빠진다
