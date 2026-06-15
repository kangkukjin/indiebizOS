"""
법률 정보 검색 도구 (국가법령정보센터 API)

Phase 0 마이그레이션: common 유틸리티 사용
레코드 통화: 목록 검색(lawSearch.do)의 raw JSON 을 파싱해 records[{title,meta,summary,url}] 로 매핑.
  → [sense:legal] >> [engines:document] / >> [engines:spreadsheet] 자동 흐름.
  비파괴: message 에 원래 raw 문자열 유지(파싱 실패 시 records 생략, 기존 동작 그대로).
"""
import sys
import os
import json

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
#   - id_key    : 상세 링크 구성용 일련번호/ID (있으면 사용)
#   - link_keys : 응답에 상세 링크가 직접 있으면 우선 사용
# 래퍼/배열 키는 generic 탐색으로도 잡히지만, 정확도를 위해 target별로 명시.
_TARGET_FIELDS = {
    # 법령
    "law": {
        "title_keys": ["법령명한글", "법령명", "법령명약칭"],
        "meta_keys": ["법령구분명", "소관부처명", "공포일자", "시행일자", "제개정구분명"],
        "id_key": "법령일련번호",
        "link_keys": ["법령상세링크"],
    },
    # 영문법령 (구조는 law 계열과 동일/유사)
    "eng_law": {
        "title_keys": ["법령명영문", "법령명한글", "법령명"],
        "meta_keys": ["법령구분명", "소관부처명", "공포일자", "시행일자"],
        "id_key": "법령일련번호",
        "link_keys": ["법령상세링크"],
    },
    # 판례
    "prec": {
        "title_keys": ["사건명"],
        "meta_keys": ["법원명", "사건번호", "선고일자", "판결유형", "선고"],
        "id_key": "판례일련번호",
        "link_keys": ["판례상세링크"],
    },
    # 헌재결정
    "detc": {
        "title_keys": ["사건명", "헌재결정례명"],
        "meta_keys": ["헌재결정구분명", "종국일자", "사건번호"],
        "id_key": "헌재결정례일련번호",
        "link_keys": ["헌재결정례상세링크"],
    },
    # 행정규칙
    "admrul": {
        "title_keys": ["행정규칙명"],
        "meta_keys": ["행정규칙종류", "소관부처명", "발령일자", "시행일자", "발령번호"],
        "id_key": "행정규칙일련번호",
        "link_keys": ["행정규칙상세링크"],
    },
    # 자치법규
    "ordin": {
        "title_keys": ["자치법규명", "자치법규명한글"],
        "meta_keys": ["지자체기관명", "자치법규종류", "공포일자", "시행일자"],
        "id_key": "자치법규일련번호",
        "link_keys": ["자치법규상세링크"],
    },
    # 법령해석례
    "exp": {
        "title_keys": ["안건명", "법령해석례명"],
        "meta_keys": ["질의기관명", "회신기관명", "회신일자", "안건번호"],
        "id_key": "법령해석례일련번호",
        "link_keys": ["법령해석례상세링크"],
    },
    # 조약
    "trty": {
        "title_keys": ["조약명", "조약명한글"],
        "meta_keys": ["조약구분명", "발효일자", "체결일자", "관보게재일자"],
        "id_key": "조약일련번호",
        "link_keys": ["조약상세링크"],
    },
    # 법률용어
    "law_term": {
        "title_keys": ["법령용어명", "용어명"],
        "meta_keys": ["출처"],
        "id_key": "법령용어ID",
        "link_keys": ["법령용어상세링크"],
    },
    # 법률서식
    "law_form": {
        "title_keys": ["서식명"],
        "meta_keys": ["소관부처명", "법령명"],
        "id_key": "서식일련번호",
        "link_keys": ["서식상세링크"],
    },
}

# 상세 링크 기본 prefix (응답에 직접 링크 없을 때 id로 구성)
_LINK_BASE = "https://www.law.go.kr"


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
        if isinstance(k, str) and k.endswith("Search") and isinstance(v, dict):
            return _rows_from_container(v)
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
        if val not in (None, "", "null"):
            return str(val).strip()
    return ""


