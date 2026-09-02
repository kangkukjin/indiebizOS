"""구성요소 생명주기 회귀 고정물 (docs/COMPONENT_APOPTOSIS_HANDOFF.md §3, 2026-09-02)

재현하는 결함 부류(전부 '카운터 심고 두고 보기'가 아니라 관문으로):
  1. 참조는 있고 실행 0 인 어휘는 candidate 가 되지 않는다(유지보수·계절 어휘 오살 회귀).
  2. success=1 이지만 빈 items 만 있는 액션은 무신호로 센다(sense:search_local 계수 19·결과 0 회귀).
  3. source='test'·channel='self_check' 실행은 신호가 아니다(2026-08-15 순찰 55% 오염 회귀).
  4. 첫 관측 후 grace 안은 무조건 alive.
  5. candidate 가 신호 1건으로 alive 복귀 + revivals 기록 + 표식 해제.
  6. 어휘 retired 는 판정 큐에만 적히고 파일을 건드리지 않는다.
  7. 후보끼리의 상호 참조는 지지가 아니다(고아 섬).
  + 가이드 candidate 표식(첫 줄 주석)·가이드 은퇴(_retired 이동 + guide_db 항목 제거)·
    워크플로우 은퇴·커밋 함수 호출·판정 큐 중복 방지·절 단위 사용 귀속.

실행: .venv/bin/python -m pytest backend/test_component_lifecycle.py -q
"""
import json
import sqlite3
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401,E402

import component_lifecycle as CL  # noqa: E402


