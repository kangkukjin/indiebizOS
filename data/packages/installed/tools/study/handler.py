import os
import time
import json
import requests
import feedparser
import xml.etree.ElementTree as ET
import html
import re
from typing import Optional

# 2026-06-03 학술 논문 어휘 통합 — search_openalex/arxiv/pubmed/semantic + download_arxiv/pubmed
# → [sense:paper]{op: search|download, source}. op 키만 _OP_DISPATCHERS(소스는 파라미터).
# 2026-06-22 국회도서관 국가학술정보(nanet) — paper source:nanet(학위논문·국내학술) + researcher(연구자·공저자)
# 2026-07-11 Wikidata 개체 해소 — [sense:entity]{op: resolve|detail, source: wikidata}.
#   resolve=동명이인/동음이의를 QID로 못박음, detail=QID→구조화된 사실(records). source는 파라미터.
# op 분기 = 파일 끝 _OP_DISPATCHERS 진짜 함수 테이블 (--check 가 AST 로 키 정확 비교).
_OP_DEFAULTS = {"paper_op": "search", "researcher_op": "find", "entity_op": "resolve"}

# arXiv 예의(politeness) 규약 — export API 는 과부하·과속 요청에 **503** 을 돌려준다.
# 우리는 그동안 UA 도 안 밝히고(기본 python-requests) 재시도도 없이 단발 호출 후
# raise_for_status() 로 즉사했다 → 503 한 번이면 그 호의 논문 채널이 통째로 죽고,
# 보고서엔 "arXiv 장애, 우리 쪽 문제 아님"으로 적혔다(2026-08-12 호). 근거가 없던 단정이다.
_ARXIV_UA = "indiebizOS/1.0 (personal research agent; mailto:kangkukjin@gmail.com)"


def _arxiv_get(url: str, timeout: int = 20, tries: int = 3):
    """arXiv 요청 — 설명형 UA + 503/429 백오프 재시도(3s·6s). 마지막 응답을 그대로 돌려준다."""
    last = None
    for attempt in range(tries):
        last = requests.get(url, headers={"User-Agent": _ARXIV_UA}, timeout=timeout)
        if last.status_code not in (429, 500, 502, 503, 504):
            return last
        if attempt < tries - 1:
            time.sleep(3 * (attempt + 1))
    return last


def _search_arxiv(tool_input: dict) -> str:
    """arXiv 프리프린트 검색 — arxiv 라이브러리 대신 Atom API(https) 직접 호출.
    arxiv 4.x 는 lxml(네이티브)→Chaquopy 불가, 1.4.x 는 http→301 실패. requests+feedparser(폰·맥 공통,
    순수파이썬)로 직접 호출해 라이브러리 의존 제거 + 양쪽 몸에서 동일 작동(이식 가능)."""
    import urllib.parse
    query = tool_input.get("query", "")
    max_results = tool_input.get("max_results", 5)
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode({
        "search_query": f"all:{query}", "start": 0, "max_results": max_results,
        "sortBy": "relevance", "sortOrder": "descending"})
    r = _arxiv_get(url)
    r.raise_for_status()
    feed = feedparser.parse(r.text)
    lines, items = [], []
    for e in feed.entries:
        aid = (e.get("id", "") or "").split("/")[-1]
        title = (e.get("title", "") or "").strip()
        authors = ", ".join(a.get("name", "") for a in e.get("authors", []))
        published = (e.get("published", "") or "")[:10]
        summary = (e.get("summary", "") or "").strip().replace("\n", " ")[:200]
        lines.append(
            f"Title: {title}\nArXiv ID: {aid}\nAuthors: {authors}\n"
            f"Published: {published}\nSummary: {summary}...\n"
            "--------------------------------------"
        )
        items.append({  # 레코드 통화 — message(사람용 문자열)와 함께 반환
            "title": title,
            "meta": " · ".join(x for x in [authors, published] if x),
            "summary": summary,
            "url": f"https://arxiv.org/abs/{aid}",
            "link_label": "논문 보기",
        })
    if not items:
        return {"items": [], "message": "No papers found for the given query."}
    # ★string-반환 변형: 포맷 문자열은 message로, 구조는 records 통화로 둘 다 노출(비파괴 + 조합 가능).
    return {"success": True, "message": "\n".join(lines), "items": items, "count": len(items)}


def _download_arxiv_pdf(tool_input: dict, context) -> str:
    """arXiv 논문 PDF 다운로드 — Atom API 로 메타 조회 후 pdf URL 을 requests 로 받음(폰·맥 공통)."""
    import urllib.parse
    arxiv_id = tool_input.get("arxiv_id") or tool_input.get("id")
    if not arxiv_id:
        return {"success": False, "error": "arxiv_id가 필요합니다."}
    filename = tool_input.get("filename")
    download_dir = context.resolve_path("papers")
    os.makedirs(download_dir, exist_ok=True)
    meta_url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode({"id_list": arxiv_id, "max_results": 1})
    r = _arxiv_get(meta_url)
    r.raise_for_status()
    feed = feedparser.parse(r.text)
    if not feed.entries:
        return {"success": False, "error": f"Could not find paper with ID: {arxiv_id}"}
    entry = feed.entries[0]
    title = (entry.get("title", arxiv_id) or arxiv_id).strip()
    pdf_url = None
    for link in entry.get("links", []):
        if link.get("type") == "application/pdf" or link.get("title") == "pdf":
            pdf_url = link.get("href")
            break
    if not pdf_url:
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
    if not filename:
        filename = "".join([c if c.isalnum() else "_" for c in title]) + ".pdf"
    path = os.path.join(download_dir, filename)
    pr = requests.get(pdf_url, timeout=60)
    pr.raise_for_status()
    with open(path, "wb") as f:
        f.write(pr.content)
    return {"success": True, "message": f"Paper '{title}' downloaded successfully to: {path}", "path": path}


def _paper_search(tool_input: dict, context) -> str:
    """[sense:paper]{op:search, source} — 학술 논문 검색."""
    source = (tool_input.get("source") or "openalex").strip().lower()
    if source == "arxiv":
        return _search_arxiv(tool_input)
    if source in ("pubmed", "pmc"):
        return _search_pubmed(tool_input)
    if source in ("semantic", "semantic_scholar", "s2"):
        return _search_semantic_scholar(tool_input)
    if source in ("nanet", "kr", "dissertation", "국회도서관"):
        return _search_nanet(tool_input)  # 국내 학술논문·학위논문(국회도서관)
    return _search_openalex(tool_input)  # openalex = 기본(범용)


def _paper_download(tool_input: dict, context) -> str:
    """[sense:paper]{op:download, source} — 논문 PDF 다운로드."""
    source = (tool_input.get("source") or "openalex").strip().lower()
    if source in ("pubmed", "pmc"):
        return _download_pubmed_pdf(tool_input, context)
    if source == "arxiv":
        return _download_arxiv_pdf(tool_input, context)
    return {"success": False, "error": "download op은 source=arxiv 또는 pubmed가 필요합니다."}


