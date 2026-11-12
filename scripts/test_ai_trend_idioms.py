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
    out = run("search_batch_view.ibl", '[fn:검색묶음추리기]{질의들:[{source:"gnews",query:"q"}],기간:-1}',
              adapters={"sense:search": unexpected})
    assert out["success"] and not out["value"]["ok"]


def test_period_is_optional_and_a_query_can_override_it():
    """게시일이 없는 출처는 days를 받지 못한다(2026-11-12 라이브: ddg 거절). 0·생략은 제한 없음이다."""
    seen = []

    def search(rt, args):
        seen.append(dict(args))
        return {"items": [{"title": "t", "url": "u"}]}

    queries = [dict(source="ddg", query="a"), dict(source="gnews", query="b", days=3)]
    for call in ('[fn:검색묶음추리기]{질의들:$queries}', '[fn:검색묶음추리기]{질의들:$queries,기간:0}'):
        seen.clear()
        out = run("search_batch_view.ibl", call, {"queries": queries}, {"sense:search": search})
        assert out["success"] and out["value"]["ok"], out
        by = {a["query"]: a for a in seen}
        assert "days" not in by["a"] and by["b"]["days"] == 3
    seen.clear()
    out = run("search_batch_view.ibl", '[fn:검색묶음추리기]{질의들:$queries,기간:7}', {"queries": queries}, {"sense:search": search})
    by = {a["query"]: a for a in seen}
    assert by["a"]["days"] == 7 and by["b"]["days"] == 3


def test_batch_marks_requested_selection_without_silently_dropping_rows():
    def search(rt, args):
        return {"items": [{"title": str(i), "url": str(i)} for i in range(4)]}

    out = run("search_batch_view.ibl", '[fn:검색묶음추리기]{질의들:[{source:"gnews",query:"q"}],개수:2}',
              adapters={"sense:search": search})
    assert out["success"], out
    assert len(out["value"]["items"]) == 2
    assert out["value"]["queries"][0]["received"] == 4
    assert out["value"]["queries"][0]["shown"] == 2


def test_batch_forwards_optional_type_and_sort_only_when_given():
    """질의의 type·sort 를 검색에 넘긴다 — 빠지면 네이버가 웹 문서(날짜 없는 위키)를 돌려준다(10-01 실측)."""
    seen = {}

    def search(rt, args):
        seen[args["query"]] = dict(args)
        return {"items": [{"title": "t", "url": "u"}]}

    queries = [dict(section="한국", source="naver", query="뉴스", type="news", sort="date"),
               dict(section="한국", source="naver", query="종류만", type="news"),
               dict(section="기술", source="gnews", query="없음"),
               dict(section="한국", source="naver", query="틀림", type=7)]
    out = run("search_batch_view.ibl", '[fn:검색묶음추리기]{질의들:$queries,기간:3,개수:2}',
              {"queries": queries}, {"sense:search": search})
    assert out["success"], out
    assert seen["뉴스"]["type"] == "news" and seen["뉴스"]["sort"] == "date"
    assert seen["종류만"]["type"] == "news" and "sort" not in seen["종류만"]
    assert "type" not in seen["없음"] and "sort" not in seen["없음"]
    assert "틀림" not in seen and out["value"]["failed"] == 1
    assert out["value"]["queries"][3]["error"]["code"] == "TYPE_CONTRACT"


def _seed_code(seed):
    """정의 본문은 .ibl 파일이 단일 원천이다. source_file 시드는 본문을 복제해 들지 않는다."""
    if seed.get("source_file"):
        return (ROOT / "data/idioms" / seed["source_file"]).read_text().strip()
    return seed["ibl_code"]


def test_seeds_are_current_and_only_the_search_batch_is_always_on():
    """검색묶음추리기는 2026-11-12 상시 소개로 올렸다. 재등록이 그 선택을 되돌리지 않게 시드가 같은 값을 든다."""
    seeds = json.loads((ROOT / "data/idioms/ai_trend_seeds.json").read_text())
    names = {"AI동향준비읽기": "ai_trend_prepare.ibl", "검색묶음추리기": "search_batch_view.ibl"}
    for seed in seeds:
        assert seed["always_on"] is (seed.get("alias") == "검색묶음추리기")
        if seed.get("alias"):
            assert _seed_code(seed) == (ROOT / "data/idioms" / names[seed["alias"]]).read_text().strip()
            assert seed.get("source_file", names[seed["alias"]]) == names[seed["alias"]]


def test_guide_introduces_idioms_with_their_real_parameters():
    """가이드는 완성 문장 없이 `이름{인자}`로 관용구를 소개한다. 그 이름과 인자가 실제 정의와 같아야 한다.

    옛 검사는 가이드의 ibl 코드 블록 셋을 컴파일·실행했다. 2026-11-06에 그 블록들이 가이드에서
    빠진 뒤로는 소개와 정의의 어긋남을 여기서 잡는다. 개별 관용구의 실행은 위의 검사들이 맡는다.
    """
    import re
    guide = (ROOT / "data/guides/ai_trend_report.md").read_text()
    introduced = re.findall(r"`([가-힣A-Za-z0-9_]+)\{([^}`]*)\}`", guide)
    assert introduced, "가이드가 이름{인자}로 소개한 관용구가 없습니다"
    defined = {}
    for path in sorted((ROOT / "data/idioms").iterdir()):
        if path.suffix in (".ibl", ".json"):
            for name, params in re.findall(r"\[def:([^\]]+)\]\(([^)]*)\)", path.read_text()):
                names = {p.split("=")[0].strip().lstrip("$") for p in params.split(",") if p.strip()}
                defined.setdefault(name, []).append((path.name, names))
    for name, args in introduced:
        assert name in defined, f"가이드가 소개한 관용구의 정의가 없습니다: {name}"
        wanted = {a.strip() for a in args.split(",") if a.strip()}
        for file, names in defined[name]:
            # 호출은 이름 붙인 인자를 쓰므로 순서는 보지 않는다.
            assert names == wanted, f"{name}: 가이드 {sorted(wanted)} / {file} {sorted(names)}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
