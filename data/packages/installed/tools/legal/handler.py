"""
법률 정보 검색 도구 (국가법령정보센터 API)

Phase 0 마이그레이션: common 유틸리티 사용
레코드 통화: 검색(lawSearch.do)·상세(lawService.do) 모두 items[{title,meta,summary,url,date,id,…}] 로 매핑.
  → [sense:legal] >> [table:document] / >> [table:spreadsheet] 자동 흐름.
  검색 items 의 id 는 같은 낱말의 {id, target} 에 그대로 넣는 상세 조회 번호다(2026-10-11, 긴문장 53회차 수리).
  원천 원문은 message(검색)·원천 키(상세)에 그대로 두되, 링크의 사용자 식별값(OC)은 지운다.
"""
import sys
import os
import json
import re

# backend/common 모듈 경로 추가
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.api_client import api_call
from common.auth_manager import get_api_key


# 패키지 디렉토리 (config.json fallback용)
_PACKAGE_DIR = os.path.dirname(__file__)

# 법률 API 대상 매핑
_TARGET_MAP = {
    "search_legal_info": None,       # tool_input에서 target 직접 지정
    "get_legal_detail": None,        # tool_input에서 target 직접 지정
    "search_laws": "law",
    "get_law_detail": "law",
    "search_precedents": "prec",
    "get_precedent_detail": "prec",
}

# ---------------------------------------------------------------------------
# 레코드 통화 매핑 (법제처 DRF lawSearch.do 응답 → records)
# ---------------------------------------------------------------------------
#
# 법제처 OPEN API(http://www.law.go.kr/DRF/lawSearch.do) JSON 응답은 target별로
# 최상위 래퍼 키와 결과 배열 키, 항목 필드명이 다르다. 아래는 공식 문서 기준 매핑.
#   - title_keys: 제목 후보 (법령명/사건명 등) — 첫 매칭 사용
#   - meta_keys : meta 줄에 " · " join 할 필드들 (존재분만)
#   - date_keys : 정렬 가능한 대표 날짜 후보 (첫 매칭 → 통화 `date` 칸 병기, YYYY-MM-DD)
#                 ★칸 규약(ibl.md, 2026-08-16 상상훈련 F1): 시행일이 meta 텍스트에만
#                 접히면 "시행일순 정렬"이 원리적으로 불가 — 수치/날짜는 칸으로 병기한다.
#   - id_key    : 상세 링크 구성용 일련번호/ID (있으면 사용)
#   - link_keys : 응답에 상세 링크가 직접 있으면 우선 사용
# 래퍼/배열 키는 generic 탐색으로도 잡히지만, 정확도를 위해 target별로 명시.
_TARGET_FIELDS = {
    # 법령
    "law": {
        "title_keys": ["법령명한글", "법령명", "법령명약칭"],
        "meta_keys": ["법령구분명", "소관부처명", "공포일자", "시행일자", "제개정구분명"],
        "date_keys": ["시행일자", "공포일자"],
        "id_key": "법령일련번호",
        "link_keys": ["법령상세링크"],
    },
    # 영문법령 (구조는 law 계열과 동일/유사)
    "eng_law": {
        "title_keys": ["법령명영문", "법령명한글", "법령명"],
        "meta_keys": ["법령구분명", "소관부처명", "공포일자", "시행일자"],
        "date_keys": ["시행일자", "공포일자"],
        "id_key": "법령일련번호",
        "link_keys": ["법령상세링크"],
    },
    # 판례
    "prec": {
        "title_keys": ["사건명"],
        "meta_keys": ["법원명", "사건번호", "선고일자", "판결유형", "선고"],
        "date_keys": ["선고일자"],
        "id_key": "판례일련번호",
        "link_keys": ["판례상세링크"],
        "extra": {"case_no": "사건번호", "court": "법원명"},
    },
    # 헌재결정
    "detc": {
        "title_keys": ["사건명", "헌재결정례명"],
        "meta_keys": ["헌재결정구분명", "종국일자", "사건번호"],
        "date_keys": ["종국일자"],
        "id_key": "헌재결정례일련번호",
        "link_keys": ["헌재결정례상세링크"],
    },
    # 행정규칙
    "admrul": {
        "title_keys": ["행정규칙명"],
        "extra": {"ministry": "소관부처명"},
        "meta_keys": ["행정규칙종류", "소관부처명", "발령일자", "시행일자", "발령번호"],
        "date_keys": ["시행일자", "발령일자"],
        "id_key": "행정규칙일련번호",
        "link_keys": ["행정규칙상세링크"],
    },
    # 자치법규
    "ordin": {
        "title_keys": ["자치법규명", "자치법규명한글"],
        "meta_keys": ["지자체기관명", "자치법규종류", "공포일자", "시행일자"],
        "date_keys": ["시행일자", "공포일자"],
        "id_key": "자치법규일련번호",
        "link_keys": ["자치법규상세링크"],
    },
    # 법령해석례
    "exp": {
        "title_keys": ["안건명", "법령해석례명"],
        "meta_keys": ["질의기관명", "회신기관명", "회신일자", "안건번호"],
        "date_keys": ["회신일자"],
        "id_key": "법령해석례일련번호",
        "link_keys": ["법령해석례상세링크"],
    },
    # 조약
    "trty": {
        "title_keys": ["조약명", "조약명한글"],
        "meta_keys": ["조약구분명", "발효일자", "체결일자", "관보게재일자"],
        "date_keys": ["발효일자", "체결일자"],
        "id_key": "조약일련번호",
        "link_keys": ["조약상세링크"],
    },
    # 법률용어
    "law_term": {
        "title_keys": ["법령용어명", "법령용어명_한글", "용어명", "법령용어명_한자"],
        "meta_keys": ["출처"],
        "id_key": "법령용어ID",
        "link_keys": ["법령용어상세링크"],
    },
    # 법률서식
    "law_form": {
        "title_keys": ["별표명", "서식명"],
        "meta_keys": ["별표종류", "관련법령명", "소관부처명", "공포일자"],
        "date_keys": ["공포일자"],
        "id_key": "별표일련번호",
        "link_keys": ["별표법령상세링크"],
        "extra": {"file_url": "별표서식파일링크", "pdf_url": "별표서식PDF파일링크", "law_name": "관련법령명"},
    },
}

