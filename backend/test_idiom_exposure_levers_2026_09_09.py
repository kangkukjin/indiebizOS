"""관용구 노출 지렛대 1~4 (2026-09-09) 관문.

1 자족형 서명 개정(--resign) · 2 '언제'=입력 모양(선정집 데이터) · 3 생산자별 용례(선정집 examples 검증) ·
4 어휘 목록 병기(잎 액션 줄 아래 `↳ 관용구`)와 expose_idioms=False 가 둘 다 지우는 스위치.
"""
import copy
import json
import sqlite3
import sys
from pathlib import Path

import pytest
import boot_paths  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

OLD = ('$대상 = [table:take]{n: "${개수}"}\n'
       '$return = $대상 >> [table:each]{keep: ["파일", "줄번호"], limit: "${개수}", collect: true, on_error: "keep"} {\n'
       "  [self:read]{path: '$it.파일', start_line: $it.줄번호, limit: ${줄수}}\n}")
NEW = OLD.replace('$대상 = [table:take]', '$대상 = $위치 >> [table:take]')
WHEN = "파일·줄번호 열이 있는 위치 목록의 앞 개수곳을 각 줄번호부터 줄수만큼 읽어 위치·본문·실패를 모을 때."


def test_anchor_is_last_leaf_action_and_ignores_fn_and_blocks():
    from ibl_access import _anchor_action
    assert _anchor_action(NEW) == "self:read"
    assert _anchor_action('$합 = $a & $b >> [table:union] >> [table:dedup]{by: "k"}; '
                          '$return = $합 >> [self:write]{path: "x", format: "json"}') == "self:write"
    assert _anchor_action('[fn:다른것]{} >> [if: empty($items)]{[self:grep]{pattern: "x"}}') == "self:grep"
    assert _anchor_action("") == ""


