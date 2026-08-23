from pathlib import Path

current_dir = Path(__file__).parent

import os
import sys

_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "backend"))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)
from common.pkg_utils import load_sibling

def load_module(module_name):
    """같은 디렉토리의 형제 모듈 로드 — 정본은 common.pkg_utils.load_sibling (감사 ⑥)"""
    return load_sibling(__file__, module_name)


def _biz_to_records(data: list) -> list:
    """지원사업 공고 레코드 → 레코드 통화 records[{title,meta,summary,url,image}].
    title=사업명 · meta=유형·기관·마감일·상태 등 존재하는 것만 join · url=상세URL."""
    records = []
    for it in (data or []):
        if not isinstance(it, dict):
            continue
        title = it.get("사업명") or ""
        meta_parts = [
            it.get("사업유형"),
            it.get("주관기관") or it.get("담당부서"),
        ]
        deadline = it.get("접수마감일")
        if deadline:
            meta_parts.append(f"마감 {deadline}")
        status = it.get("공고상태")
        if status:
            meta_parts.append(status)
        rec = {
            "title": title,
            "meta": " · ".join(x for x in meta_parts if x),
            "summary": "",
            "url": it.get("상세URL") or "",
        }
        # 칸 규약 3(날짜, F1-date 2026-08-16 5회차): 마감일이 meta 텍스트에만 있으면
        # "마감 임박순" 정렬 불가(legal 시행일 동형) — end_date 병기(YYYY-MM-DD).
        _d = str(deadline or "").strip().replace(".", "").replace("-", "").replace("/", "")
        if len(_d) == 8 and _d.isdigit():
            rec["end_date"] = f"{_d[:4]}-{_d[4:6]}-{_d[6:]}"
        records.append(rec)
    return records


def _attach_records(result):
    """data 목록이 있으면 단일 통화 items(records-관습 카드 shape) 부착."""
    if isinstance(result, dict) and isinstance(result.get("data"), list):
        result["items"] = _biz_to_records(result["data"])
    return result

def execute(tool_input: dict, context):
    """IndieBiz OS에서 도구를 호출할 때 실행되는 메인 핸들러 (ToolContext 기반 신규 시그니처)."""
    tool_name = context.tool_name

    if tool_name == "startup_search":
        query = tool_input.get("query") or tool_input.get("keyword", "")
        # 기본 kstartup — 중기부(MSS) data.go.kr API 폐기로 all 은 실패 호출만 낭비.
        # source=all/mss 는 여전히 호출 가능(MSS 는 graceful 강등).
        source = tool_input.get("source", "kstartup")
        # ★정본 limit(별칭 count — ibl_actions.yaml aliases). 관문이 count→limit 로
        #   정규화하지만 직접 호출(REST·앱)도 있으니 둘 다 읽는다.
        count = tool_input.get("limit", tool_input.get("count", 10))
        if source == "kstartup":
            tool = load_module("tool_kstartup")
            return _attach_records(tool.search_kstartup(query, count))
        elif source == "mss":
            tool = load_module("tool_mss_biz")
            return _attach_records(tool.search_mss_biz(query, count))
        else:
            ks = load_module("tool_kstartup").search_kstartup(query, count)
            mss = load_module("tool_mss_biz").search_mss_biz(query, count)
            # source=all: 합쳐진 봉투엔 최상위 data가 없으므로 두 소스를 합쳐 items로 부착.
            records = []
            if isinstance(ks, dict) and isinstance(ks.get("data"), list):
                records += _biz_to_records(ks["data"])
            if isinstance(mss, dict) and isinstance(mss.get("data"), list):
                records += _biz_to_records(mss["data"])
            return {"kstartup": ks, "mss": mss, "items": records}

    return {
        "success": False,
        "error": f"Unknown tool: {tool_name}"
    }

def get_definitions():
    """모든 도구 정의 반환"""
    tool_kstartup = load_module("tool_kstartup")
    tool_mss = load_module("tool_mss_biz")
    return [
        tool_kstartup.get_tool_definition(),
        tool_mss.get_tool_definition()
    ]
