"""ep2835·2836 검토 수리 3건 회귀 (2026-09-05, 사용자 판정 "세 가지 다 고쳐줘").

  G1  [self:grep] 은 로그(*.log·회전본 *.log.N)·_backups·.worktrees·spill 을 기본 제외하고 봉투 `excluded` 로 신고한다.
      include_logs:true 면 로그가 다시 모집단에 든다(rg 경로·파이썬 경로 둘 다 — 한글 패턴으로 파이썬 경로를 강제).
  E1  [self:edit] replace_all:true 는 old_string 이 여러 곳이어도 전부 바꾸고 교체 수를 말한다.
      기본(false)은 종전대로 거절하되 replace_all 을 안내한다.
  T1  hippo_tree.settle_topic — 새 하위 가지 제안은 되풀이(TOPIC_BIRTH_MIN)가 증명될 때까지 조상 가지에 기록되고,
      기존 가지·새 최상위 가지는 그대로 통과한다. 원장은 트리 폴더 안 `_topic_proposals.json`.
임시 폴더·임시 트리만 만진다(실 트리·실 DB 무접촉). 실행: .venv/bin/python -m pytest backend/test_grep_edit_topic_gate_2026_09_05.py -q
"""
import importlib.util
import json
import os
import sqlite3
import sys

import pytest

BACKEND = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND)
import boot_paths  # noqa: E402,F401

_ESS = os.path.join(os.path.dirname(BACKEND), "data", "packages", "installed", "tools", "system_essentials")


def _load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", os.path.join(_ESS, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- G1 grep 잡음 제외
def _grep_tree(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("NEEDLE 코드\n", encoding="utf-8")
    (tmp_path / "backend_keeper.log").write_text("NEEDLE 로그 한 줄 코드\n", encoding="utf-8")
    (tmp_path / "old.log.1").write_text("NEEDLE 회전 로그 코드\n", encoding="utf-8")
    (tmp_path / "_backups").mkdir()
    (tmp_path / "_backups" / "x.md").write_text("NEEDLE 백업 코드\n", encoding="utf-8")
    return str(tmp_path)


@pytest.mark.parametrize("pattern", ["NEEDLE", "코드"])       # ASCII=rg 경로 · 한글=파이썬 경로
def test_g1_logs_and_noise_excluded_by_default(tmp_path, pattern):
    G = _load("fs_grep")
    root = _grep_tree(tmp_path)
    r = json.loads(G.run({"pattern": pattern, "path": root}, root))
    files = {row["파일"] if isinstance(row, dict) and "파일" in row else str(row) for row in r.get("items", [])}
    joined = " ".join(files) + " " + (r.get("text") or "")
    assert "a.py" in joined
    assert ".log" not in joined and "_backups" not in joined, joined
    assert r.get("excluded") and "include_logs" in r["excluded"]
    r2 = json.loads(G.run({"pattern": pattern, "path": root, "include_logs": True}, root))
    j2 = " ".join(str(x) for x in r2.get("items", [])) + " " + (r2.get("text") or "")
    assert "backend_keeper.log" in j2 and "old.log.1" in j2
    assert r2.get("excluded") is None


# ---------------------------------------------------------------- E1 edit replace_all
def _edit(tmp_path, **params):
    from ibl_engine import execute_ibl
    p = tmp_path / "t.txt"
    p.write_text("foo\nbar foo\nfoo end\n", encoding="utf-8")
    ti = {"_node": "self", "action": "edit", "params": {"path": str(p), "old_string": "foo", "new_string": "baz", **params}}
    out = execute_ibl(ti, str(tmp_path))
    return str(out), p.read_text(encoding="utf-8")


def test_e1_replace_all_replaces_every_occurrence(tmp_path):
    out, text = _edit(tmp_path, replace_all=True)
    assert text == "baz\nbar baz\nbaz end\n", text
    assert "3곳 교체" in out, out


def test_e1_default_still_rejects_ambiguous_but_hints(tmp_path):
    out, text = _edit(tmp_path)
    assert text.startswith("foo\n")                         # 무변경
    assert "3번 발견" in out and "replace_all" in out, out


def test_e1_declared_in_vocabulary():
    import yaml
    d = yaml.safe_load(open(os.path.join(_ESS, "ibl_actions.yaml"), encoding="utf-8"))
    edit = d["self"]["actions"]["edit"] if "self" in d else d["nodes"]["self"]["actions"]["edit"]
    assert edit["params"]["replace_all"] == "boolean"
    grep = d["self"]["actions"]["grep"] if "self" in d else d["nodes"]["self"]["actions"]["grep"]
    assert grep["params"]["include_logs"] == "boolean"


# ---------------------------------------------------------------- T1 가지 출생 관문
def _mk_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE ibl_examples (id INTEGER PRIMARY KEY AUTOINCREMENT, intent TEXT, ibl_code TEXT, nodes TEXT, "
                 "category TEXT DEFAULT 'single', difficulty INTEGER, source TEXT, success_count INTEGER DEFAULT 0, "
                 "fail_count INTEGER DEFAULT 0, tags TEXT, created_at TEXT, updated_at TEXT, avg_ms REAL, avg_tokens REAL, "
                 "topic TEXT DEFAULT '', alias TEXT DEFAULT '', returns TEXT DEFAULT '')")
    conn.execute("INSERT INTO ibl_examples (intent, ibl_code, topic, created_at, updated_at) VALUES ('x', '[self:time]{}', '개발', '2026-09-05', '2026-09-05')")
    conn.commit(); conn.close()


def test_t1_new_subtopic_needs_repetition(tmp_path, monkeypatch):
    import hippo_tree as HT
    db = str(tmp_path / "usage.db"); _mk_db(db)
    monkeypatch.setattr(HT, "DOC_DIR", str(tmp_path / "tree"))
    assert HT.settle_topic("개발", db)[0] == "개발"                          # 기존 가지 통과
    assert HT.settle_topic("여행", db)[0] == "여행"                          # 새 최상위 가지 통과
    t, note = HT.settle_topic("개발/설정 값 올리기", db)
    assert t == "개발" and "1회째" in note                                   # 첫 제안 → 조상
    ledger = json.load(open(os.path.join(str(tmp_path / "tree"), HT.PROPOSALS_NAME), encoding="utf-8"))
    assert ledger == {"개발/설정 값 올리기": 1}
    t2, note2 = HT.settle_topic("개발/설정 값 올리기", db)
    assert t2 == "개발/설정 값 올리기" and "출생" in note2                    # 되풀이 → 출생
    assert "개발/설정 값 올리기" not in json.load(open(os.path.join(str(tmp_path / "tree"), HT.PROPOSALS_NAME), encoding="utf-8"))
    assert HT.settle_topic("개발/설정 값 올리기/세부", db)[0] == "개발"       # 깊이 3 도 같은 규칙, 가장 가까운 기존 조상


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