# 상세 링크 기본 prefix (응답에 직접 링크 없을 때 id로 구성)
_LINK_BASE = "https://www.law.go.kr"
_TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")

# 어휘의 target 이름 → 원천 API target. 나머지는 이름이 같다.
# (exp·eng_law·law_term·law_form 을 그대로 보내면 원천이 빈 응답을 준다 — 2026-10-11 실측)
_API_TARGET = {"exp": "expc", "eng_law": "elaw", "law_term": "lstrm", "law_form": "licbyl"}

# 상세 조회(lawService.do): target별로 검색 행의 어느 칸이 조회 번호이고 어느 인자로 보내는가.
#   id_key   : 검색 items 의 id 칸에 실을 행 필드 — params[0] 인자로 통하는 번호
#   params   : 차례로 시도할 인자 이름(앞의 것이 "일치하는 … 없습니다" 면 다음 것)
#   page     : 사람이 여는 공개 주소(사용자 식별값 없음). {seq} = seq_key 값
_DETAIL = {
    "law":      {"id_key": "법령ID", "params": ["ID", "MST"], "seq_key": "법령일련번호", "page": "/LSW/lsInfoP.do?lsiSeq={seq}"},
    "eng_law":  {"id_key": "법령ID", "params": ["ID", "MST"], "seq_key": "법령일련번호", "page": "/LSW/lsInfoP.do?lsiSeq={seq}&viewCls=engLsInfoR"},
    "prec":     {"id_key": "판례일련번호", "params": ["ID"], "seq_key": "판례일련번호", "page": "/LSW/precInfoP.do?precSeq={seq}"},
    "detc":     {"id_key": "헌재결정례일련번호", "params": ["ID"], "seq_key": "헌재결정례일련번호", "page": "/LSW/detcInfoP.do?detcSeq={seq}"},
    "admrul":   {"id_key": "행정규칙일련번호", "params": ["ID"], "seq_key": "행정규칙일련번호", "page": "/LSW/admRulLsInfoP.do?admRulSeq={seq}"},
    "ordin":    {"id_key": "자치법규ID", "params": ["ID", "MST"], "seq_key": "자치법규일련번호", "page": "/LSW/ordinInfoP.do?ordinSeq={seq}"},
    "exp":      {"id_key": "법령해석례일련번호", "params": ["ID"], "seq_key": "법령해석례일련번호", "page": "/LSW/expcInfoP.do?expcSeq={seq}"},
    "trty":     {"id_key": "조약일련번호", "params": ["ID"], "seq_key": "조약일련번호", "page": "/LSW/trtyInfoP.do?trtySeq={seq}"},
    "law_term": {"id_key": "법령용어ID", "params": ["trmSeqs"], "seq_key": None, "page": None},
    "law_form": {"id_key": "별표일련번호", "params": [], "seq_key": None, "page": None},   # 상세 조회 없음 — 파일 링크가 검색 행에
}
# 상세 한 건의 요약(summary) 칸으로 쓸 원천 필드 후보
_SUMMARY_KEYS = ["판시사항", "질의요지", "법령용어정의", "결정요지", "판결요지"]