def _row_to_record(row: dict, fields: dict, target: str) -> dict:
    """단일 결과 행 → record{title,meta,summary,url}."""
    title = _pick(row, fields.get("title_keys", []))
    meta_parts = []
    for mk in fields.get("meta_keys", []):
        v = row.get(mk)
        if v not in (None, "", "null"):
            meta_parts.append(str(v).strip())
    # url: 직접 링크 우선, 없으면 id 로 구성 시도
    url = _pick(row, fields.get("link_keys", []))
    if url and url.startswith("/"):
        url = _LINK_BASE + url
    if not url:
        id_key = fields.get("id_key")
        item_id = row.get(id_key) if id_key else None
        if item_id not in (None, "", "null"):
            url = f"{_LINK_BASE}/DRF/lawService.do?OC=&target={target}&type=HTML&ID={item_id}"
    return {
        "title": title,
        "meta": " · ".join(meta_parts),
        "summary": "",
        "url": url,
    }


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

    파싱 실패/빈 결과면 None 반환(호출 측에서 records 생략 → 기존 동작 유지).
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
        return None
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
    return records or None


def _wrap_search_result(raw, target: str) -> dict:
    """검색(lawSearch.do) raw 응답을 레코드 통화 dict 로 변환.

    비파괴: message 에 raw 문자열(또는 str화)을 그대로 넣고, 파싱 성공 시에만 records 추가.
    """
    raw_str = raw if isinstance(raw, str) else str(raw)
    out = {"success": True, "message": raw_str}
    try:
        records = _build_records(raw_str, target)
    except Exception:
        records = None  # 파싱 중 어떤 예외도 기존 동작을 깨지 않음
    if records:
        out["records"] = records
        out["count"] = len(records)
    return out


def execute(tool_input: dict, context) -> str:
    """법률 패키지 도구 실행 핸들러 (ToolContext 기반 신규 시그니처)."""
    tool_name = context.tool_name
    api_key = get_api_key("LAW_API_KEY", package_dir=_PACKAGE_DIR)
    if not api_key:
        return "에러: Law API 키가 설정되지 않았습니다. 패키지 폴더의 config.json에 'api_key'를 입력하거나 LAW_API_KEY 환경 변수를 설정해주세요."

    if tool_name == "legal_lookup":
        query = tool_input.get("query")
        item_id = tool_input.get("id") or tool_input.get("law_id") or tool_input.get("precedent_id")
        target = tool_input.get("target", "law")
        if item_id:
            # 상세 조회(lawService.do)는 전문(단건)이라 레코드 통화 비대상 — 기존처럼 raw 반환
            result = api_call(
                "law", "/lawService.do",
                params={"OC": api_key, "target": target, "type": "JSON", "ID": item_id},
                raw_response=True,
            )
            return result if isinstance(result, str) else str(result)
        elif query:
            # 목록 검색(lawSearch.do) → 레코드 통화
            result = api_call(
                "law", "/lawSearch.do",
                params={"OC": api_key, "target": target, "type": "JSON", "query": query},
                raw_response=True,
            )
            return _wrap_search_result(result, target)
        else:
            return "에러: query 또는 id 중 하나가 필요합니다."

    if tool_name in ("search_legal_info", "search_laws", "search_precedents"):
        target = _TARGET_MAP.get(tool_name) or tool_input.get("target", "law")
        result = api_call(
            "law", "/lawSearch.do",
            params={
                "OC": api_key,
                "target": target,
                "type": "JSON",
                "query": tool_input.get("query"),
            },
            raw_response=True,
        )
        return _wrap_search_result(result, target)

    elif tool_name in ("get_legal_detail", "get_law_detail", "get_precedent_detail"):
        target = _TARGET_MAP.get(tool_name) or tool_input.get("target", "law")
        item_id = tool_input.get("id") or tool_input.get("law_id") or tool_input.get("precedent_id")
        result = api_call(
            "law", "/lawService.do",
            params={
                "OC": api_key,
                "target": target,
                "type": "JSON",
                "ID": item_id,
            },
            raw_response=True,
        )
        return result if isinstance(result, str) else str(result)

    return f"알 수 없는 도구: {tool_name}"
