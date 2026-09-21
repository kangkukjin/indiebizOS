"""판정 관용구의 정적 계약·이름 호출·메타데이터 재등록 회귀. 외부 API는 격리한다."""
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest
import boot_paths  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
CATALOG = json.loads((ROOT / "data/idioms/curated.json").read_text())
NAMES = ("관련자료골라읽기", "의미로본문찾기")
ENTRIES = {e["name"]: e for e in CATALOG["idioms"] if e["name"] in NAMES}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_inferred_returns_and_catalog_examples():
    from curate_idioms import validate_catalog
    from ibl_typecheck import typecheck_code
    infos = validate_catalog({"idioms": list(ENTRIES.values())})
    for name, entry in ENTRIES.items():
        assert infos[name]["returns"] == "items⟨열 미상⟩"
        result = typecheck_code(f"[def: {name}]{{\n{entry['body']}\n}}\n"
                                + entry["example"] + ' >> [table:select]{columns:["url"]}')
        assert result["ok"] and not result.get("abstained"), result


class Registry:
    def __init__(self, path):
        self.path = path

    def _get_connection(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def find_phrase_by_alias(self, name):
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM ibl_examples WHERE alias=?", (name,)).fetchone()
            return dict(row) if row else None


def test_metadata_refresh_preserves_history_and_is_idempotent(tmp_path, monkeypatch):
    import ibl_usage_db
    from register_idiom import refresh_idiom_metadata
    db = Registry(tmp_path / "usage.db")
    refreshed = []
    monkeypatch.setattr(ibl_usage_db, "_tree_refresh", lambda topic, **kw: refreshed.append(topic))
    with db._get_connection() as conn:
        conn.execute("CREATE TABLE ibl_examples(id INTEGER PRIMARY KEY, alias, intent, ibl_code, "
                     "returns, signature, topic, always_on, success_count, fail_count)")
        for i, (name, entry) in enumerate(ENTRIES.items(), 1):
            conn.execute("INSERT INTO ibl_examples VALUES(?,?,?,?,?,?,?,?,?,?)",
                         (i, name, entry["when"], entry["body"], "scalar", "[]", "수집", 1, 7, 2))
    for name in NAMES:
        before = db.find_phrase_by_alias(name)
        assert refresh_idiom_metadata(db, name)
        after = db.find_phrase_by_alias(name)
        assert after["returns"] == "items⟨열 미상⟩"
        assert {k: v for k, v in after.items() if k not in ("returns", "signature")} == {
            k: v for k, v in before.items() if k not in ("returns", "signature")}
        assert not refresh_idiom_metadata(db, name)
    assert refreshed == ["수집"] * 4


@pytest.fixture
def run_named(tmp_path, monkeypatch):
    import ibl_engine
    import ibl_typecheck
    import ibl_usage_db
    import workflow_engine
    from common import spill
    from ibl_parser import parse_with_vars
    from ibl_control_blocks import _execute_fn
    from ibl_executors import _execute_table_each
    from tool_context import ToolContext

    helper = load("_judge_idiom_helper", "data/scripts/judgment_idioms.py")
    dataops = load("_judge_idiom_dataops", "data/packages/installed/tools/data-ops/handler.py")
    observed = {"judge": [], "crawl": []}

    class DB:
        def find_phrase_by_alias(self, name):
            return {"ibl_code": ENTRIES[name]["body"], "alias": name} if name in ENTRIES else None

        def update_success_by_code(self, *args, **kwargs):
            pass

    monkeypatch.setattr(ibl_usage_db, "IBLUsageDB", DB)
    monkeypatch.setattr(workflow_engine, "get_workflow", lambda name: None)
    monkeypatch.setattr(ibl_typecheck, "FN_CODE_SOURCES", [lambda n: ENTRIES[n]["body"] if n in ENTRIES else None])
    monkeypatch.setattr(spill, "_root", lambda: str(tmp_path / "spill"))
    original = ibl_engine._execute_ibl_impl

    def leaf(ti, project, agent_id=None):
        node, action, params = ti.get("_node"), ti.get("action"), dict(ti.get("params") or {})
        if node == "fn":
            return _execute_fn(ti, project, agent_id)
        if node == "self" and action == "script":
            assert params["id"] == "판정관용구"
            return {"success": True, "id": "판정관용구", "exit_code": 0,
                    **helper.run(helper.decode(params["args"]))}
        if node == "table" and action == "judge":
            rows = helper.rows(params["items"])
            observed["judge"].append(len(rows))
            return {"success": True, "items": [dict(r, judgment_result_value=True,
                    judgment_result_status="decided") for r in rows], "api_calls": 1}
        if node == "table" and action == "each":
            params["_depth"] = ti.get("_depth", 0)
            return _execute_table_each(params, project, agent_id=agent_id)
        if node == "table" and "data_" + str(action) in dataops._DISPATCH:
            return dataops.execute(params, ToolContext(project, "data_" + action))
        if node == "sense" and action == "crawl":
            observed["crawl"].append(params["url"])
            return {"success": True, "items": [{"text": "본문", "url": params["url"]}]}
        return original(ti, project, agent_id)

    monkeypatch.setattr(ibl_engine, "_execute_ibl_impl", leaf)
    monkeypatch.setattr(ibl_engine, "execute_ibl", leaf)

    def run(name, rows, limit, piped=False):
        args = {"질문": "관련 자료", "개수": limit}
        if name == "의미로본문찾기":
            args["문맥"] = 0
        if not piped:
            args["목록"] = {"items": rows}
        code = f"[fn:{name}]" + json.dumps(args, ensure_ascii=False)
        if piped:
            code = '$입력=' + json.dumps(rows, ensure_ascii=False) + '; $입력 >> ' + code
        steps, _ = parse_with_vars(code)
        result = workflow_engine.execute_pipeline(steps, str(tmp_path))
        assert result["success"], result
        final = result["final_result"]
        return helper.decode(final), observed

    return run


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("piped", [False, True])
def test_named_call_preserves_rows_audit_and_source_failures(run_named, name, piped):
    rows = [{"text": "본문", "title": "제목", "url": "https://fixture.test/a"},
            {"_error": "upstream", "url": "https://fixture.test/bad"}]
    result, calls = run_named(name, rows, 1, piped)
    assert result["items"][-1] == rows[-1]
    assert result["error_count"] == 1 and result["partial"] is True
    assert result["selection_info"]["evaluated"] == 1 and len(result["judgment_audit"]) == 2
    assert calls["judge"] == [1]
    assert len(calls["crawl"]) == (name == "관련자료골라읽기")


@pytest.mark.parametrize("name", NAMES)
def test_named_zero_limit_makes_no_external_calls(run_named, name):
    result, calls = run_named(name, [{"text": "본문", "title": "제목", "url": "https://fixture.test/a"}], 0)
    assert result["items"] == []
    assert result["selection_info"]["api_batches"] == 0
    assert calls == {"judge": [], "crawl": []}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