def _coerce_list(val):
    """단일 dict 또는 list 를 list 로 정규화."""
    if isinstance(val, list):
        return val
    if isinstance(val, dict):
        return [val]
    return []


def _find_result_rows(data: dict):
    """법제처 응답 dict 에서 결과 행 배열을 찾아 반환.

    구조: {<XxxSearch>: {<rowKey>: [...] , totalCnt:..., ...}}
    target별 행 키(law/prec/admrul...)가 다르므로, Search 래퍼 안에서
    list 또는 dict(단건) 값을 가진 첫 필드를 결과로 본다.
    """
    if not isinstance(data, dict):
        return []
    # 1) *Search 래퍼 우선 — 래퍼가 있으면 그것이 권위. 비어있어도 top-level 로 폴백하지 않음
    #    (그래야 {LawSearch:{totalCnt:"0"}} 같은 빈 결과가 totalCnt 행으로 오인되지 않음).
    for k, v in data.items():
        if isinstance(v, dict) and (isinstance(k, str) and k.endswith("Search") or "totalCnt" in v):
            return _rows_from_container(v)      # 해석례의 래퍼는 "Expc" — 이름이 아니라 totalCnt 로도 알아본다
    # 2) 래퍼 없이 바로 결과 컨테이너인 경우
    return _rows_from_container(data)


def _rows_from_container(container: dict):
    """결과 컨테이너 dict 에서 행 배열 추출 (메타 카운트 필드 제외)."""
    # 명시적으로 흔한 행 키 먼저 (단건이면 dict 로 옴)
    skip_keys = {"totalCnt", "page", "numOfRows", "pageNo", "section", "resultCode", "resultMsg", "키워드", "target", "query"}
    candidates = []
    for k, v in container.items():
        if k in skip_keys:
            continue
        if isinstance(v, list) and v and isinstance(v[0], dict):
            candidates.append(v)
        elif isinstance(v, dict):
            candidates.append([v])
    # 가장 큰 리스트(실제 결과 배열) 선택
    if candidates:
        return max(candidates, key=len)
    return []


def _pick(row: dict, keys):
    """row 에서 keys 중 첫 비어있지 않은 값 반환."""
    for k in keys:
        val = row.get(k)
        if val not in (None, "", "null") and not isinstance(val, (dict, list)):
            return _TAG_RE.sub("", str(val)).strip()     # 검색어 강조 표시(<strong …>) 제거
    return ""


