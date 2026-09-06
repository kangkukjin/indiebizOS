"""`[fn:]` 0건 재진단 + 계기 수리 (2026-09-07, ep2950~2952 감사).

관측: 09-06 수리(d885412b, 서명·보여주기) 뒤 재기동된 몸에서 IBL 문장 2,501건에 `[fn:]` 호출 0.
ep2952 로그: 의식이 `[fn:유튜브팁보고서작성]` 을 지정 → 실행자가 expand 로 정의를 열고 → 본문을 베껴
*변형* 을 쳤다(35호출·실패 8). 그 관용구는 실행 0 이고 본문의 날짜 필터는 첫 호출부터 죽을 몸이었다.

뿌리 둘과 관문:
  ① 정의를 열면 베낀다 — expand 카드는 호출 한 줄 먼저(phrase_expand_card), 실행 관문은 변형도 인식(variant_of)
  ② 돈 적 없는 정의가 이름을 얻는다 — 슬롯 값 접지(slot_values_ungrounded), 표시는 '실행 0' 을 말한다
계기(에피소드통계): 궤적이 1차 소스(로그 줄 쪼개짐과 무관), 문법오류는 턴 변수 문맥 안에서 판정.
로거: _extract_hint 는 한 줄(개행이 화살표 줄을 쪼개던 뿌리).
"""
import importlib.util
import io
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: E402,F401

ROOT = Path(__file__).resolve().parents[1]


# ── 로거 ─────────────────────────────────────────────────────────────────────
def test_로그_힌트는_한_줄이다():
    from system_tools import _extract_hint
    code = '$a = [self:time]{}\n$b = $a >> [table:take]{n: 1}\n  [table:count]{}'
    hint = _extract_hint({"code": code})
    assert "\n" not in hint and "$b = $a" in hint, hint          # 개행 제거 *뒤에* 자른다 — 둘째 문장이 보인다


