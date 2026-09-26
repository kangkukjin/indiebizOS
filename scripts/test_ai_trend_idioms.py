"""보고서 재조회 절약: 실제 실행기로 원문·빈값·부분 실패 보존을 검증한다."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401

import json
import pytest
from ibl_v2_adapters import Adapter, load_registry
from ibl_v2_compile import compile_program
from ibl_v2_ir import Fault
from ibl_v2_runtime import Runtime


def run(file, call, inputs=None, adapters=None):
    registry = load_registry()
    for name, fn in (adapters or {}).items():
        registry[name] = Adapter(registry[name].contract, fn)
    source = (ROOT / "data/idioms" / file).read_text() + "\n" + call
    plan = compile_program(source, registry, inputs or {})
    assert not plan.issues, plan.report()
    return Runtime(plan, inputs or {}).run()


def prepare(files, failure=None):
    seen = []

    def listing(rt, args):
        import fnmatch
        return [dict(name=name, path="/fixture/" + name, is_dir=False)
                for name in files if fnmatch.fnmatch(name, args["pattern"])]

    def read(rt, args):
        seen.append(args)
        if failure and args["path"].endswith(failure):
            raise Fault("TOOL", "읽기 권한 없음", kind="permission")
        return {"text": files[Path(args["path"]).name], "blocks": [], "data": {}}

    out = run("ai_trend_prepare.ibl", '[fn:AI동향준비읽기]{폴더:"/fixture"}',
              adapters={"self:list": listing, "self:read": read})
    return out, seen


def test_prepare_latest_full_text_and_absent_optional_files():
    full = "\n".join(f"line {n}" for n in range(250))
    out, seen = prepare({"ai_trend_report_2026-09-24.md": "old",
                         "ai_trend_report_2026-09-26.md": full,
                         "_methodology_rules.md": "rules"})
    assert out["success"], out
    value = out["value"]
    docs = {d["kind"]: d for d in value["documents"]}
    assert value["previous_found"] and docs["previous"]["text"] == full
    assert docs["coverage"]["found"] is False and docs["scan"]["found"] is False
    assert len(seen) == 2 and all("limit" not in a for a in seen)


def test_prepare_present_empty_file_differs_from_absence():
    out, _ = prepare({"_methodology_rules.md": "", "_scan_log.json": ""})
    assert out["success"], out
    assert out["value"]["previous_found"] is False
    docs = {d["kind"]: d for d in out["value"]["documents"]}
    assert docs["scan"]["found"] and docs["scan"]["text"] == ""
    assert not docs["coverage"]["found"]


@pytest.mark.parametrize("name", ["_methodology_rules.md", "_scan_log.json"])
def test_prepare_permission_is_not_empty_state(name):
    out, _ = prepare({"_methodology_rules.md": "rules", "_scan_log.json": "[]"}, name)
    assert out["success"] is False
    assert "읽기 권한 없음" in json.dumps(out, ensure_ascii=False)


def test_batch_keeps_sections_dates_and_failures_without_mirror_payload():
    seen = []
    article = {"title": "same", "url": "https://example.org/a", "summary": "원문 요약",
               "date": "2026-09-24", "pubDate": "2026-09-25", "opaque": "x" * 8000}

    def search(rt, args):
        seen.append(args)
        if args["query"] == "failure":
            raise Fault("TOOL", "원천 장애", kind="runtime")
        if args["query"] == "empty":
            return {"items": []}
        return {"items": [article], "results": [article], "text": "x" * 16000}

    queries = [dict(section=s, source="gnews", query=q)
               for s, q in [("투자", "a"), ("기술", "b"), ("사례", "empty"), ("기술", "failure")]]
    out = run("search_batch_view.ibl", '[fn:검색묶음추리기]{질의들:$queries,기간:7,개수:6}',
              {"queries": queries}, {"sense:search": search})
    assert out["success"], out
    v = out["value"]
    assert v["ok"] is False and v["failed"] == 1 and len(seen) == 4
    assert out["source_complete"] is False
    assert [r["section"] for r in v["items"]] == ["투자", "기술"]
    assert v["items"][0]["summary"] == article["summary"]
    assert v["items"][0]["dates"]["date"] != v["items"][0]["dates"]["pubDate"]
    assert v["queries"][2]["ok"] and v["queries"][2]["received"] == 0
    assert v["queries"][3]["error"]["message"] == "원천 장애"
    assert "opaque" not in json.dumps(v) and len(json.dumps(v)) < 3000
    assert all(a["days"] == 7 and a["limit"] == 6 for a in seen)


def test_batch_partial_source_keeps_partial_evidence():
    def search(rt, args):
        raise Fault("PARTIAL_SOURCE", "원천 누락", kind="partial",
                    partial={"items": [{"title": "partial", "url": "a"}]})

    out = run("search_batch_view.ibl", '[fn:검색묶음추리기]{질의들:[{source:"gnews",query:"q"}]}',
              adapters={"sense:search": search})
    assert out["success"], out
    value = out["value"]
    assert value["failed"] == 1 and value["items"] == []
    assert out["source_complete"] is False
    assert value["queries"][0]["error"]["partial"]["items"][0]["title"] == "partial"


def test_batch_empty_and_invalid_inputs_do_not_search():
    def unexpected(rt, args):
        pytest.fail("검색하면 안 되는 입력")

    out = run("search_batch_view.ibl", '[fn:검색묶음추리기]{질의들:[]}',
              adapters={"sense:search": unexpected})
    assert out["success"] and out["value"]["ok"] and out["value"]["items"] == []
    out = run("search_batch_view.ibl", '[fn:검색묶음추리기]{질의들:[{source:"gnews",query:"q"}],기간:0}',
              adapters={"sense:search": unexpected})
    assert out["success"] and not out["value"]["ok"]


def test_batch_marks_requested_selection_without_silently_dropping_rows():
    def search(rt, args):
        return {"items": [{"title": str(i), "url": str(i)} for i in range(4)]}

    out = run("search_batch_view.ibl", '[fn:검색묶음추리기]{질의들:[{source:"gnews",query:"q"}],개수:2}',
              adapters={"sense:search": search})
    assert out["success"], out
    assert len(out["value"]["items"]) == 2
    assert out["value"]["queries"][0]["received"] == 4
    assert out["value"]["queries"][0]["shown"] == 2


def test_seeds_are_current_and_not_always_on():
    seeds = json.loads((ROOT / "data/idioms/ai_trend_seeds.json").read_text())
    names = {"AI동향준비읽기": "ai_trend_prepare.ibl", "검색묶음추리기": "search_batch_view.ibl"}
    for seed in seeds:
        assert seed["always_on"] is False
        if seed.get("alias"):
            assert seed["ibl_code"] == (ROOT / "data/idioms" / names[seed["alias"]]).read_text().strip()


def test_guide_calls_compile_and_run_with_fixed_sources():
    import re
    seeds = json.loads((ROOT / "data/idioms/ai_trend_seeds.json").read_text())
    library = {s["alias"]: s["ibl_code"] for s in seeds if s.get("alias")}
    registry = load_registry()
    fixtures = {"self:list": lambda rt, a: [],
                "self:read": lambda rt, a: {"text": "rules", "blocks": [], "data": {}},
                "sense:search": lambda rt, a: {"items": [{"title": "fixture", "url": "fixture"}]}}
    for key, fn in fixtures.items():
        registry[key] = Adapter(registry[key].contract, fn)
    guide = (ROOT / "data/guides/ai_trend_report.md").read_text()
    blocks = re.findall(r"```ibl\n(.*?)```", guide, re.S)
    assert len(blocks) == 2
    for code in blocks:
        plan = compile_program(code, registry, definitions=library)
        assert not plan.issues, plan.report()
        out = Runtime(plan, {}).run()
        assert out["success"], out
        if "검색묶음추리기" in code:
            assert out["value"]["ok"] and len(out["value"]["queries"]) == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