def _fixture_usage(tmp_path, body, alias="위치마다읽기", topic="찾기"):
    from ibl_usage_db import _signature_of     # 저장 서명은 원장 규약 그대로(표시·실행이 한 벌)
    (tmp_path / "data/idioms").mkdir(parents=True)
    catalog = {"version": 1, "demote": {}, "idioms": [{
        "name": alias, "when": WHEN, "topic": topic, "body": body, "always_on": True,
        "inputs": "위치: 파일·줄번호 items. 개수·줄수: 정수.",
        "example": '$위치 = [self:read]{path:"a.json"}; [fn:위치마다읽기]{위치:$위치,개수:3,줄수:5}'}]}
    (tmp_path / "data/idioms/curated.json").write_text(json.dumps(catalog, ensure_ascii=False))
    with sqlite3.connect(tmp_path / "data/ibl_usage.db") as con:
        con.execute("CREATE TABLE ibl_examples (intent,ibl_code,success_count,fail_count,"
                    "topic,alias,returns,signature,always_on,created_at)")
        con.execute("INSERT INTO ibl_examples VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (WHEN, body, 0, 0, topic, alias, "items", _signature_of(body), 1, "2026-09-09"))


def test_catalog_line_stands_under_anchor_and_switch_strips_both(tmp_path, monkeypatch):
    import ibl_access
    import runtime_utils
    _fixture_usage(tmp_path, NEW)
    monkeypatch.setattr(runtime_utils, "get_base_path", lambda: tmp_path)
    monkeypatch.setattr(ibl_access, "_get_nodes_path", lambda: ROOT / "data/ibl_nodes.yaml")   # 어휘는 실물
    monkeypatch.setattr(ibl_access, "_idioms_cache", {"text": None, "t": 0, "key": None, "anchors": {}})
    env = ibl_access.build_environment()
    lines = env.splitlines()
    i = next(k for k, l in enumerate(lines) if l.strip().startswith("self:read ::"))
    assert lines[i + 1].strip().startswith("↳ 관용구 [fn:위치마다읽기]{위치: "), lines[i + 1]
    assert "<ibl_idioms" in env and env.count("↳ 관용구") == 1     # 다른 잎 액션 옆에는 서지 않는다
    hidden = ibl_access.build_environment(expose_idioms=False)
    assert "↳ 관용구" not in hidden and "<ibl_idioms" not in hidden
    assert "self:read ::" in hidden and "self:write ::" in hidden   # 어휘 목록 자체는 그대로


def test_validate_catalog_runs_every_producer_example_through_the_gate():
    import curate_idioms
    catalog = json.loads((ROOT / "data/idioms/curated.json").read_text())
    entry = next(e for e in catalog["idioms"] if e["name"] == "위치마다읽기")
    assert entry["examples"], "생산자가 다른 용례가 선정집에 있어야 한다(지렛대 3)"
    assert "grep" not in entry["when"].split("(")[0]          # '언제'는 생산자가 아니라 입력 모양으로 시작한다(지렛대 2)
    piped = copy.deepcopy(catalog)
    next(e for e in piped["idioms"] if e["name"] == "위치마다읽기")["examples"].append(
        {"intent": "파이프로 위치 전달", "code": '[self:read]{path:"a.json"} >> [fn:위치마다읽기]{개수:3,줄수:5}'})
    curate_idioms.validate_catalog(piped)
    bad = copy.deepcopy(piped)
    next(e for e in bad["idioms"] if e["name"] == "위치마다읽기")["examples"][-1]["code"] = (
        '[self:read]{path:"a.json"} >> [fn:위치마다읽기]{개수:3}')
    with pytest.raises(ValueError, match="인자"):
        curate_idioms.validate_catalog(bad)
    bad = copy.deepcopy(piped)
    next(e for e in bad["idioms"] if e["name"] == "위치마다읽기")["examples"][-1]["code"] = (
        '[fn:위치마다읽기]{개수:3,줄수:5}')
    with pytest.raises(ValueError, match="인자"):
        curate_idioms.validate_catalog(bad)


class _DB:
    """update_idiom 이 쓰는 표면만 — 실 원장·벡터·가지 문서 무접촉."""
    def __init__(self, path):
        self.path = path
        with self._get_connection() as c:
            c.execute("CREATE TABLE ibl_examples (id INTEGER PRIMARY KEY, intent, ibl_code, alias, returns, signature,"
                      " success_count DEFAULT 0, fail_count DEFAULT 0, bypass_count DEFAULT 0, avg_ms, avg_tokens,"
                      " updated_at, topic, always_on, source)")
    def _get_connection(self):
        c = sqlite3.connect(self.path); c.row_factory = sqlite3.Row
        return c
    def add(self, alias, code, source="manual_registry"):
        with self._get_connection() as c:
            cur = c.execute("INSERT INTO ibl_examples (intent, ibl_code, alias, topic, always_on, source) VALUES (?,?,?,?,1,?)",
                            (WHEN, code, alias, "찾기", source))
            return cur.lastrowid
    def find_phrase_by_alias(self, name):
        with self._get_connection() as c:
            r = c.execute("SELECT * FROM ibl_examples WHERE alias=?", (name,)).fetchone()
            return dict(r) if r else None
    def _index_single(self, *a, **k):
        pass


def test_update_idiom_signature_change_needs_resign_and_names_old_callers(tmp_path, monkeypatch, capsys):
    import ibl_usage_db
    from register_idiom import update_idiom
    monkeypatch.setattr(ibl_usage_db, "_tree_refresh", lambda *a, **k: None)
    db = _DB(tmp_path / "usage.db")
    rid = db.add("위치마다읽기", OLD)
    caller = db.add("", '[self:grep]{pattern:"x"} >> [fn:위치마다읽기]{개수:3,줄수:5}', source="idiom_registry")
    with pytest.raises(ValueError, match="--resign"):
        update_idiom(db, "위치마다읽기", NEW, "서명 개정 시험")
    assert update_idiom(db, "위치마다읽기", NEW, "서명 개정 시험", resign=True) is True
    row = db.find_phrase_by_alias("위치마다읽기")
    assert row["ibl_code"] == NEW and "위치" in json.loads(row["signature"]) if row["signature"].startswith("[") else True
    with db._get_connection() as c:
        assert c.execute("SELECT count(*) FROM ibl_idiom_revisions WHERE example_id=?", (rid,)).fetchone()[0] == 1
    out = capsys.readouterr().out
    assert f"#{caller}" in out and "옛 서명" in out      # 옛 서명으로 부르는 용례를 이름으로 짚어 준다


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