def _norm_date(v) -> str:
    """법제처 날짜(예: '20251001' / '2025.10.01')를 정렬 가능한 'YYYY-MM-DD'로.
    형식을 못 알아보면 빈 문자열 — 어중간한 값을 date 칸에 넣지 않는다."""
    s = str(v or "").strip().replace(".", "").replace("-", "").replace("/", "")
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return ""


def _clean(v) -> str:
    """원천 글의 <br/> 를 줄바꿈으로, 사용자 식별값(OC)을 지운다."""
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return _redact(s.replace("<br/>", "\n").replace("<br>", "\n")).strip()


_OC_RE = re.compile(r"OC=[^&\"'\\\s<]*")


def _redact(s: str) -> str:
    """원천 응답의 링크마다 붙어 오는 API 사용자 식별값을 지운다(값이 바깥 문서·저장 파일로 따라가지 않게)."""
    return _OC_RE.sub("OC=", s) if isinstance(s, str) else s


def _public_url(row: dict, fields: dict, target: str) -> str:
    """사람이 여는 공개 주소. 모르는 대상은 원천 링크에서 식별값만 지운 것."""
    d = _DETAIL.get(target) or {}
    seq = row.get(d.get("seq_key")) if d.get("seq_key") else None
    if d.get("page") and seq not in (None, "", "null"):
        return _LINK_BASE + d["page"].format(seq=seq)
    url = _pick(row, (fields or {}).get("link_keys", []))
    if "/DRF/" in url:
        return ""          # 원천 API 주소는 사용자 식별값 없이는 열리지 않는다 — 싣지 않는다
    if url.startswith("/"):
        url = _LINK_BASE + url
    return _redact(url)


def _row_to_record(row: dict, fields: dict, target: str) -> dict:
    """단일 결과 행 → record{title,meta,summary,url,date?,id?,…}.

    id  = 같은 낱말의 {id, target} 에 그대로 넣는 상세 조회 번호(target별 _DETAIL.id_key).
    date = 대표 날짜 칸 병기(칸 규약 F1, YYYY-MM-DD) — meta 표시 문자열은 그대로 두고
    파이프(sort/filter)가 물 수 있는 칸을 *추가*한다(제거 아님·병기).
    """
    title = _pick(row, fields.get("title_keys", []))
    meta_parts = []
    for mk in fields.get("meta_keys", []):
        v = row.get(mk)
        if v not in (None, "", "null"):
            meta_parts.append(str(v).strip())
    rec = {
        "title": title,
        "meta": " · ".join(meta_parts),
        "summary": "",
        "url": _public_url(row, fields, target),
    }
    d = _norm_date(_pick(row, fields.get("date_keys", [])))
    if d:
        rec["date"] = d                 # 칸 규약 F1: 대표 날짜 병기 (시행일순 정렬 가능)
    item_id = _pick(row, [(_DETAIL.get(target) or {}).get("id_key") or fields.get("id_key") or ""])
    if item_id:
        rec["id"] = item_id
    for name, key in (fields.get("extra") or {}).items():
        v = _pick(row, [key])
        if v:
            rec[name] = (_LINK_BASE + v) if v.startswith("/") else v
    if not rec["url"] and rec.get("pdf_url"):
        rec["url"] = rec["pdf_url"]
    return rec


def _generic_record(row: dict) -> dict:
    """필드 매핑이 없는 target 용 폴백: 제목/링크처럼 보이는 필드 추정."""
    title = ""
    url = ""
    meta_parts = []
    for k, v in row.items():
        if v in (None, "", "null") or not isinstance(k, str):
            continue
        sv = str(v).strip()
        kl = k
        if not title and ("명" in kl or "사건" in kl or "title" in kl.lower()):
            title = sv
            continue
        if not url and ("링크" in kl or "link" in kl.lower() or sv.startswith("http")):
            url = sv if sv.startswith("http") else (_LINK_BASE + sv if sv.startswith("/") else sv)
            continue
        # 일련번호/ID/긴 본문은 meta 에서 제외
        if "일련번호" in kl or kl.endswith("ID") or len(sv) > 60:
            continue
        meta_parts.append(sv)
    if not title:
        # 첫 문자열 값을 제목으로
        for v in row.values():
            if isinstance(v, str) and v.strip():
                title = v.strip()
                break
    return {
        "title": title,
        "meta": " · ".join(meta_parts[:5]),
        "summary": "",
        "url": url,
    }


