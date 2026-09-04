"""언어 개정 3건 회귀 (2026-09-04, 사용자 판정 "제안된 언어개정을 실행") — 관용구 리허설·되돌려 묻기가 적발한 마찰.

  L1  따옴표 밖 `${이름}` 은 `$이름` 과 같은 변수 참조로 파싱된다(수치 자리 포함). 치환도 같다.
  L2  산문 결과(문자열 통화)에 `.message`·`.text` 를 물으면 그 산문이다. 다른 경로는 종전대로 정직 오류.
  L3  [sense:search_youtube]{queries} 배치 팬아웃 — 검색어마다 query 태그, video_id 중복 제거, sections.

실행: .venv/bin/python -m pytest backend/test_lang_revision_2026_09_04.py -q
"""
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND)
import boot_paths  # noqa: E402,F401


def test_l1_unquoted_braced_variable_parses_like_bare():
    from ibl_parser import parse
    from ibl_param_vocab import code_syntax_error
    for code in ('[table:take]{n: ${개수}}', '[sense:place]{query: "x", lat: ${위도}, lng: $경도, limit: ${개수}}',
                 '$n = 3\n[table:take]{n: ${n}}'):
        assert code_syntax_error(code) is None, code
    st = parse('[table:take]{n: ${개수}, m: $개수}')
    steps = st if isinstance(st, list) else st.get("steps") or [st]
    params = next(s for s in _walk(steps) if s.get("action") == "take")["params"]
    assert params["n"] == "${개수}" and params["m"] == "$개수"
    # 할당된 변수는 두 표기가 같은 참조 — 파서가 같은 step 자리표로 치환한다
    a = parse('$x = [self:time]\n[table:take]{n: $x}')
    b = parse('$x = [self:time]\n[table:take]{n: ${x}}')
    pa = next(s for s in _walk(a) if s.get("action") == "take")["params"]["n"]
    pb = next(s for s in _walk(b) if s.get("action") == "take")["params"]["n"]
    assert pa == pb and "{{_step_" in str(pa)


def _walk(obj):
    if isinstance(obj, dict):
        if "action" in obj:
            yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def test_l2_prose_result_message_and_text():
    from workflow_binding import _extract_result_field_obj, _extract_result_field
    prose = "불릿 셋으로 요약한 산문이다."
    assert _extract_result_field_obj(prose, "message") == prose
    assert _extract_result_field_obj(prose, "text") == prose
    assert _extract_result_field_obj(prose, "message?") == prose
    assert _extract_result_field(prose, "message") == prose
    with pytest.raises(ValueError):
        _extract_result_field_obj(prose, "count")          # 산문에 다른 경로는 종전대로 정직 오류
    assert _extract_result_field_obj('{"message": "봉투 산문", "count": 1}', "message") == "봉투 산문"


def test_l3_search_youtube_queries_fanout():
    import importlib.util
    p = os.path.join(BACKEND, "..", "data", "packages", "installed", "tools", "youtube", "handler.py")
    spec = importlib.util.spec_from_file_location("yt_handler", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    class FakeYT:
        def search_youtube(self, query, count=5):
            base = {"a": [("v1", "A1"), ("v2", "A2")], "b": [("v2", "B2"), ("v3", "B3")]}[query]
            return {"success": True, "results": [{"video_id": v, "title": t} for v, t in base][:count]}
    out = mod._direct_search({"queries": ["a", "b"], "count": 5}, FakeYT())
    assert out["success"] and out["queries"] == ["a", "b"] and out["count"] == 3
    assert [i["video_id"] for i in out["items"]] == ["v1", "v2", "v3"]          # v2 는 한 번만(먼저 온 a 태그)
    assert [i["query"] for i in out["items"]] == ["a", "a", "b"]
    assert out["sections"] == [{"query": "a", "count": 2}, {"query": "b", "count": 1}]
    out = mod._direct_search({"queries": "a, b"}, FakeYT())
    assert out["count"] == 3                                                   # 쉼표 문자열도 같은 뜻
    single = mod._direct_search({"query": "a"}, FakeYT())
    assert [i["video_id"] for i in single["items"]] == ["v1", "v2"] and "queries" not in single


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