# ─── 국회도서관 국가학술정보(LOSI) OpenAPI ──────────────────────────────
# losi-api.nanet.go.kr — 연구자(authorView)·공저자(coAuthor)·통합검색(searchTotal).
# 인증키는 .env NANET_API_KEY(auth_manager 'nanet' 레지스트리). POST + authKey.
# ★실측(2026-08-04): 통합검색 엔드포인트는 searchTotal(researchTotal 은 별개 미승인 API).
#   [300] 에러는 "키 만료"뿐 아니라 "해당 API 권한 없음"에도 같은 코드(미존재 엔드포인트=HTTP 404).
_NANET_BASE = "http://losi-api.nanet.go.kr"


def _nanet_call(endpoint: str, params: dict) -> dict:
    """LOSI OpenAPI 호출. authKey 주입(.env) 후 POST. 빈 값 파라미터는 제거."""
    try:
        from common.auth_manager import get_auth_query_params
        auth = get_auth_query_params("nanet")  # {"authKey": key} | None
    except Exception:
        auth = None
    if not auth:
        return {"_err": "NANET_API_KEY 미설정 — losi-open.nanet.go.kr에서 발급한 국가학술정보 인증키를 .env에 넣으세요."}
    data = {**auth}
    for k, v in params.items():
        if v not in (None, ""):
            data[k] = v
    try:
        r = requests.post(f"{_NANET_BASE}/{endpoint}", data=data, timeout=20)
        return r.json()
    except ValueError:
        return {"_err": "국가학술정보 응답 파싱 실패(비JSON). 인증키 활성/엔드포인트 확인 필요."}
    except requests.RequestException as e:
        return {"_err": f"국가학술정보 API 호출 실패: {e}"}


def _nanet_rows(j: dict):
    """LOSI 응답에서 (행 리스트, 에러문자열) 추출. result[0]이 에러 dict이거나 행 리스트."""
    if j.get("_err"):
        return None, j["_err"]
    res = j.get("result")
    if isinstance(res, list) and res:
        first = res[0]
        if isinstance(first, dict) and first.get("error"):
            e = (first["error"] or [{}])[0]
            return None, f"[{e.get('code')}] {e.get('message')}"
        if isinstance(first, list):
            return first, None          # result:[[ {...}, ... ]]
        return res, None                # result:[ {...}, ... ]
    return [], None


def _nanet_author_find(tool_input: dict, context=None) -> str:
    """연구자 검색(authorView) — 동명이인을 소속·출생연도·lodID로 분리."""
    name = tool_input.get("name") or tool_input.get("name_ko") or tool_input.get("query")
    if not name:
        return {"success": False, "error": "연구자명(name)이 필요합니다. 예: [sense:researcher]{name: \"정은정\", org: \"서울대\"}", "items": []}
    org = tool_input.get("org") or tool_input.get("orgName_ko")
    params = {
        "name_ko": name,
        "name_en": tool_input.get("name_en"),
        "orgName_ko": org,
        "display": tool_input.get("max_results") or tool_input.get("display") or 30,
    }
    rows, err = _nanet_rows(_nanet_call("authorView", params))
    if err:
        return {"success": False, "error": f"국가학술정보 연구자 검색 실패: {err}", "items": []}
    # org 필터가 빈 결과면(authorView는 부분일치 안 함) 이름만으로 재조회 후 소속 부분일치로 거름.
    # — 침묵 빈결과 함정 방지.
    org_filtered = False
    if not rows and org:
        all_rows, err2 = _nanet_rows(_nanet_call("authorView", {**params, "orgName_ko": None}))
        if err2:
            return {"success": False, "error": f"국가학술정보 연구자 검색 실패: {err2}", "items": []}
        rows = [r for r in (all_rows or []) if isinstance(r, dict) and org in (r.get("orgName_ko") or "")]
        org_filtered = True
    if not rows:
        hint = f"(소속 '{org}' 부분일치 0건 — 소속 빼고 재시도 권장) " if org else ""
        return {"items": [], "message": f"'{name}' 연구자를 국가학술정보에서 찾지 못했습니다 {hint}(국내 학술 출판 이력 기준 — 산업/비출판 인물은 없을 수 있음)."}
    lines = [f"국가학술정보 연구자 '{name}' — {len(rows)}명 (소속·출생연도로 동명이인 분리):"]
    records = []
    for a in rows:
        if not isinstance(a, dict):
            continue
        bd = (a.get("birthday") or "")
        by = bd[:4] if len(bd) >= 4 else "?"
        en = a.get("name_en") or ""
        org_ko = a.get("orgName_ko") or "?"
        pos = a.get("position") or "-"
        lid = a.get("lodID")
        lines.append(
            f"- {a.get('name_ko')}{(' / ' + en) if en else ''} | 소속:{org_ko} "
            f"| 출생:{by} | 직위:{pos} | lodID:{lid}"
        )
        records.append({  # 레코드 통화 — 동명이인 후보를 소속·생년·lodID로 식별
            "title": a.get("name_ko") or name,
            "meta": " · ".join(x for x in [org_ko if org_ko != "?" else None,
                                            (f"출생 {by}" if by != "?" else None),
                                            (pos if pos != "-" else None)] if x),
            "summary": (f"lodID:{lid}" if lid else "") + (f" / {en}" if en else ""),
            "url": None,
        })
    lines.append("→ [sense:researcher]{op:coauthor, name:\"<이름>\"}으로 연관연구자망 교차검증 가능(이름 기반 — 동명이인 합산 주의).")
    return {"success": True, "message": "\n".join(lines), "items": records, "count": len(records)}


