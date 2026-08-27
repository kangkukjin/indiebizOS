"""검색 통화의 date 필드 가드 — D1~D5.

2026-08-28 동향 보고서 완성 프로그램 정찰이 적발한 비대칭: hn 은 date(ISO8601)를
싣는데 gnews 는 발행일이 meta 문자열에만 갇혔고 naver 는 아예 버렸다 — §2-5
신선도 하드룰(NEW=2주 이내)을 [table:filter] 술어로 세울 수 없었다.
수리 = gnews `_rfc2822_iso`·naver `_item_date_iso` 가 통화 행에 date(ISO8601)를
싣는다. 파싱 불능이면 필드 자체를 싣지 않는다(모르는 날짜 미주장 — B46 부류).

수리 전 코드에서 D1·D3 이 빨강(함수 부재)이어야 한다.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: F401,E402

_ROOT = Path(__file__).resolve().parent.parent
_WEB = _ROOT / "data/packages/installed/tools/web"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, _WEB / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def web_handler():
    return _load("date_guard_web_handler", "handler.py")


@pytest.fixture(scope="module")
def naver_tool():
    return _load("date_guard_naver_tool", "tool_naver_search.py")


def test_D1_gnews_rfc2822_to_iso(web_handler):
    out = web_handler._rfc2822_iso("Wed, 26 Aug 2026 15:23:00 GMT")
    assert out.get("date", "").startswith("2026-08-26")


def test_D2_gnews_unparseable_claims_nothing(web_handler):
    assert web_handler._rfc2822_iso("") == {}
    assert web_handler._rfc2822_iso("어제쯤") == {}


def test_D3_naver_news_pubdate(naver_tool):
    out = naver_tool._item_date_iso({"pub_date": "Thu, 27 Aug 2026 09:00:00 +0900"})
    assert out.get("date", "").startswith("2026-08-27")


def test_D4_naver_blog_postdate(naver_tool):
    assert naver_tool._item_date_iso({"post_date": "20260815"}) == {"date": "2026-08-15"}
    # 8자리 숫자가 아니면 미주장
    assert naver_tool._item_date_iso({"post_date": "2026-08"}) == {}


def test_D5_naver_no_date_claims_nothing(naver_tool):
    assert naver_tool._item_date_iso({}) == {}


def test_D6_gnews_single_item_builder(web_handler):
    """디스패치 세 갈래(queries·headlines·단일 query)가 행을 사설 재조립하지 않는다.

    행 생성자는 _gnews_item 한 벌 — 옛 인라인 조립("source·published join")이 파일에
    한 번(그 한 벌 안)만 남아야 한다. 늘어나면 date 필드가 다시 새는 갈래가 생긴 것.
    """
    row = web_handler._gnews_item(
        {"title": "t", "url": "u", "source": "s",
         "published": "Wed, 26 Aug 2026 15:23:00 GMT", "summary": "본문"}, "태그")
    assert row["date"].startswith("2026-08-26")
    assert row["query"] == "태그" and row["link_label"] == "기사 보기"
    src = (_WEB / "handler.py").read_text(encoding="utf-8")
    joins = src.count('[r.get("source"), r.get("published")]')
    assert joins == 1, f"gnews 행 조립이 {joins}곳 — _gnews_item 한 벌이어야 한다"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
