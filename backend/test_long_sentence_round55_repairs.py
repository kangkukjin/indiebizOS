"""긴문장 55회차(의료상담 — 진료 전 준비철) 수리 회귀.

L55-1 메뉴만 감싼 <article>/<main> 선언을 본문으로 골라 정적 본문 수만 자를 152자로 줄이던 것
L55-1b selector 로 고른 영역을 그 안의 선언 영역으로 다시 좁히던 것
L55-2 PubMed 가 간격·재시도 없이 E-utilities 를 불러 함께 부르면 429 로 죽던 것
L55-3 여러 PMID 를 한 id 로 묶어 물어 PMC 번호가 다른 논문(첫 PMID)에 붙던 것
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "data/packages/installed/tools/web"
STUDY = ROOT / "data/packages/installed/tools/study"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def crawl():
    return _load(WEB / "tool_webcrawl.py", "r55_tool_webcrawl")


@pytest.fixture()
def study(monkeypatch):
    module = _load(STUDY / "handler.py", "r55_study_handler")
    monkeypatch.setattr(module.time, "sleep", lambda s: None)
    return module


BODY_PARA = "고혈압 환자는 가슴 통증이나 호흡곤란이 생기면 운동을 멈추고 즉시 병원을 방문해야 합니다. " * 20
MENU_PAGE = (
    "<html><head><title>건강정보</title></head><body>"
    "<article class='src-subject-wrap'><p>주제별</p><p>전체</p><p>건강문제</p><p>치료방법</p></article>"
    f"<div id='sub-content'><h2>운동요법</h2><p>{BODY_PARA}</p></div>"
    "</body></html>"
)


def test_l55_1_thin_declared_region_does_not_hide_body(crawl):
    _, text = crawl._parse_html(MENU_PAGE, "https://fixture.test/doc")
    assert "즉시 병원을 방문" in text          # 본문이 살아 있다
    assert "주제별" in text                    # 메뉴를 버리는 게 아니라 body 전체로 물러난다
    body = _load(WEB / "webcrawl_body.py", "r55_webcrawl_body")
    sel = body.selection(MENU_PAGE)
    assert sel["scope"] == "body_fallback" and sel["selector"] == "body"
    assert sel["skipped_thin"] == ['article, [itemprop="articleBody"]']


def test_l55_1_real_article_is_still_selected(crawl):
    page = f"<body><div class='chrome'>{'둘러보기 ' * 400}</div><article><p>{BODY_PARA}</p></article></body>"
    _, text = crawl._parse_html(page, "https://fixture.test/a")
    assert "즉시 병원을 방문" in text and "둘러보기" not in text
    # 짧은 글이라도 문서 전체가 짧으면 선언을 그대로 따른다(기존 계약)
    _, text = crawl._parse_html("<body><article>First</article><article>Second</article><div>기타</div></body>", "https://fixture.test")
    assert text == "First\n\nSecond"


def test_l55_1b_explicit_selector_is_not_narrowed_again(crawl):
    view = _load(WEB / "webcrawl_view.py", "r55_webcrawl_view")
    page = (f"<html><body><div id='wrap'><article><p>{'요약 ' * 300}</p></article>"
            f"<div class='detail'><p>{BODY_PARA}</p></div></div></body></html>")
    result = {"success": True, "url": "https://fixture.test/x",
              "_page_structure": {"documents": [{"html": page, "url": "https://fixture.test/x"}], "errors": []}}
    out = view.project(result, selector="#wrap", include_images=False, image_offset=0, image_limit=4,
                       parse_html=crawl._parse_html)
    assert out["success"] and "요약" in out["text"] and "즉시 병원을 방문" in out["text"]


def test_l55_1c_form_wrapping_the_page_is_not_dropped_as_ui(crawl):
    page = ("<html><body><form id='viewForm'><article class='menu'><p>주제별</p></article>"
            f"<div class='contents-Div'><p>{BODY_PARA}</p></div><button>인쇄</button></form>"
            "<form class='search'><input name='q'><button>검색</button></form></body></html>")
    _, text = crawl._parse_html(page, "https://fixture.test/form")
    assert "즉시 병원을 방문" in text           # 페이지 전체를 감싼 form 은 틀이지 조작부가 아니다
    assert "인쇄" not in text and "검색" not in text   # 단추·작은 검색 form 은 그대로 걷는다


class _Resp:
    def __init__(self, status=200, data=None, headers=None):
        self.status_code, self._data, self.headers = status, data or {}, headers or {}

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"{self.status_code} Client Error")


def test_l55_2_pubmed_retries_429_and_spaces_calls(study, monkeypatch):
    calls, sleeps = [], []
    monkeypatch.setattr(study.time, "sleep", lambda s: sleeps.append(s))

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(url.rsplit("/", 1)[-1])
        if len(calls) == 1:
            return _Resp(429, headers={"Retry-After": "1"})
        if "esearch" in url:
            return _Resp(data={"esearchresult": {"idlist": ["111"]}})
        if "esummary" in url:
            return _Resp(data={"result": {"111": {"title": "T", "authors": [], "pubdate": "2024 Jan", "source": "J"}}})
        return _Resp(data={"linksets": []})

    monkeypatch.setattr(study.requests, "get", fake_get)
    out = study._search_pubmed({"query": "x", "limit": 1})
    assert out["success"] and out["items"][0]["pmid"] == "111"
    assert calls[:2] == ["esearch.fcgi", "esearch.fcgi"]          # 429 뒤 같은 요청을 다시
    assert any(s >= 1 for s in sleeps)                             # 물러났다가
    assert sum(1 for s in sleeps if 0 < s < 1) >= 1                # 잇단 호출 사이 간격도 둔다


def test_l55_2_pubmed_reports_failure_after_retries(study, monkeypatch):
    monkeypatch.setattr(study.requests, "get", lambda *a, **k: _Resp(429))
    out = study._search_pubmed({"query": "x"})
    assert out["success"] is False and "429" in out["error"] and out["items"] == []


def test_l55_3_pmc_ids_attach_to_their_own_paper(study, monkeypatch):
    seen = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        seen["params"] = params
        return _Resp(data={"linksets": [
            {"ids": ["37436926"], "linksetdbs": [{"dbto": "pmc", "linkname": "pubmed_pmc_refs", "links": ["13618000"]}]},
            {"ids": ["28734939"], "linksetdbs": [{"dbto": "pmc", "linkname": "pubmed_pmc", "links": ["5696016"]},
                                                 {"dbto": "pmc", "linkname": "pubmed_pmc_refs", "links": ["13643158"]}]},
            {"ids": ["34978586"], "linksetdbs": [{"dbto": "pmc", "linkname": "pubmed_pmc", "links": ["8837711"]}]},
        ]})

    monkeypatch.setattr(study.requests, "get", fake_get)
    got = study._get_pmc_ids(["37436926", "28734939", "34978586"])
    assert got == {"28734939": "PMC5696016", "34978586": "PMC8837711"}   # 인용한 글(refs)의 번호를 제 것으로 붙이지 않는다
    ids = [v for k, v in seen["params"] if k == "id"]
    assert ids == ["37436926", "28734939", "34978586"]                    # id 를 하나씩 — 묶으면 원천이 한 묶음으로 답한다


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