# ── 에피소드통계: 궤적 1차 소스 + 턴 변수 문맥 ───────────────────────────────
def _load_script():
    path = ROOT / "data" / "scripts" / "에피소드통계.py"
    spec = importlib.util.spec_from_file_location("ep_stats_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pulse_db(tmp_path, codes_ok, log):
    """episode 1 하나: codes_ok = [(code, success)] 를 궤적+코퍼스로, log 는 로그 방언."""
    import hashlib
    db = tmp_path / "world_pulse.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE episode_log (id INTEGER PRIMARY KEY, started_at TEXT, ended_at TEXT, agent TEXT,
                    user_message TEXT, log TEXT, total_ms INTEGER, task_id TEXT, source TEXT, owner TEXT,
                    run_id TEXT, parent_run_id TEXT)""")
    conn.execute("""CREATE TABLE episode_summary (id INTEGER PRIMARY KEY, episode_id INTEGER, started_at TEXT,
                    agent TEXT, user_message TEXT, hippocampus_score REAL, unconscious_decision TEXT,
                    consciousness_ms INTEGER, execution_rounds INTEGER, total_ms INTEGER, evaluation_result TEXT,
                    steps TEXT, source TEXT, run_id TEXT)""")
    conn.execute("""CREATE TABLE trajectory_event (run_id TEXT, event_seq INTEGER, episode_id INTEGER, task_id TEXT,
                    parent_run_id TEXT, ts TEXT, kind TEXT, data TEXT, source TEXT)""")
    conn.execute("""CREATE TABLE ibl_code_corpus (code_sha256 TEXT PRIMARY KEY, code TEXT, code_chars INTEGER,
                    masked TEXT, first_seen TEXT, last_seen TEXT, seen_count INTEGER, success_count INTEGER,
                    fail_count INTEGER, last_success INTEGER, last_ms INTEGER, last_error TEXT, last_agent TEXT,
                    last_origin TEXT, source TEXT)""")
    seq = 0
    for code, ok in codes_ok:
        sha = hashlib.sha256(code.encode()).hexdigest()
        conn.execute("INSERT OR IGNORE INTO ibl_code_corpus (code_sha256, code) VALUES (?, ?)", (sha, code))
        heads = [f"fn:{code.split('[fn:')[1].split(']')[0]}"] if "[fn:" in code else ["self:time"]
        conn.execute("INSERT INTO trajectory_event VALUES ('r1', ?, 1, 't', NULL, '2026-09-07T06:00:00', 'ibl.started', ?, '')",
                     (seq, json.dumps({"code_sha256": sha, "actions": heads, "nested": False})))
        seq += 1
        conn.execute("INSERT INTO trajectory_event VALUES ('r1', ?, 1, 't', NULL, '2026-09-07T06:00:01', 'ibl.finished', ?, '')",
                     (seq, json.dumps({"success": bool(ok)})))
        seq += 1
    conn.execute("INSERT INTO episode_log (id, started_at, agent, log, total_ms, source) "
                 "VALUES (1, '2026-09-07T06:00:00', 'system_ai', ?, 1000, 'usage')", (log,))
    conn.commit(); conn.close()
    return db


def _run(mod, monkeypatch, capsys, args):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(args, ensure_ascii=False)))
    mod.main()
    return json.loads(capsys.readouterr().out)


def test_에피소드통계는_궤적을_세고_로그_줄_쪼개짐에_무관하다(monkeypatch, capsys, tmp_path):
    mod = _load_script()
    codes = [('$a = [self:time]{}\n$b = $a >> [table:take]{n: 1}', True),
             ('$b >> [table:count]{}', True),                     # 앞 호출의 $b — 격리 파싱이면 '미할당' 오탐
             ('[fn:둘줄취하기]{n: 1}', False)]
    # 옛 로거의 쪼개진 화살표 줄: 힌트에 개행이 실려 `[node:action]` 이 첫 줄에만 있다 — 로그로 세면 1
    log = "\n".join(['[DeepSeek] 라운드 1/100 시작',
                     '[06:00:00] [system_ai] [self:time] ($a = [self:time]{}',
                     '$b = $a >> [table:take]{n: 1}) -> OK (3ms)'])
    monkeypatch.setattr(mod, "DB", _pulse_db(tmp_path, codes, log))
    row = _run(mod, monkeypatch, capsys, {"last": 5})["items"][0]
    assert row["IBL"] == 3 and row["실패"] == 1 and row["fn"] == 1, row
    assert row["문장"] == 4 and "문법오류" not in row["상태"], row   # 턴 변수 문맥 주입 — $b 는 오탐이 아니다
    assert row["상태"] == "로그계수 0≠궤적 3", row["상태"]   # 쪼개진 줄은 로그로는 0 — 계기끼리의 어긋남은 숨기지 않는다


def test_에피소드통계_진짜_문법오류는_문맥_주입_뒤에도_남는다(monkeypatch, capsys, tmp_path):
    mod = _load_script()
    codes = [('$a = [self:time]{}', True), ('$없는변수 >> [table:count]{}', False), ('[self:time]{ 깨진', False)]
    monkeypatch.setattr(mod, "DB", _pulse_db(tmp_path, codes, ""))
    row = _run(mod, monkeypatch, capsys, {"last": 5})["items"][0]
    assert row["상태"] == "문법오류 2", row      # 코퍼스(온전한 코드)라 미할당도 진짜 결함이다


# ── 실행 관문: 변형 인식 ────────────────────────────────────────────────────────
IDIOM = ('$원장 = [self:ledger]{path: "${원장경로}", op: "select", target: "covered", fields: ["id"]}\n'
         '$검색 = [sense:search_youtube]{query: "${주제}", limit: 12} >> [table:dedup]{by: "video_id"}\n'
         '$신선 = $검색 >> [table:filter]{where: "upload_date >= ${기준일}"} >> [table:sort]{by: "view_count", desc: true}\n'
         '$신선 >> [table:take]{n: 30}')
VARIANT = ('$원장 = [self:ledger]{path: "x.json", op: "select", target: "covered", fields: ["id", "verdict"]}\n'
           '$검색 = [sense:search_youtube]{query: "a", limit: 12} & [sense:search_youtube]{query: "b", limit: 12} >> [table:union]\n'
           '$신선 = $검색 >> [table:filter]{where: "upload_date >= 20260311"} >> [table:sort]{by: "view_count", desc: true}\n'
           '$신선 >> [table:take]{n: 40}')


def test_변형도_이름으로_인식된다(monkeypatch):
    import fn_recognizer
    monkeypatch.setattr(fn_recognizer, "_aliased_programs", lambda: [("유튜브모으기", IDIOM)])
    monkeypatch.setattr(fn_recognizer, "_aliased_shapes", lambda: {})
    v = fn_recognizer.variant_of(VARIANT)
    assert v and v["alias"] == "유튜브모으기" and v["hit"] == 3 and v["missed"] == [2], v
    hint = fn_recognizer.fn_hint_for(VARIANT)
    assert hint["variant"] is True and "[def: 유튜브모으기]" in hint["note"]
    # 무관한 프로그램은 변형이 아니다
    assert fn_recognizer.variant_of('$a = [self:time]{}\n$a >> [table:count]{}') is None


# ── 증류 관문: 슬롯 값 접지 ─────────────────────────────────────────────────────
def test_슬롯_값이_실행문에_없으면_이름을_받지_못한다():
    from ibl_idiom import slot_values_ungrounded
    calls = ['$신선 = $정보 >> [table:filter]{where: "upload_date >= 20260311"}']
    code = '$신선 = $정보 >> [table:filter]{where: "upload_date >= ${기준일}"}\n$신선 >> [table:take]{n: 3}'
    assert slot_values_ungrounded({"기준일": "2026-03-11"}, calls, code=code)      # 반성기가 값을 바꿔 적었다
    assert slot_values_ungrounded({"기준일": 20260311}, calls, code=code) is None   # 대입하면 실행문이 되살아난다
    assert slot_values_ungrounded({}, calls, code=code)                            # 값 없는 슬롯 = 검증 불가


def test_자동_작명은_값_접지를_지난다(monkeypatch):
    """rag 의 자동 작명 분기가 slot_values_ungrounded 를 부른다 — 부를 수 없는 모양과 같은 문."""
    src = (ROOT / "backend" / "cognition" / "ibl_usage_rag.py").read_text(encoding="utf-8")
    i = src.index("자동 작명(2026-09-05, 처방 2)")
    assert "slot_values_ungrounded(distilled.get(\"slots\")" in src[i:i + 3000]


# ── 회상 표면 ────────────────────────────────────────────────────────────────
def test_expand_카드는_호출이_먼저이고_실행_0을_말한다():
    import hippo_tree
    row = {"id": 1, "alias": "유튜브모으기", "ibl_code": IDIOM, "intent": "유튜브를 모은다", "category": "phrase",
           "success_count": 0, "fail_count": 0, "signature": "원장경로 주제 기준일", "returns": "items"}
    out = hippo_tree.render_names_first("보고서/X", [], [row], "", expand="유튜브모으기")
    assert out.startswith("호출: [fn:유튜브모으기]{"), out[:80]
    assert out.index("호출:") < out.index("[def: 유튜브모으기]")
    assert "실행 0" in out
    listing = hippo_tree.render_names_first("보고서/X", [], [row], "")
    assert "실행 0" in listing


def test_관용구_호출_실패_봉투에_정의가_실린다(monkeypatch, tmp_path):
    import ibl_control_blocks as cb

    class _DB:
        def find_phrase_by_alias(self, name):
            return {"ibl_code": '[self:read]{path: "${경로}"}\n[table:count]{}', "alias": name}
        def update_success_by_code(self, *_a, **_k):
            pass
        def phrase_aliases(self, n):
            return []
    import ibl_usage_db
    monkeypatch.setattr(ibl_usage_db, "IBLUsageDB", lambda: _DB())
    import workflow_engine
    monkeypatch.setattr(workflow_engine, "get_workflow", lambda name: None)
    monkeypatch.setattr(workflow_engine, "execute_pipeline",
                        lambda *a, **k: {"success": False, "error": "Step 1 에러: 파일 없음"})
    out = cb._execute_fn({"_node": "fn", "action": "읽고세기", "params": {"경로": "/없음"}}, str(tmp_path), "t")
    assert out["success"] is False and out["fn_source"] == "idiom"
    assert out["def"].startswith("[def: 읽고세기]{") and "본문을 새로 조립하지 말 것" in out["hint"]


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
