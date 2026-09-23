"""관용구 층(idiom tier) 회귀 — 낱말과 얼린 워크플로 사이의 가로대 (2026-09-04, docs/IBL_IDIOM_TIER_HANDOFF.md).

계약:
  P1  접지 = 순서 보존 부분열: 관용구의 각 문장은 슬롯을 이번 값으로 되돌렸을 때 실행 호출과 머리·인자 키가
      같아야 하고(문자열·수치는 비워 비교), 순서는 실행 순서의 부분열. 순서 어긋남·미실행 문장은 거절.
  P2  증류는 낱말(code)과 관용구(phrase)를 독립으로 저장한다 — 낱말이 스킵돼도 관용구는 산다. 관용구는
      category='phrase', 코드는 `; ` 로 이은 문장 열, 슬롯은 `${…}` 그대로(값은 저장하지 않는다).
  P3  회상된 관용구를 **이름으로 불러** 썼으면 새 관용구를 뽑지 않고, 귀속은 그 관용구에 간다. 부르지 않고
      베낀 턴은 사용이 아니다(2026-09-07) — 그 자리는 낡은 정의의 덮어쓰기로 간다.
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

pytestmark = pytest.mark.usefixtures('isolated_distill_training')

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
    # 가지 출생 관문(settle_topic, 2026-09-05)이 실 트리를 읽고 제안 원장을 쓰지 않게 — 임시 트리에 지도의 가지를 실존시킨다
    import tempfile
    import hippo_tree as _ht
    _tree = tempfile.mkdtemp(prefix="idiom_tree_")
    monkeypatch.setattr(_ht, "DOC_DIR", _tree)
    os.makedirs(os.path.join(_tree, "개발", "프론트"), exist_ok=True)
    open(os.path.join(_tree, "개발", "프론트", _ht.DOC_NAME), "w", encoding="utf-8").write("# 개발/프론트\n")
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
    import ibl_distill_value
    monkeypatch.setattr(ibl_distill_value, "known_examples", lambda db: [])
    saved = []
    monkeypatch.setattr(mod.IBLUsageDB, "_instance", None)
    monkeypatch.setattr(mod.IBLUsageDB, "__init__", lambda self, *a, **k: None)
    monkeypatch.setattr(mod.IBLUsageDB, "add_example", lambda self, **kw: saved.append(kw) or len(saved))
    monkeypatch.setattr(mod.IBLUsageDB, "_index_single", lambda self, *a, **k: None)
    # 이름 조회도 임시로(2026-09-07 덮어쓰기 길이 생기면서) — 스텁을 안 두면 증류가 실 원장의 이름을 읽고 덮는다
    monkeypatch.setattr(mod.IBLUsageDB, "find_phrase_by_alias", lambda self, name: None)
    monkeypatch.setattr(mod.IBLUsageDB, "alias_of_code", lambda self, code: "")
    import ibl_usage_rag as rag
    monkeypatch.setattr(rag, "_validate_ibl_actions", lambda code: True)
    import ibl_param_vocab
    monkeypatch.setattr(ibl_param_vocab, "check_code_params", lambda code: [])
    # 학습 저장은 isolated_distill_training 안에서 실제 atomic replace까지 검사한다.
    return saved


TOOL_CALLS = [{"tool_name": "execute_ibl", "input": {"code": c}, "success": True} for c in CALLS]


def test_p2_phrase_is_not_saved_automatically(monkeypatch, tmp_path):
    """★정책 반전(2026-09-07 사용자 판정): 자동 경로는 관용구를 **저장하지 않는다**.

    상시 프롬프트에 소개되는 관용구는 실질적으로 어휘이고, 어휘는 자동으로 늘어나서는 안 된다.
    옛 판은 여기서 phrase 한 건이 저장되는 것을 지켰다 — 사흘에 38건이 그렇게 태어나 34건이 실행 0."""
    import ibl_usage_rag as rag
    import hippo_tree
    monkeypatch.setattr(hippo_tree, "DOC_DIR", str(tmp_path / "tree"))
    os.makedirs(tmp_path / "tree" / "개발" / "프론트")
    (tmp_path / "tree" / "개발" / "프론트" / hippo_tree.DOC_NAME).write_text("# 개발/프론트\n", encoding="utf-8")
    saved = _arm(monkeypatch, {"intent": "프론트 컴포넌트를 찾아 읽고 고친다", "code": "", "topic": "개발/프론트",
                               "phrase": PHRASE, "slots": SLOTS})
    rag.distill_experience("파일 필드 추가해줘", TOOL_CALLS, top_score=0.3)
    assert [s for s in saved if s.get("category") == "phrase"] == []


def test_p2_word_saved_without_a_name(monkeypatch, isolated_distill_training):
    """용례(코퍼스)는 종전대로 쌓인다 — 멈춘 것은 **이름**이지 경험이 아니다."""
    import ibl_usage_rag as rag
    saved = _arm(monkeypatch, {"decision": "keep", "benefit": "검색 뒤 표본 선택", "applicability": "결과 행을 반환하는 검색",
                               "source_ids": [CALLS.index(PIPE) + 1], "intent": "검색해 상위 5건", "code": PIPE, "topic": "개발/프론트",
                               "phrase": PHRASE, "slots": SLOTS})
    assert rag.distill_experience("AI 팁 5개", TOOL_CALLS, top_score=0.3) is True
    assert sorted(s["category"] for s in saved) == ["pipeline"]
    assert all(not s.get("alias") for s in saved), "자동 경로가 아직 이름을 준다"
    assert json.loads(isolated_distill_training.read_text())[0]['ibl_code'] == PIPE
    assert not isolated_distill_training.with_suffix('.distill.tmp').exists()


def test_p2_gates_still_reject_on_the_manual_path(monkeypatch):
    """관문은 살아 있다 — 방아쇠만 사람에게 갔다. 수동 경로(_distill_phrase)를 직접 두드려 확인한다."""
    import ibl_usage_rag as rag
    for phrase, slots in (([PHRASE[2], PHRASE[0]], SLOTS),      # 순서 뒤집힘 = 실행에 없던 모양
                          ([PHRASE[0]], SLOTS),                  # 한 문장 = 낱말이지 관용구가 아니다
                          ([GREP, READ], {})):                   # 슬롯으로 안 비운 홈 경로 = 개인 명사
        saved = _arm(monkeypatch, {"intent": "x", "code": "", "topic": "개발/프론트",
                                   "phrase": phrase, "slots": slots})
        got = rag._distill_phrase("x", {"phrase": phrase, "slots": slots}, CALLS, "개발/프론트", TOOL_CALLS)
        assert got is False and saved == []


def test_p2_prompt_no_longer_asks_for_idioms():
    """증류를 멈췄으면 반성기에게 짓게 하는 요청도 없다 — 출력 토큰은 매 턴 비용이다."""
    import ibl_usage_rag as rag
    p = rag._build_distill_prompt("u", "  1. [a:b]", "", "")
    assert '"phrase"' not in p and '"slots"' not in p and "phrase_name" not in p
    assert "[node:" not in p              # 자리표 머리 금지 — 경량 모델이 베낀다(이 뜻은 살아 있다)


# ---------------------------------------------------------------- P3 회상 사용·귀속
def test_p3_phrase_used_half_rule():
    import ibl_usage_rag as rag
    code = "; ".join(PHRASE)
    assert rag._phrase_used(code, CALLS) is True
    assert rag._phrase_used(code, [GREP, PIPE]) is False          # 3문장 중 1 → 미달
    assert rag._phrase_used(code, [GREP, READ]) is True           # 2/3 → 사용
    assert rag._phrase_used(code, [EDIT, GREP, READ]) is True     # 순서 보존 부분열(grep, read)


def test_p3_known_phrase_called_by_name_skips_new_phrase(monkeypatch):
    """이름으로 **부른** 턴만 사용 — 근접 중복을 막는 원래 뜻은 그대로다."""
    import ibl_usage_rag as rag
    calls = TOOL_CALLS + [{"tool_name": "execute_ibl",
                           "input": {"code": '[fn:아는관용구]{패턴: "notebook"}'}, "success": True}]
    saved = _arm(monkeypatch, {"intent": "x", "code": "", "topic": "개발/프론트", "phrase": PHRASE, "slots": SLOTS},
                 recall=["; ".join(PHRASE)])
    assert rag.distill_experience("x", calls, top_score=0.3) is False and saved == []


def test_p3_retyped_but_not_called_is_not_use(monkeypatch):
    """`_phrase_used` 의 뜻은 살아 있다 — 부르지 않고 베낀 턴은 **사용이 아니다**(회상 귀속·우회 집계가 읽는다).

    옛 판은 이 계약을 '자동 증류를 스킵하느냐'로 확인했다. 자동 증류가 없어진 뒤(2026-09-07)에는
    판정기 자체를 두드린다 — 계약이 사라진 게 아니라 그것을 읽는 자리가 바뀌었다."""
    import ibl_usage_rag as rag
    code = "; ".join(PHRASE)
    assert rag._phrase_used(code, CALLS) is True                      # 본문이 실행됐다 = 사용
    assert rag._phrase_used(code, [f'[fn:찾아고치기]{{패턴: "p"}}']) is False   # 이름만 있고 본문이 안 돌면 아니다
    saved = _arm(monkeypatch, {"intent": "x", "code": "", "topic": "개발/프론트", "phrase": PHRASE, "slots": SLOTS},
                 recall=[code])
    rag.distill_experience("x", TOOL_CALLS, top_score=0.3)
    assert [s for s in saved if s.get("category") == "phrase"] == []   # 자동 경로는 어느 쪽이든 뽑지 않는다


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
    # 트리의 기본 DB를 바꾸면 _index의 시험 DB 판별도 바뀐다. 벡터 쪽까지 격리한다.
    monkeypatch.setattr(mod, "DB_PATH", db)
    monkeypatch.setattr(mod.IBLUsageDB, "_instance", None)
    monkeypatch.setattr(mod.IBLUsageDB, "_index_single", lambda *a, **k: None)
    # 검증자 계약은 (code, function_body) — 관용구 몸은 함수 몸으로 읽는다(언어 개정 2026-09-07).
    # 한 인자 스텁을 두면 _syntax_reason 의 fail-closed 가 **모든 코드를 거절**로 바꾼다(설계대로).
    import ibl_signature_slot as _slot        # 슬롯의 주인(2026-09-07 이동) — 원장은 재수출만 한다
    monkeypatch.setattr(_slot, "_CODE_VALIDATOR", lambda code, function_body=False: None)
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
    assert '호출: `[fn:찾아고치기]{패턴: "…", 루트: "…", 파일: "…", 앞: "…", 뒤: "…"} → Record`' in text   # 관용구 = 이름 붙은 함수
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
    # recall의 items는 용례와 호출 가능한 함수를 함께 싣는다. count는 통화 행수다.
    assert r["count"] == len(r["items"]) == 2 and r["example_count"] == 1
    assert r["phrase_count"] == 1 and r["phrases"][0]["id"] == pid


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
        self.id = 1
        self.ibl_code, self.intent, self.score, self.category, self.topic = code, intent, score, category, topic
        self.success_rate, self.avg_ms, self.avg_tokens, self.nodes = -1.0, -1.0, -1.0, ""
        self.alias, self.signature, self.returns = "", None, ""


def test_p5_references_carry_phrase_block_and_word_channel_excludes_phrase(monkeypatch):
    import ibl_usage_rag as rag
    import ibl_usage_db as mod
    import thread_context
    calls = []
    def fake_search(self, query, top_k=5, **kw):
        calls.append(kw)
        if kw.get("aliased_only"):
            ex = _Ex("; ".join(PHRASE), "찾아 읽고 고친다", 0.8, "phrase", "개발/프론트")
            ex.alias, ex.signature, ex.returns = "찾아읽고고치기", "패턴 루트 파일 앞 뒤", "effect"
            return [ex]
        return [_Ex(PIPE, "검색", 0.7)]
    monkeypatch.setattr(mod.IBLUsageDB, "_instance", None)
    monkeypatch.setattr(mod.IBLUsageDB, "__init__", lambda self, *a, **k: None)
    monkeypatch.setattr(mod.IBLUsageDB, "search_hybrid", fake_search)
    monkeypatch.setattr(mod.IBLUsageDB, "find_phrase_by_alias", lambda self, name, edition=1:
                        None if edition == 2 else {
                            "alias": name, "ibl_code": "; ".join(PHRASE),
                            "signature": "패턴 루트 파일 앞 뒤", "returns": "effect"})
    monkeypatch.setattr(rag, "_own_only", lambda r: r)
    monkeypatch.setattr(rag, "_extract_implementations_from_refs", lambda x: "")
    r = rag.IBLUsageRAG(); r.clear_cache()
    monkeypatch.setattr(r, "_is_ibl_relevant", lambda q: True)
    xml, top_score, top_code = rag.build_execution_memory("컴포넌트 고쳐줘")
    assert top_code == '' and top_score == 0.7  # 구형 원문은 반사 실행하지 않는다
    assert any(k.get("exclude_category") == "phrase" for k in calls)  # 낱말 채널은 관용구 제외
    assert 'kind="phrase"' in xml and 'sentences="3"' in xml
    assert 'slots="패턴, 루트, 파일, 앞, 뒤"' in xml and 'name="찾아읽고고치기"' in xml
    # 이름 먼저(2026-09-05 판정을 회상 채널에도, 2026-09-06): 본문은 안 싣는다 — 서명 한 줄만
    assert '[fn:찾아읽고고치기]{패턴: "…", 루트: "…", 파일: "…", 앞: "…", 뒤: "…"} → Record' in xml
    assert "[def: " not in xml and PHRASE[0] not in xml
    assert thread_context.get_phrase_recall() == ["; ".join(PHRASE)]
    # 문턱(2026-09-06): 본문을 안 싣게 됐으니 낱말의 저신뢰 바닥까지 연다 — 안 보이면 못 부른다
    calls.clear()
    def low(self, query, top_k=5, **kw):
        if not kw.get("aliased_only"):
            return []
        ex = _Ex("; ".join(PHRASE), score=0.5, category="phrase")
        ex.alias, ex.signature, ex.returns = "이름", "", ""
        return [ex]
    monkeypatch.setattr(mod.IBLUsageDB, "search_hybrid", low)
    r.clear_cache()
    assert len(r.search_phrases("x")) == 1        # 0.5 ≥ 저신뢰 바닥(0.45)
    def lower(self, query, top_k=5, **kw):
        ex = _Ex("; ".join(PHRASE), score=0.3, category="phrase")
        ex.alias = "이름"
        return [ex] if kw.get("aliased_only") else []
    monkeypatch.setattr(mod.IBLUsageDB, "search_hybrid", lower)
    r.clear_cache()
    assert r.search_phrases("x") == []            # 무관 노이즈는 여전히 뺀다


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
def test_p7_always_on_idioms_map(tmp_path, monkeypatch):
    """상시 블록은 **어휘 층**만 싣는다 — `always_on=1` (2026-09-07 사용자 판정).

    옛 판은 이름 붙은 것 전부를 사용 횟수 순으로 실었다. 그 결과가 사흘에 38건·34건 실행 0 이었다.
    이제 층이 둘이다: always_on=1 = 소개(어휘, 사람이 고른다) / 0 = 등록만(부를 수는 있으나 소개 안 함).
    그리고 한 항목은 뜻이 아니라 **언제/골격**을 말한다 — 이름만으로는 부를 조건을 알 수 없다."""
    import ibl_access as A
    import runtime_utils
    db = str(tmp_path / "usage.db"); _mk_db(db)
    conn = sqlite3.connect(db)
    now = datetime.now().isoformat()
    conn.execute("ALTER TABLE ibl_examples ADD COLUMN alias TEXT DEFAULT ''")
    conn.execute("ALTER TABLE ibl_examples ADD COLUMN signature TEXT")
    conn.execute("ALTER TABLE ibl_examples ADD COLUMN always_on INTEGER DEFAULT 0")
    rows = [("어디 있는지 모르는 것을 읽어야 할 때", "; ".join(PHRASE), 5, 1, "찾아고치기", "패턴 루트 파일 앞 뒤", 1),
            ("등록만 — 소개 안 함", '[sense:search]{query: "${q}"}; [table:take]{n: 3}', 9, 0, "등록만이름", "q", 0),
            ("낱말", PIPE, 9, 0, "", None, 0)]
    for intent, code, sc, fc, alias, sig, on in rows:
        conn.execute("INSERT INTO ibl_examples (intent, ibl_code, category, success_count, fail_count, created_at, "
                     "updated_at, topic, alias, signature, always_on) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (intent, code, "phrase" if alias else "pipeline", sc, fc, now, now, "개발", alias, sig, on))
    conn.commit(); conn.close()
    (tmp_path / "data").mkdir()
    os.replace(db, str(tmp_path / "data" / "ibl_usage.db"))
    monkeypatch.setattr(runtime_utils, "get_base_path", lambda: tmp_path)
    monkeypatch.setattr(A, "_idioms_cache", {"t": 0.0, "text": "", "key": None})
    # 소유 판정은 이 시험의 대상이 아니다 — 그리고 밀봉해야 한다. code_is_own 은 ibl_nodes.yaml 경로를 첫 사용 때 전역에
    # 굳히는데, 위에서 base path 를 tmp 로 바꿨으므로 **앞선 시험이 그 전역을 데워 놨느냐**에 따라 통과·실패가 갈렸다
    # (2026-09-18 실측: 전수 실행에서 간헐 실패 — 경로가 식은 채 오면 tmp 에는 어휘가 없어 전부 '남의 것'→ 빈 지도).
    import ibl_registry
    monkeypatch.setattr(ibl_registry, "code_is_own", lambda code: True)
    block = A.idioms_map(None)
    assert block.startswith("<ibl_idioms") and block.endswith("</ibl_idioms>")
    assert "[개발]" in block
    # 항목 = 호출 · 언제 · 골격 (뜻 한 줄이 아니라 **부를 조건**)
    assert '- [fn:찾아고치기]{패턴: "…", 루트: "…", 파일: "…", 앞: "…", 뒤: "…"}' in block
    assert "  언제: 어디 있는지 모르는 것을 읽어야 할 때" in block
    assert "  골격: self:grep → self:read → self:edit" in block
    assert "· 사용 6회" in block
    # 층 — 등록만 인 것도, 이름 없는 낱말도 싣지 않는다
    assert "등록만이름" not in block and PIPE not in block
    # 본문은 싣지 않는다 — recall{expand:"이름"} 으로만(베끼기 방지)
    assert "  [def: 찾아고치기]{" not in block and PHRASE[0] not in block and "expand" in block
    monkeypatch.setattr(A, "_idioms_cache", {"t": 0.0, "text": "", "key": None})
    assert "찾아고치기" not in A.idioms_map({"others"})        # 허용 노드 밖 어휘가 든 이름은 빠진다


# ── 2026-09-06 속편: 이름은 경제로 판정 · 이름의 뜻이 intent ─────────────────────────────────────

def test_p3_uncallable_by_saved_chars():
    from ibl_idiom import uncallable_reason, saved_chars, MIN_SAVED_CHARS
    # 얼어 있는 본문이 호출문보다 짧으면 부를 값이 없다
    tiny = '$x = $값; $return = $x'
    sig = ["값"]
    assert saved_chars(tiny, sig) < MIN_SAVED_CHARS
    assert uncallable_reason(sig, 2, tiny) is not None
    # 얼어 있는 본문이 길면(지시문·고정 인자) 부를 값이 있다
    fat = ('[sense:search]{source: "gnews", query: "$질의", limit: 10} >> [table:dedup]{by: "url"} >> '
           '[table:ai]{instruction: "사건 단위로 분류하고 한 줄 요지를 쓴다. 중복은 합치고 날짜를 붙인다", '
           'fields: ["label", "date", "title", "summary", "url"]}; [self:write]{path: "$경로", content: "$요지"}')
    assert uncallable_reason(["질의", "경로", "요지"], 2, fat) is None
    # code 없이 부르면 옛 판정만(하위 호환)
    assert uncallable_reason(sig, 2) is None


def test_p3_meaning_becomes_intent_on_the_manual_path(monkeypatch):
    """저장되는 intent 는 *이 사건의 요약*이 아니라 *부를 조건*이다 — 수동 경로에서도 그대로."""
    import ibl_usage_rag as rag
    saved = _arm(monkeypatch, {})
    got = rag._distill_phrase("USB 연결된 폰에서 계기 트리 혼종 문제를 진단하고 수리한다",
                              {"phrase": PHRASE, "slots": SLOTS, "phrase_name": "찾아읽고고치기",
                               "phrase_meaning": "패턴으로 파일을 찾아 매칭 자리 주변을 읽고 지정한 줄을 고친다"},
                              CALLS, "개발/프론트", TOOL_CALLS)
    assert got is True and saved
    assert saved[0]["intent"] == "패턴으로 파일을 찾아 매칭 자리 주변을 읽고 지정한 줄을 고친다"
    assert saved[0]["alias"] == "찾아읽고고치기"


def test_p3_registration_requires_the_when_line():
    """'언제'를 묻던 자리가 반성기 프롬프트에서 **등록 관문**으로 옮겨졌다(2026-09-07)."""
    import ibl_usage_rag as rag
    p = rag._build_distill_prompt("x", "1. [self:read]{path: \"a\"}", "", "")
    assert "phrase_meaning" not in p                    # 더는 모델에게 짓게 하지 않는다
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    import register_idiom
    info, why = register_idiom._gates("찾아고치기2", "", "; ".join(PHRASE))
    assert info is None and "--when" in why