def _nanet_coauthor(tool_input: dict, context=None) -> str:
    """연관연구자망(relAuthor) — 이름으로 함께 연구한 학자들을 떠 신원 재확인.

    ★실측 계약(2026-08-04): 엔드포인트는 coAuthor 아니라 relAuthor. searchTerm=이름(필수),
    lodID 스코핑·페이지네이션 없음(한 번에 최대 ~80명, 동명이인의 연관연구자가 합쳐져 옴).
    inst/birth 는 대부분 null → 소속 검증은 find(authorView)와 교차."""
    name = (tool_input.get("name") or tool_input.get("query")
            or tool_input.get("searchTerm") or "")
    if not name:
        hint = " (연관연구자 API는 이름 기반 — lodID 스코핑 미지원)" if (
            tool_input.get("id") or tool_input.get("lodID") or tool_input.get("authorID")) else ""
        return {"success": False, "error": f"coauthor op은 name(연구자 이름)이 필요합니다{hint}. "
                         "예: [sense:researcher]{op:\"coauthor\", name:\"정은정\"}", "items": []}
    j = _nanet_call("relAuthor", {"searchTerm": name})
    if j.get("_err"):
        return {"success": False, "error": f"연관연구자 조회 실패: {j['_err']}", "items": []}
    res = j.get("result")
    r0 = res[0] if isinstance(res, list) and res else {}
    if not isinstance(r0, dict):
        r0 = {}
    if r0.get("error"):
        e = (r0["error"] or [{}])[0]
        return {"success": False, "error": f"연관연구자 조회 실패: [{e.get('code')}] {e.get('message')}", "items": []}
    rows = r0.get("authorList") or []
    if not rows:
        return {"items": [], "message": f"'{name}'의 연관연구자 정보가 없습니다."}
    limit = int(tool_input.get("max_results") or tool_input.get("display") or 30)
    lines = [f"'{name}' 연관연구자 — {min(len(rows), limit)}명 (전체 {len(rows)}명, 동명이인 합산 주의):"]
    records = []
    for a in rows[:limit]:
        if not isinstance(a, dict):
            continue
        nm = a.get("name") or "?"
        lid = a.get("lodAuthorID") or ""
        inst = a.get("inst") or ""
        birth = a.get("birth") or ""
        lines.append(f"- {nm}" + (f" | 소속:{inst}" if inst else "") + (f" | lodID:{lid}" if lid else ""))
        records.append({  # 레코드 통화 — 연관연구자 신원
            "title": nm,
            "meta": " · ".join(x for x in [inst, (f"출생 {birth}" if birth else "")] if x),
            "summary": (f"lodID:{lid}" if lid else ""),
            "url": None,
        })
    return {"success": True, "message": "\n".join(lines), "items": records, "count": len(records)}


def _search_nanet(tool_input: dict) -> str:
    """통합검색(searchTotal) — 국내 학술논문·학위논문. 학위논문=인물 신원의 결정적 닻.

    ★실측 계약(2026-08-04): 검색어 파라미터=searchTerm(query 아님), 페이지당 5건 고정
    (건수 파라미터 없음), 페이지네이션=pageNo, divFlag/pubYear 서버 필터 없음.
    → max_results 는 pageNo 추적으로, type·year 는 클라이언트 후필터로 이행."""
    query = tool_input.get("query") or tool_input.get("q") or tool_input.get("keyword")
    if not query:
        return {"success": False, "error": "검색어(query)가 필요합니다.", "items": []}
    want = int(tool_input.get("max_results") or tool_input.get("display") or 10)
    year_f = str(tool_input.get("year") or "").strip()
    type_f = str(tool_input.get("type") or "").strip()
    # 자료유형 후필터 — divFlag 값으로 정규화(모르는 값은 대문자 부분일치)
    # divFlag 실측 분포(2026-08-04): ARTICLE(학술논문)·THESIS(학위논문)·BOOK(단행본)
    _type_map = {"학위논문": "THESIS", "학술논문": "ARTICLE", "논문": "ARTICLE", "기사": "ARTICLE",
                 "단행본": "BOOK", "도서": "BOOK", "책": "BOOK"}
    div_want = (_type_map.get(type_f) or type_f).upper() if type_f else ""

    lines_body, records = [], []
    total = None
    page = int(tool_input.get("page") or 1)
    last_page = page + 19          # 후필터가 걸러도 왕복 상한 20페이지(100행)
    while len(records) < want and page <= last_page:
        j = _nanet_call("searchTotal", {"searchTerm": query, "pageNo": page})
        if j.get("_err"):
            return {"success": False, "error": f"국가학술정보 통합검색 실패: {j['_err']}", "items": []}
        res = j.get("result")
        r0 = res[0] if isinstance(res, list) and res else {}
        if not isinstance(r0, dict):
            r0 = {}
        if r0.get("error"):
            e = (r0["error"] or [{}])[0]
            return {"success": False, "error": f"국가학술정보 통합검색 실패: [{e.get('code')}] {e.get('message')}", "items": []}
        if total is None:
            total = r0.get("totalCount")
        rows = r0.get("searchList") or []
        if not rows:
            break
        for it in rows:
            if not isinstance(it, dict):
                continue
            div = str(it.get("divFlag") or "")
            yr = str(it.get("pubYear") or "")
            if div_want and div_want not in div.upper():
                continue
            if year_f and yr != year_f:
                continue
            title = it.get("title") or "(제목없음)"
            authors = ", ".join(a.get("name", "") for a in (it.get("authorList") or [])
                                if isinstance(a, dict) and a.get("name"))
            journal = ((it.get("journal") or {}).get("title")) or ""
            publisher = it.get("publisher") or ""
            meta = " · ".join(x for x in [div, authors, journal or publisher, yr] if x)
            url = it.get("url") or ""
            summary = (it.get("abstractCont") or "").strip()
            lines_body.append(f"- {title}" + (f" [{meta}]" if meta else "") + (f"\n  {url}" if url else ""))
            records.append({  # 레코드 통화 — 국내 학술논문·학위논문
                "title": title,
                "meta": meta,
                "summary": summary,
                "url": url,
            })
            if len(records) >= want:
                break
        page += 1
    if not records:
        filt = " (type/year 후필터 적용)" if (div_want or year_f) else ""
        return {"items": [], "message": f"'{query}'에 대한 국가학술정보 결과가 없습니다{filt}."}
    head = f"국가학술정보 통합검색 '{query}' — {len(records)}건" + (f" (전체 {total:,}건)" if isinstance(total, int) else "") + ":"
    return {"success": True, "message": "\n".join([head] + lines_body),
            "items": records, "count": len(records), "total": total}


# ─── Wikidata 개체 해소(entity resolution) — 지식 그래프 ────────────────
# www.wikidata.org/w/api.php — wbsearchentities(검색)·wbgetentities(상세).
# 무API키(공개), 순수 requests(맥·폰 공통). Wikimedia는 서술적 User-Agent 요구.
_WD_API = "https://www.wikidata.org/w/api.php"
_WD_HEADERS = {"User-Agent": "IndieBizOS/1.0 (entity resolution; contact kangkukjin@gmail.com)"}


