"""조합 비용이 모델의 눈에 보인다 (2026-09-05, 사용자 판정 "적합도가 보여야 육종이 된다").

계약:
  · scripts/ibl_composition_cost_metrics.py — 에피소드별 호출 경제(호출·1액션 호출·타이핑·되읽기·실패·
    첫 프로그램 성공·통화 부류 실패)를 world_pulse 궤적에서 센다. 정기 보고서(`보고서 써줘`)는 기본 제외.
  · hippo_tree.note_run — 주행 머리에 `· 호출 k · 실패 m · 타이핑 NK자` 꼬리, 되풀이 검토는 `놓침: ` 한 줄.
    parse_run_heads 가 새 머리와 옛 머리(꼬리 없음)를 다 읽고, render_names_first 의 주행 줄에 최근 비용이 실린다.
  · cognitive_trace.build_reflection_message — 궤적 앞에 `이번 주행: execute_ibl k회(액션 1개 호출 j회) · 실패 m ·
    타이핑 NK자` 한 줄(수치만, 질문 없음).
  · ibl_usage_rag — 증류 프롬프트의 되풀이 검토(retyped·mergeable) 규칙과 JSON 칸, note_run 으로의 전달.

★실 DB·실 트리 무접촉: 궤적은 tmp sqlite, 가지 문서는 hippo_tree.DOC_DIR 임시화(pitfall_test_writes_to_real_store).
실행: .venv/bin/python -m pytest -q backend/test_composition_metrics_2026_09_05.py
"""
import importlib.util
import json
import os
import sqlite3
import sys
import types
from datetime import datetime, timedelta

import pytest

BACKEND = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND)
import boot_paths  # noqa: E402,F401

SCRIPT = os.path.join(os.path.dirname(BACKEND), "scripts", "ibl_composition_cost_metrics.py")


