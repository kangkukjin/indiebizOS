"""주소별 발췌의 원문 위치·선택·실패 보존을 실제 IBL 실행기로 확인한다."""
import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

from ibl_v2_adapters import Adapted, decode_envelope, load_registry
from ibl_v2_compile import compile_program
from ibl_v2_ir import Fault
from ibl_v2_runtime import Runtime
from test_function_support import current_source

ROOT = Path(__file__).resolve().parents[1]
BODY = (ROOT / "data/idioms/url_extract.ibl").read_text()
spec = importlib.util.spec_from_file_location(
    "url_extract_collection", ROOT / "data/scripts/collection_idioms.py")
collection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collection)


def execute(targets, pages, suffix="", options=""):
    seen = []

    def crawl(runtime, args):
        seen.append(args["url"])
        page = pages[args["url"]]
        if isinstance(page, Exception):
            raise page
        value, evidence = decode_envelope(page, registry["sense:crawl"].contract["adapter"], args)
        return Adapted(value, evidence)

    def script(runtime, args):
        assert args["id"] == "수집관용구"
        value, evidence = decode_envelope(collection.run(args["args"]), {"value_path": ""})
        return Adapted(value, evidence)

    registry = load_registry()
    for key, fn in [("sense:crawl", crawl), ("self:script", script)]:
        registry[key] = replace(registry[key], run=fn)
    source = current_source("본문에서찾기") + "\n" + BODY.split("\n", 1)[1]
    source += '\n$r = [fn:주소별발췌]{대상:$targets' + options + '}\n' + (suffix or '$r')
    plan = compile_program(source, registry, {"targets": targets})
    assert not plan.issues, plan.report()
    return Runtime(plan, {"targets": targets}).run(), seen


def page(url, lines, **metadata):
    return {"url": url, "title": "원문", "text": "\n".join(lines),
            "items": [{"url": url, "text": text, "paragraph_index": i,
                       "title": "원문", "version_ref": "fixture-v1"}
                      for i, text in enumerate(lines)], **metadata}


def test_per_address_conditions_preserve_locations_and_selection():
    out, seen = execute(
        [{"url": "a", "pattern": "price", "limit": 1},
         {"url": "b", "pattern": "license", "context": 1}],
        {"a": page("a-final", ["price 10", "other", "price 20"]),
         "b": page("b", ["before", "license", "after"])})
    assert out["success"], out
    value = out["value"]
    assert value["ok"] and value["error_count"] == 0, [
        s["error"]["message"] for s in value["sources"] if s["error"]]
    assert sorted(seen) == ["a", "b"]
    assert [r["text"] for r in value["items"]] == ["price 10", "before", "license", "after"]
    first = value["items"][0]
    assert (first["requested_url"], first["url"], first["paragraph_index"]) == ("a", "a-final", 0)
    assert first["version_ref"] == "fixture-v1"
    assert value["sources"][0]["match_info"]["omitted_matches"] == 1
    assert any(m["scope"] == "selection" for m in value["truncations"])


def test_same_url_different_patterns_and_pipe_to_consumer():
    out, seen = execute(
        [{"url": "a", "pattern": "price"}, {"url": "a", "pattern": "license"}],
        {"a": page("a", ["price", "license"])},
        '$r.items >> [table:select]{columns:["request_index","text"]}')
    assert out["success"], out
    assert out["value"] == [{"request_index": 0, "text": "price"},
                            {"request_index": 1, "text": "license"}]
    assert seen == ["a", "a"]


def test_no_match_is_distinct_from_failed_source_with_partial_evidence():
    error = Fault("PARTIAL_SOURCE", "원문 일부 누락", kind="partial",
                  partial={"items": [{"url": "bad", "text": "남아 있는 원문"}]})
    out, _ = execute(
        [{"url": "good", "pattern": "price"},
         {"url": "empty", "pattern": "price"},
         {"url": "bad", "pattern": "price"}],
        {"good": page("good", ["price 10"]), "empty": page("empty", ["other"]),
         "bad": error})
    assert out["success"] and not out["source_complete"], out
    value = out["value"]
    assert not value["ok"] and value["partial"] and value["error_count"] == 1
    assert value["sources"][1]["ok"] and value["sources"][1]["match_info"]["total_matches"] == 0
    assert value["sources"][2]["error"]["partial"]["items"][0]["text"] == "남아 있는 원문"
    assert value["items"][0]["text"] == "price 10"
    assert value["items"][1]["requested_url"] == "bad" and value["items"][1]["_error"]


def test_empty_targets_do_not_crawl():
    out, seen = execute([], {})
    assert out["success"] and out["value"]["ok"] and not seen
    assert out["value"]["items"] == [] and out["value"]["sources"] == []


@pytest.mark.parametrize("entry", [
    {"url": "a", "pattern": "["},
    {"url": "a", "pattern": "x", "context": -1},
    {"url": "a", "pattern": "x", "limit": 1.5},
])
def test_invalid_pattern_and_selection_are_not_empty_success(entry):
    out, _ = execute([entry], {"a": page("a", [])})
    assert out["success"] and not out["value"]["ok"], out
    assert out["value"]["error_count"] == 1
    assert out["value"]["sources"][0]["error"]


def test_source_truncation_survives_extraction():
    source = page("a", ["price"], truncated=True,
                  truncations=[{"scope": "source", "reason": "fixture truncation"}])
    out, _ = execute([{"url": "a", "pattern": "price"}], {"a": source})
    assert not out["source_complete"], out
    assert "fixture truncation" in json.dumps(out, ensure_ascii=False)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