def _wd_get(params: dict) -> dict:
    """Wikidata Action API GET (format=json 고정)."""
    r = requests.get(_WD_API, params={**params, "format": "json"},
                     headers=_WD_HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()


def _wd_search(query: str, lang: str, limit: int) -> list:
    """wbsearchentities — lang 라벨 없으면 en 폴백."""
    data = _wd_get({"action": "wbsearchentities", "search": query,
                    "language": lang, "uselang": lang, "type": "item", "limit": limit})
    hits = data.get("search") or []
    if not hits and lang != "en":
        data = _wd_get({"action": "wbsearchentities", "search": query,
                        "language": "en", "uselang": "en", "type": "item", "limit": limit})
        hits = data.get("search") or []
    return hits


def _wd_labels(ids: list, lang: str) -> dict:
    """P-id/Q-id 라벨 배치 해소 (wbgetentities props=labels, 50개씩)."""
    out, ids = {}, [i for i in dict.fromkeys(ids) if i]
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        try:
            d = _wd_get({"action": "wbgetentities", "ids": "|".join(chunk),
                         "props": "labels", "languages": f"{lang}|en"})
        except Exception:
            continue
        for k, v in (d.get("entities") or {}).items():
            labs = v.get("labels") or {}
            out[k] = (labs.get(lang) or labs.get("en") or {}).get("value") or k
    return out


def _wd_snak_value(snak: dict, label_map: dict):
    """mainsnak → 사람이 읽는 값 문자열 (개체는 라벨 해소, 시간·수량 포맷)."""
    if snak.get("snaktype") != "value":
        return None
    dv = snak.get("datavalue") or {}
    t, v = dv.get("type"), dv.get("value")
    if t == "wikibase-entityid":
        return label_map.get(v.get("id"), v.get("id"))
    if t == "string":
        return v
    if t == "monolingualtext":
        return (v or {}).get("text")
    if t == "time":
        tv = (v or {}).get("time") or ""    # 예: +1946-08-04T00:00:00Z
        m = re.match(r"[+-](\d+)-(\d\d)-(\d\d)", tv)
        if m:
            y, mo, d = m.groups()
            if mo == "00":
                return y
            if d == "00":
                return f"{y}-{mo}"
            return f"{y}-{mo}-{d}"
        return tv
    if t == "quantity":
        return ((v or {}).get("amount") or "").lstrip("+")
    if t == "globecoordinate":
        return f"{(v or {}).get('latitude')}, {(v or {}).get('longitude')}"
    return None


def _wikidata_resolve(tool_input: dict) -> str:
    """개체 후보 검색 — 동명이인/동음이의를 QID·설명으로 분리."""
    query = tool_input.get("query") or tool_input.get("q") or tool_input.get("name")
    if not query:
        return {"success": False, "error": "검색어(query)가 필요합니다. 예: [sense:entity]{query: \"강국진\"}", "items": []}
    lang = (tool_input.get("lang") or "ko").strip()
    limit = int(tool_input.get("max_results") or tool_input.get("limit") or 7)
    try:
        hits = _wd_search(query, lang, limit)
    except Exception as e:
        return {"success": False, "error": f"Wikidata 검색 오류: {e}", "items": []}
    if not hits:
        return {"items": [], "message": f"'{query}'에 해당하는 Wikidata 개체를 찾지 못했습니다."}
    lines = [f"Wikidata 개체 후보 '{query}' — {len(hits)}건 (QID로 동명이인/동음이의 해소):"]
    records = []
    for h in hits:
        qid = h.get("id")
        label = h.get("label") or query
        desc = h.get("description") or ""
        lines.append(f"- {label} ({qid})" + (f" — {desc}" if desc else ""))
        records.append({  # 레코드 통화 — 개체 후보를 QID·설명으로 식별
            "title": label,
            "meta": " · ".join(x for x in [qid, desc] if x),
            "summary": desc,
            "url": f"https://www.wikidata.org/wiki/{qid}",
            "qid": qid,
        })
    lines.append("→ QID를 [sense:entity]{op:\"detail\", id:\"<QID>\"}에 넣어 구조화된 사실 조회.")
    return {"success": True, "message": "\n".join(lines), "items": records, "count": len(records)}


def _wikidata_detail(tool_input: dict) -> str:
    """QID(또는 query) → 구조화된 속성·사실 (P-속성명: 값, records 통화)."""
    lang = (tool_input.get("lang") or "ko").strip()
    qid = tool_input.get("id") or tool_input.get("qid")
    if not qid:
        query = tool_input.get("query") or tool_input.get("q") or tool_input.get("name")
        if not query:
            return {"success": False, "error": "id(QID) 또는 query가 필요합니다. 예: [sense:entity]{op:\"detail\", id:\"Q42\"}", "items": []}
        try:
            hits = _wd_search(query, lang, 1)
        except Exception as e:
            return {"success": False, "error": f"Wikidata 조회 오류: {e}", "items": []}
        if not hits:
            return {"items": [], "message": f"'{query}'에 해당하는 Wikidata 개체를 찾지 못했습니다."}
        qid = hits[0].get("id")
    qid = str(qid).strip().upper()
    if not re.match(r"^Q\d+$", qid):
        return {"success": False, "error": f"올바른 QID가 아닙니다: {qid} (예: Q42). 이름으로 찾으려면 op:resolve 사용.", "items": []}
    try:
        data = _wd_get({"action": "wbgetentities", "ids": qid,
                        "props": "labels|descriptions|claims", "languages": f"{lang}|en"})
    except Exception as e:
        return {"success": False, "error": f"Wikidata 상세 오류: {e}", "items": []}
    ent = (data.get("entities") or {}).get(qid)
    if not ent or ent.get("missing") is not None and "missing" in ent:
        return {"items": [], "message": f"{qid} 개체 정보가 없습니다."}

    def _pick(obj):    # labels/descriptions dict → lang→en 폴백
        d = obj or {}
        for L in (lang, "en"):
            if d.get(L):
                return d[L].get("value")
        return None

    label = _pick(ent.get("labels")) or qid
    desc = _pick(ent.get("descriptions")) or ""
    claims = ent.get("claims") or {}
    prop_ids = list(claims.keys())
    truncated = len(prop_ids) > 30
    prop_ids = prop_ids[:30]
    # 라벨 해소 대상(속성 P-id + 값이 개체인 Q-id) 수집 → 한 번에 배치 조회
    value_qids = []
    for pid in prop_ids:
        for st in (claims[pid] or [])[:3]:
            dv = (((st.get("mainsnak") or {}).get("datavalue")) or {}).get("value")
            if isinstance(dv, dict) and dv.get("entity-type") == "item" and dv.get("id"):
                value_qids.append(dv["id"])
    label_map = _wd_labels(prop_ids + value_qids, lang)
    lines = [f"[{label}] ({qid})" + (f" — {desc}" if desc else ""),
             f"https://www.wikidata.org/wiki/{qid}", ""]
    records = []
    for pid in prop_ids:
        plabel = label_map.get(pid, pid)
        vals = []
        for st in (claims[pid] or [])[:3]:
            val = _wd_snak_value(st.get("mainsnak") or {}, label_map)
            if val:
                vals.append(str(val))
        if not vals:
            continue
        valstr = ", ".join(vals)
        lines.append(f"- {plabel}: {valstr}")
        records.append({  # 레코드 통화 — 사실 1건 = 속성:값
            "title": plabel,
            "meta": pid,
            "summary": valstr,
            "url": None,
        })
    if truncated:
        lines.append(f"… (속성 {len(claims)}개 중 30개만 표시)")
    return {"success": True, "message": "\n".join(lines), "items": records,
            "count": len(records), "qid": qid, "label": label}


def _entity_source_err(tool_input: dict):
    """[sense:entity] 공용 source 게이트 — 지원 밖 source 면 에러 dict, 아니면 None."""
    source = (tool_input.get("source") or "wikidata").strip().lower()
    if source not in ("wikidata", "wd", "wikimedia"):
        return {"success": False, "error": f"현재 source는 wikidata만 지원합니다 (요청: {source})."}
    return None


def _entity_resolve(tool_input: dict, context) -> str:
    """[sense:entity]{op:resolve} — 개체 후보 검색 (Wikidata)."""
    return _entity_source_err(tool_input) or _wikidata_resolve(tool_input)


def _entity_detail(tool_input: dict, context) -> str:
    """[sense:entity]{op:detail} — QID → 구조화된 사실 (Wikidata)."""
    return _entity_source_err(tool_input) or _wikidata_detail(tool_input)


def execute(tool_input: dict, context) -> str:
    """ToolContext 기반 신규 시그니처. op 도구 분기 = 파일 끝 _OP_DISPATCHERS 함수 테이블."""
    tool_name = context.tool_name

    if tool_name in _OP_DISPATCHERS:
        op = (tool_input.get("op") or _OP_DEFAULTS.get(tool_name, "")).strip()
        fn = _OP_DISPATCHERS[tool_name].get(op)
        if fn is None:
            return {"success": False, "error": f"알 수 없는 op '{op}'. 사용: {'|'.join(_OP_DISPATCHERS[tool_name])}"}
        return fn(tool_input, context)

    elif tool_name == "fetch_pew_research":
        return _fetch_rss("https://www.pewresearch.org/feed/", "Pew Research Center", tool_input.get("limit", 10))

    elif tool_name == "fetch_world_bank_data":
        return _fetch_world_bank_data(tool_input)

    else:
        return json.dumps({"success": False, "error": f"Unknown tool: {tool_name}"}, ensure_ascii=False)


def _search_semantic_scholar(tool_input: dict) -> str:
    """
    Semantic Scholar API를 사용한 논문 검색

    Rate Limit: 인증 없이 5분당 100건 (429 에러 시 재시도)
    API 문서: https://api.semanticscholar.org/api-docs/
    """
    import time

    query = tool_input.get("query")
    max_results = tool_input.get("max_results", 5)
    year_from = tool_input.get("year_from")

    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": max_results,
        "fields": "title,authors,year,citationCount,abstract,url,openAccessPdf"
    }

    if year_from:
        params["year"] = f"{year_from}-"

    # Rate limit 대응: 최대 3번 재시도
    max_retries = 3
    retry_delay = 2  # 초

    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=15)

            # Rate limit (429) 처리
            if response.status_code == 429:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))  # 점진적 대기
                    continue
                else:
                    return {"success": False, "error": "Semantic Scholar API 요청 한도 초과. 잠시 후 다시 시도하거나, OpenAlex 또는 arXiv를 사용해주세요.", "items": []}

            response.raise_for_status()
            data = response.json()

            papers = data.get("data", [])
            if not papers:
                return {"items": [], "message": f"'{query}' 검색 결과가 없습니다."}

            total = data.get("total", len(papers))
            results = []
            results.append(f"Semantic Scholar 검색 결과: '{query}' (총 {total:,}건 중 {len(papers)}건 표시)\n")
            records = []

            for i, paper in enumerate(papers, 1):
                authors = ", ".join([a.get("name", "Unknown") for a in paper.get("authors", [])[:3]])
                if len(paper.get("authors", [])) > 3:
                    authors += " et al."

                raw_abstract = paper.get("abstract", "") or ""
                if raw_abstract:
                    abstract = raw_abstract[:200] + "..." if len(raw_abstract) > 200 else raw_abstract
                else:
                    abstract = "No abstract available"

                pdf_url = ""
                if paper.get("openAccessPdf"):
                    pdf_url = f"\nPDF (Open Access): {paper['openAccessPdf'].get('url', '')}"

                separator = "-" * 60
                title = paper.get('title', 'Unknown')
                year = paper.get('year', 'Unknown')
                citations = paper.get('citationCount', 0)
                paper_url = paper.get('url', '')
                paper_info = (
                    f"[{i}] {title}\n"
                    f"Authors: {authors}\n"
                    f"Year: {year} | Citations: {citations}\n"
                    f"URL: {paper_url}{pdf_url}\n"
                    f"Abstract: {abstract}\n"
                    f"{separator}"
                )
                results.append(paper_info)
                records.append({  # 레코드 통화
                    "title": title,
                    "meta": " · ".join(x for x in [
                        authors,
                        str(year) if year not in (None, "Unknown") else "",
                        f"인용 {citations}" if citations else "",
                    ] if x),
                    "summary": raw_abstract,
                    "url": paper_url or "",
                })

            return {"success": True, "message": "\n".join(results), "items": records, "count": len(records)}

        except requests.RequestException as e:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            return {"success": False, "error": f"Semantic Scholar 검색 오류: {str(e)}", "items": []}

    return {"success": False, "error": "Semantic Scholar 검색 실패. 다른 검색 도구를 사용해주세요.", "items": []}


