import importlib.util
from pathlib import Path

current_dir = Path(__file__).parent

def load_module(module_name):
    module_path = current_dir / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        records.append({
            "title": title,
            "meta": " · ".join(x for x in meta_parts if x),
            "summary": "",
            "url": it.get("상세URL") or "",
        })
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
        count = tool_input.get("count", 10)
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

    if tool_name == "search_kstartup":
        tool = load_module("tool_kstartup")
        keyword = tool_input.get("keyword", "")
        count = tool_input.get("count", 10)
        return _attach_records(tool.search_kstartup(keyword, count))

    elif tool_name == "search_mss_biz":
        tool = load_module("tool_mss_biz")
        keyword = tool_input.get("keyword", "")
        count = tool_input.get("count", 10)
        return _attach_records(tool.search_mss_biz(keyword, count))

    else:
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