def _d(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat()


TODAY = date.today().isoformat()


@pytest.fixture
def env(tmp_path, monkeypatch):
    """격리된 몸 — 라이브 원장은 한 바이트도 건드리지 않는다."""
    root = tmp_path
    data = root / "data"
    for d in ("guides", "workflows", "scripts", "common_prompts", "system_ai_prompts"):
        (data / d).mkdir(parents=True)
    (root / "outputs" / "imagination_training").mkdir(parents=True)

    monkeypatch.setattr(CL, "BASE", root)
    monkeypatch.setattr(CL, "DATA", data)
    monkeypatch.setattr(CL, "POLICY_PATH", data / "lifecycle_policy.yaml")
    monkeypatch.setattr(CL, "STATE_PATH", data / "lifecycle_state.json")
    monkeypatch.setattr(CL, "FLAGS_PATH", data / "lifecycle_flags.json")
    monkeypatch.setattr(CL, "VERDICTS_PATH", root / "outputs" / "imagination_training" / "PENDING_VERDICTS.md")
    monkeypatch.setattr(CL, "GUIDES_DIR", data / "guides")
    monkeypatch.setattr(CL, "GUIDE_INDEX_PATH", data / "guide_db.json")
    monkeypatch.setattr(CL, "WORKFLOWS_DIR", data / "workflows")
    monkeypatch.setattr(CL, "SCRIPTS_DIR", data / "scripts")
    monkeypatch.setattr(CL, "SCRIPTS_STATE_PATH", data / "scripts.json")
    monkeypatch.setattr(CL, "NODES_PATH", data / "ibl_nodes.yaml")
    monkeypatch.setattr(CL, "PULSE_DB_PATH", data / "world_pulse.db")
    monkeypatch.setattr(CL, "GUIDE_USAGE_DB_PATH", data / "guide_usage.db")
    monkeypatch.setattr(CL, "USAGE_DB_PATH", data / "ibl_usage.db")
    monkeypatch.setattr(CL, "TRIGGERS_PATH", data / "event_triggers.json")
    monkeypatch.setattr(CL, "CALENDAR_PATH", data / "calendar_events.json")
    monkeypatch.setattr(CL, "PROMPT_DIRS", (data / "common_prompts", data / "system_ai_prompts"))

    commits = []
    monkeypatch.setattr(CL, "COMMIT_FN", lambda paths, msg: (commits.append((paths, msg)) or True))

    (data / "lifecycle_policy.yaml").write_text(
        "grace_days: 30\ncandidate_after_days: 60\nretire_after_days: 90\ncadence_hours: 24\n",
        encoding="utf-8")
    (data / "ibl_nodes.yaml").write_text(
        "nodes:\n  self:\n    actions:\n      time: {}\n      foo: {}\n  sense:\n    actions:\n      bar: {}\n",
        encoding="utf-8")
    (data / "guide_db.json").write_text(json.dumps({"guides": []}), encoding="utf-8")

    conn = sqlite3.connect(str(data / "world_pulse.db"))
    conn.execute("""CREATE TABLE action_health (id INTEGER PRIMARY KEY, node TEXT, action TEXT,
                    success INTEGER, response_ms INTEGER, source TEXT, timestamp TEXT,
                    channel TEXT, error TEXT, shape TEXT, n_items INTEGER)""")
    conn.execute("""CREATE TABLE workflow_run (id INTEGER PRIMARY KEY, workflow_id TEXT, success INTEGER,
                    response_ms INTEGER, source TEXT, shape TEXT, timestamp TEXT)""")
    conn.commit(); conn.close()
    conn = sqlite3.connect(str(data / "guide_usage.db"))
    conn.execute("CREATE TABLE guide_use (id INTEGER PRIMARY KEY, guide TEXT, used_on TEXT, origin TEXT, n INTEGER)")
    conn.commit(); conn.close()
    conn = sqlite3.connect(str(data / "ibl_usage.db"))
    conn.execute("CREATE TABLE ibl_examples (id INTEGER PRIMARY KEY, intent TEXT, ibl_code TEXT, source TEXT)")
    conn.commit(); conn.close()

    class Env:
        pass
    e = Env(); e.root = root; e.data = data; e.commits = commits
    return e


def _seed_state(env, first_seen_days_ago=200, candidates=None):
    """모든 항목이 유예를 지난 상태로 시작 — key 를 미리 알 수 없으니 인벤토리로 채운다."""
    inv = CL.collect_inventory()
    st = {"first_seen": {k: _d(first_seen_days_ago) for k in inv},
          "candidates": candidates or {}, "revivals": [], "retired": [], "verdict_queued": {}}
    CL.STATE_PATH.write_text(json.dumps(st), encoding="utf-8")
    return st


def _health(env, node, action, days_ago=1, success=1, source="usage", channel=None, shape="items", n_items=3):
    conn = sqlite3.connect(str(env.data / "world_pulse.db"))
    conn.execute("INSERT INTO action_health(node, action, success, source, timestamp, channel, shape, n_items) "
                 "VALUES (?,?,?,?,?,?,?,?)",
                 (node, action, success, source, _d(days_ago) + "T10:00:00", channel, shape, n_items))
    conn.commit(); conn.close()


def _guide(env, name, text):
    p = env.data / "guides" / name
    p.write_text(text, encoding="utf-8")
    db = json.loads((env.data / "guide_db.json").read_text())
    db["guides"].append({"id": name[:-3], "name": name, "description": "", "keywords": [], "file": name})
    (env.data / "guide_db.json").write_text(json.dumps(db, ensure_ascii=False), encoding="utf-8")
    return p


def _candidates(res):
    return {c["key"] for c in res["candidates"]}


# ── 1. 참조는 지지다 ─────────────────────────────────────────────────────────────

def test_referenced_but_unexecuted_action_is_not_candidate(env):
    _guide(env, "a.md", "# A\n\n## 절\n[self:foo]{} 를 쓴다.\n")
    # 가이드 a.md 는 켜진 트리거가 지목해 살아 있다
    (env.data / "event_triggers.json").write_text(json.dumps({"triggers": [
        {"id": "t1", "enabled": True, "pipeline": "read_guide a.md 후 실행"}]}), encoding="utf-8")
    _seed_state(env)
    res = CL.compute_transitions(today=TODAY)
    assert "action:self:foo" not in _candidates(res), "가이드가 참조하는 어휘는 실행 0 이어도 산다"
    assert "guide:a.md" not in _candidates(res), "트리거가 지목하는 가이드는 산다"
    # 아무도 안 부르고 아무도 안 참조하는 어휘만 후보
    assert "action:self:time" in _candidates(res)
    assert "action:sense:bar" in _candidates(res)


# ── 2. 계수 ≠ 쓸모 ──────────────────────────────────────────────────────────────

def test_empty_items_success_is_not_a_signal(env):
    _seed_state(env)
    _health(env, "self", "time", days_ago=2, shape="items", n_items=0)     # 성공했지만 빈손
    _health(env, "sense", "bar", days_ago=2, shape="items", n_items=5)     # 결과 있음
    res = CL.compute_transitions(today=TODAY)
    assert "action:self:time" in _candidates(res), "빈 items 성공은 생존 신호가 아니다(search_local 회귀)"
    assert "action:sense:bar" not in _candidates(res)


# ── 3. 순찰·시험은 삶이 아니다 ─────────────────────────────────────────────────

def test_self_check_and_test_sources_are_not_signals(env):
    _seed_state(env)
    _health(env, "self", "time", days_ago=1, source="test")
    _health(env, "self", "foo", days_ago=1, source="usage", channel="self_check")
    _health(env, "self", "foo", days_ago=1, source="self_check")
    res = CL.compute_transitions(today=TODAY)
    assert {"action:self:time", "action:self:foo"} <= _candidates(res)


# ── 4. 신생 유예 ────────────────────────────────────────────────────────────────

def test_grace_period_keeps_new_items_alive(env):
    res = CL.compute_transitions(today=TODAY)          # 상태 없음 = 전부 오늘 첫 관측
    assert not res["candidates"]
    assert res["grace"] == res["total"]


# ── 5. 부활 ─────────────────────────────────────────────────────────────────────

def test_candidate_revives_on_signal_and_mark_is_removed(env):
    p = _guide(env, "g.md", "# G\n\n## 절\n[self:foo]{}\n")
    _seed_state(env)
    r1 = CL.compute_transitions(today=TODAY)
    assert "guide:g.md" in _candidates(r1)
    assert p.read_text(encoding="utf-8").startswith("<!-- lifecycle: candidate since"), "보이는 표식(숨김 아님)"
    # 다음 날 주입됐다
    conn = sqlite3.connect(str(env.data / "guide_usage.db"))
    conn.execute("INSERT INTO guide_use(guide, used_on, origin, n) VALUES (?,?,?,1)", ("g.md", TODAY, "agent"))
    conn.commit(); conn.close()
    r2 = CL.compute_transitions(today=TODAY)
    assert "guide:g.md" not in _candidates(r2)
    assert any(r["key"] == "guide:g.md" and r["by"].startswith("signal:") for r in r2["revived"])
    assert not p.read_text(encoding="utf-8").startswith("<!--"), "표식 해제"
    st = json.loads(CL.STATE_PATH.read_text())
    assert st["revivals"] and st["revivals"][0]["key"] == "guide:g.md"


def test_revival_by_reference_records_referrer(env):
    _seed_state(env, candidates={"action:self:foo": {"since": _d(10), "evidence": "e", "kind": "action"}})
    (env.data / "common_prompts" / "p.md").write_text("[self:foo] 를 쓰라", encoding="utf-8")
    res = CL.compute_transitions(today=TODAY)
    rev = [r for r in res["revived"] if r["key"] == "action:self:foo"]
    assert rev and rev[0]["by"].startswith("reference:prompt:p.md")


# ── 6. 어휘 은퇴는 판정 큐 ───────────────────────────────────────────────────────

def test_action_retirement_goes_to_verdict_queue_only(env):
    _seed_state(env, candidates={"action:self:time": {"since": _d(100), "evidence": "참조 0 · 실행 0",
                                                      "kind": "action"}})
    res = CL.compute_transitions(today=TODAY)
    assert "action:self:time" in res["verdicts"]
    assert not res["retired"], "어휘는 기계가 은퇴시키지 않는다(언어 개정)"
    pv = CL.VERDICTS_PATH.read_text(encoding="utf-8")
    assert "`action:self:time`" in pv and "- [ ]" in pv
    assert (env.data / "ibl_nodes.yaml").read_text().count("time") == 1, "카탈로그 무접촉"
    # 두 번 돌아도 한 줄
    CL.compute_transitions(today=TODAY)
    assert CL.VERDICTS_PATH.read_text(encoding="utf-8").count("`action:self:time`") == 1
    assert not env.commits, "어휘 판정 큐 적립은 커밋할 파일이 없다"


# ── 7. 고아 섬 ──────────────────────────────────────────────────────────────────

def test_mutual_references_between_candidates_are_not_support(env):
    _guide(env, "a.md", "# A\n\n## 절\n자세한 건 b.md 를 보라.\n")
    _guide(env, "b.md", "# B\n\n## 절\n선행은 a.md.\n")
    _seed_state(env, candidates={
        "guide:a.md": {"since": _d(5), "evidence": "e", "kind": "guide"},
        "guide:b.md": {"since": _d(5), "evidence": "e", "kind": "guide"}})
    res = CL.compute_transitions(today=TODAY)
    assert {"guide:a.md", "guide:b.md"} <= _candidates(res)
    assert not res["revived"]


# ── 은퇴 집행 (가역 층) ──────────────────────────────────────────────────────────

def test_guide_retirement_moves_file_and_removes_index_entry_and_commits(env):
    p = _guide(env, "old.md", "# Old\n")
    _seed_state(env, candidates={"guide:old.md": {"since": _d(100), "evidence": "참조 0", "kind": "guide"}})
    res = CL.compute_transitions(today=TODAY)
    assert any(r["key"] == "guide:old.md" for r in res["retired"])
    assert not p.exists()
    assert (env.data / "guides" / "_retired" / "old.md").exists()
    db = json.loads((env.data / "guide_db.json").read_text())
    assert all(g["file"] != "old.md" for g in db["guides"]), "유령 등재를 남기지 않는다(빌드 가드 회귀)"
    assert env.commits and env.commits[-1][1].startswith("apoptosis:")
    paths = env.commits[-1][0]
    assert "data/guides/old.md" in paths and "data/guides/_retired/old.md" in paths and "data/guide_db.json" in paths


def test_workflow_and_script_retirement(env):
    (env.data / "workflows" / "wf.yaml").write_text("name: wf\nsteps: '[self:time]{}'\n", encoding="utf-8")
    (env.data / "scripts" / "registry.yaml").write_text(
        "sc:\n  description: d\n  file: sc.py\n  interpreter: python\n", encoding="utf-8")
    (env.data / "scripts" / "sc.py").write_text("print(1)\n", encoding="utf-8")
    _seed_state(env, candidates={
        "workflow:wf": {"since": _d(100), "evidence": "e", "kind": "workflow"},
        "script:sc": {"since": _d(100), "evidence": "e", "kind": "script"}})
    res = CL.compute_transitions(today=TODAY)
    keys = {r["key"] for r in res["retired"]}
    assert {"workflow:wf", "script:sc"} <= keys
    assert (env.data / "workflows" / "_retired" / "wf.yaml").exists()
    assert (env.data / "scripts" / "_retired" / "sc.py").exists()
    import yaml
    reg = yaml.safe_load((env.data / "scripts" / "registry.yaml").read_text()) or {}
    assert "sc" not in reg
    rreg = yaml.safe_load((env.data / "scripts" / "_retired" / "registry.yaml").read_text())
    assert rreg["sc"]["file"] == "sc.py", "되살리기용 등록 항목 보존"


def test_workflow_candidate_mark_is_a_yaml_field_not_a_hide(env):
    (env.data / "workflows" / "wf.yaml").write_text("name: wf\nsteps: '[self:time]{}'\n", encoding="utf-8")
    _seed_state(env)
    CL.compute_transitions(today=TODAY)
    import yaml
    d = yaml.safe_load((env.data / "workflows" / "wf.yaml").read_text())
    assert d["lifecycle"]["candidate_since"] == TODAY and d["steps"], "본문은 그대로, 표식만 추가"


def test_workflow_run_signal_keeps_workflow_alive(env):
    (env.data / "workflows" / "wf.yaml").write_text("name: wf\nsteps: '[self:time]{}'\n", encoding="utf-8")
    conn = sqlite3.connect(str(env.data / "world_pulse.db"))
    conn.execute("INSERT INTO workflow_run(workflow_id, success, source, timestamp) VALUES (?,?,?,?)",
                 ("wf", 1, "usage", _d(3) + "T01:00:00"))
    conn.commit(); conn.close()
    _seed_state(env)
    res = CL.compute_transitions(today=TODAY)
    assert "workflow:wf" not in _candidates(res)
    # 워크플로우가 부르는 어휘도 산다(참조)
    assert "action:self:time" not in _candidates(res)


# ── 판정 큐 유틸 ─────────────────────────────────────────────────────────────────

def test_queue_verdict_dedupes_and_keeps_sections(env):
    CL.VERDICTS_PATH.write_text("# 큐\n\n## 미결\n\n(없음)\n\n## 판정 완료 (사용자가 옮김)\n", encoding="utf-8")
    assert CL.queue_verdict("backup:x", "x 삭제?")
    assert not CL.queue_verdict("backup:x", "x 삭제?")
    txt = CL.VERDICTS_PATH.read_text(encoding="utf-8")
    assert txt.count("`backup:x`") == 1 and "(없음)" not in txt
    assert txt.index("## 미결") < txt.index("`backup:x`") < txt.index("## 판정 완료")


# ── 절 단위 사용 귀속 (guide_registry) ──────────────────────────────────────────

def test_section_use_attribution(tmp_path, monkeypatch):
    import guide_registry as GR
    monkeypatch.setattr(GR, "GUIDES_DIR", tmp_path)
    monkeypatch.setattr(GR, "DB_PATH", tmp_path / "guide_usage.db")
    (tmp_path / "g.md").write_text("# G\n\n## 하나\n[self:time]{}\n\n## 둘\n[sense:bar]{}\n", encoding="utf-8")
    assert GR.record_section_use("g.md", {("self", "time")}) == 1
    assert GR.record_section_use("g.md", set()) == 0, "실행 없는 턴은 관측 기회가 아니다"
    uses = GR.section_uses("g.md", 30)
    assert uses.get("하나") == 1 and "둘" not in uses and uses.get("*") == 1


def test_executed_pairs_extraction():
    from guide_feedback import _executed_pairs
    calls = [{"name": "execute_ibl", "input": {"code": '[self:read]{path:"x"} >> [table:count]{}'}},
             {"name": "ibl:sense:search", "input": {}},
             {"name": "execute_ibl", "input": {"node": "self", "action": "time", "params": {}}}]
    assert _executed_pairs(calls) == {("self", "read"), ("table", "count"), ("sense", "search"), ("self", "time")}


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-q"]))