def _search_pubmed(tool_input: dict) -> str:
    """PubMed API를 사용한 의학/생명과학 논문 검색 (PMC ID 포함)"""
    query = tool_input.get("query")
    max_results = tool_input.get("max_results", 5)

    # Step 1: Search for paper IDs
    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    search_params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json"
    }

    try:
        search_response = requests.get(search_url, params=search_params, timeout=15)
        search_response.raise_for_status()
        search_data = search_response.json()

        id_list = search_data.get("esearchresult", {}).get("idlist", [])

        if not id_list:
            return {"items": [], "message": "No papers found for the given query."}

        # Step 2: Fetch paper details with PMC links
        fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        fetch_params = {
            "db": "pubmed",
            "id": ",".join(id_list),
            "retmode": "json"
        }

        fetch_response = requests.get(fetch_url, params=fetch_params, timeout=15)
        fetch_response.raise_for_status()
        fetch_data = fetch_response.json()

        # Step 3: Get PMC IDs using elink
        pmc_ids = _get_pmc_ids(id_list)

        results = []
        records = []
        result_data = fetch_data.get("result", {})

        for pmid in id_list:
            paper = result_data.get(pmid, {})
            if not paper or pmid == "uids":
                continue

            title = paper.get("title", "Unknown")
            authors_list = paper.get("authors", [])
            authors = ", ".join([a.get("name", "") for a in authors_list[:3]])
            if len(authors_list) > 3:
                authors += " et al."

            pub_date = paper.get("pubdate", "Unknown")
            journal = paper.get("source", "Unknown")

            # PMC ID가 있으면 표시
            pmcid = pmc_ids.get(pmid)
            pmc_info = ""
            if pmcid:
                pmc_info = f"\nPMC ID: {pmcid} (Free full text available - use download_pubmed_pdf)"

            paper_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            paper_info = (
                f"Title: {title}\n"
                f"Authors: {authors}\n"
                f"Journal: {journal}\n"
                f"Published: {pub_date}\n"
                f"PMID: {pmid}{pmc_info}\n"
                f"URL: {paper_url}\n"
                "--------------------------------------"
            )
            results.append(paper_info)
            records.append({  # 레코드 통화 (PubMed esummary엔 초록이 없음 → summary 생략)
                "title": title,
                "meta": " · ".join(x for x in [
                    authors,
                    journal if journal != "Unknown" else "",
                    pub_date if pub_date != "Unknown" else "",
                    pmcid if pmcid else "",
                ] if x),
                "summary": "",
                "url": paper_url,
            })

        if not results:
            return {"items": [], "message": "No papers found for the given query."}

        return {"success": True, "message": "\n".join(results), "items": records, "count": len(records)}

    except requests.RequestException as e:
        return {"success": False, "error": f"Error searching PubMed: {str(e)}", "items": []}