def _build_records(raw: str, target: str):
    """raw JSON 문자열 → (records list 또는 None).

    파싱 실패·원천 오류 응답이면 None, 0건이면 빈 목록.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    # 에러 응답({result:"...실패...", msg:...})은 records 만들지 않음
    if "result" in data and "msg" in data and not any(
        isinstance(v, (list, dict)) for v in data.values()
    ):
        return None
    rows = _find_result_rows(data)
    rows = _coerce_list(rows)
    if not rows:
        return []          # 0건은 빈 목록(파싱 실패의 None 과 구별)
    fields = _TARGET_FIELDS.get(target)
    records = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        rec = _row_to_record(row, fields, target) if fields else _generic_record(row)
        # 제목 없는 행은 폴백 시도, 그래도 없으면 스킵
        if not rec.get("title") and fields:
            rec = _generic_record(row)
        if rec.get("title"):
            records.append(rec)
    return records


def _search_meta(raw_str: str) -> dict:
    """검색 응답의 전체 건수와 검색 범위(section)."""
    try:
        data = json.loads(raw_str)
    except (ValueError, TypeError):
        return {}
    for k, v in (data.items() if isinstance(data, dict) else []):
        if isinstance(v, dict) and ("totalCnt" in v or "section" in v):
            try:
                total = int(v.get("totalCnt"))
            except (TypeError, ValueError):
                total = None
            return {"total": total, "section": v.get("section")}
    return {}


def _search(api_key: str, target: str, query: str) -> dict:
    """검색(lawSearch.do) → 레코드 통화.

    이름(법령명·사건명 등)에서 먼저 찾고, 0건이면 본문에서 한 번 더 찾는다 — 어느 쪽에서 찾았는지는
    search_scope 가 말한다. 0건도 items:[] · count:0 이다. total 은 원천의 전체 건수(items 는 첫 쪽).
    """
    api_target = _API_TARGET.get(target, target)
    out, scope = None, "name"
    for scope, extra in (("name", {}), ("body", {"search": 2})):
        raw = api_call("law", "/lawSearch.do",
                       params={"OC": api_key, "target": api_target, "type": "JSON", "query": query, **extra},
                       raw_response=True)
        raw_str = raw if isinstance(raw, str) else str(raw)
        try:
            records = _build_records(raw_str, target)
        except Exception:
            records = None
        if records is None:
            if out is not None:
                break          # 본문 재검색이 실패하면 이름 검색의 0건 응답을 그대로 낸다
            return {"success": False, "error_code": "SOURCE_ERROR",
                    "error": f"법령정보 원천이 '{target}' 검색에 읽을 수 없는 응답을 주었습니다: {_redact(raw_str)[:200]}"}
        meta = _search_meta(raw_str)
        out = {"success": True, "message": _redact(raw_str), "items": records, "count": len(records),
               "total": meta.get("total") if meta.get("total") is not None else len(records),
               "search_scope": scope}
        if records:
            break
    if out["search_scope"] == "body" and out["items"]:
        out["note"] = "이름(법령명·사건명)에는 맞는 것이 없어 본문에서 찾은 결과입니다."
    elif not out["items"]:
        out["search_scope"] = "name+body"
        out["note"] = "이름과 본문 어디에도 맞는 것이 없습니다."
    if out["total"] > out["count"]:
        # 검색의 첫 쪽은 요청한 전체의 절단이 아니라 원천이 고른 상위 결과다 — 절단 표지(실행기가 불완전 원천으로
        # 거절한다)를 세우지 않고, 전체 건수(total)와 안내로 "더 있다" 를 말한다.
        out["note"] = (out.get("note", "") + f" 전체 {out['total']}건 중 첫 {out['count']}건입니다 — 검색어를 좁히세요.").strip()
    return out


def _lines(v) -> list:
    """글·목록·중첩 목록을 줄 목록으로."""
    if v in (None, ""):
        return []
    if isinstance(v, str):
        return [v.strip()] if v.strip() else []
    if isinstance(v, list):
        return [line for x in v for line in _lines(x)]
    return []


def _article_records(law: dict, law_name: str) -> list:
    """법령 전문의 조문 단위 → 조마다 한 행 {no:"제6조의3", title, text, date, chapter}."""
    units = _coerce_list(((law.get("조문") or {}) if isinstance(law.get("조문"), dict) else {}).get("조문단위"))
    out, chapter = [], ""
    for j in units:
        if not isinstance(j, dict):
            continue
        head = " ".join(_lines(j.get("조문내용")))
        if j.get("조문여부") != "조문":
            chapter = head or chapter       # 편·장·절 머리 — 뒤 조문들의 chapter 로
            continue
        no = f"제{str(j.get('조문번호', '')).strip()}조"
        branch = str(j.get("조문가지번호") or "").strip()
        if branch and branch != "0":
            no += f"의{branch}"
        lines = _lines(j.get("조문내용"))
        for h in _coerce_list(j.get("항")):
            lines += _lines(h.get("항내용"))
            for o in _coerce_list(h.get("호")):
                lines += _lines(o.get("호내용"))
                for m in _coerce_list(o.get("목")):
                    lines += _lines(m.get("목내용"))
        name = str(j.get("조문제목") or "").strip()
        rec = {"title": f"{no}({name})" if name else no, "meta": law_name, "summary": "", "url": "",
               "no": no, "article_title": name, "text": _clean("\n".join(lines)), "chapter": chapter}
        d = _norm_date(j.get("조문시행일자"))
        if d:
            rec["date"] = d
        out.append(rec)
    return out


def _not_found_text(data) -> str:
    """원천의 '못 찾음' 응답이면 그 글, 아니면 빈 글. 모양: {"Law": "일치하는 … 없습니다."} 또는 빈 객체·빈 글."""
    if data in (None, "", {}, []):
        return "원천이 빈 응답을 주었습니다."
    if isinstance(data, dict) and len(data) == 1:
        v = next(iter(data.values()))
        if isinstance(v, str):
            return v.strip() or "원천이 빈 응답을 주었습니다."
    return ""


def _detail(api_key: str, target: str, item_id) -> dict:
    """상세(lawService.do) → 원천 키는 그대로 두고 items 를 더한다.

    법령: items = 조마다 한 행(no·title·text·date·chapter) + law{name,id,mst,enforce_date,…}.
    그 밖: items = 한 행(title·meta·summary·date·id + 원천 필드 글).
    못 찾으면 실패(NOT_FOUND)다 — 원천의 "일치하는 …없습니다" 를 성공으로 넘기지 않는다.
    """
    spec = _DETAIL.get(target) or {"params": ["ID"]}
    if not spec.get("params"):
        return {"success": False, "error_code": "UNSUPPORTED_OPERATION",
                "error": f"'{target}' 은 상세 조회가 없습니다. 검색 결과 행의 file_url·pdf_url 을 쓰세요."}
    api_target = _API_TARGET.get(target, target)
    data, reason, tried = None, "", []
    for param in spec["params"]:
        raw = api_call("law", "/lawService.do",
                       params={"OC": api_key, "target": api_target, "type": "JSON", param: item_id},
                       raw_response=True)
        raw_str = _redact(raw if isinstance(raw, str) else str(raw))
        tried.append(param)
        try:
            parsed = json.loads(raw_str) if raw_str.strip() else {}
        except (ValueError, TypeError):
            return {"success": False, "error_code": "SOURCE_ERROR",
                    "error": f"법령정보 원천이 읽을 수 없는 응답을 주었습니다: {raw_str[:200]}"}
        reason = _not_found_text(parsed)
        if not reason:
            data = parsed
            break
    if data is None:
        hint = "검색 결과 items 의 id 를 target 과 함께 넣으세요."
        if target in ("exp", "eng_law", "law_term", "law_form") or target not in _DETAIL:
            hint += f" target '{target}' 의 번호인지도 확인하세요."
        return {"success": False, "error_code": "NOT_FOUND",
                "error": f"{target} 번호 '{item_id}' 로 찾지 못했습니다 — 원천 응답: {reason} {hint}",
                "id": str(item_id), "target": target}
    out = {"success": True, "target": target, "id": str(item_id), **data}
    service = next((v for v in data.values() if isinstance(v, dict)), {})
    # 기본정보가 한 겹 안에 있는 대상(행정규칙·자치법규·조약 등)은 그 칸들을 같은 높이로 올려 읽는다
    service = {**{k: v for sub_key, sub in service.items() if isinstance(sub, dict) and "기본정보" in str(sub_key)
                  for k, v in sub.items()}, **service}
    if target == "law" and isinstance(data.get("법령"), dict):
        law = data["법령"]
        info = law.get("기본정보") if isinstance(law.get("기본정보"), dict) else {}
        name = str(info.get("법령명_한글") or "").strip()
        items = _article_records(law, name)
        url = f"{_LINK_BASE}/LSW/lsInfoP.do?lsId={info.get('법령ID')}" if info.get("법령ID") else ""
        for it in items:
            it["url"] = url
        out["law"] = {"name": name, "id": str(info.get("법령ID") or ""), "enforce_date": _norm_date(info.get("시행일자")),
                      "promulgation_date": _norm_date(info.get("공포일자")), "revision": str(info.get("제개정구분") or ""),
                      "kind": (info.get("법종구분") or {}).get("content", "") if isinstance(info.get("법종구분"), dict) else "",
                      "url": url}
        out["items"], out["count"] = items, len(items)
        return out
    fields = _TARGET_FIELDS.get(target) or {}
    rec = _row_to_record(service, fields, target) if fields else _generic_record(service)
    if not rec.get("title"):
        rec = {**_generic_record(service), **{k: v for k, v in rec.items() if v}}
    rec["id"] = str(item_id)
    rec["summary"] = next((_clean(service[k]) for k in _SUMMARY_KEYS if service.get(k) not in (None, "")), "")
    for k, v in service.items():      # 원천 필드의 글(한글 이름 그대로, <br/> 는 줄바꿈으로)
        if isinstance(k, str) and k not in rec and isinstance(v, str):
            rec[k] = _clean(v)
    out["items"], out["count"] = [rec], 1
    return out


def execute(tool_input: dict, context) -> str:
    """법률 패키지 도구 실행 핸들러 (ToolContext 기반 신규 시그니처)."""
    tool_name = context.tool_name
    api_key = get_api_key("LAW_API_KEY", package_dir=_PACKAGE_DIR)
    if not api_key:
        return json.dumps({"success": False, "error": "Law API 키가 설정되지 않았습니다. 패키지 폴더의 config.json에 'api_key'를 입력하거나 LAW_API_KEY 환경 변수를 설정해주세요."}, ensure_ascii=False)

    target = _TARGET_MAP.get(tool_name) or tool_input.get("target") or "law"
    item_id = tool_input.get("id") or tool_input.get("law_id") or tool_input.get("precedent_id")
    query = tool_input.get("query")

    if tool_name == "legal_lookup":
        if item_id:
            return _detail(api_key, target, item_id)
        if query:
            return _search(api_key, target, query)
        return json.dumps({"success": False, "error": "query 또는 id 중 하나가 필요합니다."}, ensure_ascii=False)
    if tool_name in ("search_legal_info", "search_laws", "search_precedents"):
        return _search(api_key, target, query)
    if tool_name in ("get_legal_detail", "get_law_detail", "get_precedent_detail"):
        return _detail(api_key, target, item_id)
    return json.dumps({"success": False, "error": f"알 수 없는 도구: {tool_name}"}, ensure_ascii=False)
