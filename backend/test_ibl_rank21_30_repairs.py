"""21~30위 어휘 감사 12개 결함의 회귀. 외부 서비스·모델은 격리한다."""

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import struct
import sys
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest

PKG = Path(__file__).resolve().parents[1] / "data/packages/installed/tools"


def load(package, name="handler"):
    folder = PKG / package
    sys.path.insert(0, str(folder))
    spec = importlib.util.spec_from_file_location(
        "rank21_" + package.replace("-", "_") + "_" + name, folder / (name + ".py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def scripts(tmp_path, monkeypatch):
    mod = load("system_essentials", "script_ops")
    for name, path in {
        "_RUN_DIR": tmp_path / "runs",
        "_JOB_DIR": tmp_path / "runs/jobs",
        "_STATE": tmp_path / "state.json",
        "_SCRIPT_DIR": tmp_path,
    }.items():
        monkeypatch.setattr(mod, name, path)
    monkeypatch.setattr(mod, "_review_environment", lambda: None)
    return mod


@pytest.mark.parametrize(
    "payload",
    [
        {"success": False, "error": "domain failure", "items": []},
        {"success": False},
        {"error": "domain failure"},
    ],
)
def test_script_business_failure_is_not_process_success(scripts, tmp_path, monkeypatch, payload):
    path = tmp_path / "failure.py"
    path.write_text("print(" + repr(json.dumps(payload)) + ")\n")
    monkeypatch.setattr(
        scripts,
        "_read_registry",
        lambda: {"fixture": {"file": path.name, "interpreter": "python"}},
    )
    result = scripts.op_run({"id": "fixture"})
    assert result["success"] is False and result["exit_code"] == 0 and result["error"]
    assert scripts.op_list({})["items"][0]["last_status"] == "error"
    # 분리 러너도 동일 판정. 알림은 보내지 않는다.
    runner = load("system_essentials", "_bg_runner")
    job_path = tmp_path / "job.json"
    job_path.write_text(
        json.dumps(
            {
                "job_id": "fixture",
                "id": "fixture",
                "script": str(path),
                "interpreter": sys.executable,
                "log": str(tmp_path / "job.log"),
            }
        )
    )
    monkeypatch.setattr(sys, "argv", ["runner", str(job_path)])
    monkeypatch.setattr(runner, "_announce", lambda job: None)
    runner.main()
    job = json.loads(job_path.read_text())
    assert job["status"] == "failed" and job["result"]["success"] is False
    scripts._JOB_DIR.mkdir(parents=True, exist_ok=True)
    (scripts._JOB_DIR / "fixture.json").write_text(json.dumps(job))
    status = scripts.op_status({"job_id": "fixture"})
    assert status["success"] is False and status["result"]["success"] is False


def test_same_second_jobs_keep_independent_input_and_completed_state(
    scripts, tmp_path, monkeypatch
):
    def spawn(argv, **kwargs):
        p = Path(argv[-1])
        job = json.loads(p.read_text())
        job.update(status="done", result={"items": [{"request": job["stdin"]}]})
        p.write_text(json.dumps(job))
        return SimpleNamespace(pid=123)

    monkeypatch.setattr(scripts.platform_utils, "spawn_detached", spawn)
    monkeypatch.setattr(scripts.time, "strftime", lambda *a: "same_second")
    results = [
        scripts._run_background("same", {}, tmp_path / "script.py", str(i), 300, sys.executable)
        for i in range(2)
    ]
    assert results[0]["job_id"] != results[1]["job_id"]
    jobs = [json.loads((scripts._JOB_DIR / (r["job_id"] + ".json")).read_text()) for r in results]
    assert [j["stdin"] for j in jobs] == ["0", "1"]
    assert all(j["status"] == "done" for j in jobs)
    assert results[0]["log"] != results[1]["log"]


@pytest.mark.parametrize("verb", ["dedup", "groupby"])
@pytest.mark.parametrize("rows", [[{"key": "A"}, "lost", {"key": "B"}], [1, 2, 3]])
def test_object_operations_refuse_silent_row_loss(verb, rows):
    mod = load("data-ops")
    result = mod.execute({"items": rows, "by": "key"}, SimpleNamespace(tool_name="data_" + verb))
    assert result["success"] is False and "객체" in result["error"]
    assert len(rows) == 3


def test_groupby_empty_table_keeps_schema_and_checks_aggregate():
    mod = load("data-ops")
    payload = {
        "table": {"columns": ["key", "v"], "rows": []},
        "by": "key",
        "agg": {"total": ["sum", "v"]},
    }
    out = mod.execute(payload, SimpleNamespace(tool_name="data_groupby"))
    assert out["success"] and out["table"] == {"columns": ["key", "total"], "rows": []}
    out = mod.execute(
        {**payload, "agg": {"total": ["sum", "missing"]}},
        SimpleNamespace(tool_name="data_groupby"),
    )
    assert out["success"] is False


@pytest.mark.parametrize("query", [{"title": "alpha"}, {"query": "alpha"}])
def test_book_search_preserves_page(query, monkeypatch):
    mod = load("books")
    import tool_library
    from xml.etree.ElementTree import fromstring

    requests = []

    def api(endpoint, params):
        requests.append(params)
        return fromstring("<response><numFound>0</numFound></response>")

    monkeypatch.setattr(tool_library, "call_library_api", api)
    out = mod._book_search({**query, "page": 3})
    assert requests[0]["pageNo"] == 3 and out["page"] == 3


@pytest.mark.parametrize(
    "html,ok",
    [
        ("<html>maintenance</html>", False),
        ("검색 결과 총 <em>0</em>건", True),
        ("검색 결과 총 <em>20</em>건", False),
    ],
)
def test_nl_does_not_claim_absence_on_parse_failure(html, ok, monkeypatch):
    mod = load("books", "tool_nl")
    monkeypatch.setattr(
        mod.requests,
        "get",
        lambda *a, **k: SimpleNamespace(text=html, raise_for_status=lambda: None),
    )
    out = mod.search_nl("alpha")
    assert out["success"] is ok
    assert (out.get("total") == 0) if ok else out.get("error")


@pytest.fixture
def notebook(tmp_path, monkeypatch):
    handler = load("notebook")
    import notebook_core as core

    monkeypatch.setattr(core, "NOTEBOOK_DIR", tmp_path / "notebook")
    monkeypatch.setattr(core, "DB_PATH", tmp_path / "notebook/test.db")
    monkeypatch.setattr(core, "_load_model", lambda: False)
    core.create_notebook("audit")
    return handler, core


def seed_notebook(core):
    conn = core._connect(with_vec=True)
    conn.execute(
        "INSERT INTO sources(id,notebook_id,title,kind) VALUES (1,1,'Other','text'),(2,1,'Target','text')"
    )
    for i in range(1, 22):
        sid = 1 if i <= 20 else 2
        text = "needle" if sid == 1 else "needle " + "filler " * 60
        conn.execute(
            "INSERT INTO chunks(id,notebook_id,source_id,seq,loc,text) VALUES (?,1,?,0,?,?)",
            (i, sid, "p.1", text),
        )
        conn.execute("INSERT INTO chunks_fts(rowid,text) VALUES (?,?)", (i, text))
    conn.commit()
    conn.close()


def test_notebook_source_scope_precedes_fts_limit(notebook):
    _, core = notebook
    seed_notebook(core)
    out = core.search_chunks("audit", "needle", top_k=1, source=2, alpha=0)
    assert out["results"][0]["source_id"] == 2
    assert (
        core.search_chunks("audit", "needle", top_k=1, source="absent", alpha=0)["results"] == []
    )


def test_notebook_source_scope_precedes_vector_limit(notebook, monkeypatch):
    pytest.importorskip("sqlite_vec")
    _, core = notebook
    seed_notebook(core)

    def vec(value):
        return struct.pack("f" * 768, *([value] * 768))

    c = core._connect(with_vec=True)
    for i in range(1, 22):
        c.execute(
            "INSERT INTO chunks_vec(rowid,embedding) VALUES (?,?)", (i, vec(0 if i <= 20 else 0.1))
        )
    c.commit()
    c.close()
    monkeypatch.setattr(core, "_embed_one", lambda q: vec(0))
    assert core._search_semantic(1, "needle", 1, source_ids=[2])[0][0] == 21
    assert core._search_semantic(999, "needle", 1) == []


@pytest.mark.parametrize(
    "answer,ok",
    [
        ("Answer [#2 p.1]", True),
        ("Answer [#2 p.999]", False),
        ("Answer [#999 p.1]", False),
        ("No citation", False),
        ("Answer [#2 p.1] and invented [#999 p.1]", False),
    ],
)
def test_notebook_verifies_real_citation_locations(notebook, monkeypatch, answer, ok):
    mod, core = notebook
    chunk = {"id": 1, "loc": "p.1", "text": "actual evidence"}
    monkeypatch.setattr(mod, "_source_chunks", lambda *a: [chunk])
    monkeypatch.setattr(mod, "_search_hints", lambda *a: [])
    monkeypatch.setattr(mod, "_select_sources", lambda *a: {"mode": "read", "sources": [2]})
    monkeypatch.setattr(mod, "_answer_from_docs", lambda *a: (answer, ""))
    m = {
        "notebook": "audit",
        "text": "#2 Target",
        "items": [{"id": 2, "title": "Target", "kind": "text", "char_count": 20}],
    }
    out = json.loads(mod._ask_by_cards(core, "audit", "question", m))
    assert out["success"] is ok
    if ok:
        assert out["citations"][0]["quote"] == "actual evidence"
    else:
        assert out["answer"] == "" and out["error"]


class Locator:
    def __init__(self, n=0):
        self.n = n

    async def count(self):
        return self.n

    async def wait_for(self, **kwargs):
        pass

    def and_(self, other):
        return Locator(min(self.n, other.n))


@pytest.mark.parametrize("input_mode,role", [(False, "button"), (True, "textbox")])
def test_browser_never_falls_back_to_another_element(input_mode, role):
    mod = load("browser-action", "browser_session")

    class Page:
        def locator(self, *a):
            return Locator(0)

        def get_by_role(self, role, **kwargs):
            assert kwargs.get("name") == "Cancel" and kwargs.get("exact") is True
            return Locator(0)

        def get_by_label(self, *a, **kw):
            return Locator(0)

        def get_by_placeholder(self, *a, **kw):
            return Locator(0)

    out = asyncio.run(
        mod._find_locator_once(
            Page(), {"role": role, "name": "Cancel", "selector": "#gone"}, input_mode
        )
    )
    assert out is None


@pytest.mark.parametrize("count", [1, 2])
def test_browser_named_candidate_must_be_unique(count):
    mod = load("browser-action", "browser_session")
    page = SimpleNamespace(get_by_role=lambda *a, **kw: Locator(count))
    out = asyncio.run(mod._find_locator_once(page, {"role": "button", "name": "Cancel"}))
    assert (out is not None) == (count == 1)


def test_host_cpu_uses_two_samples(monkeypatch):
    mod = load("pc-manager")
    import psutil

    calls = []

    class Process:
        info = {"pid": 1, "name": "fixture", "memory_percent": 2}

        def cpu_percent(self, interval):
            calls.append("sample")
            return 0 if len(calls) == 1 else 95

    monkeypatch.setattr(psutil, "process_iter", lambda attrs: [Process()])
    import time

    monkeypatch.setattr(time, "sleep", lambda t: calls.append("wait"))
    out = json.loads(mod._host_apps({}))
    assert calls == ["sample", "wait", "sample"]
    assert out["items"][0]["cpu_percent"] == 95


@pytest.mark.parametrize(
    "old,new", [("docs/old.md", "docs/new.md"), ("한 글/old\t.md", "한 글/new{a}.md")]
)
def test_body_rename_keeps_literal_paths(old, new, monkeypatch):
    mod = load("system_essentials", "body_ops")
    calls = []
    monkeypatch.setattr(mod, "_guard_root", lambda: ("/repo", None))

    def git(root, args):
        calls.append(args)
        if "--numstat" in args:
            assert "-z" in args
            return "1\t2\t\0" + old + "\0" + new + "\0", None
        assert args[-2:] == [old, new]
        return "rename from " + old + "\nrename to " + new, None

    monkeypatch.setattr(mod, "_git", git)
    out = mod.op_diff({})
    assert out["items"][0]["파일"] == new and out["items"][0]["이전경로"] == old
    assert out["items"][0]["diff"]


def test_memory_sync_commits_before_index_and_retries(tmp_path, monkeypatch):
    pytest.importorskip("sqlite_vec")
    load("memory", "memory_db")
    import memory_db as db
    import memory_tree as tree

    path = str(tmp_path / "memory.db")
    db._ensure_schema(path)

    def connection(path):
        import sqlite_vec

        c = sqlite3.connect(path, timeout=0.05)
        c.enable_load_extension(True)
        sqlite_vec.load(c)
        c.enable_load_extension(False)
        return c

    monkeypatch.setattr(db, "_get_vec_conn", connection)

    def embed(text):
        return struct.pack(
            "f" * db.EMBEDDING_DIM, *([0.2 if "new" in text else 0.1] * db.EMBEDDING_DIM)
        )

    monkeypatch.setattr(db, "_embed", embed)
    c = sqlite3.connect(path)
    c.execute(
        "INSERT INTO memories(id,category,content,node) VALUES (1,'기타','old fact','audit')"
    )
    c.commit()
    c.close()
    assert db._index_one(path, 1, "old fact")
    doc = Path(tree.refresh_node(path, "audit"))
    doc.write_text(doc.read_text().replace("old fact", "new fact"))
    os.utime(doc, (doc.stat().st_mtime + 5,) * 2)
    result = tree.sync_node(path, "audit")
    assert result["updated"] == 1 and result["index_pending"] == []
    c = connection(path)
    actual = c.execute("SELECT embedding FROM memories_vec WHERE rowid=1").fetchone()[0]
    c.close()
    assert actual == embed("new fact")
    doc.write_text(doc.read_text().replace("new fact", "new retry"))
    os.utime(doc, (doc.stat().st_mtime + 5,) * 2)
    original = db._index_one
    monkeypatch.setattr(db, "_index_one", lambda *a, **kw: False)
    assert tree.sync_node(path, "audit")["index_pending"] == [1]
    monkeypatch.setattr(db, "_index_one", original)
    assert tree.sync_node(path, "audit")["index_pending"] == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