def _get_pmc_ids(pmid_list: list) -> dict:
    """PMID 목록에서 PMC ID 매핑을 가져옴"""
    if not pmid_list:
        return {}

    link_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
    link_params = {
        "dbfrom": "pubmed",
        "db": "pmc",
        "id": ",".join(pmid_list),
        "retmode": "json"
    }

    try:
        response = requests.get(link_url, params=link_params, timeout=15)
        response.raise_for_status()
        data = response.json()

        pmc_ids = {}
        linksets = data.get("linksets", [])

        for linkset in linksets:
            pmid = str(linkset.get("ids", [None])[0])
            linksetdbs = linkset.get("linksetdbs", [])

            for linksetdb in linksetdbs:
                if linksetdb.get("dbto") == "pmc":
                    links = linksetdb.get("links", [])
                    if links:
                        pmc_ids[pmid] = f"PMC{links[0]}"
                        break

        return pmc_ids

    except Exception:
        return {}


def _download_pubmed_pdf(tool_input: dict, context) -> str:
    """PMC에서 무료 전문 PDF 다운로드 (OA API 사용)"""
    import xml.etree.ElementTree as ET
    import tarfile
    import io
    import urllib.request
    import urllib.error

    pmcid = (tool_input.get("pmcid") or tool_input.get("id") or "").strip()
    filename = tool_input.get("filename")

    if not pmcid:
        return {"success": False, "error": "PMC ID is required"}

    # PMC 접두사 정규화
    if not pmcid.upper().startswith("PMC"):
        pmcid = f"PMC{pmcid}"
    pmcid = pmcid.upper()

    download_dir = context.resolve_path("papers")
    os.makedirs(download_dir, exist_ok=True)

    try:
        # 1. OA API로 다운로드 링크 가져오기
        oa_url = f"https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id={pmcid}"
        oa_response = requests.get(oa_url, timeout=30)
        oa_response.raise_for_status()

        # XML 파싱
        root = ET.fromstring(oa_response.text)
        error = root.find(".//error")
        if error is not None:
            return {"success": False, "error": f"{error.text}"}

        link = root.find(".//link")
        if link is None:
            return {"success": False, "error": f"No download link available for {pmcid}. This paper may not be open access."}

        href = link.get("href")
        file_format = link.get("format", "")

        if not href:
            return {"success": False, "error": f"Could not find download URL for {pmcid}"}

        # 2. 파일 다운로드 (FTP 및 HTTP 지원)
        if href.startswith("ftp://"):
            # FTP는 urllib 사용
            with urllib.request.urlopen(href, timeout=120) as response:
                download_content = response.read()
        else:
            # HTTP/HTTPS는 requests 사용
            download_response = requests.get(href, timeout=60)
            download_response.raise_for_status()
            download_content = download_response.content

        # 파일명 설정
        if not filename:
            filename = f"{pmcid}.pdf"
        elif not filename.endswith(".pdf"):
            filename += ".pdf"

        file_path = os.path.join(download_dir, filename)

        # 3. tar.gz인 경우 PDF 추출
        if file_format == "tgz" or href.endswith(".tar.gz"):
            tar_content = io.BytesIO(download_content)
            with tarfile.open(fileobj=tar_content, mode="r:gz") as tar:
                # PDF 파일 찾기
                pdf_found = False
                for member in tar.getmembers():
                    if member.name.endswith(".pdf"):
                        pdf_file = tar.extractfile(member)
                        if pdf_file:
                            with open(file_path, "wb") as f:
                                f.write(pdf_file.read())
                            pdf_found = True
                            break

                if not pdf_found:
                    # PDF가 없으면 전체 tar.gz 저장
                    tar_path = os.path.join(download_dir, f"{pmcid}.tar.gz")
                    with open(tar_path, "wb") as f:
                        f.write(download_content)
                    return {"success": True, "message": f"Paper archive downloaded to: {tar_path} (PDF not found in archive, may contain other formats)", "path": tar_path}
        else:
            # 직접 PDF인 경우
            with open(file_path, "wb") as f:
                f.write(download_content)

        return {"success": True, "message": f"Paper downloaded successfully to: {file_path}", "path": file_path}

    except requests.RequestException as e:
        return {"success": False, "error": f"Error downloading PDF: {str(e)}"}
    except urllib.error.URLError as e:
        return {"success": False, "error": f"Error downloading from FTP: {str(e)}"}
    except ET.ParseError as e:
        return {"success": False, "error": f"Error parsing OA API response: {str(e)}"}
    except tarfile.TarError as e:
        return {"success": False, "error": f"Error extracting archive: {str(e)}"}


