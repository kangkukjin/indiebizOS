"""Legal source normalization preserves bodies, provenance and date meanings."""
import boot_paths  # noqa: F401

import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
ENGLISH = {"Law": {
    "InfSection": {"lsNmEng": "TEST ACT", "lsId": "001248", "ancYd": "20251001"},
    "JoSection": {"Jo": [
        {"joYn": "N", "joCts": "CHAPTER I GENERAL PROVISIONS"},
        {"joYn": "Y", "joNo": "0003", "joBrNo": "00", "joTtl": "Effect",
         "joCts": "Article 3 (Effect)<br/>An exact body & its exceptions."},
        {"joYn": "Y", "joNo": "0006", "joBrNo": "03", "joTtl": "Renewal",
         "joCts": ["Article 6-3 (Renewal)", "(1) A rule.", "(2) Its exception."]}]},
    "ArSection": {"Ar": {"arCts": "ADDENDA: takes effect later.",
                         "arAncYd": "20251001", "arAncNo": "21065"}},
    "BylSection": ""}}


@pytest.fixture
def legal(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "legal_handler_test", ROOT / "data/packages/installed/tools/legal/handler.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "get_api_key", lambda *a, **k: "fixture-private-oc")
    return module


def run_detail(legal, monkeypatch, data, target="eng_law", item_id="001248"):
    calls = []

    def respond(*args, **kwargs):
        calls.append(kwargs["params"])
        return json.dumps(data, ensure_ascii=False)

    monkeypatch.setattr(legal, "api_call", respond)
    result = legal.execute({"id": item_id, "target": target},
                           SimpleNamespace(tool_name="legal_lookup"))
    return result, calls


def test_english_articles_addenda_and_provenance(legal, monkeypatch):
    out, calls = run_detail(legal, monkeypatch, ENGLISH)
    assert out["success"] and out["count"] == 2
    assert out["Law"] == ENGLISH["Law"]
    assert calls[0]["target"] == "elaw"
    assert [r["no"] for r in out["items"]] == ["제3조", "제6조의3"]
    assert out["items"][0]["text"] == "Article 3 (Effect)\nAn exact body & its exceptions."
    assert out["items"][1]["text"] == "Article 6-3 (Renewal)\n(1) A rule.\n(2) Its exception."
    assert all(r["chapter"] == "CHAPTER I GENERAL PROVISIONS" for r in out["items"])
    assert all(r["url"] == out["law"]["url"] for r in out["items"])
    assert "viewCls=engLsInfoR" in out["law"]["url"]
    assert out["law"]["name"] == "TEST ACT"
    assert out["law"]["promulgation_date"] == "2025-10-01"
    assert out["law"]["enforce_date"] == ""  # Never replace enforcement with promulgation.
    assert all(r["date"] == "" for r in out["items"])
    assert out["addenda"] == [{"text": "ADDENDA: takes effect later.",
                               "promulgation_date": "2025-10-01", "promulgation_no": "21065"}]


def test_english_single_article_with_dates(legal, monkeypatch):
    source = copy.deepcopy(ENGLISH)
    source["Law"]["InfSection"]["efYd"] = "20260102"
    article = source["Law"]["JoSection"]["Jo"][1]
    article["joEnfYd"] = "20260102"
    source["Law"]["JoSection"]["Jo"] = article
    out, _ = run_detail(legal, monkeypatch, source)
    assert out["count"] == 1 and out["items"][0]["date"] == "2026-01-02"
    assert out["law"]["enforce_date"] == "2026-01-02"


@pytest.mark.parametrize("section", [{}, {"Jo": []}, {"Jo": {"joYn": "Y", "joNo": "0001", "joCts": ""}}])
def test_empty_english_body_is_not_success(legal, monkeypatch, section):
    source = copy.deepcopy(ENGLISH)
    source["Law"]["JoSection"] = section
    out, _ = run_detail(legal, monkeypatch, source)
    assert out["success"] is False and out["error_code"] == "SOURCE_ERROR"
    assert out["Law"] == source["Law"]


def test_english_unknown_shape_does_not_manufacture_empty_row(legal, monkeypatch):
    out, _ = run_detail(legal, monkeypatch, {"Unexpected": {"metadata": "only"}})
    assert out["success"] is False and out["items"] == []


def test_term_search_retains_dictionary_kind_and_public_link(legal, monkeypatch):
    source = {"LsTrmSearch": {"totalCnt": "1", "lstrm": {
        "법령용어ID": "12789", "법령용어명": "대항력", "사전구분코드": "011403",
        "법령용어상세링크": "/DRF/lawService.do?OC=fixture-private-oc&target=lstrm",
        "법령용어상세검색": "/LSW/lsTrmInfoR.do?trmSeqs=12789&mobile="}}}
    monkeypatch.setattr(legal, "api_call", lambda *a, **k: json.dumps(source))
    out = legal.execute({"query": "대항력", "target": "law_term"},
                        SimpleNamespace(tool_name="legal_lookup"))
    row = out["items"][0]
    assert row["dictionary_code"] == "011403"
    assert row["id"] == "12789" and row["url"].endswith("/LSW/lsTrmInfoR.do?trmSeqs=12789")
    assert "fixture-private-oc" not in json.dumps(out)


def test_term_detail_keeps_translation_distinct_from_definition(legal, monkeypatch):
    source = {"LsTrmService": {"법령용어일련번호": "12789", "법령용어명_한글": "대항력",
                              "법령용어코드": "011403", "법령용어코드명": "법령한영사전",
                              "법령용어정의": "counterforce"}}
    out, calls = run_detail(legal, monkeypatch, source, "law_term", "12789")
    row = out["items"][0]
    assert calls[0]["trmSeqs"] == "12789"
    assert row["dictionary_name"] == "법령한영사전"
    assert row["dictionary_code"] == "011403"
    assert row["meta"] == "법령한영사전"
    assert row["summary"] == "counterforce"
    assert row["url"].endswith("trmSeqs=12789")


def test_fallback_failure_preserves_unchecked_scope(legal, monkeypatch):
    responses = iter([json.dumps({"PrecSearch": {"totalCnt": "0", "prec": []}}), '<html>broken</html>'])
    monkeypatch.setattr(legal, 'api_call', lambda *a, **k: next(responses))
    out = legal._search('fixture', 'prec', 'missing')
    assert out['source_complete'] is False
    assert out['checked_scopes'] == ['name']
    assert out['search_scope'] == 'name'
    assert out['errors'][0]['scope'] == 'body'
    from ibl_v2_adapters import decode_envelope
    from ibl_v2_ir import Fault
    with pytest.raises(Fault) as failure:
        decode_envelope(out, {'protocol': 'legacy-envelope', 'value_path': ''}, {})
    assert failure.value.code == 'PARTIAL_SOURCE'


def test_explicit_page_preserves_scope_and_pagination(legal, monkeypatch):
    calls = []
    def request(*a, **k):
        calls.append(k['params'])
        return json.dumps({'PrecSearch': {'totalCnt': '5', 'prec': [{'판례일련번호': '3', '사건명': 'case'}]}})
    monkeypatch.setattr(legal, 'api_call', request)
    out = legal._search('fixture', 'prec', 'query', page=2, limit=2, search_scope='body')
    assert calls[0]['page'] == 2 and calls[0]['display'] == 2 and calls[0]['search'] == 2
    assert out['next_page'] == 3 and out['has_more'] and out['source_complete']
    assert out['selection'] == {'scope': 'page', 'page': 2, 'limit': 2}
    assert not legal._search('fixture', 'prec', 'query', page=2)['success']
    assert len(calls) == 1


if __name__ == "__main__":
    import sys

    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
