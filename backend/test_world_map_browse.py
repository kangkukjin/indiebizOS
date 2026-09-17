"""이름을 모르는 상태의 분야 탐색과 새 지식 입구의 도달·간섭 회귀."""
import json
import subprocess
import sys
from dataclasses import replace

import pytest
import boot_paths  # noqa: F401
import knowledge_catalog as catalog
from world_context import assemble
from test_knowledge_catalog import ROOT, world  # noqa: F401


def test_every_entry_reachable_by_browsing_without_names():
    snapshot = catalog.load_snapshot(ROOT)
    pending, found, visited = [{"op": "browse", "limit": 3}], set(), set()
    while pending:
        args = pending.pop()
        result = catalog.lookup(ROOT, **args)
        assert result["status"] in {"ok", "partial"}
        if result["next"]:
            pending.append(result["next"])
        for row in result["items"]:
            if row["item_type"] == "category":
                key = tuple(row["path"])
                assert key not in visited
                visited.add(key)
                assert row["entry_count"] == sum(e.path[:len(key)] == key for e in snapshot.entries)
                pending.append(dict(row["browse"], limit=3))
            else:
                assert row["id"] not in found
                found.add(row["id"])
    assert found == {e.id for e in snapshot.entries}


def test_browse_prefix_is_a_category_not_a_text_match():
    assert catalog.lookup(ROOT, op="browse", path=["인문학"])["status"] == "no_match"
    assert catalog.lookup(ROOT, op="browse", path=["인문", "역사와 고고학", "기록"])["total"] == 2
    for path in ("인문", [1], [""], ["x"] * 6):
        with pytest.raises(ValueError):
            catalog.lookup(ROOT, op="browse", path=path)
    for args in ({"op": "search", "path": ["인문"]}, {"op": "browse", "query": "인문"}):
        with pytest.raises(ValueError):
            catalog.lookup(ROOT, **args)


def test_browse_pages_do_not_mix_revisions(world):
    first = catalog.lookup(world, op="browse", path=["인문"], limit=1)
    path = world / catalog.CATALOG_PATH
    path.write_text(path.read_text() + "\n# changed\n")
    assert catalog.lookup(world, **first["next"])["status"] == "stale_revision"
    assert catalog.lookup(world, **first["items"][0]["browse"])["status"] == "stale_revision"


def test_exact_category_fallback_does_not_expand_ordinary_sentences():
    s = catalog.load_snapshot(ROOT)
    # 임의의 새 분류도 동작해야 한다. 세계의 명사를 코드에 넣지 않는다.
    entry = replace(s.entries[0], path=("새분류",), name="XYZ", hint="abc def", aliases=())
    s = replace(s, entries=(entry,))
    rows, mode = catalog.search(ROOT, s, "새분류")
    assert mode == "category_exact" and rows[0][0].id == entry.id
    assert catalog.search(ROOT, s, "새분류 이야기만 듣고 싶지는 않아")[0] == []


@pytest.mark.parametrize("query,expected", [
    ("가족의 역사를 인터뷰해서 남겨 두고 싶어", {"oral_history"}),
    ("옛 기록을 읽을 때 작성자의 의도를 어떻게 살피지", {"primary_source_analysis"}),
    ("이미 쓴 돈이 아까워서 프로젝트를 계속하고 있어", {"sunk_cost"}),
    ("직접 하는 일과 분업의 이점을 비교해보자", {"comparative_advantage"}),
    ("몇 개 팔아야 가게 운영비를 충당할지 계산해줘", {"break_even"}),
    ("팔릴지 먼저 알아보고 나서 만들고 싶어", {"market_research"}),
    ("협상 결렬 때 내가 할 수 있는 일을 정리하자", {"batna"}),
    ("두 포장재의 제조부터 폐기까지 영향을 비교해줘", {"life_cycle_assessment"}),
    ("건강 연구 종합 자료에서 근거를 찾아보자", {"cochrane"}),
    ("의학 검색어를 분야별로 찾고 싶다", {"mesh"}),
    ("그 표현의 실제 쓰임을 여러 책에서 비교하자", {"kwic", "antconc"}),
    ("학교 반경 안에 어떤 시설이 있는지 살펴보자", {"spatial_buffer", "qgis"}),
    ("행정구역별로 시설을 묶어보자", {"spatial_join", "qgis"}),
    ("장면 순서를 그림으로 먼저 보여주자", {"storyboard"}),
    ("풀이 과정을 읽고 왜 그런지 설명하며 공부하자", {"worked_examples"}),
    ("쓴 글의 논리 흐름을 점검해줘", {"reverse_outline"}),
    ("소설 분석을 문장 표현에 근거해서 해보자", {"close_reading"}),
    ("재고의 유입과 유출을 구분하자", {"stock_flow"}),
    ("반복되는 악순환을 모형으로 표현하고 싶어", {"system_dynamics"}),
    ("키보드만으로 사이트를 쓸 수 있는지 보자", {"accessibility"}),
])
def test_knowledge_bridges_reach_context(query, expected):
    s = catalog.load_snapshot(ROOT)
    candidates, _ = catalog.search(ROOT, s, query)
    context, _ = assemble(s, candidates)
    assert expected <= {n["id"] for n in context["nodes"]}


@pytest.mark.parametrize("query", ["안녕", "정말 고마워", "응 그렇게 해", "방금 말은 취소할게"])
def test_new_vocabulary_does_not_fill_unrelated_turns(query):
    s = catalog.load_snapshot(ROOT)
    assert not catalog.search(ROOT, s, query)[0]


def test_script_browse_and_no_match_recovery():
    p = subprocess.run([sys.executable, str(ROOT / "data/scripts/world_map_lookup.py")],
                       input=json.dumps({"op": "browse", "path": ["사회", "협상"]}),
                       text=True, capture_output=True, check=True, timeout=10)
    result = json.loads(p.stdout)
    assert {r["id"] for r in result["items"]} == {"batna", "integrative_negotiation", "zopa"}   # 2026-09-18 트리 정비: 경제/선택은 경제/분석으로 합쳐졌다
    empty = catalog.lookup(ROOT, query="nonexistent-vocabulary")
    assert empty["status"] == "no_match"
    assert catalog.lookup(ROOT, **empty["browse"])["items"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