def _search_openalex(tool_input: dict) -> str:
    """
    OpenAlex API를 사용한 학술 논문 검색

    OpenAlex는 세계 최대 오픈 학술 데이터베이스로 2.6억+ 논문을 보유하고 있습니다.
    모든 학문 분야를 커버하며, 완전 무료로 API 키 없이 사용 가능합니다.

    API 문서: https://docs.openalex.org/
    """
    query = tool_input.get("query")
    max_results = min(tool_input.get("max_results", 10), 200)  # 최대 200개
    year_from = tool_input.get("year_from")
    year_to = tool_input.get("year_to")
    open_access = tool_input.get("open_access", False)
    sort_by = tool_input.get("sort_by", "relevance")

    # API 엔드포인트
    url = "https://api.openalex.org/works"

    # 필터 구성
    filters = []

    # 연도 필터
    if year_from and year_to:
        filters.append(f"publication_year:{year_from}-{year_to}")
    elif year_from:
        filters.append(f"publication_year:>{year_from - 1}")
    elif year_to:
        filters.append(f"publication_year:<{year_to + 1}")

    # 오픈액세스 필터
    if open_access:
        filters.append("is_oa:true")

    # 정렬 옵션
    sort_mapping = {
        "relevance": "relevance_score:desc",
        "cited": "cited_by_count:desc",
        "recent": "publication_date:desc"
    }
    sort_param = sort_mapping.get(sort_by, "relevance_score:desc")

    # 요청 파라미터
    params = {
        "search": query,
        "per-page": max_results,
        "sort": sort_param,
        "select": "id,title,authorships,publication_year,cited_by_count,doi,open_access,abstract_inverted_index,primary_location"
    }

    if filters:
        params["filter"] = ",".join(filters)

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        works = data.get("results", [])
        total_count = data.get("meta", {}).get("count", 0)

        if not works:
            return {"items": [], "message": f"'{query}' 검색 결과가 없습니다."}

        results = []
        results.append(f"OpenAlex 검색 결과: '{query}' (총 {total_count:,}건 중 {len(works)}건 표시)\n")
        records = []

        for i, work in enumerate(works, 1):
            # 제목
            title = work.get("title", "제목 없음")

            # 저자 추출
            authorships = work.get("authorships", [])
            authors = []
            for auth in authorships[:3]:
                author_name = auth.get("author", {}).get("display_name", "Unknown")
                authors.append(author_name)
            if len(authorships) > 3:
                authors.append("et al.")
            authors_str = ", ".join(authors) if authors else "저자 정보 없음"

            # 발행연도, 인용수
            year = work.get("publication_year", "Unknown")
            citations = work.get("cited_by_count", 0)

            # DOI
            doi = work.get("doi", "")
            doi_str = f"\nDOI: {doi}" if doi else ""

            # 오픈액세스 PDF URL
            oa_info = work.get("open_access", {})
            oa_url = oa_info.get("oa_url", "")
            oa_str = f"\nPDF (Open Access): {oa_url}" if oa_url else ""

            # 저널/출처 정보
            primary_loc = work.get("primary_location", {}) or {}
            source = primary_loc.get("source", {}) or {}
            journal = source.get("display_name", "")
            journal_str = f"\nJournal: {journal}" if journal else ""

            # 초록 복원 (inverted index에서) — 500자까지 허용
            full_abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))
            if full_abstract:
                abstract = full_abstract[:500] + "..." if len(full_abstract) > 500 else full_abstract
                abstract_str = f"\nAbstract: {abstract}"
            else:
                abstract_str = ""

            # OpenAlex ID에서 URL 생성
            work_id = work.get("id", "")
            openalex_url = work_id if work_id else ""
            # 상세 링크는 DOI(landing page) 우선, 없으면 OpenAlex 페이지
            record_url = doi if doi else openalex_url

            separator = "-" * 60
            paper_info = (
                f"[{i}] {title}\n"
                f"Authors: {authors_str}\n"
                f"Year: {year} | Citations: {citations:,}{journal_str}{doi_str}{oa_str}{abstract_str}\n"
                f"OpenAlex: {openalex_url}\n"
                f"{separator}"
            )
            results.append(paper_info)
            records.append({  # 레코드 통화
                "title": title,
                "meta": " · ".join(x for x in [
                    authors_str if authors_str != "저자 정보 없음" else "",
                    str(year) if year not in (None, "Unknown") else "",
                    journal,
                    f"인용 {citations:,}" if citations else "",
                ] if x),
                "summary": full_abstract,
                "url": record_url or "",
            })

        return {"success": True, "message": "\n".join(results), "items": records, "count": len(records)}

    except requests.RequestException as e:
        return {"success": False, "error": f"OpenAlex 검색 오류: {str(e)}", "items": []}
    except Exception as e:
        return {"success": False, "error": f"검색 처리 오류: {str(e)}", "items": []}


def _reconstruct_abstract(inverted_index: dict) -> str:
    """
    OpenAlex의 abstract_inverted_index에서 원문 초록을 복원합니다.

    OpenAlex는 저장 공간 절약을 위해 초록을 inverted index 형태로 저장합니다.
    예: {"word1": [0, 5], "word2": [1, 3]} -> 위치 기반으로 단어 재배열
    """
    if not inverted_index:
        return ""

    try:
        # 위치-단어 매핑 생성
        word_positions = []
        for word, positions in inverted_index.items():
            for pos in positions:
                word_positions.append((pos, word))

        # 위치순 정렬 후 단어 연결
        word_positions.sort(key=lambda x: x[0])
        abstract = " ".join([word for pos, word in word_positions])

        return abstract
    except Exception:
        return ""

def _fetch_rss(url: str, source_name: str, limit: int = 10) -> str:
    """RSS 피드를 가져와서 파싱합니다 (feedparser 사용)."""
    try:
        feed = feedparser.parse(url)
        
        if not feed.entries:
            return {"items": [], "message": f"{source_name}에서 기사를 찾을 수 없습니다."}
            
        results = [f"### {source_name} 최신 소식 (최대 {limit}건)\n"]
        records = []

        for i, entry in enumerate(feed.entries[:limit], 1):
            title = entry.get("title", "제목 없음")
            link = entry.get("link", "")
            pub_date = entry.get("published", entry.get("updated", ""))
            description = entry.get("summary", entry.get("description", ""))

            # HTML 태그 제거 및 언이스케이프
            description = re.sub('<[^<]+?>', '', description)
            description = html.unescape(description).strip()
            if len(description) > 200:
                description = description[:200] + "..."

            item_info = (
                f"[{i}] {title}\n"
                f"날짜: {pub_date}\n"
                f"링크: {link}\n"
                f"요약: {description}\n"
                "--------------------------------------"
            )
            results.append(item_info)
            records.append({  # 레코드 통화
                "title": title,
                "meta": " · ".join(x for x in [source_name, pub_date] if x),
                "summary": description,
                "url": link,
            })

        return {"success": True, "message": "\n".join(results), "items": records, "count": len(records)}

    except Exception as e:
        return {"success": False, "error": f"{source_name} RSS 가져오기 오류: {str(e)}", "items": []}

# _search_guardian 은 2026-08-05 어휘 압축 (2)에서 web 패키지 [sense:search]{source:"guardian"} 로 이주.


