"""실제 검색 관용구의 결과를 투영해도 날짜 충돌과 누락을 보존한다."""
from pathlib import Path

import boot_paths  # noqa: F401
import pytest
from ibl_v2_adapters import Adapter, load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]


def test_search_projection_preserves_conflicting_and_missing_dates():
    # Keep the consumer composition here; load the real idiom definition below.
    code = '''
$검색=[fn:검색묶음추리기]{질의들:[{section:"투자",source:"gnews",query:"AI funding investment"},{section:"기술",source:"naver",type:"news",query:"AI 에이전트 연구"}],기간:7,개수:6}
$후보=$검색.items >> [table:select]{columns:["section","title","dates","url"]}
return {ok:$검색.ok,items:$후보,queries:$검색.queries,failed:$검색.failed}
'''
    definition = (ROOT / "data/idioms/search_batch_view.ibl").read_text()
    articles = [
        {"title": "conflict", "url": "https://example.com/a",
         "date": "2026-10-08", "pubDate": "2026-10-07"},
        {"title": "unknown", "url": "https://example.com/b"},
    ]
    registry = load_registry()
    registry["sense:search"] = Adapter(
        registry["sense:search"].contract, lambda rt, args: {"items": articles})
    plan = compile_program(definition + "\n" + code, registry, {})
    assert not plan.issues, plan.report()
    result = Runtime(plan, {}).run()
    assert result["success"], result
    value = result["value"]
    assert value["ok"] and value["failed"] == 0 and len(value["queries"]) == 2
    assert len(value["items"]) == 4
    for row in value["items"]:
        assert "date" not in row
        assert row["dates"] == ({"date": "2026-10-08", "pubDate": "2026-10-07",
                                 "published_at": None, "published": None}
                                if row["title"] == "conflict" else
                                dict.fromkeys(["date", "pubDate", "published_at", "published"]))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
