"""노출된 실제 본문을 현재 판본으로 호출한다. 웹·판정만 대역, 원장은 격리한다."""
import json
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

from test_ibl_v2_assets import memory  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "data/idioms/curated.json").read_text())["idioms"]
NAMES = ("주소마다읽기", "관련자료골라읽기", "의미로본문찾기", "좁혀서읽기")


@pytest.fixture
def call(memory, monkeypatch, tmp_path):
    import ibl_engine
    from ibl_v2_entry import handle_request
    for entry in CATALOG:
        if entry["name"] in NAMES:
            assert memory.add_examples_batch([{
                "intent": entry["when"], "ibl_code": entry["body"],
                "alias": entry["name"], "category": "phrase"}]) == 1
    calls = {"judge": 0, "crawl": []}
    original = ibl_engine._execute_ibl_impl

    def leaf(ti, project, agent_id=None):
        node, action, params = ti.get("_node"), ti.get("action"), ti.get("params") or {}
        if node == "table" and action == "judge":
            calls["judge"] += 1
            rows = params["items"]
            rows = json.loads(rows) if isinstance(rows, str) else rows
            rows = rows["items"] if isinstance(rows, dict) else rows
            return {"success": True, "items": [dict(row, judgment_result_value=True,
                    judgment_result_status="decided") for row in rows], "api_calls": 1}
        if node == "sense" and action == "crawl":
            calls["crawl"].append(params["url"])
            if params["url"].endswith("/bad"):
                return {"success": False, "error": "수집 실패"}
            return {"success": True, "items": [{"text": "본문", "url": params["url"]}]}
        return original(ti, project, agent_id)

    monkeypatch.setattr(ibl_engine, "_execute_ibl_impl", leaf)

    def execute(name, params, downstream=False):
        code = "[fn:" + name + "]{" + ",".join(k + ":$" + k for k in params) + "}"
        if downstream:
            code = "$r=" + code + "\nreturn $r.items"
        return handle_request({"edition": 2, "code": code, "inputs": params}, str(tmp_path))
    execute.calls = calls
    return execute


def params(name, rows, count):
    result = {"목록": rows, "개수": count}
    if name != "주소마다읽기":
        result["질문"] = "핵심"
    if name == "의미로본문찾기":
        result["문맥"] = 0
    return result


ROWS = [{"url": "https://fixture.test/A", "title": "A", "text": "핵심"},
        {"url": "https://fixture.test/a", "title": "a", "text": "핵심"}]


@pytest.mark.parametrize("name", NAMES[:3])
@pytest.mark.parametrize("count", [0, 1, 2])
def test_deliberate_selection_and_zero_pass_current_boundary(call, name, count):
    out = call(name, params(name, ROWS, count), downstream=True)
    assert out["success"] and out["source_complete"], out.get("error")
    assert len(out["value"]) == count
    if count == 0:
        assert call.calls == {"judge": 0, "crawl": []}


@pytest.mark.parametrize("name", NAMES[:2])
def test_distinct_url_spelling_survives_but_exact_duplicate_is_fetched_once(call, name):
    rows = ROWS + [ROWS[0], {"url": "https://fixture.test/a?x=A", "title": "query"},
                  {"url": "https://fixture.test/a?x=a", "title": "query"}]
    out = call(name, params(name, rows, 10))
    assert out["success"], out.get("error")
    assert set(call.calls["crawl"]) == {row["url"] for row in rows}
    assert len(call.calls["crawl"]) == 4


@pytest.mark.parametrize("name", NAMES[:3])
@pytest.mark.parametrize("count", [0, 1])
def test_duplicate_and_beyond_limit_source_errors_are_retained(call, name, count):
    from ibl_v2_ir import unpack
    failures = [{"url": ROWS[0]["url"], "_error": "중복 주소 실패"},
                {"url": "https://fixture.test/unread", "_error": "상한 밖 실패"}]
    out = call(name, params(name, ROWS + failures, count))
    assert not out["success"] and not out["source_complete"]
    assert out["diagnostic"]["code"] == "PARTIAL_SOURCE", out.get("error")
    partial = unpack(out["partial_wire"]["data"])
    assert [r for r in partial["items"] if r.get("_error")] == failures
    assert "https://fixture.test/unread" not in call.calls["crawl"]


@pytest.mark.parametrize("name", NAMES[:3])
def test_selection_cannot_hide_preexisting_source_truncation(call, name):
    source = {"items": ROWS, "truncated": True}
    out = call(name, params(name, source, 1))
    assert not out["success"] and not out["source_complete"]
    assert out["diagnostic"]["code"] == "PARTIAL_SOURCE"


def test_real_crawl_failure_is_not_a_successful_selection(call):
    out = call("주소마다읽기", params("주소마다읽기", [{"url": "https://fixture.test/bad"}], 1))
    assert not out["success"] and not out["source_complete"]


@pytest.mark.parametrize("pattern", ["TODO", "할일"])
def test_narrow_read_can_sample_many_matches_in_both_search_paths(call, tmp_path, pattern):
    (tmp_path / "sample.py").write_text((pattern + "\n") * 8)
    out = call("좁혀서읽기", {"패턴": pattern, "루트": "sample.py", "파일패턴": "*.py"})
    assert out["success"] and out["source_complete"], out.get("error")
    assert len(out["value"]["items"]) == 3


def test_narrow_read_does_not_hide_clipped_source_line(call, tmp_path):
    (tmp_path / "sample.py").write_text("TODO " + "a" * 600)
    out = call("좁혀서읽기", {"패턴": "TODO", "루트": "sample.py", "파일패턴": "*.py"})
    assert not out["success"] and not out["source_complete"]


@pytest.mark.parametrize("row_count,size_cap", [(0, False), (2, False), (6, True)])
def test_grep_resource_stop_is_never_relabelled_as_selection(tmp_path, monkeypatch, row_count, size_cap):
    from test_grep_glob_dialect import _load_fs_grep
    grep = _load_fs_grep()
    path = tmp_path / "sample.py"
    path.write_text("TODO\n" * 8)
    monkeypatch.setattr(grep, "_RG_BIN", None)
    monkeypatch.setattr(grep, "_py_grep", lambda *a: (
        [(str(path), i + 1, "TODO") for i in range(row_count)], True, size_cap, None))
    out = json.loads(grep.run({"pattern": "TODO", "path": str(path), "limit": 6}, str(tmp_path)))
    assert out["truncated"] and not out["total_complete"]
    assert out["truncations"][0]["scope"] == "source"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