# ── 내부 해소 테이블 (자연어 지표·국가명 → World Bank 코드) ────────────
# 흔한 케이스만 큐레이션. 미등록 입력은 원시 코드로 간주하고 그대로 통과.
_WB_INDICATORS = {
    "gdp": "NY.GDP.MKTP.CD", "국내총생산": "NY.GDP.MKTP.CD",
    "1인당gdp": "NY.GDP.PCAP.CD", "인당gdp": "NY.GDP.PCAP.CD",
    "gdppercapita": "NY.GDP.PCAP.CD",
    "gdp성장률": "NY.GDP.MKTP.KD.ZG", "경제성장률": "NY.GDP.MKTP.KD.ZG",
    "gdpgrowth": "NY.GDP.MKTP.KD.ZG", "성장률": "NY.GDP.MKTP.KD.ZG",
    "인구": "SP.POP.TOTL", "population": "SP.POP.TOTL", "총인구": "SP.POP.TOTL",
    "인구증가율": "SP.POP.GROW", "populationgrowth": "SP.POP.GROW",
    "인플레이션": "FP.CPI.TOTL.ZG", "물가": "FP.CPI.TOTL.ZG",
    "물가상승률": "FP.CPI.TOTL.ZG", "inflation": "FP.CPI.TOTL.ZG",
    "실업률": "SL.UEM.TOTL.ZS", "unemployment": "SL.UEM.TOTL.ZS",
    "기대수명": "SP.DYN.LE00.IN", "lifeexpectancy": "SP.DYN.LE00.IN",
    "수출": "NE.EXP.GNFS.CD", "exports": "NE.EXP.GNFS.CD",
    "수입": "NE.IMP.GNFS.CD", "imports": "NE.IMP.GNFS.CD",
    "1인당소득": "NY.GNP.PCAP.CD", "gnipercapita": "NY.GNP.PCAP.CD",
    "출산율": "SP.DYN.TFRT.IN", "fertility": "SP.DYN.TFRT.IN",
    "도시인구비율": "SP.URB.TOTL.IN.ZS", "urban": "SP.URB.TOTL.IN.ZS",
    "정부부채": "GC.DOD.TOTL.GD.ZS", "governmentdebt": "GC.DOD.TOTL.GD.ZS",
    "co2": "EN.ATM.CO2E.PC", "이산화탄소": "EN.ATM.CO2E.PC", "탄소배출": "EN.ATM.CO2E.PC",
}
_WB_COUNTRIES = {
    "한국": "KOR", "대한민국": "KOR", "korea": "KOR", "southkorea": "KOR", "rok": "KOR",
    "북한": "PRK", "northkorea": "PRK",
    "미국": "USA", "usa": "USA", "us": "USA", "unitedstates": "USA", "america": "USA",
    "일본": "JPN", "japan": "JPN",
    "중국": "CHN", "china": "CHN",
    "독일": "DEU", "germany": "DEU",
    "영국": "GBR", "uk": "GBR", "unitedkingdom": "GBR", "britain": "GBR",
    "프랑스": "FRA", "france": "FRA",
    "인도": "IND", "india": "IND",
    "러시아": "RUS", "russia": "RUS",
    "캐나다": "CAN", "canada": "CAN",
    "호주": "AUS", "australia": "AUS",
    "브라질": "BRA", "brazil": "BRA",
    "이탈리아": "ITA", "italy": "ITA",
    "스페인": "ESP", "spain": "ESP",
    "멕시코": "MEX", "mexico": "MEX",
    "인도네시아": "IDN", "indonesia": "IDN",
    "베트남": "VNM", "vietnam": "VNM",
    "대만": "TWN", "taiwan": "TWN",
    "싱가포르": "SGP", "singapore": "SGP",
    "태국": "THA", "thailand": "THA",
}


def _norm_wb_key(s: str) -> str:
    return "".join(str(s).lower().split())


def _resolve_wb_indicator(indicator: str) -> str:
    """지표명(자연어)→World Bank 코드. 이미 코드(점 포함)면 그대로."""
    if not indicator:
        return indicator
    if "." in indicator:  # NY.GDP.MKTP.CD 같은 원시 코드
        return indicator
    return _WB_INDICATORS.get(_norm_wb_key(indicator), indicator)


def _resolve_wb_country(country: str) -> str:
    """국가명(자연어)→ISO3. 'all'/2~3자 코드/숫자는 그대로."""
    if not country or country == "all":
        return country or "all"
    key = _norm_wb_key(country)
    if key in _WB_COUNTRIES:
        return _WB_COUNTRIES[key]
    # ISO2/ISO3/숫자 코드로 보이면 대문자로 통과
    if country.isalpha() and len(country) in (2, 3):
        return country.upper()
    return country


def _fetch_world_bank_data(tool_input: dict) -> str:
    """World Bank API를 사용하여 국가별 지표 데이터를 가져옵니다."""
    indicator = _resolve_wb_indicator(tool_input.get("indicator"))
    country = _resolve_wb_country(tool_input.get("country", "all"))
    date = tool_input.get("date")
    per_page = tool_input.get("per_page", 50)
    
    # API URL 구성
    # 예: http://api.worldbank.org/v2/country/KOR/indicator/NY.GDP.MKTP.CD?format=json&date=2010:2022
    url = f"http://api.worldbank.org/v2/country/{country}/indicator/{indicator}"
    params = {
        "format": "json",
        "per_page": per_page
    }
    if date:
        params["date"] = date
        
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        # World Bank API 응답 구조: [metadata, data_list]
        if not data or len(data) < 2 or not data[1]:
            return json.dumps({"success": False,
                               "error": f"지표 '{indicator}'(국가: {country})에 대한 데이터를 찾을 수 없습니다."},
                              ensure_ascii=False)
            
        data_list = data[1]

        indicator_name = data_list[0].get("indicator", {}).get("value", indicator)
        country_name = (data_list[0].get("country", {}) or {}).get("value", country)

        # 표준 테이블 통화 + 사람용 요약을 함께 산출
        rows = []
        summary = [f"### World Bank 데이터: {indicator_name} ({country_name})\n"]
        for entry in data_list:
            year = entry.get("date")
            value = entry.get("value")
            if value is not None:
                rows.append([year, value])
                if isinstance(value, (int, float)):
                    fv = f"{value:,.2f}".rstrip('0').rstrip('.')
                else:
                    fv = str(value)
                summary.append(f"- {year}: {fv}")
            else:
                summary.append(f"- {year}: 데이터 없음")

        # 연도 오름차순 (차트/표에 자연스러운 시간 순서; WB는 보통 내림차순 반환)
        rows.sort(key=lambda r: str(r[0]))

        return json.dumps({
            "success": True,
            "indicator": indicator_name,
            "country": country_name,
            # 단일 통화 items(행 dict) — 첫 키=연도(x축 라벨), 둘째=지표값(수치 시리즈).
            # 소비자(chart/spreadsheet)가 items→table 재구성(키 순서=열). §3 table 흡수.
            "items": [{"연도": r[0], indicator_name: r[1]} for r in rows],
            "summary": "\n".join(summary),
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"success": False, "error": f"World Bank API 요청 오류: {str(e)}"}, ensure_ascii=False)


# _search_books 는 2026-08-05 어휘 압축 (6)-2b 에서 culture 패키지 [sense:book]{source:"google"} 로 이주(tool_gbooks.py).


# ── 디스패치 테이블 — 진짜 함수 참조 (--check 가 AST 로 키 정확 비교) ──

_OP_DISPATCHERS = {
    "paper_op": {"search": _paper_search, "download": _paper_download},
    "researcher_op": {"find": _nanet_author_find, "coauthor": _nanet_coauthor},
    "entity_op": {"resolve": _entity_resolve, "detail": _entity_detail},
}