def _load_script():
    spec = importlib.util.spec_from_file_location("ibl_composition_cost_metrics", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- 궤적 픽스처 (tmp sqlite)
def _mk_pulse(path):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE episode_log (id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL, ended_at TEXT,
            agent TEXT, user_message TEXT, log TEXT, total_ms INTEGER, task_id TEXT, source TEXT, owner TEXT,
            run_id TEXT, parent_run_id TEXT);
        CREATE TABLE trajectory_event (run_id TEXT NOT NULL, event_seq INTEGER NOT NULL, episode_id INTEGER,
            task_id TEXT, parent_run_id TEXT, ts TEXT NOT NULL, kind TEXT NOT NULL, data TEXT, source TEXT,
            PRIMARY KEY (run_id, event_seq));
    """)
    conn.commit()
    return conn


def _episode(conn, eid, message, log="", when=None, source="usage", total_ms=1000):
    when = when or datetime.now().isoformat()
    conn.execute("INSERT INTO episode_log (id, started_at, user_message, log, total_ms, source, run_id) VALUES (?,?,?,?,?,?,?)",
                 (eid, when, message, log, total_ms, source, f"run{eid}"))
    conn.commit()


def _calls(conn, eid, specs):
    """specs = [(actions, code_chars, result_chars, success), ...] 를 started/finished 짝으로 적는다."""
    seq = 0
    for actions, code_chars, result_chars, ok in specs:
        seq += 1
        conn.execute("INSERT INTO trajectory_event (run_id, event_seq, episode_id, ts, kind, data) VALUES (?,?,?,?,?,?)",
                     (f"run{eid}", seq, eid, "t", "ibl.started",
                      json.dumps({"action_count": len(actions), "actions": actions, "code_chars": code_chars,
                                  "pipes": max(0, len(actions) - 1), "nested": False})))
        if ok is None:
            continue                                     # 짝 없는 started(미완)
        seq += 1
        conn.execute("INSERT INTO trajectory_event (run_id, event_seq, episode_id, ts, kind, data) VALUES (?,?,?,?,?,?)",
                     (f"run{eid}", seq, eid, "t", "ibl.finished",
                      json.dumps({"elapsed_ms": 5, "result_chars": result_chars, "success": ok})))
    conn.commit()


@pytest.fixture
def pulse(tmp_path):
    db = str(tmp_path / "pulse.db")
    conn = _mk_pulse(db)
    yield conn
    conn.close()


def test_first_program_success_and_call_economy(pulse):
    M = _load_script()
    # 첫 호출이 3액션 프로그램이고 성공 → 첫 프로그램 성공. 그 뒤 1액션 호출 둘(하나 실패), 미완 하나.
    _episode(pulse, 1, "새 요청 하나")
    _calls(pulse, 1, [(["self:read", "table:filter", "self:write"], 300, 2000, True),
                      (["self:memory"], 50, 400, True),
                      (["self:time"], 20, 100, False),
                      (["self:read"], 30, 0, None)])
    # 첫 호출이 1액션 → 첫 프로그램 실패(성공했어도)
    _episode(pulse, 2, "새 요청 둘")
    _calls(pulse, 2, [(["self:memory"], 40, 900, True), (["sense:search", "table:take"], 120, 3000, True)])
    rows = {r["id"]: r for r in M.measure(pulse, days=14)}
    r1, r2 = rows[1], rows[2]
    assert r1["calls"] == 4 and r1["single_action_calls"] == 3 and r1["failed_calls"] == 1
    assert r1["typed_chars"] == 400 and r1["reread_chars"] == 2500
    assert r1["first_program_success"] is True and r1["first_call_actions"] == ["self:read", "table:filter", "self:write"]
    assert r2["first_program_success"] is False and r2["calls"] == 2
    agg = M.aggregate(list(rows.values()))
    assert agg["episodes_with_calls"] == 2 and agg["first_program_success"] == {"ok": 1, "of": 2, "rate": 0.5}
    assert agg["sum"]["calls"] == 6 and agg["sum"]["single_action_calls"] == 4
    # 표·요약에 사용자 문장은 실리지 않는다(개인 명사 금지) — id·수치·머리만
    table = M.render_table(list(rows.values()))
    assert "새 요청" not in table and "self:read, table:filter, self:write" in table


def test_reports_excluded_by_default_and_included_on_request(pulse):
    M = _load_script()
    _episode(pulse, 1, "부동산 발굴 보고서 써줘")
    _calls(pulse, 1, [(["self:memory"], 40, 900, True)])
    _episode(pulse, 2, "정기 보고서가 아닌 질문")
    _calls(pulse, 2, [(["self:memory"], 40, 900, True)])
    _episode(pulse, 3, "오래된 요청", when=(datetime.now() - timedelta(days=30)).isoformat())
    _calls(pulse, 3, [(["self:memory"], 40, 900, True)])
    _episode(pulse, 4, "다른 출처", source="test")
    _calls(pulse, 4, [(["self:memory"], 40, 900, True)])
    assert [r["id"] for r in M.measure(pulse, days=14)] == [2]
    assert sorted(r["id"] for r in M.measure(pulse, days=14, exclude_reports=False)) == [1, 2]
    assert sorted(r["id"] for r in M.measure(pulse, days=14, source=None)) == [2, 4]
    assert sorted(r["id"] for r in M.measure(pulse, days=60)) == [2, 3]
    assert M.is_report_request("유튜브 AI 팁 보고서 써줘 ") and not M.is_report_request("보고서 써줘야 하나 고민")


def test_currency_failure_class_is_counted_from_log(pulse):
    M = _load_script()
    log = ("[IBL] 오류: >> 양쪽은 통화 종류가 같아야 합니다\n"
           "[IBL] 오류: $검색 은 아직 값을 기록하지 않았습니다\n"
           "[IBL] 오류: path 에는 string 이 와야 합니다\n"
           "[IBL] 오류: 결과가 통화(items/table)로 파싱되지 않았습니다\n"
           "[IBL] 오류: 파일이 없습니다\n")
    _episode(pulse, 1, "새 요청", log=log)
    _calls(pulse, 1, [(["self:read", "table:filter"], 100, 500, False)])
    _episode(pulse, 2, "깨끗한 주행", log="[IBL] 완료")
    _calls(pulse, 2, [(["self:read", "table:filter"], 100, 500, True)])
    rows = {r["id"]: r for r in M.measure(pulse, days=14)}
    assert rows[1]["currency_failures"] == 4 and rows[2]["currency_failures"] == 0
    assert M.aggregate(list(rows.values()))["sum"]["currency_failures"] == 4
    assert M.currency_failures(None) == 0


# ---------------------------------------------------------------- 주행 머리 비용 (임시 트리)
def _mk_usage_db(path):
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


@pytest.fixture
def tree(tmp_path, monkeypatch):
    import hippo_tree as HT
    db = str(tmp_path / "usage.db"); _mk_usage_db(db)
    monkeypatch.setattr(HT, "DOC_DIR", str(tmp_path / "tree"))          # ★실 트리 무접촉
    monkeypatch.setattr(HT, "GUIDE_DB_PATH", str(tmp_path / "guide_db.json"))
    monkeypatch.setattr(HT, "_default_db_path", lambda: db)
    return HT, db


S1 = '[self:memory]{op: "recall", node: "보고서/X"}'
S2 = '[sense:search]{query: "${주제}"} >> [table:take]{n: 5}'


def test_note_run_head_carries_cost_and_missed_line(tree):
    HT, db = tree
    r = HT.note_run("보고서/X", "보고서 · 27호", [S1, S2], ok=True, when="2026-09-05", db_path=db,
                    calls=23, failed=7, typed_chars=18432,
                    missed={"retyped": ["뉴스모아쓰기", "outputs/x/경로.json", "뉴스모아쓰기"],
                            "mergeable": ["3-7", "12", "이상한 값"]})
    assert r["success"]
    assert HT.doc_path("보고서/X").startswith(HT.DOC_DIR)                  # 임시 트리에 썼다
    text = open(HT.doc_path("보고서/X"), encoding="utf-8").read()
    assert "### 2026-09-05 · 보고서 27호 · 문장 2 · ✓ · 호출 23 · 실패 7 · 타이핑 18K자" in text
    assert "놓침: 이름 재타이핑 뉴스모아쓰기 · 묶을 수 있던 문장 3-7, 12" in text
    assert "경로.json" not in text and "이상한 값" not in text              # 개인 명사·잡값은 거른다
    # 옛 머리(비용 없음)와 새 머리를 파서가 함께 읽는다
    HT.note_run("보고서/X", "옛 주행", [S1, S2], ok=False, when="2026-08-28", db_path=db)
    HT.note_run("보고서/X", "짧은 주행", [S1, S2], ok=True, when="2026-08-30", db_path=db, calls=9, failed=0, typed_chars=850)
    sec = HT._split_runs(open(HT.doc_path("보고서/X"), encoding="utf-8").read())[1]
    heads = HT.parse_run_heads(sec)
    assert [h["calls"] for h in heads] == [9, None, 23] and heads[0]["typed_chars"] == 850 and heads[2]["typed_chars"] == 18000
    assert heads[1]["ok"] is False and heads[1]["intent"] == "옛 주행"
    assert HT.runs_of(HT.doc_path("보고서/X")) == 3                         # 놓침 줄은 주행으로 세지 않는다
    # 이름 먼저 회상의 주행 줄 — 건수 + 최근 비용 + 최소 호출, 본문은 없다
    out = HT.render_names_first("보고서/X", [], [], open(HT.doc_path("보고서/X"), encoding="utf-8").read())
    assert "## 주행 3건 — 최근: 호출 9·실패 0·타이핑 850자 / 최소 호출: 9(2026-08-30) — expand:\"주행\"" in out
    assert S2 not in out
    # 비용 머리가 하나도 없으면 옛 줄 그대로
    HT.note_run("보고서/Y", "무비용", [S1, S2], when="2026-09-01", db_path=db)
    out_y = HT.render_names_first("보고서/Y", [], [], open(HT.doc_path("보고서/Y"), encoding="utf-8").read())
    assert "## 주행 1건 — expand:\"주행\"" in out_y


def test_note_run_without_cost_keeps_old_head(tree):
    HT, db = tree
    HT.note_run("보고서/Z", "부동산 보고서 27호", [S1, S2], when="2026-09-04", db_path=db)
    text = open(HT.doc_path("보고서/Z"), encoding="utf-8").read()
    assert "### 2026-09-04 · 부동산 보고서 27호 · 문장 2 · ✓\n1. `" in text and "\n놓침:" not in text


# ---------------------------------------------------------------- 자기반성 비용 줄
def test_reflection_message_leads_with_run_cost():
    from cognitive_trace import build_reflection_message, run_cost_line, ibl_call_cost
    calls = [{"name": "execute_ibl", "input": {"code": S1}, "result": "x", "is_error": False},
             {"name": "execute_ibl", "input": {"code": S2}, "result": "x", "is_error": True},
             {"name": "execute_ibl", "input": {"code": "[self:time]"}, "result": "x", "is_error": False},
             {"name": "Bash", "input": {"command": "ls"}, "result": "x", "is_error": False}]
    c = ibl_call_cost(calls)
    assert c == {"calls": 3, "single": 2, "failed": 1, "typed_chars": len(S1) + len(S2) + len("[self:time]")}
    line = run_cost_line(calls)
    assert line == f"이번 주행: execute_ibl 3회(액션 1개 호출 2회) · 실패 1 · 타이핑 {c['typed_chars']}자"
    assert "?" not in line                                                  # 수치만 — 질문 없음(출력 계약)
    msg = build_reflection_message("초안", calls)
    assert msg.index(line) < msg.index("## 지금까지의 궤적") < msg.index("## 네가 내놓으려던 응답")
    # 증류용 모양({tool_name, success})도 같은 계수
    assert ibl_call_cost([{"tool_name": "execute_ibl", "input": {"code": S2}, "success": False}]) == \
        {"calls": 1, "single": 0, "failed": 1, "typed_chars": len(S2)}
    assert run_cost_line([{"name": "Bash", "input": {}}]) == ""
    assert "이번 주행:" not in build_reflection_message("초안", [{"name": "Bash", "input": {}, "result": ""}])


# ---------------------------------------------------------------- 증류의 세 번째 질문
def test_distill_prompt_asks_for_retyped_and_mergeable():
    import ibl_usage_rag as rag
    p = rag._build_distill_prompt("u", "  1. " + S1, "", "")
    assert "되풀이 검토" in p and '"retyped"' in p and '"mergeable"' in p
    assert "[node:" not in p                                                # G5 자리표 금지 유지


def test_distill_passes_cost_and_missed_to_note_run(monkeypatch, tmp_path):
    import ibl_usage_db as mod
    import thread_context
    import hippo_tree
    import ibl_usage_rag as rag
    # 가지 출생 관문(settle_topic, 2026-09-05): '보고서/X' 가 임시 트리에 실존해야 그 가지로 기록된다(실 트리 무접촉)
    monkeypatch.setattr(hippo_tree, "DOC_DIR", str(tmp_path / "tree"))
    os.makedirs(tmp_path / "tree" / "보고서" / "X")
    (tmp_path / "tree" / "보고서" / "X" / hippo_tree.DOC_NAME).write_text("# 보고서/X\n", encoding="utf-8")
    monkeypatch.setattr(thread_context, "get_goal_eval_outcome", lambda: None)
    monkeypatch.setattr(thread_context, "clear_goal_eval_outcome", lambda: None)
    monkeypatch.setattr(mod.IBLUsageDB, "hippo_disabled", classmethod(lambda cls: False))
    fake = types.ModuleType("consciousness_agent")
    reply = {"intent": "보고서 작성", "code": "", "topic": "보고서/X", "phrase": [],
             "retyped": ["뉴스모아쓰기"], "mergeable": ["1-2"]}
    fake.oneshot_ai_call = lambda **kw: json.dumps(reply, ensure_ascii=False)
    monkeypatch.setitem(sys.modules, "consciousness_agent", fake)
    monkeypatch.setattr(hippo_tree, "map_text", lambda *a, **k: "- 보고서/X (3)")
    got = {}
    monkeypatch.setattr(hippo_tree, "note_run",
                        lambda topic, intent, sentences, ok=True, **kw: got.update(kw, topic=topic) or {"success": True, "sentences": len(sentences)})
    calls = [{"tool_name": "execute_ibl", "input": {"code": S1}, "success": True},
             {"tool_name": "execute_ibl", "input": {"code": S2}, "success": True},
             {"tool_name": "execute_ibl", "input": {"code": "[self:time]"}, "success": False}]
    rag.distill_experience("보고서 써줘라", calls, top_score=0.1)
    assert got["topic"] == "보고서/X" and got["calls"] == 3 and got["failed"] == 1
    assert got["typed_chars"] == len(S1) + len(S2) + len("[self:time]")
    assert got["missed"] == {"retyped": ["뉴스모아쓰기"], "mergeable": ["1-2"]}


# ---------------------------------------------------------------- 이음매 지표(셸↔IBL, 모델 경유)
def test_seam_metrics_counts_only_model_carried_data():
    M = _load_script()
    log = (
        '[ClaudeCode/시스템 AI] tool_use Bash {"command": "grep -rn mediaModel backend"}\n'
        '[ClaudeCode/시스템 AI] tool_result backend/static/app_render_core.js:236: function mediaModel(\n'
        '[ClaudeCode/시스템 AI] tool_use mcp__indiebizos__execute_ibl {"code": "[self:read]{path: \\"backend/static/app_render_core.js\\", start_line: 236}"}\n'
        '[ClaudeCode/시스템 AI] tool_result {"result": "..."}\n'
        '[ClaudeCode/시스템 AI] tool_use Bash {"command": "python3 - <<EOF\\nprint(ids)\\nEOF"}\n'
        '[ClaudeCode/시스템 AI] tool_result [1650, 1651, 1654]\n'
        '[ClaudeCode/시스템 AI] tool_use mcp__indiebizos__execute_ibl {"code": "[table:each]{items: [{id: 1650}, {id: 1651}, {id: 1654}], do: \\"[self:x]{}\\"}"}\n'
        '[ClaudeCode/시스템 AI] tool_result {"success": true}\n'
        '[ClaudeCode/시스템 AI] tool_use mcp__indiebizos__execute_ibl {"code": "[self:time]{}"}\n'
        '[ClaudeCode/시스템 AI] tool_result {"time": "2026-09-05"}\n'
    )
    m = M.seam_metrics_from_log(log)
    # 인접 쌍: Bash→IBL(grep→read: 경로는 grep 입력에도 있었지만 **줄 번호 236** 이 되찍힘 — 이것도 경유), IBL→Bash, Bash→IBL(id 되찍기), IBL→IBL(아님)
    assert m["seams"] == 3
    assert m["carried"] == 2 and m["carried_values"] == 4            # 236 + 1650·1651·1654 가 모델을 거쳐 건너감
    assert M.seam_metrics_from_log("")["seams"] == 0


def test_seam_tracker_at_provider_boundary_sees_full_results():
    """프로바이더 자리의 트래커 — 결과 전문으로 되찍기를 잡는다(로그 절단과 무관). 다른 도구가 끼면 이음매가 아니다."""
    from seam_metrics import SeamTracker, crossed_values
    t = SeamTracker()
    assert t.on_tool_use("Bash", {"command": "python3 -c 'print(ids)'"}) is None
    t.on_tool_result("[1650, 1651, 1654]" + " x" * 500)                      # 300자 넘는 결과 — 로그라면 잘렸을 자리
    obs = t.on_tool_use("mcp__indiebizos__execute_ibl", {"code": "[table:each]{items: [{id: 1650}, {id: 1651}, {id: 1654}]}"})
    assert obs and obs["from"] == "shell" and obs["to"] == "ibl" and obs["carried"] and obs["values"] == 3
    t.on_tool_result('{"success": true, "items": [{"path": "/tmp/out_2026.json"}]}')
    obs2 = t.on_tool_use("Bash", {"command": "cat /tmp/out_2026.json"})
    assert obs2 and obs2["from"] == "ibl" and obs2["carried"] and obs2["sample"] == ["tmp/out_2026.json"]   # 값은 앞뒤 /·. 을 벗겨 정규화
    assert t.on_tool_use("Read", {"file_path": "/tmp/out_2026.json"}) is None   # 다른 도구 — 이음매 아님
    assert t.on_tool_use("mcp__indiebizos__execute_ibl", {"code": "[self:time]{}"}) is None
    assert t.summary() == {"seams": 2, "carried": 2, "carried_values": 4}
    assert crossed_values("총 8행", "grep 8행", "[self:read]{limit: 8}") == []     # 짧은 수치·앞 입력에 있던 값은 안 센다


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
