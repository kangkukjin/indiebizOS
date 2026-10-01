"""4202: administrative scope, location failures, and expression repair hints."""
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest

from test_episode_audit_2026_09_09 import _package_module


@pytest.mark.parametrize("query", ["천안시 동남구", "충남 천안시 동남구", "천안 동남구"])
@pytest.mark.parametrize("separator", [" ", ","])
def test_region_selects_requested_scope_instead_of_descendants(monkeypatch, query, separator):
    naver = _package_module("tool_naver.py")
    regions = [
        {"cortarNo": "4413110200", "cortarName": "충청남도 천안시 동남구 봉명동"},
        {"cortarNo": "4413100000", "cortarName": "충청남도 천안시 동남구"},
        {"cortarNo": "4413110300", "cortarName": "충청남도 천안시 동남구 신방동"},
    ]
    for row in regions:
        row["cortarName"] = row["cortarName"].replace(" ", separator)
    monkeypatch.setattr(naver, "_api_get", lambda *a: {"regions": regions})
    assert naver._resolve_keyword(query)["cortarNo"] == "4413100000"


@pytest.mark.parametrize("regions,query", [
    ([{"cortarNo": "1", "cortarName": "충청남도 천안시 동남구 봉명동"}], "천안시 동남구"),
    ([{"cortarNo": "1", "cortarName": "대전광역시 중구"},
      {"cortarNo": "2", "cortarName": "서울특별시 중구"}], "중구"),
    ([{"cortarNo": "1", "cortarName": "충청남도 천안시 동남구"}], "충북 천안시 동남구"),
])
def test_region_never_guesses_a_child_or_ambiguous_parent(monkeypatch, regions, query):
    naver = _package_module("tool_naver.py")
    monkeypatch.setattr(naver, "_api_get", lambda *a: {"regions": regions})
    with pytest.raises(ValueError, match="검색 후보"):
        naver._resolve_keyword(query)


def test_region_province_alias_selects_parent_without_neighborhood_bias(monkeypatch):
    naver = _package_module("tool_naver.py")
    monkeypatch.setattr(naver, "_api_get", lambda *a: {"regions": [
        {"cortarNo": "1", "cortarName": "전북특별자치도 전주시"},
        {"cortarNo": "2", "cortarName": "전북특별자치도"},
    ]})
    assert naver._resolve_keyword("전북")["cortarNo"] == "2"


@pytest.fixture
def commercial(monkeypatch):
    handler = _package_module("handler.py")
    calls = []

    def search(**kwargs):
        calls.append(kwargs)
        return {"success": True, "data": [{"name": "상점"}], "count": 1}

    monkeypatch.setattr(handler, "load_module", lambda _: SimpleNamespace(
        search_commercial_district=search))
    return handler, calls, SimpleNamespace(tool_name="search_commercial_district")


@pytest.mark.parametrize("key", ["query", "area", "region"])
def test_unresolved_place_is_not_reported_as_missing_coordinates(commercial, monkeypatch, key):
    handler, calls, context = commercial
    monkeypatch.setattr(handler, "_geocode_query_to_latlng", lambda _: None)
    result = handler.execute({key: "천안 청수동 법원"}, context)
    assert result["success"] is False and not calls
    assert result["error_type"] == "location_unresolved"
    assert result["query"] == "천안 청수동 법원"
    assert "해소하지 못했습니다" in result["error"]
    assert "sense:place" in result["hint"]


def test_resolved_place_keeps_coordinates_and_items(commercial, monkeypatch):
    handler, calls, context = commercial
    monkeypatch.setattr(handler, "_geocode_query_to_latlng", lambda _: {
        "lat": 36.7, "lng": 127.1, "matched": "확인된 주소"})
    result = handler.execute({"query": "장소", "radius": 1000}, context)
    assert result["success"] and result["items"][0]["title"] == "상점"
    assert result["조회지역"] == "확인된 주소"
    assert (calls[0]["lat"], calls[0]["lng"], calls[0]["radius"]) == (36.7, 127.1, 1000)


@pytest.mark.parametrize("location", [{"lat": 0, "lng": 0}, {"region_code": "44131"}])
def test_explicit_location_bypasses_failed_query(commercial, monkeypatch, location):
    handler, calls, context = commercial
    monkeypatch.setattr(handler, "_geocode_query_to_latlng",
                        lambda _: pytest.fail("explicit coordinates/code must not geocode"))
    result = handler.execute({**location, "query": "찾을 수 없는 장소"}, context)
    assert result["success"] and len(calls) == 1
    assert all(calls[0][key] == value for key, value in location.items())


@pytest.mark.parametrize("code,hint", [
    ('return contains(["식료품 소매","의원"],"의원")', "$찾는값 in $목록"),
    ('return join(["가","나"],", ")', 'join(구분자, 문자열목록)'),
])
def test_type_error_provides_existing_expression_repair(code, hint):
    from ibl_v2_compile import compile_program
    plan = compile_program(code)
    assert plan.issues
    assert any(hint in issue.get("hint", "") for issue in plan.issues)


def test_suggested_repairs_compose_filter_aggregate_and_text():
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    code = '''
    $분류=["식료품 소매","의원"]
    $선택=filter([{업종:"의원",금액:3},{업종:"법무",금액:9},
                  {업종:"식료품 소매",금액:5}],($행)=>$행.업종 in $분류)
    return {합계:reduce($선택,0,($합,$행)=>$합+$행.금액),
            표시:join(", ",map($선택,($행)=>$행.업종))}
    '''
    plan = compile_program(code)
    assert not plan.issues
    result = Runtime(plan).run()
    assert result["success"] and result["value"] == {"합계": 8, "표시": "의원, 식료품 소매"}


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
